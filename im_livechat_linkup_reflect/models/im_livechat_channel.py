# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from contextlib import contextmanager

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.addons.mail_linkup_reflet.models.discuss_channel import (
    START_RULE_MODES,
)

from ..authorization import distress_opening, distress_operators

MODERATOR_GROUP = "mail_linkup_reflet.group_linkup_moderator"
LINKUP_KINDS = [
    ("welcome", "LinkUp welcome"),
    ("distress", "Distress"),
]


class ImLivechatChannel(models.Model):
    """The live chat channels of LinkUp (§9.11).

    ``linkup_kind`` marks the two channels of the data: ``welcome``, whose
    operators are the members who volunteer, in ``user_ids``, and whose
    rule carries the welcome script; ``distress``, which has no rule, and
    whose operators are the LinkUp moderators, whatever ``user_ids`` holds.

    The distress channel has an operator only inside
    ``authorization.distress_opening``, which the server opens with the
    moderators who are in no conflict of interest with the report
    (LU-F-116 RM5): ``available_operator_ids``, that ``_get_operator``
    reads first, is empty otherwise, so ``/im_livechat/get_session`` and
    ``/im_livechat/init`` never open nor offer it, and a
    ``previous_operator_id`` that names an excluded moderator matches
    nobody.
    """

    _inherit = "im_livechat.channel"

    linkup_kind = fields.Selection(
        LINKUP_KINDS,
        string="LinkUp role",
        copy=False,
        index="btree_not_null",
        help="The welcome of the visitors, or the conversations of"
        " distress with the moderation.",
    )
    linkup_start_rule = fields.Selection(
        [("inherit", "Global rule")] + START_RULE_MODES,
        string="LinkUp start rule",
        default="inherit",
        required=True,
        help="Start rule of the conversations of this channel; a"
        " conversation of the distress channel has none.",
    )

    @api.depends("user_ids.im_status")
    def _compute_available_operator_ids(self):
        super()._compute_available_operator_ids()
        distress = self.filtered(lambda c: c.linkup_kind == "distress")
        if not distress:
            return
        allowed = distress_operators()
        moderators = self.env["res.users"]
        if allowed:
            moderators = (
                self._linkup_moderators()
                .filtered(lambda user: user.id in allowed)
                .filtered(lambda user: user._is_user_available())
            )
        for channel in distress:
            channel.available_operator_ids = moderators

    @api.model
    def _linkup_get(self, kind):
        """The channel of ``kind``, under ``sudo``, or an empty
        recordset."""
        return self.sudo().search([("linkup_kind", "=", kind)], limit=1)

    @api.model
    def _linkup_moderators(self):
        """The LinkUp moderators who may be operators: active internal
        users of the moderator group, the superuser excepted."""
        group = self.env.ref(MODERATOR_GROUP)
        return group.sudo().users.filtered(
            lambda user: user.active
            and not user.share
            and user.id != SUPERUSER_ID
        )

    @contextmanager
    def _linkup_distress_scope(self, report):
        """Open the distress channel to the moderators who may process
        ``report`` for the duration of the block.

        The available operators are computed fields kept in the cache: they
        are dropped on entering and on leaving, so that no value computed
        inside reaches a reading outside, nor the reverse.
        """
        allowed = self.env["linkup.report"]._linkup_moderators_for(report)
        self.invalidate_recordset(["available_operator_ids"])
        try:
            with distress_opening(allowed.ids):
                yield
        finally:
            self.invalidate_recordset(["available_operator_ids"])

    @api.model
    def _linkup_distress_operator(self, report, lang=None, country_id=None):
        """An available moderator in no conflict of interest with
        ``report``, chosen by ``_get_operator``, or ``False``."""
        channel = self._linkup_get("distress")
        if not channel:
            return False
        with channel._linkup_distress_scope(report):
            return channel._get_operator(lang=lang, country_id=country_id)

    @api.model
    def _linkup_open_distress(self, report, user, previous_operator_id=None):
        """Open a conversation of the distress channel between the member
        ``user`` and a moderator (LU-F-126 RM1, RM2).

        The values are those of ``_get_livechat_discuss_channel_vals``,
        computed inside the distress scope of ``report``; the conversation
        takes no start rule (RM4). It is created by the server
        (``discuss.channel._linkup_server_create``), and its two parties
        receive it. Return the conversation, or an empty recordset
        when no moderator is available (RM3).
        """
        Channel = self.env["discuss.channel"]
        channel = self._linkup_get("distress")
        user = user.sudo()
        if not channel:
            return Channel
        try:
            previous_operator_id = int(previous_operator_id or 0) or None
        except (TypeError, ValueError):
            previous_operator_id = None
        with channel._linkup_distress_scope(report):
            vals = channel.with_context(
                lang=False
            )._get_livechat_discuss_channel_vals(
                user.partner_id.name,
                previous_operator_id=previous_operator_id,
                user_id=user.id,
                country_id=user.country_id.id,
                lang=user.lang,
            )
        if not vals:
            return Channel
        vals["linkup_start_rule"] = "off"
        conversation = Channel.with_context(
            lang=user.lang
        )._linkup_server_create(vals)
        conversation._linkup_post_distress_notice(user.lang)
        conversation.channel_member_ids.filtered(
            lambda member: member.partner_id == user.partner_id
        ).fold_state = "open"
        conversation._broadcast(
            [conversation.livechat_operator_id.id, user.partner_id.id]
        )
        return conversation

    def _linkup_conversation_name(self, visitor_name, operator):
        """The name of a conversation, as ``im_livechat`` gives it."""
        return " ".join(
            [
                visitor_name or _("Visitor"),
                operator.livechat_username or operator.name,
            ]
        )
