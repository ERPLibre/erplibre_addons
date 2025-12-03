#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class ErplibreModeExec(models.Model):
    _name = "erplibre.mode.exec"
    _description = "erplibre_mode_exec"

    name = fields.Char()

    active = fields.Boolean(default=True)

    value = fields.Char()
