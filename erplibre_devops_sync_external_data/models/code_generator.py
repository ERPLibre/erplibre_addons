#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import api, fields, models, modules, tools


class CodeGeneratorModule(models.Model):
    _inherit = "code.generator.module"

    enable_sync_external_data_write = fields.Boolean(
        string="Enable sync external data write",
        help="Will write external data from erplibre_devops",
    )

    devops_cg_model_ids = fields.Many2many(
        comodel_name="devops.cg.model", string="Devops CG Models"
    )
