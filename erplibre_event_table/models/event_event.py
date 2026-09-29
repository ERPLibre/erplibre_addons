# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models


class EventEvent(models.Model):
    _inherit = "event.event"

    use_rotating_tables = fields.Boolean(
        string="Rotating Tables",
        compute="_compute_use_rotating_tables",
        precompute=True,
        readonly=False,
        store=True,
    )
    table_plan_ids = fields.One2many(
        "event.table.plan", "event_id", string="Rotating Table Plans"
    )
    table_plan_count = fields.Integer(
        compute="_compute_table_plan_count",
        string="# Rotating Table Plans",
    )

    @api.depends("event_type_id")
    def _compute_use_rotating_tables(self):
        # Copy the template's value only when the template CHANGES, the
        # website_event.website_menu pattern: on a record already saved,
        # `_origin` is the record itself, so a plain write never enters
        # this branch and a hand-set value survives. The elif branch gives
        # the field its value on a new record, which precompute requires.
        for event in self:
            if (
                event.event_type_id
                and event.event_type_id != event._origin.event_type_id
            ):
                event.use_rotating_tables = (
                    event.event_type_id.use_rotating_tables
                )
            elif not event.use_rotating_tables:
                event.use_rotating_tables = False

    @api.depends("table_plan_ids")
    def _compute_table_plan_count(self):
        for event in self:
            event.table_plan_count = len(event.table_plan_ids)

    def action_view_table_plans(self):
        self.ensure_one()
        if not self.table_plan_ids:
            # Creating a plan from the event is the only path that proves
            # the event uses rotating tables without the operator ever
            # ticking the checkbox: turn the option on so the button and
            # the stat button stay visible afterwards instead of hiding
            # the plan they just opened.
            self.use_rotating_tables = True
            plan = self.env["event.table.plan"].create({"event_id": self.id})
            return {
                "type": "ir.actions.act_window",
                "res_model": "event.table.plan",
                "view_mode": "form",
                "res_id": plan.id,
                "context": {"default_event_id": self.id},
            }
        if len(self.table_plan_ids) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "event.table.plan",
                "view_mode": "form",
                "res_id": self.table_plan_ids.id,
                "context": {"default_event_id": self.id},
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": "event.table.plan",
            "view_mode": "list,form",
            "domain": [("event_id", "=", self.id)],
            "context": {"default_event_id": self.id},
        }

    def action_add_table_participants(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "event.table.participant.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_event_id": self.id},
        }
