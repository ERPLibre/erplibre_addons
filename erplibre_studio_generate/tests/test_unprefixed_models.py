# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import os
import shutil
import tempfile
from unittest.mock import patch

from odoo.addons.base.models.ir_model import IrModel as BaseIrModel
from odoo.addons.erplibre_studio_generate.models import (
    erplibre_studio_project as project_module,
)
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import sql

MODULE = "studio_test_unprefixed_models"
BOOK = "studio_demo.book"
PROJECT_MODULE = "odoo.addons.erplibre_studio_generate.models.erplibre_studio_project"
LOADER_LOGGER = "odoo.addons.erplibre_studio_generate.models.ir_model"


@tagged("post_install", "-at_install")
class TestUnprefixedModels(StudioCase):
    """A model without x_ on a development database: the rule the editor
    shows, the checks of the name, the mark Apply writes, the core rule
    kept for the rows without it, the take-over by a module of the same
    name, the generation, and the uninstall that waits for the models."""

    # The rule this module reads from the database.
    production_rule_pinned = False

    def setUp(self):
        super().setUp()
        self.IrModel = self.env["ir.model"].sudo()
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(
            MODULE, name="Studio unprefixed models", destination=self.destination
        )

    def book_line(self):
        return self.make_model(self.project, "Studio demo book", model=BOOK)

    def status(self, name, line=None):
        return self.project._studio_model_name_status(name, line)

    def test_rule_follows_the_constraint(self):
        rule = self.project._studio_model_name_rule()
        field_rule = self.project._studio_field_name_rule()
        self.assertEqual(
            (rule["mode"], rule["prefix_required"]), ("development", False)
        )
        self.assertEqual(rule["label"], field_rule["label"])
        self.assertIn("code_generator", rule["text"])
        data = self.Editor.get_editor_data(
            "res.partner", self.form.id, "form", self.project.id
        )
        self.assertEqual(data["model_name_rule"], rule)
        with patch.object(
            sql, "constraint_definition", lambda *args: "CHECK (name LIKE 'x\\_%')"
        ):
            rule = self.project._studio_model_name_rule()
            self.assertEqual(
                (rule["mode"], rule["prefix_required"]), ("production", True)
            )
            self.assertTrue(self.project._studio_field_name_rule()["prefix_required"])

    def test_check_model_name(self):
        result = self.Editor.check_model_name(self.project.id, BOOK)
        self.assertEqual(result["status"], "available")
        self.assertFalse(result["rule"]["prefix_required"])
        self.assertEqual(self.status("decimal.precision")["owner"]["kind"], "model")
        self.assertEqual(
            self.Editor.check_model_name(self.project.id, "decimal.precision")[
                "status"
            ],
            "taken",
        )
        for name in ("class", "res.studio_demo", "erplibre.studio_demo"):
            with self.subTest(name=name):
                result = self.Editor.check_model_name(self.project.id, name)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(self.status(name)["code"], "reserved")
        line = self.book_line()
        # A dot and an underscore give the same table.
        owner = self.status("studio_demo_book")["owner"]
        self.assertEqual(
            (owner["kind"], owner["table"], owner["model"]),
            ("table", "studio_demo_book", BOOK),
        )
        with self.assertRaisesRegex(UserError, "studio_demo_book"):
            self.make_model(self.project, "Other book", model="studio_demo_book")
        self.assertIsNone(self.status(BOOK, line)["code"])
        self.assertEqual(self.status(BOOK)["owner"]["kind"], "project")
        # A model a module on the addons path defines, installed or not;
        # the generated module of the project itself aside.
        shelf = "studio_demo.shelf"
        with patch(
            f"{PROJECT_MODULE}.module_model_names",
            lambda: {shelf: frozenset({"studio_demo_library"})},
        ):
            self.assertEqual(self.status(shelf)["owner"]["kind"], "module")
            with self.assertRaisesRegex(UserError, shelf):
                self.make_model(self.project, "Shelf", model=shelf)
        with patch(
            f"{PROJECT_MODULE}.module_model_names", lambda: {shelf: frozenset({MODULE})}
        ):
            self.assertIsNone(self.status(shelf)["code"])

    def test_module_table_reserved(self):
        """The table of a model a module on the addons path defines, installed
        or not, is reserved too: the name without dots of a model of a
        module, or a model of its explicit ``_table``. The project's own
        generated module aside."""
        tables = {"studio_demo_shelf": frozenset({"studio_demo_library"})}
        with patch(f"{PROJECT_MODULE}.module_model_tables", lambda: tables):
            status = self.status("studio_demo_shelf")
            self.assertEqual(status["code"], "unique")
            self.assertEqual(
                (status["owner"]["kind"], status["owner"]["table"]),
                ("module", "studio_demo_shelf"),
            )
            self.assertIn("studio_demo_shelf", status["message"])
            with self.assertRaisesRegex(UserError, "studio_demo_shelf"):
                self.make_model(self.project, "Shelf", model="studio_demo.shelf")
        tables = {"studio_demo_shelf": frozenset({MODULE})}
        with patch(f"{PROJECT_MODULE}.module_model_tables", lambda: tables):
            self.assertIsNone(self.status("studio_demo_shelf")["code"])
        # The sources of the addons path: a core model, installed or not,
        # in its form without dots.
        self.assertIn("sale_order", project_module.module_model_tables())
        self.assertEqual(self.status("sale_order")["code"], "unique")

    def test_scan_reads_names_and_tables(self):
        """The scan of the sources gives each model its explicit ``_table``,
        else its name with its dots as ``_``, class by class."""
        root = tempfile.mkdtemp(prefix="erplibre_studio_scan_")
        self.addCleanup(shutil.rmtree, root, True)
        module = os.path.join(root, "studio_demo_vault", "models")
        os.makedirs(module)
        with open(
            os.path.join(root, "studio_demo_vault", "__manifest__.py"), "w"
        ) as fh:
            fh.write("{'name': 'Vault'}\n")
        with open(os.path.join(module, "vault.py"), "w") as fh:
            fh.write(
                "class Vault(models.Model):\n"
                "    _name = 'studio_demo.vault'\n"
                "    _table = 'studio_demo_safe'\n"
                "\n"
                "class Key(models.Model):\n"
                "    _name = 'studio_demo.key'\n"
            )
        names, tables = project_module._module_models(((root, 0),))
        modules = frozenset({"studio_demo_vault"})
        self.assertEqual(
            names, {"studio_demo.vault": modules, "studio_demo.key": modules}
        )
        self.assertEqual(
            tables, {"studio_demo_safe": modules, "studio_demo_key": modules}
        )

    def test_apply_reads_the_sources_again(self):
        """Apply and the generation read the sources of the addons path
        again: a model added inside an existing module changes no directory
        of the addons path."""
        self.book_line()
        with patch(f"{PROJECT_MODULE}.refresh_module_models") as refresh:
            self.project.action_apply()
            self.assertTrue(refresh.called)
            refresh.reset_mock()
            self.project._check_generation_model_names()
            self.assertTrue(refresh.called)

    def test_apply_creates_the_marked_model(self):
        line = self.book_line()
        self.project.action_apply()
        record = self.IrModel._get(BOOK)
        self.assertEqual(record.state, "manual")
        self.assertTrue(record.erplibre_studio_unprefixed)
        self.assertIn(record, self.project.created_model_ids)
        self.assertTrue(line.applied)
        self.assertIn(BOOK, self.env)
        self.assertTrue(sql.table_exists(self.env.cr, "studio_demo_book"))
        book = self.env[BOOK].create({"x_name": "Un livre"})
        self.assertEqual(book.x_name, "Un livre")
        # A new setup of the registry builds it again from its row.
        self.registry.setup_models(self.env.cr)
        self.assertEqual(self.env[BOOK].browse(book.id).x_name, "Un livre")
        self.assertFalse(self.project._studio_model_name_problems())

    def test_unmarked_create_still_needs_x(self):
        with self.assertRaises(ValidationError):
            self.IrModel.create({"model": "studio_demo.other", "name": "Other"})
        with self.assertRaises(ValidationError):
            self.IrModel.create(
                {
                    "model": "class",
                    "name": "Keyword",
                    "erplibre_studio_unprefixed": True,
                }
            )
        with self.production_rule(), self.assertRaises(ValidationError):
            self.IrModel.create(
                {
                    "model": "studio_demo.other",
                    "name": "Other",
                    "erplibre_studio_unprefixed": True,
                }
            )

    def test_production_rule_refuses(self):
        line = self.book_line()
        with self.production_rule():
            with self.assertRaisesRegex(UserError, "x_"):
                self.make_model(self.project, "Shelf", model="studio_demo.shelf")
            with self.assertRaisesRegex(UserError, "x_"):
                self.project._studio_update_model(
                    line, {"model": "studio_demo.library"}
                )
            self.assertEqual(
                [p["line_id"] for p in self.project._studio_model_name_problems()],
                [line.id],
            )
            counts = self.Editor._project_counts(self.project)
            self.assertEqual(counts["name_blockers"], 1)
            with self.assertRaisesRegex(UserError, "x_"):
                self.project.action_apply()
            # Past the checks, Apply refuses it before ir.model does.
            with self.assertRaisesRegex(UserError, "needs the x_ prefix"):
                self.project._apply_models([])
        self.assertFalse(self.IrModel._get(BOOK))

    def test_discard_keeps_an_applied_unprefixed_line(self):
        line = self.book_line()
        self.project.action_apply()
        self.project._studio_update_model(line, {"name": "Studio demo books"})
        with self.production_rule():
            self.project.action_discard()
            restored = self.project.new_model_ids
            self.assertEqual(restored.mapped("model"), [BOOK])
            self.assertEqual(restored.name, "Studio demo book")
            self.assertTrue(restored.applied)
            self.assertFalse(self.project._studio_model_name_problems())

    def test_module_class_takes_the_model_over(self):
        self.book_line()
        self.project.action_apply()

        class ModuleBook:
            _custom = False
            _module = "studio_demo_library"

        # The class of a module of that name in the registry; the setup of
        # the custom models itself is left out.
        with (
            patch.dict(self.registry.models, {BOOK: ModuleBook}),
            patch.object(BaseIrModel, "_add_manual_models", lambda self_: None),
            self.assertLogs(LOADER_LOGGER, "WARNING") as logs,
        ):
            self.env["ir.model"]._add_manual_models()
        self.assertIn(
            f"Studio model {BOOK} is defined by the module studio_demo_library",
            logs.output[0],
        )
        self.env.cr.execute("SELECT state FROM ir_model WHERE model = %s", [BOOK])
        self.assertEqual(self.env.cr.fetchone()[0], "base")

    def test_uninstall_waits_for_the_models(self):
        self.book_line()
        self.project.action_apply()
        module = self.env["ir.module.module"].search(
            [("name", "=", "erplibre_studio_generate")]
        )
        with self.assertRaises(UserError) as caught:
            module.button_uninstall()
        message = str(caught.exception)
        self.assertIn("Studio unprefixed models", message)
        self.assertIn(BOOK, message)
        module.invalidate_recordset(["state"])
        self.assertEqual(module.state, "installed")
        self.project.action_revert()
        self.assertFalse(self.IrModel._get(BOOK))
        self.assertIsNone(module._studio_unprefixed_refusal())

    def test_generate_writes_the_model(self):
        self.book_line()
        self.project.action_apply()
        with self.server_actions():
            self.project.action_generate()
        target = os.path.join(self.destination, MODULE)

        def read(*parts):
            with open(os.path.join(target, *parts), encoding="utf-8") as fh:
                return fh.read()

        source = read("models", "studio_demo_book.py")
        # Run as Odoo imports it, not only compiled.
        exec(  # pylint: disable=exec-used
            compile(source, "studio_demo_book.py", "exec"),
            {"__name__": f"odoo.addons.{MODULE}.models.studio_demo_book"},
        )
        tree = ast.parse(source)
        names = [
            ast.literal_eval(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and getattr(node.targets[0], "id", None) == "_name"
        ]
        self.assertEqual(names, [BOOK])
        hooks = ast.parse(read("hooks.py"))
        models_node = next(
            n
            for n in hooks.body
            if isinstance(n, ast.Assign) and n.targets[0].id == "MODELS"
        )
        self.assertEqual(ast.literal_eval(models_node.value), (BOOK,))
        self.assertIn("model_studio_demo_book", read("security", "ir.model.access.csv"))

    def test_generation_refuses_a_keyword_table(self):
        line = self.book_line()
        self.project._check_generation_model_names()
        self.env.cr.execute(
            "UPDATE erplibre_studio_model SET model = 'class' WHERE id = %s", [line.id]
        )
        line.invalidate_recordset(["model"])
        with self.server_actions(), self.assertRaisesRegex(UserError, "class"):
            self.project.action_generate()

    def test_generation_refuses_a_module_name(self):
        """An applied model whose name a module on the addons path defines
        since is not written: the two classes would be one model."""
        self.book_line()
        self.project.action_apply()
        names = {BOOK: frozenset({"studio_demo_library"})}
        with (
            patch(f"{PROJECT_MODULE}.module_model_names", lambda: names),
            self.server_actions(),
            self.assertRaisesRegex(UserError, "A module on the addons path"),
        ):
            self.project.action_generate()

    def test_foreign_module_owns_the_model(self):
        """A model of the project that another module defines now: Apply,
        Revert and the generation are refused and name that module."""
        self.book_line()
        self.project.action_apply()
        ModuleBook = type(
            "ModuleBook",
            (self.registry[BOOK],),
            {
                "_register": False,
                "_custom": False,
                "_original_module": "studio_demo_library",
            },
        )
        self.env.cr.execute(
            "UPDATE ir_model SET state = 'base' WHERE model = %s", [BOOK]
        )
        self.env["ir.model"].invalidate_model(["state"])
        with patch.dict(self.registry.models, {BOOK: ModuleBook}):
            self.assertEqual(
                self.project._studio_foreign_models(), {BOOK: "studio_demo_library"}
            )
            refusal = self.project._studio_revert_refusal()
            self.assertIn(f"{BOOK} (studio_demo_library)", refusal)
            with self.assertRaisesRegex(UserError, "studio_demo_library"):
                self.project.action_revert()
            with self.assertRaisesRegex(UserError, "studio_demo_library"):
                self.project.action_apply()
            with (
                self.server_actions(),
                self.assertRaisesRegex(UserError, "studio_demo_library"),
            ):
                self.project.action_generate()
        # Its own generated module defines it: not another module.
        ModuleBook._original_module = MODULE
        with patch.dict(self.registry.models, {BOOK: ModuleBook}):
            self.assertEqual(self.project._studio_foreign_models(), {})
