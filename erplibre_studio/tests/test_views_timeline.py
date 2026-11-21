# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .. import arch as studio_arch
from .common import TIMELINE_ARCH, StudioCase

ITEM = "//t[@t-name='timeline-item']"


@tagged("post_install", "-at_install")
class TestTimelineDetection(StudioCase):
    def test_timeline_only_with_web_timeline(self):
        installed = bool(
            self.env["ir.module.module"].search(
                [("name", "=", "web_timeline"), ("state", "=", "installed")]
            )
        )
        types = self.Project._view_types()
        self.assertEqual("timeline" in types, installed)
        self.assertEqual(types[:5], ("form", "list", "kanban", "search", "pivot"))
        data = self.Editor.get_editor_data("res.partner", False, "list")
        self.assertEqual(data["view_types"], list(types))
        if not installed:
            with self.assertRaises(UserError):
                self.Editor.get_editor_data("res.partner", False, "timeline")


@tagged("post_install", "-at_install")
class TestTimelineStudio(StudioCase):
    """The studio on a timeline view, when web_timeline is installed."""

    def setUp(self):
        super().setUp()
        if not self.timeline_available():
            self.skipTest("web_timeline is not installed")
        self.timeline = self.make_view("timeline", TIMELINE_ARCH)
        self.project = self.make_project("studio_test_timeline")

    def item_fields(self, arch):
        item = arch.xpath(ITEM)[0]
        return [
            name
            for node in item.iter()
            for name in [studio_arch.shown_field_name("timeline", node)]
            if name
        ]

    def test_editor_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.timeline.id, "timeline", self.project.id
        )
        self.assertEqual(data["view_type"], "timeline")
        self.assertEqual(data["layout"]["template"], ITEM)
        self.assertEqual(data["layout"]["loaded_fields"], ["name"])
        self.assertEqual(data["layout"]["colors"], [])
        self.assertEqual(
            data["required_attributes"],
            {"timeline": ["date_start", "default_group_by"]},
        )
        self.assertEqual(data["settable"]["timeline"]["date_stop"], "date_field")
        self.assertIn(["create_date", "Created on"], data["choices"]["date_field"])
        self.assertNotIn("name", dict(data["choices"]["date_field"]))
        self.assertEqual(data["blocks"]["attrs"]["date_start"], "create_date")
        self.assertTrue(data["blocks"]["drop"])

    def test_changes_and_their_xpath(self):
        self.op(
            self.project,
            self.timeline,
            type="add_existing_field",
            target=f"{ITEM}/div[1]",
            position="inside",
            field_name="email",
        )
        self.op(
            self.project,
            self.timeline,
            type="add_existing_field",
            target="/timeline",
            position="inside",
            field_name="is_company",
        )
        self.op(
            self.project,
            self.timeline,
            type="set_attribute",
            target="/timeline",
            attribute="date_stop",
            value="",
        )
        self.op(
            self.project,
            self.timeline,
            type="set_attribute",
            target="/timeline",
            attribute="default_group_by",
            value="country_id",
        )
        self.op(
            self.project,
            self.timeline,
            type="set_attribute",
            target="/timeline",
            attribute="colors",
            value=[
                {
                    "color": "#ec7063",
                    "field": "is_company",
                    "operator": "==",
                    "value": True,
                }
            ],
        )
        self.op(
            self.project,
            self.timeline,
            type="set_attribute",
            target="/timeline",
            attribute="mode",
            value="week",
        )
        self.op(
            self.project,
            self.timeline,
            type="hide",
            target=f"{ITEM}/div[1]/span[1]",
            value=True,
        )
        self.assertEqual(
            [(c.change_type, c.xpath) for c in self.project.change_ids],
            [
                ("add_existing_field", f"{ITEM}/div[1]"),
                ("add_existing_field", "/timeline"),
                ("set_attribute", "/timeline"),
                ("set_attribute", "/timeline"),
                ("set_attribute", "/timeline"),
                ("set_attribute", "/timeline"),
                ("hide", f"{ITEM}/div[1]/span[1]"),
            ],
        )
        arch = self.draft(self.project, self.timeline)
        self.assertEqual(self.item_fields(arch), ["name", "email"])
        self.assertEqual(arch.xpath(f"{ITEM}/div/span")[0].get("invisible"), "True")
        self.assertIn("is_company", [n.get("name") for n in arch.iterchildren("field")])
        self.assertIsNone(arch.get("date_stop"))
        self.assertEqual(
            (arch.get("default_group_by"), arch.get("colors"), arch.get("mode")),
            ("country_id", "#ec7063:is_company == True", "week"),
        )
        colors = self.project.change_ids.filtered(
            lambda c: c._payload().get("attribute") == "colors"
        )
        self.assertEqual(colors._payload()["fields"], ["is_company"])

    def add_to_item(self, name, target=f"{ITEM}/div[1]", position="inside"):
        return self.op(
            self.project,
            self.timeline,
            type="add_existing_field",
            target=target,
            position=position,
            field_name=name,
        )

    def test_item_fields_show_the_search_read_values(self):
        """A field dropped into the item shows ``record.<name>`` and is
        loaded by the view; a field the view loads already is not loaded
        twice."""
        self.add_to_item("email")
        self.add_to_item("user_id")
        self.op(
            self.project,
            self.timeline,
            type="add_existing_field",
            target="/timeline",
            position="inside",
            field_name="is_company",
        )
        self.add_to_item("is_company")
        arch = self.draft(self.project, self.timeline)
        self.assertFalse(arch.xpath(f"{ITEM}//field"))
        values = [
            (n.get("name"), n.get("t-esc")) for n in arch.xpath(f"{ITEM}/div/span")
        ]
        self.assertEqual(
            values,
            [
                (None, "record.name"),
                ("email", "record.email or ''"),
                ("user_id", "record.user_id and record.user_id[1] or ''"),
                ("is_company", "record.is_company"),
            ],
        )
        loaded = [n.get("name") for n in arch.iterchildren("field")]
        self.assertEqual(sorted(loaded), ["email", "is_company", "name", "user_id"])
        self.assertEqual(
            self.item_fields(arch), ["name", "email", "user_id", "is_company"]
        )
        data = self.Editor.get_editor_data(
            "res.partner", self.timeline.id, "timeline", self.project.id
        )
        palette = {f["name"] for f in data["palette"]}
        self.assertNotIn("email", palette)
        self.assertIn("phone", palette)
        # The fields of the item are blocks the editor moves and hides.
        templates = next(
            b for b in data["blocks"]["children"] if b["tag"] == "templates"
        )
        item_block = templates["children"][0]
        names = [b.get("name") for b in item_block["children"][0]["children"]]
        self.assertEqual(names, ["name", "email", "user_id", "is_company"])
        with self.assertRaises(UserError):
            self.add_to_item("email")
        with self.assertRaises(UserError):
            # A one2many has no value an item shows.
            self.add_to_item("child_ids")
        self.op(
            self.project,
            self.timeline,
            type="hide",
            target="//span[@name='email']",
            value=True,
        )
        self.assertEqual(
            self.draft(self.project, self.timeline)
            .xpath("//span[@name='email']")[0]
            .get("invisible"),
            "True",
        )
        with self.assertRaises(UserError):
            # An item field stays in the item.
            self.op(
                self.project,
                self.timeline,
                type="move",
                source="//span[@name='user_id']",
                target="/timeline",
                position="inside",
            )

    def test_remove_an_item_field_of_the_project(self):
        self.add_to_item("email")
        self.op(
            self.project,
            self.timeline,
            type="move",
            source="//span[@name='email']",
            target=f"{ITEM}/div[1]/span[1]",
            position="before",
        )
        self.op(
            self.project,
            self.timeline,
            type="remove",
            target="//span[@name='email']",
        )
        self.assertFalse(self.project.change_ids)
        arch = self.draft(self.project, self.timeline)
        self.assertEqual(self.item_fields(arch), ["name"])
        self.assertEqual([n.get("name") for n in arch.iterchildren("field")], ["name"])
        # A native item field is hidden.
        self.op(
            self.project,
            self.timeline,
            type="remove",
            target=f"{ITEM}/div[1]/span[1]",
        )
        self.assertEqual(self.project.change_ids.mapped("change_type"), ["hide"])

    def test_group_by_a_relation_only(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.timeline.id, "timeline", self.project.id
        )
        self.assertEqual(
            data["settable"]["timeline"]["default_group_by"], "relation_group_field"
        )
        choices = dict(data["choices"]["relation_group_field"])
        self.assertIn("country_id", choices)
        self.assertIn("user_id", choices)
        self.assertNotIn("type", choices)
        self.assertNotIn("active", choices)
        for value in ("type", "active", "name"):
            with self.subTest(value=value), self.assertRaises(UserError):
                self.op(
                    self.project,
                    self.timeline,
                    type="set_attribute",
                    target="/timeline",
                    attribute="default_group_by",
                    value=value,
                )
        for value in ("country_id", "category_id"):
            self.op(
                self.project,
                self.timeline,
                type="set_attribute",
                target="/timeline",
                attribute="default_group_by",
                value=value,
            )
            arch = self.draft(self.project, self.timeline)
            self.assertEqual(arch.get("default_group_by"), value)

    def test_color_rules_web_timeline_evaluates(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.timeline.id, "timeline", self.project.id
        )
        self.assertNotIn("many2one", data["layout"]["color_types"])
        self.assertNotIn("datetime", data["layout"]["color_types"])
        refused = [
            # [id, name] in search_read: never equal to an id.
            {"color": "red", "field": "user_id", "operator": "==", "value": 2},
            # « : » in the value ends the rule.
            {
                "color": "red",
                "field": "create_date",
                "operator": ">=",
                "value": "2026-01-01 08:00:00",
            },
            {"color": "red", "field": "ref", "operator": "==", "value": "Ref: A"},
            {"color": "red", "field": "ref", "operator": "==", "value": "a;b"},
        ]
        for rule in refused:
            with self.subTest(rule=rule), self.assertRaises(UserError):
                self.op(
                    self.project,
                    self.timeline,
                    type="set_attribute",
                    target="/timeline",
                    attribute="colors",
                    value=[rule],
                )
        self.assertFalse(self.project.change_ids)
        self.op(
            self.project,
            self.timeline,
            type="set_attribute",
            target="/timeline",
            attribute="colors",
            value=[
                {"color": "red", "field": "ref", "operator": "==", "value": "A-1"},
                {"color": "#00ff00", "field": "color", "operator": ">", "value": "3"},
            ],
        )
        arch = self.draft(self.project, self.timeline)
        self.assertEqual(arch.get("colors"), "red:ref == 'A-1';#00ff00:color > 3")

    def test_refused_operations(self):
        refused = [
            {
                "type": "set_attribute",
                "target": "/timeline",
                "attribute": "date_start",
                "value": "",
            },
            {
                "type": "set_attribute",
                "target": "/timeline",
                "attribute": "date_start",
                "value": "name",
            },
            {
                "type": "set_attribute",
                "target": "/timeline",
                "attribute": "mode",
                "value": "year",
            },
            {
                "type": "set_attribute",
                "target": "/timeline",
                "attribute": "colors",
                "value": [{"color": "red;", "field": "is_company", "value": 1}],
            },
            {
                "type": "set_attribute",
                "target": "/timeline",
                "attribute": "colors",
                "value": "red:1",
            },
            {
                "type": "add_existing_field",
                "target": "/timeline",
                "position": "inside",
                "field_name": "name",
            },
            {"type": "hide", "target": "//field[@name='name']", "value": True},
            {"type": "add_field", "target": "/timeline", "position": "inside"},
        ]
        for operation in refused:
            with self.subTest(operation=operation), self.assertRaises(UserError):
                self.op(self.project, self.timeline, **operation)
        self.assertFalse(self.project.change_ids)

    def test_preview_isolation(self):
        editor, other = self.make_users()
        self.project.user_id = editor
        self.op(
            self.project,
            self.timeline,
            type="set_attribute",
            target="/timeline",
            attribute="mode",
            value="week",
        )
        key = self.preview_key(self.project)
        self.assertEqual(self.view_arch(self.timeline, editor, key).get("mode"), "week")
        self.assertIsNone(self.view_arch(self.timeline, other, key).get("mode"))
        self.assertIsNone(self.view_arch(self.timeline, editor).get("mode"))

    def test_apply_discard_revert_undo(self):
        self.op(
            self.project,
            self.timeline,
            type="add_existing_field",
            target=f"{ITEM}/div[1]",
            position="inside",
            field_name="email",
        )
        self.op(
            self.project,
            self.timeline,
            type="set_attribute",
            target="/timeline",
            attribute="default_group_by",
            value="country_id",
        )
        studio = self.check_apply_is_idempotent(self.project, self.timeline)
        arch = self.view_arch(self.timeline)
        self.assertEqual(self.item_fields(arch), ["name", "email"])
        self.assertEqual(arch.get("default_group_by"), "country_id")
        self.project.action_undo(self.timeline)
        self.assertEqual(self.project.state, "draft")
        self.project.action_discard()
        self.assertEqual(self.project.state, "applied")
        self.project.action_revert()
        self.assertFalse(studio.exists())
        self.assertEqual(
            self.view_arch(self.timeline).get("default_group_by"), "user_id"
        )

    def test_view_of_web_timeline(self):
        """The timeline web_timeline puts on the scheduled actions, when its
        demo data is loaded."""
        cron = self.env.ref("web_timeline.ir_cron_timeline", raise_if_not_found=False)
        if not cron:
            self.skipTest("web_timeline demo data is not loaded")
        data = self.Editor.get_editor_data(
            "ir.cron", cron.id, "timeline", self.project.id
        )
        self.assertFalse(data["layout"]["template"])
        self.op(
            self.project,
            cron,
            type="set_attribute",
            target="/timeline",
            attribute="default_group_by",
            value="user_id",
        )
        self.project.action_apply()
        self.assertEqual(
            self.view_arch(cron, model="ir.cron").get("default_group_by"), "user_id"
        )
