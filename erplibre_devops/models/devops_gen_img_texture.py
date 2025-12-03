# !/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsGenImgTexture(models.Model):
    _name = "devops.gen.img.texture"
    _description = "devops_gen_img_texture"
    _order = "name asc,id asc"

    name = fields.Char()
