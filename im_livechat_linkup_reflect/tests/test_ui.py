# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Web client of the live chat: the tours of a visitor in the widget of
the website (T-53, T-55, T-54) and of a member who reports a distress in
Discuss (T-54), and the Hoot tests of the module, those of Discuss and
those of the widget (§12.1)."""

from odoo import Command, fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.web.tests import test_js
from odoo.tests import HttpCase, tagged

MODULE = "im_livechat_linkup_reflect"
MEMBER = "mail_linkup_reflet.group_linkup_member"
MODERATOR = "mail_linkup_reflet.group_linkup_moderator"

# Suite of the Hoot tests of the module, as the Hoot runner names it.
HOOT_SUITE = f"@{MODULE}"


@tagged("post_install", "-at_install")
class TestLinkupLivechatUi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def user(login, name, group):
            new = mail_new_test_user(
                cls.env,
                login=login,
                password=login,
                name=name,
                email=f"{login}@example.com",
                groups=group,
            )
            new.write({"linkup_tour_done": True})
            return new

        cls.nicolas = user("linkup_lc_ui_nicolas", "Nicolas", MEMBER)
        cls.france = user("linkup_lc_ui_france", "France", MEMBER)
        cls.sam = user("linkup_lc_ui_sam", "Sam", MEMBER)
        cls.jean = user("linkup_lc_ui_jean", "Jean", MODERATOR)
        cls.joanna = user("linkup_lc_ui_joanna", "Joanna", MODERATOR)
        cls.env["linkup.link"]._get_or_create(cls.joanna, cls.france)
        cls.welcome = cls.env.ref(f"{MODULE}.livechat_channel_welcome")
        cls.distress = cls.env.ref(f"{MODULE}.livechat_channel_distress")
        cls.welcome.user_ids = cls.nicolas
        cls.Reflet = cls.env["linkup.reflet"]
        cls.Report = cls.env["linkup.report"]
        # Nobody but the users a test sets online is available.
        cls.env["bus.presence"].sudo().search([]).unlink()

    def _online(self, *users):
        Presence = self.env["bus.presence"].sudo()
        for user in users:
            Presence.search([("user_id", "=", user.id)]).unlink()
            Presence.create(
                {
                    "user_id": user.id,
                    "status": "online",
                    "last_poll": fields.Datetime.now(),
                    "last_presence": fields.Datetime.now(),
                }
            )
        self.env.invalidate_all()

    def test_guide_then_reflection_to_a_member(self):
        """T-53, T-55: a visitor answers the guide in the widget, which
        writes their draft and sends nothing; then Nicolas joins through
        "Talk to a member", the strict rule shows, and the visitor sends him
        the reflection of the guide."""
        self._online(self.nicolas)
        self.start_tour("/", "linkup_livechat_guide_tour")
        reflet = self.Reflet.sudo().search(
            [("author_guest_id", "!=", False)], order="id desc", limit=1
        )
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(reflet.recipient_id, self.nicolas)
        self.assertEqual(reflet.category_id.code, "emotions")
        self.assertEqual(reflet.you_said, "The chores and a job wear me out")
        self.assertEqual(reflet.understood, "you are exhausted")
        self.assertTrue(reflet.real_world_declared)
        self.assertEqual(reflet.channel_id.livechat_channel_id, self.welcome)
        self.assertTrue(reflet.message_id)

    def test_visitor_needs_help_now(self):
        """T-54: "Need help now" of the widget creates the urgent report of
        the visitor and brings Jean, online, into the conversation, which
        joins the distress channel."""
        self._online(self.jean)
        self.start_tour("/", "linkup_livechat_help_now_tour")
        report = self.Report.sudo().search(
            [("reporter_guest_id", "!=", False)], order="id desc", limit=1
        )
        self.assertTrue(report.urgent)
        self.assertEqual(report.reason, "distress")
        conversation = report.distress_channel_id
        self.assertEqual(conversation.livechat_channel_id, self.distress)
        self.assertEqual(
            conversation.livechat_operator_id, self.jean.partner_id
        )

    def test_member_reports_a_distress(self):
        """T-54, LU-F-126 CA1: France reports a message of Sam as a
        distress; the conversation opens with Jean, never with Joanna,
        linked to France, both being online."""
        self._online(self.jean, self.joanna)
        group = self.env["discuss.channel"].create(
            {
                "name": "Atelier",
                "channel_type": "group",
                "channel_member_ids": [
                    Command.create({"partner_id": member.partner_id.id})
                    for member in (self.sam, self.france)
                ],
            }
        )
        group.with_user(self.sam).message_post(
            body="Linkup distress message",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.start_tour(
            f"/odoo/discuss?active_id=discuss.channel_{group.id}",
            "linkup_livechat_distress_report_tour",
            login=self.france.login,
        )
        report = self.Report.sudo().search(
            [("reporter_id", "=", self.france.id)]
        )
        self.assertEqual(report.reason, "distress")
        conversation = report.distress_channel_id
        self.assertEqual(
            conversation.livechat_operator_id, self.jean.partner_id
        )
        self.assertNotIn(
            self.joanna.partner_id,
            conversation.sudo().channel_member_ids.partner_id,
        )

    def test_hoot_suite(self):
        """The Hoot tests of the module in Discuss, in a desktop
        browser."""
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

    def test_hoot_suite_widget(self):
        """The Hoot tests of the module in the widget of the visitors, in
        a desktop browser."""
        suite_id = test_js.HOOTCommon._generate_hash(self, HOOT_SUITE)
        self.browser_js(
            "/web/tests/livechat?headless&loglevel=2&preset=desktop"
            f"&timeout=15000&id={suite_id}",
            "",
            "",
            login="admin",
            timeout=1800,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=test_js.unit_test_error_checker,
        )
