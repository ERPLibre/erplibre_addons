#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsCgModel(models.Model):
    _name = "devops.cg.model"
    _description = "devops_cg_model"
    _order = "sequence, id"

    name = fields.Char(required=True)

    active = fields.Boolean(default=True)

    sequence = fields.Integer(default=10)

    description = fields.Char()

    is_to_remove = fields.Boolean(
        help=(
            "Active to tell the code generator to remove by refactoring this"
            " model."
        )
    )

    is_inherit = fields.Boolean(help="If the model inherit another model.")

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

    def get_field_dct(self):
        self.ensure_one()
        dct_model = {}
        for field_id in self.field_ids:
            dct_model[field_id.name] = field_id.get_dct()
        return dct_model
