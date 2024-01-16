from odoo import _, api, fields, models


class DevopsCgModule(models.Model):
    _name = "devops.cg.module"
    _description = "devops_cg_module"

    name = fields.Char()

    code_generator = fields.Many2one(
        comodel_name="devops.cg",
        string="Project",
        ondelete="cascade",
    )

    model_ids = fields.One2many(
        comodel_name="devops.cg.model",
        inverse_name="module_id",
        string="Model",
    )

    devops_workspace_ids = fields.Many2many(
        comodel_name="devops.workspace",
        string="DevOps Workspace",
    )
