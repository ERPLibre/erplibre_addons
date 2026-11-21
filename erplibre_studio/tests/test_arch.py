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
