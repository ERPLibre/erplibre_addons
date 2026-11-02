# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree

from odoo.tests import TransactionCase, tagged

from odoo.addons.erplibre_info.tests.test_views import check_object_buttons


@tagged("post_install", "-at_install")
class TestViewButtons(TransactionCase):
    def test_object_buttons_are_record_methods(self):
        checked = check_object_buttons(
            self, ["erplibre_info_git", "erplibre_info_developer_menu"]
        )
        self.assertGreater(checked, 10)

    def test_settings_page_shows_outside_the_developer_mode(self):
        """The snapshot settings serve every administrator: the ERPLibre page
        loses the developer-mode group of erplibre_info."""
        admin = self.env["res.users"].create(
            {
                "name": "ERPLibre snapshot settings admin",
                "login": "erplibre_info_git_settings_admin",
                "groups_id": [(6, 0, [self.env.ref("base.group_system").id])],
            }
        )
        settings = self.env["res.config.settings"].with_user(admin)
        arch = etree.fromstring(settings.get_view(view_type="form")["arch"])
        self.assertTrue(arch.xpath("//app[@name='erplibre_info']"))
        self.assertTrue(arch.xpath("//setting[@id='erplibre_snapshot_check_dirty']"))
        self.assertFalse(arch.xpath("//setting[@id='erplibre_server_actions']"))
