# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError

from ..exceptions import LinkupError

EXTINGUISHED_REASONS = [
    ("reflet", "Reflection sent"),
    ("message", "Message of the highlighted member"),
    ("call", "Call started"),
    ("manual", "Hidden by the highlighted member"),
    ("withdrawn", "Withdrawn by the sender"),
]


class LinkupHighlight(models.Model):
    """ "You add to my happiness": a member puts another one in the light.

    A highlight thanks without words and carries no points. It is created
    ``active`` by ``action_send``, which forces the sender to the current
    user; a pair holds at most one active highlight in each direction,
    enforced by a partial unique index. The next exchange between the two
    members puts it out (``_linkup_extinguish``): a reflection sent in the
    pair, a message posted by the highlighted member in their direct
    conversation, a call started in it. The highlighted member hides it
    (``action_dismiss``), the sender withdraws it (``action_withdraw``).

    Members read the highlights they sent or received, and write none:
    every change goes through a method that checks the acting user and
    writes under ``sudo``. Each change reaches both parties over the bus.

    A highlight sent to a member who blocks its sender is a ``phantom``:
    its sender reads it and sees it go out as any other, and its recipient
    never reads it nor hears of it, so that the sender does not learn of
    the block.
    """

    _name = "linkup.highlight"
    _description = "LinkUp highlight: you add to my happiness"
    _order = "create_date desc, id desc"

    sender_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    recipient_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    channel_id = fields.Many2one(
        "discuss.channel",
        string="Conversation",
        ondelete="set null",
        readonly=True,
        help="Direct conversation the highlight was sent from, if any.",
    )
    context = fields.Selection(
        [("thread", "Conversation"), ("drag", "Dragged onto a person")],
        required=True,
        default="thread",
        readonly=True,
    )
    active = fields.Boolean(default=True, readonly=True)
    # Never readable by the sender: a highlight to a member who blocks them
    # reaches nobody, and looks delivered to them.
    phantom = fields.Boolean(
        groups="base.group_system", readonly=True, copy=False
    )
    extinguished_date = fields.Datetime(readonly=True)
    extinguished_reason = fields.Selection(EXTINGUISHED_REASONS, readonly=True)

    _sql_constraints = [
        (
            "sender_not_recipient",
            "CHECK(sender_id != recipient_id)",
            "A member does not put themself in the light.",
        ),
    ]

    def init(self):
        """At most one active highlight per sender and recipient."""
        super().init()
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS linkup_highlight_one_active_idx
            ON linkup_highlight (sender_id, recipient_id) WHERE active
            """
        )

    @api.depends("sender_id", "recipient_id")
    def _compute_display_name(self):
        for highlight in self:
            highlight.display_name = " → ".join(
                highlight.sudo().mapped("sender_id.name")
                + highlight.sudo().mapped("recipient_id.name")
            )

    # ------------------------------------------------------------------
    # Store and bus
    # ------------------------------------------------------------------

    def _to_store(self, store: Store, /):
        """Add the highlights to a Store: the two partners, by name, the
        state and the date. The same values go to both parties."""
        for highlight in self.sudo():
            store.add(
                self._name,
                {
                    "id": highlight.id,
                    "sender": Store.one(
                        highlight.sender_id.partner_id,
                        fields=["name", "avatar_128"],
                    ),
                    "recipient": Store.one(
                        highlight.recipient_id.partner_id,
                        fields=["name", "avatar_128"],
                    ),
                    "active": highlight.active,
                    "create_date": highlight.create_date,
                    "channel_id": highlight.channel_id.id,
                },
            )

    def _linkup_notify(self, received=False):
        """Send the highlights to their two parties over the bus.

        With ``received``, the recipient gets them as
        ``linkup.highlight/received``, which its client announces; every
        other update is a plain Store insertion. The recipient of a phantom
        highlight gets nothing.
        """
        for highlight in self.sudo():
            highlight.sender_id.partner_id._bus_send_store(Store(highlight))
            if highlight.phantom:
                continue
            highlight.recipient_id.partner_id._bus_send_store(
                Store(highlight),
                notification_type=(
                    "linkup.highlight/received"
                    if received
                    else "mail.record/insert"
                ),
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @api.model
    def action_send(self, recipient_id, channel_id=None):
        """Put a member of the sender's scope in the light.

        The sender is the current user. ``channel_id``, when given, must be
        the direct conversation of the two members; the highlight then comes
        from that conversation, and otherwise from a person dropped onto.
        A highlight already active in this direction is left as it is and
        returned: a new press has no effect. In a ``blocked`` pair, the
        sender who blocked the recipient is refused; the sender whom the
        recipient blocked gets a phantom highlight, which they read as a
        delivered one and which never reaches the recipient. Once the block
        is lifted, a new press puts the phantom out and delivers a new one.
        A suspended member sends none. Return the id of the active
        highlight.
        """
        Reflet = self.env["linkup.reflet"]
        Reflet._linkup_check_member()
        sender = self.env.user
        sender._linkup_check_not_suspended()
        recipient = Reflet._linkup_get_recipient(recipient_id)
        channel = self.env["discuss.channel"]
        if channel_id:
            try:
                channel_ids = [int(channel_id)]
            except (TypeError, ValueError):
                channel_ids = []
            # sudo: discuss.channel.member - the parties of the conversation
            channel = (
                self.env["discuss.channel"]
                .sudo()
                .browse(channel_ids)
                .exists()
                .filtered(
                    lambda c: c.channel_type == "chat"
                    and c.channel_member_ids.partner_id
                    == (sender.partner_id | recipient.partner_id)
                )
            )
            if not channel:
                raise LinkupError(
                    "linkup.unavailable",
                    _("This highlight cannot be sent."),
                )
        reach = self.env["linkup.block"]._linkup_reach(sender, recipient)
        if reach == "blocker":
            raise LinkupError(
                "linkup.unavailable",
                _("This highlight cannot be sent."),
            )
        # The row of the sender serializes two presses at once: the second
        # waits for nothing, fails on the lock, and its retry finds the
        # highlight of the first.
        self.flush_model(["sender_id", "recipient_id", "active"])
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id = %s FOR NO KEY UPDATE NOWAIT",
            [sender.id],
        )
        current = self.sudo().search(
            [
                ("sender_id", "=", sender.id),
                ("recipient_id", "=", recipient.id),
            ],
            limit=1,
        )
        phantom = reach == "phantom"
        if current and current.phantom and not phantom:
            current._linkup_put_out("withdrawn")
            # The partial unique index checks the insertion below at once.
            current.flush_recordset(["active"])
        elif current:
            return current.id
        highlight = self.sudo().create(
            {
                "sender_id": sender.id,
                "recipient_id": recipient.id,
                "channel_id": channel.id,
                "context": "thread" if channel else "drag",
                "phantom": phantom,
            }
        )
        highlight._linkup_notify(received=True)
        return highlight.id

    def _linkup_put_out(self, reason):
        """Put the active highlights out with ``reason`` and tell both
        parties."""
        highlights = self.sudo().filtered("active")
        if not highlights:
            return
        highlights.write(
            {
                "active": False,
                "extinguished_date": fields.Datetime.now(),
                "extinguished_reason": reason,
            }
        )
        highlights._linkup_notify()

    def _linkup_own(self, field):
        """The highlight under ``sudo``, if ``field`` holds the current
        user; refused otherwise."""
        self.ensure_one()
        highlight = self.sudo().with_context(active_test=False)
        if highlight[field] != self.env.user:
            raise AccessError(
                _("This action belongs to another party of the highlight.")
            )
        return highlight

    def action_withdraw(self):
        """The sender withdraws the highlight; an inactive one is left."""
        self._linkup_own("sender_id")._linkup_put_out("withdrawn")
        return True

    def action_dismiss(self):
        """The highlighted member hides the highlight; the recipient of a
        phantom one is a stranger to it."""
        highlight = self._linkup_own("recipient_id")
        if highlight.phantom:
            raise AccessError(
                _("This action belongs to another party of the highlight.")
            )
        highlight._linkup_put_out("manual")
        return True

    @api.model
    def _linkup_extinguish(self, user1, user2, reason, recipient=None):
        """Put out the active highlights between two members.

        Without ``recipient``, both directions go out; with it, only the
        highlight that ``recipient`` received from the other member, as a
        message of the highlighted member does.
        """
        if not user1 or not user2 or user1 == user2:
            return
        pairs = (
            [(user2, user1), (user1, user2)]
            if recipient is None
            else [(user1 if recipient == user2 else user2, recipient)]
        )
        domain = []
        for sender, highlighted in pairs:
            domain = (["|"] if domain else []) + domain
            domain += [
                "&",
                ("sender_id", "=", sender.id),
                ("recipient_id", "=", highlighted.id),
            ]
        self.sudo().search(domain)._linkup_put_out(reason)

    @api.model
    def _linkup_store_for(self, user):
        """The active highlights ``user`` sent or received, for the Store
        of their web client; a phantom one counts for its sender only."""
        return self.sudo().search(
            [
                "|",
                ("sender_id", "=", user.id),
                "&",
                ("recipient_id", "=", user.id),
                ("phantom", "=", False),
            ]
        )
