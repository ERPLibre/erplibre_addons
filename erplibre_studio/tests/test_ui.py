# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from lxml import etree
from odoo.tests import HttpCase, tagged

from .common import TIMELINE_ARCH


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

    def arch_of(self, xmlid):
        """The arch get_view gives for the contact view ``xmlid``."""
        view = self.env.ref(xmlid)
        arch = self.env["res.partner"].get_view(view.id, view.type)["arch"]
        return etree.fromstring(arch)

    def test_views_tour(self):
        """A kanban and a search view customized end to end: drop, widget,
        new filter, both previews, Apply. The applied views show the
        changes to every user, without the draft context."""
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        self.start_tour(
            "/odoo/action-base.action_partner_form?debug=1",
            "erplibre_studio_views",
            login="admin",
            timeout=240,
        )
        project = self.env["erplibre.studio.project"].search(
            [("module_name", "=", "studio_tour_views")]
        )
        self.assertEqual(project.state, "applied")
        self.assertEqual(
            sorted(project.change_ids.mapped("change_type")),
            ["add_existing_field", "add_node", "set_attribute"],
        )
        self.assertEqual(
            sorted(project.studio_view_ids.mapped("type")), ["kanban", "search"]
        )
        kanban = self.arch_of("base.res_partner_kanban_view")
        phone = kanban.xpath("//t[@t-name='card']//field[@name='phone']")
        self.assertEqual(phone[0].get("widget"), "phone")
        self.assertEqual(phone[0].getnext().get("name"), "email")
        search = self.arch_of("base.view_res_partner_filter")
        tax = search.xpath("//filter[@string='Tour has a tax ID']")
        self.assertEqual(tax[0].get("domain"), "[('vat', '!=', False)]")

    def test_timeline_item_field_tour(self):
        """A field the project drops into a timeline item renders in the
        browser once applied: the item shows its value, no JS error."""
        Project = self.env["erplibre.studio.project"]
        if "timeline" not in Project._view_types():
            self.skipTest("web_timeline is not installed")
        view = self.env["ir.ui.view"].create(
            {
                "name": "erplibre_studio tour timeline",
                "model": "res.partner",
                "type": "timeline",
                "arch": TIMELINE_ARCH,
                "priority": 1000,
            }
        )
        company = self.env["res.partner"].create(
            {"name": "Studio timeline company", "is_company": True}
        )
        self.env["res.partner"].create(
            {
                "name": "Studio timeline contact",
                "email": "studio.timeline@example.invalid",
                "parent_id": company.id,
                "user_id": self.env.ref("base.user_admin").id,
            }
        )
        project = Project.create(
            {"name": "Tour timeline", "module_name": "studio_tour_timeline"}
        )
        item = "//t[@t-name='timeline-item']/div[1]"
        for name in ("email", "parent_id"):
            project._apply_operation(
                view,
                {
                    "type": "add_existing_field",
                    "target": item,
                    "position": "inside",
                    "field_name": name,
                },
            )
        # The guard asks a request in developer mode; this one has none.
        Run = type(self.env["erplibre.code.run"])
        with patch.object(Run, "_is_debug_mode", lambda run: True):
            project.action_apply()
        action = self.env["ir.actions.act_window"].create(
            {
                "name": "Studio timeline",
                "res_model": "res.partner",
                "view_mode": "timeline",
                "view_id": view.id,
                "domain": [("name", "like", "Studio timeline")],
            }
        )
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        self.start_tour(
            f"/odoo/action-{action.id}",
            "erplibre_studio_timeline",
            login="admin",
            timeout=180,
        )

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
