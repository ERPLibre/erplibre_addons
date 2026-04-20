# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase


class TestDevopsExecBundle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workspace = cls.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )

    def _create_bundle(self, vals=None):
        defaults = {"description": "Test bundle"}
        if self.workspace:
            defaults["devops_workspace"] = self.workspace.id
        if vals:
            defaults.update(vals)
        return self.env["devops.exec.bundle"].create(defaults)

    # ── Name compute ──

    def test_name_contains_description(self):
        bundle = self._create_bundle({"description": "Deploy"})
        self.assertIn("Deploy", bundle.name)

    def test_name_without_description(self):
        bundle = self._create_bundle({"description": False})
        # Should not crash, name is just the id
        self.assertTrue(bundle.name is not False)

    # ── Time duration ──

    def test_duration_calculation(self):
        now = datetime.now()
        bundle = self._create_bundle()
        bundle.write(
            {
                "exec_start_date": now,
                "exec_stop_date": now + timedelta(seconds=60),
            }
        )
        self.assertEqual(bundle.exec_time_duration, 60)

    def test_duration_without_stop(self):
        bundle = self._create_bundle()
        self.assertFalse(bundle.exec_time_duration)

    def test_time_duration_result_formatted(self):
        now = datetime.now()
        bundle = self._create_bundle()
        bundle.write(
            {
                "exec_start_date": now,
                "exec_stop_date": now + timedelta(seconds=90),
            }
        )
        self.assertIn("1:30", bundle.time_duration_result)

    # ── Execution finish ──

    def test_not_finished_without_stop_date(self):
        bundle = self._create_bundle()
        self.assertFalse(bundle.execution_finish)

    def test_finished_with_stop_date(self):
        bundle = self._create_bundle()
        bundle.write({"exec_stop_date": datetime.now()})
        self.assertTrue(bundle.execution_finish)

    # ── Parent-child hierarchy ──

    def test_parent_child_relation(self):
        parent = self._create_bundle({"description": "Parent"})
        child = self._create_bundle(
            {"description": "Child", "parent_id": parent.id}
        )
        self.assertEqual(child.parent_id, parent)
        self.assertIn(child, parent.child_ids)

    def test_get_parent_root_no_parent(self):
        bundle = self._create_bundle()
        self.assertEqual(bundle.get_parent_root(), bundle)

    def test_get_parent_root_nested(self):
        root = self._create_bundle({"description": "Root"})
        mid = self._create_bundle(
            {"description": "Mid", "parent_id": root.id}
        )
        leaf = self._create_bundle(
            {"description": "Leaf", "parent_id": mid.id}
        )
        self.assertEqual(leaf.get_parent_root(), root)

    # ── get_last_exec ──

    def test_get_last_exec_empty(self):
        bundle = self._create_bundle()
        self.assertFalse(bundle.get_last_exec())

    def test_get_last_exec_returns_last(self):
        bundle = self._create_bundle()
        exec1 = self.env["devops.exec"].create(
            {
                "cmd": "echo 1",
                "devops_exec_bundle_id": bundle.id,
            }
        )
        exec2 = self.env["devops.exec"].create(
            {
                "cmd": "echo 2",
                "devops_exec_bundle_id": bundle.id,
            }
        )
        last = bundle.get_last_exec()
        self.assertEqual(last, exec2)

    # ── Defaults ──

    def test_default_active(self):
        bundle = self._create_bundle()
        self.assertTrue(bundle.active)

    def test_default_start_date(self):
        bundle = self._create_bundle()
        self.assertTrue(bundle.exec_start_date)
