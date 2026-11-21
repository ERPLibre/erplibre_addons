# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StudioCase

CARD = "//t[@t-name='card']"


@tagged("post_install", "-at_install")
class TestKanbanStudio(StudioCase):
    """The studio on the kanban view of the contacts."""

    def setUp(self):
        super().setUp()
        self.kanban = self.env.ref("base.res_partner_kanban_view")
        self.project = self.make_project("studio_test_kanban")

    def card_fields(self, arch):
        return [n.get("name") for n in arch.xpath(f"{CARD}//field")]

    def test_editor_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.kanban.id, "kanban", self.project.id
        )
        self.assertEqual(data["view_type"], "kanban")
        self.assertIn("kanban", data["view_types"])
        self.assertEqual(data["hide_mode"], "invisible")
        self.assertEqual(data["layout"]["card"], CARD)
        self.assertEqual(data["layout"]["templates"], {"card": CARD})
        self.assertIn("active", data["layout"]["loaded_fields"])
        self.assertIn("web_ribbon", data["layout"]["widgets"])
        self.assertIn("add_widget", data["operations"])
        self.assertNotIn("relabel", data["operations"])
        self.assertEqual(data["settable"]["kanban"]["default_group_by"], "group_field")
        self.assertIn(["country_id", "Country"], data["choices"]["group_field"])
        self.assertNotIn("avatar_128", dict(data["choices"]["group_field"]))
        root = data["blocks"]
        self.assertFalse(root["drop"])
        declared = [b for b in root["children"] if b["tag"] == "field"]
        self.assertTrue(declared)
        self.assertFalse(any(b["movable"] or b["in_template"] for b in declared))
        templates = next(b for b in root["children"] if b["tag"] == "templates")
        card = templates["children"][0]
        self.assertEqual(
            (card["path"], card["kind"], card["drop"]), (CARD, "template", True)
        )
        palette = [f["name"] for f in data["palette"]]
        # « active » is only loaded, not shown: it can go into the card.
        self.assertIn("active", palette)
        self.assertIn("phone", palette)
        self.assertNotIn("email", palette)

    def test_changes_and_their_xpath(self):
        self.op(
            self.project,
            self.kanban,
            type="add_existing_field",
            target="//field[@name='email']",
            position="after",
            field_name="phone",
            widget="phone",
        )
        self.op(
            self.project,
            self.kanban,
            type="move",
            source="//field[@name='email']",
            target=f"{CARD}/main[1]/div[1]",
            position="before",
        )
        self.op(
            self.project,
            self.kanban,
            type="hide",
            target="//field[@name='city']",
            value=True,
        )
        self.op(
            self.project,
            self.kanban,
            type="set_attribute",
            target="/kanban",
            attribute="default_group_by",
            value="country_id",
        )
        self.op(
            self.project,
            self.kanban,
            type="set_attribute",
            target="/kanban",
            attribute="quick_create",
            value=False,
        )
        self.op(
            self.project,
            self.kanban,
            type="add_widget",
            target=f"{CARD}/main[1]/footer[1]/div[1]",
            position="inside",
            widget="web_ribbon",
            attrs={"title": "VIP", "bg_color": "text-bg-success"},
        )
        changes = self.project.change_ids
        self.assertEqual(
            [(c.change_type, c.xpath, c.position) for c in changes],
            [
                ("add_existing_field", "//field[@name='email']", "after"),
                ("move", f"{CARD}/main[1]/div[1]", "before"),
                ("hide", "//field[@name='city']", "attributes"),
                ("set_attribute", "/kanban", "attributes"),
                ("set_attribute", "/kanban", "attributes"),
                ("add_node", f"{CARD}/main[1]/footer[1]/div[1]", "inside"),
            ],
        )
        self.assertEqual(changes[0]._payload()["node_attrs"], {"widget": "phone"})
        arch = self.draft(self.project, self.kanban)
        main = arch.xpath(f"{CARD}/main")[0]
        self.assertEqual(
            [n.get("name") for n in main.iterchildren("field")][:2], ["email", "phone"]
        )
        self.assertEqual(arch.xpath("//field[@name='phone']")[0].get("widget"), "phone")
        self.assertEqual(
            arch.xpath("//field[@name='city']")[0].get("invisible"), "True"
        )
        self.assertEqual(
            (arch.get("default_group_by"), arch.get("quick_create")),
            ("country_id", "False"),
        )
        ribbon = arch.xpath(f"{CARD}/main/footer/div/widget")[0]
        self.assertEqual(
            (ribbon.get("name"), ribbon.get("title"), ribbon.get("bg_color")),
            ("web_ribbon", "VIP", "text-bg-success"),
        )

        # The same attribute again replaces its change; its original value
        # removes it.
        self.op(
            self.project,
            self.kanban,
            type="set_attribute",
            target="/kanban",
            attribute="default_group_by",
            value="user_id",
        )
        group_by = self.project.change_ids.filtered(
            lambda c: c.change_type == "set_attribute"
            and c._payload()["attribute"] == "default_group_by"
        )
        self.assertEqual(len(group_by), 1)
        self.assertEqual(group_by._payload()["fields"], ["user_id"])
        original = self.kanban._get_combined_arch().get("default_group_by") or ""
        self.op(
            self.project,
            self.kanban,
            type="set_attribute",
            target="/kanban",
            attribute="default_group_by",
            value=original,
        )
        self.assertFalse(group_by.exists())

        # Removing a field the project added drops its change.
        self.op(
            self.project, self.kanban, type="remove", target="//field[@name='phone']"
        )
        self.assertNotIn(
            "phone", self.card_fields(self.draft(self.project, self.kanban))
        )
        self.assertNotIn(
            "add_existing_field", self.project.change_ids.mapped("change_type")
        )

    def test_refused_operations(self):
        refused = [
            # Between the t-if and the t-else of the image.
            {
                "type": "add_existing_field",
                "target": f"{CARD}/aside[1]/t[2]",
                "position": "before",
                "field_name": "phone",
            },
            # Outside the card.
            {
                "type": "add_existing_field",
                "target": "/kanban",
                "position": "inside",
                "field_name": "phone",
            },
            # Already in the card.
            {
                "type": "add_existing_field",
                "target": "//field[@name='email']",
                "position": "after",
                "field_name": "city",
            },
            {
                "type": "move",
                "source": f"{CARD}/aside[1]/t[1]",
                "target": "//field[@name='email']",
                "position": "after",
            },
            # A field the card reads (« record.active »): never hidden.
            {"type": "hide", "target": "//field[@name='active']", "value": True},
            {
                "type": "set_attribute",
                "target": "/kanban",
                "attribute": "default_group_by",
                "value": "avatar_128",
            },
            {
                "type": "set_attribute",
                "target": "/kanban",
                "attribute": "t-att-class",
                "value": "1",
            },
            {
                "type": "add_widget",
                "target": "//field[@name='email']",
                "position": "after",
                "widget": "script",
            },
            {"type": "relabel", "target": "//field[@name='email']", "value": "Mail"},
            {"type": "add_filter", "target": "/kanban", "position": "inside"},
        ]
        for operation in refused:
            with self.subTest(operation=operation), self.assertRaises(UserError):
                self.op(self.project, self.kanban, **operation)
        self.assertFalse(self.project.change_ids)

    def test_preview_isolation(self):
        editor, other = self.make_users()
        self.project.user_id = editor
        self.op(
            self.project,
            self.kanban,
            type="add_existing_field",
            target="//field[@name='email']",
            position="after",
            field_name="phone",
        )
        self.op(
            self.project,
            self.kanban,
            type="add_field",
            target="//field[@name='phone']",
            position="after",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        key = self.preview_key(self.project)
        draft = self.view_arch(self.kanban, editor, key)
        self.assertIn("phone", self.card_fields(draft))
        # A field not created yet stays out of the card.
        self.assertNotIn("x_nickname", self.card_fields(draft))
        self.assertNotIn(
            "phone", self.card_fields(self.view_arch(self.kanban, other, key))
        )
        self.assertNotIn("phone", self.card_fields(self.view_arch(self.kanban, editor)))
        self.assertIn(
            "phone", self.card_fields(self.view_arch(self.kanban, editor, key))
        )

    def test_apply_discard_revert_undo(self):
        self.op(
            self.project,
            self.kanban,
            type="add_existing_field",
            target="//field[@name='email']",
            position="after",
            field_name="phone",
        )
        self.op(
            self.project,
            self.kanban,
            type="set_attribute",
            target="/kanban",
            attribute="default_group_by",
            value="country_id",
        )
        studio = self.check_apply_is_idempotent(self.project, self.kanban)
        arch = self.view_arch(self.kanban)
        self.assertIn("phone", self.card_fields(arch))
        self.assertEqual(arch.get("default_group_by"), "country_id")
        self.env["res.partner"].get_views([[self.kanban.id, "kanban"]])

        self.op(
            self.project,
            self.kanban,
            type="hide",
            target="//field[@name='city']",
            value=True,
        )
        self.project.action_undo(self.kanban)
        self.assertEqual(self.project.state, "applied")
        self.op(
            self.project,
            self.kanban,
            type="hide",
            target="//field[@name='city']",
            value=True,
        )
        self.assertEqual(self.project.state, "draft")
        self.project.action_discard()
        self.assertEqual(len(self.project.change_ids), 2)
        self.assertEqual(self.project.state, "applied")
        self.project.action_revert()
        self.assertFalse(studio.exists())
        self.assertNotIn("phone", self.card_fields(self.view_arch(self.kanban)))
        self.assertEqual(self.project.state, "draft")


CHAIN_KANBAN = """
<kanban>
    <field name="is_company"/>
    <templates>
        <t t-name="card">
            <span t-if="record.is_company.raw_value">Company</span>
            <span t-else="">Person</span>
            <span><t t-esc="record.name.value"/></span>
            <field name="email"/>
        </t>
    </templates>
</kanban>
"""


@tagged("post_install", "-at_install")
class TestKanbanTemplateRules(StudioCase):
    """What a kanban template refuses, on a card made for the test."""

    def setUp(self):
        super().setUp()
        self.kanban = self.make_view("kanban", CHAIN_KANBAN)
        self.project = self.make_project("studio_test_kanban_rules")

    def test_head_of_a_chain_is_neither_hidden_nor_removed(self):
        for otype in ("hide", "remove"):
            with self.subTest(otype=otype), self.assertRaises(UserError):
                self.op(
                    self.project,
                    self.kanban,
                    type=otype,
                    target=f"{CARD}/span[1]",
                    value=True,
                )
        self.assertFalse(self.project.change_ids)
        # The end of the chain hides: the chain still compiles.
        self.op(
            self.project, self.kanban, type="hide", target=f"{CARD}/span[2]", value=True
        )
        self.assertEqual(self.project.change_ids.mapped("change_type"), ["hide"])

    def test_no_drop_into_a_content_directive(self):
        with self.assertRaises(UserError) as caught:
            self.op(
                self.project,
                self.kanban,
                type="add_existing_field",
                target=f"{CARD}/span[3]/t[1]",
                position="inside",
                field_name="phone",
            )
        self.assertIn("replaces its content", str(caught.exception))
        self.assertFalse(self.project.change_ids)

    def test_remove_a_ribbon_of_the_project(self):
        self.op(
            self.project,
            self.kanban,
            type="add_widget",
            target="//field[@name='email']",
            position="after",
            widget="web_ribbon",
            attrs={"title": "VIP", "bg_color": "text-bg-success"},
        )
        arch = self.draft(self.project, self.kanban)
        self.assertEqual(len(arch.xpath(f"{CARD}/widget")), 1)
        self.op(
            self.project,
            self.kanban,
            type="move",
            source="//widget[@name='web_ribbon']",
            target=f"{CARD}/span[1]",
            position="before",
        )
        self.op(
            self.project,
            self.kanban,
            type="remove",
            target="//widget[@name='web_ribbon']",
        )
        self.assertFalse(self.project.change_ids)
        self.assertFalse(self.draft(self.project, self.kanban).xpath("//widget"))
