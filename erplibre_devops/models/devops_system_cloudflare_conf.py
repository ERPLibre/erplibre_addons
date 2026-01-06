#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsSystemCloudflareSiteConf(models.Model):
    _name = "devops.system.cloudflare.conf"
    _description = "devops_system_cloudflare_conf"
    _order = "id"

    name = fields.Char()

    listing = fields.Char()

    permission = fields.Text()

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
    )
