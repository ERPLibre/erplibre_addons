# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.addons.erplibre_info import runner
from odoo.tests import new_test_user, tagged

from ..models.erplibre_doctor_report import PARAM_NOTIFY
from .common import MODULE_ABSENT, DoctorCase


@tagged("post_install", "-at_install")
class TestDailyAnalysis(DoctorCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cron = cls.env.ref("erplibre_doctor.ir_cron_erplibre_doctor")
        cls.watcher = new_test_user(
            cls.env, login="erplibre_doctor_watcher", groups="base.group_user"
        )
        cls.portal = new_test_user(
            cls.env, login="erplibre_doctor_portal", groups="base.group_portal"
        )

    def notifications(self, report):
        comment = self.env.ref("mail.mt_comment")
        return report.message_ids.filtered(
            lambda message: message.subtype_id == comment
        )

    def test_cron(self):
        self.assertTrue(self.cron.active)
        self.assertEqual(self.cron.model_id.model, "erplibre.doctor.report")
        self.assertEqual(self.cron.code, "model._cron_run_analysis()")
        self.assertEqual(
            (self.cron.interval_number, self.cron.interval_type), (1, "days")
        )

    def test_notifies_the_listed_internal_users(self):
        self.Report._set_notify_users(self.watcher | self.portal)
        # a portal user is never notified
        self.assertEqual(self.Report._notify_users(), self.watcher)
        report = self.Report._cron_run_analysis()
        self.assertEqual(report.problem_count, 2)
        message = self.notifications(report)
        self.assertEqual(len(message), 1)
        self.assertEqual(message.partner_ids, self.watcher.partner_id)
        self.assertIn(report.name, message.body)
        self.assertIn(f"<li>{MODULE_ABSENT}: Not found</li>", message.body)
        self.assertNotIn("<li>base:", message.body)

    def test_cron_day_in_the_company_time_zone(self):
        self.env.company.partner_id.tz = "Pacific/Kiritimati"
        self.assertEqual(self.Report._cron_tz(), "Pacific/Kiritimati")
        report = self.Report._cron_run_analysis()
        day = fields.Date.context_today(
            self.Report.with_context(tz="Pacific/Kiritimati")
        )
        self.assertIn(day.strftime("/%Y/%m/%d/"), report.name)

    def test_no_problem_no_message(self):
        self.Report._set_notify_users(self.watcher)
        self.write_config({self.image: {"image_list": [{"module": ["base"]}]}})
        self.addCleanup(self.write_config, self.config)
        report = self.Report._cron_run_analysis()
        self.assertEqual(report.problem_count, 0)
        self.assertFalse(self.notifications(report))

    def test_incomplete_analysis_is_notified(self):
        self.Report._set_notify_users(self.watcher)
        self.env["ir.config_parameter"].sudo().set_param(
            runner.PARAM_ROOT, self.root + "_missing"
        )
        report = self.Report._cron_run_analysis()
        self.assertEqual(report.state, "error")
        self.assertIn(
            "conf/module_list_image_db_odoo.json",
            self.notifications(report).body,
        )

    def test_nobody_to_notify(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_NOTIFY, "x,0,")
        self.assertFalse(self.Report._notify_users())
        report = self.Report._cron_run_analysis()
        self.assertFalse(self.notifications(report))

    def test_settings(self):
        settings = self.env["res.config.settings"].create(
            {
                "erplibre_doctor_daily": False,
                "erplibre_doctor_notify_user_ids": [(6, 0, self.watcher.ids)],
            }
        )
        settings.set_values()
        self.assertFalse(self.cron.active)
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param(PARAM_NOTIFY),
            str(self.watcher.id),
        )
        settings = self.env["res.config.settings"].create({})
        self.assertFalse(settings.erplibre_doctor_daily)
        self.assertEqual(
            settings.erplibre_doctor_notify_user_ids, self.watcher
        )
        settings.erplibre_doctor_daily = True
        settings.set_values()
        self.assertTrue(self.cron.active)
