# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StudioCase

# A form of the contacts made by the test: the demo data of dms_field adds
# the documents tree to the contact form of base.
FORM = (
    "<form><sheet>"
    "<group name='g'><field name='name'/></group>"
    "<notebook><page name='p'><field name='email'/></page></notebook>"
    "</sheet></form>"
)
PAGE = "//page[@name='p']"
GROUP = "//group[@name='g']"
DMS = "//field[@name='dms_directory_ids']"
PLACE = "documents tree goes in a tab or the sheet"
ONLY_DMS = "Only the DMS directories"


@tagged("post_install", "-at_install")
class TestDmsStudio(StudioCase):
    """The documents tree of dms_field in a form of the contacts, which
    dms_field makes inherit dms.field.mixin, when dms_field is installed."""

    def setUp(self):
        super().setUp()
        if not self.Project._studio_dms_available() or (
            "dms_directory_ids" not in self.env["res.partner"]._fields
        ):
            self.skipTest("dms_field is not installed")
        self.form_view = self.make_view("form", FORM)
        self.project = self.make_project("studio_test_dms")

    def payload(self, view=None, model="res.partner"):
        view = view or self.form_view
        return self.Editor.get_editor_data(model, view.id, view.type, self.project.id)

    def add_tree(self, target=PAGE, position="inside", view=None):
        return self.op(
            self.project,
            view or self.form_view,
            type="add_existing_field",
            target=target,
            position=position,
            field_name="dms_directory_ids",
            special="dms_list",
        )

    def set_mode(self, value, target=DMS):
        return self.op(
            self.project,
            self.form_view,
            type="set_attribute",
            target=target,
            attribute="mode",
            value=value,
        )

    def test_palette_item(self):
        item = next(
            i for i in self.payload()["palette"] if i["name"] == "dms_directory_ids"
        )
        self.assertEqual(item["string"], "Documents (DMS)")
        self.assertEqual(item["special"], "dms_list")
        self.assertEqual(item["type"], "one2many")
        # A list shows the field as any one2many.
        tree = self.env.ref("base.view_partner_tree")
        item = next(
            i
            for i in self.payload(view=tree)["palette"]
            if i["name"] == "dms_directory_ids"
        )
        self.assertNotIn("special", item)
        # A model without the mixin has no such item.
        country = self.env.ref("base.view_country_form")
        palette = self.payload(view=country, model="res.country")["palette"]
        self.assertFalse([i for i in palette if i.get("special")])
        # Once in the form, the field leaves the palette.
        self.add_tree()
        names = [i["name"] for i in self.payload()["palette"]]
        self.assertNotIn("dms_directory_ids", names)

    def test_add_in_a_tab_and_the_sheet(self):
        change = self.add_tree()
        self.assertEqual(
            change._payload()["node_attrs"],
            {"mode": "dms_list", "nolabel": "1"},
        )
        node = self.draft(self.project, self.form_view).xpath(DMS)[0]
        self.assertEqual(node.getparent().get("name"), "p")
        self.assertEqual((node.get("mode"), node.get("nolabel")), ("dms_list", "1"))
        change.unlink()
        self.add_tree(target=GROUP, position="after")
        node = self.draft(self.project, self.form_view).xpath(DMS)[0]
        self.assertEqual(node.getparent().tag, "sheet")

    def test_add_refused_elsewhere(self):
        with self.assertRaisesRegex(UserError, PLACE):
            self.add_tree(target=GROUP)
        tree = self.make_view("list", "<list><field name='name'/></list>")
        with self.assertRaisesRegex(UserError, PLACE):
            self.add_tree(target="/list", view=tree)
        with self.assertRaisesRegex(UserError, ONLY_DMS):
            self.op(
                self.project,
                self.form_view,
                type="add_existing_field",
                target=PAGE,
                position="inside",
                field_name="child_ids",
                special="dms_list",
            )
        self.assertFalse(self.project.change_ids)

    def test_mode_switch(self):
        self.add_tree()
        change = self.set_mode("")
        self.assertEqual(change._payload()["value"], "")
        node = self.draft(self.project, self.form_view).xpath(DMS)[0]
        self.assertIsNone(node.get("mode"))
        # Back to the tree: the arch is the one of the drop again.
        self.assertFalse(self.set_mode("dms_list"))
        self.assertFalse(change.exists())
        node = self.draft(self.project, self.form_view).xpath(DMS)[0]
        self.assertEqual(node.get("mode"), "dms_list")
        with self.assertRaisesRegex(UserError, "Invalid value"):
            self.set_mode("kanban")

    def test_mode_refused_on_another_field(self):
        self.op(
            self.project,
            self.form_view,
            type="add_existing_field",
            target=PAGE,
            position="inside",
            field_name="child_ids",
        )
        children = "//field[@name='child_ids']"
        for value in ("dms_list", ""):
            with self.assertRaisesRegex(UserError, ONLY_DMS):
                self.set_mode(value, target=children)

    def test_apply(self):
        self.add_tree()
        self.check_apply_is_idempotent(self.project, self.form_view)
        node = self.view_arch(self.form_view).xpath(DMS)[0]
        self.assertEqual(node.get("mode"), "dms_list")
        # The client loads the form with the documents tree of dms_field.
        self.env["res.partner"].get_views([[self.form_view.id, "form"]])

    def test_template_in_layout(self):
        Template = self.env["dms.field.template"].sudo()
        Template.search([("model", "=", "res.partner")]).unlink()
        layout = self.payload()["layout"]
        self.assertIs(layout["dms_template"], False)
        self.assertEqual(
            layout["dms_template_action"],
            "dms_field.action_dms_field_template",
        )
        self.assertTrue(self.env.ref(layout["dms_template_action"]))
        storage = self.env["dms.storage"].create(
            {"name": "Studio test storage", "save_type": "database"}
        )
        Template.create(
            {
                "name": "Studio test template",
                "storage_id": storage.id,
                "model_id": self.env["ir.model"]._get_id("res.partner"),
            }
        )
        self.assertIs(self.payload()["layout"]["dms_template"], True)
        # A model without the mixin, and a view other than a form: no key.
        country = self.env.ref("base.view_country_form")
        layout = self.payload(view=country, model="res.country")["layout"]
        self.assertNotIn("dms_template", layout)
        tree = self.env.ref("base.view_partner_tree")
        self.assertNotIn("dms_template", self.payload(view=tree)["layout"])
