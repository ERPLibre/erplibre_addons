# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import PIVOT_ARCH, StudioCase


@tagged("post_install", "-at_install")
class TestPivotStudio(StudioCase):
    """The studio on a pivot view of the contacts: base has none, the test
    makes one."""

    def setUp(self):
        super().setUp()
        self.pivot = self.make_view("pivot", PIVOT_ARCH)
        self.project = self.make_project("studio_test_pivot")

    def axes(self, arch):
        return [
            (n.get("name"), n.get("type"), n.get("interval"))
            for n in arch.iter("field")
        ]

    def test_editor_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.pivot.id, "pivot", self.project.id
        )
        self.assertEqual(data["hide_mode"], "remove")
        self.assertEqual(
            data["layout"]["axes"],
            {
                "row": ["//field[@name='country_id']"],
                "col": [],
                "measure": ["//field[@name='partner_latitude']"],
            },
        )
        self.assertTrue(data["blocks"]["drop"])
        self.assertEqual(
            [(b["name"], b["axis"]) for b in data["blocks"]["children"]],
            [("country_id", "row"), ("partner_latitude", "measure")],
        )
        palette = {f["name"]: f["axes"] for f in data["palette"]}
        self.assertEqual(palette["partner_longitude"], ["row", "col", "measure"])
        self.assertEqual(palette["create_date"], ["row", "col"])
        self.assertNotIn("avatar_128", palette)
        self.assertNotIn("country_id", palette)
        self.assertIn(
            ["partner_longitude", "Geo Longitude"], data["choices"]["measure"]
        )
        self.assertEqual(
            data["settable"]["field"], {"type": "axis", "interval": "interval"}
        )

    def test_changes_and_their_xpath(self):
        self.op(
            self.project,
            self.pivot,
            type="add_existing_field",
            target="/pivot",
            position="inside",
            field_name="create_date",
            axis="col",
            interval="month",
        )
        self.op(
            self.project,
            self.pivot,
            type="add_existing_field",
            target="//field[@name='partner_latitude']",
            position="after",
            field_name="partner_longitude",
            axis="measure",
        )
        # From the rows to the columns, before create_date.
        self.op(
            self.project,
            self.pivot,
            type="move",
            source="//field[@name='country_id']",
            target="//field[@name='create_date']",
            position="before",
            axis="col",
        )
        self.op(
            self.project,
            self.pivot,
            type="set_attribute",
            target="//field[@name='create_date']",
            attribute="interval",
            value="year",
        )
        self.op(
            self.project,
            self.pivot,
            type="set_attribute",
            target="/pivot",
            attribute="disable_linking",
            value=True,
        )
        self.op(
            self.project,
            self.pivot,
            type="hide",
            target="//field[@name='partner_latitude']",
            value=True,
        )
        changes = self.project.change_ids
        self.assertEqual(
            [(c.change_type, c.xpath, c.position) for c in changes],
            [
                ("add_existing_field", "/pivot", "inside"),
                ("add_existing_field", "//field[@name='partner_latitude']", "after"),
                ("move", "//field[@name='create_date']", "before"),
                ("set_attribute", "//field[@name='create_date']", "attributes"),
                ("set_attribute", "/pivot", "attributes"),
                ("remove", "//field[@name='partner_latitude']", "replace"),
            ],
        )
        self.assertEqual(
            changes[0]._payload()["node_attrs"], {"interval": "month", "type": "col"}
        )
        move = changes[2]._payload()
        self.assertEqual(move["attrs"], {"type": "col"})
        self.assertEqual(move["attrs_xpath"], "//field[@name='country_id']")
        arch = self.draft(self.project, self.pivot)
        self.assertEqual(
            self.axes(arch),
            [
                ("partner_longitude", "measure", None),
                ("country_id", "col", None),
                ("create_date", "col", "year"),
            ],
        )
        self.assertEqual(arch.get("disable_linking"), "True")
        self.assertIn("(col)", changes[2].summary)

        # Moving a measure field to the rows.
        self.op(
            self.project,
            self.pivot,
            type="move",
            source="//field[@name='partner_longitude']",
            target="//field[@name='create_date']",
            position="after",
            axis="row",
        )
        arch = self.draft(self.project, self.pivot)
        self.assertEqual(self.axes(arch)[-1], ("partner_longitude", "row", None))

    def test_refused_operations(self):
        refused = [
            {
                "type": "add_existing_field",
                "target": "/pivot",
                "position": "inside",
                "field_name": "name",
                "axis": "measure",
            },
            {
                "type": "add_existing_field",
                "target": "/pivot",
                "position": "inside",
                "field_name": "name",
            },
            {
                "type": "add_existing_field",
                "target": "/pivot",
                "position": "inside",
                "field_name": "name",
                "axis": "row",
                "interval": "month",
            },
            {
                "type": "add_existing_field",
                "target": "/pivot",
                "position": "inside",
                "field_name": "avatar_128",
                "axis": "row",
            },
            {
                "type": "add_existing_field",
                "target": "//field[@name='country_id']",
                "position": "inside",
                "field_name": "name",
                "axis": "row",
            },
            {
                "type": "add_existing_field",
                "target": "/pivot",
                "position": "inside",
                "field_name": "country_id",
                "axis": "col",
            },
            {
                "type": "set_attribute",
                "target": "//field[@name='partner_latitude']",
                "attribute": "interval",
                "value": "month",
            },
            {
                "type": "set_attribute",
                "target": "//field[@name='country_id']",
                "attribute": "type",
                "value": "measure",
            },
            {
                "type": "set_attribute",
                "target": "//field[@name='country_id']",
                "attribute": "widget",
                "value": "x",
            },
            {"type": "add_field", "target": "/pivot", "position": "inside"},
        ]
        for operation in refused:
            with self.subTest(operation=operation), self.assertRaises(UserError):
                self.op(self.project, self.pivot, **operation)
        self.assertFalse(self.project.change_ids)

    def test_same_value_leaves_no_change(self):
        change = self.op(
            self.project,
            self.pivot,
            type="set_attribute",
            target="//field[@name='partner_latitude']",
            attribute="type",
            value="measure",
        )
        self.assertFalse(change)
        self.assertFalse(self.project.change_ids)

    def test_preview_isolation(self):
        editor, other = self.make_users()
        self.project.user_id = editor
        self.op(
            self.project,
            self.pivot,
            type="add_existing_field",
            target="/pivot",
            position="inside",
            field_name="create_date",
            axis="col",
            interval="month",
        )
        key = self.preview_key(self.project)
        added = ("create_date", "col", "month")
        self.assertIn(added, self.axes(self.view_arch(self.pivot, editor, key)))
        self.assertNotIn(added, self.axes(self.view_arch(self.pivot, other, key)))
        self.assertNotIn(added, self.axes(self.view_arch(self.pivot, editor)))

    def test_apply_discard_revert_undo(self):
        self.op(
            self.project,
            self.pivot,
            type="move",
            source="//field[@name='country_id']",
            target="/pivot",
            position="inside",
            axis="col",
        )
        studio = self.check_apply_is_idempotent(self.project, self.pivot)
        self.assertIn(
            ("country_id", "col", None), self.axes(self.view_arch(self.pivot))
        )
        self.env["res.partner"].get_views([[self.pivot.id, "pivot"]])
        self.op(
            self.project,
            self.pivot,
            type="hide",
            target="//field[@name='partner_latitude']",
            value=True,
        )
        self.project.action_undo(self.pivot)
        self.assertEqual(self.project.state, "applied")
        self.project.action_revert()
        self.assertFalse(studio.exists())
        self.assertIn(
            ("country_id", "row", None), self.axes(self.view_arch(self.pivot))
        )
