# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.tests import BaseCase, tagged

from .. import arch as studio_arch

FORM = """
<form>
    <sheet>
        <group>
            <group name="left">
                <field name="name"/>
                <field name="phone"/>
            </group>
            <group>
                <field name="email"/>
            </group>
        </group>
        <notebook>
            <page string="Lines">
                <field name="child_ids">
                    <list><field name="name"/></list>
                </field>
            </page>
        </notebook>
    </sheet>
</form>
"""


def spec_text(change, view_type="form"):
    return etree.tostring(
        studio_arch.change_spec(change, view_type), encoding="unicode"
    )


@tagged("post_install", "-at_install")
class TestArch(BaseCase):
    def setUp(self):
        super().setUp()
        self.root = etree.fromstring(FORM)

    def test_xpath_by_name_then_by_position(self):
        root = self.root
        self.assertEqual(studio_arch.node_xpath(root, root), "/form")
        email = root.xpath("//field[@name='email']")[0]
        self.assertEqual(studio_arch.node_xpath(root, email), "//field[@name='email']")
        left = root.xpath("//group[@name='left']")[0]
        self.assertEqual(studio_arch.node_xpath(root, left), "//group[@name='left']")
        right = left.getnext()
        self.assertEqual(
            studio_arch.node_xpath(root, right),
            "/form/sheet[1]/group[1]/group[2]",
        )
        # « name » shows twice: the second is located from its ancestors.
        inner = root.xpath("//list/field[@name='name']")[0]
        path = studio_arch.node_xpath(root, inner)
        self.assertEqual(path, "//field[@name='child_ids']/list[1]/field[1]")
        self.assertIs(root.xpath(path)[0], inner)
        for node in root.iter():
            if isinstance(node.tag, str):
                self.assertIs(root.xpath(studio_arch.node_xpath(root, node))[0], node)

    def test_change_specs(self):
        add = {
            "type": "add_field",
            "xpath": "//field[@name='phone']",
            "position": "after",
            "payload": {
                "field_name": "x_note",
                "node_attrs": {"optional": "show"},
            },
        }
        self.assertEqual(
            spec_text(add),
            '<xpath expr="//field[@name=\'phone\']" position="after">'
            '<field name="x_note" optional="show"/></xpath>',
        )
        move = {
            "type": "move",
            "xpath": "//field[@name='name']",
            "position": "before",
            "payload": {"source": "//field[@name='email']"},
        }
        self.assertEqual(
            spec_text(move),
            '<xpath expr="//field[@name=\'name\']" position="before">'
            '<xpath expr="//field[@name=\'email\']" position="move"/></xpath>',
        )
        hide = {
            "type": "hide",
            "xpath": "//field[@name='email']",
            "payload": {"value": True},
        }
        self.assertIn('<attribute name="invisible">True</attribute>', spec_text(hide))
        self.assertIn(
            '<attribute name="column_invisible">True</attribute>',
            spec_text(hide, "list"),
        )
        relabel = {
            "type": "relabel",
            "xpath": "//field[@name='email']",
            "payload": {"value": "Mail"},
        }
        self.assertIn('<attribute name="string">Mail</attribute>', spec_text(relabel))
        optional = {
            "type": "optional",
            "xpath": "//field[@name='email']",
            "payload": {"value": ""},
        }
        self.assertIn('<attribute name="optional"/>', spec_text(optional, "list"))
        with self.assertRaises(studio_arch.ArchError):
            studio_arch.change_spec({"type": "drop_table", "xpath": "/form"}, "form")

    def test_apply_changes_in_sequence(self):
        changes = [
            {
                "key": 1,
                "type": "move",
                "xpath": "//field[@name='name']",
                "position": "before",
                "payload": {"source": "//field[@name='email']"},
            },
            # Positional, located in the arch left by the move: the second
            # group is now empty.
            {
                "key": 2,
                "type": "add_field",
                "xpath": "/form/sheet/group[1]/group[2]",
                "position": "inside",
                "payload": {"field_name": "x_note"},
            },
            {
                "key": 3,
                "type": "relabel",
                "xpath": "//field[@name='nothing']",
                "payload": {"value": "?"},
            },
            {
                "key": 4,
                "type": "relabel",
                "xpath": "//field[@name='phone']",
                "payload": {"value": "Tel"},
            },
        ]
        arch, errors = studio_arch.apply_changes(self.root, changes, "form")
        self.assertEqual(list(errors), [3])
        left = arch.xpath("//group[@name='left']/field")
        self.assertEqual([f.get("name") for f in left], ["email", "name", "phone"])
        self.assertEqual(left[2].get("string"), "Tel")
        right = arch.xpath("/form/sheet/group[1]/group[2]/field")
        self.assertEqual([f.get("name") for f in right], ["x_note"])
        # The arch given is left untouched.
        self.assertEqual(len(self.root.xpath("//field[@name='x_note']")), 0)

    def test_dependent_changes(self):
        """The changes that no longer act on the same node once others
        leave: a positional XPath that finds another node, a node a removed
        change adds, and so on down the chain; a change by name stays."""
        root = etree.fromstring(
            '<form><group><field name="a"/></group>'
            '<group><field name="b"/></group></form>'
        )
        dependent = studio_arch.dependent_changes
        move = {
            "key": 1,
            "type": "move",
            "xpath": "/form/group[1]",
            "position": "before",
            "payload": {"source": "/form/group[2]"},
        }
        # The first group is the moved one only while the move applies.
        title = {
            "key": 2,
            "type": "set_attribute",
            "xpath": "/form/group[1]",
            "payload": {"attribute": "string", "value": "First"},
        }
        by_name = {
            "key": 3,
            "type": "relabel",
            "xpath": "//field[@name='a']",
            "payload": {"value": "A"},
        }
        changes = [move, title, by_name]
        self.assertEqual(dependent(root, changes, "form", {1}), [2])
        self.assertEqual(dependent(root, changes, "form", {2}), [])
        self.assertEqual(dependent(root, changes, "form", {3}), [])
        # The marks of the comparison stay out of the arch given.
        self.assertFalse(root.xpath(f"//*[@{studio_arch.UID_MARK}]"))
        add = {
            "key": 1,
            "type": "add_field",
            "xpath": "//field[@name='a']",
            "position": "after",
            "payload": {"field_name": "x_new"},
        }
        relabel = {
            "key": 2,
            "type": "relabel",
            "xpath": "//field[@name='x_new']",
            "payload": {"value": "New"},
        }
        self.assertEqual(dependent(root, [add, relabel, by_name], "form", {1}), [2])
        group = {
            "key": 1,
            "type": "add_node",
            "xpath": "/form/group[2]",
            "position": "after",
            "payload": {"node": {"tag": "group", "attrs": {"name": "x_outer"}}},
        }
        inner = {
            "key": 2,
            "type": "add_node",
            "xpath": "//group[@name='x_outer']",
            "position": "inside",
            "payload": {"node": {"tag": "group", "attrs": {"name": "x_inner"}}},
        }
        field = {
            "key": 3,
            "type": "add_field",
            "xpath": "//group[@name='x_inner']",
            "position": "inside",
            "payload": {"field_name": "x_deep"},
        }
        chain = [group, inner, by_name, field]
        self.assertEqual(dependent(root, chain, "form", {1}), [2, 3])
        self.assertEqual(dependent(root, chain, "form", {2}), [3])

    def test_view_arch(self):
        text = studio_arch.view_arch(
            [
                {
                    "type": "hide",
                    "xpath": "//field[@name='email']",
                    "payload": {"value": True},
                }
            ],
            "list",
        )
        data = etree.fromstring(text)
        self.assertEqual(data.tag, "data")
        self.assertEqual(data[0].get("position"), "attributes")

    def test_blocks(self):
        blocks = studio_arch.arch_blocks(
            self.root, "form", {"name": {"string": "Name"}}
        )
        self.assertEqual(blocks["kind"], "container")
        sheet = blocks["children"][0]
        self.assertTrue(sheet["drop"])
        left = sheet["children"][0]["children"][0]
        self.assertEqual(left["path"], "//group[@name='left']")
        name = left["children"][0]
        self.assertEqual(
            (name["kind"], name["name"], name["label"]),
            ("field", "name", "Name"),
        )
        notebook = sheet["children"][1]
        self.assertFalse(notebook["drop"])
        child_ids = notebook["children"][0]["children"][0]
        # An x2many is a leaf: its sub-view is not edited.
        self.assertNotIn("children", child_ids)
        title = etree.fromstring(
            "<form><div><h1><field name='name'/></h1></div></form>"
        )
        h1 = studio_arch.arch_blocks(title, "form", {})["children"][0]["children"][0]
        self.assertEqual((h1["kind"], h1["drop"]), ("container", False))
        self.assertEqual(h1["children"][0]["name"], "name")
        list_root = etree.fromstring(
            "<list><field name='name'/><button name='x'/></list>"
        )
        blocks = studio_arch.arch_blocks(list_root, "list", {})
        self.assertEqual([b["kind"] for b in blocks["children"]], ["field", "other"])

    def test_names(self):
        self.assertEqual(
            studio_arch.field_name_from_label("Note privée", set()),
            "x_note_privee",
        )
        self.assertEqual(
            studio_arch.field_name_from_label("Note", {"x_note", "x_note_2"}),
            "x_note_3",
        )
        self.assertEqual(studio_arch.field_name_from_label("!!", set()), "x_field")
        self.assertTrue(studio_arch.valid_field_name("x_a1"))
        self.assertFalse(studio_arch.valid_field_name("a1"))
        self.assertFalse(studio_arch.valid_field_name("x_A"))
        for name in ("studio_partner", "a1"):
            self.assertTrue(studio_arch.valid_module_name(name))
        for name in ("", "1a", "Studio", "a-b", "a b", "a" * 65):
            self.assertFalse(studio_arch.valid_module_name(name))

    def test_field_name_refusal(self):
        def code(name, **kwargs):
            refusal = studio_arch.field_name_refusal(name, **kwargs)
            return refusal and refusal.code

        self.assertIsNone(code("x_a1"))
        self.assertEqual(code("a1"), "prefix")
        self.assertIsNone(code("a1", prefix_required=False))
        self.assertEqual(code("x_"), "prefix")
        self.assertEqual(code("X_a"), "format")
        self.assertEqual(code("x_é"), "format")
        self.assertEqual(code("1a", prefix_required=False), "format")
        self.assertEqual(code("x_" + "a" * 62), "format")
        self.assertIsNone(code("x_" + "a" * 61))
        self.assertEqual(code("class"), "reserved")
        self.assertEqual(code("_foo"), "reserved")
        self.assertEqual(code("in_group_7"), "reserved")
        self.assertEqual(code("sel_groups_1_2", prefix_required=False), "reserved")
        self.assertEqual(code("x_write", reserved={"x_write"}), "reserved")
        self.assertEqual(
            studio_arch.field_name_checks("Class"),
            {"format": False, "reserved": True, "prefix": False},
        )
        self.assertFalse(studio_arch.valid_field_name("a1"))
        self.assertTrue(studio_arch.valid_field_name("a1", prefix_required=False))
        # The relation tables keep their own rule: « x_ » always.
        self.assertTrue(studio_arch.valid_table_name("x_mod_a_b_rel"))
        self.assertFalse(studio_arch.valid_table_name("mod_a_b_rel"))
        self.assertFalse(studio_arch.valid_table_name("x_" + "a" * 62))

    def test_errors_carry_a_code(self):
        root = etree.fromstring("<form><field name='a'/></form>")
        with self.assertRaises(studio_arch.ArchError) as caught:
            studio_arch.locate(root, "//field[@name='b']")
        self.assertEqual(caught.exception.code, "no_node")
        self.assertEqual(caught.exception.params, {"xpath": "//field[@name='b']"})
        with self.assertRaises(studio_arch.ArchError) as caught:
            studio_arch.locate(root, "//field[")
        self.assertEqual(caught.exception.code, "invalid_xpath")
        _arch, errors = studio_arch.apply_changes(
            root,
            [{"key": 1, "type": "drop", "xpath": "/form", "payload": {}}],
            "form",
            message=lambda exc: f"code {exc.code}",
        )
        self.assertEqual(errors, {1: "code unknown_change"})
        self.assertTrue(studio_arch.constant_true("True"))
        self.assertFalse(studio_arch.constant_true("is_company"))
        self.assertFalse(studio_arch.constant_true(None))

    def test_model_names(self):
        for name in ("x_item", "x_a1_b", "x_" + "a" * 48):
            self.assertTrue(studio_arch.valid_model_name(name), name)
        for name in (
            "",
            "x_",
            "x_1a",
            "x_A",
            "item",
            "x_a.b",
            "x_a-b",
            "x_" + "a" * 49,
        ):
            self.assertFalse(studio_arch.valid_model_name(name), name)
        self.assertEqual(
            studio_arch.model_name_from_label("Équipe à faire", set()),
            "x_equipe_a_faire",
        )
        self.assertEqual(
            studio_arch.model_name_from_label("Item", {"x_item", "x_item_2"}),
            "x_item_3",
        )
        self.assertEqual(studio_arch.model_name_from_label("!!", set()), "x_model")
        self.assertEqual(studio_arch.model_name_from_label("3 D", set()), "x_model_3_d")
        long_name = studio_arch.model_name_from_label("word " * 30, set())
        self.assertTrue(studio_arch.valid_model_name(long_name))
        self.assertTrue(
            studio_arch.valid_model_name(
                studio_arch.model_name_from_label("word " * 30, {long_name})
            )
        )

    def test_model_name_refusal(self):
        def code(name, **kwargs):
            refusal = studio_arch.model_name_refusal(name, **kwargs)
            return refusal and refusal.code

        for prefix_required in (True, False):
            self.assertIsNone(code("x_studio_demo", prefix_required=prefix_required))
        self.assertEqual(code("studio_demo.book"), "prefix")
        self.assertIsNone(code("studio_demo.book", prefix_required=False))
        self.assertEqual(code("x_studio.book"), "prefix")
        for name in ("Studio", "studio..book", ".book", "book.", "1book", "a.1b"):
            with self.subTest(name=name):
                self.assertEqual(code(name, prefix_required=False), "format")
        # The table, dots as _, holds MODEL_NAME_SIZE characters at most.
        self.assertEqual(
            code("a" * 25 + "." + "b" * 25, prefix_required=False), "format"
        )
        self.assertIsNone(code("a" * 24 + "." + "b" * 25, prefix_required=False))
        self.assertEqual(code("class", prefix_required=False), "reserved")
        self.assertIsNone(code("studio_class", prefix_required=False))
        self.assertIsNone(code("studio.class", prefix_required=False))
        for name in ("ir.studio_demo", "res", "res.studio_demo", "web.x", "report"):
            with self.subTest(name=name):
                self.assertEqual(code(name, prefix_required=False), "reserved")
        self.assertIsNone(code("resource_demo", prefix_required=False))
        self.assertEqual(
            code(
                "studio_demo.shelf",
                prefix_required=False,
                reserved={"studio_demo.shelf"},
            ),
            "reserved",
        )
        self.assertEqual(
            studio_arch.model_name_checks("Res"),
            {"format": False, "reserved": True, "prefix": False},
        )
        self.assertEqual(
            studio_arch.model_table("studio_demo.book"), "studio_demo_book"
        )
        self.assertTrue(studio_arch.valid_model_name("studio_demo.book", False))
        self.assertFalse(studio_arch.valid_model_name("studio_demo.book"))

    def test_default_model_arch(self):
        form = etree.fromstring(studio_arch.default_model_arch("form", "Item"))
        self.assertEqual(form.get("string"), "Item")
        self.assertEqual(
            [node.get("name") for node in form.iter("field", "group")],
            ["x_name", "studio_main", "studio_left", "studio_right"],
        )
        self.assertEqual(form.find(".//field").get("placeholder"), "Item")
        self.assertFalse(form.xpath("//chatter"))
        form = etree.fromstring(studio_arch.default_model_arch("form", "Item", True))
        self.assertEqual(form[-1].tag, "chatter")
        for view_type in ("list", "search"):
            root = etree.fromstring(studio_arch.default_model_arch(view_type, "Item"))
            self.assertEqual(root.tag, view_type)
            self.assertEqual([f.get("name") for f in root], ["x_name"])
        # The label is an attribute value: lxml escapes it.
        form = etree.fromstring(studio_arch.default_model_arch("form", 'A "b" <c>'))
        self.assertEqual(form.get("string"), 'A "b" <c>')
        with self.assertRaises(studio_arch.ArchError):
            studio_arch.default_model_arch("kanban", "Item")

    def test_default_model_arch_options(self):
        plain = etree.fromstring(studio_arch.default_model_arch("form", "Item"))
        form = etree.fromstring(
            studio_arch.default_model_arch("form", "Item", archivable=True)
        )
        ribbon = form.find("sheet")[0]
        self.assertEqual(
            (ribbon.tag, ribbon.get("name"), ribbon.get("invisible")),
            ("widget", "web_ribbon", "x_active"),
        )
        self.assertEqual(
            form.find("sheet")[-1].attrib, {"name": "x_active", "invisible": "1"}
        )
        # The nodes of the plain form keep their paths.
        for xpath in ("/form/sheet/div[1]", "//group[@name='studio_left']"):
            node = studio_arch.locate(plain, xpath)
            self.assertEqual(
                studio_arch.node_xpath(plain, node),
                studio_arch.node_xpath(form, studio_arch.locate(form, xpath)),
            )
        self.assertEqual(
            studio_arch.node_xpath(form, form.find("sheet/div")),
            "/form/sheet[1]/div[1]",
        )
        # The list: the handle first; the search: the filter last.
        root = etree.fromstring(
            studio_arch.default_model_arch("list", "Item", manual_order=True)
        )
        self.assertEqual(
            [(f.get("name"), f.get("widget")) for f in root],
            [("x_sequence", "handle"), ("x_name", None)],
        )
        root = etree.fromstring(
            studio_arch.default_model_arch("search", "Item", archivable=True)
        )
        self.assertEqual([n.tag for n in root], ["field", "filter"])
        self.assertEqual(root[1].get("domain"), "[('x_active', '=', False)]")
        # An option leaves the views it does not concern as they are.
        for view_type, option in (
            ("form", "manual_order"),
            ("list", "archivable"),
            ("search", "manual_order"),
        ):
            self.assertEqual(
                studio_arch.default_model_arch(view_type, "Item", **{option: True}),
                studio_arch.default_model_arch(view_type, "Item"),
            )

    def test_order_terms(self):
        self.assertEqual(
            studio_arch.order_terms("x_name DESC, id"),
            [("x_name", "desc"), ("id", "asc")],
        )
        with self.assertRaises(studio_arch.ArchError):
            studio_arch.order_terms("x_name; drop")

    def test_chatter_stays_in_place(self):
        root = etree.fromstring(
            studio_arch.default_model_arch("form", "Item", chatter=True)
        )
        chatter = root.find("chatter")
        self.assertEqual(studio_arch.move_refusal("form", chatter).code, "no_move")
        self.assertEqual(studio_arch.hide_refusal("form", chatter).code, "no_hide")
        self.assertEqual(
            studio_arch.drop_refusal("form", chatter, "after").code, "no_drop"
        )
        self.assertIsNotNone(studio_arch.drop_refusal("form", chatter, "inside"))
        block = studio_arch.arch_blocks(root, "form", {})["children"][-1]
        self.assertEqual(
            (block["tag"], block["kind"], block["movable"]), ("chatter", "other", False)
        )
        self.assertNotIn("drop", block)
