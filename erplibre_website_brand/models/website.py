# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import base64
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import file_open
from odoo.tools.mimetypes import guess_mimetype

DEFAULT_URL = "https://erplibre.ca"
DEFAULT_LOGO = "erplibre_website_brand/static/src/img/erplibre_logo.svg"
DEFAULT_ACCENT = "#1F6F54"
DEFAULT_TEXT = "#4A535B"
DEFAULT_BACKGROUND = "#FFFFFF"
# A colour goes into a style attribute: a hexadecimal value or an rgb() /
# rgba() of numbers only, nothing that could close the declaration.
CSS_COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9\s.,%]+\))$")
# Styles with a text of their own besides the phrase: one field each,
# erplibre_signature_<style>_text.
SECONDARY_TEXT_STYLES = (
    "seal",
    "circular_seal",
    "builder",
    "accelerated",
    "band",
    "tooltip",
)
SIGNATURE_STYLES = [
    ("pill", "A · Pill"),
    ("seal", "B · Seal"),
    ("line", "C · Line"),
    ("circular_seal", "D · Circular seal"),
    ("builder", "E · Website builder"),
    ("accelerated", "F · Accelerated development"),
    ("badge", "G · Two-tone badge"),
    ("stack", "H · Technology stack"),
    ("editorial", "I · Editorial"),
    ("band", "J · Band"),
    ("tooltip", "K · Logo and tooltip"),
]


