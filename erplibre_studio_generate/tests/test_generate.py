# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

MODULE = "studio_test_generate"


@tagged("post_install", "-at_install")
class TestGenerate(StudioCase):
    """Generation through code_generator into a temporary directory."""

    def setUp(self):
        super().setUp()
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(MODULE, destination=self.destination)
        self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={
                "ttype": "selection",
                "field_description": "Partner level",
                "selection": [["gold", "Gold"], ["silver", "Silver"]],
            },
        )
        self.op(
            self.project,
            self.list,
            type="add_field",
            target="//field[@name='email']",
            position="after",
            field={
                "ttype": "many2one",
                "field_description": "Sponsor",
                "relation": "res.users",
            },
        )
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='phone']",
            value="Telephone",
        )
        self.op(
            self.project,
            self.list,
            type="move",
            source="//field[@name='city']",
            target="//field[@name='complete_name']",
            position="after",
        )
        self.op(
            self.project,
            self.form,
            type="hide",
            target="//field[@name='website']",
            value=True,
        )
        self.op(
            self.project,
            self.form,
            type="required",
            target="//field[@name='x_partner_level']",
            value=True,
        )
        self.project.action_apply()

    def read(self, *parts):
        with open(
            os.path.join(self.destination, MODULE, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_generate_then_regenerate(self):
        partner_model = self.env["ir.model"]._get("res.partner")
        with self.server_actions():
            self.project.action_generate()
        target = os.path.join(self.destination, MODULE)
        self.assertEqual(self.project.generated_path, target)
        self.assertEqual(self.project.state, "generated")
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertEqual(manifest["version"], "18.0.1.0.0")
        self.assertEqual(manifest["depends"], ["base"])
        self.assertEqual(manifest["license"], "AGPL-3")
        self.assertIn("views/erplibre_studio_views.xml", manifest["data"])
        self.assertFalse(os.path.exists(os.path.join(target, "security")))
        # No new model: no hook, not an application.
        self.assertNotIn("pre_init_hook", manifest)
        self.assertNotIn("application", manifest)
        self.assertFalse(os.path.exists(os.path.join(target, "hooks.py")))

        model = self.read("models", "res_partner.py")
        compile(model, "res_partner.py", "exec")
        self.assertIn('_inherit = "res.partner"', model)
        self.assertIn("from odoo import fields, models\n", model)
        self.assertNotIn("_name =", model)
        for absent in (
            "_order",
            "_rec_name",
            "_sql_constraints",
            "x_nickname",
        ):
            self.assertNotIn(absent, model)
        self.assertIn("x_partner_level = fields.Selection(", model)
        self.assertIn('("gold", "Gold")', model)
        # Required on the view node, never NOT NULL on the table.
        self.assertNotIn("required", model)
        self.assertIn("x_sponsor = fields.Many2one(", model)
        self.assertIn('comodel_name="res.users"', model)

        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        records = views.findall("record")
        self.assertEqual(
            sorted(r.get("id") for r in records),
            ["base_view_partner_form_studio", "base_view_partner_tree_studio"],
        )
        for record in records:
            self.assertEqual(record.get("model"), "ir.ui.view")
            self.assertEqual(record.find("field[@name='priority']").text, "99")
            self.assertIn(
                record.find("field[@name='inherit_id']").get("ref"),
                ("base.view_partner_form", "base.view_partner_tree"),
            )
        list_record = views.find("record[@id='base_view_partner_tree_studio']")
        self.assertTrue(list_record.xpath(".//xpath[@position='move']"))
        self.assertIn("Telephone", etree.tostring(list_record, encoding="unicode"))
        form_record = views.find("record[@id='base_view_partner_form_studio']")
        self.assertTrue(
            form_record.xpath(".//attribute[@name='required'][text()='True']")
        )
        self.assertIn("ERPLibre studio", self.read("readme", "DESCRIPTION.md"))
        self.assertTrue(
            os.path.isfile(os.path.join(target, "static", "description", "icon.png"))
        )

        # The model went back to its owner: nobody.
        self.assertFalse(partner_model.m2o_module)
        self.assertFalse(partner_model.inherit_model_ids)
        log = self.project.generation_log
        self.assertIn("version: 18.0.1.0.0", log)
        self.assertIn("models/res_partner.py", log)

        # A new change, applied and regenerated: same directory, next version.
        self.op(
            self.project,
            self.list,
            type="optional",
            target="//field[@name='phone']",
            value="hide",
        )
        with self.server_actions(), self.assertRaises(UserError):
            self.project.action_generate()
        self.project.action_apply()
        with open(os.path.join(target, "stale.txt"), "w") as fh:
            fh.write("removed by the regeneration")
        with self.server_actions():
            self.project.action_generate()
        self.assertEqual(self.project.version, "18.0.1.0.1")
        self.assertEqual(
            ast.literal_eval(self.read("__manifest__.py"))["version"],
            "18.0.1.0.1",
        )
        self.assertFalse(os.path.exists(os.path.join(target, "stale.txt")))
        self.assertIn(
            'name="optional">hide<',
            self.read("views", "erplibre_studio_views.xml"),
        )
        self.assertEqual(os.listdir(self.destination), [MODULE])
        with self.assertRaises(UserError):
            self.project.module_name = "studio_test_renamed"

    def test_foreign_directory_is_never_replaced(self):
        os.makedirs(os.path.join(self.destination, MODULE))
        with self.server_actions(), self.assertRaises(UserError):
            self.project.action_generate()
        self.assertEqual(os.listdir(os.path.join(self.destination, MODULE)), [])

    def test_writer_temporary_directory_is_removed(self):
        made = []
        real = tempfile.mkdtemp

        def mkdtemp(*args, **kwargs):
            made.append(real(*args, **kwargs))
            return made[-1]

        with self.server_actions(), patch("tempfile.mkdtemp", mkdtemp):
            self.project.action_generate()
        self.assertTrue(made)
        self.assertFalse([path for path in made if os.path.exists(path)])

    def test_version_typed_by_the_user_is_kept(self):
        with self.server_actions():
            self.project.action_generate()
            self.assertEqual(self.project.version, "18.0.1.0.0")
            self.project.version = "18.0.2.0.0"
            self.project.action_generate()
            self.assertEqual(self.project.version, "18.0.2.0.0")
            self.assertEqual(
                ast.literal_eval(self.read("__manifest__.py"))["version"],
                "18.0.2.0.0",
            )
            # Not above the last generation: the patch number moves up.
            self.project.version = "18.0.1.5.0"
            self.project.action_generate()
        self.assertEqual(self.project.version, "18.0.2.0.1")
        self.assertEqual(self.project.generated_version, "18.0.2.0.1")

    def test_marker_names_the_project(self):
        with self.server_actions():
            self.project.action_generate()
        target = os.path.join(self.destination, MODULE)
        self.assertTrue(self.project._is_own_directory(target))
        other = self.make_project("studio_test_marker_other")
        self.assertFalse(other._is_own_directory(target))
        with open(os.path.join(target, ".erplibre_studio")) as fh:
            text = fh.read()
        # A digest: no database, project nor module name in clear.
        self.assertNotIn(MODULE, text)
        self.assertEqual(len(text.strip()), 64)

    def test_forged_generation_state_never_removes_a_folder(self):
        """Even with generated_path and generation_count forged in the
        database, a folder without the marker of the project stays."""
        foreign = os.path.join(self.destination, MODULE)
        os.makedirs(foreign)
        with open(os.path.join(foreign, "work.py"), "w") as fh:
            fh.write("# uncommitted work\n")
        admin = new_test_user(
            self.env,
            login="erplibre_studio_generate_forger",
            groups="base.group_user,base.group_system",
        )
        with self.assertRaises(UserError):
            self.project.with_user(admin).write(
                {"generated_path": foreign, "generation_count": 1}
            )
        self.env.cr.execute(
            "UPDATE erplibre_studio_project SET generated_path = %s, "
            "generation_count = 1 WHERE id = %s",
            (foreign, self.project.id),
        )
        self.project.invalidate_recordset()
        with self.server_actions(), self.assertRaises(UserError):
            self.project.with_user(admin).action_generate()
        self.assertEqual(os.listdir(foreign), ["work.py"])
        # A link to a directory is never replaced either.
        shutil.rmtree(foreign)
        elsewhere = tempfile.mkdtemp(prefix="erplibre_studio_test_link_")
        self.addCleanup(shutil.rmtree, elsewhere, True)
        os.symlink(elsewhere, foreign)
        with self.server_actions(), self.assertRaises(UserError):
            self.project.action_generate()
        self.assertTrue(os.path.islink(foreign))

    def test_field_edit_after_the_module_is_installed(self):
        """Once installed, the generated module owns the field row: Apply
        leaves it and says so, the next generation writes the new
        definition from the project."""
        field = self.env["ir.model.fields"]._get("res.partner", "x_partner_level")
        self.env.cr.execute(
            "UPDATE ir_model_fields SET state = 'base' WHERE id = %s", (field.id,)
        )
        field.invalidate_recordset()
        self.env["ir.model.data"].create(
            {
                "module": MODULE,
                "name": "field_res_partner__x_partner_level",
                "model": "ir.model.fields",
                "res_id": field.id,
            }
        )
        self.op(
            self.project,
            self.form,
            type="relabel",
            target="//field[@name='x_partner_level']",
            value="Level",
        )
        self.op(
            self.project,
            self.form,
            type="help",
            target="//field[@name='x_partner_level']",
            value="Customer tier",
        )
        result = self.project.action_apply()
        self.assertEqual(result["tag"], "display_notification")
        self.assertIn("res.partner.x_partner_level", result["params"]["message"])
        self.assertEqual(field.field_description, "Partner level")
        self.assertEqual(self.project.state, "applied")
        data = self.Editor.project_action(
            self.project.id, "action_apply", "res.partner", False, "form"
        )
        self.assertIn("x_partner_level", data["notice"])
        with self.server_actions():
            self.project.action_generate()
        model = self.read("models", "res_partner.py")
        self.assertIn('string="Level"', model)
        self.assertIn('help="Customer tier"', model)
        self.assertNotIn("Partner level", model)

    def test_fields_applied_before_this_module(self):
        """Apply leaves the whitelist flag of code_generator alone: the
        generation exports the fields of the project, and only them."""
        fields = self.project.field_ids
        self.assertEqual(len(fields), 2)
        self.assertFalse(any(fields.mapped("is_show_whitelist_model_inherit")))
        with self.server_actions():
            self.project.action_generate()
        model = self.read("models", "res_partner.py")
        compile(model, "res_partner.py", "exec")
        self.assertIn("x_partner_level = fields.Selection(", model)
        self.assertIn("x_sponsor = fields.Many2one(", model)
        self.assertEqual(model.count(" = fields."), 2)

    def test_whitelist_flag_on_the_model(self):
        """A flagged field on the model, of this project or of another one,
        never drops an unflagged field of the project from the module: the
        writer, on a model the module extends, otherwise exports the
        flagged fields only."""
        other = self.make_project("studio_test_generate_other")
        self.op(
            other,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={"ttype": "char", "field_description": "Tier"},
        )
        other.action_apply()
        flagged = self.env["ir.model.fields"].search(
            [
                ("model", "=", "res.partner"),
                ("name", "in", ["x_partner_level", "x_tier"]),
            ]
        )
        self.assertEqual(len(flagged), 2)
        self.env.cr.execute(
            "UPDATE ir_model_fields SET is_show_whitelist_model_inherit = true "
            "WHERE id IN %s",
            (tuple(flagged.ids),),
        )
        flagged.invalidate_recordset()
        with self.server_actions():
            self.project.action_generate()
        model = self.read("models", "res_partner.py")
        compile(model, "res_partner.py", "exec")
        self.assertIn("x_partner_level = fields.Selection(", model)
        self.assertIn("x_sponsor = fields.Many2one(", model)
        self.assertNotIn("x_tier", model)
        self.assertEqual(model.count(" = fields."), 2)
        self.assertIn("x_sponsor", self.read("views", "erplibre_studio_views.xml"))
