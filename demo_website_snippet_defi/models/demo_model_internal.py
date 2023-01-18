from odoo import _, api, fields, models


class DemoModelInternal(models.Model):
    _name = "demo.model.internal"
    _description = "demo_model_internal"

    name = fields.Char()
