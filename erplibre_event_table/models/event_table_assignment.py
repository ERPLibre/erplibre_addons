# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class EventTableAssignment(models.Model):
    _name = "event.table.assignment"
    _inherit = ["event.table.seat.claim"]
    _description = "Rotating Table Assignment"
    _order = "plan_id, round_number, table_number, seat_number, id"

    plan_id = fields.Many2one(
        "event.table.plan", required=True, ondelete="cascade", index=True
    )
    event_id = fields.Many2one(
        related="plan_id.event_id", store=True, index=True
    )
    combination_id = fields.Many2one(
        "event.table.combination",
        required=True,
        ondelete="cascade",
        index=True,
    )
    round_number = fields.Integer(string="Round", required=True)
    table_id = fields.Many2one(
        "event.table", required=True, ondelete="cascade", index=True
    )
    table_number = fields.Integer(related="table_id.number", store=True)
    participant_id = fields.Many2one(
        "event.table.participant",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        related="participant_id.partner_id", store=True, index=True
    )
    seat_number = fields.Integer(
        string="Seat", help="0 when seats are not assigned."
    )

    _sql_constraints = [
        (
            "participant_round_unique",
            "UNIQUE(plan_id, round_number, participant_id)",
            "A participant sits once per round.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("event_table_assignment_write"):
            raise UserError(
                _("Assignments change only through the floor plan.")
            )
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get("event_table_assignment_write"):
            raise UserError(
                _("Assignments change only through the floor plan.")
            )
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get("event_table_assignment_write"):
            raise UserError(
                _("Assignments change only through the floor plan.")
            )
        return super().unlink()

    @api.constrains("seat_number", "table_id", "round_number")
    def _check_seat_unique(self):
        """Declare the seat rule over this model's own field names.

        The rule itself, and why it cannot be a SQL index, live in the
        event.table.seat.claim mixin; only the field list a constraint
        watches has to be written where the fields exist.
        """
        self._check_seat_claim_unique()

    def _seat_claim_error(self):
        return _("A seat holds one participant per round.")

    @api.constrains("table_id", "round_number", "participant_id")
    def _check_table_capacity(self):
        """A table never holds more people than it has seats.

        Odoo validates Python constraints at the end of EVERY write, so the
        middle state of a swap towards a full table would trip this check.
        It stands down under the write flag, and the plan replays it once,
        explicitly, at the end of the move.
        """
        if self.env.context.get("event_table_assignment_write"):
            return
        for assignment in self:
            occupancy = self.search_count(
                [
                    ("plan_id", "=", assignment.plan_id.id),
                    ("round_number", "=", assignment.round_number),
                    ("table_id", "=", assignment.table_id.id),
                ]
            )
            if occupancy > assignment.table_id.seat_count:
                raise ValidationError(
                    _(
                        "Table %(table)s holds %(seats)s people at most.",
                        table=assignment.table_id.number,
                        seats=assignment.table_id.seat_count,
                    )
                )
