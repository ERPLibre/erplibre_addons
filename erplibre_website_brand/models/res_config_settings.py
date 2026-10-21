# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from markupsafe import Markup

from odoo import api, fields, models

from odoo.addons.erplibre_website_brand.models.website import (
    SECONDARY_TEXT_STYLES,
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    erplibre_signature_style = fields.Selection(
        related="website_id.erplibre_signature_style", readonly=False
    )
    erplibre_signature_background = fields.Selection(
        related="website_id.erplibre_signature_background", readonly=False
    )
    erplibre_signature_color_mode = fields.Selection(
        related="website_id.erplibre_signature_color_mode", readonly=False
    )
    erplibre_signature_accent_color = fields.Char(
        related="website_id.erplibre_signature_accent_color", readonly=False
    )
    erplibre_signature_text_color = fields.Char(
        related="website_id.erplibre_signature_text_color", readonly=False
    )
    erplibre_signature_background_color = fields.Char(
        related="website_id.erplibre_signature_background_color", readonly=False
    )
    erplibre_signature_logo_background = fields.Boolean(
        related="website_id.erplibre_signature_logo_background", readonly=False
    )
    erplibre_signature_logo_background_color = fields.Char(
        related="website_id.erplibre_signature_logo_background_color",
        readonly=False,
    )
    erplibre_signature_logo = fields.Binary(
        related="website_id.erplibre_signature_logo", readonly=False
    )
    erplibre_signature_text = fields.Char(
        related="website_id.erplibre_signature_text", readonly=False
    )
    erplibre_signature_seal_text = fields.Char(
        related="website_id.erplibre_signature_seal_text", readonly=False
    )
    erplibre_signature_circular_seal_text = fields.Char(
        related="website_id.erplibre_signature_circular_seal_text", readonly=False
    )
    erplibre_signature_builder_text = fields.Char(
        related="website_id.erplibre_signature_builder_text", readonly=False
    )
    erplibre_signature_accelerated_text = fields.Char(
        related="website_id.erplibre_signature_accelerated_text", readonly=False
    )
    erplibre_signature_band_text = fields.Char(
        related="website_id.erplibre_signature_band_text", readonly=False
    )
    erplibre_signature_tooltip_text = fields.Char(
        related="website_id.erplibre_signature_tooltip_text", readonly=False
    )
    erplibre_signature_url = fields.Char(
        related="website_id.erplibre_signature_url", readonly=False
    )
    erplibre_signature_preview = fields.Html(
        string="Signature preview",
        compute="_compute_erplibre_signature_preview",
        sanitize=False,
    )

    @api.depends(
        "website_id",
        "erplibre_signature_style",
        "erplibre_signature_background",
        "erplibre_signature_color_mode",
        "erplibre_signature_accent_color",
        "erplibre_signature_text_color",
        "erplibre_signature_background_color",
        "erplibre_signature_logo_background",
        "erplibre_signature_logo_background_color",
        "erplibre_signature_logo",
        "erplibre_signature_text",
        "erplibre_signature_url",
        *(f"erplibre_signature_{style}_text" for style in SECONDARY_TEXT_STYLES),
    )
    def _compute_erplibre_signature_preview(self):
        """Render the signature as the footer will, on the chosen background.

        The values come from the form, saved or not: the website record
        gives the defaults, the settings record overrides them.
        """
        for settings in self:
            if not settings.website_id:
                settings.erplibre_signature_preview = False
                continue
            website = settings.website_id
            logo = settings.erplibre_signature_logo
            values = website._erplibre_signature_values(
                logo=logo if logo != website.erplibre_signature_logo else None
            )
            values.update(
                style=settings.erplibre_signature_style or values["style"],
                dark=settings.erplibre_signature_background == "dark",
                palette=settings.erplibre_signature_color_mode == "palette",
                custom=settings.erplibre_signature_color_mode == "custom",
                color_style=website._erplibre_signature_color_style(
                    settings.erplibre_signature_color_mode,
                    settings.erplibre_signature_accent_color,
                    settings.erplibre_signature_text_color,
                    settings.erplibre_signature_background_color,
                    settings.erplibre_signature_logo_background
                    and settings.erplibre_signature_logo_background_color,
                ),
                url=settings.erplibre_signature_url or values["url"],
                text=settings.erplibre_signature_text or "",
                texts=website._erplibre_signature_texts(
                    {
                        style: settings[f"erplibre_signature_{style}_text"]
                        for style in SECONDARY_TEXT_STYLES
                    }
                ),
            )
            html = self.env["ir.qweb"]._render(
                "erplibre_website_brand.signature", values
            )
            background = "dark" if values["dark"] else "light"
            settings.erplibre_signature_preview = Markup(
                '<div class="o_erplibre_signature_preview '
                'o_erplibre_signature_preview_%s">%s</div>'
            ) % (background, html)
