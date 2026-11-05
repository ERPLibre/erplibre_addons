# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models

from ..exceptions import LinkupError
from .res_users import MEMBER_GROUP


class LinkupBlock(models.Model):
    """A member blocks another one (LU-F-115).

    One record per blocker and blocked member. While a block exists in
    either direction, the link of the pair is ``blocked``: the record rules
    close the two members to each other, no reflection action, message,
    reaction or call goes through in the pair, and a mention or a call
    invitation in a shared conversation skips the other party.

    The blocked member is never told: a reflection or a highlight they send
    to the blocker looks delivered and reaches nobody (phantom delivery), a
    post in their direct conversation is refused as for a deleted account
    (``linkup.unavailable``), and every refusal elsewhere reads the same as
    for a person outside their scope.

    Members read their own blocks and write none: ``action_block`` and
    ``action_unblock`` force the blocker to the current user and write under
    ``sudo``.
    """

    _name = "linkup.block"
    _description = "LinkUp block between two members"
    _order = "create_date desc, id desc"

    blocker_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    blocked_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )

    _sql_constraints = [
        (
            "pair_unique",
            "UNIQUE(blocker_id, blocked_id)",
            "A member blocks another member once.",
        ),
        (
            "not_self",
            "CHECK(blocker_id != blocked_id)",
            "A member does not block themself.",
        ),
    ]

    @api.depends("blocker_id", "blocked_id")
    def _compute_display_name(self):
        for block in self:
            block.display_name = " ⊘ ".join(
                block.sudo().mapped("blocker_id.name")
                + block.sudo().mapped("blocked_id.name")
            )

    # ------------------------------------------------------------------
    # Server helpers
    # ------------------------------------------------------------------

    @api.model
    def _linkup_reach(self, sender, recipient):
        """How a sending of ``sender`` reaches ``recipient``.

        ``open`` when no block separates them; ``blocker`` when the sender
        blocked the recipient, who then refuses the sending openly;
        ``phantom`` when only the recipient blocked the sender, so that the
        sending looks delivered and reaches nobody. The link of the pair
        decides whether the pair is blocked, the records which side.
        """
        link = self.env["linkup.link"]._get_between(sender, recipient)
        if link.state != "blocked":
            return "open"
        if self.sudo().search_count(
            [("blocker_id", "=", sender.id), ("blocked_id", "=", recipient.id)]
        ):
            return "blocker"
        return "phantom"

    @api.model
    def _linkup_blocked_users(self, users):
        """The users a block separates from one of ``users``, in either
        direction."""
        if not users:
            return self.env["res.users"]
        blocks = self.sudo().search(
            [
                "|",
                ("blocker_id", "in", users.ids),
                ("blocked_id", "in", users.ids),
            ]
        )
        return (blocks.blocker_id | blocks.blocked_id) - users

    @api.model
    def _linkup_has_blocked(self, blocker, blocked):
        """Tell whether ``blocker`` blocked ``blocked``."""
        return bool(
            self.sudo().search_count(
                [
                    ("blocker_id", "=", blocker.id),
                    ("blocked_id", "=", blocked.id),
                ]
            )
        )

    @api.model
    def _linkup_target(self, user_id=None, partner_id=None):
        """The member the current user blocks or unblocks, by user or by
        partner id.

        The target is a LinkUp member other than the current user, whom
        the current user reads, or shares a link with in any state, or
        already blocks. Any other id, existing or not, gets the same
        refusal. Return the user under ``sudo``.
        """
        me = self.env.user
        unavailable = LinkupError(
            "linkup.unavailable", _("This member cannot be blocked.")
        )
        try:
            user_id = int(user_id) if user_id else False
            partner_id = int(partner_id) if partner_id else False
        except (TypeError, ValueError):
            raise unavailable from None
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        if user_id:
            users = Users.browse(user_id).exists()
        elif partner_id:
            users = (
                self.env["res.partner"]
                .sudo()
                .with_context(active_test=False)
                .browse(partner_id)
                .exists()
                .user_ids
            )
        else:
            users = Users
        target = users.filtered(
            lambda user: user != me
            and not user.share
            and user._linkup_has_group_id(MEMBER_GROUP)
        )[:1]
        if not target:
            raise unavailable
        if not (
            self.env["res.users"].search_count([("id", "=", target.id)])
            or self.env["linkup.link"]._get_between(me, target)
            or self._linkup_has_blocked(me, target)
        ):
            raise unavailable
        return target

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @api.model
    def action_block(self, user_id=None, partner_id=None):
        """Block a member, given by user or by partner id.

        The link of the pair becomes ``blocked``, created when missing. The
        highlights of the pair go out: the one the blocker sent is
        withdrawn, the one they received is hidden, as each of them could
        do by hand. The direct conversation of the pair is unpinned for the
        blocker only: it is hidden, not deleted, and the blocked member
        keeps theirs as it was. Blocking again changes nothing.
        """
        self.env["linkup.reflet"]._linkup_check_member()
        me = self.env.user
        target = self._linkup_target(user_id, partner_id)
        link = self.env["linkup.link"]._get_or_create(me, target)
        link._linkup_lock()
        if not self._linkup_has_blocked(me, target):
            self.sudo().create({"blocker_id": me.id, "blocked_id": target.id})
        link.sudo().write({"state": "blocked"})
        Highlight = self.env["linkup.highlight"]
        Highlight._linkup_extinguish(me, target, "withdrawn", recipient=target)
        Highlight._linkup_extinguish(me, target, "manual", recipient=me)
        for chat in self.env["discuss.channel"]._linkup_pair_chats(me, target):
            chat.with_user(me).channel_pin(pinned=False)
        return True

    @api.model
    def action_unblock(self, user_id=None, partner_id=None):
        """Lift the block of the current user on a member.

        Once no block is left in the pair, its link takes back the state
        its reflections give it (``linkup.link._linkup_after_unblock``).
        The conversation of the pair stays hidden until it is opened.
        """
        self.env["linkup.reflet"]._linkup_check_member()
        me = self.env.user
        target = self._linkup_target(user_id, partner_id)
        blocks = self.sudo().search(
            [("blocker_id", "=", me.id), ("blocked_id", "=", target.id)]
        )
        if not blocks:
            return True
        link = self.env["linkup.link"]._get_between(me, target)
        if link:
            link._linkup_lock()
        blocks.unlink()
        if link and not self._linkup_has_blocked(target, me):
            link._linkup_after_unblock()
        return True

    @api.model
    def linkup_blocked_members(self):
        """The members the current user blocks, for their settings: one
        entry per block with ``user_id``, ``partner_id`` and ``name``, the
        most recent first."""
        self.env["linkup.reflet"]._linkup_check_member()
        blocks = self.search([("blocker_id", "=", self.env.uid)])
        return [
            {
                "id": block.id,
                "user_id": block.sudo().blocked_id.id,
                "partner_id": block.sudo().blocked_id.partner_id.id,
                "name": block.sudo().blocked_id.partner_id.name
                or block.sudo().blocked_id.name,
            }
            for block in blocks
        ]
