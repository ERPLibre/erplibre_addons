# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The guide of a first reflection (T-53, LU-F-125): the steps added to
the chatbot, the draft each answer writes, the refusal of an empty text,
and a chatbot that never sends."""

import json

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from .common import MEMBER, LinkupLivechatCase

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

    def test_guide_kept_to_the_server(self):
        """Sam marks none of his conversations as a guide, nor chooses the
        step of its chatbot; a group marked as a guide otherwise gets no
        answer of the chatbot."""
        step = self.env.ref("im_livechat_linkup_reflect.guide_step_understood")
        workshop = self.workshop.with_user(self.sam)
        for vals in (
            {"linkup_member_guide": True},
            {"chatbot_current_step_id": step.id},
        ):
            with self.subTest(vals=vals), self.assertRaises(AccessError):
                workshop.write(vals)
        group = self.Channel.create(
            {
                "name": "Groupe",
                "channel_type": "group",
                "channel_partner_ids": [
                    Command.link(user.partner_id.id)
                    for user in (self.sam, self.france)
                ],
                "linkup_member_guide": True,
                "chatbot_current_step_id": step.id,
            }
        )
        self._post(group, UNDERSTOOD, user=self.sam)
        self.assertFalse(self._bot_bodies(group))
        self.assertFalse(self._drafts(self.sam))

    def test_guide_not_created_by_a_member(self):
        """Sam creates no conversation marked as a guide or holding a step
        of its chatbot, through the values or the defaults of the context,
        the latter under ``sudo`` included; the same group without them
        opens."""
        step = self.env.ref("im_livechat_linkup_reflect.guide_step_understood")
        Channel = self.Channel.with_user(self.sam)
        vals = {"name": "Groupe", "channel_type": "group"}
        for channel_vals, context in (
            (dict(vals, linkup_member_guide=True), {}),
            (dict(vals, chatbot_current_step_id=step.id), {}),
            (vals, {"default_linkup_member_guide": True}),
            (vals, {"default_chatbot_current_step_id": step.id}),
        ):
            models = (Channel, Channel.sudo()) if context else (Channel,)
            for model in models:
                with self.subTest(vals=channel_vals, context=context):
                    with self.assertRaisesRegex(AccessError, "guide"):
                        model.with_context(**context).create(
                            dict(channel_vals)
                        )
        group = Channel.create(dict(vals))
        self.assertFalse(group.sudo().chatbot_current_step_id)


@tagged("post_install", "-at_install")
class TestLinkupChatbotRoutes(LinkupLivechatCase, HttpCase):
    """``/chatbot/restart`` and ``/chatbot/step/trigger`` run a script
    only in a live chat conversation, and only its own."""

    def _rpc(self, route, params):
        response = self.url_open(
            route,
            data=json.dumps(
                {"jsonrpc": "2.0", "method": "call", "id": 1, "params": params}
            ),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _chat(self):
        """The direct conversation of Sam and France, opened by a
        confirmed reflection."""
        self._confirmed()
        return self.Channel.with_user(self.sam).channel_get(
            [self.france.partner_id.id]
        )

    def test_routes_refused_outside_live_chat(self):
        """Sam restarts then triggers the welcome script and the script of
        the guide in his group and his direct conversation: refused, no
        step is set there and the chatbot posts nothing."""
        chat = self._chat()
        self.authenticate(self.sam.login, self.sam.login)
        for channel in (self.workshop, chat):
            for script in (self.welcome_script, self.guide_script):
                params = {
                    "channel_id": channel.id,
                    "chatbot_script_id": script.id,
                }
                with self.subTest(channel=channel.name, script=script.title):
                    self.assertIn(
                        "error", self._rpc("/chatbot/restart", params)
                    )
                    self.assertIn(
                        "error", self._rpc("/chatbot/step/trigger", params)
                    )
                    self.env.invalidate_all()
                    self.assertFalse(channel.sudo().chatbot_current_step_id)
                    self.assertFalse(self._bot_bodies(channel))

    def test_test_page_restarts_its_script(self):
        """The default administrator tests the welcome script, then a
        script outside LinkUp, on the test page of each, and restarts it:
        the first step of the script follows the restart."""
        other = self.env["chatbot.script"].create(
            {
                "title": "Essai",
                "script_step_ids": [
                    Command.create({"step_type": "text", "message": "Bonjour"})
                ],
            }
        )
        self.authenticate("admin", "admin")
        for script in (self.welcome_script, other):
            with self.subTest(script=script.title):
                response = self.url_open(f"/chatbot/{script.id}/test")
                self.assertEqual(response.status_code, 200)
                channel = self.Channel.sudo().search(
                    [
                        ("channel_type", "=", "livechat"),
                        ("livechat_channel_id", "=", False),
                        (
                            "livechat_operator_id",
                            "=",
                            script.operator_partner_id.id,
                        ),
                    ],
                    order="id desc",
                    limit=1,
                )
                params = {
                    "channel_id": channel.id,
                    "chatbot_script_id": script.id,
                }
                self.assertNotIn(
                    "error", self._rpc("/chatbot/restart", params)
                )
                self.assertNotIn(
                    "error", self._rpc("/chatbot/step/trigger", params)
                )
                self.env.invalidate_all()
                self.assertEqual(
                    channel.chatbot_current_step_id,
                    script.script_step_ids.sorted("sequence")[:1],
                )

    def test_linkup_administrator_tests_a_script(self):
        """Henri, a LinkUp administrator who is not a system administrator,
        opens the test page of the welcome script, then restarts it: the
        conversation of the test holds its first step."""
        henri = mail_new_test_user(
            self.env,
            login="linkup_lc_test_admin",
            name="Henri",
            email="linkup_lc_test_admin@example.com",
            groups=f"{MEMBER},mail_linkup_reflet.group_linkup_admin,"
            "im_livechat.im_livechat_group_user",
        )
        self.assertFalse(henri.has_group("base.group_system"))
        script = self.welcome_script
        self.authenticate(henri.login, henri.login)
        response = self.url_open(f"/chatbot/{script.id}/test")
        self.assertEqual(response.status_code, 200)
        channel = self.Channel.sudo().search(
            [
                ("channel_type", "=", "livechat"),
                ("livechat_channel_id", "=", False),
                ("channel_member_ids.partner_id", "=", henri.partner_id.id),
            ],
            order="id desc",
            limit=1,
        )
        self.assertTrue(channel.chatbot_current_step_id)
        params = {"channel_id": channel.id, "chatbot_script_id": script.id}
        self.assertNotIn("error", self._rpc("/chatbot/restart", params))
        self.assertNotIn("error", self._rpc("/chatbot/step/trigger", params))
        self.env.invalidate_all()
        self.assertEqual(
            channel.chatbot_current_step_id,
            script.script_step_ids.sorted("sequence")[:1],
        )

    def test_operator_scripts_kept_from_plain_members(self):
        """A live chat conversation without a live chat channel that holds
        Sam, led by the LinkUp bot, runs no script of the bot: Sam
        neither restarts it nor runs its first step there."""
        channel = self.Channel.sudo().create(
            {
                "name": "Essai",
                "channel_type": "livechat",
                "livechat_operator_id": self.bot.id,
                "channel_member_ids": [
                    Command.create({"partner_id": self.sam.partner_id.id}),
                    Command.create({"partner_id": self.bot.id}),
                ],
            }
        )
        first = self.welcome_script.script_step_ids.sorted("sequence")[:1]
        as_sam = channel.with_user(self.sam)
        with self.assertLinkupCode("linkup.unavailable"):
            as_sam._chatbot_restart(self.welcome_script)
        with self.assertLinkupCode("linkup.unavailable"):
            first._process_step(as_sam)
        self.assertFalse(channel.chatbot_current_step_id)

    def test_script_of_another_conversation_refused(self):
        """A visitor of the welcome channel restarts their conversation
        with the script of the guide, or runs a step of it: refused, the
        welcome script restarts."""
        channel, guest = self._welcome_session()
        visitor = self._as_visitor(channel, guest)
        first = self.guide_script.script_step_ids.sorted("sequence")[:1]
        with self.assertLinkupCode("linkup.unavailable"):
            visitor._chatbot_restart(self.guide_script)
        with self.assertLinkupCode("linkup.unavailable"):
            first._process_step(visitor)
        visitor._chatbot_restart(self.welcome_script)
        self.assertFalse(channel.chatbot_current_step_id)

    def test_guide_answers_no_route(self):
        """The guide of Sam, run by the server, answers neither route: its
        step and the posts of its chatbot stay as they were."""
        result = self.Reflet.with_user(self.sam).linkup_start_guide()
        guide = self.Channel.sudo().browse(result["channel_id"])
        step = guide.chatbot_current_step_id
        bodies = self._bot_bodies(guide)
        self.authenticate(self.sam.login, self.sam.login)
        params = {
            "channel_id": guide.id,
            "chatbot_script_id": self.guide_script.id,
        }
        for route in ("/chatbot/restart", "/chatbot/step/trigger"):
            with self.subTest(route=route):
                response = self._rpc(route, params)
                self.assertNotIn("error", response)
                self.assertIsNone(response.get("result"))
        self.env.invalidate_all()
        self.assertEqual(guide.chatbot_current_step_id, step)
        self.assertEqual(self._bot_bodies(guide), bodies)
