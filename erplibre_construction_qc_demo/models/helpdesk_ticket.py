# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    ignore_associate_chantier = fields.Boolean(
        tracking=True,
        help="Skip the chantier-association algorithm for this ticket",
    )

    chantier_project_id = fields.Many2one(
        comodel_name="project.project",
        string="Chantier associé",
        tracking=True,
    )
