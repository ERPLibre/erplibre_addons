# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.tests import BaseCase, tagged

from .. import arch as studio_arch

KANBAN = """
<kanban default_group_by="state">
    <field name="active"/>
    <templates>
        <t t-name="card">
            <widget name="web_ribbon" title="Archived"/>
            <main>
                <field name="name"/>
                <t t-if="record.active.raw_value">
                    <field name="email"/>
                </t>
                <t t-else="">
                    <span>-</span>
                </t>
                <footer><div/></footer>
            </main>
        </t>
    </templates>
</kanban>
"""

SEARCH = """
<search>
    <field name="name"/>
    <filter name="companies" string="Companies" domain="[('is_company', '=', True)]"/>
    <separator/>
    <group name="group_by">
        <filter name="by_country" string="Country" context="{'group_by': 'country_id'}"/>
    </group>
</search>
"""

PIVOT = """
<pivot>
    <field name="country_id" type="row"/>
    <field name="create_date" type="col" interval="month"/>
    <field name="partner_latitude" type="measure"/>
</pivot>
"""

TIMELINE = """
<timeline date_start="create_date" default_group_by="user_id" colors="#ec7063:is_company == True">
    <field name="name"/>
    <templates>
        <t t-name="timeline-item"><div><span t-esc="record.name"/></div></t>
    </templates>
</timeline>
"""


def spec_text(change, view_type):
    return etree.tostring(
        studio_arch.change_spec(change, view_type), encoding="unicode"
    )


