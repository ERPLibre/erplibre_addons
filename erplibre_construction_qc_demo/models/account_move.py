# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    chantier_project_id = fields.Many2one(
        comodel_name="project.project", string="Chantier"
    )


class AccountMove(models.Model):
    _inherit = "account.move"

    chantier_project_id = fields.Many2one(
        comodel_name="project.project",
        string="Chantier",
        compute="_compute_chantier_project_id",
        store=True,
    )

    @api.depends(
        "invoice_line_ids.sale_line_ids",
        "invoice_line_ids.sale_line_ids.order_id.chantier_project_id",
    )
    def _compute_chantier_project_id(self):
        for move in self:
            chantier = self.env["project.project"]
            for line in move.invoice_line_ids:
                for sol in line.sale_line_ids:
                    candidate = sol.order_id.chantier_project_id
                    if candidate and candidate.is_chantier:
                        chantier = candidate
                        break
                if chantier:
                    break
            move.chantier_project_id = chantier
