# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import unittest

from ..messages import CODES, TEMPLATES, finding, params_of, render

SPEC_CODES = """
skipped_translation php_removed php_unbalanced php_unpaired
foreign_lang_skipped foreign_lang_page choice_ignored local_edit_kept
local_edit_overwritten menu_skipped_existing_url stale_record
skipped_container_type unused_container layout_detected
footer_not_imported container_inlined php_approximated langs_fallback
langs_version_mismatch main_lang_defaulted form_replaced search_rewired
social_unsupported literal_placeholder missing_media media_matched_by_name
media_url_conflict media_skipped_type media_name_refused media_too_large
media_duplicate media_unreadable media_capped svg_sanitised
unresolved_link url_conflict rewrite_conflict ref_slugified form_removed
unsafe_markup_removed head_asset_dropped script_removed script_kept
inline_script_needs_jquery css_rescoped css_external_removed recreated
menu_flattened menu_capped language_mismatch author_alias_ignored
credits source_error page_error run_error
""".split()


class MessagesCases:
    def test_every_spec_code_has_a_template(self):
        self.assertEqual(sorted(CODES), sorted(SPEC_CODES))
        for code, (severity, template) in TEMPLATES.items():
            self.assertIn(severity, ("info", "warning", "error"), code)
            self.assertTrue(template, code)
            render(code, {name: "x" for name in params_of(code)})

    def test_finding_checks_params(self):
        f = finding(
            "foreign_lang_skipped",
            page_ref="standalone-fr",
            ref="standalone-fr",
            lang="fr",
            url="/standalone-fr.php",
        )
        self.assertEqual(f.severity, "info")
        self.assertEqual(f.params["lang"], "fr")
        self.assertEqual(f.url, "/standalone-fr.php")
        with self.assertRaises(ValueError):
            finding("credits", file="README.md")
        with self.assertRaises(ValueError):
            finding("credits", file="README.md", text="t", extra="y")
        with self.assertRaises(KeyError):
            finding("no_such_code")

    def test_code_is_positional_only(self):
        f = finding(
            "php_removed",
            page_ref="home",
            ref="home",
            line=3,
            context="text",
            code="echo 1;",
            bytes=7,
        )
        self.assertEqual(f.code, "php_removed")
        self.assertEqual(f.params["code"], "echo 1;")
        self.assertEqual(
            render("php_removed", f.params),
            "PHP removed from home at line 3 (text): echo 1;; "
            "7 HTML bytes removed",
        )

    def test_media_too_large_is_a_warning(self):
        f = finding("media_too_large", relpath="big.mp4", limit="20 MiB")
        self.assertEqual(f.severity, "warning")
        self.assertEqual(
            render("media_too_large", f.params),
            "Media big.mp4 skipped: larger than the 20 MiB per-file limit",
        )

    def test_detail_truncated_and_values_stringified(self):
        f = finding("menu_capped", limit=200, detail="d" * 400)
        self.assertEqual(f.params, {"limit": "200"})
        self.assertEqual(len(f.detail), 300)

    def test_render(self):
        self.assertEqual(
            render("menu_capped", {"limit": "200"}),
            "Menu import stopped after 200 entries",
        )
        translated = render(
            "menu_capped",
            {"limit": "7"},
            translate=lambda text: text.replace("Menu import", "Import"),
        )
        self.assertEqual(translated, "Import stopped after 7 entries")


class TestMessages(MessagesCases, unittest.TestCase):
    pass
