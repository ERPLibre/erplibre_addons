# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The personal data of a member (T-17, LU-F-117, LU-F-026 RM4, LU-NF-014,
LU-NF-053, Q-23): the export holds the data of its requester only, and the
deletion of an account erases its content everywhere, keeps the points
ledger anonymized and leaves the other members intact."""

import base64
import json
from datetime import timedelta

from odoo import fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_gamification.tests.common import LinkupPointsCase
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

ADMIN = "mail_linkup_reflet.group_linkup_admin"
# Phrases invented for the tests, searched for after the erasure.
SAM_SAID = "Que tu as planté des tomates bleues."
SAM_MESSAGE = "Mon message sur les tomates bleues"
FRANCE_SAID = "Que tu aimes les pommes de pin."
FRANCE_MESSAGE = "Mon message sur les pommes de pin"
THIRD_SAID = "Que tu joues du basson le mardi."


class LinkupPersonalDataCase(LinkupPointsCase):
    """Sam and France share a confirmed reflection, its points and a
    direct conversation; France also sends Sam a reflection, and Jacques
    one, which Sam is a stranger to."""

    def setUp(self):
        super().setUp()
        self.Data = self.env["linkup.personal.data"]
        self.Users = self.env["res.users"]
        self.Message = self.env["mail.message"].sudo()
        self.sam_reflet = self._sent(you_said=SAM_SAID)
        self.sam_reflet.with_user(self.france).action_confirm()
        self.france_reflet = self._sent(
            self.france, self.sam, you_said=FRANCE_SAID
        )
        self.third_reflet = self._sent(
            self.france, self.jacques, you_said=THIRD_SAID
        )
        self.chat = self.sam_reflet.channel_id
        self.attachment = self.env["ir.attachment"].create(
            {
                "name": "tomates-bleues.txt",
                "datas": base64.b64encode(b"bleues"),
                "res_model": "discuss.channel",
                "res_id": self.chat.id,
            }
        )
        self.sam_message = self.chat.sudo().message_post(
            author_id=self.sam.partner_id.id,
            body=SAM_MESSAGE,
            attachment_ids=self.attachment.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.france_message = self.chat.sudo().message_post(
            author_id=self.france.partner_id.id,
            body=FRANCE_MESSAGE,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.env["mail.message.reaction"].create(
            {
                "message_id": self.france_message.id,
                "content": "👍",
                "partner_id": self.sam.partner_id.id,
            }
        )

    def _ask_deletion(self, user, days_ago=31):
        """Ask the deletion of ``user``, dated ``days_ago`` days back."""
        self.Users.with_user(user).linkup_request_deletion()
        user.sudo().linkup_deletion_requested_date = (
            fields.Datetime.now() - timedelta(days=days_ago)
        )

    def _karma_matches_ledger(self, user):
        lines = self.Ledger.sudo().search([("user_id", "=", user.id)])
        return user.sudo().karma == sum(lines.mapped("points"))


@tagged("post_install", "-at_install")
class TestLinkupExport(LinkupPersonalDataCase):
    def test_export_holds_own_data_only(self):
        """CA1: Sam's export holds his reflections, his messages, his
        ledger and his consents, and no reflection between two others, no
        message, address or phone of another member."""
        self.env["linkup.consent"]._linkup_record(self.sam, "terms", True)
        data = self.Users.with_user(self.sam).linkup_export_data()
        dump = json.dumps(data, ensure_ascii=False)
        self.assertEqual(data["format"], "linkup.personal_data")
        self.assertEqual(data["profile"]["email"], self.sam.email)
        self.assertEqual(
            {row["id"] for row in data["reflections"]},
            {self.sam_reflet.id, self.france_reflet.id},
        )
        authored = next(
            row for row in data["reflections"] if row["role"] == "author"
        )
        self.assertEqual(authored["you_said"], SAM_SAID)
        self.assertEqual(authored["other_member"], "France")
        self.assertNotIn(THIRD_SAID, dump)
        self.assertEqual(
            [row["text"] for row in data["messages"]], [SAM_MESSAGE]
        )
        self.assertEqual(
            data["messages"][0]["attachments"], ["tomates-bleues.txt"]
        )
        self.assertNotIn(FRANCE_MESSAGE, dump)
        lines = self.Ledger.sudo().search([("user_id", "=", self.sam.id)])
        self.assertTrue(lines)
        self.assertEqual(len(data["points"]["lines"]), len(lines))
        self.assertEqual(data["points"]["balance"], self.sam.karma)
        self.assertEqual(data["consents"][-1]["purpose"], "terms")
        self.assertEqual(
            [row["other_member"] for row in data["links"]], ["France"]
        )
        for other in (self.france, self.jacques, self.luce):
            self.assertNotIn(other.email, dump)

    def test_export_of_a_received_reflection_follows_its_reading(self):
        """A reflection France withdrew leaves Sam's export, as it leaves
        his reading; it stays in hers."""
        reflet = self.france_reflet
        reflet.with_user(self.france).action_withdraw()
        ids = {
            row["id"]
            for row in self.Users.with_user(self.sam).linkup_export_data()[
                "reflections"
            ]
        }
        self.assertNotIn(reflet.id, ids)
        ids = {
            row["id"]
            for row in self.Users.with_user(self.france).linkup_export_data()[
                "reflections"
            ]
        }
        self.assertIn(reflet.id, ids)

    def test_export_needs_a_member(self):
        """A user outside LinkUp exports nothing."""
        outsider = mail_new_test_user(
            self.env,
            login="linkup_pd_outsider",
            groups="base.group_user",
        )
        with self.assertRaises(AccessError):
            self.Users.with_user(outsider).linkup_export_data()


@tagged("post_install", "-at_install")
class TestLinkupDeletion(LinkupPersonalDataCase):
    def test_request_and_cancel(self):
        """RM3, CA3: a deletion asked waits for its delay of grace; once
        cancelled, the account stays active and intact."""
        info = self.Users.with_user(self.sam).linkup_request_deletion()
        self.assertTrue(info["deletion_date"])
        self.assertEqual(
            info["deletion_date"] - info["deletion_requested"],
            timedelta(days=30),
        )
        profile = self.Users.with_user(self.sam).linkup_profile_info()
        self.assertEqual(profile["deletion_date"], info["deletion_date"])
        self.Data._cron_linkup_retention()
        self.assertTrue(self.sam.active)
        info = self.Users.with_user(self.sam).linkup_cancel_deletion()
        self.assertFalse(info["deletion_date"])
        self.sam.sudo().linkup_deletion_requested_date = False
        self.Data._cron_linkup_retention()
        self.assertTrue(self.sam.active)
        self.assertEqual(self.sam_reflet.you_said, SAM_SAID)

    def test_admin_account_not_deleted_by_itself(self):
        """An administrator account is closed by another administrator."""
        admin = mail_new_test_user(
            self.env,
            login="linkup_pd_system",
            groups=f"{MEMBER},base.group_system",
        )
        with self.assertLinkupCode("linkup.unavailable"):
            self.Users.with_user(admin).linkup_request_deletion()

    def test_deletion_erases_the_account_and_its_content(self):
        """RM2, CA2: once the delay is over, Sam's account is anonymized and
        archived; the texts of his reflections, written and received, his
        messages, attachments and reactions, and the history of his
        partner are gone, from the records and from the searches. His
        ledger stays, with his karma equal to its sum; France, Jacques and
        their content are intact."""
        email = self.sam.email
        self.sam.partner_id.message_post(body=f"Ancienne adresse {email}")
        consent = self.env["linkup.consent"]._linkup_record(
            self.sam, "terms", True
        )
        consent.sudo().ip_hash = "hash"
        lines = self.Ledger.sudo().search([("user_id", "=", self.sam.id)])
        france_lines = self.Ledger.sudo().search(
            [("user_id", "=", self.france.id)]
        )
        self.assertTrue(lines and france_lines)
        self._ask_deletion(self.sam)
        self.Data._cron_linkup_retention()

        sam = self.sam.sudo().with_context(active_test=False)
        self.assertFalse(sam.active)
        self.assertEqual(sam.partner_id.name, "Deleted member")
        self.assertFalse(sam.partner_id.email)
        self.assertTrue(sam.login.startswith("lu-deleted-"))
        self.assertTrue(sam.linkup_deleted_date)
        self.assertFalse(sam.linkup_erase_pending)
        for reflet in (self.sam_reflet, self.france_reflet):
            self.assertTrue(reflet.linkup_content_removed)
            self.assertFalse(reflet.you_said or reflet.understood)
            card = reflet._linkup_card_values()
            self.assertTrue(card["content_removed"])
            self.assertFalse(card["you_said"])
        self.assertEqual(self.third_reflet.you_said, THIRD_SAID)
        self.assertFalse(self.attachment.exists())
        self.assertFalse(
            self.env["ir.attachment"]
            .sudo()
            .search([("name", "=", "tomates-bleues.txt")])
        )
        for phrase in (SAM_MESSAGE, SAM_SAID, email):
            self.assertFalse(
                self.Message.search(
                    [
                        "|",
                        ("body", "ilike", phrase),
                        ("email_from", "ilike", phrase),
                    ]
                ),
                phrase,
            )
        self.assertFalse(
            self.Message.search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", self.chat.id),
                    ("record_name", "ilike", "Sam"),
                ]
            )
        )
        self.assertFalse(
            self.env["linkup.reflet"]
            .sudo()
            .search(
                [
                    "|",
                    ("you_said", "ilike", "tomates"),
                    ("you_said", "ilike", "pommes de pin"),
                ]
            )
        )
        self.assertFalse(
            self.env["res.partner"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("id", "=", sam.partner_id.id),
                    "|",
                    ("email", "ilike", email),
                    ("name", "=", "Sam"),
                ]
            )
        )
        self.assertFalse(
            self.env["res.partner"]
            .sudo()
            .with_context(active_test=False)
            .search([("email_normalized", "=", email)])
        )
        self.assertFalse(
            self.env["mail.message.reaction"].search(
                [("partner_id", "=", sam.partner_id.id)]
            )
        )
        self.assertNotIn("Sam", self.sam_reflet.message_id.body)
        self.assertNotIn("Sam", self.chat.name)
        self.assertFalse(consent.ip_hash)
        self.assertIn(FRANCE_MESSAGE, self.france_message.body)
        self.assertEqual(
            self.Ledger.sudo().search([("user_id", "=", self.sam.id)]), lines
        )
        self.assertEqual(
            self.Ledger.sudo().search([("user_id", "=", self.france.id)]),
            france_lines,
        )
        self.assertTrue(self._karma_matches_ledger(sam))
        self.assertTrue(self._karma_matches_ledger(self.france))
        self.assertNotIn(sam.id, self.Ledger._cron_check_karma())
        self.assertTrue(self.france.active)
        self.assertEqual(self.france.partner_id.name, "France")

    def test_deletion_waits_for_an_open_report(self):
        """RM2: a message an open report points to keeps its content until
        the report is closed; the retention cron then erases it."""
        report = self.env["linkup.report"].browse(
            self.env["linkup.report"]
            .with_user(self.france)
            .action_create_report(
                message_id=self.sam_message.id, reason="harassment"
            )
        )
        self._ask_deletion(self.sam)
        self.Data._cron_linkup_retention()
        sam = self.sam.sudo().with_context(active_test=False)
        self.assertTrue(sam.linkup_deleted_date)
        self.assertTrue(sam.linkup_erase_pending)
        self.assertIn(SAM_MESSAGE, self.sam_message.body)
        report.sudo().write({"state": "dismissed"})
        self.Data._cron_linkup_retention()
        self.assertFalse(sam.linkup_erase_pending)
        self.assertNotIn(SAM_MESSAGE, self.sam_message.body or "")


@tagged("post_install", "-at_install")
class TestLinkupEraseRejected(LinkupPersonalDataCase):
    def test_recipient_erases_a_rejected_reflection(self):
        """RM4: Jacques erases the texts of a reflection he rejected; its
        author cannot, and a confirmed reflection keeps its texts."""
        reflet = self._sent(self.sam, self.jacques, you_said="Faux.")
        reflet.with_user(self.jacques).action_reject()
        with self.assertRaises(AccessError):
            reflet.with_user(self.sam).action_erase_content()
        reflet.with_user(self.jacques).action_erase_content()
        self.assertTrue(reflet.linkup_content_removed)
        self.assertFalse(reflet.you_said)
        with self.assertLinkupCode("linkup.already_answered"):
            self.sam_reflet.with_user(self.france).action_erase_content()
        self.assertEqual(self.sam_reflet.you_said, SAM_SAID)

    def test_reported_rejected_reflection_kept(self):
        """A rejected reflection an open report points to keeps its texts
        until the report is closed."""
        reflet = self._sent(self.sam, self.jacques, you_said="Faux.")
        reflet.with_user(self.jacques).action_reject()
        self.env["linkup.report"].with_user(self.jacques).action_create_report(
            reflet_id=reflet.id, reason="harassment"
        )
        with self.assertLinkupCode("linkup.unavailable"):
            reflet.with_user(self.jacques).action_erase_content()
        self.assertEqual(reflet.you_said, "Faux.")


@tagged("post_install", "-at_install")
class TestLinkupAdminReading(LinkupPersonalDataCase):
    def test_admin_reads_no_content_of_others(self):
        """LU-NF-053: a LinkUp administrator does not read the reflections
        of two other members through the ORM."""
        admin = mail_new_test_user(
            self.env, login="linkup_pd_admin", groups=f"{MEMBER},{ADMIN}"
        )
        Reflet = self.env["linkup.reflet"].with_user(admin)
        self.assertFalse(Reflet.search([("id", "=", self.sam_reflet.id)]))
        with self.assertRaises(AccessError):
            self.sam_reflet.with_user(admin).read(["you_said"])


@tagged("post_install", "-at_install")
class TestLinkupExportRoute(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.camille = mail_new_test_user(
            cls.env,
            login="linkup_pd_camille",
            name="Camille",
            email="linkup_pd_camille@example.com",
            groups=MEMBER,
        )
        mail_new_test_user(
            cls.env,
            login="linkup_pd_andre",
            name="André",
            email="linkup_pd_andre@example.com",
            groups=MEMBER,
        )

    def test_route_downloads_the_session_user_only(self):
        """The route downloads the data of the session user as a file; it
        takes no identifier, and asks a login first."""
        response = self.url_open("/linkup/v1/me/export", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/web/login", response.headers["Location"])
        self.authenticate("linkup_pd_camille", "linkup_pd_camille")
        response = self.url_open("/linkup/v1/me/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        data = response.json()
        self.assertEqual(data["profile"]["pseudonym"], "Camille")
        self.assertNotIn("linkup_pd_andre", response.text)

    def test_delete_route_requests_then_cancels(self):
        """The route asks for the deletion of the session account, then
        cancels it with ``cancel``; the user is the only target."""
        self.authenticate("linkup_pd_camille", "linkup_pd_camille")
        asked = self.make_jsonrpc_request("/linkup/v1/me/delete", {})
        self.assertTrue(asked["deletion_requested"])
        self.camille.invalidate_recordset()
        self.assertTrue(self.camille.linkup_deletion_requested_date)
        cancelled = self.make_jsonrpc_request(
            "/linkup/v1/me/delete", {"cancel": True}
        )
        self.assertFalse(cancelled["deletion_requested"])
        self.camille.invalidate_recordset()
        self.assertFalse(self.camille.linkup_deletion_requested_date)
