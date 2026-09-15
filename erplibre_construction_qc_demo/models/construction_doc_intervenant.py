# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ConstructionDocIntervenant(models.Model):
    _name = "construction.doc_intervenant"
    _description = "Intervenant de chantier (mirror)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "nom"
    _order = "nom, id"

    nom = fields.Char(tracking=True)
    courriel = fields.Char(tracking=True)
    role = fields.Char(string="Rôle", tracking=True)
    type_label = fields.Char(string="Type", tracking=True)
    file_no_line = fields.Integer(string="No line spreadsheet", tracking=True)
    partner_id = fields.Many2one("res.partner", tracking=True)
