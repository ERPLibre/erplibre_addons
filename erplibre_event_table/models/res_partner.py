# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    table_assignment_ids = fields.One2many(
        "event.table.assignment",
        "partner_id",
        string="Rotating Table Assignments",
    )
    table_plan_count = fields.Integer(
        compute="_compute_table_plan_count", string="# Rotating Tables"
    )

    @api.depends("table_assignment_ids")
    def _compute_table_plan_count(self):
        Assignment = self.env["event.table.assignment"]
        if not Assignment.has_access("read"):
            self.table_plan_count = 0
            return
        counts = dict(
            Assignment._read_group(
                [("partner_id", "in", self.ids)],
                groupby=["partner_id"],
                aggregates=["plan_id:count_distinct"],
            )
        )
        for partner in self:
            partner.table_plan_count = counts.get(partner, 0)

    def action_view_table_assignments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Rotating Table Assignments"),
            "res_model": "event.table.assignment",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"group_by": ["plan_id"]},
        }
