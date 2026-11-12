# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .res_users import ADMIN_GROUP


class DiscussChannel(models.Model):
    """The access of a plain member to a channel (LU-F-112 RM1).

    By default a channel is "on invitation only": a plain member reads it
    once they belong to it (``security/linkup_rules.xml``), and enters it
    when a LinkUp administrator or a linked member of it adds them, or
    through its invitation link (``discuss.channel.member``).

    ``linkup_published`` opens a channel to every plain member: its name,
    its description and its members read as Discuss shows an open channel,
    and any member joins it alone. Unpublishing it keeps its members, and
    a newcomer needs an invitation again. A LinkUp administrator, a system
    administrator or the creator of the channel sets it: Odoo 18 gives a
    channel no administrator among its members. The check reads the real
    user, ``sudo`` included.
    """

    _inherit = "discuss.channel"

    linkup_published = fields.Boolean(
        string="Published to the LinkUp members",
        default=False,
        copy=False,
        help="Every LinkUp member sees the channel, its description and its"
        " members, and joins it alone. Otherwise a member enters it on"
        " invitation only: added by a linked member of it, or through its"
        " invitation link.",
    )
    linkup_can_publish = fields.Boolean(
        string="May publish the channel",
        compute="_compute_linkup_can_publish",
        help="Whether the current user may publish or unpublish the"
        " channel.",
    )

    @api.depends_context("uid")
    def _compute_linkup_can_publish(self):
        for channel in self:
            channel.linkup_can_publish = channel._linkup_can_publish()

    def _linkup_can_publish(self):
        """Whether the real user may publish or unpublish the channel: a
        LinkUp administrator, a system administrator, or the creator of a
        channel, a thread of a channel following its channel."""
        self.ensure_one()
        user = self.env.user
        if user._is_superuser() or user.has_group("base.group_system"):
            return True
        if user._linkup_has_group_id(ADMIN_GROUP):
            return True
        channel = self.sudo()
        return (
            channel.channel_type == "channel"
            and not channel.parent_channel_id
            and channel.create_uid == user
        )

    def write(self, vals):
        if "linkup_published" in vals:
            refused = self.filtered(
                lambda channel: not channel._linkup_can_publish()
            )
            if refused:
                raise AccessError(
                    _(
                        "Only a LinkUp administrator or the creator of a"
                        " channel publishes it."
                    )
                )
        return super().write(vals)
