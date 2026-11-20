# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from types import SimpleNamespace
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_info.tests.test_views import check_object_buttons
from odoo.tests import tagged

from .common import DoctorCase


@tagged("post_install", "-at_install")
class TestSettings(DoctorCase):
    def test_last_report(self):
        self.Report.search([]).unlink()
        settings = self.env["res.config.settings"].create({})
        self.assertFalse(settings.erplibre_doctor_report_id)
        self.assertTrue(settings.erplibre_doctor_summary)
        action = settings.action_erplibre_doctor_start()
        report = self.Report.browse(action["res_id"])
        self.assertEqual(action["res_model"], "erplibre.doctor.report")
        values = self.env["res.config.settings"].get_values()
        self.assertEqual(values["erplibre_doctor_report_id"], report.id)
        self.assertIn("2", values["erplibre_doctor_summary"])
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.erplibre_doctor_report_id, report)
        self.assertEqual(
            settings.action_erplibre_doctor_open_report()["res_id"], report.id
        )
        self.assertEqual(
            settings.action_erplibre_doctor_open_reports()["res_model"],
            "erplibre.doctor.report",
        )

    def test_object_buttons_are_record_methods(self):
        self.assertTrue(check_object_buttons(self, ["erplibre_doctor"]))

    def test_doctor_shows_without_developer_mode(self):
        """The ERPLibre page and its Doctor block show to the Settings group
        outside the developer mode; the server actions stay in it."""
        admin = self.env["res.users"].create(
            {
                "name": "Doctor settings admin",
                "login": "erplibre_doctor_settings_admin",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_system").id,
                            self.env.ref("base.group_no_one").id,
                        ],
                    )
                ],
            }
        )
        settings = self.env["res.config.settings"].with_user(admin)
        for developer in (False, True):
            session = SimpleNamespace(session=SimpleNamespace(debug="1"))
            with patch(
                "odoo.addons.base.models.ir_ui_view.request",
                session if developer else None,
            ):
                arch = etree.fromstring(
                    settings.get_view(view_type="form")["arch"]
                )
            with self.subTest(developer=developer):
                self.assertTrue(arch.xpath("//app[@name='erplibre_info']"))
                self.assertTrue(
                    arch.xpath("//setting[@id='erplibre_doctor_analysis']")
                )
