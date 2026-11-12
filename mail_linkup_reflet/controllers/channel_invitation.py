# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import http
from odoo.addons.mail.controllers.discuss.public_page import (
    PublicPageController,
)
from odoo.http import request
from odoo.tools import consteq

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
    """

    @http.route()
    def discuss_channel_invitation(self, channel_id, invitation_token):
        user = request.env.user
        if not user._is_public() and user._linkup_is_plain_member():
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
