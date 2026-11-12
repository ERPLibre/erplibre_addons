# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import Command, _, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError, UserError

from ..authorization import (
    channel_post,
    current_post,
    in_server_notification,
    server_notification,
)
from ..exceptions import LinkupError
from .res_users import ADMIN_GROUP

# Modes of the start rule (LU-F-060), global and by conversation.
START_RULE_MODES = [
    ("strict", "Strict"),
    ("incitative", "Incentive"),
    ("off", "Off"),
]
START_RULE_PARAM = "linkup.start_rule_mode"
START_RULE_DEFAULT = "strict"
# What a restricted member does not write on a direct conversation: free
# text that the other party reads, past the start rule and a block.
CHAT_TEXT_FIELDS = frozenset({"name", "description", "image_128"})


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    linkup_start_rule = fields.Selection(
        [("inherit", "Global rule")] + START_RULE_MODES,
        string="LinkUp start rule",
        default="inherit",
        required=True,
        groups="mail_linkup_reflet.group_linkup_admin",
        help="Global rule: a direct conversation follows the start rule of"
        " the LinkUp settings, a group or a channel has none.",
    )
    linkup_effective_start_rule = fields.Selection(
        START_RULE_MODES,
        string="Effective start rule",
        compute="_compute_linkup_effective_start_rule",
        compute_sudo=True,
    )

    @api.depends("linkup_start_rule", "channel_type")
    def _compute_linkup_effective_start_rule(self):
        for channel in self:
            channel.linkup_effective_start_rule = channel._linkup_start_rule()

    # ------------------------------------------------------------------
    # Start rule (LU-F-060 to LU-F-063)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_global_start_rule(self):
        """The mode of the LinkUp settings, ``strict`` when unset or
        invalid."""
        mode = (
            self.env["ir.config_parameter"].sudo().get_param(START_RULE_PARAM)
        )
        modes = dict(START_RULE_MODES)
        return mode if mode in modes else START_RULE_DEFAULT

    def _linkup_start_rule(self):
        """The mode that applies to the conversation.

        A conversation set to ``inherit`` follows the global mode when it is
        a direct conversation, the mode of its parent when it is the thread
        of a channel, and has no rule otherwise; a mode set on the
        conversation by a LinkUp administrator wins. It is read on every
        post, never cached, so a change of the settings applies at once.
        """
        self.ensure_one()
        mode = self.sudo().linkup_start_rule
        if mode and mode != "inherit":
            return mode
        parent = self.sudo().parent_channel_id
        if parent:
            return parent._linkup_start_rule()
        if self.channel_type == "chat":
            return self._linkup_global_start_rule()
        return "off"

    def _linkup_start_rule_satisfied(self, user):
        """Tell whether a confirmed reflection opens the conversation.

        In a direct conversation, the condition belongs to the pair: it
        holds when the link of its two LinkUp members is ``active``, or
        when one party is not a restricted LinkUp member (a system
        administrator, a user outside LinkUp), so that both parties read
        the same answer. In a group or a channel, it holds when ``user``
        has an active link with another member of the conversation whose
        account is not archived, or is not a restricted member.
        """
        self.ensure_one()
        # sudo: discuss.channel.member - the parties of the conversation
        users = (
            self.sudo()
            .channel_member_ids.partner_id.with_context(active_test=False)
            .user_ids.filtered(lambda u: not u.share)
        )
        Link = self.env["linkup.link"].sudo()
        if self.channel_type == "chat":
            members = users.filtered(
                lambda u: u._linkup_is_restricted_member()
            )
            if len(members) < 2 or len(users) != 2:
                return True
            # A blocked pair reads as it did before the block, so that the
            # blocked member sees no change; a block refuses the posts by
            # itself (``_linkup_check_reach``).
            link = Link._get_between(members[0], members[1])
            return link.state == "active" or bool(
                link.state == "blocked" and link.first_link_date
            )
        if not user._linkup_is_restricted_member():
            return True
        # The link of an archived account opens no group: the conversation
        # goes on with the others only.
        others = (users - user).filtered("active")
        if not others:
            return False
        return bool(
            Link.search_count(
                [
                    ("state", "=", "active"),
                    "|",
                    "&",
                    ("user_a_id", "=", user.id),
                    ("user_b_id", "in", others.ids),
                    "&",
                    ("user_b_id", "=", user.id),
                    ("user_a_id", "in", others.ids),
                ],
                limit=1,
            )
        )

    def _linkup_start_rule_blocks(self, user):
        """Tell whether the start rule refuses the free text of ``user``
        here: a restricted member, in a ``strict`` conversation that no
        confirmed reflection opened yet."""
        self.ensure_one()
        return (
            user._linkup_is_restricted_member()
            and self._linkup_start_rule() == "strict"
            and not self._linkup_start_rule_satisfied(user)
        )

    def _linkup_check_start_rule(self, message_type):
        """Refuse a post that the start rule forbids.

        A ``notification`` passes when the server writes its text: under
        ``sudo``, or inside ``authorization.server_notification``, which
        the pin of a message and the arrival of a member open. Any other
        post is checked, whatever its type, attachments and voice messages
        included: the composer of the web client, a scheduled message or
        the feedback of an activity would otherwise post a client text as
        a ``notification``. The carrier message of a reflection passes
        through ``authorization.linkup_post`` alone, on the conversation of
        that reflection.
        """
        if message_type == "notification" and (
            self.env.su or in_server_notification()
        ):
            return
        user = self.env.user
        post = current_post(self.env)
        for channel in self:
            if (
                post
                and (
                    self.env["linkup.reflet"].sudo().browse(post.reflet_id)
                ).channel_id
                == channel
            ):
                continue
            if channel._linkup_start_rule_blocks(user):
                raise LinkupError(
                    "linkup.start_rule",
                    _(
                        "Start with a reflection of a real exchange: free"
                        " text opens once a reflection is confirmed in this"
                        " conversation."
                    ),
                )

    # ------------------------------------------------------------------
    # Block and suspension (LU-F-115)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_pair_chats(self, user1, user2):
        """The direct conversations of two users, under ``sudo``."""
        return (
            self.sudo()
            .search(
                [
                    ("channel_type", "=", "chat"),
                    (
                        "channel_member_ids.partner_id",
                        "=",
                        user1.partner_id.id,
                    ),
                    (
                        "channel_member_ids.partner_id",
                        "=",
                        user2.partner_id.id,
                    ),
                ]
            )
            .filtered(lambda chat: len(chat.channel_member_ids) == 2)
        )

    def _linkup_pair_blocked(self):
        """Tell whether the conversation is the direct conversation of a
        ``blocked`` pair."""
        self.ensure_one()
        users = self._linkup_chat_users()
        return (
            len(users) == 2
            and self.env["linkup.link"]._get_between(users[0], users[1]).state
            == "blocked"
        )

    def _linkup_pair_archived(self):
        """Tell whether the conversation is a direct conversation whose
        other party holds an archived account, banned or deleted."""
        self.ensure_one()
        if self.channel_type != "chat":
            return False
        # sudo: discuss.channel.member - the parties of the conversation
        users = (
            self.sudo()
            .channel_member_ids.partner_id.with_context(active_test=False)
            .user_ids.filtered(lambda user: not user.share)
        )
        return len(users) == 2 and not all(users.mapped("active"))

    def _linkup_unavailable(self):
        return LinkupError(
            "linkup.unavailable", _("This conversation is unavailable.")
        )

    def _linkup_check_reach(self, message_type):
        """Refuse what a suspension or a block forbids, before the start
        rule.

        A suspended member posts, reacts and calls nowhere. In the direct
        conversation of a ``blocked`` pair, nobody does: the refusal is
        ``linkup.unavailable``. A restricted member gets the same refusal
        in a direct conversation whose other party holds an archived
        account, the code of a deleted account. A ``notification`` whose
        text the server writes passes, as for the start rule.
        """
        if message_type == "notification" and (
            self.env.su or in_server_notification()
        ):
            return
        user = self.env.user
        user._linkup_check_not_suspended()
        restricted = user._linkup_is_restricted_member()
        for channel in self:
            if channel._linkup_pair_blocked() or (
                restricted and channel._linkup_pair_archived()
            ):
                raise channel._linkup_unavailable()

    def _linkup_drop_blocked_partners(self, partner_ids):
        """The partner ids of a post without those a block separates from
        its author: a mention never reaches them."""
        partners = (
            self.env["res.partner"]
            .sudo()
            .with_context(active_test=False)
            .browse(partner_ids)
        )
        blocked = self.env["linkup.block"]._linkup_blocked_users(self.env.user)
        if not blocked:
            return list(partner_ids)
        return [
            partner.id
            for partner in partners
            if not partner.user_ids & blocked
        ]

    def _linkup_start_rule_info(self):
        """What the web client reads of the start rule of the conversation:
        the effective mode, and whether a confirmed reflection opened it,
        for the current user in a group or a channel."""
        self.ensure_one()
        mode = self._linkup_start_rule()
        return {
            "linkup_start_rule": mode,
            "linkup_start_rule_satisfied": mode == "off"
            or self._linkup_start_rule_satisfied(self.env.user),
        }

    def _channel_basic_info(self):
        data = super()._channel_basic_info()
        data.update(self._linkup_start_rule_info())
        return data

    def _linkup_send_start_rule(self):
        """Send the start rule of the conversations to their members, once
        a link of the pair changes."""
        for channel in self.sudo():
            channel._bus_send_store(channel, channel._linkup_start_rule_info())

    def _get_allowed_message_post_params(self):
        """A restricted member chooses neither the type nor the subtype of
        a post: ``/mail/message/post`` then posts a ``comment``."""
        params = super()._get_allowed_message_post_params()
        if self.env.user._linkup_is_restricted_member():
            params = params - {"message_type", "subtype_xmlid"}
        return params

    @api.private
    def message_post(self, *, message_type="notification", **kwargs):
        """Post on the conversation, under the start rule.

        The method is not callable remotely: a client posts through
        ``/mail/message/post``, which filters its parameters. The comment of
        a restricted member without a subtype gets the one the web client
        sends, ``mail.mt_comment``. The message is created inside
        ``authorization.channel_post``, the only way a member creates the
        message of a conversation without ``sudo``.

        A suspension, and the block of a direct conversation, refuse the
        post first (``_linkup_check_reach``); a mention skips the people a
        block separates from the author.
        """
        self._linkup_check_reach(message_type)
        self._linkup_check_start_rule(message_type)
        if len(self) == 1 and (
            kwargs.get("partner_ids") or kwargs.get("special_mentions")
        ):
            kwargs = self._linkup_mentions(kwargs)
        if (
            message_type == "comment"
            and not kwargs.get("subtype_xmlid")
            and not kwargs.get("subtype_id")
            and self.env.user._linkup_is_restricted_member()
        ):
            kwargs["subtype_xmlid"] = "mail.mt_comment"
        with channel_post(self.ids):
            return super().message_post(message_type=message_type, **kwargs)

    def _linkup_mentions(self, kwargs):
        """The arguments of a post whose mentions skip the people a block
        separates from the author. ``@everyone`` is expanded here, to the
        members of the conversation, so that it skips them too."""
        kwargs = dict(kwargs)
        partner_ids = list(kwargs.get("partner_ids") or [])
        special = list(kwargs.get("special_mentions") or [])
        if "everyone" in special:
            special.remove("everyone")
            kwargs["special_mentions"] = special
            # sudo: discuss.channel.member - the members of the conversation
            partner_ids = list(
                set(partner_ids)
                | set(self.sudo().channel_member_ids.partner_id.ids)
            )
        kwargs["partner_ids"] = self._linkup_drop_blocked_partners(partner_ids)
        return kwargs

    @api.private
    def message_post_with_source(self, *args, **kwargs):
        """Not callable remotely either: it posts through ``message_post``
        with the message type its caller gives."""
        return super().message_post_with_source(*args, **kwargs)

    def set_message_pin(self, message_id, pinned):
        """Pin or unpin a message; the notification it posts is written by
        the server."""
        with server_notification():
            return super().set_message_pin(message_id, pinned)

    def add_members(self, *args, **kwargs):
        """Add members; the notification of their arrival is written by the
        server. ``discuss.channel.member.create`` checks who is added."""
        with server_notification():
            return super().add_members(*args, **kwargs)

    # ------------------------------------------------------------------
    # Creation of conversations (LU-F-063 RM2)
    # ------------------------------------------------------------------

    def _linkup_check_member_channel_type(self, vals_list):
        """Keep a restricted member from creating a channel.

        A channel (``channel_type = 'channel'``) has no start rule of its
        own and may be open to every internal user: a member who created
        one would talk there with anyone, past the start rule, and widen
        their scope to whoever joins. Only an administrator creates one. A
        thread of a channel (``parent_channel_id``) stays open to members:
        it follows the start rule of its parent. Neither the type nor the
        parent of a conversation changes once it exists. The check reads
        the real user, ``sudo`` included.
        """
        if not self.env.user._linkup_is_restricted_member():
            return
        for vals in vals_list:
            if vals.get("channel_type") == "channel" and not vals.get(
                "parent_channel_id"
            ):
                raise AccessError(
                    _("Only a LinkUp administrator creates a channel.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        self._linkup_check_member_channel_type(vals_list)
        return super().create(vals_list)

    @api.depends("channel_type")
    def _compute_group_public_id(self):
        """Keep a new channel to the LinkUp administrators (LU-F-063 RM2).

        ``mail`` opens every new channel without a group to all internal
        users, and so to every member, with its member list. A channel
        created without an authorized group gets the LinkUp
        administrators instead; an animation channel names its group
        explicitly, as ``channel_create`` does with the group it receives.
        """
        unset = self.filtered(
            lambda channel: channel.channel_type == "channel"
            and not channel.parent_channel_id
            and not channel.group_public_id
        )
        super()._compute_group_public_id()
        group = self.env.ref(ADMIN_GROUP, raise_if_not_found=False)
        if group:
            unset.group_public_id = group

    def write(self, vals):
        user = self.env.user
        if {"channel_type", "parent_channel_id"}.intersection(
            vals
        ) and user._linkup_is_restricted_member():
            raise AccessError(
                _(
                    "Only a LinkUp administrator changes the type of a"
                    " conversation."
                )
            )
        if (
            CHAT_TEXT_FIELDS.intersection(vals)
            and not self.env.su
            and user._linkup_is_restricted_member()
        ):
            self._linkup_check_text_change()
        return super().write(vals)

    def _linkup_check_text_change(self):
        """Refuse to a restricted member a new name, description or image
        of a conversation that the other people read.

        The server names a direct conversation: its two parties read the
        name and the description there, which would carry free text past
        the start rule and a block. Elsewhere, the start rule and a
        suspension apply as to a post.
        """
        if any(channel.channel_type == "chat" for channel in self):
            raise AccessError(
                _(
                    "The name and the description of a direct conversation"
                    " are not changed."
                )
            )
        self._linkup_check_reach("comment")
        self._linkup_check_start_rule("comment")

    # ------------------------------------------------------------------
    # Contact initiated by the server (LU-F-063 RM1)
    # ------------------------------------------------------------------

    # The decorators of ``mail`` are repeated: an override declared on a
    # class of its own does not inherit them, and without ``returns`` the
    # web client would receive the record instead of its Store data.
    @api.model
    @api.returns("self", lambda channels: Store(channels).get_result())
    def channel_get(self, partners_to, pin=True, force_open=False):
        """Open the direct conversation of the current user with a partner,
        within LinkUp's contact rule."""
        self._linkup_check_direct_contact(partners_to)
        return super().channel_get(partners_to, pin=pin, force_open=force_open)

    @api.model
    def _linkup_check_direct_contact(self, partner_ids):
        """Keep a restricted member from opening a direct conversation that
        no confirmed reflection opened.

        A member creates the direct conversation of a pair with an
        ``active`` link only, and so never with a member a block separates
        from them, nor with an archived account. Opening again a direct
        conversation the member already belongs to adds nobody and stays
        allowed. The server opens the others itself, to carry a
        reflection, inside ``authorization.linkup_post``. Every refusal is the same, whatever
        the reason, so that it tells nothing of a block. ``sudo`` calls are
        the server's own and are not checked here; the creation of the
        members still is (``discuss.channel.member``).
        """
        user = self.env.user
        if self.env.su or not user._linkup_is_restricted_member():
            return
        others = set(partner_ids or []) - {user.partner_id.id}
        post = current_post(self.env)
        if post:
            others -= post.partner_ids
        if not others:
            return
        refused = AccessError(
            _(
                "A LinkUp member opens a direct conversation only with a"
                " person of a confirmed reflection."
            )
        )
        if len(others) != 1:
            raise refused
        partner = (
            self.env["res.partner"]
            .sudo()
            .with_context(active_test=False)
            .browse(list(others))
            .exists()
        )
        if not partner:
            raise refused
        Link = self.env["linkup.link"]
        if any(
            Link._is_active_between(user, other)
            for other in partner.user_ids.filtered(
                lambda u: u.active and not u.share
            )
        ):
            return
        # sudo: discuss.channel.member - the chats the member belongs to
        if (
            self.sudo()
            .search(
                [
                    ("channel_type", "=", "chat"),
                    ("channel_member_ids.partner_id", "=", user.partner_id.id),
                    ("channel_member_ids.partner_id", "=", partner.id),
                ]
            )
            .filtered(lambda chat: len(chat.channel_member_ids) == 2)
        ):
            return
        raise refused

    @api.model
    def _linkup_restrict_general_channel(self):
        """Close the default "general" channel to members.

        ``mail`` subscribes every new internal user to that channel through
        its ``group_ids`` and opens it to ``base.group_user``. Emptying
        ``group_ids`` stops the automatic subscription, and restricting it to
        the system administrators hides it from members. A database where
        the channel no longer exists is left as is.
        """
        channel = self.env.ref(
            "mail.channel_all_employees", raise_if_not_found=False
        )
        if not channel:
            return
        channel.sudo().write(
            {
                "group_ids": [Command.clear()],
                "group_public_id": self.env.ref("base.group_system").id,
            }
        )

    def _check_can_update_message_content(self, message):
        """Refuse the edition of a carrier message, and any edition that the
        start rule forbids.

        ``/mail/message/update_content`` writes the new body under
        ``sudo`` once this check passes: the carrier of a reflection keeps
        the neutral sentence the server wrote, and a comment posted while
        the conversation was open (incentive mode, say) takes no new free
        text once a strict rule closes it.
        """
        # sudo: mail.message - the reverse field is kept to administrators
        if message.sudo().linkup_reflet_ids:
            raise UserError(
                _("The message of a reflection cannot be changed.")
            )
        self._linkup_check_reach("comment")
        self._linkup_check_start_rule("comment")
        return super()._check_can_update_message_content(message)

    def _message_update_content(
        self, message, body, attachment_ids=None, partner_ids=None, **kwargs
    ):
        """Edit a message; a mention added by the edition skips the people a
        block separates from the author, as a mention of a post does."""
        if partner_ids and len(self) == 1:
            partner_ids = self._linkup_drop_blocked_partners(partner_ids)
        return super()._message_update_content(
            message,
            body,
            attachment_ids=attachment_ids,
            partner_ids=partner_ids,
            **kwargs,
        )

    def _message_post_after_hook(self, message, msg_vals):
        """Link the carrier message to its reflection before the broadcast.

        ``mail.thread.message_post`` calls this hook right before
        ``_notify_thread``, which builds the ``discuss.channel/new_message``
        payload: linking here puts the card of the reflection in that
        payload. Only a post authorized by ``authorization.linkup_post`` is
        linked, on the conversation of the reflection, by its author, and
        while the reflection has no carrier yet.
        """
        post = current_post(self.env)
        if (
            post
            and len(self) == 1
            and message.author_id == self.env.user.partner_id
        ):
            reflet = self.env["linkup.reflet"].sudo().browse(post.reflet_id)
            if reflet.channel_id == self and not reflet.message_id:
                reflet.message_id = message
        self._linkup_extinguish_highlights(message, post)
        return super()._message_post_after_hook(message, msg_vals)

    def _linkup_chat_users(self):
        """The two internal users of a direct conversation, or an empty
        recordset for any other conversation."""
        self.ensure_one()
        if self.channel_type != "chat":
            return self.env["res.users"]
        # sudo: discuss.channel.member - the parties of the conversation
        users = (
            self.sudo()
            .channel_member_ids.partner_id.user_ids.filtered(
                lambda user: not user.share
            )
            .sudo(False)
        )
        return users if len(users) == 2 else self.env["res.users"]

    def _linkup_extinguish_highlights(self, message, post):
        """Put out the highlights of the pair after an exchange (LU-F-052).

        In a direct conversation, the carrier of a reflection puts out the
        highlights of both directions; a comment of a member puts out the
        one that member received from the other party.
        """
        if (
            len(self) != 1
            or self.channel_type != "chat"
            or message.message_type != "comment"
        ):
            return
        users = self._linkup_chat_users()
        if not users:
            return
        Highlight = self.env["linkup.highlight"]
        if post:
            Highlight._linkup_extinguish(users[0], users[1], "reflet")
        elif self.env.user in users:
            Highlight._linkup_extinguish(
                users[0], users[1], "message", recipient=self.env.user
            )

    def _notify_thread_by_web_push(
        self, message, recipients_data, msg_vals=False, **kwargs
    ):
        """Leave out of the web push of a reflection the members who turned
        its notification off (``linkup_notify_reflet_received``), and send
        those who chose discreet notifications (``linkup_notify_discreet``)
        a payload without any name, in their own language."""
        recipients_data = self._linkup_push_recipients(
            message, recipients_data
        )
        discreet = self._linkup_discreet_partners(message, recipients_data)
        super()._notify_thread_by_web_push(
            message,
            [
                data
                for data in recipients_data
                if data["id"] not in discreet.ids
            ],
            msg_vals=msg_vals,
            **kwargs,
        )
        by_lang = {}
        for partner in discreet:
            by_lang.setdefault(partner.lang, []).append(partner.id)
        for lang, partner_ids in by_lang.items():
            super(
                DiscussChannel,
                self.with_context(linkup_discreet_push=True, lang=lang),
            )._notify_thread_by_web_push(
                message,
                [
                    data
                    for data in recipients_data
                    if data["id"] in partner_ids
                ],
                msg_vals=msg_vals,
                **kwargs,
            )

    def _notify_by_web_push_prepare_payload(self, message, msg_vals=False):
        """A discreet payload names nobody: "LinkUp", "New LinkUp event",
        the icon of the instance, and the conversation to open."""
        payload = super()._notify_by_web_push_prepare_payload(
            message, msg_vals=msg_vals
        )
        if self.env.context.get("linkup_discreet_push"):
            payload["title"] = "LinkUp"
            payload["options"]["body"] = _("New LinkUp event")
            payload["options"][
                "icon"
            ] = "/web/static/img/odoo-icon-192x192.png"
        return payload

    def _linkup_settings_partners(self, message, recipients_data, domain):
        """The partners among ``recipients_data`` whose settings match
        ``domain``, when ``message`` carries a reflection; none otherwise."""
        if not message.sudo().linkup_reflet_ids:
            return self.env["res.partner"]
        partner_ids = [data["id"] for data in recipients_data]
        # sudo: res.users.settings - the notification settings of recipients
        return (
            self.env["res.users.settings"]
            .sudo()
            .search([("user_id.partner_id", "in", partner_ids), *domain])
            .user_id.partner_id
        )

    def _linkup_discreet_partners(self, message, recipients_data):
        """The recipients of the web push of a reflection who chose discreet
        notifications."""
        return self._linkup_settings_partners(
            message, recipients_data, [("linkup_notify_discreet", "=", True)]
        )

    def _linkup_push_recipients(self, message, recipients_data):
        """The recipients of the web push of ``message``, without the
        members whose settings turn off the notification of a received
        reflection. Any other message keeps all its recipients."""
        muted = self._linkup_settings_partners(
            message,
            recipients_data,
            [("linkup_notify_reflet_received", "=", False)],
        ).ids
        return [data for data in recipients_data if data["id"] not in muted]
