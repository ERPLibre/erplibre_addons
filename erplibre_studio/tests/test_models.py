# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
from unittest.mock import patch

from lxml import etree
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from ..models.erplibre_studio_project import (
    DEFAULT_APP_ICON,
    MODEL_VIEW_PRIORITY,
    STUDIO_PRIORITY,
)
from .common import StudioCase

MODEL = "x_studio_test_item"


@tagged("post_install", "-at_install")
class TestModels(StudioCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_models")

    def ref(self, name, model, module="studio_test_models"):
        data = self.module_records(module, model).filtered(lambda d: d.name == name)
        return self.env[model].browse(data.res_id).exists()

    def item_line(self, **values):
        return self.make_model(self.project, "Studio test item", model=MODEL, **values)

    # ── draft ───────────────────────────────────────────────────────────

    def test_model_name_rules(self):
        for name in (
            "studio_item",
            "x_",
            "x_1item",
            "x_Item",
            "x_item-a",
            "x_item.a",
            "x_" + "a" * 49,
        ):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.make_model(self.project, "Item", model=name)
        # A model of the registry.
        self.env["ir.model"].create(
            {"name": "Hand made", "model": "x_studio_test_hand"}
        )
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.make_model(self.project, "Item", model="x_studio_test_hand")
        # Another project creates it.
        line = self.item_line()
        other = self.make_project("studio_test_models_other")
        with self.assertRaisesRegex(UserError, "Studio test"):
            with self.env.cr.savepoint():
                self.make_model(other, "Item", model=MODEL)
        renamed = self.make_model(other, "Other item", model="x_studio_test_other")
        with self.assertRaisesRegex(UserError, "Studio test"):
            with self.env.cr.savepoint():
                other._studio_update_model(renamed, {"model": MODEL})
        # The name follows the label; it is free.
        free = self.make_model(self.project, "Studio test item")
        self.assertEqual(free.model, f"{MODEL}_2")
        digits = self.make_model(self.project, "2026 item")
        self.assertEqual(digits.model, "x_model_2026_item")
        # Immutable once applied.
        self.project.action_apply()
        self.assertTrue(line.applied)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            line.model = "x_studio_test_renamed"
        late = self.make_model(self.project, "Studio test late")
        late.model = "x_studio_test_renamed"
        self.assertFalse(late.applied)
        self.assertEqual(self.project.access_line_ids[-1:].model, late.model)

    def test_label_app_and_icon(self):
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.make_model(self.project, " ")
        line = self.item_line(
            menu={"mode": "app", "app_icon": "base,static/description/icon.png"}
        )
        app = self.project.app_ids
        self.assertEqual(
            (app.name, app.icon, app.xml_name, line.app_id),
            ("Studio test item", "base,static/description/icon.png", "menu_app", app),
        )
        # A model in an app needs the app, an app its name.
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            line.app_id = False
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            app.name = " "
        for icon in (
            "base,static/description/settings.png",
            "base,static/src/img/icon.png",
            "studio_test_nowhere,static/description/icon.png",
            "base/static/description/icon.png",
        ):
            with self.subTest(icon=icon), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    app.icon = icon
        icons = self.Project._studio_app_icons()
        self.assertEqual(icons[0]["value"], DEFAULT_APP_ICON)
        self.assertEqual(
            icons[0]["url"], "/erplibre_studio/static/description/icon.png"
        )
        self.assertIn("base,static/description/icon.png", [i["value"] for i in icons])
        # A second model goes in the same app.
        second = self.make_model(
            self.project, "Second", menu={"mode": "app", "app_name": "Ignored"}
        )
        self.assertEqual(self.project.app_ids, app)
        self.assertEqual((line | second).mapped("menu_mode"), ["app", "app"])
        self.assertEqual(second.app_id, app)

    def test_menu_parent(self):
        loose = self.env["ir.ui.menu"].create({"name": "Studio test loose"})
        with_action = self.env.ref("erplibre_studio.erplibre_studio_project_menu")
        for parent in (loose, with_action):
            with self.subTest(menu=parent.name), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.item_line(menu={"mode": "menu", "parent_id": parent.id})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.item_line(menu={"mode": "menu"})
        parent = self.env.ref("base.menu_custom")
        line = self.item_line(
            menu={"mode": "menu", "parent_id": parent.id, "name": "Items"}
        )
        self.assertFalse(self.project.app_ids)
        self.project.action_apply()
        menu = self.ref(f"menu_{MODEL}", "ir.ui.menu")
        self.assertEqual((menu.parent_id, menu.name), (parent, "Items"))
        self.assertFalse(self.ref("menu_app", "ir.ui.menu"))
        self.assertEqual(self.project.created_menu_ids, menu)
        # The menus of the project are not parents.
        other = self.make_project("studio_test_models_other")
        other_line = self.make_model(other, "Other item", menu={"mode": "app"})
        other.action_apply()
        app = other.created_menu_ids.filtered(lambda m: not m.parent_id)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            other_line.write({"menu_mode": "menu", "menu_parent_id": app.id})
        # Another project goes under it: this app cannot be removed.
        line.write({"menu_mode": "menu", "menu_parent_id": app.id})
        self.project.action_apply()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            other.action_revert()

    def test_chatter_needs_mail(self):
        with patch.object(
            type(self.Project), "_studio_mail_available", lambda self: False
        ):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self.item_line(chatter=True)
            self.assertFalse(
                self.Editor.get_editor_data(
                    "res.partner", False, "form", self.project.id
                )["mail_available"]
            )

    def test_draft_leaves_the_registry(self):
        line = self.item_line()
        self.assertNotIn(MODEL, self.env)
        self.assertFalse(self.env["ir.model"]._get(MODEL))
        self.assertFalse(line.applied)
        # The model, its access row and its app.
        self.assertEqual(self.project.item_count, 3)
        self.assertEqual(self.project.state, "draft")
        self.assertEqual(len(self.project.access_line_ids), 1)

    # ── apply ───────────────────────────────────────────────────────────

    def test_apply_creates_the_model_its_views_action_menu_and_access(self):
        line = self.item_line(menu={"mode": "app"})
        self.project.action_apply()
        self.assertEqual(self.project.state, "applied")
        self.assertTrue(line.applied)
        model = self.ref(f"model_{MODEL}", "ir.model")
        self.assertEqual(
            (model.model, model.state, model.name),
            (MODEL, "manual", "Studio test item"),
        )
        self.assertEqual(line.ir_model_id, model)
        x_name = self.env["ir.model.fields"]._get(MODEL, "x_name")
        self.assertEqual((x_name.ttype, x_name.required), ("char", True))
        views = {}
        for view_type in ("form", "list", "search"):
            view = self.ref(f"view_{MODEL}_{view_type}", "ir.ui.view")
            self.assertEqual(
                (view.type, view.mode, view.priority, view.model),
                (view_type, "primary", MODEL_VIEW_PRIORITY, MODEL),
            )
            views[view_type] = view
        self.assertEqual(
            self.project.created_view_ids,
            views["form"] | views["list"] | views["search"],
        )
        form = etree.fromstring(views["form"].arch)
        self.assertEqual(form.get("string"), "Studio test item")
        self.assertTrue(
            form.xpath("//sheet/div[@class='oe_title']/h1/field[@name='x_name']")
        )
        self.assertTrue(
            form.xpath("//group[@name='studio_main']/group[@name='studio_left']")
        )
        self.assertFalse(form.xpath("//chatter"))
        action = self.ref(f"action_{MODEL}", "ir.actions.act_window")
        self.assertEqual(
            (action.res_model, action.view_mode, action.search_view_id),
            (MODEL, "list,form", views["search"]),
        )
        app = self.ref("menu_app", "ir.ui.menu")
        self.assertEqual(
            (app.name, app.web_icon, app.parent_id.id),
            ("Studio test item", DEFAULT_APP_ICON, False),
        )
        self.assertTrue(app.web_icon_data)
        menu = self.ref(f"menu_{MODEL}", "ir.ui.menu")
        self.assertEqual((menu.parent_id, menu.action), (app, action))
        self.assertEqual(self.project.created_menu_ids, app | menu)
        access = self.ref(f"access_{MODEL}_base_group_user", "ir.model.access")
        self.assertEqual(
            (access.model_id, access.group_id, access.perm_read, access.perm_unlink),
            (model, self.env.ref("base.group_user"), True, True),
        )
        self.assertEqual(self.project.created_access_ids, access)
        self.assertEqual(self.project.created_model_ids, model)
        self.assertEqual(self.project.created_action_ids, action)
        record = self.env[MODEL].create({"x_name": "First"})
        self.assertEqual(record.display_name, "First")
        self.assertEqual(self.Editor._resolve_view(MODEL, False, "form"), views["form"])
        self.assertEqual(self.Editor._resolve_view(MODEL, False, "list"), views["list"])

        # Applying again: the same records, no new external id.
        count = len(self.module_records("studio_test_models"))
        self.assertEqual(count, 8)
        self.project.action_apply()
        self.assertEqual(len(self.module_records("studio_test_models")), count)
        self.assertEqual(self.ref(f"model_{MODEL}", "ir.model"), model)
        self.assertEqual(self.project.created_menu_ids, app | menu)
        self.assertEqual(
            self.project.created_view_ids,
            views["form"] | views["list"] | views["search"],
        )

        # A new label, menu label and app name update them.
        line.write(
            {"name": "Studio test thing", "menu_name": "Things", "menu_sequence": 7}
        )
        self.project.app_ids.name = "Studio test app"
        self.assertEqual(self.project.state, "draft")
        self.project.action_apply()
        self.assertEqual(self.project.state, "applied")
        self.assertEqual(
            self.ref(f"model_{MODEL}", "ir.model").name, "Studio test thing"
        )
        self.assertEqual(action.name, "Studio test thing")
        self.assertEqual(
            (menu.name, menu.sequence, app.name), ("Things", 7, "Studio test app")
        )
        form = etree.fromstring(views["form"].arch)
        self.assertEqual(form.get("string"), "Studio test thing")
        self.assertEqual(len(self.module_records("studio_test_models")), count)

    def test_chatter(self):
        if not self.mail_available():
            self.skipTest("mail is not installed")
        line = self.item_line(chatter=True)
        self.project.action_apply()
        model = line.ir_model_id
        self.assertTrue(model.is_mail_thread and model.is_mail_activity)
        self.assertIn("message_ids", self.env[MODEL]._fields)
        self.assertIn("activity_ids", self.env[MODEL]._fields)
        form = self.ref(f"view_{MODEL}_form", "ir.ui.view")
        self.assertEqual(etree.fromstring(form.arch)[-1].tag, "chatter")
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            line.chatter = False
        # A chatter added later.
        later = self.make_model(
            self.project, "Studio test later", model="x_studio_test_later"
        )
        self.project.action_apply()
        self.assertNotIn("message_ids", self.env["x_studio_test_later"]._fields)
        later.chatter = True
        self.project.action_apply()
        self.assertTrue(later.ir_model_id.is_mail_thread)
        self.assertIn("message_ids", self.env["x_studio_test_later"]._fields)
        form = self.ref("view_x_studio_test_later_form", "ir.ui.view")
        self.assertTrue(etree.fromstring(form.arch).xpath("/form/chatter"))
        record = self.env["x_studio_test_later"].create({"x_name": "Later"})
        record.message_post(body="Studio test message")
        # The models leave with their messages.
        self.project.action_revert()
        self.assertNotIn("x_studio_test_later", self.env)

    def test_removed_model_leaves_the_database(self):
        keep = self.item_line()
        gone = self.make_model(
            self.project, "Studio test gone", model="x_studio_test_gone"
        )
        self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={
                "ttype": "many2one",
                "field_description": "Gone",
                "relation": "x_studio_test_gone",
            },
        )
        self.project.action_apply()
        self.assertEqual(
            self.env["ir.model.fields"]._get("res.partner", "x_gone").relation,
            "x_studio_test_gone",
        )
        self.env["x_studio_test_gone"].create({"x_name": "Gone"})
        gone_records = gone._studio_views()
        self.assertEqual(len(gone_records), 3)
        gone.unlink()
        # The many2one to it left the draft with it.
        self.assertFalse(self.project.change_ids)
        self.assertEqual(self.project.access_line_ids.mapped("model"), [MODEL])
        self.project.action_apply()
        self.assertNotIn("x_studio_test_gone", self.env)
        self.assertFalse(self.env["ir.model"]._get("x_studio_test_gone"))
        self.assertFalse(self.env["ir.model.fields"]._get("res.partner", "x_gone"))
        for view in gone_records.values():
            self.assertFalse(view.exists())
        names = self.module_records("studio_test_models").mapped("name")
        self.assertFalse([n for n in names if "gone" in n])
        self.assertTrue(keep.applied)
        self.assertEqual(self.project.created_model_ids.mapped("model"), [MODEL])
        self.assertEqual(len(self.project.created_view_ids), 3)
        self.assertEqual(self.project.state, "applied")

    def test_edit_a_new_model_then_revert(self):
        line = self.item_line()
        self.project.action_apply()
        form = line._studio_views()["form"]
        self.op(
            self.project,
            form,
            type="add_field",
            target="//group[@name='studio_left']",
            position="inside",
            field={"ttype": "char", "field_description": "Code"},
        )
        self.project.action_apply()
        studio = self.project.studio_view_ids
        self.assertEqual(
            (studio.inherit_id, studio.priority, studio.mode),
            (form, STUDIO_PRIORITY, "extension"),
        )
        arch = etree.fromstring(self.env[MODEL].get_view(form.id, "form")["arch"])
        self.assertTrue(
            arch.xpath("//group[@name='studio_left']/field[@name='x_code']")
        )
        self.env[MODEL].create({"x_name": "Kept?", "x_code": "K"})
        result = self.project.action_revert()
        self.assertEqual(result["params"]["type"], "warning")
        self.assertIn("1", result["params"]["message"])
        self.assertNotIn(MODEL, self.env)
        self.assertFalse(self.module_records("studio_test_models"))
        self.assertFalse(form.exists() or studio.exists())
        for name in (
            "created_model_ids",
            "created_view_ids",
            "created_action_ids",
            "created_menu_ids",
            "created_access_ids",
            "studio_view_ids",
            "field_ids",
        ):
            self.assertFalse(self.project[name], name)
        # The lines stay, the change of the removed view goes with it.
        self.assertEqual(self.project.new_model_ids, line)
        self.assertEqual(len(self.project.access_line_ids), 1)
        self.assertFalse(self.project.change_ids)
        self.assertEqual(self.project.state, "draft")
        self.assertFalse(line.applied)
        self.project.action_apply()
        self.assertIn(MODEL, self.env)
        self.assertEqual(len(self.module_records("studio_test_models")), 8)

    def test_revert_refused_while_another_project_needs_the_model(self):
        self.item_line()
        self.project.action_apply()
        other = self.make_project("studio_test_models_other")
        self.op(
            other,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={"ttype": "many2one", "field_description": "Item", "relation": MODEL},
        )
        other.action_apply()
        with self.assertRaisesRegex(UserError, "res.partner.x_item"):
            with self.env.cr.savepoint():
                self.project.action_revert()
        other.action_revert()
        # A field of another project on the model.
        form = self.ref(f"view_{MODEL}_form", "ir.ui.view")
        self.op(
            other,
            form,
            type="add_field",
            target="//group[@name='studio_right']",
            position="inside",
            field={"ttype": "integer", "field_description": "Size"},
        )
        with self.assertRaisesRegex(UserError, "change of the project"):
            with self.env.cr.savepoint():
                self.project.action_revert()
        other.action_apply()
        with self.assertRaisesRegex(UserError, f"{MODEL}.x_size"):
            with self.env.cr.savepoint():
                self.project.action_revert()
        other.action_revert()
        other.change_ids.unlink()
        # An access row of another project on it.
        other._studio_set_access(
            [
                {
                    "model": MODEL,
                    "group_id": self.env.ref("base.group_system").id,
                    "perm_read": True,
                }
            ]
        )
        with self.assertRaisesRegex(UserError, "access row of the project"):
            with self.env.cr.savepoint():
                self.project.action_revert()
        other._studio_set_access([])
        self.project.action_revert()
        self.assertNotIn(MODEL, self.env)

    def test_discard_restores_every_line_kind(self):
        line = self.item_line()
        group = self.env.ref("base.group_system")
        self.project._studio_save_rule(
            {
                "name": "Own",
                "model": MODEL,
                "domain": "[('create_uid', '=', user.id)]",
                "group_ids": [group.id],
                "perm_read": True,
            }
        )
        self.project.action_apply()
        snapshot = self.project.applied_snapshot
        self.assertEqual(
            set(json.loads(snapshot)),
            {"apps", "groups", "changes", "models", "access", "rules"},
        )
        line.name = "Studio test renamed"
        self.project._studio_set_access([])
        self.project.rule_line_ids.unlink()
        self.make_model(self.project, "Studio test extra", model="x_studio_test_extra")
        self.project.app_ids.name = "Studio test other app"
        self.assertEqual(self.project.state, "draft")
        self.project.action_discard()
        self.assertEqual(self.project.state, "applied")
        self.assertEqual(self.project._current_snapshot(), snapshot)
        self.assertEqual(self.project.new_model_ids.mapped("model"), [MODEL])
        self.assertEqual(self.project.rule_line_ids.xml_name, f"rule_{MODEL}_1")
        self.assertEqual(self.project.rule_line_ids.group_ids, group)
        self.assertEqual(self.project.app_ids.name, "Studio test item")
        self.assertEqual(self.project.new_model_ids.app_id, self.project.app_ids)
        self.assertTrue(self.project.new_model_ids.applied)
        # Without an Apply, discarding empties the draft.
        fresh = self.make_project("studio_test_models_fresh")
        self.make_model(fresh, "Studio test fresh", model="x_studio_test_fresh")
        fresh.action_discard()
        self.assertFalse(fresh.item_count or fresh.app_ids)

    def test_project_of_views_keeps_its_snapshot(self):
        """A project with changes of views only keeps the snapshot of the
        projects recorded before the models: it stays applied."""
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='email']",
            value="Mail",
        )
        self.project.action_apply()
        self.assertIsInstance(json.loads(self.project.applied_snapshot), list)
        self.project._update_state()
        self.assertEqual(self.project.state, "applied")
        loaded = self.project._studio_load_snapshot(self.project.applied_snapshot)
        self.assertEqual(len(loaded["changes"]), 1)
        self.assertEqual(loaded["models"], [])

    def test_many2one_to_a_model_of_the_draft(self):
        self.item_line()
        comodels = self.Editor.get_comodels(self.project.id)
        self.assertIn([MODEL, "Studio test item"], comodels)
        other = self.make_project("studio_test_models_other")
        self.assertNotIn(MODEL, [m for m, _n in self.Editor.get_comodels(other.id)])
        self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={"ttype": "many2one", "field_description": "Item", "relation": MODEL},
        )
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.op(
                other,
                self.form,
                type="add_field",
                target="//field[@name='vat']",
                position="after",
                field={
                    "ttype": "many2one",
                    "field_description": "Item",
                    "relation": MODEL,
                },
            )
        self.project.action_apply()
        field = self.env["ir.model.fields"]._get("res.partner", "x_item")
        self.assertEqual((field.ttype, field.relation), ("many2one", MODEL))
        item = self.env[MODEL].create({"x_name": "Item"})
        partner = self.env["res.partner"].create({"name": "Studio", "x_item": item.id})
        self.assertEqual(partner.x_item, item)

    def test_unlink_and_rename(self):
        self.item_line()
        self.project.action_apply()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.project.unlink()
        count = len(self.module_records("studio_test_models"))
        self.project.module_name = "studio_test_models_renamed"
        self.assertFalse(self.module_records("studio_test_models"))
        self.assertEqual(len(self.module_records("studio_test_models_renamed")), count)
        self.assertTrue(self.project.new_model_ids.applied)
        self.project.action_apply()
        self.assertEqual(len(self.module_records("studio_test_models_renamed")), count)
        self.project.action_revert()
        self.project.unlink()

    def test_open_editor_on_the_new_model(self):
        line = self.item_line()
        # Before Apply, on the default form of the model, not created yet.
        action = self.project.action_open_editor()
        self.assertEqual(
            (action["params"]["res_model"], action["params"]["view_id"]),
            (MODEL, False),
        )
        self.project.action_apply()
        action = self.project.action_open_editor()
        self.assertEqual(action["params"]["res_model"], MODEL)
        self.assertEqual(action["params"]["view_id"], line._studio_views()["form"].id)
