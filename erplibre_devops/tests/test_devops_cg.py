# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsCg(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workspace = cls.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )

    def test_create_basic(self):
        cg = self.env["devops.cg"].create({"name": "Test CG"})
        self.assertEqual(cg.name, "Test CG")
        self.assertFalse(cg.force_clean_before_generate)

    def test_create_with_module_hierarchy(self):
        cg = self.env["devops.cg"].create(
            {
                "name": "Test Project",
                "module_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "mod_a",
                            "model_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "name": "mod_a.model_x",
                                        "field_ids": [
                                            (
                                                0,
                                                0,
                                                {
                                                    "name": "field_1",
                                                    "type": "char",
                                                },
                                            ),
                                        ],
                                    },
                                ),
                            ],
                        },
                    ),
                ],
            }
        )
        self.assertEqual(len(cg.module_ids), 1)
        self.assertEqual(len(cg.module_ids.model_ids), 1)
        self.assertEqual(len(cg.module_ids.model_ids.field_ids), 1)

    def test_create_with_workspace_context_propagates(self):
        if not self.workspace:
            self.skipTest("No 'me' workspace found")
        cg = (
            self.env["devops.cg"]
            .with_context(
                default_devops_workspace_ids=[self.workspace.id]
            )
            .create(
                {
                    "name": "Workspace CG",
                    "module_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "mod_ws",
                                "model_ids": [
                                    (
                                        0,
                                        0,
                                        {
                                            "name": "mod_ws.model",
                                            "field_ids": [
                                                (
                                                    0,
                                                    0,
                                                    {
                                                        "name": "f1",
                                                        "type": "char",
                                                    },
                                                ),
                                            ],
                                        },
                                    ),
                                ],
                            },
                        ),
                    ],
                }
            )
        )
        self.assertEqual(cg.default_workspace_master.id, self.workspace.id)
        self.assertIn(self.workspace, cg.devops_workspace_ids)
        for mod in cg.module_ids:
            self.assertIn(self.workspace, mod.devops_workspace_ids)
            for model in mod.model_ids:
                self.assertIn(self.workspace, model.devops_workspace_ids)
                for field in model.field_ids:
                    self.assertIn(
                        self.workspace, field.devops_workspace_ids
                    )

    def test_module_cascade_delete(self):
        cg = self.env["devops.cg"].create(
            {
                "name": "To Delete",
                "module_ids": [(0, 0, {"name": "mod_del"})],
            }
        )
        module_id = cg.module_ids[0].id
        cg.unlink()
        self.assertFalse(
            self.env["devops.cg.module"].search([("id", "=", module_id)])
        )
