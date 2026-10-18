# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import base64
import csv
import io
import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import file_open

MODULE = "studio_test_generate_models"
ITEM = "x_studio_test_gen_item"
TAG = "x_studio_test_gen_tag"
RULE_DOMAIN = "[('create_uid', '=', user.id), ('id', '<', 1000000)]"
PERMS = ("perm_read", "perm_write", "perm_create", "perm_unlink")


@tagged("post_install", "-at_install")
class TestGenerateModels(StudioCase):
    """Generation of a project that creates models: their Python classes,
    default views, actions, app and menus, access rights and record
    rules."""

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
        self.chatter = self.mail_available()
        self.user_group = self.env.ref("base.group_user")
        self.parent_menu = self.env.ref("base.menu_custom")
        self.project = self.make_project(MODULE, destination=self.destination)
        self.item = self.make_model(
            self.project,
            "Studio test item",
            model=ITEM,
            chatter=self.chatter,
            menu={
                "mode": "app",
                "app_name": "Studio test app",
                "app_icon": "base,static/description/icon.png",
            },
        )
        self.tag = self.make_model(
            self.project,
            "Studio test tag",
            model=TAG,
            menu={"mode": "menu", "parent_id": self.parent_menu.id, "name": "Tags"},
        )
        self.project.action_apply()
        self.op(
            self.project,
            self.item._studio_views()["form"],
            type="add_field",
            target="//group[@name='studio_left']",
            position="inside",
            field={
                "ttype": "many2one",
                "field_description": "Tag",
                "relation": TAG,
            },
        )
        self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={
                "ttype": "many2one",
                "field_description": "Studio item",
                "relation": ITEM,
            },
        )
        rows = [
            {"model": a.model, "group_id": a.group_id.id, **{p: a[p] for p in PERMS}}
            for a in self.project.access_line_ids
        ]
        rows.append(
            {
                "model": "res.partner.category",
                "group_id": self.user_group.id,
                "perm_read": True,
                "perm_write": True,
                "perm_create": True,
                "perm_unlink": False,
            }
        )
        self.project._studio_set_access(rows)
        self.rule = self.project._studio_save_rule(
            {
                "name": "Own items & < all",
                "model": ITEM,
                "domain": RULE_DOMAIN,
                "group_ids": self.user_group.ids,
                "perm_read": True,
                "perm_write": True,
                "perm_create": False,
                "perm_unlink": True,
            }
        )
        self.project.action_apply()

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

    @staticmethod
    def class_of(source):
        """(class attributes, {field: keywords}) of the first class of the
        Python ``source``, literals only."""
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        attributes, fields = {}, {}
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            name = item.targets[0].id
            if isinstance(item.value, ast.Call):
                fields[name] = {
                    kw.arg: ast.literal_eval(kw.value) for kw in item.value.keywords
                }
            else:
                attributes[name] = ast.literal_eval(item.value)
        return attributes, fields

    # ── python ─────────────────────────────────────────────────────────

    def test_model_classes(self):
        item_model = self.env["ir.model"]._get(ITEM)
        self.generate()
        attributes, fields = self.class_of(self.read("models", f"{ITEM}.py"))
        self.assertEqual(attributes["_name"], ITEM)
        self.assertEqual(attributes["_description"], "Studio test item")
        if self.chatter:
            self.assertEqual(
                attributes["_inherit"], ["mail.activity.mixin", "mail.thread"]
            )
        else:
            self.assertNotIn("_inherit", attributes)
        self.assertEqual(sorted(fields), ["x_name", "x_tag"])
        self.assertEqual(fields["x_name"], {"string": "Name", "required": True})
        self.assertEqual(fields["x_tag"]["comodel_name"], TAG)
        attributes, fields = self.class_of(self.read("models", f"{TAG}.py"))
        self.assertEqual(attributes["_name"], TAG)
        self.assertNotIn("_inherit", attributes)
        self.assertEqual(list(fields), ["x_name"])
        # The extended model keeps the fields of the project only.
        attributes, fields = self.class_of(self.read("models", "res_partner.py"))
        self.assertEqual(attributes, {"_inherit": "res.partner"})
        self.assertEqual(list(fields), ["x_studio_item"])
        self.assertEqual(fields["x_studio_item"]["comodel_name"], ITEM)
        # The links of the generation are gone.
        self.assertFalse(item_model.m2o_module)
        self.assertFalse(item_model.inherit_model_ids)

    def test_manifest_hooks_and_icon(self):
        self.generate()
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertEqual(
            manifest["depends"], ["base", "mail"] if self.chatter else ["base"]
        )
        self.assertTrue(manifest["application"])
        self.assertEqual(manifest["pre_init_hook"], "erplibre_studio_take_over")
        self.assertEqual(
            manifest["data"],
            [
                "security/ir.model.access.csv",
                f"security/{MODULE}.xml",
                "views/erplibre_studio_views.xml",
            ],
        )
        self.assertIn(
            "from .hooks import erplibre_studio_take_over", self.read("__init__.py")
        )
        hooks = self.read("hooks.py")
        tree = ast.parse(hooks)
        models_node = next(
            n
            for n in tree.body
            if isinstance(n, ast.Assign) and n.targets[0].id == "MODELS"
        )
        self.assertEqual(ast.literal_eval(models_node.value), (ITEM, TAG))
        # The hook makes the custom models of its names the module's, and
        # them only.
        hand_made = self.env["ir.model"].create(
            {"name": "Hand made", "model": "x_studio_test_gen_hand"}
        )
        namespace = {}
        exec(compile(hooks, "hooks.py", "exec"), namespace)
        # A custom model of the module this version does not define: the
        # module is older than the database, the load stops. (Checked while
        # the models of the project are still custom: a new custom model
        # reloads the registry, which builds custom models only.)
        ahead = self.env["ir.model"].create(
            {"name": "Studio test ahead", "model": "x_studio_test_gen_ahead"}
        )
        self.project._studio_bind(ahead, "model_x_studio_test_gen_ahead")
        with self.assertRaisesRegex(UserError, "x_studio_test_gen_ahead"):
            namespace["take_over"](self.env.cr)
        self.module_records(MODULE, "ir.model").filtered(
            lambda d: d.res_id == ahead.id
        ).unlink()
        ahead.unlink()
        namespace["erplibre_studio_take_over"](self.env)
        self.env["ir.model"].invalidate_model(["state"])
        self.assertEqual(
            [self.env["ir.model"]._get(m).state for m in (ITEM, TAG)],
            ["base", "base"],
        )
        self.assertEqual(hand_made.state, "manual")
        with file_open("base/static/description/icon.png", "rb") as fh:
            self.assertEqual(
                self.read("static", "description", "icon.png", mode="rb"), fh.read()
            )
        readme = self.read("readme", "DESCRIPTION.md")
        self.assertIn(f"`{ITEM}` (Studio test item): new model", readme)
        self.assertIn("Studio test app", readme)
        self.assertIn(f"`{TAG}` (Studio test tag)", readme)
        self.assertIn("`res.partner.category`: access right rwc-", readme)
        self.assertIn("Own items & < all", readme)

    def test_generation_owns_its_external_ids_and_migrates(self):
        """Apply marks its external ids « noupdate », the generation takes
        them back: an upgrade then updates their records. Each version
        ships the migration that takes over the models Apply created since
        the install."""
        data = self.module_records(MODULE)
        self.assertEqual(set(data.mapped("noupdate")), {True})
        self.generate()
        data.invalidate_recordset(["noupdate"])
        self.assertEqual(set(data.mapped("noupdate")), {False})
        version = self.project.generated_version
        migration = self.read("migrations", version, "pre-migration.py")
        tree = ast.parse(migration)
        imports = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        self.assertEqual(
            (imports[0].module, [a.name for a in imports[0].names]),
            (f"odoo.addons.{MODULE}.hooks", ["take_over"]),
        )
        self.assertEqual(
            [n.name for n in tree.body if isinstance(n, ast.FunctionDef)], ["migrate"]
        )
        # What Apply makes next waits for the next generation.
        self.make_model(self.project, "Studio test later", model="x_studio_test_later")
        self.project.action_apply()
        later = self.module_records(MODULE).filtered(
            lambda d: d.name == "model_x_studio_test_later"
        )
        self.assertTrue(later.noupdate)

    def test_install_needs_the_last_apply(self):
        self.generate()
        self.assertEqual(self.project.state, "generated")
        self.make_model(self.project, "Studio test later", model="x_studio_test_later")
        self.project.action_apply()
        self.assertEqual(self.project.state, "applied")
        with self.server_actions(), self.assertRaisesRegex(UserError, "again"):
            self.project.action_install_module()

    def test_a_dependency_the_server_does_not_know(self):
        Project = type(self.project)
        depends = ["base", "studio_test_nowhere_module"]
        with patch.object(Project, "_dependencies", lambda self_: depends):
            with self.server_actions():
                with self.assertRaisesRegex(UserError, "studio_test_nowhere_module"):
                    self.project.action_generate()
        self.assertFalse(self.project.generation_count)

    def test_long_texts_keep_their_value(self):
        """A text longer than a line stays one value once the generation
        formats the files: the name of an action, of a rule, a domain."""
        label = "Studio test item " + "with a label that keeps going " * 4
        domain = (
            "['|', ('create_uid', '=', user.id), ('x_name', 'in', ['"
            + "', '".join(["studio"] * 15)
            + "'])]"
        )
        self.project._studio_update_model(self.item, {"name": label.strip()})
        self.project._studio_save_rule(
            {
                "id": self.rule.id,
                "name": label.strip(),
                "model": ITEM,
                "domain": domain,
                "group_ids": self.user_group.ids,
                "perm_read": True,
            }
        )
        self.project.action_apply()
        self.generate()
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        action = views.find(f"record[@id='action_{ITEM}']")
        self.assertEqual(action.find("field[@name='name']").text, label.strip())
        security = etree.fromstring(self.read("security", f"{MODULE}.xml").encode())
        rule = security.find(".//record[@model='ir.rule']")
        self.assertEqual(rule.find("field[@name='name']").text, label.strip())
        self.assertEqual(rule.find("field[@name='domain_force']").text, domain)

    # ── security ───────────────────────────────────────────────────────

    def test_access_rights(self):
        self.generate()
        rows = list(
            csv.DictReader(io.StringIO(self.read("security", "ir.model.access.csv")))
        )
        self.assertEqual(
            rows,
            [
                {
                    "id": "access_res_partner_category_base_group_user",
                    "name": "access_res_partner_category_base_group_user",
                    "model_id:id": "base.model_res_partner_category",
                    "group_id:id": "base.group_user",
                    "perm_read": "1",
                    "perm_write": "1",
                    "perm_create": "1",
                    "perm_unlink": "0",
                },
                *[
                    {
                        "id": f"access_{model}_base_group_user",
                        "name": f"access_{model}_base_group_user",
                        "model_id:id": f"model_{model}",
                        "group_id:id": "base.group_user",
                        **{perm: "1" for perm in PERMS},
                    }
                    for model in (ITEM, TAG)
                ],
            ],
        )
        # The rows of the other modules on the existing model stay theirs.
        self.assertTrue(
            self.env["ir.model.access"].search_count(
                [("model_id.model", "=", "res.partner.category")]
            )
            > 1
        )

    def test_record_rules(self):
        self.generate()
        root = etree.fromstring(self.read("security", f"{MODULE}.xml").encode())
        records = root.findall(".//record")
        self.assertEqual(
            [(r.get("model"), r.get("id")) for r in records],
            [("ir.rule", self.rule.xml_name)],
        )
        record = records[0]
        self.assertEqual(record.find("field[@name='name']").text, "Own items & < all")
        self.assertEqual(record.find("field[@name='domain_force']").text, RULE_DOMAIN)
        self.assertEqual(
            record.find("field[@name='model_id']").get("ref"), f"model_{ITEM}"
        )
        self.assertEqual(
            record.find("field[@name='groups']").get("eval"),
            "[(6, 0, [ref('base.group_user')])]",
        )
        self.assertEqual(record.find("field[@name='perm_create']").get("eval"), "False")

    # ── views, actions, menus ──────────────────────────────────────────

    def test_views_actions_and_menus(self):
        self.generate()
        # The generation formats the file: blank text is left out.
        root = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode(),
            etree.XMLParser(remove_blank_text=True),
        )
        ids = [(node.tag, node.get("id")) for node in root]
        item_form = f"view_{ITEM}_form"
        self.assertEqual(
            ids,
            [
                *[
                    ("record", f"view_{model}_{view_type}")
                    for model in (ITEM, TAG)
                    for view_type in ("form", "list", "search")
                ],
                ("record", "base_view_partner_form_studio"),
                ("record", f"{MODULE}_{item_form}_studio"),
                ("record", f"action_{ITEM}"),
                ("record", f"action_{TAG}"),
                ("menuitem", "menu_app"),
                ("menuitem", f"menu_{ITEM}"),
                ("menuitem", f"menu_{TAG}"),
            ],
        )
        form = root.find(f"record[@id='{item_form}']")
        self.assertEqual(form.find("field[@name='model']").text, ITEM)
        self.assertEqual(form.find("field[@name='priority']").text, "16")
        arch = form.find("field[@name='arch']")[0]
        self.assertEqual(
            etree.tostring(arch, encoding="unicode"),
            etree.tostring(
                etree.fromstring(
                    self.project._studio_default_arch(self.item, "form"),
                    etree.XMLParser(remove_blank_text=True),
                ),
                encoding="unicode",
            ),
        )
        self.assertEqual(bool(arch.find("chatter") is not None), self.chatter)
        inherited = root.find(f"record[@id='{MODULE}_{item_form}_studio']")
        self.assertEqual(
            inherited.find("field[@name='inherit_id']").get("ref"),
            f"{MODULE}.{item_form}",
        )
        self.assertTrue(inherited.xpath(".//field[@name='x_tag']"))
        action = root.find(f"record[@id='action_{ITEM}']")
        self.assertEqual(
            {f.get("name"): f.text or f.get("ref") for f in action},
            {
                "name": "Studio test item",
                "res_model": ITEM,
                "view_mode": "list,form",
                "search_view_id": f"view_{ITEM}_search",
            },
        )
        app = root.find("menuitem[@id='menu_app']")
        self.assertEqual(
            dict(app.attrib),
            {
                "id": "menu_app",
                "name": "Studio test app",
                "web_icon": f"{MODULE},static/description/menu_app.png",
                "sequence": "50",
            },
        )
        self.assertEqual(
            root.find(f"menuitem[@id='menu_{ITEM}']").get("parent"), "menu_app"
        )
        tag_menu = root.find(f"menuitem[@id='menu_{TAG}']")
        self.assertEqual(
            (tag_menu.get("parent"), tag_menu.get("name"), tag_menu.get("action")),
            ("base.menu_custom", "Tags", f"action_{TAG}"),
        )

    # ── checks ─────────────────────────────────────────────────────────

    def test_rights_alone_generate(self):
        """A project that only gives an access right on an existing model
        generates a module of that row."""
        project = self.make_project(
            "studio_test_generate_rights", destination=self.destination
        )
        with self.server_actions(), self.assertRaises(UserError):
            project.action_generate()
        project._studio_set_access(
            [
                {
                    "model": "res.partner.category",
                    "group_id": self.user_group.id,
                    "perm_read": True,
                }
            ]
        )
        project.action_apply()
        with self.server_actions():
            project.action_generate()
        target = os.path.join(self.destination, "studio_test_generate_rights")
        manifest = ast.literal_eval(self.read_in(target, "__manifest__.py"))
        self.assertEqual(manifest["depends"], ["base"])
        self.assertNotIn("application", manifest)
        self.assertNotIn("pre_init_hook", manifest)
        self.assertFalse(os.path.exists(os.path.join(target, "hooks.py")))
        self.assertIn(
            "base.model_res_partner_category,base.group_user,1,0,0,0",
            self.read_in(target, "security", "ir.model.access.csv"),
        )

    @staticmethod
    def read_in(target, *parts):
        with open(os.path.join(target, *parts), encoding="utf-8") as fh:
            return fh.read()

    def test_dependencies_of_rights(self):
        """The groups, existing models, parent menus and the fields named by
        the domains bring their modules."""
        self.assertEqual(
            self.project._dependencies(), ["base", "mail"] if self.chatter else ["base"]
        )
        if not self.chatter:
            return
        project = self.make_project("studio_test_generate_rule_deps")
        project._studio_save_rule(
            {
                "name": "Bounced partners",
                "model": "res.partner",
                "domain": "[('message_bounce', '>', 0)]",
                "perm_read": True,
            }
        )
        self.assertEqual(project._dependencies(), ["base", "mail"])

    def test_model_label_checked_again(self):
        """A label recorded before this module was installed goes through
        the checks of the generation: it becomes a Python string."""
        self.env.cr.execute(
            "UPDATE erplibre_studio_model SET name = %s WHERE id = %s",
            ('Studio "test" item', self.item.id),
        )
        self.item.invalidate_recordset()
        with self.server_actions(), self.assertRaises(UserError):
            self.project.action_generate()

    def test_icon_of_the_studio_without_app_icon(self):
        self.project.app_ids.icon = False
        self.project.action_apply()
        self.generate()
        with file_open("erplibre_studio/static/description/icon.png", "rb") as fh:
            studio_icon = fh.read()
        self.assertEqual(
            self.read("static", "description", "icon.png", mode="rb"), studio_icon
        )
        self.assertEqual(
            base64.b64decode(self.project.code_generator_id.icon_real_image),
            studio_icon,
        )
