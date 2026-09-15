# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase


class TestDevopsExec(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workspace = cls.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )

    def _create_exec(self, vals=None):
        defaults = {"cmd": "echo hello"}
        if self.workspace:
            defaults["devops_workspace"] = self.workspace.id
        if vals:
            defaults.update(vals)
        return self.env["devops.exec"].create(defaults)

    # ── Computed name ──

    def test_name_contains_workspace_id(self):
        rec = self._create_exec()
        if self.workspace:
            self.assertIn(
                f"workspace {self.workspace.id}", rec.name
            )

    def test_name_contains_module(self):
        rec = self._create_exec({"module": "sale"})
        self.assertIn("sale", rec.name)

    # ── Time duration ──

    def test_duration_with_start_and_stop(self):
        now = datetime.now()
        rec = self._create_exec(
            {
                "exec_start_date": now,
                "exec_stop_date": now + timedelta(seconds=120),
            }
        )
        self.assertEqual(rec.exec_time_duration, 120)

    def test_duration_without_stop_is_false(self):
        rec = self._create_exec({"exec_start_date": datetime.now()})
        self.assertFalse(rec.exec_time_duration)

    def test_time_duration_result_format(self):
        now = datetime.now()
        rec = self._create_exec(
            {
                "exec_start_date": now,
                "exec_stop_date": now + timedelta(seconds=3661),
            }
        )
        # 3661 seconds = 1:01:01
        self.assertIn("1:01:01", rec.time_duration_result)

    # ── Execution finish ──

    def test_execution_not_finished(self):
        rec = self._create_exec()
        rec.write({"exec_stop_date": False})
        self.assertFalse(rec.execution_finish)

    def test_execution_finished(self):
        rec = self._create_exec({"exec_stop_date": datetime.now()})
        self.assertTrue(rec.execution_finish)

    # ── Log all (combined stdout + stderr) ──

    def test_log_all_empty(self):
        rec = self._create_exec()
        self.assertEqual(rec.log_all, "")

    def test_log_all_stdout_only(self):
        rec = self._create_exec({"log_stdout": "output line"})
        self.assertEqual(rec.log_all, "output line")

    def test_log_all_stderr_only(self):
        rec = self._create_exec({"log_stderr": "error line"})
        self.assertEqual(rec.log_all, "error line")

    def test_log_all_combined(self):
        rec = self._create_exec(
            {"log_stdout": "out\n", "log_stderr": "err\n"}
        )
        self.assertIn("out", rec.log_all)
        self.assertIn("err", rec.log_all)

    # ── compute_error() ──

    def test_compute_error_finds_errors(self):
        rec = self._create_exec(
            {
                "log_stdout": "INFO starting\nERROR something broke\nINFO done",
            }
        )
        rec.compute_error()
        self.assertTrue(
            self.env["devops.log.error"].search(
                [("exec_id", "=", rec.id)]
            )
        )

    def test_compute_error_finds_warnings(self):
        rec = self._create_exec(
            {
                "log_stdout": "INFO starting\nWARNING deprecated call\nINFO done",
            }
        )
        rec.compute_error()
        self.assertTrue(
            self.env["devops.log.warning"].search(
                [("exec_id", "=", rec.id)]
            )
        )

    def test_compute_error_ignores_known_errors(self):
        rec = self._create_exec(
            {
                "log_stdout": "ERROR fetchmail_notify_error_to_sender something",
            }
        )
        rec.compute_error()
        errors = self.env["devops.log.error"].search(
            [("exec_id", "=", rec.id)]
        )
        self.assertFalse(errors)

    def test_compute_error_ignores_known_warnings(self):
        rec = self._create_exec(
            {
                "log_stdout": "WARNING have the same label: blah",
            }
        )
        rec.compute_error()
        warnings = self.env["devops.log.warning"].search(
            [("exec_id", "=", rec.id)]
        )
        self.assertFalse(warnings)

    def test_compute_error_strips_keyword_from_detection(self):
        """Keywords in keyword_error_to_remove should not trigger errors."""
        rec = self._create_exec(
            {
                "log_stdout": "devops.cg.field.has_error is a field name",
            }
        )
        rec.compute_error()
        errors = self.env["devops.log.error"].search(
            [("exec_id", "=", rec.id)]
        )
        # The keyword "error" was removed from line before detection
        self.assertFalse(errors)

    def test_compute_error_no_errors_in_clean_log(self):
        rec = self._create_exec(
            {
                "log_stdout": "INFO all good\nINFO done",
            }
        )
        rec.compute_error()
        errors = self.env["devops.log.error"].search(
            [("exec_id", "=", rec.id)]
        )
        warnings = self.env["devops.log.warning"].search(
            [("exec_id", "=", rec.id)]
        )
        self.assertFalse(errors)
        self.assertFalse(warnings)

    def test_compute_error_both_error_and_warning(self):
        rec = self._create_exec(
            {
                "log_stdout": (
                    "ERROR critical fail\n"
                    "WARNING deprecation notice\n"
                ),
            }
        )
        rec.compute_error()
        errors = self.env["devops.log.error"].search(
            [("exec_id", "=", rec.id)]
        )
        warnings = self.env["devops.log.warning"].search(
            [("exec_id", "=", rec.id)]
        )
        self.assertTrue(errors)
        self.assertTrue(warnings)

    # ── Default values ──

    def test_default_active(self):
        rec = self._create_exec()
        self.assertTrue(rec.active)

    def test_default_start_date_set(self):
        rec = self._create_exec()
        self.assertTrue(rec.exec_start_date)
