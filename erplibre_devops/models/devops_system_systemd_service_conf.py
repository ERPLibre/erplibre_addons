#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsSystemSystemdServiceConf(models.Model):
    _name = "devops.system.systemd.service.conf"
    _description = "devops_system_systemd_service_conf"
    _order = "id"

    name = fields.Char()

    is_erplibre_detected = fields.Boolean(
        help="When detect the word erplibre into file_content.",
        compute="_compute_analyse",
    )

    file_content = fields.Text()

    file_path = fields.Char()

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
    )

    @api.depends("file_content")
    def _compute_analyse(self):
        for rec in self:
            if rec.file_content:
                rec.is_erplibre_detected = (
                    "erplibre" in rec.file_content.lower()
                )
