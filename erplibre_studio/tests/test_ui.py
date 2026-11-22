# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from lxml import etree
from odoo.tests import HttpCase, tagged

from .common import TIMELINE_ARCH, production_rule_patch


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
        new filter, both previews, a pivot view added, Apply. The applied
        views show the changes to every user, without the draft context."""
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
        # The pivot view the tour adds is the one of the contacts now.
        added = project.view_line_ids
        self.assertEqual(added.view_type, "pivot")
        self.assertTrue(added.applied)
        self.assertEqual(
            self.env["ir.ui.view"].default_view("res.partner", "pivot"),
            added.view_id.id,
        )
        kanban = self.arch_of("base.res_partner_kanban_view")
        phone = kanban.xpath("//t[@t-name='card']//field[@name='phone']")
        self.assertEqual(phone[0].get("widget"), "phone")
        self.assertEqual(phone[0].getnext().get("name"), "email")
        search = self.arch_of("base.view_res_partner_filter")
        tax = search.xpath("//filter[@string='Tour has a tax ID']")
        self.assertEqual(tax[0].get("domain"), "[('vat', '!=', False)]")

    def test_graph_tour(self):
        """A graph view added to the draft of the contacts: a field dropped
        on its group-bys, the line chart chosen in the canvas, the preview
        renders the graph before Apply."""
        if self.env["ir.ui.view"].default_view("res.partner", "graph"):
            self.skipTest("res.partner has a graph view in this database")
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        self.start_tour(
            "/odoo/action-base.action_partner_form?debug=1",
            "erplibre_studio_graph_editor",
            login="admin",
            timeout=240,
        )
        project = self.env["erplibre.studio.project"].search(
            [("module_name", "=", "studio_tour_graph")]
        )
        line = project.view_line_ids
        self.assertEqual(line.view_type, "graph")
        self.assertFalse(line.applied)
        view = self.env["erplibre.studio.editor"]._resolve_view(
            "res.partner", False, "graph", project
        )
        arch, errors = project._draft_arch(view)
        self.assertFalse(errors)
        self.assertEqual(arch.get("type"), "line")
        country = arch.xpath("//field[@name='country_id']")
        self.assertEqual(country[0].get("type"), "row")
        # The field goes after the group-by of the added view: it splits
        # the X axis into series.
        self.assertEqual(arch.xpath("//field")[-1].get("name"), "country_id")

    def test_calendar_tour(self):
        """A calendar view added to the draft of the contacts: the week
        scale chosen in the canvas in place of the month, a date dropped
        on its end date, the preview renders the calendar before Apply."""
        if self.env["ir.ui.view"].default_view("res.partner", "calendar"):
            self.skipTest("res.partner has a calendar view in this database")
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        self.start_tour(
            "/odoo/action-base.action_partner_form?debug=1",
            "erplibre_studio_calendar_editor",
            login="admin",
            timeout=240,
        )
        project = self.env["erplibre.studio.project"].search(
            [("module_name", "=", "studio_tour_calendar")]
        )
        line = project.view_line_ids
        self.assertEqual(line.view_type, "calendar")
        self.assertFalse(line.applied)
        view = self.env["erplibre.studio.editor"]._resolve_view(
            "res.partner", False, "calendar", project
        )
        arch, errors = project._draft_arch(view)
        self.assertFalse(errors)
        self.assertEqual(arch.get("mode"), "week")
        self.assertEqual(arch.get("date_stop"), "write_date")

    def test_hierarchy_tour(self):
        """A hierarchy view added to the draft of the contacts: the email
        added to its card with Enter on the palette, the preview renders
        the hierarchy before Apply."""
        if "hierarchy" not in self.env["erplibre.studio.project"]._view_types():
            self.skipTest("web_hierarchy is not installed")
        if self.env["ir.ui.view"].default_view("res.partner", "hierarchy"):
            self.skipTest("res.partner has a hierarchy view in this database")
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        self.start_tour(
            "/odoo/action-base.action_partner_form?debug=1",
            "erplibre_studio_hierarchy_editor",
            login="admin",
            timeout=240,
        )
        project = self.env["erplibre.studio.project"].search(
            [("module_name", "=", "studio_tour_hierarchy")]
        )
        line = project.view_line_ids
        self.assertEqual(line.view_type, "hierarchy")
        self.assertFalse(line.applied)
        view = self.env["erplibre.studio.editor"]._resolve_view(
            "res.partner", False, "hierarchy", project
        )
        arch, errors = project._draft_arch(view)
        self.assertFalse(errors)
        self.assertEqual(arch.get("parent_field"), "parent_id")
        card = arch.xpath("//t[@t-name='hierarchy-box']")[0]
        self.assertIn("email", [f.get("name") for f in card.iter("field")])

    def timeline_setup(self):
        """A timeline view of the contacts, a contact of a company to show
        in it, and an action that opens the view: (view, action). Skips the
        test without web_timeline."""
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
        return view, action

    def test_timeline_item_field_tour(self):
        """A field the project drops into a timeline item renders in the
        browser once applied: the item shows its value, no JS error."""
        view, action = self.timeline_setup()
        project = self.env["erplibre.studio.project"].create(
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
        self.start_tour(
            f"/odoo/action-{action.id}",
            "erplibre_studio_timeline",
            login="admin",
            timeout=180,
        )

    def test_timeline_editor_tour(self):
        """The lanes of a timeline in the editor: a scale, a field dropped
        on the end date, a color rule; the timeline of the canvas and the
        preview render the draft."""
        view, action = self.timeline_setup()
        self.start_tour(
            f"/odoo/action-{action.id}?debug=1",
            "erplibre_studio_timeline_editor",
            login="admin",
            timeout=240,
        )
        project = self.env["erplibre.studio.project"].search(
            [("module_name", "=", "studio_tour_timeline_editor")]
        )
        self.assertEqual(
            sorted(
                change._payload()["attribute"]
                for change in project.change_ids
                if change.change_type == "set_attribute"
            ),
            ["colors", "mode"],
        )
        arch, _errors = project._draft_arch(view)
        self.assertEqual(arch.get("mode"), "week")
        self.assertEqual(arch.get("date_stop"), "write_date")
        self.assertEqual(arch.get("colors"), "#ec7063:is_company == True")

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


@tagged("post_install", "-at_install")
class TestStudioModelsUi(HttpCase):
    """A class of its own: Apply adds a model to the registry, which the
    rollback of the test leaves there until the cleanup of the class."""

    def test_models_tour(self):
        """A new model made from the editor: a new app with an icon, Apply
        and open, a field dropped into its form and renamed, an access
        right changed, a rule checked and saved, Apply. Every record lives
        under the external ids of the module."""
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        # The tour checks the refusal of a name without x_.
        with production_rule_patch(self.env):
            self.start_tour(
                "/odoo/action-base.action_partner_form?debug=1&view_type=list",
                "erplibre_studio_models",
                login="admin",
                timeout=240,
            )
        project = self.env["erplibre.studio.project"].search(
            [("module_name", "=", "studio_tour_models")]
        )
        self.assertEqual(project.state, "applied")
        self.assertEqual(
            (project.app_ids.name, project.app_ids.icon),
            ("Tour item", "base,static/description/icon.png"),
        )
        line = project.new_model_ids
        self.assertEqual((line.model, line.name), ("x_tour_item", "Tour item"))
        model = project.created_model_ids
        self.assertEqual((model.model, model.state), ("x_tour_item", "manual"))
        self.assertIn("x_tour_item", self.env)
        app = project.created_menu_ids.filtered(lambda m: not m.parent_id)
        self.assertEqual(app.name, "Tour item")
        self.assertEqual(app.web_icon, "base,static/description/icon.png")
        menu = project.created_menu_ids - app
        self.assertEqual(menu.parent_id, app)
        self.assertEqual(menu.action, project.created_action_ids)
        self.assertEqual(project.created_action_ids.res_model, "x_tour_item")
        new_fields = project.field_ids.filtered(lambda f: f.model == "x_tour_item")
        self.assertEqual(new_fields.mapped("name"), ["x_tour_code"])
        access = project.created_access_ids
        self.assertEqual(access.group_id, self.env.ref("base.group_user"))
        self.assertEqual(
            (
                access.perm_read,
                access.perm_write,
                access.perm_create,
                access.perm_unlink,
            ),
            (True, True, True, False),
        )
        rule = project.created_rule_ids
        self.assertEqual(
            (rule.name, rule.model_id, rule.domain_force, rule.groups),
            (
                "Tour own items",
                model,
                "[('create_uid', '=', user.id)]",
                self.env.ref("base.group_user"),
            ),
        )
        form = project.created_view_ids.filtered(lambda v: v.type == "form")
        studio = project.studio_view_ids
        self.assertEqual(studio.inherit_id, form)
        new_field = project.field_ids
        self.assertEqual((new_field.model, new_field.ttype), ("x_tour_item", "char"))
        arch = etree.fromstring(
            self.env["x_tour_item"].get_view(form.id, "form")["arch"]
        )
        left = arch.xpath("//group[@name='studio_left']/field")
        self.assertEqual([n.get("name") for n in left], [new_field.name])


@tagged("post_install", "-at_install")
class TestStudioJ4Ui(HttpCase):
    """The J4 editor end to end: a class of its own, Apply adds models to
    the registry until the cleanup of the class."""

    def test_j4_tour(self):
        """Two apps, a model in each, a one2many whose inverse the studio
        creates, both previews, two groups, a global rule, Apply, then the
        Revert confirmation. Apply creates what the editor showed."""
        self.env["res.lang"]._activate_lang("en_US")
        self.env.ref("base.user_admin").lang = "en_US"
        self.start_tour(
            "/odoo/action-base.action_partner_form?debug=1&view_type=list",
            "erplibre_studio_j4",
            login="admin",
            timeout=300,
        )
        project = self.env["erplibre.studio.project"].search(
            [("module_name", "=", "studio_tour_j4")]
        )
        self.assertEqual(project.state, "applied")
        # The real preview left nothing behind; Apply created the models the
        # approval was for, and cleared it.
        self.assertFalse(project.approved_uid or project.approved_snapshot)
        self.assertEqual(
            [(app.name, app.xml_name, app.icon) for app in project.app_ids],
            [
                ("Tour shop", "menu_app", "base,static/description/icon.png"),
                ("Tour stock", "menu_app_tour_stock", False),
            ],
        )
        lines = {line.model: line for line in project.new_model_ids}
        self.assertEqual(sorted(lines), ["x_tour_line", "x_tour_order"])
        self.assertEqual(lines["x_tour_order"].app_id.name, "Tour shop")
        self.assertEqual(lines["x_tour_line"].app_id.name, "Tour stock")
        roots = project.created_menu_ids.filtered(lambda m: not m.parent_id)
        self.assertEqual(sorted(roots.mapped("name")), ["Tour shop", "Tour stock"])
        shop = self.env.ref("studio_tour_j4.menu_app")
        self.assertEqual(shop.web_icon, "base,static/description/icon.png")
        # The relation pair: the one2many and the inverse it created.
        Fields = self.env["ir.model.fields"]
        inverse = Fields._get("x_tour_line", "x_tour_order_id")
        self.assertEqual(
            (inverse.ttype, inverse.relation, inverse.on_delete),
            ("many2one", "x_tour_order", "cascade"),
        )
        one2many = Fields._get("x_tour_order", "x_tour_line")
        self.assertEqual(
            (one2many.ttype, one2many.relation, one2many.relation_field),
            ("one2many", "x_tour_line", "x_tour_order_id"),
        )
        # The change recorded on the pending form went to the created view.
        form = self.env.ref("studio_tour_j4.view_x_tour_order_form")
        arch = etree.fromstring(
            self.env["x_tour_order"].get_view(form.id, "form")["arch"]
        )
        left = arch.xpath("//group[@name='studio_left']/field[@name='x_tour_line']")
        self.assertEqual(len(left), 1)
        self.assertTrue(left[0].xpath("./list/field[@name='x_name']"))
        self.assertIn(form, project.studio_view_ids.inherit_id)
        # The groups, in the category of their app.
        user = self.env.ref("studio_tour_j4.group_tour_shop_tour_user")
        admin = self.env.ref("studio_tour_j4.group_tour_shop_tour_admin")
        self.assertEqual(user.category_id.name, "Tour shop")
        self.assertEqual(admin.category_id, user.category_id)
        self.assertIn(user, admin.implied_ids)
        self.assertIn(self.env.ref("base.group_user"), user.implied_ids)
        rule = project.created_rule_ids
        self.assertEqual(
            (rule.name, rule.model_id.model, rule.groups),
            ("Tour all orders", "x_tour_order", self.env["res.groups"]),
        )
        # The confirmation was cancelled: everything stays.
        self.assertIn("x_tour_order", self.env)
        self.assertTrue(project.applied_snapshot)
