# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_community.tests.common import LinkupCommunityCase
from odoo.addons.mail_linkup_community.tests.test_moderation import (
    LinkupModerationMixin,
)

MEMBER = "mail_linkup_reflet.group_linkup_member"
MODULE = "im_livechat_linkup_reflect"


class LinkupLivechatMixin:
    """The two channels of the data, their scripts, and Nicolas, a member
    who volunteers as operator of the welcome channel. Nobody is online
    until a test says so (``_online``)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.nicolas = mail_new_test_user(
            cls.env,
            login="linkup_lc_nicolas",
            name="Nicolas",
            email="linkup_lc_nicolas@example.com",
            groups=MEMBER,
        )
        cls.welcome = cls.env.ref(f"{MODULE}.livechat_channel_welcome")
        cls.distress = cls.env.ref(f"{MODULE}.livechat_channel_distress")
        cls.welcome.user_ids = cls.nicolas
        cls.welcome_script = cls.env.ref(f"{MODULE}.chatbot_script_welcome")
        cls.guide_script = cls.env.ref(f"{MODULE}.chatbot_script_guide")
        cls.bot = cls.env.ref(f"{MODULE}.partner_linkup_bot")
        cls.public = cls.env.ref("base.public_user")
        cls.Channel = cls.env["discuss.channel"]
        cls.Guest = cls.env["mail.guest"]
        cls.GuestEvent = cls.env["linkup.guest.event"]
        cls.Ledger = cls.env["linkup.points.ledger"]
        # Nobody but the users a test sets online is available.
        cls.env["bus.presence"].sudo().search([]).unlink()

    def _record_events(self):
        """Keep the scoring events real: the ledger is what the points of
        a visitor are checked against."""
        self.events = []

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

    def _answer(self, step_xmlid):
        return self.env.ref(f"{MODULE}.{step_xmlid}")

    # Conversations

    def _visitor(self, name="Visiteur"):
        return self.Guest.sudo().create({"name": name})

    def _welcome_session(self, guest=None):
        """A conversation of the welcome channel opened as
        ``/im_livechat/get_session`` opens it for a visitor: its welcome
        steps posted, the visitor added. Return ``(conversation,
        visitor)``."""
        guest = guest or self._visitor()
        script = self.welcome_script.sudo()
        vals = (
            self.welcome.sudo()
            .with_context(lang=False)
            ._get_livechat_discuss_channel_vals(
                "Visiteur", chatbot_script=script
            )
        )
        channel = self.Channel._linkup_server_create(vals)
        script._post_welcome_steps(channel)
        channel._add_members(guests=guest, post_joined_message=False)
        return channel, guest

    def _as_visitor(self, channel, guest, **context):
        return channel.with_user(self.public).with_context(
            guest=guest, **context
        )

    def _post(self, channel, body, user=None, guest=None, **context):
        """Post a comment as ``/mail/message/post`` does: under ``sudo``,
        for the user or the visitor of the request."""
        if guest:
            channel = self._as_visitor(channel, guest, **context)
        else:
            channel = channel.with_user(user).with_context(**context)
        return channel.sudo().message_post(
            body=body, message_type="comment", subtype_xmlid="mail.mt_comment"
        )

    def _chatbot(self, channel, body, answer=None, user=None, guest=None):
        """Answer the current step as the widget does: post the answer,
        with the choice made, then trigger the next step as
        ``/chatbot/step/trigger``. In the guide of a member, which the
        server runs in Discuss, the post alone answers. Return the next
        step."""
        context = {"selected_answer_id": answer.id} if answer else {}
        message = self._post(channel, body, user=user, guest=guest, **context)
        if channel.sudo().linkup_member_guide:
            return channel.sudo().chatbot_current_step_id
        if guest:
            channel = self._as_visitor(channel, guest)
        else:
            channel = channel.with_user(user)
        step = channel.sudo().chatbot_current_step_id
        next_step = step._process_answer(channel, message.body)
        if next_step:
            next_step._process_step(channel)
        return next_step

    def _trigger(self, channel, user=None, guest=None):
        """Trigger the step that follows a step without question, as the
        widget does once it shows it."""
        if guest:
            channel = self._as_visitor(channel, guest)
        else:
            channel = channel.with_user(user)
        step = channel.sudo().chatbot_current_step_id
        next_step = step._process_answer(channel, "")
        if next_step:
            next_step._process_step(channel)
        return next_step

    def _bot_bodies(self, channel):
        return (
            channel.sudo()
            .message_ids.filtered(lambda m: m.author_id == self.bot)
            .sorted("id")
            .mapped("body")
        )

    def _member_session(self, guest=None):
        """A conversation of the welcome channel where Nicolas joined the
        visitor through "Talk to a member"."""
        self._online(self.nicolas)
        channel, guest = self._welcome_session(guest)
        step = self._chatbot(
            channel,
            "Talk to a member",
            answer=self._answer("welcome_answer_member"),
            guest=guest,
        )
        self.assertEqual(step, self._answer("welcome_step_member"))
        self.assertIn(
            self.nicolas.partner_id,
            channel.sudo().channel_member_ids.partner_id,
        )
        return channel, guest


class LinkupLivechatCase(
    LinkupLivechatMixin, LinkupModerationMixin, LinkupCommunityCase
):
    """The members of the community (Sam, France, Jacques, Luce), its
    moderators (Joanna, Jean, Thomas linked to Sam) and administrator
    (Henri), and the live chat of LinkUp."""
