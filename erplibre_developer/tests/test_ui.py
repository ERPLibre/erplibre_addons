# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged


def _hoot_error(message):
    return "[HOOT]" not in message


@tagged("post_install", "-at_install")
class TestDeveloperUi(HttpCase):
    def test_drawer_tour(self):
        """The drawer opens from the debug menu of a list, against the real
        server: views, fields, highlight, inspect, actions, code. The tour
        finds the menu item by its English label."""
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        self.start_tour(
            "/odoo/action-base.action_partner_form?debug=1&view_type=list",
            "erplibre_developer_drawer",
            login="admin",
            timeout=180,
        )

    def test_hoot(self):
        """The hoot unit tests of the drawer (web.assets_unit_tests)."""
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000"
            "&filter=erplibre_developer",
            "",
            "",
            login="admin",
            timeout=900,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=_hoot_error,
        )
