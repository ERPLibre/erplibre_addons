from odoo import fields, models


class ErplibreSyncTestEntry(models.Model):
    _name = "erplibre.sync.test.entry"
    _description = "Mirror model for sync external data tests"
    _inherit = ["mail.thread"]
    _order = "id desc"

    project_code = fields.Char(string="Code projet", tracking=True)
    client_name = fields.Char(string="Nom client", tracking=True)
    client_email = fields.Char(string="Courriel client", tracking=True)
    opportunity_name = fields.Char(string="Opportunité", tracking=True)
    amount = fields.Float(string="Montant", tracking=True)
    expected_date = fields.Date(string="Date prévue", tracking=True)
    file_no_line = fields.Integer(string="N° ligne fichier", tracking=True)

    partner_id = fields.Many2one("res.partner", string="Contact", tracking=True)
    crm_lead_id = fields.Many2one("crm.lead", string="Opportunité CRM", tracking=True)
    sale_order_id = fields.Many2one("sale.order", string="Soumission", tracking=True)
    project_id = fields.Many2one("project.project", string="Projet", tracking=True)
    invoice_id = fields.Many2one("account.move", string="Facture", tracking=True)
