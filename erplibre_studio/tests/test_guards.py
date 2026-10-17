# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import StudioCase


@tagged("post_install", "-at_install")
class TestGuards(StudioCase):
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
        self.user = new_test_user(
            self.env,
            login="erplibre_studio_manager",
            groups="base.group_user,base.group_erp_manager",
        )

    def _editor_calls(self, editor):
        project_id = self.project.id
        return [
            lambda: editor.action_customize("res.partner", False, "list"),
            lambda: editor.get_editor_data("res.partner", False, "list", project_id),
            lambda: editor.create_project("Other", "studio_test_other"),
            lambda: editor.apply_operation(
                project_id, "res.partner", False, "list", {"type": "hide"}
            ),
            lambda: editor.project_action(
                project_id, "action_apply", "res.partner", False, "list"
            ),
            lambda: editor.get_comodels(),
            lambda: editor.get_comodels(project_id),
            lambda: editor.get_studio_choices(project_id),
            lambda: editor.create_model(
                project_id, {"name": "Guard"}, "res.partner", False, "list"
            ),
            lambda: editor.update_model(
                project_id, 0, {"name": "Guard"}, "res.partner", False, "list"
            ),
            lambda: editor.remove_model(project_id, 0, "res.partner", False, "list"),
            lambda: editor.update_app(
                project_id, {"name": "Guard"}, "res.partner", False, "list"
            ),
            lambda: editor.set_access(project_id, [], "res.partner", False, "list"),
            lambda: editor.save_rule(
                project_id, {"name": "Guard"}, "res.partner", False, "list"
            ),
            lambda: editor.remove_rule(project_id, 0, "res.partner", False, "list"),
            lambda: editor.check_rule_domain(project_id, "res.partner", "[]"),
            lambda: editor.get_access_existing(project_id, "res.partner"),
        ]

    def test_settings_administrator_runs_the_editor(self):
        """A real user of the Settings group, not the superuser: the access
        checks of the ORM run."""
        admin = new_test_user(
            self.env,
            login="erplibre_studio_admin",
            groups="base.group_user,base.group_system",
        )
        editor = self.Editor.with_user(admin)
        data = editor.get_editor_data("res.partner", False, "list", self.project.id)
        self.assertEqual(data["project"]["id"], self.project.id)
        self.assertEqual(self.project.user_id, admin)
        data = editor.apply_operation(
            self.project.id,
            "res.partner",
            False,
            "list",
            {
                "type": "relabel",
                "target": "//field[@name='email']",
                "value": "Mail",
            },
        )
        self.assertEqual(len(data["changes"]), 2)
        editor.project_action(
            self.project.id, "action_apply", "res.partner", False, "list"
        )
        self.assertEqual(self.project.state, "applied")

    def test_settings_administrator_creates_a_model(self):
        """A Settings administrator, not the superuser, creates a model with
        its menu, rights and rule, applies and reverts it."""
        admin = new_test_user(
            self.env,
            login="erplibre_studio_admin",
            groups="base.group_user,base.group_system",
        )
        editor = self.Editor.with_user(admin)
        # Opening the project makes the user its editor: a new revision.
        data = editor.get_editor_data("res.partner", False, "list", self.project.id)
        revision = data["project"]["revision"]
        data = editor.create_model(
            self.project.id,
            {
                "name": "Guard item",
                "model": "x_studio_test_guard",
                "menu": {"mode": "app"},
            },
            "res.partner",
            False,
            "list",
            revision,
        )
        data = editor.save_rule(
            self.project.id,
            {
                "name": "Guard rule",
                "model": "x_studio_test_guard",
                "domain": "[('create_uid', '=', user.id)]",
                "perm_read": True,
            },
            "res.partner",
            False,
            "list",
            data["project"]["revision"],
        )
        data = editor.project_action(
            self.project.id,
            "action_apply",
            "res.partner",
            False,
            "list",
            data["project"]["revision"],
        )
        self.assertEqual(data["project"]["state"], "applied")
        self.assertIn("x_studio_test_guard", self.env)
        self.assertEqual(len(self.project.created_menu_ids), 2)
        self.assertEqual(len(self.project.created_rule_ids), 1)
        editor.project_action(
            self.project.id,
            "action_revert",
            "res.partner",
            False,
            "list",
            self.project.draft_revision,
        )
        self.assertNotIn("x_studio_test_guard", self.env)

    def test_line_models_for_the_settings_group(self):
        user = self.user
        for model in (
            "erplibre.studio.model",
            "erplibre.studio.access",
            "erplibre.studio.rule",
        ):
            with self.subTest(model=model), self.assertRaises(AccessError):
                self.env[model].with_user(user).search([])

    def test_settings_group_required(self):
        for call in self._editor_calls(self.Editor.with_user(self.user)):
            with self.assertRaises(AccessError):
                call()

    def test_developer_mode_required(self):
        self._debug = False
        for call in self._editor_calls(self.Editor):
            with self.assertRaises(UserError):
                call()
        for action in ("action_apply", "action_revert", "action_discard"):
            with self.subTest(action=action), self.assertRaises(UserError):
                getattr(self.project, action)()

    def test_line_models_need_the_developer_mode(self):
        """The models, access rows and rules of a project, written through
        the ORM as the editor writes them, under the same guard."""
        line = self.make_model(self.project, "Guard item", model="x_studio_test_guard")
        access = self.project.access_line_ids
        rule = self.project._studio_save_rule(
            {"name": "Guard rule", "model": "res.partner", "perm_read": True}
        )
        self._debug = False
        # A Settings administrator: the superuser skips the guard.
        admin = self.env.ref("base.user_admin")
        line, access, rule = (r.with_user(admin) for r in (line, access, rule))
        values = {
            "erplibre.studio.model": {"model": "x_studio_test_guard_b", "name": "B"},
            "erplibre.studio.access": {
                "model": "res.partner.category",
                "group_id": self.env.ref("base.group_system").id,
                "perm_read": True,
            },
            "erplibre.studio.rule": {"name": "B", "model": "res.partner"},
        }
        for record in (line, access, rule):
            with self.subTest(model=record._name):
                with self.assertRaisesRegex(UserError, "developer mode"):
                    self.env[record._name].with_user(admin).create(
                        {"project_id": self.project.id, **values[record._name]}
                    )
                with self.assertRaisesRegex(UserError, "developer mode"):
                    record.write({"sequence": 5} if "sequence" in record else {})
                with self.assertRaisesRegex(UserError, "developer mode"):
                    record.unlink()
        self.assertTrue(line.exists() and access.exists() and rule.exists())
