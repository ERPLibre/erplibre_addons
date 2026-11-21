# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.tools.misc import file_path

from ..models.erplibre_studio_project import DEFAULT_APP_ICON
from .common import StudioCase

PROJECT_MODULE = "odoo.addons.erplibre_studio.models.erplibre_studio_project"

MODULE = "studio_test_apps"
ORDER = "x_studio_test_order"
STOCK = "x_studio_test_stock"
BASE_ICON = "base,static/description/icon.png"


@tagged("post_install", "-at_install")
class TestApps(StudioCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.shop = self.project._studio_save_app(
            {"name": "Studio test shop", "icon": BASE_ICON}
        )
        self.stock = self.project._studio_save_app({"name": "Studio test stock"})

    def ref(self, name, model):
        data = self.module_records(MODULE, model).filtered(lambda d: d.name == name)
        return self.env[model].browse(data.res_id).exists()

    def in_app(self, label, model, app):
        return self.make_model(
            self.project, label, model=model, menu={"mode": "app", "app_id": app.id}
        )

    def test_each_app_its_menu(self):
        self.assertEqual(
            (self.shop.xml_name, self.stock.xml_name),
            ("menu_app", "menu_app_studio_test_stock"),
        )
        order = self.in_app("Studio test order", ORDER, self.shop)
        stock = self.in_app("Studio test stock item", STOCK, self.stock)
        extra = self.make_model(
            self.project,
            "Studio test extra",
            model="x_studio_test_extra",
            menu={"mode": "app", "new_app": {"name": "Studio test stock"}},
        )
        self.assertEqual(extra.app_id.xml_name, "menu_app_studio_test_stock_2")
        self.assertEqual(len(self.project.app_ids), 3)
        empty = self.project._studio_save_app({"name": "Studio test empty"})
        self.project.action_apply()
        shop_menu = self.ref("menu_app", "ir.ui.menu")
        stock_menu = self.ref("menu_app_studio_test_stock", "ir.ui.menu")
        self.assertEqual(
            (shop_menu.name, shop_menu.web_icon, shop_menu.parent_id.id),
            ("Studio test shop", BASE_ICON, False),
        )
        self.assertEqual(stock_menu.web_icon, DEFAULT_APP_ICON)
        self.assertEqual(self.ref(f"menu_{ORDER}", "ir.ui.menu").parent_id, shop_menu)
        self.assertEqual(self.ref(f"menu_{STOCK}", "ir.ui.menu").parent_id, stock_menu)
        # An app no model goes in makes no menu.
        self.assertFalse(self.ref(empty.xml_name, "ir.ui.menu"))
        self.assertTrue(order.applied and stock.applied)
        payload = self.Editor._project_payload(self.project)
        self.assertEqual(
            [a["xml_name"] for a in payload["apps"]],
            [
                "menu_app",
                "menu_app_studio_test_stock",
                "menu_app_studio_test_stock_2",
                "menu_app_studio_test_empty",
            ],
        )
        self.assertEqual(
            payload["app"], {"name": "Studio test shop", "icon": BASE_ICON}
        )
        self.assertEqual(payload["models"][0]["app_id"], self.shop.id)
        # Removed while a model goes in it: refused.
        with self.assertRaisesRegex(UserError, ORDER):
            with self.env.cr.savepoint():
                self.project._studio_remove_app(self.shop)
        self.project._studio_remove_app(empty)
        self.assertFalse(empty.exists())
        # A model moved to another app moves its menu.
        self.project._studio_update_model(
            order, {"menu": {"mode": "app", "app_id": self.stock.id}}
        )
        self.project.action_apply()
        self.assertEqual(self.ref(f"menu_{ORDER}", "ir.ui.menu").parent_id, stock_menu)
        self.assertFalse(shop_menu.exists())

    def test_app_checks(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.project._studio_save_app({"id": self.shop.id, "name": " "})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.project._studio_save_app(
                {"name": "Studio test bad icon", "icon": "base/static/icon.png"}
            )
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.project._studio_save_app({"name": ""})
        # A client does not choose the external id.
        app = self.env["erplibre.studio.app"].create(
            {
                "project_id": self.project.id,
                "name": "Studio test sent",
                "xml_name": "menu_app_forced",
            }
        )
        self.assertEqual(app.xml_name, "menu_app_studio_test_sent")
        # The app of a model is an app of its project.
        other = self.make_project("studio_test_apps_other")
        line = self.make_model(other, "Studio test other")
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            line.write({"app_id": self.shop.id})

    def test_discard_keeps_the_external_ids(self):
        self.in_app("Studio test order", ORDER, self.shop)
        self.in_app("Studio test stock item", STOCK, self.stock)
        self.project.action_apply()
        snapshot = self.project.applied_snapshot
        self.stock.name = "Studio test renamed"
        self.project._studio_remove_model(self.project.new_model_ids[1])
        self.project._studio_remove_app(self.stock)
        self.assertEqual(self.project.state, "draft")
        self.project.action_discard()
        self.assertEqual(self.project.state, "applied")
        self.assertEqual(self.project._current_snapshot(), snapshot)
        stock = self.project.app_ids.filtered(lambda a: a.name == "Studio test stock")
        self.assertEqual(stock.xml_name, "menu_app_studio_test_stock")
        self.assertEqual(
            self.project.new_model_ids.filtered(lambda m: m.model == STOCK).app_id,
            stock,
        )

    def test_icon_once_the_module_is_installed(self):
        """Installed with the icon of the app, the generated module owns the
        app menu and its icon: Apply gives it the icon of the module, and a
        new icon waits for the next generation."""
        self.in_app("Studio test order", ORDER, self.shop)
        self.project.action_apply()
        menu = self.ref("menu_app", "ir.ui.menu")
        module_icon = f"{MODULE},static/description/menu_app.png"
        Project = type(self.Project)

        def installed(projects):
            for project in projects:
                project.module_id = False
                project.module_state = "installed"

        def holds_icon(path, *args, **kwargs):
            if path.startswith(f"{MODULE}/"):
                return path
            return file_path(path, *args, **kwargs)

        with (
            patch.object(Project, "_compute_module_id", installed),
            patch(f"{PROJECT_MODULE}.file_path", holds_icon),
        ):
            self.project.invalidate_recordset(["module_state", "module_id"])
            self.assertEqual(self.project._studio_app_web_icon(self.shop), module_icon)
            # The take-over writes the icon of the module on the menu.
            menu.web_icon = module_icon
            Menu = type(menu)
            written = []
            write = Menu.write

            def spy(records, vals):
                written.extend(records.ids)
                return write(records, vals)

            with patch.object(Menu, "write", spy):
                self.assertIs(self.project.action_apply(), True)
            self.assertNotIn(menu.id, written)
            self.assertEqual(menu.web_icon, module_icon)
            # A new icon: the menu keeps the one of the module until the
            # module is generated again.
            self.shop.icon = DEFAULT_APP_ICON
            with patch.object(
                Project, "_studio_generated_icon", lambda p, a: BASE_ICON
            ):
                result = self.project.action_apply()
            self.assertIn("Studio test shop", result["params"]["message"])
            self.assertEqual(menu.web_icon, module_icon)
        self.project.invalidate_recordset(["module_state", "module_id"])

    def test_icon_of_an_app_the_module_does_not_hold(self):
        """Installed without the icon of an app (an app added since the last
        generation): the menu keeps the chosen icon, and Apply says it waits
        for the next generation."""
        self.in_app("Studio test order", ORDER, self.shop)
        Project = type(self.Project)

        def installed(projects):
            for project in projects:
                project.module_id = False
                project.module_state = "installed"

        with patch.object(Project, "_compute_module_id", installed):
            self.project.invalidate_recordset(["module_state", "module_id"])
            self.assertIsNone(self.project._studio_module_icon(self.shop))
            self.assertEqual(self.project._studio_app_web_icon(self.shop), BASE_ICON)
            result = self.project.action_apply()
            self.assertIn("app icon Studio test shop", result["params"]["message"])
        self.assertEqual(self.ref("menu_app", "ir.ui.menu").web_icon, BASE_ICON)
        self.project.invalidate_recordset(["module_state", "module_id"])
