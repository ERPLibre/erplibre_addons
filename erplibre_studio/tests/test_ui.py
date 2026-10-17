# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged


def _hoot_error(message):
    return "[HOOT]" not in message


@tagged("post_install", "-at_install")
class TestStudioUi(HttpCase):
    def test_editor_tour(self):
        """The editor against the real server, opened from the developer
        panel of the contact list. The tour finds the menu item by its
        English label."""
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        self.start_tour(
            "/odoo/action-base.action_partner_form?debug=1&view_type=list",
            "erplibre_studio_editor",
            login="admin",
            timeout=180,
        )
        project = self.env["erplibre.studio.project"].search(
            [("module_name", "=", "studio_tour_contacts")]
        )
        self.assertEqual(project.user_id, self.env.ref("base.user_admin"))
        self.assertFalse(project.change_ids)
        self.assertEqual(project.draft_revision, 2)

    def test_hoot(self):
        """The hoot unit tests of the editor (web.assets_unit_tests)."""
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000"
            "&filter=erplibre_studio",
            "",
            "",
            login="admin",
            timeout=900,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=_hoot_error,
        )
