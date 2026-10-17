# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.arch import ArchError
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .. import version as studio_version


@tagged("post_install", "-at_install")
class TestProjectGenerate(StudioCase):
    """The project fields and checks of the generation."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_guard")
        self.op(
            self.project,
            self.list,
            type="hide",
            target="//field[@name='city']",
            value=True,
        )

    def test_default_version(self):
        self.assertEqual(self.project.version, "18.0.1.0.0")

    def test_manifest_text_and_version(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.make_project("studio_test_quote", name="Contact's fields")
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.make_project("studio_test_version", version="18.0.1.0")
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.make_project("studio_test_series", version="17.0.1.0.0")

    def test_destination_choices(self):
        Project = type(self.Project)
        choices = [
            (
                "odoo18.0/addons/Example_addons",
                "odoo18.0/addons/Example_addons",
            )
        ]
        Param = self.env["ir.config_parameter"].sudo()
        with patch.object(Project, "_destination_choices", lambda self_: choices):
            Param.set_param("erplibre_studio.default_destination", choices[0][0])
            self.assertEqual(
                self.make_project("studio_test_dest").destination,
                choices[0][0],
            )
            Param.set_param("erplibre_studio.default_destination", "elsewhere")
            self.assertFalse(self.make_project("studio_test_dest_2").destination)

    def test_field_texts_reach_python_safely(self):
        """A new field's label and tooltip go into a quoted Python string
        of the generated module: no quote, backslash nor line break."""
        project = self.make_project()
        refused = [
            {"field_description": "Path\\"},
            {
                "field_description": '\\\'+str(__import__("os").getpid())+"',
                "help": '")#',
            },
            {"field_description": "It's"},
            {"field_description": "Note", "help": "two\nlines"},
        ]
        for field in refused:
            with self.subTest(field=field), self.assertRaises(UserError):
                with self.env.cr.savepoint():
                    self.op(
                        project,
                        self.form,
                        type="add_field",
                        target="//field[@name='vat']",
                        field={"ttype": "char", **field},
                    )
        self.assertFalse(project.change_ids)
        self.op(
            project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        # The relabel of a field of the project goes through the same check.
        for otype in ("relabel", "help"):
            with self.subTest(otype=otype), self.assertRaises(UserError):
                with self.env.cr.savepoint():
                    self.op(
                        project,
                        self.form,
                        type=otype,
                        target="//field[@name='x_nickname']",
                        value="a\\b",
                    )

    def test_disk_writes_need_the_odoo_conf_flag(self):
        self.project.action_apply()
        with self.server_actions(flag=False):
            with self.assertRaises(UserError):
                self.project.action_generate()
            with self.assertRaises(UserError):
                self.project.action_install_module()
        self.assertFalse(self.project.generation_count)

    def test_generation_needs_an_applied_project(self):
        with self.server_actions():
            with self.assertRaises(UserError):
                self.project.action_generate()
            self.project.action_apply()
            # No destination chosen.
            with self.assertRaises(UserError):
                self.project.action_generate()

    def test_next_version(self):
        """The version asked is kept when above the last generated one;
        versions compare as integers, part by part."""
        cases = [
            ("18.0.1.0.0", False, "18.0.1.0.0"),
            ("18.0.1.0.0", "18.0.1.0.0", "18.0.1.0.1"),
            ("18.0.2.0.0", "18.0.1.0.4", "18.0.2.0.0"),
            ("18.0.1.0.10", "18.0.1.0.9", "18.0.1.0.10"),
            ("18.0.1.0.2", "18.0.1.0.10", "18.0.1.0.11"),
        ]
        for requested, generated, expected in cases:
            with self.subTest(requested=requested, generated=generated):
                self.assertEqual(
                    studio_version.next_version(requested, generated), expected
                )
        with self.assertRaises(ArchError) as caught:
            studio_version.next_version("18.0.x", "18.0.1.0.0")
        self.assertEqual(caught.exception.code, "invalid_version")
        self.assertEqual(caught.exception.params, {"version": "18.0.x"})

    def test_versions(self):
        self.assertEqual(studio_version.bump_version("18.0.1.0.9"), "18.0.1.0.10")
        self.assertTrue(studio_version.valid_version("18.0.1.2.3", "18.0"))
        self.assertFalse(studio_version.valid_version("17.0.1.2.3", "18.0"))
        self.assertFalse(studio_version.valid_version("18.0.1.0", "18.0"))

    def test_invalid_version_in_the_user_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env["ir.module.module"].search(
            [("name", "=", "erplibre_studio_generate")]
        )._update_translations(["fr_FR"])
        project = self.project.with_context(lang="fr_FR")
        message = project._arch_message(
            ArchError("Invalid version 18.0.x.", "invalid_version", version="18.0.x")
        )
        self.assertEqual(message, "Version invalide 18.0.x.")

    def test_generation_needs_the_developer_mode(self):
        self.project.action_apply()
        self._debug = False
        for action in ("action_generate", "action_install_module"):
            with self.subTest(action=action), self.assertRaises(UserError):
                getattr(self.project, action)()

    def test_generation_fields_are_managed(self):
        admin = new_test_user(
            self.env,
            login="erplibre_studio_generate_admin",
            groups="base.group_user,base.group_system",
        )
        project = self.project.with_user(admin)
        forged = [
            {"generated_path": "/tmp/elsewhere"},
            {"generation_count": 1},
            {"generated_snapshot": "[]"},
            {"code_generator_id": False},
        ]
        for vals in forged:
            with self.subTest(vals=vals), self.assertRaises(UserError):
                project.write(vals)
        with self.assertRaises(UserError):
            self.Project.with_user(admin).create(
                {
                    "name": "Forged",
                    "module_name": "studio_test_forged",
                    "generation_count": 1,
                }
            )
        project.write({"name": "Renamed", "version": "18.0.1.2.0"})
        self.assertEqual(project.version, "18.0.1.2.0")

    def test_texts_recorded_before_this_module(self):
        """A text recorded while this module was not installed went through
        no check: the generation refuses it."""
        self.project.action_apply()
        self.env.cr.execute(
            "UPDATE erplibre_studio_project SET summary = %s WHERE id = %s",
            ("It's", self.project.id),
        )
        self.project.invalidate_recordset()
        with self.server_actions(), self.assertRaises(UserError):
            self.project.action_generate()
        self.project.summary = "Contacts"
        change = self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        payload = change._payload()
        payload["field"]["help"] = 'a"b'
        change._set_payload(payload)
        self.project.action_apply()
        with self.server_actions(), self.assertRaises(UserError):
            self.project.action_generate()
        self.assertFalse(self.project.generation_count)

    def test_form_shows_the_generation(self):
        arch = etree.fromstring(
            self.Project.get_view(
                self.env.ref("erplibre_studio.erplibre_studio_project_view_form").id,
                "form",
            )["arch"]
        )
        names = arch.xpath("//header/button/@name")
        self.assertIn("action_generate", names)
        self.assertIn("action_install_module", names)
        self.assertFalse(arch.xpath("//div[@name='generation_hint']"))
        for name in ("version", "destination", "generation_log"):
            self.assertTrue(arch.xpath(f"//field[@name='{name}']"), name)

    def test_editor_payload_shows_the_version(self):
        data = self.Editor.with_context(lang="en_US").get_editor_data(
            "res.partner", False, "list", self.project.id
        )
        self.assertEqual(data["project"]["version"], "18.0.1.0.0")
        self.assertEqual(
            dict(self.Project._fields["state"].selection)["generated"], "Generated"
        )
