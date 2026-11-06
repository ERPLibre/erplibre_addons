# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The isolation tests of the exit of the public community (§11.1, T-14,
T-19, LU-F-112, LU-NF-003, LU-NF-009): a member signed up through the
public page reads no directory, no address, no photo of a member they are
not linked to, and no report of another member, by RPC and whatever the
context of the call; a member who shares a conversation reads no address
of the others, not even in the messages, and writes their own address
only as the profile allows it."""

import io
import re

from odoo import fields
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.tests import HttpCase, tagged
from PIL import Image

from .common import SIGNUP_FORM, VERIFY_RE, LinkupCommunityCase
from .test_moderation import LinkupModerationMixin
from .test_privacy import PIXEL

PASSWORD = "linkup-Isolation-2026"
# What a client adds to the context of its calls to read more.
WIDENING_CONTEXT = {
    "active_test": False,
    "show_email": True,
    "show_address": True,
    "partner_show_db_id": True,
}
REQUIRED = ("terms", "privacy", "sensitive_data")
# A date a client could pass as a default, long before the tests.
PAST = "2000-01-01 00:00:00"


@tagged("post_install", "-at_install")
class TestLinkupPublicMemberIsolation(LinkupCommunityCase, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        (cls.sam | cls.france).partner_id.write({"image_1920": PIXEL})

    def _sign_up(self, email, name):
        """Sign ``email`` up through the public page, confirm its address
        and log it in; return its account."""
        page = self.url_open("/web/signup")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        response = self.url_open(
            "/web/signup",
            data=dict(
                SIGNUP_FORM,
                login=email,
                name=name,
                password=PASSWORD,
                confirm_password=PASSWORD,
                csrf_token=csrf.group(1),
            ),
        )
        self.assertIn("o-linkup-SignupSentPage", response.text)
        self.url_open(f"/linkup/verify/{self._verify_token(email)}")
        self.authenticate(email, PASSWORD)
        return self.env["res.users"].browse(self.session.uid)

    def _call(self, model, method, *args, **kwargs):
        kwargs.setdefault("context", WIDENING_CONTEXT)
        return self.make_jsonrpc_request(
            f"/web/dataset/call_kw/{model}/{method}",
            {"model": model, "method": method, "args": args, "kwargs": kwargs},
        )

    def test_public_member_reads_nobody(self):
        """A new member of the public signup, by RPC and with a widening
        context, reads their own account and nothing of the others: no
        user, no address, no photo, no reflection, no link, no report,
        no message of a conversation they are not part of."""
        self._sent()
        self.env["linkup.report"].with_user(self.sam).action_create_report(
            user_id=self.france.id, reason="harassment"
        )
        self.workshop.with_user(self.sam).message_post(
            body="Bonjour l'atelier",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        camille = self._sign_up("camille.isolation@example.com", "Camille")
        self.assertTrue(camille._linkup_is_restricted_member())
        users = self._call(
            "res.users", "search_read", [], fields=["login", "email", "name"]
        )
        self.assertEqual([row["id"] for row in users], [camille.id])
        partners = self._call(
            "res.partner", "search_read", [], fields=["email", "phone"]
        )
        others = [
            row for row in partners if row["id"] != camille.partner_id.id
        ]
        self.assertNotIn(self.sam.partner_id.id, [row["id"] for row in others])
        self.assertFalse(
            [row for row in others if row["email"] or row["phone"]]
        )
        for search in (self.sam.email, "Sam", "France"):
            with self.subTest(search=search):
                self.assertFalse(
                    self._call("res.partner", "name_search", search)
                )
                for method in ("im_search", "get_mention_suggestions"):
                    found = self._call("res.partner", method, search)
                    self.assertFalse(
                        [
                            row
                            for row in found.get("res.partner", [])
                            if row["id"] != camille.partner_id.id
                        ]
                    )
        for model in (
            "linkup.reflet",
            "linkup.link",
            "linkup.report",
            "linkup.block",
            "linkup.invitation",
            "linkup.moderation.notice",
        ):
            with self.subTest(model=model):
                self.assertFalse(
                    self._call(model, "search_read", [], fields=["id"])
                )
        messages = self._call(
            "mail.message",
            "search_read",
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", self.workshop.id),
            ],
            fields=["body", "email_from"],
        )
        self.assertFalse(messages)
        consents = self._call(
            "linkup.consent", "search_read", [], fields=["user_id"]
        )
        self.assertEqual({row["user_id"][0] for row in consents}, {camille.id})
        avatar = self.url_open(
            f"/web/image/res.partner/{self.sam.partner_id.id}/avatar_128"
        )
        self.assertGreater(Image.open(io.BytesIO(avatar.content)).size[0], 1)

    def test_shared_conversation_gives_no_address(self):
        """Sam shares a conversation with France: he reads her pseudonym and
        her messages, never her address, neither in the message, nor in the
        Store of Discuss, nor in a display name the context asks with the
        address; his own stays his."""
        message = self.workshop.with_user(self.france).message_post(
            body="Bonjour Sam",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.assertIn(self.france.email, message.sudo().email_from)
        row = message.with_user(self.sam).read(["email_from", "reply_to"])[0]
        self.assertFalse(row["email_from"])
        self.assertFalse(row["reply_to"])
        self.assertTrue(
            message.with_user(self.france).read(["email_from"])[0][
                "email_from"
            ]
        )
        self.assertFalse(
            self.env["mail.message"]
            .with_user(self.sam)
            .search([("email_from", "ilike", "linkup_rf_france")])
        )
        store = Store(message.with_user(self.sam)).get_result()
        self.assertFalse(store["mail.message"][0]["email_from"])
        self.assertNotIn(self.france.email, str(store))
        partner = self.france.partner_id.with_user(self.sam)
        self.assertEqual(
            partner.with_context(show_email=True).display_name, "France"
        )
        labels = [
            label
            for _id, label in self.env["res.partner"]
            .with_user(self.sam)
            .with_context(show_email=True)
            .name_search("France")
        ]
        self.assertTrue(labels)
        self.assertFalse([label for label in labels if "@" in label])
        own = self.sam.partner_id.with_user(self.sam)
        self.assertIn(
            self.sam.email, own.with_context(show_email=True).display_name
        )
        self.authenticate(self.sam.login, self.sam.login)
        result = self.make_jsonrpc_request(
            "/discuss/channel/messages",
            {"channel_id": self.workshop.id, "limit": 30},
        )
        self.assertNotIn(self.france.email, str(result))

    def test_own_address_through_the_preferences(self):
        """The preferences of Odoo let a member write their own address:
        it is checked as the profile checks it, and verified again."""
        self._as_public_account(self.sam, verified=True, consents=REQUIRED)
        me = self.sam.with_user(self.sam)
        me.write({"email": "sam.nouveau@example.com"})
        self.assertEqual(self.sam.email, "sam.nouveau@example.com")
        self.assertFalse(self.sam.sudo().linkup_email_verified)
        mail = self._mails_to("sam.nouveau@example.com")
        self.assertTrue(VERIFY_RE.search(mail[-1:].body_html))
        with self.assertRaises(LinkupError):
            me.write({"email": self.france.email})
        self.env["linkup.email.blocklist"]._linkup_add(
            "banni@example.com", "banned"
        )
        with self.assertRaises(LinkupError):
            me.write({"email": "banni@example.com"})
        self.assertEqual(self.sam.email, "sam.nouveau@example.com")


@tagged("post_install", "-at_install")
class TestLinkupServerContext(LinkupModerationMixin, LinkupCommunityCase):
    """The proofs the server writes keep their own date, whatever the
    context of the call that writes them (LU-NF-013, LU-NF-040)."""

    def test_consent_keeps_its_date_and_version(self):
        self.Consent.with_user(self.sam).with_context(
            default_date=PAST, default_version="0", default_granted=False
        ).action_grant(["notifications"])
        consent = self.Consent.sudo().search(
            [("user_id", "=", self.sam.id), ("purpose", "=", "notifications")],
            limit=1,
        )
        self.assertTrue(consent.granted)
        self.assertEqual(consent.version, "1")
        self.assertGreater(consent.date, fields.Datetime.to_datetime(PAST))

    def test_audit_row_keeps_its_date_and_record(self):
        report = self._report(self.sam, user_id=self.france.id)
        self._as(self.joanna).with_context(
            default_date=PAST,
            default_res_model="res.users",
            default_res_id=self.france.id,
        ).action_moderation_take(report.id)
        row = self.Audit.sudo().search([("report_id", "=", report.id)])
        self.assertEqual(row.action, "take")
        self.assertGreater(row.date, fields.Datetime.to_datetime(PAST))
        self.assertFalse(row.res_model)
        self.assertFalse(row.res_id)
