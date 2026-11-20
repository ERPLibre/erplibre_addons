# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMenus(TransactionCase):
    def test_doctor_under_the_erplibre_dev_menu(self):
        menu = self.env.ref("erplibre_doctor.erplibre_doctor_dev_menu")
        self.assertEqual(
            menu.parent_id,
            self.env.ref(
                "erplibre_info_developer_menu.erplibre_dev_menu_erplibre"
            ),
        )
        self.assertEqual(menu.groups_id, self.env.ref("base.group_system"))
        self.assertEqual(
            menu.action,
            self.env.ref("erplibre_doctor.erplibre_doctor_report_action"),
        )
