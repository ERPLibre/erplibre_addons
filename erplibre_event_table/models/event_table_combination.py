# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventTableCombination(models.Model):
    _name = "event.table.combination"
    _description = "Rotating Table Combination"
    _order = "plan_id, rank"

    plan_id = fields.Many2one(
        "event.table.plan", required=True, ondelete="cascade", index=True
    )
    event_id = fields.Many2one(
        related="plan_id.event_id", store=True, index=True
    )
    plan_state = fields.Selection(related="plan_id.state")
    rank = fields.Integer(required=True)
    name = fields.Char(compute="_compute_name")
    # placement_data holds [[round, participant_id, table_number, seat], ...]
    # sorted by (round, table_number, seat, participant_id). It carries no
    # required=True: the database would refuse an empty list with an
    # unreadable message, so emptiness is checked in Python.
    placement_data = fields.Json()
    company_pair_count = fields.Integer(
        string="Colleague Pairs", readonly=True
    )
    repeated_pair_count = fields.Integer(
        string="Repeated Meetings", readonly=True
    )
    extra_meeting_count = fields.Integer(
        string="Extra Meetings", readonly=True
    )
    max_pair_meetings = fields.Integer(
        string="Most Meetings of a Pair", readonly=True
    )
    table_return_count = fields.Integer(string="Table Returns", readonly=True)
    met_distinct_min = fields.Integer(
        string="People Met (Minimum)", readonly=True
    )
    met_distinct_avg = fields.Float(
        string="People Met (Average)", digits=(16, 1), readonly=True
    )
    cost = fields.Integer(readonly=True)
    lower_bound = fields.Integer(string="Proven Minimum", readonly=True)
    # The library composes this as top_level_seed * SEED_STRIDE + k so that
    # this candidate's draw replays exactly; it reaches ~2.2e15, past the
    # 4-byte range of an Integer column, and a double holds it exactly
    # below 2**53. A reader must int() it before handing it to
    # random.Random: seeding with a float does not reproduce the same
    # stream as seeding with the equal integer, since CPython only uses an
    # int seed directly and hashes anything else.
    seed = fields.Float(readonly=True)
    distance_to_first = fields.Float(digits=(16, 2), readonly=True)
    is_proven_optimal = fields.Boolean(readonly=True)
    is_close_variant = fields.Boolean(string="Close Variant", readonly=True)
    is_adjusted = fields.Boolean(string="Adjusted by Hand", readonly=True)
    # Written once, at generation, and never recomputed: the plan's pins
    # go on changing after a combination is born, so anything derived
    # from the CURRENT pins would describe a constraint this combination
    # was never generated under.
    is_pin_constrained = fields.Boolean(
        string="Generated Around Pins",
        readonly=True,
        help="The reserved places of the plan were held while this"
        " combination was generated.",
    )
    is_chosen = fields.Boolean(compute="_compute_is_chosen")
    method = fields.Selection(
        [("design", "Algebraic Design"), ("greedy", "Greedy Construction")],
        readonly=True,
    )
    stopped_by = fields.Selection(
        [
            ("lower_bound", "Minimum reached"),
            ("no_conflict", "No conflict left"),
            ("iterations", "Iteration limit"),
            ("time", "Time limit"),
        ],
        readonly=True,
    )

    @api.depends("rank")
    def _compute_name(self):
        for combination in self:
            combination.name = _("Combination %(rank)s", rank=combination.rank)

    @api.depends("plan_id.chosen_combination_id")
    def _compute_is_chosen(self):
        for combination in self:
            combination.is_chosen = (
                combination.plan_id.chosen_combination_id == combination
            )

    def unlink(self):
        """Keep the plan's chosen pointer aimed at something that exists.

        Deleting the combination a plan currently uses would clear
        chosen_combination_id by cascade and leave the assignments
        standing with nothing left to explain where they came from.
        Choosing another combination moves the pointer, which frees this
        one; action_clear_combinations skips it for the same reason.
        """
        for combination in self:
            if combination.plan_id.chosen_combination_id == combination:
                raise UserError(
                    _(
                        "This combination is the one in use. Choose"
                        " another one before deleting it."
                    )
                )
        return super().unlink()

    def get_floor_plan_data(self):
        self.ensure_one()
        return self.plan_id.get_floor_plan_data(combination_id=self.id)

    def action_open_preview(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "event.table.combination",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_choose(self):
        self.ensure_one()
        plan = self.plan_id
        plan._lock()
        if plan.state not in ("proposed", "chosen"):
            raise UserError(_("Generate combinations before choosing one."))
        placements = plan._combination_placements(self)
        tables = {table.number: table.id for table in plan.table_ids}
        participants = set(plan.participant_ids.ids)
        if not placements or any(
            placement.table not in tables
            or placement.person not in participants
            for placement in placements
        ):
            raise UserError(
                _(
                    "Participants or tables changed since this combination"
                    " was generated. Generate the combinations again."
                )
            )
        lines = self.env["event.table.assignment"].with_context(
            event_table_assignment_write=True
        )
        plan.assignment_ids.with_context(
            event_table_assignment_write=True
        ).unlink()
        lines.create(
            [
                {
                    "plan_id": plan.id,
                    "combination_id": self.id,
                    "round_number": placement.round,
                    "table_id": tables[placement.table],
                    "participant_id": placement.person,
                    "seat_number": placement.seat,
                }
                for placement in placements
            ]
        )
        plan.write({"state": "chosen", "chosen_combination_id": self.id})
        self.is_adjusted = False
        plan.message_post(
            body=_("%(combination)s chosen.", combination=self.name)
        )
