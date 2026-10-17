# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.tests import tagged
from odoo.tools import sql

from .common import StudioCase


@tagged("post_install", "-at_install")
class TestInstall(StudioCase):
    """erplibre_studio without code_generator: it installs on a server
    started without --dev and leaves the core constraint on the names of
    the custom fields."""

    def test_no_dependency_on_code_generator(self):
        closure = self.env["ir.module.module.dependency"].all_dependencies(
            ["erplibre_studio"]
        )
        names = set(closure) | {n for deps in closure.values() for n in deps}
        self.assertIn("erplibre_developer", names)
        self.assertNotIn("code_generator", names)
        self.assertNotIn("erplibre_studio_generate", names)

    def test_custom_field_names_keep_their_constraint(self):
        """ir_model_fields_name_manual_field is there unless code_generator,
        which drops it, is installed."""
        generator = self.env["ir.module.module"].search(
            [("name", "=", "code_generator"), ("state", "=", "installed")]
        )
        if generator:
            self.skipTest("code_generator drops the constraint")
        definition = sql.constraint_definition(
            self.env.cr, "ir_model_fields", "ir_model_fields_name_manual_field"
        )
        self.assertTrue(definition)

    def test_form_without_generation(self):
        """The form of the project: no generation button, a hint that names
        the module of the generation."""
        view = self.env.ref("erplibre_studio.erplibre_studio_project_view_form")
        arch = etree.fromstring(view.arch)
        self.assertFalse(arch.xpath("//button[@name='action_generate']"))
        self.assertFalse(arch.xpath("//button[@name='action_install_module']"))
        hint = arch.xpath("//div[@name='generation_hint']")
        self.assertEqual(len(hint), 1)
        text = "".join(hint[0].itertext())
        self.assertIn("ERPLibre studio generate", text)
        self.assertIn("--dev", text)

    def test_editor_payload_names_the_state(self):
        project = self.make_project()
        data = self.Editor.with_context(lang="en_US").get_editor_data(
            "res.partner", False, "list", project.id
        )
        self.assertEqual(data["project"]["state"], "draft")
        self.assertEqual(data["project"]["state_label"], "Draft")
