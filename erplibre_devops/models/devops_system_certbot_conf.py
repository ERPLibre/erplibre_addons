#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsSystemCertbotSiteConf(models.Model):
    _name = "devops.system.certbot.conf"
    _description = "devops_system_certbot_conf"
    _order = "id"

    name = fields.Char(compute="_compute_name", store=True)

    version = fields.Char()

    path_bin = fields.Char()

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
    )

    def _compute_name(self):
        for rec in self:
            rec.name = rec.version
