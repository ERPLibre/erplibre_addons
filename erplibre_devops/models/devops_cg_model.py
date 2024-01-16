from odoo import _, api, fields, models


class DevopsCgModel(models.Model):
    _name = "devops.cg.model"
    _description = "devops_cg_model"

    name = fields.Char()

    description = fields.Char()

    field_ids = fields.One2many(
        comodel_name="devops.cg.field",
        inverse_name="model_id",
        string="Field",
    )

    module_id = fields.Many2one(
        comodel_name="devops.cg.module",
        string="Module",
        ondelete="cascade",
    )

    devops_workspace_ids = fields.Many2many(
        comodel_name="devops.workspace",
        string="DevOps Workspace",
    )
