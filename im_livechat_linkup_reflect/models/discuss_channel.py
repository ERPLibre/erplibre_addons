# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from markupsafe import Markup
from odoo import SUPERUSER_ID, api, models
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError

from ..authorization import bot_post, in_bot_post, livechat_post_reflet_id


class DiscussChannel(models.Model):
    """The start rule of LinkUp in a live chat conversation (LU-F-127 RM3).

    A conversation of the distress channel has none. Any other live chat
    conversation follows its own ``linkup_start_rule``, else the one of its
    live chat channel, else the global mode (LU-F-060). The condition is a
    confirmed reflection of this conversation, whoever its parties are.

    The rule binds every party, the visitor and the operator alike, once
    the conversation holds two people: the answers to the chatbot before a
    human operator joins are never refused. The carrier message of a
    reflection of the conversation (``authorization.livechat_post``) and
    the messages of the chatbot (``authorization.bot_post``) pass.
    """

    _inherit = "discuss.channel"

    def _linkup_livechat_kind(self):
        """The LinkUp role of the live chat channel of the conversation."""
        self.ensure_one()
        return self.sudo().livechat_channel_id.linkup_kind

    def _linkup_start_rule(self):
        self.ensure_one()
        if self.channel_type != "livechat":
            return super()._linkup_start_rule()
        if self._linkup_livechat_kind() == "distress":
            return "off"
        channel = self.sudo()
        for mode in (
            channel.linkup_start_rule,
            channel.livechat_channel_id.linkup_start_rule,
        ):
            if mode and mode != "inherit":
                return mode
        return self._linkup_global_start_rule()

    def _linkup_livechat_people(self):
        """The number of people in a live chat conversation: its visitors
        (``mail.guest``) and the partners of a user, the superuser and the
        partner of a chatbot, which has no user, left out."""
        self.ensure_one()
        # sudo: discuss.channel.member - the parties of the conversation
        members = self.sudo().channel_member_ids
        root = self.env["res.users"].sudo().browse(SUPERUSER_ID).partner_id
        partners = members.partner_id.with_context(active_test=False).filtered(
            lambda partner: partner.user_ids and partner != root
        )
        return len(members.guest_id) + len(partners)

    def _linkup_livechat_pair(self):
        """Whether the conversation holds the two parties of a reflection
        of a live chat: one visitor and one member who operates it, not
        suspended."""
        self.ensure_one()
        guests = self.sudo().channel_member_ids.guest_id
        if len(guests) != 1:
            return False
        try:
            self.env["linkup.reflet"]._linkup_livechat_counterpart(
                self.sudo(), self.env["res.users"], guests
            )
        except LinkupError:
            return False
        return True

    def _linkup_start_rule_info(self):
        """What the web client reads of a live chat conversation of
        LinkUp: the role of its live chat channel
        (``linkup_livechat_kind``), whether a reflection may go between its
        visitor and its member (``linkup_can_reflect``), and the start
        rule, reported as satisfied while it does not bind yet, before a
        second person joins."""
        info = super()._linkup_start_rule_info()
        if self.channel_type != "livechat":
            return info
        kind = self._linkup_livechat_kind() or False
        info["linkup_livechat_kind"] = kind
        info["linkup_can_reflect"] = bool(
            kind == "welcome" and self._linkup_livechat_pair()
        )
        if self._linkup_livechat_people() < 2:
            info["linkup_start_rule_satisfied"] = True
        return info

    def _linkup_start_rule_satisfied(self, user):
        """In a live chat conversation, a confirmed reflection of this
        conversation opens it to both parties."""
        self.ensure_one()
        if self.channel_type != "livechat":
            return super()._linkup_start_rule_satisfied(user)
        return bool(
            self.env["linkup.reflet"]
            .sudo()
            .search_count(
                [
                    ("channel_id", "=", self.id),
                    ("kind", "=", "initial"),
                    ("state", "=", "confirmed"),
                ],
                limit=1,
            )
        )

    def _linkup_start_rule_blocks(self, user):
        """In a live chat conversation, ``strict`` refuses the free text of
        whoever posts, the visitor included, once two people hold it and
        until a reflection of it is confirmed."""
        self.ensure_one()
        if self.channel_type != "livechat":
            return super()._linkup_start_rule_blocks(user)
        return (
            self._linkup_start_rule() == "strict"
            and self._linkup_livechat_people() >= 2
            and not self._linkup_start_rule_satisfied(user)
        )

    def _linkup_check_start_rule(self, message_type):
        """Let the carrier of a reflection of a live chat conversation and
        the messages of its chatbot through the start rule."""
        allowed = self.filtered(
            lambda channel: channel.channel_type == "livechat"
            and (
                livechat_post_reflet_id(channel.id) or in_bot_post(channel.id)
            )
        )
        return super(DiscussChannel, self - allowed)._linkup_check_start_rule(
            message_type
        )

    def _chatbot_post_message(self, chatbot_script, body):
        """Post as the chatbot, which the start rule lets through."""
        with bot_post(self.ids):
            return super()._chatbot_post_message(chatbot_script, body)

    def _chatbot_restart(self, chatbot_script):
        """``/chatbot/restart`` restarts the script of a conversation of
        LinkUp only while its party holds it alone with the chatbot: once
        a member or a moderator joined, or in a conversation of distress,
        the script stays done, so that no step of it (a moderator, a member,
        the guide) reaches a conversation that holds two people."""
        for channel in self:
            kind = channel._linkup_livechat_kind()
            if kind and (
                kind == "distress" or channel._linkup_livechat_people() >= 2
            ):
                raise channel._linkup_unavailable()
        return super()._chatbot_restart(chatbot_script)

    def _message_post_after_hook(self, message, msg_vals):
        """Link the carrier message of a reflection of a live chat
        conversation before the broadcast, so that the new message carries
        the card."""
        reflet_id = len(self) == 1 and livechat_post_reflet_id(self.id)
        if reflet_id:
            reflet = self.env["linkup.reflet"].sudo().browse(reflet_id)
            if reflet.channel_id == self and not reflet.message_id:
                reflet.message_id = message
        return super()._message_post_after_hook(message, msg_vals)

    @api.model
    def _linkup_livechat_conversation(self, channel_id):
        """The live chat conversation ``channel_id`` of the welcome channel,
        under ``sudo``, or an empty recordset."""
        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            return self.sudo().browse()
        channel = self.sudo().browse(channel_id).exists()
        if (
            channel.channel_type != "livechat"
            or channel.livechat_channel_id.linkup_kind != "welcome"
        ):
            return self.sudo().browse()
        return channel

    @api.model
    def _linkup_server_create(self, vals):
        """Create a live chat conversation opened by the server, under
        ``sudo`` as the public user, as ``/im_livechat/get_session`` does:
        its members are those of ``vals`` only, no creator joins it, and
        the checks of the scope of a member, which read the real user, do
        not bind the server."""
        return (
            self.with_user(self.env.ref("base.public_user"))
            .sudo()
            .with_context(mail_create_nosubscribe=False)
            .create(vals)
        )

    def _linkup_post_distress_notice(self, lang):
        """Post, in the conversation of distress, the reminder that LinkUp
        is not an emergency service (LU-F-118 RM3), as a notification of
        the server in the language ``lang``."""
        Report = self.env["linkup.report"]
        text = Report.with_context(lang=lang)._linkup_distress_notice()
        for conversation in self.sudo():
            conversation.message_post(
                author_id=self.env.ref("base.partner_root").id,
                body=Markup('<div class="o_mail_notification">%s</div>')
                % text,
                message_type="notification",
                subtype_xmlid="mail.mt_comment",
            )
