# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Le réglage du cachet de signature, par société."""

import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..tools.stamp_drawing import ERPLIBRE_COLORS

COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class ResCompany(models.Model):
    _inherit = "res.company"

    sign_stamp_enabled = fields.Boolean(string="Signature Stamp")
    sign_stamp_frame = fields.Boolean(string="Guilloche Frame", default=True)
    sign_stamp_show_date = fields.Boolean(string="Signing Date", default=True)
    sign_stamp_show_code = fields.Boolean(
        string="Signature Code", default=True
    )
    sign_stamp_show_name = fields.Boolean(string="Signer Name")
    sign_stamp_show_role = fields.Boolean(string="Signer Role")
    sign_stamp_placement = fields.Selection(
        [("inside", "Inside the box"), ("below", "Below the box")],
        string="Stamp Lines Placement",
        default="inside",
    )
    sign_stamp_color_mode = fields.Selection(
        [
            ("erplibre", "ERPLibre"),
            ("company", "Document layout colors"),
            ("custom", "Custom"),
        ],
        string="Stamp Colors",
        default="erplibre",
    )
    sign_stamp_color_1 = fields.Char(
        string="Stamp Color 1", default=ERPLIBRE_COLORS[0]
    )
    sign_stamp_color_2 = fields.Char(
        string="Stamp Color 2", default=ERPLIBRE_COLORS[1]
    )

    @api.constrains("sign_stamp_color_1", "sign_stamp_color_2")
    def _check_sign_stamp_colors(self):
        for company in self:
            for color in (
                company.sign_stamp_color_1,
                company.sign_stamp_color_2,
            ):
                if color and not COLOR_PATTERN.match(color):
                    raise ValidationError(
                        self.env._("%s is not a #rrggbb color.", color)
                    )

    def _get_sign_stamp_colors(self):
        """Rend les deux couleurs ``#rrggbb`` du cachet, selon
        ``sign_stamp_color_mode``.

        ``company`` prend ``primary_color`` et ``secondary_color``, celles de
        la mise en page des documents ; ``custom`` prend les deux couleurs du
        réglage. Une couleur absente ou mal formée retombe sur celle
        d'ERPLibre au même rang.
        """
        self.ensure_one()
        if self.sign_stamp_color_mode == "company":
            chosen = (self.primary_color, self.secondary_color)
        elif self.sign_stamp_color_mode == "custom":
            chosen = (self.sign_stamp_color_1, self.sign_stamp_color_2)
        else:
            chosen = ERPLIBRE_COLORS
        return tuple(
            color if color and COLOR_PATTERN.match(color) else default
            for color, default in zip(chosen, ERPLIBRE_COLORS, strict=True)
        )
