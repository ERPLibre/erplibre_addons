# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CALENDAR_ARCH, StudioCase


@tagged("post_install", "-at_install")
class TestCalendarStudio(StudioCase):
    """The studio on a calendar view of the contacts, made by the test."""

    def setUp(self):
        super().setUp()
        self.calendar = self.make_view("calendar", CALENDAR_ARCH)
        self.project = self.make_project("studio_test_calendar")

    def set_attribute(self, target, attribute, value, view=None):
        return self.op(
            self.project,
            view or self.calendar,
            type="set_attribute",
            target=target,
            attribute=attribute,
            value=value,
        )

    def test_editor_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.calendar.id, "calendar", self.project.id
        )
        self.assertIn("calendar", data["view_types"])
        entry = next(e for e in data["view_list"] if e["type"] == "calendar")
        self.assertTrue(entry["editable"])
        self.assertEqual(data["hide_mode"], "invisible")
        self.assertEqual(
            data["layout"],
            {
                "root": "/calendar",
                "popover": ["//field[@name='name']", "//field[@name='email']"],
                "loaded_by_attributes": ["create_date", "user_id"],
            },
        )
        self.assertTrue(data["blocks"]["drop"])
        settable = data["settable"]
        self.assertEqual(settable["calendar"]["date_start"], "date_field")
        self.assertEqual(settable["calendar"]["color"], "color_field")
        self.assertEqual(settable["calendar"]["all_day"], "bool_field")
        self.assertEqual(settable["calendar"]["mode"], "calendar_mode")
        self.assertEqual(settable["field"], {"filters": "calendar_filter"})
        self.assertEqual(data["required_attributes"]["calendar"], ["date_start"])
        choices = data["choices"]
        colors = [name for name, _label in choices["color_field"]]
        self.assertIn("user_id", colors)
        self.assertIn("type", colors)
        self.assertNotIn("comment", colors)
        self.assertNotIn("create_date", colors)
        booleans = [name for name, _label in choices["bool_field"]]
        self.assertIn("active", booleans)
        self.assertNotIn("name", booleans)
        self.assertEqual(
            choices["calendar_mode"],
            [["day", "day"], ["week", "week"], ["month", "month"], ["year", "year"]],
        )
        self.assertEqual(choices["calendar_filter"], [["True", "True"]])
        palette = {f["name"]: f["type"] for f in data["palette"]}
        self.assertIn("phone", palette)
        self.assertNotIn("email", palette)
        self.assertNotIn("child_ids", palette)
        self.assertNotIn("image_1920", palette)
        self.assertIn("set_attribute", data["operations"])
        self.assertNotIn("add_field", data["operations"])

    def test_changes(self):
        self.op(
            self.project,
            self.calendar,
            type="add_existing_field",
            target="/calendar",
            position="inside",
            field_name="phone",
        )
        self.op(
            self.project,
            self.calendar,
            type="move",
            source="//field[@name='email']",
            target="//field[@name='name']",
            position="before",
        )
        self.op(
            self.project,
            self.calendar,
            type="hide",
            target="//field[@name='email']",
            value=True,
        )
        self.op(
            self.project,
            self.calendar,
            type="relabel",
            target="//field[@name='name']",
            value="Contact",
        )
        for attribute, value in (
            ("date_stop", "write_date"),
            ("color", ""),
            ("mode", "month"),
            ("quick_create", False),
        ):
            self.set_attribute("/calendar", attribute, value)
        arch = self.draft(self.project, self.calendar)
        self.assertEqual(
            [(f.get("name"), f.get("invisible"), f.get("string")) for f in arch],
            [
                ("email", "True", None),
                ("name", None, "Contact"),
                ("phone", None, None),
            ],
        )
        self.assertEqual(
            (
                arch.get("date_start"),
                arch.get("date_stop"),
                arch.get("color"),
                arch.get("mode"),
                arch.get("quick_create"),
            ),
            ("create_date", "write_date", None, "month", "False"),
        )
        stop = self.project.change_ids.filtered(
            lambda c: c._payload().get("attribute") == "date_stop"
        )
        self.assertEqual(stop._payload()["fields"], ["write_date"])

    def test_filters(self):
        """« filters » on a many2one makes it a side panel filter; False
        removes the attribute, which the calendar tests by its presence."""
        self.op(
            self.project,
            self.calendar,
            type="add_existing_field",
            target="/calendar",
            position="inside",
            field_name="user_id",
        )
        target = "//field[@name='user_id']"
        self.set_attribute(target, "filters", True)
        node = self.draft(self.project, self.calendar).xpath(target)[0]
        self.assertEqual(node.get("filters"), "True")
        self.set_attribute(target, "filters", False)
        node = self.draft(self.project, self.calendar).xpath(target)[0]
        self.assertNotIn("filters", node.attrib)
        filtered = self.make_view(
            "calendar",
            '<calendar date_start="create_date">'
            '<field name="user_id" filters="1"/></calendar>',
        )
        # « 1 » is a filter already: True leaves no change.
        self.assertFalse(self.set_attribute(target, "filters", True, filtered))
        self.set_attribute(target, "filters", "False", filtered)
        node = self.draft(self.project, filtered).xpath(target)[0]
        self.assertNotIn("filters", node.attrib)

    def test_refused_operations(self):
        refused = [
            # The calendar needs its start date.
            ("/calendar", "date_start", ""),
            ("/calendar", "date_start", "name"),
            # A number of hours, not a date.
            ("/calendar", "date_delay", "write_date"),
            ("/calendar", "mode", "fit"),
            ("/calendar", "color", "comment"),
            ("/calendar", "all_day", "name"),
            ("/calendar", "scales", "month"),
            ("//field[@name='email']", "filters", True),
        ]
        for target, attribute, value in refused:
            with (
                self.subTest(attribute=attribute, value=value),
                self.assertRaises(UserError),
            ):
                self.set_attribute(target, attribute, value)
        with self.assertRaises(UserError):
            self.op(
                self.project,
                self.calendar,
                type="add_field",
                target="/calendar",
                position="inside",
            )
        with self.assertRaises(UserError):
            # Already in the popover.
            self.op(
                self.project,
                self.calendar,
                type="add_existing_field",
                target="/calendar",
                position="inside",
                field_name="email",
            )
        self.assertFalse(self.project.change_ids)

    def test_same_value_leaves_no_change(self):
        for attribute, value in (("mode", "week"), ("color", "user_id")):
            self.assertFalse(self.set_attribute("/calendar", attribute, value))
        self.assertFalse(self.project.change_ids)

    def test_apply_revert_undo(self):
        self.set_attribute("/calendar", "mode", "day")
        self.set_attribute("/calendar", "date_stop", "write_date")
        studio = self.check_apply_is_idempotent(self.project, self.calendar)
        arch = self.view_arch(self.calendar)
        self.assertEqual(
            (arch.get("mode"), arch.get("date_stop")), ("day", "write_date")
        )
        self.env["res.partner"].get_views([[self.calendar.id, "calendar"]])
        self.op(
            self.project,
            self.calendar,
            type="hide",
            target="//field[@name='email']",
            value=True,
        )
        node = self.draft(self.project, self.calendar).xpath("//field[@name='email']")
        self.assertEqual(node[0].get("invisible"), "True")
        self.project.action_undo(self.calendar)
        self.assertEqual(self.project.state, "applied")
        self.project.action_revert()
        self.assertFalse(studio.exists())
        arch = self.view_arch(self.calendar)
        self.assertEqual((arch.get("mode"), arch.get("date_stop")), ("week", None))
