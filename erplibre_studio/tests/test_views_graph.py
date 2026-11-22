# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import GRAPH_ARCH, StudioCase


@tagged("post_install", "-at_install")
class TestGraphStudio(StudioCase):
    """The studio on a graph view of the contacts, made by the test."""

    def setUp(self):
        super().setUp()
        self.graph = self.make_view("graph", GRAPH_ARCH)
        self.project = self.make_project("studio_test_graph")

    def axes(self, arch):
        return [
            (n.get("name"), n.get("type"), n.get("interval"))
            for n in arch.iter("field")
        ]

    def test_editor_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.graph.id, "graph", self.project.id
        )
        self.assertIn("graph", data["view_types"])
        self.assertEqual(data["hide_mode"], "remove")
        self.assertEqual(
            data["layout"]["axes"],
            {
                "row": ["//field[@name='country_id']"],
                "measure": ["//field[@name='partner_latitude']"],
            },
        )
        self.assertEqual(data["layout"]["others"], [])
        self.assertTrue(data["blocks"]["drop"])
        self.assertEqual(
            [(b["name"], b["axis"]) for b in data["blocks"]["children"]],
            [("country_id", "row"), ("partner_latitude", "measure")],
        )
        self.assertEqual(
            data["settable"]["graph"],
            {
                "type": "graph_type",
                "stacked": "bool",
                "order": "graph_order",
                "disable_linking": "bool",
                "cumulated": "bool",
            },
        )
        self.assertEqual(
            data["settable"]["field"], {"type": "graph_axis", "interval": "interval"}
        )
        choices = data["choices"]
        self.assertEqual(
            choices["graph_type"], [["bar", "bar"], ["line", "line"], ["pie", "pie"]]
        )
        self.assertEqual(choices["graph_order"], [["asc", "asc"], ["desc", "desc"]])
        self.assertEqual(
            choices["graph_axis"], [["row", "row"], ["measure", "measure"]]
        )
        # The kinds of CHOICES keep their values in every view type.
        self.assertIn(["fit", "fit"], choices["timeline_mode"])
        palette = {f["name"]: f["axes"] for f in data["palette"]}
        self.assertEqual(palette["create_date"], ["row"])
        self.assertEqual(palette["partner_longitude"], ["row", "measure"])
        self.assertNotIn("avatar_128", palette)
        self.assertNotIn("country_id", palette)
        self.assertIn("set_attribute", data["operations"])
        self.assertNotIn("add_field", data["operations"])

    def test_col_field_reads_as_a_group_by(self):
        """A field of type « col », and a field of a groupable type without
        a « type », which the graph reads as group-bys, show in the
        group-by lane and keep their axis in their block."""
        graph = self.make_view(
            "graph",
            '<graph><field name="country_id" type="col"/>'
            '<field name="name"/></graph>',
        )
        data = self.Editor.get_editor_data(
            "res.partner", graph.id, "graph", self.project.id
        )
        self.assertEqual(
            data["layout"]["axes"],
            {
                "row": ["//field[@name='country_id']", "//field[@name='name']"],
                "measure": [],
            },
        )
        self.assertEqual(data["layout"]["others"], [])
        self.assertEqual(data["blocks"]["children"][0]["axis"], "col")

    def test_fields_filed_as_the_graph_reads_them(self):
        """The graph groups by an untyped groupable field, in arch order with
        the typed ones: the first one is its X axis. An invisible field,
        and an untyped field of a type it cannot group by, are on no
        axis."""
        graph = self.make_view(
            "graph",
            '<graph><field name="company_id"/>'
            '<field name="country_id" type="row"/>'
            '<field name="partner_latitude"/>'
            '<field name="state_id" type="row" invisible="1"/>'
            '<field name="color" type="measure" invisible="True"/>'
            '<field name="partner_longitude" type="measure"/></graph>',
        )
        data = self.Editor.get_editor_data(
            "res.partner", graph.id, "graph", self.project.id
        )
        self.assertEqual(
            data["layout"]["axes"],
            {
                "row": [
                    "//field[@name='company_id']",
                    "//field[@name='country_id']",
                ],
                "measure": ["//field[@name='partner_longitude']"],
            },
        )
        self.assertEqual(
            data["layout"]["others"],
            [
                "//field[@name='partner_latitude']",
                "//field[@name='state_id']",
                "//field[@name='color']",
            ],
        )

    def test_changes(self):
        self.op(
            self.project,
            self.graph,
            type="add_existing_field",
            target="/graph",
            position="inside",
            field_name="create_date",
            axis="row",
            interval="month",
        )
        # From the measure to the group-bys, first of them.
        self.op(
            self.project,
            self.graph,
            type="move",
            source="//field[@name='partner_latitude']",
            target="//field[@name='country_id']",
            position="before",
            axis="row",
        )
        # And back to the measure, at the end.
        self.op(
            self.project,
            self.graph,
            type="move",
            source="//field[@name='partner_latitude']",
            target="/graph",
            position="inside",
            axis="measure",
        )
        for attribute, value in (("type", "line"), ("stacked", False)):
            self.op(
                self.project,
                self.graph,
                type="set_attribute",
                target="/graph",
                attribute=attribute,
                value=value,
            )
        self.op(
            self.project,
            self.graph,
            type="set_attribute",
            target="/graph",
            attribute="order",
            value="desc",
        )
        changes = self.project.change_ids
        self.assertEqual(
            changes[0]._payload()["node_attrs"], {"interval": "month", "type": "row"}
        )
        self.assertEqual(changes[1]._payload()["attrs"], {"type": "row"})
        self.assertIn("(measure)", changes[2].summary)
        arch = self.draft(self.project, self.graph)
        self.assertEqual(
            self.axes(arch),
            [
                ("country_id", "row", None),
                ("create_date", "row", "month"),
                ("partner_latitude", "measure", None),
            ],
        )
        self.assertEqual(
            (arch.get("type"), arch.get("stacked"), arch.get("order")),
            ("line", "False", "desc"),
        )

    def test_refused_operations(self):
        refused = [
            # A measure adds up a number field.
            {
                "type": "add_existing_field",
                "target": "/graph",
                "position": "inside",
                "field_name": "name",
                "axis": "measure",
            },
            # A graph has no column axis.
            {
                "type": "add_existing_field",
                "target": "/graph",
                "position": "inside",
                "field_name": "create_date",
                "axis": "col",
            },
            {
                "type": "set_attribute",
                "target": "//field[@name='country_id']",
                "attribute": "type",
                "value": "col",
            },
            # A measure takes no interval.
            {
                "type": "set_attribute",
                "target": "//field[@name='partner_latitude']",
                "attribute": "interval",
                "value": "month",
            },
            {
                "type": "set_attribute",
                "target": "/graph",
                "attribute": "type",
                "value": "area",
            },
            {
                "type": "set_attribute",
                "target": "/graph",
                "attribute": "order",
                "value": "name",
            },
            {
                "type": "set_attribute",
                "target": "/graph",
                "attribute": "sample",
                "value": True,
            },
            {"type": "add_field", "target": "/graph", "position": "inside"},
        ]
        for operation in refused:
            with self.subTest(operation=operation), self.assertRaises(UserError):
                self.op(self.project, self.graph, **operation)
        self.assertFalse(self.project.change_ids)

    def test_same_value_leaves_no_change(self):
        for target, attribute, value in (
            ("//field[@name='partner_latitude']", "type", "measure"),
            ("/graph", "type", "bar"),
        ):
            change = self.op(
                self.project,
                self.graph,
                type="set_attribute",
                target=target,
                attribute=attribute,
                value=value,
            )
            self.assertFalse(change)
        self.assertFalse(self.project.change_ids)

    def test_apply_discard_revert_undo(self):
        self.op(
            self.project,
            self.graph,
            type="set_attribute",
            target="/graph",
            attribute="type",
            value="pie",
        )
        studio = self.check_apply_is_idempotent(self.project, self.graph)
        self.assertEqual(self.view_arch(self.graph).get("type"), "pie")
        self.env["res.partner"].get_views([[self.graph.id, "graph"]])
        self.op(
            self.project,
            self.graph,
            type="hide",
            target="//field[@name='partner_latitude']",
            value=True,
        )
        self.assertNotIn(
            "partner_latitude",
            [n[0] for n in self.axes(self.draft(self.project, self.graph))],
        )
        self.project.action_undo(self.graph)
        self.assertEqual(self.project.state, "applied")
        self.project.action_revert()
        self.assertFalse(studio.exists())
        self.assertEqual(self.view_arch(self.graph).get("type"), "bar")