class Website(models.Model):
    _inherit = "website"

    @api.model
    def _default_erplibre_signature_logo(self):
        with file_open(DEFAULT_LOGO, "rb") as logo:
            return base64.b64encode(logo.read())

    erplibre_signature_style = fields.Selection(
        SIGNATURE_STYLES,
        string="Signature style",
        default="pill",
        required=True,
    )
    erplibre_signature_background = fields.Selection(
        [("light", "Light background"), ("dark", "Dark background")],
        string="Signature background",
        default="light",
        required=True,
        help="Background the signature sits on: each style has a version "
        "drawn for a light footer and one for a dark footer.",
    )
    erplibre_signature_color_mode = fields.Selection(
        [
            ("default", "Default"),
            ("palette", "Website palette"),
            ("custom", "Custom"),
        ],
        string="Signature colors",
        default="default",
        required=True,
        help="Default: the colors of the mockups. Website palette: the accent "
        "comes from the website's colors (first one on a light background, "
        "second one on a dark background) and the text takes the color of "
        "the footer. Custom: the three colors below.",
    )
    erplibre_signature_accent_color = fields.Char(
        string="Signature accent color",
        default=DEFAULT_ACCENT,
        help="Color of « ERPLibre » and of the drawn details, in custom mode.",
    )
    erplibre_signature_text_color = fields.Char(
        string="Signature text color",
        default=DEFAULT_TEXT,
        help="Color of the phrase and of the other text, in custom mode.",
    )
    erplibre_signature_background_color = fields.Char(
        string="Signature background color",
        default=DEFAULT_BACKGROUND,
        help="Background of the parts drawn on a surface (pill, builder "
        "frame, band, badge label, tooltip), in custom mode.",
    )
    erplibre_signature_logo_background = fields.Boolean(
        string="Signature logo background",
        help="In custom mode, draws the color below behind the logo. "
        "Unchecked, the logo has a transparent background.",
    )
    erplibre_signature_logo_background_color = fields.Char(
        string="Signature logo background color",
        default=DEFAULT_BACKGROUND,
        help="Color behind the logo, in custom mode with a logo background.",
    )
    erplibre_signature_logo = fields.Binary(
        string="Signature logo",
        default=_default_erplibre_signature_logo,
        help="Left empty, the ERPLibre logo shipped with the module is used.",
    )
    erplibre_signature_text = fields.Char(
        string="Signature phrase",
        translate=True,
        help="Words before « ERPLibre ». Left empty, the translated default "
        "« Built with » is used.",
    )
    erplibre_signature_seal_text = fields.Char(
        string="Signature text, B · Seal",
        translate=True,
        help="Line under « ERPLibre », style B. Left empty: « Free software · Digital sovereignty », translated.",
    )
    erplibre_signature_circular_seal_text = fields.Char(
        string="Signature text, D · Circular seal",
        translate=True,
        help="End of the ring, after « ERPLibre », style D. Left empty: « Free software », translated.",
    )
    erplibre_signature_builder_text = fields.Char(
        string="Signature text, E · Website builder",
        translate=True,
        help="Line above « ERPLibre Website », style E. Left empty: « Site built with the website builder », translated.",
    )
    erplibre_signature_accelerated_text = fields.Char(
        string="Signature text, F · Accelerated development",
        translate=True,
        help="Line under the main one, after « + », style F. Left empty: « AI integration », translated.",
    )
    erplibre_signature_band_text = fields.Char(
        string="Signature text, J · Band",
        translate=True,
        help="Label on the left of the band, style J. Left empty: « Free software », translated.",
    )
    erplibre_signature_tooltip_text = fields.Char(
        string="Signature text, K · Logo and tooltip",
        translate=True,
        help="Sentence of the tooltip, style K. Left empty: « This site is built with ERPLibre, a free business platform. », translated.",
    )
    erplibre_signature_url = fields.Char(
        string="Signature link",
        default=DEFAULT_URL,
        help="Address the signature links to.",
    )

    @api.constrains("erplibre_signature_url")
    def _check_erplibre_signature_url(self):
        for website in self:
            url = website.erplibre_signature_url
            if url and not url.startswith(("https://", "http://", "/")):
                raise ValidationError(
                    self.env._(
                        "The signature link must start with https://, http:// or /."
                    )
                )

    @api.constrains(
        "erplibre_signature_accent_color",
        "erplibre_signature_text_color",
        "erplibre_signature_background_color",
        "erplibre_signature_logo_background_color",
    )
    def _check_erplibre_signature_colors(self):
        for website in self:
            for color in (
                website.erplibre_signature_accent_color,
                website.erplibre_signature_text_color,
                website.erplibre_signature_background_color,
                website.erplibre_signature_logo_background_color,
            ):
                if color and not CSS_COLOR.match(color.strip()):
                    raise ValidationError(
                        self.env._(
                            "A signature color is a hexadecimal value such as "
                            "#1F6F54, or rgb()/rgba(): « %s » is not.",
                            color,
                        )
                    )

    @api.model
    def _erplibre_signature_color_style(
        self, mode, accent, text, background, logo_background=None
    ):
        """Inline style of the custom colors, empty in any other mode.

        Custom properties the stylesheet reads: the accent; the text color
        for the phrase, the names and, lighter, the secondary text; the
        background of the parts drawn on a surface; the background behind
        the logo, with the padding that shows it. An invalid or empty color
        keeps the stylesheet's value, which is transparent for the logo.

        :param logo_background: color behind the logo, falsy for none.
        """
        if mode != "custom":
            return ""
        declarations = []
        accent = (accent or "").strip()
        text = (text or "").strip()
        background = (background or "").strip()
        if CSS_COLOR.match(accent):
            declarations.append(f"--o-erplibre-accent: {accent}")
        if CSS_COLOR.match(text):
            declarations += [
                f"--o-erplibre-text: {text}",
                f"--o-erplibre-ink: {text}",
                f"--o-erplibre-muted: color-mix(in srgb, {text} 75%, transparent)",
            ]
        if CSS_COLOR.match(background):
            declarations.append(f"--o-erplibre-surface: {background}")
        logo_background = (logo_background or "").strip()
        if CSS_COLOR.match(logo_background):
            declarations += [
                f"--o-erplibre-logo-surface: {logo_background}",
                "--o-erplibre-logo-padding: 2px",
            ]
        return "; ".join(declarations)

    def _erplibre_signature_values(self, logo=None):
        """Values of the « erplibre_website_brand.signature » template.

        :param logo: base64 logo shown instead of the stored one, for a
            preview of an unsaved change; it is inlined as a data URI.
        :return: dict with style, dark, palette, custom, color_style,
            logo_url, url, text and texts; text is empty when the translated
            default phrase applies, color_style when the colors are not
            custom; texts maps a style to its own text, set ones only.
        """
        self.ensure_one()
        if logo:
            mimetype = guess_mimetype(base64.b64decode(logo))
            logo_url = f"data:{mimetype};base64,{logo.decode()}"
        elif self.erplibre_signature_logo:
            unique = self.write_date.strftime("%Y%m%d%H%M%S")
            logo_url = (
                f"/web/image/website/{self.id}/erplibre_signature_logo"
                f"?unique={unique}"
            )
        else:
            logo_url = f"/{DEFAULT_LOGO}"
        return {
            "style": self.erplibre_signature_style or "pill",
            "dark": self.erplibre_signature_background == "dark",
            "palette": self.erplibre_signature_color_mode == "palette",
            "custom": self.erplibre_signature_color_mode == "custom",
            "color_style": self._erplibre_signature_color_style(
                self.erplibre_signature_color_mode,
                self.erplibre_signature_accent_color,
                self.erplibre_signature_text_color,
                self.erplibre_signature_background_color,
                self.erplibre_signature_logo_background
                and self.erplibre_signature_logo_background_color,
            ),
            "logo_url": logo_url,
            "url": self.erplibre_signature_url or DEFAULT_URL,
            "text": self.erplibre_signature_text or "",
            "texts": self._erplibre_signature_texts(
                {
                    style: self[f"erplibre_signature_{style}_text"]
                    for style in SECONDARY_TEXT_STYLES
                }
            ),
        }

    @api.model
    def _erplibre_signature_texts(self, values):
        """The texts of their own that are set, by style; the template
        falls back on the translated default for the others."""
        return {
            style: text.strip()
            for style, text in values.items()
            if text and text.strip()
        }
