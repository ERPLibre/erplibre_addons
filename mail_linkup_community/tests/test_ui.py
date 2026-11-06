# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Web client of the community: the tour of the consent banner of a new
member (LU-F-111), the tour of the profile (LU-F-082), the tours of a
report and of its moderation (LU-F-114, LU-F-116), and the Hoot unit tests
of the module (§12.1)."""

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.web.tests import test_js
from odoo.tests import HttpCase, tagged

# Suite of the Hoot tests of the module, as the Hoot runner names it.
HOOT_SUITE = "@mail_linkup_community"


@tagged("post_install", "-at_install")
class TestLinkupCommunityUi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.camille = mail_new_test_user(
            cls.env,
            login="linkup_cm_ui_camille",
            password="linkup_cm_ui_camille",
            name="Camille",
            email="linkup_cm_ui_camille@example.com",
            groups="mail_linkup_reflet.group_linkup_member",
        )
        cls.camille.write({"linkup_tour_done": True})

    def test_consent_tour(self):
        """A new member accepts the three required consents from the
        Reflet view; each one is recorded apart."""
        self.camille.sudo().linkup_consent_required = True
        self.start_tour(
            "/odoo/linkup",
            "linkup_consent_tour",
            login=self.camille.login,
        )
        Consent = self.env["linkup.consent"]
        self.assertEqual(Consent._linkup_missing(self.camille.sudo()), [])
        rows = Consent.sudo().search([("user_id", "=", self.camille.id)])
        self.assertEqual(
            sorted(rows.mapped("purpose")),
            ["privacy", "sensitive_data", "terms"],
        )

    def test_profile_tour(self):
        """The member opens the profile from the menu of their avatar,
        changes their pseudonym, chooses who may send them a first
        reflection and withdraws the consent to sensitive information."""
        self.env["linkup.consent"]._linkup_record(
            self.camille, "sensitive_data", True
        )
        self.start_tour(
            "/odoo/linkup",
            "linkup_profile_tour",
            login=self.camille.login,
        )
        self.assertEqual(self.camille.name, "Camille L.")
        self.assertEqual(
            self.camille.sudo().linkup_first_reflet_scope, "email_or_code"
        )
        self.assertFalse(
            self.env["linkup.consent"]._linkup_active(
                self.camille, "sensitive_data"
            )
        )

    def test_report_and_moderation_tours(self):
        """A member reports a message of the group from its menu; a
        moderator reads it, takes the report and warns its author, each
        step written to the audit log."""

        def user(login, name, group):
            new = mail_new_test_user(
                self.env,
                login=login,
                password=login,
                name=name,
                email=f"{login}@example.com",
                groups=group,
            )
            new.write({"linkup_tour_done": True})
            return new

        sam = user(
            "linkup_cm_ui_sam", "Sam", "mail_linkup_reflet.group_linkup_member"
        )
        joanna = user(
            "linkup_cm_ui_joanna",
            "Joanna",
            "mail_linkup_reflet.group_linkup_moderator",
        )
        group = self.env["discuss.channel"].create(
            {
                "name": "Atelier",
                "channel_type": "group",
                "channel_member_ids": [
                    Command.create({"partner_id": member.partner_id.id})
                    for member in (sam, self.camille)
                ],
            }
        )
        message = group.with_user(sam).message_post(
            body="Linkup tour message",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.start_tour(
            f"/odoo/discuss?active_id=discuss.channel_{group.id}",
            "linkup_report_tour",
            login=self.camille.login,
        )
        report = self.env["linkup.report"].search(
            [("reporter_id", "=", self.camille.id)]
        )
        self.assertEqual(report.message_id, message)
        self.assertEqual(report.reported_user_id, sam)
        self.assertEqual(report.reason, "harassment")
        self.start_tour(
            "/odoo/linkup-moderation",
            "linkup_moderation_tour",
            login=joanna.login,
        )
        self.assertEqual(report.state, "actioned")
        self.assertEqual(report.action_taken, "warning")
        audit = self.env["linkup.audit.log"].search(
            [("report_id", "=", report.id)], order="id"
        )
        self.assertEqual(
            audit.mapped("action"), ["content_read", "take", "warn"]
        )
        self.assertEqual(audit.actor_id, joanna)
        notice = self.env["linkup.moderation.notice"].search(
            [("user_id", "=", sam.id)]
        )
        self.assertEqual(notice.decision, "warning")

    def test_hoot_suite(self):
        """The Hoot tests of the module, in a desktop browser."""
        suite_id = test_js.HOOTCommon._generate_hash(self, HOOT_SUITE)
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000"
            f"&id={suite_id}",
            "",
            "",
            login="admin",
            timeout=1800,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=test_js.unit_test_error_checker,
        )
