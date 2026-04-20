#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsCgField(models.Model):
    _inherit = "devops.cg.field"

    enable_sync_external = fields.Boolean(
        string="Enable sync_external",
        help="Feature associate with sync external",
    )

    sync_external_is_primary = fields.Boolean(
        string="Is primary",
        help="Sync external - This is a primary field for indexation",
    )

    sync_external_associate_header_name = fields.Char(
        help="CSV header name, will be associate for migration sync external"
    )
