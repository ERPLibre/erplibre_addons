# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The guide of a first reflection (T-53, LU-F-125): the steps added to
the chatbot, the draft each answer writes, the refusal of an empty text,
and a chatbot that never sends."""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import LinkupLivechatCase

YOU_SAID = "Que la pluie te rend calme."
UNDERSTOOD = "Que tu aimes les jours tranquilles."


@tagged("post_install", "-at_install")
class TestLinkupLivechatGuide(LinkupLivechatCase):
    def _category_answer(self, step, category):
        return step.answer_ids.filtered(
            lambda answer: answer.linkup_category_id == category
        )

    def _start(self, user=None):
        user = user or self.sam
        result = self.Reflet.with_user(user).linkup_start_guide()
        return self.Channel.browse(result["channel_id"]).sudo()

    def _guide(self, channel, user=None, category=None):
        """Answer the category step, then both texts, as ``user``."""
        user = user or self.sam
        step = self.env.ref("im_livechat_linkup_reflect.guide_step_category")
        category = category or self.emotions
        self._chatbot(
            channel,
            category.name,
            answer=self._category_answer(step, category),
            user=user,
        )
        self._chatbot(channel, YOU_SAID, user=user)
        return self._chatbot(channel, UNDERSTOOD, user=user)

    def _drafts(self, user):
        return self.Reflet.sudo().search(
            [("author_id", "=", user.id), ("state", "=", "draft")]
        )

    def test_step_types(self):
        """RM1: the four steps of the guide and the forward to a moderator
        are types of ``chatbot.script.step``."""
        types = dict(
            self.env["chatbot.script.step"]._fields["step_type"].selection
        )
        for code in (
            "linkup_category",
            "linkup_you_said",
            "linkup_understood",
            "linkup_reflet_review",
            "linkup_forward_moderator",
        ):
            self.assertIn(code, types)
        self.assertEqual(
            self.guide_script.script_step_ids.sorted("sequence").mapped(
                "step_type"
            ),
            [
                "text",
                "linkup_category",
                "linkup_you_said",
                "linkup_understood",
                "linkup_reflet_review",
            ],
        )

    def test_category_answers_follow_the_categories(self):
        """RM1: the answers of a category step are the active categories,
        each with its definition in the message of the step; an archived
        category leaves them."""
        step = self.env.ref("im_livechat_linkup_reflect.guide_step_category")
        categories = self.env["linkup.category"].search([])
        self.assertEqual(step.answer_ids.linkup_category_id, categories)
        self.emotions.sudo().active = False
        self.assertFalse(self._category_answer(step, self.emotions))
        self.emotions.sudo().active = True
        self.assertTrue(self._category_answer(step, self.emotions))
        channel = self._start()
        body = self._bot_bodies(channel)[-1]
        for category in categories:
            self.assertIn(category.name, body)

    def test_guide_writes_a_draft(self):
        """CA1, RM2, RM3: Emotions, then both texts, make a draft of Sam
        with that category and those texts; nothing is sent, no carrier
        message is posted, and the review tells where the draft waits."""
        channel = self._start()
        self.assertEqual(channel.channel_type, "livechat")
        self.assertEqual(
            channel.channel_member_ids.partner_id,
            self.sam.partner_id | self.bot,
        )
        step = self._guide(channel)
        self.assertEqual(step.step_type, "linkup_reflet_review")
        draft = self._drafts(self.sam)
        self.assertEqual(len(draft), 1)
        self.assertEqual(draft.category_id, self.emotions)
        self.assertEqual(draft.you_said, YOU_SAID)
        self.assertEqual(draft.understood, UNDERSTOOD)
        self.assertFalse(draft.message_id)
        self.assertFalse(draft.channel_id)
        self.assertFalse(
            self.Reflet.sudo().search(
                [("author_id", "=", self.sam.id), ("state", "!=", "draft")]
            )
        )
        review = self._bot_bodies(channel)[-1]
        self.assertIn(UNDERSTOOD, review)
        self.assertIn("Reflet view", review)
        # The body of the "You told me" step shows the category chosen and
        # its examples.
        you_said_body = self._bot_bodies(channel)[-3]
        self.assertIn(self.emotions.name, you_said_body)

    def test_empty_text_refused(self):
        """CA2: an empty "I understood that" is refused by the server with
        ``linkup.validation``, and the step stays the current one."""
        channel = self._start()
        step = self.env.ref("im_livechat_linkup_reflect.guide_step_category")
        self._chatbot(
            channel,
            self.emotions.name,
            answer=self._category_answer(step, self.emotions),
            user=self.sam,
        )
        self._chatbot(channel, YOU_SAID, user=self.sam)
        understood = self.env.ref(
            "im_livechat_linkup_reflect.guide_step_understood"
        )
        self.assertEqual(channel.chatbot_current_step_id, understood)
        with self.assertLinkupCode("linkup.validation", field="understood"):
            self._chatbot(channel, "   ", user=self.sam)
        self.assertEqual(channel.chatbot_current_step_id, understood)
        self.assertFalse(self._drafts(self.sam).understood)

    def test_text_too_long_refused(self):
        """RM2: the length of LU-F-013 RM2 binds the guide as the card."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.reflet_text_max_length", "10"
        )
        channel = self._start()
        step = self.env.ref("im_livechat_linkup_reflect.guide_step_category")
        self._chatbot(
            channel,
            self.emotions.name,
            answer=self._category_answer(step, self.emotions),
            user=self.sam,
        )
        with self.assertLinkupCode("linkup.validation", field="you_said"):
            self._chatbot(channel, YOU_SAID, user=self.sam)

    def test_category_required(self):
        """RM2: a category step answered by a typed text, without a
        category chosen, is refused."""
        channel = self._start()
        with self.assertLinkupCode("linkup.validation", field="category_id"):
            self._chatbot(channel, "Une catégorie", user=self.sam)

    def test_draft_restored_in_the_reflet_view(self):
        """CA3: the Reflet view restores the draft filled by the guide."""
        self._guide(self._start())
        info = self.Reflet.with_user(self.sam)._linkup_draft_info()
        self.assertEqual(info["category_id"], self.emotions.id)
        self.assertEqual(info["you_said"], YOU_SAID)
        self.assertEqual(info["understood"], UNDERSTOOD)

    def test_restart_keeps_the_draft(self):
        """RM4: "Restart" starts the script again without erasing the
        draft; choosing another category keeps the texts."""
        channel = self._start()
        self._guide(channel)
        mine = channel.with_user(self.sam)
        mine._chatbot_restart(self.guide_script)
        draft = self._drafts(self.sam)
        self.assertEqual(draft.understood, UNDERSTOOD)
        # The widget then starts the script from its first step.
        self.guide_script.script_step_ids.sorted("sequence")[:1]._process_step(
            mine
        )
        step = self._trigger(channel, user=self.sam)
        self.assertEqual(
            step,
            self.env.ref("im_livechat_linkup_reflect.guide_step_category"),
        )
        self._chatbot(
            channel,
            self.needs.name,
            answer=self._category_answer(step, self.needs),
            user=self.sam,
        )
        self.assertEqual(draft.category_id, self.needs)
        self.assertEqual(draft.you_said, YOU_SAID)
        self.assertEqual(draft.understood, UNDERSTOOD)

    def test_guide_of_a_visitor(self):
        """RM2: in the welcome widget, the guide writes the draft of the
        visitor, never a draft of a member; the answers to the chatbot pass
        the start rule."""
        channel, guest = self._welcome_session()
        self._chatbot(
            channel,
            "Try a guided reflection",
            answer=self._answer("welcome_answer_guide"),
            guest=guest,
        )
        step = self._answer("welcome_step_guide_category")
        self.assertEqual(channel.chatbot_current_step_id, step)
        self._chatbot(
            channel,
            self.goals.name,
            answer=self._category_answer(step, self.goals),
            guest=guest,
        )
        self._chatbot(channel, YOU_SAID, guest=guest)
        review = self._chatbot(channel, UNDERSTOOD, guest=guest)
        self.assertEqual(review.step_type, "linkup_reflet_review")
        draft = self.Reflet._linkup_guest_draft(guest)
        self.assertEqual(draft.category_id, self.goals)
        self.assertEqual(draft.understood, UNDERSTOOD)
        self.assertFalse(draft.author_id)
        self.assertIn("Talk to a member", self._bot_bodies(channel)[-1])

    def test_conversation_of_another_party(self):
        """RM2: an answer is written only by a member of the conversation:
        a visitor of another conversation gets an access error."""
        channel, guest = self._welcome_session()
        self._chatbot(
            channel,
            "Try a guided reflection",
            answer=self._answer("welcome_answer_guide"),
            guest=guest,
        )
        step = self._answer("welcome_step_guide_category")
        other = self._as_visitor(channel, self._visitor("Autre"))
        with self.assertRaises(AccessError):
            other.sudo().chatbot_current_step_id._linkup_party(other)
        with self.assertRaises(AccessError):
            self._chatbot(
                channel,
                self.goals.name,
                answer=self._category_answer(step, self.goals),
                guest=other.env.context["guest"],
            )
        self.assertFalse(
            self.Reflet._linkup_guest_draft(other.env.context["guest"])
        )
