# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The limit of "Need help now" (LU-NF-006, LU-F-126): at most
``linkup.livechat_help_now_per_hour`` urgent reports an hour, counted for a
visitor and for the address of the request. Beyond it, the resources still
show, but no report is created and no moderator is brought."""

from odoo.tests import tagged

from .common import LinkupLivechatCase

ALREADY = "Your request is already with the moderation team."


@tagged("post_install", "-at_install")
class TestLinkupHelpNowLimit(LinkupLivechatCase):
    def _press(self, channel, guest):
        """Press "Need help now" in the widget, as
        ``/linkup/v1/livechat/help_now`` does for the visitor ``guest``."""
        return (
            self.env["chatbot.script.step"]
            .with_user(self.public)
            .with_context(guest=guest)
            ._linkup_help_now(channel.id, guest=guest)
        )

    def _reports(self):
        return (
            self.env["linkup.report"]
            .sudo()
            .search(
                [
                    ("reason", "=", "distress"),
                    ("reporter_guest_id", "!=", False),
                ]
            )
        )

    def _set_limit(self, value):
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.livechat_help_now_per_hour", value
        )

    def test_fourth_press_of_a_visitor(self):
        """The third press of a visitor in an hour creates its urgent
        report; the fourth, in a new conversation, creates none and brings
        no moderator, even one online: the visitor reads the resources and
        that the request is already with the team."""
        guest = self._visitor()
        for _press in range(3):
            channel, guest = self._welcome_session(guest)
            result = self._press(channel, guest)
            self.assertFalse(result["limited"])
        self.assertEqual(len(self._reports()), 3)
        self.assertIn("queue", self._bot_bodies(channel)[-1])
        self._online(self.jean)
        channel, guest = self._welcome_session(guest)
        result = self._press(channel, guest)
        self.assertTrue(result["limited"])
        self.assertFalse(result["operator_found"])
        self.assertTrue(result["resources"])
        self.assertEqual(len(self._reports()), 3)
        self.assertEqual(channel.livechat_channel_id, self.welcome)
        self.assertNotIn(
            self.jean.partner_id, channel.sudo().channel_member_ids.partner_id
        )
        body = self._bot_bodies(channel)[-1]
        self.assertIn(ALREADY, body)
        self.assertIn("9-8-8", body)
        self.assertNotIn("queue", body)

    def test_fourth_press_from_one_address(self):
        """Four visitors behind one address: the fourth press, through the
        step "Need help now" of the welcome script, is held back as
        well."""
        for _press in range(3):
            channel, guest = self._welcome_session()
            self.assertFalse(self._press(channel, guest)["limited"])
        self._online(self.jean)
        channel, guest = self._welcome_session()
        self._chatbot(
            channel,
            "Need help now",
            answer=self._answer("welcome_answer_help"),
            guest=guest,
        )
        self.assertEqual(len(self._reports()), 3)
        self.assertNotIn(
            self.jean.partner_id, channel.sudo().channel_member_ids.partner_id
        )
        self.assertIn(ALREADY, self._bot_bodies(channel)[-1])

    def test_press_again_in_an_open_report(self):
        """A press in a conversation whose report is still open creates no
        report, so the limit never holds it back."""
        guest = self._visitor()
        for _press in range(3):
            channel, guest = self._welcome_session(guest)
            self._press(channel, guest)
        result = self._press(channel, guest)
        self.assertFalse(result["limited"])
        self.assertEqual(len(self._reports()), 3)

    def test_parameter(self):
        """The limit is a setting; a value below 1 falls back to 3."""
        self._set_limit("1")
        guest = self._visitor()
        channel, guest = self._welcome_session(guest)
        self.assertFalse(self._press(channel, guest)["limited"])
        channel, guest = self._welcome_session(guest)
        self.assertTrue(self._press(channel, guest)["limited"])
        self._set_limit("0")
        channel, guest = self._welcome_session(guest)
        self.assertFalse(self._press(channel, guest)["limited"])
        self.assertEqual(len(self._reports()), 2)
