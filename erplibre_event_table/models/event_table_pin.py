# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventTablePin(models.Model):
    """A place reserved by hand, which the next generation works around.

    A pin is an INPUT to generation where event.table.assignment is its
    OUTPUT, and the two stay apart for two reasons. Every reader of
    assignment_ids — table sheets, participant cards, the mail template,
    the unseated count — treats a row as somebody seated, so a pin
    living there would be printed on a table sheet and mailed out as a
    real place. And action_choose replaces every assignment of a plan,
    while outliving a generation is exactly what a pin is for.
    """

    _name = "event.table.pin"
    _inherit = ["event.table.seat.claim"]
    _description = "Rotating Table Pin"
    _order = "plan_id, round_number, id"

    plan_id = fields.Many2one(
        "event.table.plan", required=True, ondelete="cascade", index=True
    )
    event_id = fields.Many2one(
        related="plan_id.event_id", store=True, index=True
    )
    round_number = fields.Integer(string="Round", required=True)
    table_id = fields.Many2one(
        "event.table", required=True, ondelete="cascade", index=True
    )
    participant_id = fields.Many2one(
        "event.table.participant",
        required=True,
        ondelete="cascade",
        index=True,
    )
    # A pin asks for a seat, it does not hold one: rotation/seats.py
    # derives every seat of a table from a single offset and knows no
    # imposed seat, so a generation can honour the TABLE and nothing
    # finer. The number is kept because it states the request, and a
    # later step is free to grant it after the fact.
    seat_number = fields.Integer(
        string="Requested Seat",
        help="0 when no seat is requested. A pin reserves the table; the"
        " seat number is a wish seating may not be able to grant.",
    )

    _sql_constraints = [
        (
            "participant_round_unique",
            "UNIQUE(plan_id, round_number, participant_id)",
            "A participant is pinned to one table per round.",
        ),
        (
            "round_number_positive",
            "CHECK(round_number >= 1)",
            "Rounds start at 1.",
        ),
    ]

    @api.constrains("seat_number", "table_id", "round_number")
    def _check_seat_unique(self):
        """Declare the seat rule over this model's own field names.

        The rule itself, and why it cannot be a SQL index, live in the
        event.table.seat.claim mixin.
        """
        self._check_seat_claim_unique()

    def _seat_claim_error(self):
        return _("A seat is requested once per table and round.")

    @api.model
    def _check_plans_accept_pins(self, plans):
        """Refuse to touch pins on a locked plan, and only there.

        Pins feed the NEXT generation and survive it, so every state
        that still accepts work accepts them, a plan already running on
        a chosen combination included: pinning someone there reserves
        their seat for the generation to come without disturbing the
        assignments standing now. The plan's own _check_not_locked says
        the same thing in a message about changing anything; this one
        names pins, which is what the caller was trying to do.
        """
        for plan in plans:
            if plan.state == "locked":
                raise UserError(
                    _("This plan is locked. Unlock it before pinning anyone.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        plans = self.env["event.table.plan"].browse(
            [vals["plan_id"] for vals in vals_list if vals.get("plan_id")]
        )
        self._check_plans_accept_pins(plans)
        return super().create(vals_list)

    def write(self, vals):
        plans = self.plan_id
        if vals.get("plan_id"):
            plans |= self.env["event.table.plan"].browse(vals["plan_id"])
        self._check_plans_accept_pins(plans)
        return super().write(vals)

    def unlink(self):
        self._check_plans_accept_pins(self.plan_id)
        return super().unlink()

    @api.model
    def _participant_key(self, participant):
        """Identify a participant across two copies of one plan.

        A contact is unique within a plan (event.table.participant's own
        partner_unique), so it identifies on its own. A guest has only a
        name and an address, a pair two guests of the same plan may
        share, which is why _plan_participant_map rejects a key it finds
        twice instead of picking one.
        """
        if participant.partner_id:
            return ("partner", participant.partner_id.id)
        return ("guest", participant.name, participant.email or "")

    @api.model
    def _plan_participant_map(self, source, target):
        """Map source participant ids to their twin in the target plan.

        A key held by more than one participant on either side maps
        nobody: the pair it would join is a guess, and a pin aimed at the
        wrong namesake is worse than a pin that is visibly missing.
        """
        source_keys = {}
        for participant in source.participant_ids:
            key = self._participant_key(participant)
            source_keys.setdefault(key, []).append(participant.id)
        target_keys = {}
        for participant in target.participant_ids:
            key = self._participant_key(participant)
            target_keys.setdefault(key, []).append(participant.id)
        return {
            ids[0]: target_keys[key][0]
            for key, ids in source_keys.items()
            if len(ids) == 1 and len(target_keys.get(key, ())) == 1
        }

    @api.model
    def _clone_plan_pins(self, source, target):
        """Re-aim a plan's pins onto the copy's own tables and people.

        plan.copy() clones tables and participants, so a pin copied as is
        would sit in the copy while pointing at the source's rows. A
        table maps by its number, unique within a plan; a participant
        maps through _plan_participant_map. A pin whose table or
        participant has no unambiguous twin is dropped and counted.
        Returns (carried, dropped).
        """
        tables = {table.number: table.id for table in target.table_ids}
        people = self._plan_participant_map(source, target)
        vals_list = []
        dropped = 0
        for pin in source.pin_ids:
            table_id = tables.get(pin.table_id.number)
            participant_id = people.get(pin.participant_id.id)
            if not table_id or not participant_id:
                dropped += 1
                continue
            vals_list.append(
                {
                    "plan_id": target.id,
                    "round_number": pin.round_number,
                    "table_id": table_id,
                    "participant_id": participant_id,
                    "seat_number": pin.seat_number,
                }
            )
        if vals_list:
            self.create(vals_list)
        return len(vals_list), dropped
