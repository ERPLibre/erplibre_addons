# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The reading of the image configuration, without the database."""

import json
import os
import tempfile

from odoo.tests import BaseCase, tagged

from .. import suggestion


@tagged("post_install", "-at_install")
class TestSuggestion(BaseCase):
    def test_image_name(self):
        self.assertEqual(suggestion.image_name("1.0"), "odoo1.0_base")

    def test_modules_of_an_image_and_its_bases(self):
        config = {
            "odoo1.0_base": {
                "base": "",
                "image_list": [{"module": ["mod_a", "mod_b"]}],
            },
            "odoo1.0_site": {
                "base": "odoo1.0_base",
                "image_list": [
                    {"module": ["mod_b", "mod_c"], "theme": "mod_theme"},
                    # a derived image « odoo1.0_site_extra »: not in the image
                    {"pkg_name": "extra", "module": ["mod_extra"]},
                ],
            },
        }
        self.assertEqual(
            suggestion.image_modules(config, "odoo1.0_site"),
            ["mod_a", "mod_b", "mod_c", "mod_theme"],
        )
        self.assertEqual(
            suggestion.image_modules(config, "odoo1.0_base"),
            ["mod_a", "mod_b"],
        )

    def test_entries_after_a_derived_image_belong_to_the_image(self):
        """An entry without pkg_name dumps the image again, with every
        entry installed before it."""
        config = {
            "odoo1.0_base": {
                "image_list": [
                    {"module": ["mod_a"]},
                    {"pkg_name": "x", "module": ["mod_x"]},
                    {"module": ["mod_b"]},
                ]
            }
        }
        self.assertEqual(
            suggestion.image_modules(config, "odoo1.0_base"),
            ["mod_a", "mod_x", "mod_b"],
        )

    def test_unknown_image_and_cycle(self):
        with self.assertRaises(suggestion.SuggestionError) as caught:
            suggestion.image_modules({}, "odoo1.0_base")
        self.assertEqual(caught.exception.code, "unknown_image")
        config = {
            "odoo1.0_a": {"base": "odoo1.0_b", "image_list": []},
            "odoo1.0_b": {"base": "odoo1.0_a", "image_list": []},
        }
        with self.assertRaises(suggestion.SuggestionError) as caught:
            suggestion.image_modules(config, "odoo1.0_a")
        self.assertEqual(caught.exception.code, "cycle")

    def test_read_config(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(suggestion.SuggestionError) as caught:
                suggestion.read_config(root)
            self.assertEqual(caught.exception.code, "missing")
            path = os.path.join(root, suggestion.CONFIG_FILE)
            os.makedirs(os.path.dirname(path))
            for content in ("{not json", "[]"):
                with open(path, "w") as fh:
                    fh.write(content)
                with self.assertRaises(suggestion.SuggestionError) as caught:
                    suggestion.read_config(root)
                self.assertEqual(caught.exception.code, "unreadable")
            with open(path, "w") as fh:
                json.dump({"odoo1.0_base": {}}, fh)
            self.assertEqual(
                suggestion.read_config(root), {"odoo1.0_base": {}}
            )
