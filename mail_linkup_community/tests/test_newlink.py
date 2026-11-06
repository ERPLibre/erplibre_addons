# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""NewLink by phone and by personal code (T-29, LU-F-020 RM3, RM4, RM6,
LU-F-016 RM7, LU-F-112 RM2, Q-21, Q-25): a share link that LinkUp never
sends, attached by the number of the invitation; a code that reaches its
member inside LinkUp when their preference allows it."""

import re

from odoo.tests import HttpCase, tagged

from .common import SIGNUP_FORM, LinkupCommunityCase

PHONE = "+1 514 555 0123"
PASSWORD = "linkup-Phone-2026"


class LinkupNewlinkMixin:
    def _invite(self, author=None, **invite):
        author = author or self.sam
        reflet = self._draft(author)
        result = reflet.with_user(author).action_send(
            invite=dict(invite, name="Camille")
        )
        return reflet, result, self.Invitation.sudo().browse(result["id"])

    def _token(self, result):
        match = re.search(
            r"/linkup/invite/([A-Za-z0-9_-]{20,})$", result["share_url"]
        )
        self.assertTrue(match)
        return match.group(1)


@tagged("post_install", "-at_install")
class TestLinkupNewlinkPhone(LinkupNewlinkMixin, LinkupCommunityCase):
    def test_share_link_in_the_answer_only(self):
        """RM3, Q-25: no message leaves; the answer holds the share link,
        the masked number and the channel; a new sending gives a new link
        and voids the former one."""
        reflet, result, invitation = self._invite(phone=PHONE)
        self.assertEqual(reflet.state, "pending_invite")
        self.assertEqual(result["channel"], "phone")
        self.assertEqual(result["email"], "•••23")
        token = self._token(result)
        self.assertEqual(invitation.phone, "+15145550123")
        self.assertFalse(invitation.email)
        self.assertFalse(
            self.env["mail.mail"].sudo().search([("body_html", "like", token)])
        )
        listed = self.Invitation.with_user(self.sam).linkup_invitations_info()
        self.assertNotIn("share_url", listed["invitations"][0])
        again = invitation.with_user(self.sam).action_resend()
        self.assertNotEqual(self._token(again), token)
        self.assertFalse(self.Invitation._linkup_find(token))

    def test_one_channel_per_invitation(self):
        """An invitation names one channel; an invalid number is refused."""
        reflet = self._draft()
        with self.assertLinkupCode("linkup.validation", "phone"):
            reflet.with_user(self.sam).action_send(
                invite={
                    "email": "camille.nouvelle@example.com",
                    "phone": PHONE,
                }
            )
        with self.assertLinkupCode("linkup.validation", "phone"):
            reflet.with_user(self.sam).action_send(invite={"phone": "12"})

    def test_number_attaches_the_reflection(self):
        """RM4: a logged-in member who types the number of the invitation
        receives the reflection; another number does not, five wrong
        numbers expire it."""
        reflet, _result, invitation = self._invite(phone=PHONE)
        wrong = invitation.with_context(linkup_typed_phone="514 555 0000")
        with self.assertLinkupCode("linkup.unavailable"):
            wrong._linkup_open_for(self.luce)
        right = invitation.with_context(linkup_typed_phone="(514) 555-0123")
        self.assertTrue(right._linkup_open_for(self.luce))
        self.assertEqual(reflet.recipient_id, self.luce)
        self.assertEqual(reflet.state, "sent")
        other, _result, invitation2 = self._invite(phone=PHONE)
        for _attempt in range(5):
            invitation2._linkup_wrong_phone()
        self.assertEqual(invitation2.state, "expired")
        self.assertEqual(other.state, "expired")


@tagged("post_install", "-at_install")
class TestLinkupNewlinkCode(LinkupNewlinkMixin, LinkupCommunityCase):
    def setUp(self):
        super().setUp()
        self.luce_code = self.luce.sudo()._linkup_code()

    def test_code_reaches_the_member(self):
        """LU-F-112 RM2, RM6: by default a member receives the invitations
        that name their code, inside LinkUp; confirming links the pair and
        tells the inviter."""
        self._bus_reset()
        reflet, result, invitation = self._invite(code=self.luce_code.lower())
        self.assertEqual(result["channel"], "code")
        self.assertEqual(invitation.invitee_id, self.luce)
        self.assertFalse(self._link(self.sam, self.luce))
        received = self.Invitation.with_user(
            self.luce
        ).linkup_received_invitations()
        self.assertEqual([info["id"] for info in received], invitation.ids)
        answer = invitation.with_user(self.luce).action_accept_received()
        self.assertTrue(answer["delivered"])
        self.assertEqual(reflet.state, "confirmed")
        self.assertEqual(self._link(self.sam, self.luce).state, "active")
        sent = {
            kind: [
                target
                for target, kind2, _p in self._bus_sent()
                if kind2 == kind
            ]
            for kind in (
                "linkup.invitation/received",
                "linkup.invitation/accepted",
            )
        }
        self.assertIn(self.luce.partner_id, sent["linkup.invitation/received"])
        self.assertIn(self.sam.partner_id, sent["linkup.invitation/accepted"])

    def test_preference_of_the_member(self):
        """LU-F-016 RM7: "nobody" receives nothing; "code" (the default)
        refuses an address; "email or code" accepts it. Sam reads the same
        answer in every case."""
        self.luce.sudo().linkup_first_reflet_scope = "nobody"
        _reflet, nobody, invitation = self._invite(code=self.luce_code)
        self.assertFalse(invitation.invitee_id)
        self.luce.sudo().linkup_first_reflet_scope = "code"
        _reflet, by_email, invitation = self._invite(email=self.luce.email)
        self.assertFalse(invitation.invitee_id)
        self.assertFalse(self._mails_to(self.luce.email))
        self.luce.sudo().linkup_first_reflet_scope = "email_or_code"
        _reflet, _result, invitation = self._invite(email=self.luce.email)
        self.assertEqual(invitation.invitee_id, self.luce)
        keys = ("state", "channel")
        self.assertEqual(
            {key: nobody[key] for key in keys},
            {"state": "sent", "channel": "code"},
        )
        self.assertEqual(by_email["state"], "sent")

    def test_unknown_code_reaches_nobody(self):
        """A code naming nobody gives the same answer as a valid one and
        reaches nobody; the own code and a malformed one are refused; the
        tries count against the daily limit of the invitations."""
        reflet = self._draft()
        own = self.sam.sudo()._linkup_code()
        with self.assertLinkupCode("linkup.validation", "code"):
            reflet.with_user(self.sam).action_send(invite={"code": own})
        with self.assertLinkupCode("linkup.validation", "code"):
            reflet.with_user(self.sam).action_send(invite={"code": "ZZ"})
        _reflet, unknown, invitation = self._invite(code="ZZZZZ-ZZZZZ")
        _reflet, known, _invitation = self._invite(code=self.luce_code)
        self.assertFalse(invitation.invitee_id)
        for key in ("state", "channel", "email", "name"):
            self.assertEqual(unknown[key], known[key])
        quota = self.Invitation.with_user(self.sam).linkup_invitations_info()
        self.assertEqual(quota["quota"]["used"], 2)


@tagged("post_install", "-at_install")
class TestLinkupNewlinkPhoneRoute(
    LinkupNewlinkMixin, LinkupCommunityCase, HttpCase
):
    """The share link through HTTP: a signup with the number attaches the
    reflection and verifies nothing; another number lets it expire."""

    def _signup(self, token, email, phone):
        url = f"/linkup/invite/{token}"
        page = self.url_open(url)
        self.assertIn('name="linkup_phone"', page.text)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        data = dict(
            SIGNUP_FORM,
            login=email,
            name="Camille",
            password=PASSWORD,
            confirm_password=PASSWORD,
            linkup_phone=phone,
            csrf_token=csrf.group(1),
        )
        response = self.url_open(url, data=data, allow_redirects=False)
        self.opener.cookies.clear()
        return response

    def _user(self, email):
        return self.env["res.users"].sudo().search([("email", "=", email)])

    def test_signup_with_the_number(self):
        reflet, result, _invitation = self._invite(phone=PHONE)
        response = self._signup(
            self._token(result), "camille.tel@example.com", "514-555-0123"
        )
        self.assertIn(response.status_code, (302, 303))
        user = self._user("camille.tel@example.com")
        self.env.invalidate_all()
        self.assertEqual(reflet.recipient_id, user)
        # The address of a share link is not proven by the link.
        self.assertFalse(user.linkup_email_verified)

    def test_signup_with_another_number(self):
        reflet, result, _invitation = self._invite(phone=PHONE)
        self._signup(
            self._token(result), "dominique.tel@example.com", "514-555-9999"
        )
        user = self._user("dominique.tel@example.com")
        self.assertTrue(user)
        self.env.invalidate_all()
        self.assertFalse(reflet.recipient_id)
        self.assertEqual(reflet.state, "expired")

    def test_logged_in_member_types_the_number(self):
        """A logged-in member reads the form of the number, and a wrong
        number says so without using the link."""
        reflet, result, invitation = self._invite(phone=PHONE)
        token = self._token(result)
        self.authenticate(self.jacques.login, self.jacques.login)
        url = f"/linkup/invite/{token}"
        page = self.url_open(url)
        self.assertIn("o-linkup-InvitePage-phone", page.text)
        csrf = re.search(
            r'name="csrf_token" value="([^"]+)"', page.text
        ).group(1)
        wrong = self.url_open(
            url, data={"linkup_phone": "5145550000", "csrf_token": csrf}
        )
        self.assertIn("alert-danger", wrong.text)
        self.assertEqual(invitation.state, "sent")
        right = self.url_open(
            url,
            data={"linkup_phone": PHONE, "csrf_token": csrf},
            allow_redirects=False,
        )
        self.assertIn(right.status_code, (302, 303))
        self.env.invalidate_all()
        self.assertEqual(reflet.recipient_id, self.jacques)
