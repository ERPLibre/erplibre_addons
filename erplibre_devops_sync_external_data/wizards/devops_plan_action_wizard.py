#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsPlanActionWizard(models.TransientModel):
    _inherit = "devops.plan.action.wizard"

    model_fast_creation_field_enable_external_sync = fields.Boolean(
        string="Field value enable external sync",
        help="Will generate code for external sync",
    )

    # def action_model_fast_creation(self):
    #     status = super().action_model_fast_creation()
    #     for rec in self:
    #         if rec.model_fast_creation_model_name:
    #             for model_id in rec.model_ids:
    #                 if model_id.name == rec.model_fast_creation_model_name:
    #                     model_id.enable_sync_external = True
    #
    #     return status

    def _generate_from_json_model(self, model_id):
        super()._generate_from_json_model(model_id)
        model_id.enable_sync_external = (
            self.model_fast_creation_field_enable_external_sync
        )
        field_name = "file_no_line"
        field_id = self.env["devops.cg.field"].search(
            [
                (
                    "devops_workspace_ids",
                    "=",
                    model_id.devops_workspace_ids.ids,
                ),
                ("name", "=", field_name),
                ("model_id", "=", model_id.id),
            ]
        )
        if not field_id:
            field_id = self.env["devops.cg.field"].create(
                [
                    {
                        "name": field_name,
                        "string": "No line spreadsheet",
                        "help": "Show the line from import file.",
                        "type": "integer",
                        "model_id": model_id.id,
                        "devops_workspace_ids": [
                            (6, 0, model_id.devops_workspace_ids.ids)
                        ],
                        "tracking": True,
                    }
                ]
            )

    def _generate_from_json_field(
        self, field_id, dct_field, is_first_run=False
    ):
        super()._generate_from_json_field(field_id, dct_field)
        csv_header_name = dct_field.get("csv_header_name")
        if csv_header_name:
            field_id.sync_external_associate_header_name = csv_header_name
        field_id.enable_sync_external = (
            self.model_fast_creation_field_enable_external_sync
        )
        field_id.sync_external_associate_header_name = dct_field.get("string")
        if is_first_run:
            field_id.sync_external_is_primary = True
