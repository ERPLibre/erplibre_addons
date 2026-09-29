# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventTableConfigureWizard(models.TransientModel):
    _name = "event.table.configure.wizard"
    _description = "Configure Rotating Tables"

    plan_id = fields.Many2one(
        "event.table.plan", required=True, ondelete="cascade"
    )
    mode = fields.Selection(
        [
            ("replace", "Replace the tables"),
            ("append", "Add tables after the last one"),
        ],
        compute="_compute_mode",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    seats_per_table = fields.Integer(
        string="Seats per Table", default=8, required=True
    )
    table_count = fields.Integer(
        string="Number of Tables",
        compute="_compute_table_count",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    existing_table_count = fields.Integer(related="plan_id.table_count")
    participant_count = fields.Integer(related="plan_id.participant_count")
    seat_balance = fields.Integer(related="plan_id.seat_balance")
    # One fully-formed sentence per case rather than a count field sitting
    # between two view text nodes: the view used to read "The <count>
    # existing tables will be deleted.", wrong at count == 1 in both
    # languages, and the two surrounding fragments extracted as unrelated
    # msgid, out of the glossary's reach.
    existing_table_warning = fields.Char(
        compute="_compute_existing_table_warning"
    )

    @api.depends("plan_id")
    def _compute_mode(self):
        for wizard in self:
            wizard.mode = "append" if wizard.plan_id.table_ids else "replace"

    @api.depends("existing_table_count")
    def _compute_existing_table_warning(self):
        for wizard in self:
            if wizard.existing_table_count == 1:
                wizard.existing_table_warning = _(
                    "The existing table will be deleted."
                )
            elif wizard.existing_table_count > 1:
                wizard.existing_table_warning = _(
                    "The %(count)s existing tables will be deleted.",
                    count=wizard.existing_table_count,
                )
            else:
                wizard.existing_table_warning = False

    @api.depends(
        "plan_id",
        "plan_id.participant_count",
        "plan_id.seat_count",
        "mode",
        "seats_per_table",
    )
    def _compute_table_count(self):
        for wizard in self:
            seats = wizard.seats_per_table or 1
            if wizard.mode == "append":
                needed = max(
                    0, wizard.participant_count - wizard.plan_id.seat_count
                )
            else:
                needed = wizard.participant_count
            wizard.table_count = max(1, math.ceil(needed / seats))

    def action_apply(self):
        self.ensure_one()
        plan = self.plan_id
        plan._check_not_locked()
        if self.table_count < 1:
            raise UserError(_("Enter at least one table."))
        if self.seats_per_table < 2:
            raise UserError(_("A table has at least 2 seats."))
        if self.mode == "replace":
            plan.table_ids.unlink()
            first_number = 1
            vals_list = [
                {
                    "plan_id": plan.id,
                    "number": first_number + index,
                    "seat_count": self.seats_per_table,
                    "position_h": position[0],
                    "position_v": position[1],
                }
                for index, position in enumerate(
                    plan._grid_positions(0, self.table_count)
                )
            ]
        else:
            first_number = max(plan.table_ids.mapped("number") or [0]) + 1
            vals_list = [
                {
                    "plan_id": plan.id,
                    "number": first_number + index,
                    "seat_count": self.seats_per_table,
                }
                for index in range(self.table_count)
            ]
        self.env["event.table"].create(vals_list)
        if self.mode == "append":
            # Appending recomputes the grid's column count from the new
            # total, so the tables already on the plan keep positions laid
            # out for the old count and the two grids do not nest. The new
            # tables above are created without a position for that reason;
            # rearranging the whole room now, the same pass Rearrange runs,
            # is what keeps them from landing on the tables already there
            # instead of a second layout algorithm that would have to
            # match `_grid_positions` by hand.
            plan.action_rearrange_tables()
        plan.message_post(
            body=_(
                "Tables %(first)s to %(last)s created, %(seats)s seats"
                " each.",
                first=first_number,
                last=first_number + self.table_count - 1,
                seats=self.seats_per_table,
            )
        )
