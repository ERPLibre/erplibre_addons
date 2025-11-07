#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class ErplibreModeVersionErplibre(models.Model):
    _name = "erplibre.mode.version.erplibre"
    _description = "erplibre_mode_version_erplibre"

    name = fields.Char()

    value = fields.Char()

    is_tag = fields.Boolean(help="Is it a tag from Git?")
