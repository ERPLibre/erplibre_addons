# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import base64
import re

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged

from odoo.addons.erplibre_website_brand.models.website import (
    DEFAULT_LOGO,
    SECONDARY_TEXT_STYLES,
    SIGNATURE_STYLES,
)

# A 1x1 transparent GIF: any image the binary field accepts will do.
GIF = base64.b64encode(
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@tagged("post_install", "-at_install")
class TestBrandPromotion(HttpCase):
    def setUp(self):
        super().setUp()
        self.website = self.env["website"].get_current_website()

    def render(self, lang="en_US"):
        """The credit as a page renders it: the website of a request reads
        its fields in the language of the page."""
        website = self.website.with_context(lang=lang)
        return str(
            self.env["ir.qweb"]
            .with_context(lang=lang)
            ._render(
                "web.brand_promotion_message",
                {"website": website, "_message": "The #1"},
            )
        )

    def text(self, html):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

    def load_french(self):
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            ["erplibre_website_brand"], ["fr_CA"], overwrite=True
        )

    def test_default_signature(self):
        html = self.render()
        self.assertIn("o_erplibre_signature_pill", html)
        self.assertIn('href="https://erplibre.ca"', html)
        self.assertIn("Built with ERPLibre", self.text(html))
        self.assertIn(
            f"/web/image/website/{self.website.id}/erplibre_signature_logo", html
        )
        self.assertNotIn("Odoo", html)
        self.assertNotIn("The #1", html)

    def test_every_style_in_both_backgrounds(self):
        for style, _label in SIGNATURE_STYLES:
            for background in ("light", "dark"):
                self.website.write(
                    {
                        "erplibre_signature_style": style,
                        "erplibre_signature_background": background,
                    }
                )
                html = self.render()
                self.assertIn(f"o_erplibre_signature_{style}", html)
                self.assertEqual(
                    "o_erplibre_signature_dark" in html, background == "dark"
                )
                self.assertIn('href="https://erplibre.ca"', html, style)
                self.assertNotIn("<block>", html, style)

    def test_french_default_phrase(self):
        self.load_french()
        self.assertIn("Créé grâce à ERPLibre", self.text(self.render("fr_CA")))

    def test_custom_phrase_translated_per_language(self):
        self.load_french()
        self.env["res.lang"]._activate_lang("en_US")
        self.website.with_context(lang="en_US").erplibre_signature_text = "Made with"
        self.website.with_context(lang="fr_CA").erplibre_signature_text = "Conçu avec"
        self.assertIn("Made with ERPLibre", self.text(self.render("en_US")))
        self.assertIn("Conçu avec ERPLibre", self.text(self.render("fr_CA")))

    def test_style_texts_default_and_custom(self):
        defaults = {
            "seal": "Free software · Digital sovereignty",
            "circular_seal": "FREE SOFTWARE",
            "builder": "Site built with the website builder",
            "accelerated": "AI integration",
            "band": "Free software",
            "tooltip": "a free business platform",
        }
        for style in SECONDARY_TEXT_STYLES:
            self.website.erplibre_signature_style = style
            self.assertIn(defaults[style], self.text(self.render()), style)
            self.website[f"erplibre_signature_{style}_text"] = f"Own {style} words"
            text = self.text(self.render())
            expected = f"Own {style} words"
            self.assertIn(
                expected.upper() if style == "circular_seal" else expected, text
            )
            self.assertNotIn(defaults[style], text, style)

    def test_custom_link_and_logo(self):
        self.website.erplibre_signature_url = "https://example.org/erp"
        self.assertIn('href="https://example.org/erp"', self.render())
        self.website.erplibre_signature_logo = False
        self.assertIn(f'src="/{DEFAULT_LOGO}"', self.render())
        self.website.erplibre_signature_logo = GIF
        self.website.flush_recordset()
        response = self.url_open(
            f"/web/image/website/{self.website.id}/erplibre_signature_logo"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"GIF89a"))

    def test_link_must_be_web_address(self):
        with self.assertRaises(ValidationError):
            self.website.erplibre_signature_url = "javascript:alert(1)"

    def test_color_modes(self):
        html = self.render()
        self.assertNotIn("o_erplibre_signature_palette", html)
        self.assertNotIn("--o-erplibre-accent:", html)
        self.website.erplibre_signature_color_mode = "palette"
        self.assertIn("o_erplibre_signature_palette", self.render())
        self.website.write(
            {
                "erplibre_signature_color_mode": "custom",
                "erplibre_signature_accent_color": "#C9A84C",
                "erplibre_signature_text_color": "rgb(10, 20, 30)",
            }
        )
        html = self.render()
        self.assertNotIn("o_erplibre_signature_palette", html)
        self.assertIn("--o-erplibre-accent: #C9A84C", html)
        self.assertIn("--o-erplibre-text: rgb(10, 20, 30)", html)

    def test_logo_background(self):
        # Transparent by default; the chosen color applies in custom mode
        # only, once the logo background is checked.
        self.website.write(
            {
                "erplibre_signature_color_mode": "custom",
                "erplibre_signature_logo_background_color": "#ABCDEF",
            }
        )
        self.assertNotIn("--o-erplibre-logo-surface", self.render())
        self.website.erplibre_signature_logo_background = True
        html = self.render()
        self.assertIn("--o-erplibre-logo-surface: #ABCDEF", html)
        self.assertIn("--o-erplibre-logo-padding: 2px", html)
        self.website.erplibre_signature_color_mode = "default"
        self.assertNotIn("--o-erplibre-logo-surface", self.render())
        with self.assertRaises(ValidationError):
            self.website.erplibre_signature_logo_background_color = "red;"

    def test_color_must_be_a_plain_value(self):
        with self.assertRaises(ValidationError):
            self.website.erplibre_signature_accent_color = 'red;" onclick="x'

    def test_settings_require_style_and_colors(self):
        arch = self.env["res.config.settings"].get_views([(False, "form")])
        arch = arch["views"]["form"]["arch"]
        arch = arch.decode() if isinstance(arch, bytes) else arch
        for field in (
            "erplibre_signature_style",
            "erplibre_signature_background",
            "erplibre_signature_color_mode",
        ):
            self.assertRegex(arch, rf'name="{field}"[^>]*required="website_id"')

    def test_settings_preview_follows_unsaved_values(self):
        settings = self.env["res.config.settings"].create(
            {
                "erplibre_signature_style": "band",
                "erplibre_signature_background": "dark",
                "erplibre_signature_text": "Propulsé par",
                "erplibre_signature_logo": GIF,
                "erplibre_signature_color_mode": "custom",
                "erplibre_signature_accent_color": "#123456",
                "erplibre_signature_logo_background": True,
                "erplibre_signature_logo_background_color": "#654321",
            }
        )
        preview = str(settings.erplibre_signature_preview)
        self.assertIn("--o-erplibre-accent: #123456", preview)
        self.assertIn("--o-erplibre-logo-surface: #654321", preview)
        self.assertIn("o_erplibre_signature_preview_dark", preview)
        self.assertIn("o_erplibre_signature_band", preview)
        self.assertIn("Propulsé par", preview)

    def test_public_footer(self):
        html = self.url_open("/").text
        self.assertIn("o_erplibre_signature", html)
        self.assertNotIn("odoo.com?utm_source=db", html)
