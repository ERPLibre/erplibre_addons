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
