#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, exceptions, fields, models, tools


class DevopsDbImage(models.Model):
    _name = "devops.db.image"
    _description = "DB image fast restoration"

    name = fields.Char()

    path = fields.Char()
