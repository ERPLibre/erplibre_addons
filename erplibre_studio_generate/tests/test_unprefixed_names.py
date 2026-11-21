# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import shutil
import tempfile
from unittest.mock import patch

from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.addons.erplibre_studio_generate.models.ir_model_fields import (
    drop_manual_name_constraint,
)
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import sql

MODULE = "studio_test_unprefixed"
PARTNER = "res.partner"
CONSTRAINT = "ir_model_fields_name_manual_field"
IR_MODEL_LOGGER = "odoo.addons.base.models.ir_model"
LOADER_LOGGER = "odoo.addons.erplibre_studio_generate.models.ir_model_fields"


@tagged("post_install", "-at_install")
class TestUnprefixedNames(StudioCase):
    """A field without x_ on a development database: the rule the editor
    shows, the mark Apply writes, the registry that loads the marked rows
    only, the generation, and the uninstall that waits for the fields."""

    # The rule this module reads from the database.
    production_rule_pinned = False

    def setUp(self):
        super().setUp()
        self.Fields = self.env["ir.model.fields"].sudo()
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(
            MODULE, name="Studio unprefixed", destination=self.destination
        )
        self.change = self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={"ttype": "char", "field_description": "Texte", "name": "texte"},
        )

    def manual_row(self, name, **vals):
        """A custom field ``name`` of res.partner, created as Apply creates
        one, without the mark unless ``vals`` gives it. Deleted again
        before the registry of the test is reset, which would log it."""
        field = self.Fields.create(
            {
                "name": name,
                "model": PARTNER,
                "model_id": self.env["ir.model"]._get_id(PARTNER),
                "ttype": "char",
                "field_description": name,
                "state": "manual",
                **vals,
            }
        )
        self.addCleanup(self.forget, field.id)
        return field

    def forget(self, field_id):
        self.env.cr.execute("DELETE FROM ir_model_fields WHERE id = %s", [field_id])
        self.registry.clear_cache()

    def test_rule_follows_the_constraint(self):
        # code_generator drops the constraint, a module installed after it
        # adds it back, the installation of this module drops it again.
        self.assertFalse(
            sql.constraint_definition(self.env.cr, "ir_model_fields", CONSTRAINT)
        )
        rule = self.Editor.get_editor_data(
            PARTNER, self.form.id, "form", self.project.id
        )["field_name_rule"]
        self.assertEqual(
            (rule["mode"], rule["prefix_required"]), ("development", False)
        )
        self.assertIn("code_generator", rule["text"])
        with patch.object(
            sql, "constraint_definition", lambda *args: "CHECK (name LIKE 'x\\_%')"
        ):
            rule = self.Editor.get_editor_data(
                PARTNER, self.form.id, "form", self.project.id
            )["field_name_rule"]
        self.assertEqual((rule["mode"], rule["prefix_required"]), ("production", True))

    def test_hook_drops_the_constraint(self):
        sql.add_constraint(
            self.env.cr,
            "ir_model_fields",
            CONSTRAINT,
            "CHECK (state != 'manual' OR name LIKE 'x\\_%')",
        )
        self.assertEqual(
            self.Editor.get_editor_data(PARTNER, self.form.id, "form", self.project.id)[
                "field_name_rule"
            ]["mode"],
            "production",
        )
        drop_manual_name_constraint(self.env.cr)
        self.assertFalse(
            sql.constraint_definition(self.env.cr, "ir_model_fields", CONSTRAINT)
        )
        # Nothing to drop: no error.
        drop_manual_name_constraint(self.env.cr)

    def test_loading_drops_the_constraint_again(self):
        # An update of base sets base up alone and adds the constraint
        # back; the hook that ends each loading of the modules drops it.
        sql.add_constraint(
            self.env.cr,
            "ir_model_fields",
            CONSTRAINT,
            "CHECK (state != 'manual' OR name LIKE 'x\\_%')",
        )
        self.env["ir.model.fields"]._register_hook()
        self.assertFalse(
            sql.constraint_definition(self.env.cr, "ir_model_fields", CONSTRAINT)
        )
        self.assertEqual(self.project._studio_field_name_rule()["mode"], "development")

    def test_apply_loads_the_field(self):
        self.project.action_apply()
        field = self.Fields._get(PARTNER, "texte")
        self.assertEqual(field.state, "manual")
        self.assertTrue(field.erplibre_studio_unprefixed)
        self.assertIn(field, self.project.field_ids)
        self.assertIn("texte", self.env[PARTNER]._fields)
        # res.users inherits res.partner by delegation: it shows the field.
        self.assertIn("texte", self.env["res.users"]._fields)
        self.assertTrue(sql.column_exists(self.env.cr, "res_partner", "texte"))
        partner = self.env[PARTNER].create({"name": "Unprefixed", "texte": "un"})
        partner.write({"texte": "deux"})
        partner.invalidate_recordset()
        self.assertEqual(partner.read(["texte"])[0]["texte"], "deux")
        for view in self.project.studio_view_ids:
            view._check_xml()
        arch = self.view_arch(self.form)
        self.assertEqual(len(arch.xpath("//field[@name='texte']")), 1)
        # A new setup of the registry reads the rows: the load path.
        self.registry.setup_models(self.env.cr)
        self.assertIn("texte", self.env[PARTNER]._fields)
        self.assertEqual(self.env[PARTNER].browse(partner.id).texte, "deux")

    def test_unmarked_row_is_not_loaded(self):
        with self.assertLogs(IR_MODEL_LOGGER, "ERROR") as logs:
            self.manual_row("texte_brut")
        self.assertIn("Failed to load field res.partner.texte_brut", logs.output[0])
        self.assertNotIn("texte_brut", self.env[PARTNER]._fields)
        self.assertFalse(sql.column_exists(self.env.cr, "res_partner", "texte_brut"))

    def test_marked_reserved_name_is_not_loaded(self):
        with (
            self.assertLogs(IR_MODEL_LOGGER, "ERROR") as errors,
            self.assertLogs(LOADER_LOGGER, "WARNING") as warnings,
        ):
            self.manual_row("write", erplibre_studio_unprefixed=True)
        self.assertIn("res.partner.write not loaded: reserved", warnings.output[0])
        self.assertIn("Failed to load field res.partner.write", errors.output[0])
        self.assertNotIn("write", self.env[PARTNER]._fields)
        self.assertTrue(callable(type(self.env[PARTNER]).write))

    def test_method_of_an_inheriting_model_is_not_loaded(self):
        # res.users copies the fields of res.partner (``_inherits``): a
        # field « authenticate » would replace its login method.
        for name in ("authenticate", "check"):
            with self.subTest(name=name):
                with (
                    self.assertLogs(IR_MODEL_LOGGER, "ERROR"),
                    self.assertLogs(LOADER_LOGGER, "WARNING") as warnings,
                ):
                    self.manual_row(name, erplibre_studio_unprefixed=True)
                # The row of the name before is still there: both log.
                self.assertIn(
                    f"res.partner.{name} not loaded: reserved",
                    "\n".join(warnings.output),
                )
                self.assertNotIn(name, self.env[PARTNER]._fields)
                self.assertNotIn(name, self.env["res.users"]._fields)
                self.assertTrue(callable(getattr(type(self.env["res.users"]), name)))
        self.assertEqual(
            self.project._studio_field_name_problem(PARTNER, "authenticate")["code"],
            "reserved",
        )

    def test_field_a_module_defines_no_longer_loads(self):
        # A row of a field of base marked as a studio field: the field of
        # the module stays, the row is not loaded over it.
        comment = self.Fields._get(PARTNER, "comment")
        self.env.cr.execute(
            "UPDATE ir_model_fields SET state = 'manual', "
            "erplibre_studio_unprefixed = TRUE WHERE id = %s",
            [comment.id],
        )
        # Cleanups run last added first: the row is restored, then the
        # cache that holds it is cleared.
        self.addCleanup(self.registry.clear_cache)
        self.addCleanup(
            self.env.cr.execute,
            "UPDATE ir_model_fields SET state = 'base', "
            "erplibre_studio_unprefixed = NULL WHERE id = %s",
            [comment.id],
        )
        self.registry.clear_cache()
        with self.assertLogs(LOADER_LOGGER, "WARNING") as logs:
            self.registry.setup_models(self.env.cr)
        self.assertIn(
            "res.partner.comment is defined by the module base now", logs.output[0]
        )
        self.assertEqual(self.env[PARTNER]._fields["comment"].type, "html")

    def test_uninstall_waits_for_the_fields(self):
        self.project.action_apply()
        Module = self.env["ir.module.module"]
        modules = {
            name: Module.search([("name", "=", name)])
            for name in ("erplibre_studio_generate", "code_generator")
        }
        for name, module in modules.items():
            with self.subTest(module=name):
                with self.assertRaises(UserError) as caught:
                    module.button_uninstall()
                message = str(caught.exception)
                self.assertIn("Studio unprefixed", message)
                self.assertIn("res.partner.texte", message)
                module.invalidate_recordset(["state"])
                self.assertEqual(module.state, "installed")
        self.project.action_revert()
        self.assertFalse(self.Fields._get(PARTNER, "texte"))
        self.assertIsNone(Module._studio_unprefixed_refusal())

    def test_generate_writes_the_name(self):
        self.project.action_apply()
        with self.server_actions():
            self.project.action_generate()
        target = os.path.join(self.destination, MODULE)
        with open(
            os.path.join(target, "models", "res_partner.py"), encoding="utf-8"
        ) as fh:
            model = fh.read()
        # Run as Odoo imports it, not only compiled: a name of the class
        # body that hid an import would fail here.
        exec(  # pylint: disable=exec-used
            compile(model, "res_partner.py", "exec"),
            {"__name__": f"odoo.addons.{MODULE}.models.res_partner"},
        )
        self.assertIn("texte = fields.Char(", model)
        with open(
            os.path.join(target, "views", "erplibre_studio_views.xml"), encoding="utf-8"
        ) as fh:
            self.assertIn('name="texte"', fh.read())

    def test_generation_refuses_a_name_the_class_holds(self):
        payload = self.change._payload()
        payload["field_name"] = "write"
        self.change._set_payload(payload)
        with self.assertRaises(UserError) as caught:
            self.project._check_generation_field_names()
        self.assertIn("write", str(caught.exception))
        payload["field_name"] = "texte"
        self.change._set_payload(payload)
        self.project._check_generation_field_names()

    def test_names_the_generated_file_imports_are_reserved(self):
        # « fields = fields.Char() » in the class body hides the import
        # for the fields that follow it.
        for name in ("fields", "models", "api"):
            with self.subTest(name=name):
                problem = self.project._studio_field_name_problem(PARTNER, name)
                self.assertEqual(problem["code"], "reserved")
        payload = self.change._payload()
        payload["field_name"] = "fields"
        self.change._set_payload(payload)
        with self.assertRaisesRegex(UserError, "fields"):
            self.project._check_generation_field_names()
