#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class ErplibreModeVersionBase(models.Model):
    _name = "erplibre.mode.version.base"
    _description = "erplibre_mode_version_base"

    name = fields.Char()

    value = fields.Char()

    is_tag = fields.Boolean(help="Is it a tag from Git?")
