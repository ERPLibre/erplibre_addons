# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDeveloperMenus(TransactionCase):
    def test_entries_under_dev_menu(self):
        dev = self.env.ref("developer_menu.conf_tech")
        system = self.env.ref("base.group_system")
        for xmlid, action in (
            (
                "erplibre_code_snapshot_dev_menu",
                "erplibre_code_snapshot_action",
            ),
            ("erplibre_code_run_dev_menu", "erplibre_code_run_action"),
            (
                "erplibre_info_settings_dev_menu",
                "erplibre_info_config_settings_action",
            ),
        ):
            menu = self.env.ref(f"erplibre_info_developer_menu.{xmlid}")
            self.assertEqual(menu.parent_id, dev)
            self.assertEqual(menu.groups_id, system)
            self.assertEqual(
                menu.action, self.env.ref(f"erplibre_info.{action}")
            )
