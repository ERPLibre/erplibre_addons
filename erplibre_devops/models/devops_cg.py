import json

from odoo import _, api, exceptions, fields, models


class DevopsCg(models.Model):
    _name = "devops.cg"
    _description = "devops_cg"

    name = fields.Char()

    # TODO if share result, do a command to copy file all and recreate it like a mirror on other workspace
    devops_workspace_ids = fields.Many2many(
        comodel_name="devops.workspace",
        string="DevOps Workspace",
    )

    # TODO create boolean cache with default workspace to work for the other
    default_workspace_master = fields.Many2one(
        comodel_name="devops.workspace",
        string="DevOps Workspace default",
    )

    module_ids = fields.One2many(
        comodel_name="devops.cg.module",
        inverse_name="code_generator",
        string="Module",
    )

    force_clean_before_generate = fields.Boolean(
        help="Will remove all modules to generate news."
    )

    @api.model_create_multi
    def create(self, vals_list):
        r = super().create(vals_list)
        w_ids = self.env.context.get("default_devops_workspace_ids")
        if w_ids:
            for cg_id in r:
                if not cg_id.default_workspace_master:
                    cg_id.default_workspace_master = w_ids[0]

                if not cg_id.devops_workspace_ids:
                    cg_id.devops_workspace_ids = [6, 0, w_ids]
                for module_id in cg_id.module_ids:
                    if not module_id.devops_workspace_ids:
                        module_id.devops_workspace_ids = [
                            (
                                6,
                                0,
                                w_ids,
                            )
                        ]
                    for model_id in module_id.model_ids:
                        if not model_id.devops_workspace_ids:
                            model_id.devops_workspace_ids = [
                                (
                                    6,
                                    0,
                                    w_ids,
                                )
                            ]
                        for field_id in model_id.field_ids:
                            if not field_id.devops_workspace_ids:
                                field_id.devops_workspace_ids = [
                                    (
                                        6,
                                        0,
                                        w_ids,
                                    )
                                ]
        return r
