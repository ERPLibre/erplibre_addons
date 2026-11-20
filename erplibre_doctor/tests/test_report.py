# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import date
from unittest.mock import patch

from odoo.addons.erplibre_info import runner
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import MODULE_ABSENT, MODULE_UNINSTALLED, DoctorCase


@tagged("post_install", "-at_install")
class TestReport(DoctorCase):
    def test_suggested_modules(self):
        report = self.new_report()
        self.assertEqual(report.state, "done")
        self.assertEqual(report.image, self.image)
        self.assertRegex(report.name, r"^DOCTOR/\d{4}/\d{2}/\d{2}/\d{4}$")
        lines = {line.name: line for line in report.line_ids}
        self.assertEqual(
            list(report.line_ids.mapped("name")),
            ["base", MODULE_UNINSTALLED, MODULE_ABSENT],
        )
        self.assertEqual(lines["base"].state_found, "installed")
        self.assertFalse(lines["base"].problem)
        self.assertEqual(lines[MODULE_UNINSTALLED].state_found, "uninstalled")
        self.assertTrue(lines[MODULE_UNINSTALLED].problem)
        self.assertTrue(lines[MODULE_UNINSTALLED].can_install)
        self.assertEqual(lines[MODULE_ABSENT].state_found, "absent")
        self.assertTrue(lines[MODULE_ABSENT].problem)
        self.assertFalse(lines[MODULE_ABSENT].can_install)
        self.assertEqual(report.problem_count, 2)
        self.assertEqual(report.installable_count, 1)

    def test_name_counts_from_one_each_day(self):
        first, second = date(2000, 1, 1), date(2000, 1, 2)
        self.assertEqual(
            self.Report._next_name(first), "DOCTOR/2000/01/01/0001"
        )
        self.assertEqual(
            self.Report._next_name(first), "DOCTOR/2000/01/01/0002"
        )
        self.assertEqual(
            self.Report._next_name(second), "DOCTOR/2000/01/02/0001"
        )
        self.assertEqual(
            self.Report._next_name(first), "DOCTOR/2000/01/01/0003"
        )
        ranges = self.env["ir.sequence.date_range"].search(
            [
                (
                    "sequence_id",
                    "=",
                    self.env.ref(
                        "erplibre_doctor.seq_erplibre_doctor_report"
                    ).id,
                ),
                ("date_from", "in", [first, second]),
            ]
        )
        self.assertEqual(
            sorted((r.date_from, r.date_to) for r in ranges),
            [(first, first), (second, second)],
        )

    def test_a_new_analysis_keeps_the_previous_report(self):
        first = self.new_report()
        action = first.action_new_analysis()
        self.assertNotEqual(action["res_id"], first.id)
        self.assertEqual(len(first.line_ids), 3)

    def assert_confirmation(self, action):
        view = self.env.ref(
            "erplibre_doctor.base_module_upgrade_view_form_doctor"
        )
        self.assertEqual(action["res_model"], "base.module.upgrade")
        self.assertEqual(action["views"], [(view.id, "form")])
        self.assertEqual(action["target"], "new")

    def test_install_missing_opens_the_confirmation(self):
        report = self.new_report()
        self.assert_confirmation(report.action_install_missing())
        self.assertEqual(self.uninstalled.state, "to install")
        # a confirmation closed without Confirm or Cancel keeps the mark:
        # the report still offers to finish
        self.assertEqual(report.installable_count, 1)
        self.assert_confirmation(report.action_install_missing())
        self.assertEqual(self.uninstalled.state, "to install")
        # Cancel takes the mark back
        self.env["base.module.upgrade"].create({}).upgrade_module_cancel()
        self.assertEqual(self.uninstalled.state, "uninstalled")

    def test_nothing_left_to_install(self):
        report = self.new_report()
        self.uninstalled.state = "installed"
        self.assertEqual(report.installable_count, 0)
        with self.assertRaises(UserError):
            report.action_install_missing()

    def test_install_one_line(self):
        report = self.new_report()
        line = report.line_ids.filtered(
            lambda line: line.name == MODULE_UNINSTALLED
        )
        self.assert_confirmation(line.action_install())
        self.assertEqual(self.uninstalled.state, "to install")
        absent = report.line_ids.filtered(
            lambda line: line.name == MODULE_ABSENT
        )
        with self.assertRaises(UserError):
            absent.action_install()

    def test_confirm_reloads_the_client(self):
        Upgrade = type(self.env["base.module.upgrade"])
        with patch.object(Upgrade, "upgrade_module", autospec=True) as upgrade:
            action = (
                self.env["base.module.upgrade"]
                .create({})
                .action_erplibre_doctor_confirm()
            )
        upgrade.assert_called_once()
        self.assertEqual(
            action, {"type": "ir.actions.client", "tag": "reload"}
        )

    def test_missing_configuration(self):
        self.env["ir.config_parameter"].sudo().set_param(
            runner.PARAM_ROOT, self.root + "_missing"
        )
        report = self.new_report()
        self.assertEqual(report.state, "error")
        self.assertIn("conf/module_list_image_db_odoo.json", report.error)
        self.assertFalse(report.line_ids)

    def test_unknown_image(self):
        self.write_config({"odoo1.0_base": {"image_list": []}})
        self.addCleanup(self.write_config, self.config)
        report = self.new_report()
        self.assertEqual(report.state, "error")
        self.assertIn(self.image, report.error)

    def test_rights(self):
        """Every internal user reads the reports, only the Settings group
        runs an analysis."""
        user = self.env["res.users"].create(
            {
                "name": "Doctor user",
                "login": "erplibre_doctor_user",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        Report = self.Report.with_user(user)
        self.assertTrue(Report.has_access("read"))
        self.assertFalse(Report.has_access("create"))
        report = self.new_report()
        self.assertTrue(report.with_user(user).line_ids.mapped("name"))
