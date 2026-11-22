# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StudioCase

BOX = "//div[@t-name='activity-box']"


@tagged("post_install", "-at_install")
class TestActivityDetection(StudioCase):
    def test_activity_only_with_mail(self):
        installed = bool(
            self.env["ir.module.module"].search(
                [("name", "=", "mail"), ("state", "=", "installed")]
            )
        )
        self.assertEqual(self.activity_available(), installed)
        data = self.Editor.get_editor_data("res.partner", False, "list")
        entry = next(e for e in data["view_list"] if e["type"] == "activity")
        if installed:
            self.assertNotEqual(entry["reason_code"], "needs_module")
            return
        self.assertEqual(entry["reason_code"], "needs_module")
        self.assertIn("mail", entry["reason"])
        self.assertFalse(self.Project._studio_has_activities("res.partner"))
        project = self.make_project("studio_test_activity_missing")
        with self.assertRaisesRegex(UserError, "mail"):
            project._studio_add_view("res.partner", "activity")


@tagged("post_install", "-at_install")
class TestActivityStudio(StudioCase):
    """The studio on the activity view mail gives the contacts: its
    « activity-box » template is a <div>."""

    def setUp(self):
        super().setUp()
        if not self.activity_available():
            self.skipTest("mail is not installed")
        self.activity = self.env.ref("mail.res_partner_view_activity")
        self.project = self.make_project("studio_test_activity")

    def op_on(self, **operation):
        return self.op(self.project, self.activity, **operation)

    def box_fields(self, arch):
        return [
            (node.get("name"), node.get("invisible"), node.get("display"))
            for node in arch.xpath(BOX)[0].iter("field")
        ]

    def test_editor_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.activity.id, "activity", self.project.id
        )
        self.assertIn("activity", data["view_types"])
        entry = next(e for e in data["view_list"] if e["type"] == "activity")
        self.assertTrue(entry["editable"])
        self.assertEqual(entry["view_id"], self.activity.id)
        layout = data["layout"]
        self.assertEqual(layout["card"], BOX)
        self.assertEqual(layout["templates"], {"activity-box": BOX})
        self.assertIn("id", layout["loaded_fields"])
        self.assertEqual(layout["widgets"], {})
        self.assertEqual(data["hide_mode"], "invisible")
        self.assertNotIn("add_widget", data["operations"])
        self.assertIn("add_field", data["operations"])
        self.assertEqual(
            data["settable"],
            {"field": {"widget": "widget", "display": "activity_display"}},
        )
        self.assertEqual(
            data["choices"]["activity_display"], [["full", "full"], ["right", "right"]]
        )
        templates = next(
            b for b in data["blocks"]["children"] if b["tag"] == "templates"
        )
        box = templates["children"][0]
        self.assertEqual(
            (box["tag"], box["kind"], box["template"], box["path"]),
            ("div", "template", "activity-box", BOX),
        )
        self.assertFalse(data["blocks"]["drop"])
        palette = {f["name"] for f in data["palette"]}
        self.assertIn("phone", palette)
        self.assertNotIn("name", palette)

    def test_changes(self):
        self.op_on(
            type="add_existing_field",
            target=BOX,
            position="inside",
            field_name="phone",
        )
        self.op_on(
            type="move",
            source="//field[@name='phone']",
            target="//field[@name='name']",
            position="after",
        )
        self.op_on(type="hide", target="//field[@name='phone']", value=True)
        self.op_on(
            type="set_attribute",
            target="//field[@name='name']",
            attribute="display",
            value="right",
        )
        self.op_on(
            type="add_field",
            target=BOX,
            position="inside",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        arch = self.draft(self.project, self.activity)
        fields = self.box_fields(arch)
        names = [name for name, _i, _d in fields]
        self.assertEqual(names[names.index("name") + 1], "phone")
        self.assertIn(("name", None, "right"), fields)
        self.assertIn(("phone", "True", None), fields)
        self.assertEqual(fields[-1][0], "x_nickname")
        # The draft compiles as an activity view: get_views reads it.
        self.env["res.partner"].with_context(
            **self.preview_key(self.project)
        ).get_views([[self.activity.id, "activity"]])

    def test_refusals(self):
        with self.assertRaises(UserError):
            # The box itself neither hides nor moves.
            self.op_on(type="hide", target=BOX, value=True)
        with self.assertRaises(UserError):
            self.op_on(
                type="move",
                source=BOX,
                target="//field[@name='id']",
                position="after",
            )
        with self.assertRaises(UserError):
            # Nothing new goes outside the box.
            self.op_on(
                type="add_existing_field",
                target="/activity",
                position="inside",
                field_name="phone",
            )
        with self.assertRaises(UserError):
            self.op_on(
                type="set_attribute",
                target="//field[@name='name']",
                attribute="display",
                value="left",
            )
        with self.assertRaises(UserError):
            # « bold » and « muted » read any text as true: not settable.
            self.op_on(
                type="set_attribute",
                target="//field[@name='name']",
                attribute="bold",
                value="1",
            )
        self.assertFalse(self.project.change_ids)

    def test_apply_and_revert(self):
        self.op_on(
            type="add_existing_field",
            target=BOX,
            position="inside",
            field_name="phone",
        )
        self.op_on(
            type="set_attribute",
            target="//field[@name='name']",
            attribute="display",
            value="right",
        )
        studio = self.check_apply_is_idempotent(self.project, self.activity)
        arch = self.view_arch(self.activity)
        fields = self.box_fields(arch)
        self.assertIn("phone", [name for name, _i, _d in fields])
        self.assertIn(("name", None, "right"), fields)
        self.env["res.partner"].get_views([[self.activity.id, "activity"]])
        self.project.action_revert()
        self.assertFalse(studio.exists())
        fields = self.box_fields(self.view_arch(self.activity))
        self.assertNotIn("phone", [name for name, _i, _d in fields])
        self.assertIn(("name", None, "full"), fields)
