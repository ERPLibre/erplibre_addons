# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""NewLink by email (T-29, LU-F-020, LU-F-026 RM2, LU-NF-015): the
invitation of a person who is not a member, its generic email, its link
used once by a signup that attaches the reflection to the invited address
only, the answer the same whoever holds the address, the refusal list,
the cancellation, the new sending, the daily limit and the purge.
"""

import re
from datetime import timedelta

from odoo import fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from .common import LinkupRefletCase

# Addresses no test user holds.
UNKNOWN = "camille.nouvelle@example.com"
OTHER = "dominique.autre@example.com"
YOU_SAID = "zz-invite-you-said"
UNDERSTOOD = "zz-invite-understood"
TOKEN_RE = re.compile(r"/linkup/invite/([A-Za-z0-9_-]{20,})")


class LinkupInvitationMixin:
    def setUp(self):
        super().setUp()
        self.Invitation = self.env["linkup.invitation"]
        self.Mail = self.env["mail.mail"].sudo()

    def _invite(self, email=UNKNOWN, author=None, name="Camille", **vals):
        """Send a new draft of ``author`` (Sam) by NewLink; return the
        reflection and the answer of the server."""
        author = author or self.sam
        reflet = self._draft(
            author, you_said=YOU_SAID, understood=UNDERSTOOD, **vals
        )
        result = reflet.with_user(author).action_send(
            invite={"email": email, "name": name}
        )
        return reflet, result

    def _invitation(self, result):
        return self.Invitation.sudo().browse(result["id"])

    def _mails(self, email):
        return self.Mail.search([("email_to", "=", email)], order="id")

    def _token(self, email=UNKNOWN):
        """The token of the last email sent to ``email``."""
        mail = self._mails(email)[-1:]
        self.assertTrue(mail, f"No invitation email to {email}.")
        match = TOKEN_RE.search(mail.body_html)
        self.assertTrue(match, "The email holds no invitation link.")
        return match.group(1)


class TestLinkupInvitation(LinkupInvitationMixin, LinkupRefletCase):
    def test_invite_unknown_address(self):
        """CA1: the draft waits for the invitation, the email is generic
        and leaves the texts out; only the hash of the token is stored."""
        reflet, result = self._invite()
        invitation = self._invitation(result)
        self.assertEqual(reflet.state, "pending_invite")
        self.assertFalse(reflet.recipient_id)
        self.assertEqual(reflet.sudo().invitation_id, invitation)
        self.assertEqual(invitation.reflet_id, reflet)
        self.assertEqual(invitation.state, "sent")
        self.assertEqual(invitation.inviter_id, self.sam)
        self.assertEqual(invitation.email, UNKNOWN)
        self.assertEqual(result["email"], "c***@example.com")
        self.assertEqual(result["state"], "sent")
        self.assertEqual(result["reflet"]["understood"], UNDERSTOOD)
        self.assertAlmostEqual(
            invitation.expiry_date,
            fields.Datetime.now() + timedelta(days=14),
            delta=timedelta(minutes=5),
        )
        mail = self._mails(UNKNOWN)
        self.assertEqual(len(mail), 1)
        token = self._token()
        self.assertNotEqual(invitation.token_hash, token)
        self.assertNotIn(token, invitation.token_hash)
        for text in (YOU_SAID, UNDERSTOOD):
            self.assertNotIn(text, mail.body_html)
            self.assertNotIn(text, mail.subject)
        self.assertIn("Sam", mail.subject)
        self.assertIn(f"/linkup/invite/{token}/optout", mail.body_html)
        # The email is attached to no record: no message tells the inviter
        # whether it went out.
        self.assertFalse(mail.model)
        self.assertFalse(mail.res_id)
        self.assertFalse(
            self.env["mail.message"]
            .with_user(self.sam)
            .search([("id", "=", mail.mail_message_id.id)])
        )
        self.assertFalse(self.events)

    def test_same_answer_whoever_holds_the_address(self):
        """CA4, CA6, RM6: an unknown address, the address of a member, of a
        member who blocks Sam, and one that refuses the invitations give
        Sam the same answer; the email leaves for the unknown address only,
        and no link nor conversation exists before an answer."""
        self.env["linkup.block"].with_user(self.france).action_block(
            self.sam.id
        )
        self.env["linkup.email.blocklist"]._linkup_add(OTHER, "invite_optout")
        answers = {}
        for email in (UNKNOWN, self.luce.email, self.france.email, OTHER):
            _reflet, result = self._invite(email, name="")
            answers[email] = {
                key: value
                for key, value in result.items()
                if key not in ("id", "email", "expiry_date", "reflet")
            }
            answers[email]["reflet"] = {
                key: value
                for key, value in result["reflet"].items()
                if key != "id"
            }
        self.assertEqual(len({repr(value) for value in answers.values()}), 1)
        self.assertEqual(len(self._mails(UNKNOWN)), 1)
        self.assertFalse(self._mails(self.luce.email))
        self.assertFalse(self._mails(self.france.email))
        self.assertFalse(self._mails(OTHER))
        self.assertFalse(self._link(self.sam, self.luce))
        self.assertFalse(
            self.env["res.users"]
            .with_user(self.sam)
            .search([("id", "=", self.luce.id)])
        )
        self.assertFalse(
            self.Reflet.with_user(self.luce).search(
                [("author_id", "=", self.sam.id)]
            )
        )

    def _open_invitations_to(self, user):
        """Let ``user`` receive the invitations naming their address: a
        module of the community restricts them to a code by default."""
        if "linkup_first_reflet_scope" in self.env["res.users"]._fields:
            user.sudo().linkup_first_reflet_scope = "email_or_code"

    def test_member_receives_inside_linkup(self):
        """RM6: the address of a member gets no email; the invitation
        reaches the member inside LinkUp with the reflection, and its
        confirmation links the pair and tells Sam. Nothing exists between
        them before."""
        self._open_invitations_to(self.luce)
        self._bus_reset()
        reflet, result = self._invite(self.luce.email)
        invitation = self._invitation(result)
        self.assertFalse(self._mails(self.luce.email))
        self.assertEqual(invitation.invitee_id, self.luce)
        self.assertIn(
            self.luce.partner_id,
            [
                target
                for target, kind, _payload in self._bus_sent()
                if kind == "linkup.invitation/received"
            ],
        )
        self.assertFalse(self._link(self.sam, self.luce))
        received = self.Invitation.with_user(
            self.luce
        ).linkup_received_invitations()
        self.assertEqual([info["id"] for info in received], invitation.ids)
        self.assertEqual(received[0]["inviter"]["name"], "Sam")
        self.assertEqual(received[0]["reflet"]["understood"], UNDERSTOOD)
        self.assertFalse(
            self.Invitation.with_user(
                self.jacques
            ).linkup_received_invitations()
        )
        with self.assertLinkupCode("linkup.unavailable"):
            invitation.with_user(self.jacques).action_accept_received()
        self._bus_reset()
        answer = invitation.with_user(self.luce).action_accept_received()
        self.assertTrue(answer["delivered"])
        self.assertEqual(invitation.state, "accepted")
        self.assertEqual(reflet.state, "confirmed")
        self.assertEqual(reflet.recipient_id, self.luce)
        link = self._link(self.sam, self.luce)
        self.assertEqual(link.state, "active")
        self.assertEqual(answer["channel_id"], link.channel_id.id)
        accepted = [
            payload
            for target, kind, payload in self._bus_sent()
            if kind == "linkup.invitation/accepted"
            and target == self.sam.partner_id
        ]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["name"], "Luce")
        self.assertFalse(
            self.Invitation.with_user(self.luce).linkup_received_invitations()
        )

    def test_member_ignores_an_invitation(self):
        """RM6: the invited member sets the invitation aside; it leaves
        their list, waits for its expiry, and Sam reads no change."""
        self._open_invitations_to(self.luce)
        reflet, result = self._invite(self.luce.email)
        invitation = self._invitation(result)
        before = invitation.with_user(self.sam).read(["write_date"])
        invitation.with_user(self.luce).action_ignore_received()
        self.assertFalse(
            self.Invitation.with_user(self.luce).linkup_received_invitations()
        )
        self.assertEqual(invitation.state, "sent")
        self.assertEqual(reflet.state, "pending_invite")
        self.assertEqual(
            invitation.with_user(self.sam).read(["write_date"]), before
        )
        with self.assertLinkupCode("linkup.unavailable"):
            invitation.with_user(self.luce).action_accept_received()

    def test_blocking_member_receives_nothing(self):
        """RM6: a member who blocks Sam receives neither an email nor the
        invitation inside LinkUp."""
        self._open_invitations_to(self.france)
        self.env["linkup.block"].with_user(self.france).action_block(
            self.sam.id
        )
        _reflet, result = self._invite(self.france.email)
        self.assertFalse(self._invitation(result).invitee_id)
        self.assertFalse(
            self.Invitation.with_user(
                self.france
            ).linkup_received_invitations()
        )

    def test_validation(self):
        """An invalid address, the own address of the inviter, a phone
        number and a missing declaration of the exchange are refused."""
        reflet = self._draft()
        for invite, field in (
            ({"email": "not-an-address"}, "email"),
            ({"email": self.sam.email.upper()}, "email"),
            ({"email": UNKNOWN, "phone": "5555550123"}, "phone"),
        ):
            with self.subTest(field=field):
                with self.assertLinkupCode("linkup.validation", field):
                    reflet.with_user(self.sam).action_send(invite=invite)
        self._draft(real_world_declared=False)
        with self.assertLinkupCode("linkup.validation", "real_world_declared"):
            reflet.with_user(self.sam).action_send(invite={"email": UNKNOWN})
        self.assertEqual(reflet.state, "draft")
        self.assertFalse(self.Invitation.sudo().search([]))

    def test_daily_limit(self):
        """RM5: beyond ``linkup.max_invitations_per_day`` sendings a day,
        new invitations and new sendings, the code is
        ``linkup.rate_limited``."""
        self.env["ir.config_parameter"].set_param(
            "linkup.max_invitations_per_day", "2"
        )
        _reflet, result = self._invite()
        self._invitation(result).with_user(self.sam).action_resend()
        info = self.Invitation.with_user(self.sam).linkup_invitations_info()
        self.assertEqual(info["quota"], {"used": 2, "max": 2})
        reflet = self._draft()
        with self.assertLinkupCode("linkup.rate_limited"):
            reflet.with_user(self.sam).action_send(invite={"email": OTHER})
        self.assertEqual(reflet.state, "draft")

    def test_resend_replaces_the_token(self):
        """A new sending gives a new link and voids the former one."""
        _reflet, result = self._invite()
        first = self._token()
        invitation = self._invitation(result)
        expiry = invitation.expiry_date
        invitation.with_user(self.sam).action_resend()
        second = self._token()
        self.assertNotEqual(first, second)
        self.assertFalse(self.Invitation._linkup_find(first))
        self.assertEqual(self.Invitation._linkup_find(second), invitation)
        self.assertEqual(invitation.expiry_date, expiry)

    def test_cancel(self):
        """LU-F-026 RM2: the invitation is cancelled, its link refused, and
        the reflection is the draft of Sam again; holding another draft,
        Sam sends or deletes it first."""
        reflet, result = self._invite()
        token = self._token()
        invitation = self._invitation(result)
        other = self._draft()
        with self.assertLinkupCode("linkup.validation", "draft"):
            invitation.with_user(self.sam).action_cancel()
        other.with_user(self.sam).action_discard_draft()
        draft_id = invitation.with_user(self.sam).action_cancel()
        self.assertEqual(draft_id, reflet.id)
        self.assertEqual(reflet.state, "draft")
        self.assertEqual(reflet.understood, UNDERSTOOD)
        self.assertFalse(reflet.sudo().invitation_id)
        self.assertEqual(invitation.state, "cancelled")
        self.assertEqual(
            self.Invitation._linkup_find(token)._linkup_token_code(),
            "linkup.invite_cancelled",
        )
        with self.assertLinkupCode("linkup.invite_cancelled"):
            invitation.with_user(self.sam).action_resend()

    def test_inviter_only(self):
        """A member reads only the invitations they sent, never the hash of
        a token, and acts on none of the others."""
        _reflet, result = self._invite()
        invitation = self._invitation(result)
        self.assertFalse(self.Invitation.with_user(self.france).search([]))
        with self.assertRaises(AccessError):
            invitation.with_user(self.france).action_cancel()
        with self.assertRaises(AccessError):
            invitation.with_user(self.france).action_resend()
        mine = self.Invitation.with_user(self.sam).search([])
        self.assertEqual(mine, invitation)
        with self.assertRaises(AccessError):
            mine.read(["token_hash"])
        info = self.Invitation.with_user(self.sam).linkup_invitations_info()
        self.assertEqual(
            [entry["id"] for entry in info["invitations"]], [invitation.id]
        )
        self.assertFalse(
            self.Invitation.with_user(self.france).linkup_invitations_info()[
                "invitations"
            ]
        )

    def test_member_opens_the_link(self):
        """A member holding the invited address uses the link while logged
        in: the reflection reaches them; another member is refused and the
        invitation stays usable."""
        reflet, result = self._invite(self.luce.email)
        invitation = self._invitation(result)
        with self.assertLinkupCode("linkup.unavailable"):
            invitation._linkup_open_for(self.jacques)
        self.assertEqual(invitation.state, "sent")
        self.assertTrue(invitation._linkup_open_for(self.luce))
        self.assertEqual(invitation.state, "accepted")
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(reflet.recipient_id, self.luce)
        self.assertEqual(self._link(self.sam, self.luce).state, "pending")
        self.assertEqual(reflet.message_id.linkup_reflet_id, reflet)
        self.assertIn(("reflect_sent", frozenset(self.sam.ids)), self.events)
        with self.assertLinkupCode("linkup.invite_used"):
            invitation._linkup_open_for(self.luce)

    def test_expiry_and_purge(self):
        """RM9, LU-NF-015: the cron expires an invitation past its date with
        its reflection, then deletes both one day after the expiry; a
        delivered reflection stays."""
        reflet, result = self._invite()
        invitation = self._invitation(result)
        delivered, result2 = self._invite(self.luce.email)
        invitation2 = self._invitation(result2)
        invitation2._linkup_open_for(self.luce)
        (invitation | invitation2).write(
            {"expiry_date": fields.Datetime.now() - timedelta(hours=1)}
        )
        self.assertEqual(
            invitation._linkup_token_code(), "linkup.invite_expired"
        )
        self.Invitation._cron_linkup_invitations()
        self.assertEqual(invitation.state, "expired")
        self.assertEqual(reflet.state, "expired")
        self.assertFalse(
            self.Invitation.with_user(self.sam).linkup_invitations_info()[
                "invitations"
            ]
        )
        (invitation | invitation2).write(
            {"expiry_date": fields.Datetime.now() - timedelta(days=2)}
        )
        self.Invitation._cron_linkup_invitations()
        self.assertFalse(invitation.exists())
        self.assertFalse(invitation2.exists())
        self.assertFalse(reflet.exists())
        self.assertTrue(delivered.exists())
        self.assertEqual(delivered.state, "sent")

    def test_reflection_of_a_forwarded_link_purged(self):
        """LU-NF-015: the reflection a forwarded link let expire is deleted
        one day after the use of the link; the invitation stays until one
        day after its own expiry, to tell that its link served."""
        reflet, result = self._invite()
        invitation = self._invitation(result)
        invitation._linkup_lock()
        self.assertFalse(invitation._linkup_consume(self.jacques))
        self.assertEqual(reflet.state, "expired")
        self.Invitation._cron_linkup_invitations()
        self.assertTrue(reflet.exists())
        invitation.accepted_date = fields.Datetime.now() - timedelta(days=2)
        self.Invitation._cron_linkup_invitations()
        self.assertFalse(reflet.exists())
        self.assertEqual(invitation._linkup_token_code(), "linkup.invite_used")

    def test_email_unreadable_by_the_inviter(self):
        """The message of the email holds the link: the inviter reads it
        neither by search nor by id, so that no message tells them whether
        an email went out, nor gives them the token."""
        _reflet, result = self._invite()
        message = self._mails(UNKNOWN).mail_message_id
        self.assertTrue(message)
        self.assertNotEqual(message.create_uid, self.sam)
        Message = self.env["mail.message"].with_user(self.sam)
        self.assertFalse(
            Message.search([("body", "ilike", "/linkup/invite/")])
        )
        with self.assertRaises(AccessError):
            Message.browse(message.id).read(["body"])

    def test_undelivered_email_rendered_alike(self):
        """An address that receives no email costs the server the same
        rendering of the email as another one, so that the time of the
        answer does not tell them apart."""
        Template = type(self.env["mail.template"])
        generate = Template._generate_template
        rendered = []

        def count(template, res_ids, render_fields, *args, **kwargs):
            rendered.append(template.id)
            return generate(template, res_ids, render_fields, *args, **kwargs)

        self.patch(Template, "_generate_template", count)
        self._invite()
        self.env["linkup.email.blocklist"]._linkup_add(OTHER, "invite_optout")
        self._invite(OTHER)
        self.assertEqual(len(rendered), 2)
        self.assertFalse(self._mails(OTHER))

    def test_suspended_inviter_sends_nothing(self):
        """A suspended member neither invites nor sends a link again; they
        still cancel (LU-F-115 RM4)."""
        _reflet, result = self._invite()
        invitation = self._invitation(result)
        self.sam.sudo().linkup_suspended_until = (
            fields.Datetime.now() + timedelta(days=1)
        )
        with self.assertLinkupCode("linkup.unavailable"):
            invitation.with_user(self.sam).action_resend()
        draft = self._draft()
        with self.assertLinkupCode("linkup.unavailable"):
            draft.with_user(self.sam).action_send(invite={"email": OTHER})
        self.assertEqual(len(self._mails(UNKNOWN)), 1)
        self.assertFalse(self._mails(OTHER))
        draft.with_user(self.sam).action_discard_draft()
        invitation.with_user(self.sam).action_cancel()
        self.assertEqual(invitation.state, "cancelled")

    def test_blocklist_keeps_hashes(self):
        """The refusal list holds a keyed hash of the address, never the
        address, and outlives the invitation it came from."""
        _reflet, result = self._invite()
        self._invitation(result)._linkup_optout()
        entry = self.env["linkup.email.blocklist"].search([])
        self.assertEqual(len(entry), 1)
        self.assertNotIn("@", entry.email_hash)
        self.assertNotIn("camille", entry.email_hash)
        self.assertTrue(
            self.env["linkup.email.blocklist"]._linkup_is_listed(
                UNKNOWN.upper()
            )
        )
        self._invite()
        self.assertEqual(len(self._mails(UNKNOWN)), 1)


@tagged("post_install", "-at_install")
class TestLinkupInvitationRoute(
    LinkupInvitationMixin, LinkupRefletCase, HttpCase
):
    """The pages of the link (T-29, LU-F-020 CA2, CA3, CA5, CA7, LU-F-026
    CA1), through HTTP."""

    def _page(self, token, data=None, **query):
        url = f"/linkup/invite/{token}"
        if query:
            url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
        if data is None:
            return self.url_open(url, allow_redirects=False)
        page = self.url_open(url)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        self.assertTrue(csrf, "The page holds no form.")
        return self.url_open(
            url,
            data=dict(data, csrf_token=csrf.group(1)),
            allow_redirects=False,
        )

    def _code(self, response):
        match = re.search(r'data-code="([^"]+)"', response.text)
        return match and match.group(1)

    def _signup(self, token, email, **extra):
        """Sign up through the link, with the fields of ``extra`` too. The
        consents and declarations of the public community go along: the
        page ignores them without it."""
        return self._page(
            token,
            data={
                **extra,
                "login": email,
                "name": "Camille",
                "password": "linkup-Camille-2026",
                "confirm_password": "linkup-Camille-2026",
                "linkup_terms": "on",
                "linkup_privacy": "on",
                "linkup_sensitive_data": "on",
                "linkup_adult": "on",
                "linkup_age_bracket": "25_34",
                "linkup_resides_canada": "on",
            },
        )

    def _user(self, email):
        return self.env["res.users"].sudo().search([("email", "=", email)])

    def test_signup_attaches_the_reflection(self):
        """CA2, CA7: the page names the inviter, never the texts; the
        signup with the invited address creates a restricted member whose
        reflection waits unread, and the link then serves no more."""
        reflet, _result = self._invite()
        token = self._token()
        page = self._page(token)
        self.assertEqual(page.status_code, 200)
        self.assertFalse(self._code(page))
        self.assertIn("Sam", page.text)
        self.assertIn("oe_signup_form", page.text)
        for text in (YOU_SAID, UNDERSTOOD, UNKNOWN):
            self.assertNotIn(text, page.text)
        # The URL holds the token: neither a referrer nor a cache keeps it.
        self.assertEqual(page.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(page.headers["Cache-Control"], "no-store")
        response = self._signup(token, UNKNOWN)
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(response.headers["Location"].endswith("/odoo/linkup"))
        user = self._user(UNKNOWN)
        self.assertEqual(len(user), 1)
        self.assertFalse(user.share)
        self.assertTrue(
            user.has_group("mail_linkup_reflet.group_linkup_member")
        )
        self.assertFalse(user.has_group("base.group_system"))
        self.assertEqual(
            user.action_id.id,
            self.env.ref("mail_linkup_reflet.action_linkup_home").id,
        )
        self.env.invalidate_all()
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(reflet.recipient_id, user)
        self.assertTrue(reflet.message_id)
        info = self.Reflet.with_user(user).linkup_reflet_view_info()
        sam = [c for c in info["contacts"] if c["user_id"] == self.sam.id]
        self.assertEqual(sam and sam[0]["unread_count"], 1)
        # A new visitor, without the session of the new member.
        self.opener.cookies.clear()
        self.assertEqual(self._code(self._page(token)), "linkup.invite_used")

    def test_forwarded_link(self):
        """CA5: a signup through the link with another address creates the
        account, but the reflection is not attached to it."""
        reflet, _result = self._invite()
        token = self._token()
        response = self._signup(token, OTHER)
        self.assertIn(response.status_code, (302, 303))
        user = self._user(OTHER)
        self.assertTrue(user)
        self.env.invalidate_all()
        self.assertFalse(reflet.recipient_id)
        self.assertEqual(reflet.state, "expired")
        self.assertFalse(self._link(self.sam, user))
        self.assertFalse(
            self.Reflet.with_user(user).search([("id", "=", reflet.id)])
        )

    def test_refused_links(self):
        """CA3, LU-F-026 CA1: an expired, a cancelled and an unknown link get
        their page, without a form."""
        _reflet, result = self._invite()
        token = self._token()
        invitation = self._invitation(result)
        invitation.write(
            {"expiry_date": fields.Datetime.now() - timedelta(minutes=1)}
        )
        page = self._page(token)
        self.assertEqual(self._code(page), "linkup.invite_expired")
        self.assertNotIn("oe_signup_form", page.text)
        invitation.write(
            {"expiry_date": fields.Datetime.now() + timedelta(days=1)}
        )
        invitation.with_user(self.sam).action_cancel()
        self.assertEqual(
            self._code(self._page(token)), "linkup.invite_cancelled"
        )
        self.assertEqual(
            self._code(self._page("z" * 43)), "linkup.unavailable"
        )

    def test_logged_in_member(self):
        """A logged-in member with the invited address lands on the Reflet
        view with the reflection; another one reads that the invitation is
        not theirs, and it stays usable. The address became the one of a
        member after the email left."""
        reflet, result = self._invite()
        token = self._token()
        camille = mail_new_test_user(
            self.env,
            login="linkup_rf_camille",
            email=UNKNOWN,
            groups="mail_linkup_reflet.group_linkup_member",
        )
        self.authenticate(self.jacques.login, self.jacques.login)
        self.assertEqual(self._code(self._page(token)), "linkup.unavailable")
        self.assertEqual(self._invitation(result).state, "sent")
        self.authenticate(camille.login, camille.login)
        response = self._page(token)
        self.assertIn(response.status_code, (302, 303))
        self.env.invalidate_all()
        self.assertEqual(reflet.recipient_id, camille)
        self.assertEqual(reflet.state, "sent")

    def test_optout(self):
        """RM7: the refusal asks first, then lists the address; the next
        invitation to it sends nothing."""
        _reflet, _result = self._invite()
        token = self._token()
        url = f"/linkup/invite/{token}/optout"
        page = self.url_open(url)
        self.assertIn("o-linkup-InvitePage-optout", page.text)
        self.assertFalse(self.env["linkup.email.blocklist"].search([]))
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        done = self.url_open(url, data={"csrf_token": csrf.group(1)})
        self.assertEqual(done.status_code, 200)
        self.assertTrue(
            self.env["linkup.email.blocklist"]._linkup_is_listed(UNKNOWN)
        )
        self._invite()
        self.assertEqual(len(self._mails(UNKNOWN)), 1)

    @mute_logger(
        "odoo.sql_db", "odoo.addons.mail_linkup_reflet.controllers.invitation"
    )
    def test_signup_with_taken_address(self):
        """An address taken after the email left keeps the invitation
        usable and says so, as the native signup does."""
        _reflet, result = self._invite(OTHER)
        token = self._token(OTHER)
        mail_new_test_user(
            self.env,
            login=OTHER,
            email=OTHER,
            groups="mail_linkup_reflet.group_linkup_member",
        )
        response = self._signup(token, OTHER)
        self.assertEqual(response.status_code, 200)
        self.assertIn("alert-danger", response.text)
        self.assertEqual(self._invitation(result).state, "sent")
