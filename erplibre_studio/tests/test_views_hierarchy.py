# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .. import arch as studio_arch
from .common import HIERARCHY_ARCH, StudioCase

CARD = "//t[@t-name='hierarchy-box']"
BODY = f"{CARD}/div[2]"


@tagged("post_install", "-at_install")
class TestHierarchyDetection(StudioCase):
    def test_hierarchy_only_with_web_hierarchy(self):
        installed = bool(
            self.env["ir.module.module"].search(
                [("name", "=", "web_hierarchy"), ("state", "=", "installed")]
            )
        )
        self.assertEqual(self.hierarchy_available(), installed)
        data = self.Editor.get_editor_data("res.partner", False, "list")
        entry = next(e for e in data["view_list"] if e["type"] == "hierarchy")
        if installed:
            self.assertNotEqual(entry["reason_code"], "needs_module")
            return
        self.assertEqual(entry["reason_code"], "needs_module")
        self.assertIn("web_hierarchy", entry["reason"])
        project = self.make_project("studio_test_hierarchy_missing")
        with self.assertRaisesRegex(UserError, "web_hierarchy"):
            project._studio_add_view("res.partner", "hierarchy")


@tagged("post_install", "-at_install")
class TestHierarchyStudio(StudioCase):
    """The studio on a hierarchy view of the contacts, made by the test,
    when web_hierarchy is installed."""

    def setUp(self):
        super().setUp()
        if not self.hierarchy_available():
            self.skipTest("web_hierarchy is not installed")
        self.hierarchy = self.make_view("hierarchy", HIERARCHY_ARCH)
        self.project = self.make_project("studio_test_hierarchy")

    def set_attribute(self, attribute, value, target="/hierarchy"):
        return self.op(
            self.project,
            self.hierarchy,
            type="set_attribute",
            target=target,
            attribute=attribute,
            value=value,
        )

    def card_fields(self, arch):
        card = arch.xpath(CARD)[0]
        return [node.get("name") for node in card.iter("field")]

    def test_editor_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.hierarchy.id, "hierarchy", self.project.id
        )
        self.assertIn("hierarchy", data["view_types"])
        entry = next(e for e in data["view_list"] if e["type"] == "hierarchy")
        self.assertTrue(entry["editable"])
        layout = data["layout"]
        self.assertEqual(layout["card"], CARD)
        self.assertEqual(layout["templates"], {"hierarchy-box": CARD})
        self.assertEqual(layout["loaded_fields"], ["child_ids"])
        self.assertEqual(layout["widgets"], {})
        self.assertEqual(data["hide_mode"], "invisible")
        self.assertNotIn("add_widget", data["operations"])
        self.assertIn("add_field", data["operations"])
        self.assertEqual(
            data["settable"]["hierarchy"],
            {
                "parent_field": "parent_field",
                "child_field": "child_field",
                "draggable": "bool",
                "default_order": "order",
            },
        )
        self.assertEqual(data["required_attributes"], {})
        choices = data["choices"]
        parents = [name for name, _l in choices["parent_field"]]
        self.assertIn("parent_id", parents)
        self.assertIn("commercial_partner_id", parents)
        self.assertNotIn("user_id", parents)
        children = [name for name, _l in choices["child_field"]]
        self.assertIn("child_ids", children)
        self.assertNotIn("bank_ids", children)
        palette = {f["name"] for f in data["palette"]}
        self.assertIn("phone", palette)
        self.assertNotIn("email", palette)
        card = data["blocks"]["children"][1]["children"][0]
        self.assertEqual(card["template"], "hierarchy-box")
        self.assertFalse(data["blocks"]["drop"])

    def test_changes(self):
        self.op(
            self.project,
            self.hierarchy,
            type="add_existing_field",
            target=BODY,
            position="inside",
            field_name="phone",
        )
        self.op(
            self.project,
            self.hierarchy,
            type="move",
            source="//field[@name='email']",
            target="//field[@name='name']",
            position="after",
        )
        self.op(
            self.project,
            self.hierarchy,
            type="hide",
            target="//field[@name='phone']",
            value=True,
        )
        self.set_attribute("draggable", True)
        self.set_attribute("default_order", "name asc")
        self.op(
            self.project,
            self.hierarchy,
            type="add_field",
            target=BODY,
            position="inside",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        arch = self.draft(self.project, self.hierarchy)
        self.assertEqual(arch.get("draggable"), "True")
        self.assertEqual(arch.get("default_order"), "name asc")
        self.assertEqual(
            [f.get("name") for f in arch.xpath(f"{CARD}/div[1]/field")],
            ["name", "email"],
        )
        body = arch.xpath(BODY)[0]
        self.assertEqual(
            [(f.get("name"), f.get("invisible")) for f in body.iter("field")],
            [("phone", "True"), ("x_nickname", None)],
        )
        # The draft compiles as a hierarchy: get_views reads it.
        self.env["res.partner"].with_context(
            **self.preview_key(self.project)
        ).get_views([[self.hierarchy.id, "hierarchy"]])

    def test_parent_and_children_fields(self):
        """The parent is a stored many2one of the model to itself; the
        children, a one2many whose inverse is that parent."""
        change = self.set_attribute("parent_field", "parent_id")
        # The view does not load parent_id: the change loads it.
        self.assertEqual(change._payload()["load"], ["parent_id"])
        arch = self.draft(self.project, self.hierarchy)
        self.assertEqual(
            (arch.get("parent_field"), arch.get("child_field")),
            ("parent_id", "child_ids"),
        )
        self.assertEqual(
            arch.xpath("/hierarchy/field/@name"), ["child_ids", "parent_id"]
        )
        with self.assertRaisesRegex(UserError, "stored many2one"):
            self.set_attribute("parent_field", "user_id")
        with self.assertRaisesRegex(UserError, "inverse"):
            self.set_attribute("child_field", "bank_ids")
        with self.assertRaises(UserError):
            self.set_attribute("child_field", "name")

    def test_parent_field_with_children_of_another_parent(self):
        """A parent field other than the inverse of the children is
        refused until the children field leaves."""
        commercial = self.env["res.partner"]._fields["commercial_partner_id"]
        self.assertEqual(commercial.comodel_name, "res.partner")
        with self.assertRaisesRegex(UserError, "Remove the children field"):
            self.set_attribute("parent_field", "commercial_partner_id")
        self.set_attribute("child_field", "")
        self.set_attribute("parent_field", "parent_id")
        # A new value replaces the change, and the field it loads.
        self.set_attribute("parent_field", "commercial_partner_id")
        arch = self.draft(self.project, self.hierarchy)
        self.assertEqual(arch.get("parent_field"), "commercial_partner_id")
        self.assertIsNone(arch.get("child_field"))
        self.assertEqual(
            arch.xpath("/hierarchy/field/@name"),
            ["child_ids", "commercial_partner_id"],
        )
        # child_ids follows parent_id, not the parent field of the view.
        with self.assertRaisesRegex(UserError, "inverse"):
            self.set_attribute("child_field", "child_ids")

    def test_refusals(self):
        with self.assertRaises(UserError):
            # Nothing new goes outside the card.
            self.op(
                self.project,
                self.hierarchy,
                type="add_existing_field",
                target="/hierarchy",
                position="inside",
                field_name="phone",
            )
        with self.assertRaises(UserError):
            self.op(
                self.project,
                self.hierarchy,
                type="add_field",
                target=BODY,
                position="inside",
                field={
                    "ttype": "one2many",
                    "field_description": "Items",
                    "relation": "res.partner",
                },
            )
        with self.assertRaises(UserError):
            self.op(
                self.project,
                self.hierarchy,
                type="set_attribute",
                target="/hierarchy",
                attribute="icon",
                value="fa-users",
            )
        with self.assertRaises(UserError):
            self.op(
                self.project,
                self.hierarchy,
                type="add_widget",
                target=BODY,
                position="inside",
                widget="web_ribbon",
                attrs={"title": "New"},
            )
        self.assertFalse(self.project.change_ids)

    def test_apply_and_revert(self):
        self.op(
            self.project,
            self.hierarchy,
            type="add_existing_field",
            target=BODY,
            position="inside",
            field_name="phone",
        )
        self.set_attribute("draggable", True)
        studio = self.check_apply_is_idempotent(self.project, self.hierarchy)
        arch = self.view_arch(self.hierarchy)
        self.assertEqual(arch.get("draggable"), "True")
        self.assertIn("phone", self.card_fields(arch))
        self.env["res.partner"].get_views([[self.hierarchy.id, "hierarchy"]])
        self.project.action_revert()
        self.assertFalse(studio.exists())
        arch = self.view_arch(self.hierarchy)
        self.assertNotIn("phone", self.card_fields(arch))
        self.assertIsNone(arch.get("draggable"))

    def test_default_arch_and_parent_field(self):
        self.assertEqual(self.project._studio_parent_field("res.partner"), "parent_id")
        self.assertIsNone(self.project._studio_parent_field("res.country"))
        with self.assertRaisesRegex(UserError, "many2one from res.country"):
            self.project._studio_add_view("res.country", "hierarchy")
        with self.assertRaises(studio_arch.ArchError):
            studio_arch.default_view_arch("hierarchy", "Countries", "name")
