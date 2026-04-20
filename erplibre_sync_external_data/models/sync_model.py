from odoo import fields, models


class SyncModel(models.Model):
    _name = "sync.model"
    _description = (
        "Synchronisation model data to guide the sync and transform."
    )
    _inherit = ["mail.activity.mixin", "mail.thread"]

    name = fields.Char(tracking=True)

    model_name = fields.Char(tracking=True)

    scenario = fields.Char(tracking=True)

    context_name = fields.Char(tracking=True)

    spreadsheet_extraction_metadata = fields.Json()
