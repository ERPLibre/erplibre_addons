# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.osv import expression

from ..authorization import current_post
from ..channel_access import invited_by_link
from ..exceptions import LinkupError


class DiscussChannelMember(models.Model):
    _inherit = "discuss.channel.member"

    @api.model_create_multi
    def create(self, vals_list):
        self._linkup_check_self_join(vals_list)
        self._linkup_check_partners_in_scope(vals_list)
        return super().create(vals_list)

    @api.model
    def _linkup_check_self_join(self, vals_list):
        """Keep a member from joining a channel by themself (LU-F-112 RM1).

        A member who is not a LinkUp administrator reads a channel
        (``channel_type = 'channel'``) only once they belong to it
        (``security/linkup_rules.xml``): joining it by themself would open
        them its member list, whoever its authorized group. They enter it
        when a LinkUp administrator adds them, or a member of it with whom
        they share an ``active`` link (``_linkup_check_partners_linked``),
        or through its invitation link (``/chat/<id>/<token>``), which the
        controller of LinkUp marks once the token of that channel is
        checked (``channel_access.channel_invitation``). A published
        channel (``linkup_published``) takes any member who joins it alone.
        A thread of a channel stays open to the members of that channel.
        The check reads the real user, ``sudo`` included: the invitation
        link joins the user under ``sudo``.
        """
        user = self.env.user
        if not user._linkup_is_plain_member():
            return
        own = user.partner_id.id
        channel_ids = {
            vals["channel_id"]
            for vals in vals_list
            if vals.get("partner_id") == own and vals.get("channel_id")
        }
        # sudo: discuss.channel - the type and the parent of the targets
        for channel in (
            self.env["discuss.channel"].sudo().browse(list(channel_ids))
        ):
            if channel.channel_type != "channel":
                continue
            if channel.linkup_published or invited_by_link(channel.id):
                continue
            parent = channel.parent_channel_id
            if parent and own in parent.channel_member_ids.partner_id.ids:
                continue
            raise AccessError(
                _(
                    "A LinkUp member enters a channel when a LinkUp"
                    " administrator or a linked member adds them, or"
                    " through its invitation link."
                )
            )

    @api.model
    def _linkup_check_partners_in_scope(self, vals_list):
        """Refuse to a restricted member to add a partner outside their scope.

        Sharing a channel puts two partners in the reading scope of each other
        (``security/linkup_rules.xml``): without this check, a member widens
        their scope to any partner id by inviting it into a channel, a group
        or a chat. ``add_members``, ``create_group``, ``channel_get`` and the
        creation of a channel all go through here, the last ones under
        ``sudo``; the check therefore reads the scope as the real user,
        without superuser rights. The member's own partner is always allowed.

        The single exception is the contact the server opens itself: inside
        ``authorization.linkup_post``, the author of the reflection being
        posted may add the partners of its two parties, and no other. A
        suspended member adds nobody.
        """
        user = self.env.user
        if not user._linkup_is_restricted_member():
            return
        partner_ids = {
            vals["partner_id"] for vals in vals_list if vals.get("partner_id")
        } - {user.partner_id.id}
        post = current_post(self.env)
        if post:
            partner_ids -= post.partner_ids
        if not partner_ids:
            return
        user._linkup_check_not_suspended()
        # The active test stays on: an archived partner, and the users of
        # an archived account in the paths of the scope, are out of it.
        visible = (
            self.env["res.partner"]
            .with_user(user)
            .with_context(active_test=True)
            .search([("id", "in", list(partner_ids))])
        )
        if set(visible.ids) != partner_ids:
            raise AccessError(
                _(
                    "A LinkUp member can only add to a conversation the people"
                    " they already share one with."
                )
            )
        self._linkup_check_partners_linked(vals_list, partner_ids)

    @api.model
    def _linkup_check_partners_linked(self, vals_list, partner_ids):
        """Refuse to a restricted member to bring someone into a
        conversation past the start rule (LU-F-063 RM1).

        A group or a channel has no start rule by default: a member who
        could put there anyone of their scope would hold with them the free
        exchange that their direct conversation keeps closed. A member adds
        to a group or a channel only the people they have an ``active`` link
        with; a ``blocked`` link is never ``active``. A direct conversation
        is opened by its own member only: it holds them, either already or
        in the same creation. The link of an archived account, banned or
        deleted, opens nothing.
        """
        user = self.env.user
        Link = self.env["linkup.link"].sudo()
        by_channel = {}
        for vals in vals_list:
            if vals.get("channel_id"):
                by_channel.setdefault(vals["channel_id"], set()).add(
                    vals.get("partner_id")
                )
        # sudo: discuss.channel - the type and the members of the targets
        channels = self.env["discuss.channel"].sudo().browse(list(by_channel))
        for channel in channels:
            added = by_channel[channel.id]
            others = added & partner_ids
            if not others:
                continue
            if channel.channel_type == "chat":
                if user.partner_id.id not in (
                    added | set(channel.channel_member_ids.partner_id.ids)
                ):
                    raise AccessError(
                        _(
                            "A LinkUp member only opens a direct conversation"
                            " they belong to."
                        )
                    )
                continue
            partners = (
                self.env["res.partner"]
                .sudo()
                .with_context(active_test=False)
                .browse(list(others))
            )
            if not all(
                any(
                    Link._is_active_between(user, other)
                    for other in partner.user_ids.filtered("active")
                )
                for partner in partners
            ):
                raise AccessError(
                    _(
                        "A LinkUp member adds to a group only the people they"
                        " have confirmed a reflection with."
                    )
                )

    def _rtc_join_call(self, *args, **kwargs):
        """Refuse a call that the start rule forbids (LU-F-063 RM3).

        In a ``strict`` conversation that no confirmed reflection opened
        yet, a restricted member neither starts nor joins a call: the call
        would carry the free exchange the rule keeps closed. A call started
        or joined in a direct conversation puts out the highlights of the
        pair (LU-F-052), whether the other party answers or not; its
        answer is reported, and ends the turn when the call opens from the
        three options (``linkup.reflet._linkup_call_answered``).
        A suspended member calls nobody, and the direct conversation of a
        ``blocked`` pair holds no call (``_linkup_check_reach``).
        """
        for member in self:
            member.channel_id._linkup_check_reach("call")
            if member.channel_id._linkup_start_rule_blocks(self.env.user):
                raise LinkupError(
                    "linkup.start_rule",
                    _(
                        "A call opens once a reflection is confirmed in this"
                        " conversation."
                    ),
                )
        res = super()._rtc_join_call(*args, **kwargs)
        for member in self:
            users = member.channel_id._linkup_chat_users()
            if users:
                self.env["linkup.highlight"]._linkup_extinguish(
                    users[0], users[1], "call"
                )
                self.env["linkup.reflet"]._linkup_call_answered(
                    member.channel_id, member
                )
        return res

    def _notify_typing(self, is_typing):
        """Tell the conversation that the member types, except in the direct
        conversation of a ``blocked`` pair, where nobody posts."""
        members = self.filtered(
            lambda member: not member.channel_id._linkup_pair_blocked()
        )
        return super(DiscussChannelMember, members)._notify_typing(is_typing)

    def _get_rtc_invite_members_domain(self, member_ids=None):
        """Leave out of the invitations to a call the people a block
        separates from the member who calls (LU-F-115 RM1): in a shared
        group, a call never rings for them."""
        domain = super()._get_rtc_invite_members_domain(member_ids=member_ids)
        users = self.sudo().partner_id.with_context(active_test=False).user_ids
        blocked = self.env["linkup.block"]._linkup_blocked_users(users)
        if blocked:
            domain = expression.AND(
                [domain, [("partner_id", "not in", blocked.partner_id.ids)]]
            )
        return domain
