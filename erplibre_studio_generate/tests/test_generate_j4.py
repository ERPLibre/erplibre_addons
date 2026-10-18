# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import csv
import io
import json
import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import file_open

from .. import upgrade

MODULE = "studio_test_generate_j4"
ORDER = "x_studio_test_j4_order"
LINE = "x_studio_test_j4_line"
NOTE = "x_studio_test_j4_note"
LEFT = "//group[@name='studio_left']"
BASE_ICON = "base,static/description/icon.png"
MAIL_ICON = "mail,static/description/icon.png"
PERMS = ("perm_read", "perm_write", "perm_create", "perm_unlink")


@tagged("post_install", "-at_install")
class TestGenerateJ4(StudioCase):
    """Generation of a project with two apps and their icons, three new
    models, a one2many with the inverse the studio creates, many2many
    between new models and from an existing model, groups of the project
    that imply each other, access rights and rules on them, and a global
    rule."""

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
        self.user_group = self.env.ref("base.group_user")
        project = self.project = self.make_project(MODULE, destination=self.destination)
        self.shop = project._studio_save_app(
            {"name": "Studio test shop", "icon": BASE_ICON}
        )
        self.stock = project._studio_save_app(
            {"name": "Studio test stock", "icon": MAIL_ICON, "menu_sequence": 60}
        )
        self.order = self.make_model(
            project,
            "Studio test order",
            model=ORDER,
            menu={"mode": "app", "app_id": self.shop.id},
        )
        self.line = self.make_model(
            project,
            "Studio test line",
            model=LINE,
            menu={"mode": "app", "app_id": self.stock.id},
        )
        self.note = self.make_model(
            project,
            "Studio test note",
            model=NOTE,
            menu={"mode": "menu", "parent_id": self.env.ref("base.menu_custom").id},
        )
        self.group_user = project._studio_save_group(
            {"name": "Studio test user", "app_id": self.shop.id}
        )
        self.group_admin = project._studio_save_group(
            {
                "name": "Studio test admin",
                "app_id": self.shop.id,
                "comment": "Every order",
                "implied_line_ids": [self.group_user.id],
                "implied_group_ids": [],
            }
        )
        project.action_apply()
        order_form = self.order._studio_views()["form"]
        self.lines = self.add(
            order_form,
            ttype="one2many",
            field_description="Lines",
            relation=LINE,
            inverse={"create": True},
        )
        self.notes = self.add(
            order_form, ttype="many2many", field_description="Notes", relation=NOTE
        )
        self.partner_orders = self.add(
            self.form,
            target="//field[@name='vat']",
            position="after",
            ttype="many2many",
            field_description="Studio orders",
            relation=ORDER,
        )
        rows = [
            {"model": a.model, "group_id": a.group_id.id, **{p: a[p] for p in PERMS}}
            for a in project.access_line_ids
        ]
        rows += [
            {
                "model": ORDER,
                "group_line_id": self.group_user.id,
                "perm_read": True,
                "perm_write": True,
                "perm_create": True,
                "perm_unlink": False,
            },
            {
                "model": ORDER,
                "group_line_id": self.group_admin.id,
                **{p: True for p in PERMS},
            },
        ]
        project._studio_set_access(rows)
        self.own_rule = project._studio_save_rule(
            {
                "name": "Studio test own orders",
                "model": ORDER,
                "domain": "[('create_uid', '=', user.id)]",
                "group_line_ids": [self.group_user.id],
                **{p: True for p in PERMS},
            }
        )
        self.all_rule = project._studio_save_rule(
            {
                "name": "Studio test every order",
                "model": ORDER,
                "domain": "[(1, '=', 1)]",
                "group_line_ids": [self.group_admin.id],
                **{p: True for p in PERMS},
            }
        )
        self.global_rule = project._studio_save_rule(
            {
                "name": "Studio test named lines",
                "model": LINE,
                "domain": "[('x_name', '!=', False)]",
                "global_rule": True,
                "perm_read": True,
            }
        )
        project.action_apply()
        self.assertEqual(project.state, "applied")

    def add(self, view, target=LEFT, position="inside", **field):
        return self.op(
            self.project,
            view,
            type="add_field",
            target=target,
            position=position,
            field=field,
        )

    def read(self, *parts, mode="r"):
        path = os.path.join(self.destination, MODULE, *parts)
        if mode == "rb":
            with open(path, "rb") as fh:
                return fh.read()
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def generate(self):
        with self.server_actions():
            self.project.action_generate()

    def definition(self, change):
        return change._payload()["field"]

    @staticmethod
    def fields_of(source):
        """{field: keywords} of the first class of the Python ``source``,
        literal keywords only; the source must compile."""
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        fields = {}
        for item in node.body:
            if isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
                fields[item.targets[0].id] = {
                    kw.arg: ast.literal_eval(kw.value)
                    for kw in item.value.keywords
                    if isinstance(kw.value, ast.Constant)
                }
                fields[item.targets[0].id]["_type"] = item.value.func.attr
        return fields

    # ── groups ─────────────────────────────────────────────────────────

    def test_groups_file(self):
        self.generate()
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertEqual(manifest["data"][0], "security/erplibre_studio_groups.xml")
        self.assertIn("security/ir.model.access.csv", manifest["data"])
        root = etree.fromstring(
            self.read("security", "erplibre_studio_groups.xml").encode(),
            etree.XMLParser(remove_blank_text=True),
        )
        user, admin = self.group_user.xml_name, self.group_admin.xml_name
        self.assertEqual(
            [(r.get("model"), r.get("id")) for r in root],
            [
                ("ir.module.category", "module_category_app"),
                ("res.groups", user),
                ("res.groups", admin),
            ],
        )
        category = root[0]
        self.assertEqual(
            {f.get("name"): f.text for f in category},
            {"name": "Studio test shop", "sequence": "50"},
        )
        records = {r.get("id"): r for r in root[1:]}
        for xml_name, name in (
            (user, "Studio test user"),
            (admin, "Studio test admin"),
        ):
            record = records[xml_name]
            self.assertEqual(record.find("field[@name='name']").text, name)
            self.assertEqual(
                record.find("field[@name='category_id']").get("ref"),
                "module_category_app",
            )
        self.assertEqual(
            records[user].find("field[@name='implied_ids']").get("eval"),
            "[(6, 0, [ref('base.group_user')])]",
        )
        self.assertEqual(
            records[admin].find("field[@name='implied_ids']").get("eval"),
            f"[(6, 0, [ref({user!r})])]",
        )
        self.assertEqual(
            records[admin].find("field[@name='comment']").text, "Every order"
        )
        # Written empty as well, so that an upgrade clears a former one.
        self.assertEqual(
            records[user].find("field[@name='comment']").get("eval"), "False"
        )
        # The external ids are those Apply gave the records.
        for xml_name in (user, admin, "module_category_app"):
            self.assertTrue(self.env.ref(f"{MODULE}.{xml_name}"))

    def test_access_rights_and_rules_on_project_groups(self):
        self.generate()
        rows = list(
            csv.DictReader(io.StringIO(self.read("security", "ir.model.access.csv")))
        )
        by_group = {
            (row["model_id:id"], row["group_id:id"]): row
            for row in rows
            if row["model_id:id"] == f"model_{ORDER}"
        }
        user = f"{MODULE}.{self.group_user.xml_name}"
        admin = f"{MODULE}.{self.group_admin.xml_name}"
        self.assertEqual(
            sorted(by_group),
            sorted(
                (f"model_{ORDER}", group) for group in ("base.group_user", user, admin)
            ),
        )
        self.assertEqual(
            [by_group[(f"model_{ORDER}", user)][p] for p in PERMS],
            ["1", "1", "1", "0"],
        )
        security = etree.fromstring(self.read("security", f"{MODULE}.xml").encode())
        rules = {
            r.get("id"): r for r in security.findall(".//record[@model='ir.rule']")
        }
        self.assertEqual(
            rules[self.own_rule.xml_name].find("field[@name='groups']").get("eval"),
            f"[(6, 0, [ref({user!r})])]",
        )
        self.assertEqual(
            rules[self.all_rule.xml_name].find("field[@name='groups']").get("eval"),
            f"[(6, 0, [ref({admin!r})])]",
        )
        # Every rule holds its whole state: an upgrade writes only the fields
        # a record names, so that a rule made global, or a permission given
        # back, keeps its former value otherwise.
        named = rules[self.global_rule.xml_name]
        self.assertEqual(
            named.find("field[@name='groups']").get("eval"), "[(6, 0, [])]"
        )
        self.assertEqual(
            {p: named.find(f"field[@name='{p}']").get("eval") for p in PERMS},
            {
                "perm_read": "True",
                "perm_write": "False",
                "perm_create": "False",
                "perm_unlink": "False",
            },
        )
        for record in rules.values():
            for perm in PERMS:
                self.assertIsNotNone(record.find(f"field[@name='{perm}']"))

    def test_dependencies_of_groups(self):
        """The module of an existing group a group of the project implies is
        a dependency; the groups of the project are the module's own."""
        self.assertEqual(self.project._dependencies(), ["base"])
        editor = self.env.ref("mail.group_mail_template_editor")
        self.project._studio_save_group(
            {"id": self.group_user.id, "implied_group_ids": editor.ids}
        )
        self.assertEqual(self.project._dependencies(), ["base", "mail"])

    def test_an_existing_group_by_an_id_of_an_installed_module(self):
        """An existing group goes into the module by its external id under an
        installed module, never by one under « __export__ »."""
        group = self.env["res.groups"].create({"name": "Studio test exported"})
        self.env["ir.model.data"].create(
            {
                "module": "__export__",
                "name": "res_groups_studio_test_exported",
                "model": "res.groups",
                "res_id": group.id,
            }
        )
        self.bind_group(group, "studio_test_invented", "group_exported")
        self.project._studio_save_group(
            {"id": self.group_user.id, "implied_group_ids": group.ids}
        )
        self.assertEqual(self.project._dependencies(), ["base", "studio_test_invented"])
        self.project.action_apply()
        self.generate()
        groups_file = self.read("security", "erplibre_studio_groups.xml")
        self.assertIn("ref('studio_test_invented.group_exported')", groups_file)
        self.assertNotIn("__export__", groups_file)

    def test_generation_checks_the_groups_again(self):
        """An existing group a project group implies that comes to grant the
        Settings: the generation refuses, as Apply does."""
        middle = self.bind_group(
            self.env["res.groups"].create({"name": "Studio test middle"}),
            "studio_test_invented",
            "group_middle",
        )
        self.project._studio_save_group(
            {"id": self.group_user.id, "implied_group_ids": middle.ids}
        )
        self.project.action_apply()
        middle.implied_ids = [(4, self.env.ref("base.group_system").id)]
        with self.assertRaisesRegex(UserError, "grants"):
            with self.env.cr.savepoint():
                self.generate()
        self.assertFalse(os.path.exists(os.path.join(self.destination, MODULE)))

    # ── relations ──────────────────────────────────────────────────────

    def test_relation_fields(self):
        self.generate()
        lines = self.definition(self.lines)
        notes = self.definition(self.notes)
        partner_orders = self.definition(self.partner_orders)
        inverse = lines["relation_field"]
        order_fields = self.fields_of(self.read("models", f"{ORDER}.py"))
        self.assertEqual(
            sorted(order_fields),
            sorted(["x_name", self.lines.field_name, self.notes.field_name]),
        )
        one2many = order_fields[self.lines.field_name]
        self.assertEqual(
            (one2many["_type"], one2many["comodel_name"], one2many["inverse_name"]),
            ("One2many", LINE, inverse),
        )
        many2many = order_fields[self.notes.field_name]
        self.assertEqual(
            (
                many2many["_type"],
                many2many["comodel_name"],
                many2many["relation"],
                many2many["column1"],
                many2many["column2"],
            ),
            (
                "Many2many",
                NOTE,
                notes["relation_table"],
                notes["column1"],
                notes["column2"],
            ),
        )
        # The names are those of the table Apply created.
        field = self.env["ir.model.fields"]._get(ORDER, self.notes.field_name)
        self.assertEqual(
            (field.relation_table, field.column1, field.column2),
            (notes["relation_table"], notes["column1"], notes["column2"]),
        )
        # The inverse many2one the studio created on the line.
        line_fields = self.fields_of(self.read("models", f"{LINE}.py"))
        self.assertEqual(sorted(line_fields), sorted([inverse, "x_name"]))
        self.assertEqual(
            (
                line_fields[inverse]["_type"],
                line_fields[inverse]["comodel_name"],
                line_fields[inverse]["ondelete"],
                line_fields[inverse]["string"],
            ),
            ("Many2one", ORDER, "cascade", "Studio test order"),
        )
        # The existing model gets its many2many to the new model only.
        partner_fields = self.fields_of(self.read("models", "res_partner.py"))
        self.assertEqual(list(partner_fields), [self.partner_orders.field_name])
        field = partner_fields[self.partner_orders.field_name]
        self.assertEqual(
            (
                field["comodel_name"],
                field["relation"],
                field["column1"],
                field["column2"],
            ),
            (
                ORDER,
                partner_orders["relation_table"],
                "res_partner_id",
                f"{ORDER}_id",
            ),
        )
        self.assertTrue(partner_orders["relation_table"].startswith(f"x_{MODULE}_"))
        # The form shows the sub-lists; the readme names the relations.
        views = self.read("views", "erplibre_studio_views.xml")
        root = etree.fromstring(views.encode())
        inherited = root.find(f"record[@id='{MODULE}_view_{ORDER}_form_studio']")
        sub_list = inherited.xpath(f".//field[@name='{self.lines.field_name}']/list")
        self.assertEqual(sub_list[0].get("editable"), "bottom")
        readme = self.read("readme", "DESCRIPTION.md")
        self.assertIn(f"`{LINE}`: field `{inverse}` (many2one", readme)
        self.assertIn(f"inverse `{inverse}`", readme)
        self.assertIn(f"table `{notes['relation_table']}`", readme)

    def test_inverse_on_an_existing_model(self):
        """A one2many of a new model to an existing model whose inverse the
        studio creates: the existing model gets the many2one, « set null »,
        and is a model of the module."""
        change = self.add(
            self.order._studio_views()["form"],
            ttype="one2many",
            field_description="Contacts",
            relation="res.partner",
            inverse={"create": True},
        )
        self.project.action_apply()
        inverse = self.definition(change)["relation_field"]
        self.assertIn("res.partner", self.project._generation_models())
        self.generate()
        field = self.fields_of(self.read("models", "res_partner.py"))[inverse]
        self.assertEqual((field["comodel_name"], field["_type"]), (ORDER, "Many2one"))
        self.assertNotIn("ondelete", field)

    # ── apps and icons ─────────────────────────────────────────────────

    def test_apps_menus_and_icons(self):
        self.generate()
        root = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode(),
            etree.XMLParser(remove_blank_text=True),
        )
        menus = [dict(node.attrib) for node in root if node.tag == "menuitem"]
        stock = self.stock.xml_name
        self.assertEqual(stock, "menu_app_studio_test_stock")
        self.assertEqual(
            menus[:2],
            [
                {
                    "id": "menu_app",
                    "name": "Studio test shop",
                    "web_icon": f"{MODULE},static/description/menu_app.png",
                    "sequence": "50",
                },
                {
                    "id": stock,
                    "name": "Studio test stock",
                    "web_icon": f"{MODULE},static/description/{stock}.png",
                    "sequence": "60",
                },
            ],
        )
        parents = {m["id"]: m.get("parent") for m in menus[2:]}
        self.assertEqual(
            parents,
            {
                f"menu_{ORDER}": "menu_app",
                f"menu_{LINE}": stock,
                f"menu_{NOTE}": "base.menu_custom",
            },
        )
        icons = {}
        for icon in (BASE_ICON, MAIL_ICON):
            with file_open(icon.replace(",", "/"), "rb") as fh:
                icons[icon] = fh.read()
        self.assertEqual(
            self.read("static", "description", "menu_app.png", mode="rb"),
            icons[BASE_ICON],
        )
        self.assertEqual(
            self.read("static", "description", f"{stock}.png", mode="rb"),
            icons[MAIL_ICON],
        )
        # The module icon is the icon of the first app.
        self.assertEqual(
            self.read("static", "description", "icon.png", mode="rb"),
            icons[BASE_ICON],
        )
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertTrue(manifest["application"])
        readme = self.read("readme", "DESCRIPTION.md")
        self.assertIn("app Studio test shop, groups: Studio test user", readme)
        self.assertIn(
            "group Studio test admin of the app Studio test shop, implies "
            "Studio test user",
            readme,
        )
        self.assertIn("menu Studio test line in the app Studio test stock", readme)

    def test_generated_icon(self):
        """The icon of an app at the last generation comes from its
        snapshot: a new icon differs from it until the next one."""
        self.assertIsNone(self.project._studio_generated_icon(self.shop))
        self.generate()
        self.assertEqual(self.project._studio_generated_icon(self.shop), BASE_ICON)
        self.assertEqual(self.project._studio_generated_icon(self.stock), MAIL_ICON)
        self.shop.icon = False
        self.assertEqual(self.project._studio_generated_icon(self.shop), BASE_ICON)
        later = self.project._studio_save_app({"name": "Studio test later"})
        self.assertIsNone(self.project._studio_generated_icon(later))
        self.project.action_apply()
        self.generate()
        self.assertEqual(self.project._studio_generated_icon(self.shop), "")

    def test_texts_of_apps_and_groups_checked_again(self):
        self.env.cr.execute(
            "UPDATE erplibre_studio_group SET name = %s WHERE id = %s",
            ('Studio "test" user', self.group_user.id),
        )
        self.group_user.invalidate_recordset()
        with self.server_actions(), self.assertRaisesRegex(UserError, "quotes"):
            self.project.action_generate()

    def test_changes_of_models_not_created_refused(self):
        """A change still on the view of a model not created yet cannot be
        in a module: the generation asks for an Apply."""
        self.env.cr.execute(
            "UPDATE erplibre_studio_change SET view_id = NULL, model_line_id = %s "
            "WHERE id = %s",
            [self.order.id, self.notes.id],
        )
        self.project.change_ids.invalidate_recordset()
        with patch.object(type(self.project), "_update_state", lambda p: None):
            with self.server_actions(), self.assertRaisesRegex(
                UserError, "not created yet"
            ):
                self.project.action_generate()

    # ── uninstall, migration ───────────────────────────────────────────

    def test_uninstall_clears_the_generation_snapshot(self):
        self.generate()
        self.assertEqual(self.project.state, "generated")
        vals = self.project._studio_uninstall_reset_vals()
        self.assertIs(vals["generated_snapshot"], False)
        self.project._studio_reset_after_uninstall()
        self.assertEqual(self.project.state, "draft")
        self.assertFalse(self.project.generated_snapshot)
        self.assertTrue(self.project.generation_count)

    def test_migration_of_a_generated_project(self):
        """A project « generated » whose generation snapshot is in the
        former form takes the applied snapshot, rewritten by the migration
        of erplibre_studio; a project whose module is behind keeps its
        own."""
        self.generate()
        applied = self.project.applied_snapshot
        former = json.loads(applied)
        former.pop("apps")
        self.env.cr.execute(
            "UPDATE erplibre_studio_project SET generated_snapshot = %s WHERE id = %s",
            [json.dumps(former), self.project.id],
        )
        self.project.invalidate_recordset()
        upgrade.migrate_generated(self.env)
        self.project.invalidate_recordset()
        self.assertEqual(self.project.generated_snapshot, applied)
        self.assertEqual(self.project.state, "generated")
        upgrade.migrate_generated(self.env)
        self.assertEqual(self.project.generated_snapshot, applied)
        # Behind: applied after the generation.
        self.env.cr.execute(
            "UPDATE erplibre_studio_project SET generated_snapshot = %s, "
            "state = 'applied' WHERE id = %s",
            [json.dumps(former), self.project.id],
        )
        self.project.invalidate_recordset()
        upgrade.migrate_generated(self.env)
        self.project.invalidate_recordset()
        self.assertEqual(self.project.generated_snapshot, json.dumps(former))
