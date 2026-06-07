#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsCgModel(models.Model):
    _inherit = "devops.cg.model"

    enable_sync_external = fields.Boolean(
        string="Enable sync_external",
        help="Feature associate with sync external",
    )

    sync_external_file_type = fields.Selection(
        selection=[("csv", "CSV"), ("xlsx", "Excel")],
        help="Feature associate with synx external",
        default="csv",
    )

    sync_external_index_line_header = fields.Integer(
        help="Indicate the line number of header. Default 0 for CSV, and 1 for Excel",
        compute="_compute_index_line_header",
        store=True,
        readonly=False,
    )

    # sync_external_skip = fields.Integer(
    #     help="Indicate the line number of header. Default 0 for CSV, and 1 for Excel",
    #     compute="_compute_index_line_header",
    #     store=True,
    #     readonly=False,
    # )

    sync_external_sheet_name = fields.Char(help="Can be Sheet0 or Sheet1")

    @api.depends("sync_external_file_type")
    def _compute_index_line_header(self):
        for rec in self:
            rec.sync_external_index_line_header = (
                0 if rec.sync_external_file_type == "csv" else 1
            )
