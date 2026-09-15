from odoo import fields, models


class SyncModel(models.Model):
    _name = "sync.model"
    _description = (
        "Synchronisation model data to guide the sync and transform."
    )
    _inherit = ["mail.activity.mixin", "mail.thread"]
    _order = "sequence, name, id"

    name = fields.Char(tracking=True)

    description = fields.Text(
        string="Description",
        tracking=True,
    )

    active = fields.Boolean(tracking=True, default=True)

    sequence = fields.Integer(tracking=True, default=10)

    model_name = fields.Char(tracking=True)

    scenario = fields.Char(tracking=True)

    context_name = fields.Char(tracking=True)

    spreadsheet_extraction_metadata = fields.Json()
