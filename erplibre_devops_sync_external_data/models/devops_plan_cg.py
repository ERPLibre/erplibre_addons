#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import json
import os

from odoo import _, api, exceptions, fields, models


class DevopsPlanCg(models.Model):
    _inherit = "devops.plan.cg"

    def _update_inherit_before_code_generator_writer(self, code_generator_id):
        super()._update_inherit_before_code_generator_writer(code_generator_id)
        for rec in self:
            # Generate data
            model_sync_external_data_ids = rec.devops_cg_model_ids.filtered(
                lambda r: not r.is_to_remove and r.enable_sync_external
            )
            if model_sync_external_data_ids:
                code_generator_id.enable_sync_external_data_write = True
                code_generator_id.add_module_dependency(
                    "erplibre_sync_external_data_spreadsheet"
                )
                code_generator_id.devops_cg_model_ids = [
                    (6, 0, model_sync_external_data_ids.ids)
                ]
                if any(
                    m.sync_external_enable_queue_job
                    for m in model_sync_external_data_ids
                ):
                    code_generator_id.add_module_dependency("queue_job")
