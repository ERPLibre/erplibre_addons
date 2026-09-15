# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsCodeTodo(TransactionCase):
    def test_create(self):
        todo = self.env["devops.code.todo"].create(
            {
                "name": "TODO fix this bug",
                "filename": "models/devops_system.py",
                "lineno": 42,
            }
        )
        self.assertEqual(todo.name, "TODO fix this bug")
        self.assertEqual(todo.lineno, 42)

    def test_default_active(self):
        todo = self.env["devops.code.todo"].create(
            {"name": "TODO something"}
        )
        self.assertTrue(todo.active)

    def test_default_sequence(self):
        todo = self.env["devops.code.todo"].create(
            {"name": "TODO ordered"}
        )
        self.assertEqual(todo.sequence, 10)

    def test_with_module(self):
        module = self.env["devops.cg.module"].create(
            {"name": "test_mod"}
        )
        todo = self.env["devops.code.todo"].create(
            {
                "name": "TODO in module",
                "module_id": module.id,
            }
        )
        self.assertEqual(todo.module_id, module)

    def test_with_workspace(self):
        workspace = self.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )
        if not workspace:
            self.skipTest("No 'me' workspace")
        todo = self.env["devops.code.todo"].create(
            {
                "name": "TODO workspace",
                "workspace_id": workspace.id,
            }
        )
        self.assertEqual(todo.workspace_id, workspace)

    def test_path_fields(self):
        todo = self.env["devops.code.todo"].create(
            {
                "name": "TODO paths",
                "path_absolute": "/home/user/project/models/test.py",
                "path_module": "models/test.py",
            }
        )
        self.assertEqual(
            todo.path_absolute, "/home/user/project/models/test.py"
        )
        self.assertEqual(todo.path_module, "models/test.py")
