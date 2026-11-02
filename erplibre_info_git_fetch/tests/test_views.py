# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from odoo.addons.erplibre_info.tests.test_views import check_object_buttons


@tagged("post_install", "-at_install")
class TestViewButtons(TransactionCase):
    def test_object_buttons_are_record_methods(self):
        self.assertGreater(check_object_buttons(self, ["erplibre_info_git_fetch"]), 10)
