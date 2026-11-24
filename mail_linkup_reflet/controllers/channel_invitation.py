# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import http
from odoo.addons.mail.controllers.discuss.public_page import (
    PublicPageController,
)
from odoo.addons.mail.models.discuss.mail_guest import add_guest_to_context
from odoo.http import request
from odoo.tools import consteq
from werkzeug.exceptions import NotFound

from ..channel_access import channel_invitation


class LinkupPublicPageController(PublicPageController):
    """The invitation link of a channel, ``/chat/<id>/<token>``, lets a
    plain member in (LU-F-112 RM1).

    A plain member reads a channel only once they belong to it: the page of
    ``mail`` reads the channel as the user before adding them, so the
    member joins first, inside ``channel_access.channel_invitation``, once
    the token of that channel is checked and its group admits them. A wrong
    or missing token, another channel or a group that refuses the user
    joins nobody, and the page of ``mail`` answers as it does for them.

    The link of a group or of a direct conversation lets no plain member
    in, since a plain member enters a group only when a linked member of it
    adds them (LU-F-063 RM1), and no outsider either while a plain member
    belongs to it: ``mail`` would add an anonymous visitor as a guest, and
    a portal user as themself, which no authorized group refuses there.
    Whoever already belongs to it opens it as ``mail`` shows it. Any token
    gets the same answer as a missing channel. A conversation without a
    plain member, a meeting of LinkUp administrators included, keeps the
    behaviour of ``mail``; ``discuss.channel.member`` keeps the outsiders
    and the plain members apart on every other path.
    """

    @http.route()
    @add_guest_to_context
    def discuss_channel_invitation(self, channel_id, invitation_token):
        user = request.env.user
        outsider = not user._is_internal()
        if outsider or user._linkup_is_plain_member():
            # sudo: discuss.channel - the type, the members and the
            # membership of the user only, the same answer for every token
            channel = (
                request.env["discuss.channel"]
                .sudo()
                .browse(channel_id)
                .exists()
            )
            if (
                channel.channel_type in ("group", "chat")
                and not channel.is_member
                and (not outsider or channel._linkup_holds_plain_members())
            ):
                raise NotFound()
        if user._linkup_is_plain_member():
            # sudo: discuss.channel - the token of the channel is checked
            # before anything of it is used
            channel = (
                request.env["discuss.channel"]
                .sudo()
                .browse(channel_id)
                .exists()
            )
            group = (
                channel.group_public_id
                or channel.parent_channel_id.group_public_id
            )
            if (
                channel.channel_type == "channel"
                and channel.uuid
                and consteq(channel.uuid, invitation_token or "")
                and (not group or group in user.groups_id)
            ):
                with channel_invitation(channel.id):
                    channel.add_members(partner_ids=user.partner_id.ids)
        return super().discuss_channel_invitation(channel_id, invitation_token)