@tagged("post_install", "-at_install")
class TestArchViews(BaseCase):
    """The arch helpers of the kanban, search, pivot and timeline views."""

    def test_template_xpath_by_its_name(self):
        root = etree.fromstring(KANBAN)
        card = root.xpath("//t[@t-name='card']")[0]
        self.assertEqual(studio_arch.node_xpath(root, card), "//t[@t-name='card']")
        main = card.find("main")
        self.assertEqual(
            studio_arch.node_xpath(root, main), "//t[@t-name='card']/main[1]"
        )
        else_node = main.xpath("t[@t-else]")[0]
        self.assertEqual(
            studio_arch.node_xpath(root, else_node), "//t[@t-name='card']/main[1]/t[2]"
        )
        self.assertEqual(list(studio_arch.templates_of(root)), ["card"])
        for node in root.iter(etree.Element):
            self.assertIs(root.xpath(studio_arch.node_xpath(root, node))[0], node)

    def test_kanban_drop_and_move_rules(self):
        root = etree.fromstring(KANBAN)
        main = root.xpath("//main")[0]
        if_node, else_node = main.xpath("t")
        name = main.find("field")
        declared = root.find("field")
        card = root.xpath("//t[@t-name='card']")[0]
        refusal = studio_arch.drop_refusal
        self.assertIsNone(refusal("kanban", main, "inside"))
        self.assertIsNone(refusal("kanban", card, "inside"))
        self.assertIsNone(refusal("kanban", name, "after"))
        self.assertIsNone(refusal("kanban", if_node, "before"))
        self.assertIsNone(refusal("kanban", else_node, "after"))
        # Inside a t-if chain: between the t-if and the t-else.
        self.assertEqual(refusal("kanban", if_node, "after").code, "chain")
        self.assertEqual(refusal("kanban", else_node, "before").code, "chain")
        # Outside the templates nothing is dropped, not even into <kanban>.
        self.assertEqual(refusal("kanban", root, "inside").code, "no_drop_inside")
        self.assertEqual(refusal("kanban", declared, "after").code, "no_drop")
        self.assertEqual(refusal("kanban", card, "after").code, "no_drop")
        self.assertEqual(studio_arch.chain_role(if_node), "if")
        self.assertEqual(studio_arch.chain_role(else_node), "else")
        self.assertIsNone(studio_arch.chain_role(name))
        self.assertEqual(studio_arch.move_refusal("kanban", if_node).code, "chain_move")
        self.assertEqual(
            studio_arch.move_refusal("kanban", declared).code, "outside_template"
        )
        self.assertEqual(studio_arch.move_refusal("kanban", card).code, "no_move")
        self.assertIsNone(studio_arch.move_refusal("kanban", name))
        self.assertEqual(
            studio_arch.hide_refusal("kanban", declared).code, "outside_template"
        )
        self.assertEqual(studio_arch.hide_refusal("kanban", if_node).code, "no_hide")
        self.assertIsNone(studio_arch.hide_refusal("kanban", name))

    def test_search_and_pivot_drop_rules(self):
        search = etree.fromstring(SEARCH)
        group = search.find("group")
        self.assertIsNone(studio_arch.drop_refusal("search", search, "inside"))
        self.assertIsNone(studio_arch.drop_refusal("search", group, "inside"))
        self.assertIsNone(
            studio_arch.drop_refusal("search", group.find("filter"), "before")
        )
        pivot = etree.fromstring(PIVOT)
        self.assertIsNone(studio_arch.drop_refusal("pivot", pivot, "inside"))
        self.assertIsNone(studio_arch.drop_refusal("pivot", pivot[0], "after"))
        self.assertEqual(
            studio_arch.drop_refusal("pivot", pivot[0], "inside").code,
            "no_drop_inside",
        )
        timeline = etree.fromstring(TIMELINE)
        # A field dropped into <timeline> is one the view loads.
        self.assertIsNone(studio_arch.drop_refusal("timeline", timeline, "inside"))
        self.assertEqual(studio_arch.hide_mode("search"), "remove")
        self.assertEqual(studio_arch.hide_mode("pivot"), "remove")
        self.assertEqual(studio_arch.hide_mode("kanban"), "invisible")
        self.assertEqual(studio_arch.hide_mode("list"), "column_invisible")

    def test_new_change_specs(self):
        remove = {"type": "remove", "xpath": "//filter[@name='companies']"}
        self.assertEqual(
            spec_text(remove, "search"),
            '<xpath expr="//filter[@name=\'companies\']" position="replace"/>',
        )
        set_attr = {
            "type": "set_attribute",
            "xpath": "/kanban",
            "payload": {"attribute": "default_group_by", "value": "country_id"},
        }
        self.assertEqual(
            spec_text(set_attr, "kanban"),
            '<xpath expr="/kanban" position="attributes">'
            '<attribute name="default_group_by">country_id</attribute></xpath>',
        )
        empty = dict(set_attr, payload={"attribute": "quick_create", "value": ""})
        self.assertIn('<attribute name="quick_create"/>', spec_text(empty, "kanban"))
        add_node = {
            "type": "add_node",
            "xpath": "//filter[@name='companies']",
            "position": "after",
            "payload": {
                "node": {
                    "tag": "filter",
                    "attrs": {
                        "name": "studio_filter_vat",
                        "string": "VAT",
                        "domain": "[('vat', '!=', False)]",
                    },
                }
            },
        }
        self.assertIn(
            "<filter domain=\"[('vat', '!=', False)]\" name=\"studio_filter_vat\" "
            'string="VAT"/>',
            spec_text(add_node, "search"),
        )
        # Neither a QWeb directive nor an unlisted tag goes through a change.
        unsafe = dict(set_attr, payload={"attribute": "t-out", "value": "1"})
        with self.assertRaises(studio_arch.ArchError) as caught:
            studio_arch.change_spec(unsafe, "kanban")
        self.assertEqual(caught.exception.code, "unsafe_attribute")
        script = dict(add_node, payload={"node": {"tag": "script", "attrs": {}}})
        with self.assertRaises(studio_arch.ArchError) as caught:
            studio_arch.change_spec(script, "search")
        self.assertEqual(caught.exception.code, "unknown_node")
        qweb = dict(
            add_node,
            payload={"node": {"tag": "widget", "attrs": {"t-att-class": "x"}}},
        )
        with self.assertRaises(studio_arch.ArchError):
            studio_arch.change_spec(qweb, "kanban")

    def test_move_with_attributes(self):
        root = etree.fromstring(PIVOT)
        change = {
            "key": 1,
            "type": "move",
            "xpath": "//field[@name='create_date']",
            "position": "after",
            "payload": {"source": "/pivot/field[1]"},
        }
        # Positional: the moved node is located where the move puts it.
        self.assertEqual(
            studio_arch.moved_node_xpath(root, change, "pivot"),
            "//field[@name='country_id']",
        )
        change["payload"].update(
            attrs={"type": "col"}, attrs_xpath="//field[@name='country_id']"
        )
        spec = studio_arch.change_spec(change, "pivot")
        self.assertEqual(spec.tag, "data")
        arch, errors = studio_arch.apply_changes(root, [change], "pivot")
        self.assertFalse(errors)
        self.assertEqual(
            [(f.get("name"), f.get("type")) for f in arch.iter("field")],
            [
                ("create_date", "col"),
                ("country_id", "col"),
                ("partner_latitude", "measure"),
            ],
        )
        # The view arch holds the two specs side by side.
        data = etree.fromstring(studio_arch.view_arch([change], "pivot"))
        self.assertEqual(
            [child.get("position") for child in data], ["after", "attributes"]
        )

    def test_values_built_from_forms(self):
        self.assertEqual(
            studio_arch.filter_condition("vat", "char", "set", None),
            ("vat", "!=", False),
        )
        self.assertEqual(
            studio_arch.filter_condition("is_company", "boolean", "=", True),
            ("is_company", "=", True),
        )
        with self.assertRaises(studio_arch.ArchError) as caught:
            studio_arch.filter_condition("is_company", "boolean", "ilike", "x")
        self.assertEqual(caught.exception.code, "bad_operator")
        self.assertEqual(
            studio_arch.domain_text([("name", "ilike", "it's")]),
            "[('name', 'ilike', \"it's\")]",
        )
        self.assertEqual(
            studio_arch.group_by_context("create_date", "month"),
            "{'group_by': 'create_date:month'}",
        )
        node = etree.fromstring("<filter context=\"{'group_by' : 'user_id'}\"/>")
        self.assertEqual(studio_arch.group_by_of(node), "user_id")
        self.assertIsNone(studio_arch.group_by_of(etree.fromstring("<filter/>")))
        rules = [
            {
                "color": "#ec7063",
                "field": "is_company",
                "operator": "==",
                "value": True,
            },
            {"color": "green", "field": "name", "operator": "!=", "value": "x"},
        ]
        text = studio_arch.colors_text(rules)
        self.assertEqual(text, "#ec7063:is_company == True;green:name != 'x'")
        self.assertEqual(
            studio_arch.colors_rules(text),
            [
                {"color": "#ec7063", "expression": "is_company == True"},
                {"color": "green", "expression": "name != 'x'"},
            ],
        )
        for bad in (
            {"color": "red;x", "field": "name", "operator": "==", "value": 1},
            {"color": "red", "field": "a b", "operator": "==", "value": 1},
            {"color": "red", "field": "name", "operator": "in", "value": 1},
        ):
            with self.assertRaises(studio_arch.ArchError):
                studio_arch.colors_text([bad])
        self.assertEqual(studio_arch.order_fields("name asc, id desc"), ["name", "id"])
        with self.assertRaises(studio_arch.ArchError):
            studio_arch.order_fields("name; drop")
        self.assertEqual(
            studio_arch.node_name_from_label(
                "studio_filter", "Société", {"studio_filter_societe"}
            ),
            "studio_filter_societe_2",
        )

    def test_blocks_per_view_type(self):
        kanban = studio_arch.arch_blocks(etree.fromstring(KANBAN), "kanban", {})
        self.assertEqual((kanban["kind"], kanban["drop"]), ("container", False))
        declared, templates = kanban["children"]
        self.assertEqual((declared["kind"], declared["movable"]), ("field", False))
        self.assertFalse(declared["in_template"])
        card = templates["children"][0]
        self.assertEqual(
            (card["kind"], card["template"], card["drop"]), ("template", "card", True)
        )
        ribbon, main = card["children"]
        self.assertEqual((ribbon["kind"], ribbon["name"]), ("widget", "web_ribbon"))
        name, if_node, else_node, footer = main["children"]
        self.assertEqual((name["kind"], name["movable"]), ("field", True))
        self.assertEqual((if_node["chain"], if_node["movable"]), ("if", False))
        self.assertEqual(else_node["chain"], "else")
        # An empty element of a template still takes a drop.
        self.assertEqual(footer["children"][0]["kind"], "container")

        search = studio_arch.arch_blocks(etree.fromstring(SEARCH), "search", {})
        kinds = [child["kind"] for child in search["children"]]
        self.assertEqual(kinds, ["field", "filter", "separator", "container"])
        self.assertEqual(search["children"][1]["domain"], "[('is_company', '=', True)]")
        group_by = search["children"][3]["children"][0]
        self.assertEqual(
            (group_by["kind"], group_by["group_by"]), ("group_by", "country_id")
        )

        pivot = studio_arch.arch_blocks(etree.fromstring(PIVOT), "pivot", {})
        self.assertTrue(pivot["drop"])
        self.assertEqual(
            [(b["axis"], b["interval"]) for b in pivot["children"]],
            [("row", None), ("col", "month"), ("measure", None)],
        )

        timeline = studio_arch.arch_blocks(etree.fromstring(TIMELINE), "timeline", {})
        self.assertTrue(timeline["drop"])
        self.assertEqual(timeline["attrs"]["date_start"], "create_date")
        item = timeline["children"][1]["children"][0]
        self.assertEqual(item["template"], "timeline-item")
        self.assertEqual(
            studio_arch.shown_field_names(etree.fromstring(TIMELINE), "timeline"),
            {"name"},
        )

    def test_content_directives_take_no_drop(self):
        root = etree.fromstring(
            """
            <kanban>
                <templates>
                    <t t-name="card">
                        <span><t t-esc="record.name.value"/></span>
                        <div t-out="record.email.value"><span>-</span></div>
                        <t t-set="label" t-value="'x'"/>
                        <t t-call="other"/>
                        <t t-if="record.active.raw_value"><span>A</span></t>
                        <div t-foreach="[1, 2]" t-as="i" t-key="i"/>
                    </t>
                </templates>
            </kanban>
            """
        )
        card = root.xpath("//t[@t-name='card']")[0]
        span, div_out, t_set, t_call, t_if, div_foreach = studio_arch.elements(card)
        esc = span[0]
        for node in (esc, div_out, t_set, t_call):
            with self.subTest(node=etree.tostring(node)):
                refusal = studio_arch.drop_refusal("kanban", node, "inside")
                self.assertEqual(refusal.code, "content_directive")
        # Next to a node in the body of a t-out: still its content.
        self.assertEqual(
            studio_arch.drop_refusal("kanban", div_out[0], "after").code,
            "content_directive",
        )
        self.assertIsNone(studio_arch.drop_refusal("kanban", t_if, "inside"))
        self.assertIsNone(studio_arch.drop_refusal("kanban", div_foreach, "inside"))
        self.assertIsNone(studio_arch.drop_refusal("kanban", t_call, "after"))
        blocks = studio_arch.arch_blocks(root, "kanban", {})
        card_block = blocks["children"][0]["children"][0]
        drops = {
            child["tag"] + str(index): child.get("drop")
            for index, child in enumerate(card_block["children"])
        }
        self.assertEqual(
            drops,
            {
                "span0": False,
                "div1": False,
                "t2": False,
                "t3": False,
                "t4": True,
                "div5": True,
            },
        )

    def test_hide_refused_on_the_head_of_a_chain(self):
        root = etree.fromstring(
            """
            <kanban>
                <templates>
                    <t t-name="card">
                        <span t-if="record.is_company.raw_value">A</span>
                        <span t-elif="record.vat.raw_value">B</span>
                        <span t-else="">C</span>
                        <span t-if="record.email.raw_value">D</span>
                    </t>
                </templates>
            </kanban>
            """
        )
        head, middle, last, alone = root.xpath("//t[@t-name='card']/span")
        self.assertEqual(studio_arch.hide_refusal("kanban", head).code, "chain_hide")
        self.assertEqual(studio_arch.hide_refusal("kanban", middle).code, "chain_hide")
        # Without it, the chain still compiles and means the same.
        self.assertIsNone(studio_arch.hide_refusal("kanban", last))
        # A t-if alone is no chain.
        self.assertIsNone(studio_arch.hide_refusal("kanban", alone))

    def test_color_values_that_break_the_attribute(self):
        for value in ("2026-01-01 08:00:00", "a;b", "a:b"):
            rule = {"color": "red", "field": "name", "operator": "==", "value": value}
            with self.subTest(value=value):
                with self.assertRaises(studio_arch.ArchError) as caught:
                    studio_arch.colors_text([rule])
                self.assertEqual(caught.exception.code, "bad_color_value")
        self.assertEqual(
            studio_arch.colors_text(
                [
                    {
                        "color": "red",
                        "field": "date",
                        "operator": ">",
                        "value": "2026-01-01",
                    }
                ]
            ),
            "red:date > '2026-01-01'",
        )
        self.assertNotIn("many2one", studio_arch.COLOR_FIELD_TYPES)
        self.assertNotIn("datetime", studio_arch.COLOR_FIELD_TYPES)

    def test_timeline_item_fields(self):
        self.assertEqual(studio_arch.item_value("email", "text"), "record.email or ''")
        self.assertEqual(studio_arch.item_value("color", "raw"), "record.color")
        self.assertEqual(
            [
                studio_arch.item_kind(t)
                for t in ("char", "integer", "boolean", "many2one")
            ],
            ["text", "raw", "raw", "many2one"],
        )
        self.assertEqual(
            studio_arch.item_value("user_id", "many2one"),
            "record.user_id and record.user_id[1] or ''",
        )
        with self.assertRaises(studio_arch.ArchError):
            studio_arch.item_value("a or b", "text")
        with self.assertRaises(studio_arch.ArchError):
            studio_arch.item_value("email", "char")
        shown = etree.fromstring(
            """
            <div>
                <span t-esc="record.name"/>
                <span name="user_id" t-out="record.user_id and record.user_id[1]"/>
                <span name="ref"><t t-esc="record.ref"/></span>
                <span t-esc="record.email or ''"/>
                <span t-esc="record.name.value"/>
                <span>Label <t t-esc="record.city"/></span>
            </div>
            """
        )
        self.assertEqual(
            [studio_arch.item_field_name(node) for node in shown],
            ["name", "user_id", "ref", "email", None, None],
        )
        change = {
            "type": "add_existing_field",
            "xpath": "//t[@t-name='timeline-item']/div[1]",
            "position": "inside",
            "payload": {"field_name": "user_id", "item": "many2one", "load": True},
        }
        spec = studio_arch.change_spec(change, "timeline")
        self.assertEqual(spec.tag, "data")
        self.assertEqual(
            etree.tostring(spec[0][0], encoding="unicode"),
            '<span name="user_id" t-esc="record.user_id and record.user_id[1] or \'\'"/>',
        )
        self.assertEqual(
            (spec[1].get("expr"), spec[1].get("position"), spec[1][0].get("name")),
            ("/timeline/templates", "before", "user_id"),
        )
        root = etree.fromstring(TIMELINE)
        arch, errors = studio_arch.apply_changes(
            root, [dict(change, key=1)], "timeline"
        )
        self.assertFalse(errors)
        self.assertEqual(
            [child.get("name") for child in arch if child.tag == "field"],
            ["name", "user_id"],
        )
        blocks = studio_arch.arch_blocks(arch, "timeline", {})
        div = blocks["children"][2]["children"][0]["children"][0]
        self.assertEqual(
            [(b["kind"], b["name"], b["movable"]) for b in div["children"]],
            [("field", "name", True), ("field", "user_id", True)],
        )
        self.assertEqual(
            studio_arch.shown_field_names(arch, "timeline"), {"name", "user_id"}
        )

    def test_nodes_found_by_the_change_that_added_them(self):
        root = etree.fromstring(SEARCH)
        separator = {
            "key": 1,
            "type": "add_node",
            "xpath": "/search/separator[1]",
            "position": "after",
            "payload": {"node": {"tag": "separator", "attrs": {}}},
        }
        hide = {
            "key": 2,
            "type": "remove",
            "xpath": "/search/separator[2]",
            "position": "replace",
            "payload": {},
        }
        other = {
            "key": 3,
            "type": "remove",
            "xpath": "/search/separator[1]",
            "position": "replace",
            "payload": {},
        }
        changes = [separator, hide, other]
        # Positional: the second separator is the one the change added.
        self.assertEqual(
            studio_arch.added_key(root, [separator], "search", "/search/separator[2]"),
            "1",
        )
        self.assertIsNone(
            studio_arch.added_key(root, [separator], "search", "/search/separator[1]")
        )
        self.assertEqual(studio_arch.changes_on_added(root, changes, "search", 1), [2])
        arch, _errors = studio_arch.apply_changes(root, changes, "search", mark=True)
        self.assertFalse(arch.xpath(f"//*[@{studio_arch.ADDED_MARK}]"))
        # The mark never reaches the arch of a view.
        self.assertNotIn(
            studio_arch.ADDED_MARK, studio_arch.view_arch(changes, "search")
        )
