# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import fields, models


class ConstructionDocDevis(models.Model):
    _name = "construction.doc_devis"
    _description = "Devis de chantier (mirror)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "numero_devis"
    _order = "numero_devis, id"

    numero_devis = fields.Char(tracking=True)
    nom_chantier = fields.Char(tracking=True)
    client_name = fields.Char(tracking=True)
    client_email = fields.Char(tracking=True)
    montant = fields.Float(tracking=True)
    file_no_line = fields.Integer(string="No line spreadsheet", tracking=True)
    partner_id = fields.Many2one("res.partner", tracking=True)
    crm_lead_id = fields.Many2one("crm.lead", tracking=True)
    sale_order_id = fields.Many2one("sale.order", tracking=True)
