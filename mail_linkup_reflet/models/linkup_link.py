# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class LinkupLink(models.Model):
    """The relation between two members, one record per unordered pair.

    The pair is stored ordered, ``user_a_id < user_b_id``, so that a single
    unique constraint covers both directions. A link is ``pending`` from the
    first reflection sent in the pair and ``active`` once one is confirmed;
    it never goes back from ``active``. A ``pending`` link whose last waiting
    reflection is rejected, withdrawn or expired becomes ``closed``: no
    reflection of the pair was ever confirmed, and the record rules stop
    opening the two members to each other. The next sending in the pair
    makes it ``pending`` again. A ``blocked`` link has a block in at least
    one direction (``linkup.block``); lifting the last one gives it back the
    state its reflections give it.

    ``turn_reflet_id`` points to the reflection that holds the current turn
    of the pair: the one whose recipient acts next. The reflection methods
    move it under a row lock of the link, so two concurrent answers cannot
    both take the same turn.
    """

    _name = "linkup.link"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp link between two members"
    _order = "last_interaction_date desc, id desc"

    user_a_id = fields.Many2one(
        "res.users", required=True, index=True, ondelete="cascade"
    )
    user_b_id = fields.Many2one(
        "res.users", required=True, index=True, ondelete="cascade"
    )
    # Kept to LinkUp administrators: ``blocked`` would tell a member that
    # the other party blocked them. The server reads it under ``sudo`` and
    # gives the clients a ``blocked`` link as ``closed``.
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("active", "Active"),
            ("closed", "Closed"),
            ("blocked", "Blocked"),
        ],
        required=True,
        default="pending",
        index=True,
        groups="mail_linkup_reflet.group_linkup_admin",
    )
    first_link_date = fields.Datetime(readonly=True)
    last_interaction_date = fields.Datetime(readonly=True)
    energy_a = fields.Integer(
        help="Points received by the first member in the events of the pair."
    )
    energy_b = fields.Integer(
        help="Points received by the second member in the events of the pair."
    )
    channel_id = fields.Many2one(
        "discuss.channel",
        string="Direct conversation",
        ondelete="set null",
    )
    virtual_round_count = fields.Integer()
    virtual_round_date = fields.Date()
    turn_reflet_id = fields.Many2one(
        "linkup.reflet",
        string="Current turn",
        ondelete="set null",
        readonly=True,
    )
    reflet_ids = fields.One2many("linkup.reflet", "link_id")

    _sql_constraints = [
        (
            "pair_unique",
            "UNIQUE(user_a_id, user_b_id)",
            "A pair of members has a single link.",
        ),
        (
            "pair_ordered",
            "CHECK(user_a_id < user_b_id)",
            "A link joins two distinct members, in increasing id order.",
        ),
    ]

    @api.depends("user_a_id", "user_b_id")
    def _compute_display_name(self):
        for link in self:
            names = link.sudo().mapped("user_a_id.name") + link.sudo().mapped(
                "user_b_id.name"
            )
            link.display_name = " ↔ ".join(names)

    @api.model_create_multi
    def create(self, vals_list):
        """Store each pair ordered, whatever order the caller gives."""
        for vals in vals_list:
            user_a, user_b = vals.get("user_a_id"), vals.get("user_b_id")
            if user_a and user_b and user_a > user_b:
                vals["user_a_id"], vals["user_b_id"] = user_b, user_a
        return super().create(vals_list)

    @api.model
    def _get_or_create(self, user1, user2):
        """Return the link of two users, creating it ``pending`` if needed.

        The insertion goes through ``ON CONFLICT DO NOTHING`` rather than the
        ORM: when two transactions create the same pair at once, the second
        one fails with a serialization error, which the RPC layer retries and
        which then finds the committed link, instead of an integrity error
        that it does not retry. The result is a ``sudo`` record.
        """
        user_a, user_b = sorted((user1.id, user2.id))
        if user_a == user_b:
            raise ValueError("A link joins two distinct users.")
        self.flush_model()
        self.env.cr.execute(
            """
            INSERT INTO linkup_link
                (user_a_id, user_b_id, state,
                 create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, 'pending',
                    %s, now() at time zone 'UTC',
                    %s, now() at time zone 'UTC')
            ON CONFLICT (user_a_id, user_b_id) DO NOTHING
            RETURNING id
            """,
            [user_a, user_b, self.env.uid, self.env.uid],
        )
        row = self.env.cr.fetchone()
        if row:
            return self.sudo().browse(row[0])
        return self.sudo().search(
            [("user_a_id", "=", user_a), ("user_b_id", "=", user_b)], limit=1
        )

    @api.model
    def _get_between(self, user1, user2):
        """The link of two users as a ``sudo`` record, or an empty one."""
        user_a, user_b = sorted((user1.id, user2.id))
        return self.sudo().search(
            [("user_a_id", "=", user_a), ("user_b_id", "=", user_b)], limit=1
        )

    @api.model
    def _is_active_between(self, user1, user2):
        """Tell whether a confirmed reflection links the two users."""
        return self._get_between(user1, user2).state == "active"

    def _linkup_other_user(self, user):
        """The member of the pair who is not ``user``."""
        self.ensure_one()
        return self.user_b_id if self.user_a_id == user else self.user_a_id

    def _linkup_lock(self):
        """Lock the row of the link for the rest of the transaction.

        ``NOWAIT`` makes a concurrent transaction fail at once with a lock
        error, which the RPC layer retries; the retry then reads the state
        written by the first one.
        """
        self.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM linkup_link WHERE id IN %s FOR UPDATE NOWAIT",
            [tuple(self.ids)],
        )
        self.invalidate_recordset()

    def _linkup_turn_user(self):
        """The member whose turn it is in the pair, or an empty recordset.

        It is the recipient of the reflection that holds the turn; a
        ``close`` ends the turn, and nobody has one until the next
        confirmed reflection.
        """
        self.ensure_one()
        reflet = self.sudo().turn_reflet_id
        if not reflet or reflet.kind == "close":
            return self.env["res.users"]
        return reflet.recipient_id

    def _linkup_touch(self):
        """Record an interaction in the pair, for the ordering of contacts."""
        self.sudo().write({"last_interaction_date": fields.Datetime.now()})

    def _linkup_reopen(self):
        """Make a ``closed`` link ``pending`` again, on a new sending.

        The caller holds the lock of the link.
        """
        self.sudo().filtered(lambda link: link.state == "closed").write(
            {"state": "pending"}
        )

    def _linkup_close_unanswered(self):
        """Close the ``pending`` links that no reflection waits on anymore.

        A link stays ``pending`` while one of its initial reflections is
        still ``sent``; otherwise its waiting reflections were all rejected,
        withdrawn or expired, or marked inaccurate, and the pair has no
        confirmed reflection. The caller holds the lock of the links, so a
        concurrent sending either commits first and is seen here, or fails
        on the lock and is retried against the ``closed`` link.
        """
        links = self.sudo().filtered(lambda link: link.state == "pending")
        if not links:
            return
        (links - links._linkup_waiting()).write({"state": "closed"})

    def _linkup_waiting(self):
        """The links among these that an initial reflection still waits on,
        a phantom one excepted: it reaches nobody."""
        return (
            self.env["linkup.reflet"]
            .sudo()
            .search(
                [
                    ("link_id", "in", self.ids),
                    ("kind", "=", "initial"),
                    ("state", "=", "sent"),
                    ("phantom", "=", False),
                ]
            )
            .link_id
        )

    def _linkup_after_unblock(self):
        """Give an unblocked link the state its reflections give it:
        ``active`` once a reflection of the pair was confirmed, ``pending``
        while an initial reflection waits, ``closed`` otherwise. The caller
        holds the lock of the link and has removed its last block."""
        for link in self.sudo().filtered(lambda link: link.state == "blocked"):
            if link.first_link_date:
                state = "active"
            elif link._linkup_waiting():
                state = "pending"
            else:
                state = "closed"
            link.write({"state": state})

    def _linkup_activate(self):
        """Mark the pair as linked, keeping the date of the first link.

        The direct conversation of the pair then receives its start rule
        again, which a confirmed reflection now satisfies.
        """
        now = fields.Datetime.now()
        for link in self.sudo():
            vals = {"state": "active", "last_interaction_date": now}
            if not link.first_link_date:
                vals["first_link_date"] = now
            if link.state != "blocked":
                link.write(vals)
        self.sudo().channel_id._linkup_send_start_rule()
