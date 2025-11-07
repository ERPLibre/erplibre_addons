#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsInstanceType(models.Model):
    _name = "devops.instance.type"
    _description = "devops_instance_type"

    name = fields.Char()
