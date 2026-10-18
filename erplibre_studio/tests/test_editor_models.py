# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StudioCase

MODEL = "x_studio_test_task"


@tagged("post_install", "-at_install")
class TestEditorModels(StudioCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_editor_models")
        self.user_group = self.env.ref("base.group_user")

    def call(self, method, *args, revision=None):
        """An editor RPC on the partner form, at the current revision."""
        if revision is None:
            revision = self.project.draft_revision
        return getattr(self.Editor, method)(
            self.project.id, *args, "res.partner", False, "form", revision
        )

    def create_task(self, **values):
        return self.call(
            "create_model",
            {
                "name": "Studio test task",
                "model": MODEL,
                "menu": {"mode": "app"},
                **values,
            },
        )

    def test_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", False, "form", self.project.id
        )
        self.assertEqual(data["mail_available"], self.mail_available())
        project = data["project"]
        self.assertEqual(
            (
                project["item_count"],
                project["app"],
                project["models"],
                project["access"],
                project["rules"],
            ),
            (0, False, [], [], []),
        )
        data = self.create_task()
        created = data["created_model"]
        self.assertEqual(
            (
                created["model"],
                created["name"],
                created["applied"],
                created["views"],
                created["menu_mode"],
            ),
            (MODEL, "Studio test task", False, {}, "app"),
        )
        project = data["project"]
        # The model, its access row and the app it made.
        self.assertEqual(project["item_count"], 3)
        self.assertEqual(project["app"], {"name": "Studio test task", "icon": False})
        self.assertEqual(
            project["access"],
            [
                {
                    "id": self.project.access_line_ids.id,
                    "model": MODEL,
                    "group": [self.user_group.id, self.user_group.full_name],
                    "perm_read": True,
                    "perm_write": True,
                    "perm_create": True,
                    "perm_unlink": True,
                }
            ],
        )
        self.call(
            "save_rule",
            {
                "name": "Studio test rule",
                "model": MODEL,
                "domain": "[]",
                "group_ids": [self.user_group.id],
                "perm_read": True,
            },
        )
        data = self.call("project_action", "action_apply")
        model = data["project"]["models"][0]
        self.assertTrue(model["applied"])
        self.assertEqual(set(model["views"]), {"form", "list", "search"})
        self.assertEqual(data["project"]["state"], "applied")
        rule = data["project"]["rules"][0]
        self.assertEqual(
            (rule["model"], rule["groups"]),
            (MODEL, [[self.user_group.id, self.user_group.full_name]]),
        )
        # The editor then opens the new model.
        form = self.Editor.get_editor_data(
            MODEL, model["views"]["form"], "form", self.project.id
        )
        self.assertEqual(form["view"]["id"], model["views"]["form"])
        self.assertEqual(form["model"], MODEL)

    def test_operations_need_the_current_revision(self):
        self.create_task()
        line = self.project.new_model_ids
        rule = self.project._studio_save_rule(
            {
                "name": "Studio test rule",
                "model": MODEL,
                "domain": "[]",
                "perm_read": True,
            }
        )
        stale = self.project.draft_revision - 1
        calls = [
            ("create_model", {"name": "Other"}),
            ("update_model", line.id, {"name": "Renamed"}),
            ("remove_model", line.id),
            ("update_app", {"name": "Renamed"}),
            ("set_access", []),
            (
                "save_rule",
                {"id": rule.id, "name": "Renamed", "model": MODEL, "perm_read": True},
            ),
            ("remove_rule", rule.id),
        ]
        for method, *args in calls:
            with self.subTest(method=method), self.assertRaises(UserError):
                self.call(method, *args, revision=stale)
        self.assertEqual(line.name, "Studio test task")
        self.assertEqual(self.project.rule_line_ids, rule)

    def test_update_remove_and_access(self):
        self.create_task()
        line = self.project.new_model_ids
        rule = self.project._studio_save_rule(
            {
                "name": "Studio test rule",
                "model": MODEL,
                "domain": "[]",
                "perm_read": True,
            }
        )
        self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={"ttype": "many2one", "field_description": "Task", "relation": MODEL},
        )
        # A new technical name before Apply moves what names the model.
        data = self.call(
            "update_model",
            line.id,
            {
                "name": "Studio test job",
                "model": "x_studio_test_job",
                "chatter": False,
                "menu": {"name": "Jobs", "sequence": 3},
            },
        )
        self.assertEqual(data["project"]["models"][0]["model"], "x_studio_test_job")
        self.assertEqual((line.menu_name, line.menu_sequence), ("Jobs", 3))
        self.assertEqual(self.project.access_line_ids.model, "x_studio_test_job")
        self.assertEqual(rule.model, "x_studio_test_job")
        payload = self.project.change_ids._payload()
        self.assertEqual(payload["field"]["relation"], "x_studio_test_job")
        data = self.call(
            "set_access",
            [
                {
                    "model": "x_studio_test_job",
                    "group_id": self.user_group.id,
                    "perm_read": True,
                },
                {
                    "model": "res.partner.category",
                    "group_id": self.user_group.id,
                    "perm_read": True,
                },
            ],
        )
        self.assertEqual(len(data["project"]["access"]), 2)
        existing = self.Editor.get_access_existing(
            self.project.id, "res.partner.category"
        )
        self.assertTrue(existing)
        self.assertTrue(all(row["module"] for row in existing))
        self.assertEqual(
            self.Editor.get_access_existing(self.project.id, "x_studio_test_job"), []
        )
        data = self.call(
            "update_app",
            {"name": "Studio test jobs", "icon": "base,static/description/icon.png"},
        )
        self.assertEqual(
            data["project"]["app"],
            {"name": "Studio test jobs", "icon": "base,static/description/icon.png"},
        )
        data = self.call("remove_model", line.id)
        self.assertEqual(data["project"]["models"], [])
        self.assertFalse(self.project.change_ids or self.project.rule_line_ids)
        self.assertEqual(self.project.access_line_ids.model, "res.partner.category")

    def test_choices(self):
        self.create_task()
        self.project.action_apply()
        choices = self.Editor.get_studio_choices(self.project.id)
        self.assertEqual(choices["mail_available"], self.mail_available())
        menus = {m["xml_id"]: m for m in choices["menus"]}
        self.assertIn("base.menu_custom", menus)
        self.assertNotIn("erplibre_studio.erplibre_studio_project_menu", menus)
        self.assertNotIn("studio_test_editor_models.menu_app", menus)
        self.assertTrue(all(m["xml_id"] for m in choices["menus"]))
        groups = {g["xml_id"]: g for g in choices["groups"]}
        self.assertEqual(groups["base.group_user"]["id"], self.user_group.id)
        self.assertEqual(
            choices["icons"][0]["value"], "erplibre_studio,static/description/icon.png"
        )
        models = [m for m, _n in choices["models"]]
        self.assertIn("res.partner", models)
        self.assertIn(MODEL, models)
        self.assertNotIn("base.module.update", models)
        # A model of the draft is offered too.
        self.make_model(self.project, "Studio test draft", model="x_studio_test_draft")
        choices = self.Editor.get_studio_choices(self.project.id)
        self.assertIn(["x_studio_test_draft", "Studio test draft"], choices["models"])
        self.assertIn(
            ["x_studio_test_draft", "Studio test draft"],
            self.Editor.get_comodels(self.project.id),
        )
        self.assertNotIn(
            "x_studio_test_draft", [m for m, _n in self.Editor.get_comodels()]
        )

    def test_editor_opens_the_project_of_the_model(self):
        """Without a project, the editor of a model the studio created opens
        the project that creates it, though the user edited another one
        since; on another model, the last project of the user."""
        self.create_task()
        self.project.action_apply()
        other = self.make_project("studio_test_editor_other")
        other.user_id = self.env.user
        data = self.Editor.get_editor_data("res.partner", False, "form")
        self.assertEqual(data["project"]["id"], other.id)
        data = self.Editor.get_editor_data(MODEL, False, "form")
        self.assertEqual(data["project"]["id"], self.project.id)
        form = self.project.created_view_ids.filtered(lambda v: v.type == "form")
        self.assertEqual(data["view"]["id"], form.id)
        # The editor without a project stays without one.
        data = self.Editor.get_editor_data(MODEL, False, "form", pick_project=False)
        self.assertFalse(data["project"])

    def test_action_that_removes_the_model_on_screen(self):
        """Apply or Revert from the form of a model of the project, which
        the action removes: the payload of the view the editor was opened
        on; once reverted, the form of the model waiting for Apply; without
        the model line, no view."""
        data = self.create_task()
        data = self.call("project_action", "action_apply")
        form_id = data["project"]["models"][0]["views"]["form"]
        line = self.project.new_model_ids

        def on_form(method, *args, fallback=None):
            return getattr(self.Editor, method)(
                self.project.id,
                *args,
                MODEL,
                form_id,
                "form",
                self.project.draft_revision,
                **({"fallback": fallback} if method == "project_action" else {}),
            )

        on_form("remove_model", line.id)
        data = on_form(
            "project_action", "action_apply", fallback=["res.partner", False, "form"]
        )
        self.assertNotIn(MODEL, self.env)
        self.assertTrue(data["view_changed"])
        self.assertEqual((data["model"], data["view_type"]), ("res.partner", "form"))
        # Revert: the model waits for Apply again, its form is the one of a
        # model not created yet.
        data = self.create_task()
        data = self.call("project_action", "action_apply")
        form_id = data["project"]["models"][0]["views"]["form"]
        data = on_form("project_action", "action_revert", fallback=[MODEL, form_id])
        self.assertNotIn(MODEL, self.env)
        self.assertTrue(data["view_changed"])
        self.assertTrue(data["view"]["pending"])
        self.assertEqual(data["project"]["id"], self.project.id)
        # Without the model line either, no view is left.
        self.project._studio_remove_model(self.project.new_model_ids)
        data = self.Editor._fallback_data(self.project, [MODEL, False, "form"])
        self.assertTrue(data["view_gone"])

    def test_check_of_a_domain_keeps_the_draft(self):
        """A check reads: it neither opens the project for the user nor
        changes its revision."""
        editor, other = self.make_users()
        Editor = self.Editor.with_user(editor)
        Editor.get_editor_data("res.partner", False, "form", self.project.id)
        revision = self.project.draft_revision
        result = self.Editor.with_user(other).check_rule_domain(
            self.project.id, "res.partner", "[]"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            (self.project.user_id, self.project.draft_revision), (editor, revision)
        )
        Editor.set_access(self.project.id, [], "res.partner", False, "form", revision)

    def test_names_taken_by_another_project(self):
        self.create_task()
        other = self.make_project("studio_test_editor_other", name="Studio other")
        choices = self.Editor.get_studio_choices(other.id)
        self.assertIn(MODEL, choices["taken_models"])
        self.assertIn("res.partner", choices["taken_models"])
        with self.assertRaisesRegex(UserError, "Studio test"):
            other._studio_create_model({"name": "Task", "model": MODEL})
