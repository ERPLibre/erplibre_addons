# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ConstructionDocFacture(models.Model):
    _name = "construction.doc_facture"
    _description = "Facture de chantier (mirror)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "no_facture"
    _order = "no_facture, id"

    no_facture = fields.Char(tracking=True)
    numero_soumission = fields.Char(tracking=True)
    date_echeance = fields.Date(tracking=True)
    montant_paye = fields.Float(tracking=True)
    fournisseur = fields.Char(tracking=True)
    file_no_line = fields.Integer(string="No line spreadsheet", tracking=True)
    project_id = fields.Many2one(
        comodel_name="project.project", string="Chantier", tracking=True
    )
