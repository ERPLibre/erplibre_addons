# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The guide of a member run by the server in Discuss (LU-F-125 RM5): each
post of the member answers the current step, and ``linkup_guide`` tells
the web client the step to answer."""

from odoo.tests import tagged

from .common import LinkupLivechatCase


@tagged("post_install", "-at_install")
class TestLinkupMemberGuide(LinkupLivechatCase):
    def _start(self):
        result = (
            self.env["linkup.reflet"].with_user(self.sam).linkup_start_guide()
        )
        return self.Channel.browse(result["channel_id"]).sudo()

    def _step(self, xmlid):
        return self.env.ref(f"im_livechat_linkup_reflect.{xmlid}")

    def test_guide_info_follows_the_steps(self):
        """The guide opens on the choice of the category, whose answers
        are the categories; each post of Sam moves it on, and the review
        waits for nothing."""
        channel = self._start()
        self.assertTrue(channel.linkup_member_guide)
        info = channel.with_user(self.sam)._channel_basic_info()[
            "linkup_guide"
        ]
        self.assertEqual(info["step_type"], "linkup_category")
        self.assertEqual(info["expects"], "choice")
        step = self._step("guide_step_category")
        answer = step.answer_ids.filtered(
            lambda item: item.linkup_category_id == self.emotions
        )
        self.assertIn({"id": answer.id, "name": answer.name}, info["answers"])
        self._post(
            channel, answer.name, user=self.sam, selected_answer_id=answer.id
        )
        self.assertEqual(
            channel.chatbot_current_step_id, self._step("guide_step_you_said")
        )
        self.assertEqual(channel._linkup_guide_info()["expects"], "text")
        self._post(channel, "Que la pluie te rend calme.", user=self.sam)
        self._post(channel, "Que tu aimes le calme.", user=self.sam)
        self.assertEqual(
            channel.chatbot_current_step_id, self._step("guide_step_review")
        )
        self.assertFalse(channel._linkup_guide_info()["expects"])
        draft = (
            self.env["linkup.reflet"]
            .sudo()
            .search([("author_id", "=", self.sam.id), ("state", "=", "draft")])
        )
        self.assertEqual(draft.category_id, self.emotions)
        self.assertEqual(draft.understood, "Que tu aimes le calme.")
        # Once the script waits for nothing, a post is a plain message.
        before = len(channel.message_ids)
        self._post(channel, "Merci !", user=self.sam)
        self.assertEqual(len(channel.message_ids), before + 1)

    def test_post_of_the_bot_answers_nothing(self):
        """The messages of the chatbot never answer a step: the welcome
        steps leave the guide on the choice of the category."""
        channel = self._start()
        self.assertEqual(
            channel.chatbot_current_step_id, self._step("guide_step_category")
        )

    def test_conversation_of_a_visitor_untouched(self):
        """A welcome conversation of a visitor is no guide of a member: its
        posts answer nothing on the server, the widget triggers its
        steps."""
        channel, guest = self._welcome_session()
        self.assertFalse(channel.linkup_member_guide)
        step = channel.chatbot_current_step_id
        self._post(channel, "Bonjour", guest=guest)
        self.assertEqual(channel.chatbot_current_step_id, step)
        self.assertNotIn("linkup_guide", channel._channel_basic_info())
