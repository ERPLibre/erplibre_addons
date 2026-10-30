# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sign_stamp_enabled = fields.Boolean(
        related="company_id.sign_stamp_enabled", readonly=False
    )
    sign_stamp_frame = fields.Boolean(
        related="company_id.sign_stamp_frame", readonly=False
    )
    sign_stamp_show_date = fields.Boolean(
        related="company_id.sign_stamp_show_date", readonly=False
    )
    sign_stamp_show_code = fields.Boolean(
        related="company_id.sign_stamp_show_code", readonly=False
    )
    sign_stamp_show_name = fields.Boolean(
        related="company_id.sign_stamp_show_name", readonly=False
    )
    sign_stamp_show_role = fields.Boolean(
        related="company_id.sign_stamp_show_role", readonly=False
    )
    sign_stamp_placement = fields.Selection(
        related="company_id.sign_stamp_placement", readonly=False
    )
    sign_stamp_color_mode = fields.Selection(
        related="company_id.sign_stamp_color_mode", readonly=False
    )
    sign_stamp_color_1 = fields.Char(
        related="company_id.sign_stamp_color_1", readonly=False
    )
    sign_stamp_color_2 = fields.Char(
        related="company_id.sign_stamp_color_2", readonly=False
    )
