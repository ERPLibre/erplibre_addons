# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsTestFramework(TransactionCase):
    """Tests for devops.test.plan, devops.test.case,
    devops.test.case.exec, devops.test.plan.exec models."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workspace = cls.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )
        cls.test_plan = cls.env["devops.test.plan"].create(
            {"name": "Test Plan A"}
        )

    # ── Test Plan ──

    def test_plan_create(self):
        plan = self.env["devops.test.plan"].create(
            {"name": "My Plan"}
        )
        self.assertEqual(plan.name, "My Plan")

    def test_plan_with_cases(self):
        case = self.env["devops.test.case"].create(
            {
                "name": "Case 1",
                "test_plan_id": self.test_plan.id,
            }
        )
        self.assertIn(case, self.test_plan.test_case_ids)

    # ── Test Case ──

    def test_case_default_active(self):
        case = self.env["devops.test.case"].create(
            {"name": "Active Case"}
        )
        self.assertTrue(case.active)

    def test_case_system_test_default_false(self):
        case = self.env["devops.test.case"].create(
            {"name": "Normal Case"}
        )
        self.assertFalse(case.is_system_test)

    # ── Test Case Exec ──

    def test_case_exec_is_pass_no_results(self):
        if not self.workspace:
            self.skipTest("No 'me' workspace")
        case = self.env["devops.test.case"].create(
            {"name": "Exec Case"}
        )
        case_exec = self.env["devops.test.case.exec"].create(
            {
                "name": "Exec 1",
                "test_case_id": case.id,
                "workspace_id": self.workspace.id,
            }
        )
        self.assertFalse(case_exec.is_pass)

    def test_case_exec_is_pass_all_pass(self):
        if not self.workspace:
            self.skipTest("No 'me' workspace")
        case = self.env["devops.test.case"].create(
            {"name": "Pass Case"}
        )
        case_exec = self.env["devops.test.case.exec"].create(
            {
                "name": "Exec Pass",
                "test_case_id": case.id,
                "workspace_id": self.workspace.id,
            }
        )
        self.env["devops.test.result"].create(
            {
                "name": "Result 1",
                "is_pass": True,
                "is_finish": True,
                "test_case_exec_id": case_exec.id,
            }
        )
        self.env["devops.test.result"].create(
            {
                "name": "Result 2",
                "is_pass": True,
                "is_finish": True,
                "test_case_exec_id": case_exec.id,
            }
        )
        self.assertTrue(case_exec.is_pass)

    def test_case_exec_is_pass_one_fails(self):
        if not self.workspace:
            self.skipTest("No 'me' workspace")
        case = self.env["devops.test.case"].create(
            {"name": "Fail Case"}
        )
        case_exec = self.env["devops.test.case.exec"].create(
            {
                "name": "Exec Fail",
                "test_case_id": case.id,
                "workspace_id": self.workspace.id,
            }
        )
        self.env["devops.test.result"].create(
            {
                "name": "Result OK",
                "is_pass": True,
                "is_finish": True,
                "test_case_exec_id": case_exec.id,
            }
        )
        self.env["devops.test.result"].create(
            {
                "name": "Result FAIL",
                "is_pass": False,
                "is_finish": True,
                "test_case_exec_id": case_exec.id,
            }
        )
        self.assertFalse(case_exec.is_pass)

    def test_case_exec_has_devops_action_false(self):
        if not self.workspace:
            self.skipTest("No 'me' workspace")
        case = self.env["devops.test.case"].create(
            {"name": "No Action"}
        )
        case_exec = self.env["devops.test.case.exec"].create(
            {
                "name": "Exec No Action",
                "test_case_id": case.id,
                "workspace_id": self.workspace.id,
            }
        )
        self.assertFalse(case_exec.has_devops_action)

    # ── Test Plan Exec ──

    def test_plan_exec_auto_name(self):
        if not self.workspace:
            self.skipTest("No 'me' workspace")
        plan_exec = self.env["devops.test.plan.exec"].create(
            {
                "test_plan_id": self.test_plan.id,
                "workspace_id": self.workspace.id,
            }
        )
        # Name is auto-generated from timestamp in create()
        self.assertTrue(plan_exec.name)

    def test_plan_exec_default_sandbox(self):
        if not self.workspace:
            self.skipTest("No 'me' workspace")
        plan_exec = self.env["devops.test.plan.exec"].create(
            {
                "test_plan_id": self.test_plan.id,
                "workspace_id": self.workspace.id,
            }
        )
        self.assertTrue(plan_exec.run_in_sandbox)

    # ── Test Result ──

    def test_result_create(self):
        result = self.env["devops.test.result"].create(
            {
                "name": "Pass result",
                "is_pass": True,
                "is_finish": True,
            }
        )
        self.assertTrue(result.is_pass)
        self.assertTrue(result.is_finish)

    def test_result_default_active(self):
        result = self.env["devops.test.result"].create(
            {"name": "Active result"}
        )
        self.assertTrue(result.active)
