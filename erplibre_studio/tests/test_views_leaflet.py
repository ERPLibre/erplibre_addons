# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StudioCase

MODULE = "studio_test_leaflet"


@tagged("post_install", "-at_install")
class TestLeafletDetection(StudioCase):
    def test_leaflet_only_with_web_view_leaflet_map(self):
        installed = bool(
            self.env["ir.module.module"].search(
                [
                    ("name", "=", "web_view_leaflet_map"),
                    ("state", "=", "installed"),
                ]
            )
        )
        types = self.Project._view_types()
        self.assertEqual("leaflet_map" in types, installed)
        self.assertEqual(types[:5], ("form", "list", "kanban", "search", "pivot"))
        data = self.Editor.get_editor_data("res.partner", False, "list")
        entry = next(e for e in data["view_list"] if e["type"] == "leaflet_map")
        if installed:
            self.assertNotEqual(entry["reason_code"], "needs_module")
            return
        self.assertEqual(entry["reason_code"], "needs_module")
        self.assertIn("web_view_leaflet_map", entry["reason"])
        with self.assertRaises(UserError):
            self.Editor.get_editor_data("res.partner", False, "leaflet_map")
        project = self.make_project("studio_test_leaflet_missing")
        with self.assertRaisesRegex(UserError, "web_view_leaflet_map"):
            project._studio_add_view("res.partner", "leaflet_map")


@tagged("post_install", "-at_install")
class TestLeafletStudio(StudioCase):
    """A map added to the contacts, when web_view_leaflet_map is installed:
    base_geolocalize, which it depends on, gives the contacts their
    coordinates and the date_localization the map reads."""

    def setUp(self):
        super().setUp()
        if "leaflet_map" not in self.Project._view_types():
            self.skipTest("web_view_leaflet_map is not installed")
        self.View = self.env["ir.ui.view"]
        if self.View.default_view("res.partner", "leaflet_map"):
            self.skipTest("res.partner has a leaflet_map view in this database")
        self.project = self.make_project(MODULE)

    def add_map(self):
        data = self.Editor.add_view(self.project.id, "res.partner", "leaflet_map")
        return self.project.view_line_ids, data

    def resolve(self):
        return self.Editor._resolve_view(
            "res.partner", False, "leaflet_map", self.project
        )

    def set_attribute(self, attribute, value):
        return self.op(
            self.project,
            self.resolve(),
            type="set_attribute",
            target="/leaflet_map",
            attribute=attribute,
            value=value,
        )

    def add_lane_field(self, attribute, ttype, label):
        return self.op(
            self.project,
            self.resolve(),
            type="add_field",
            target="/leaflet_map",
            position="inside",
            attribute=attribute,
            field={"ttype": ttype, "field_description": label},
        )

    def test_add_view(self):
        line, data = self.add_map()
        root = etree.fromstring(line.arch)
        title = self.env["res.partner"]._rec_name_fallback()
        self.assertEqual(root.tag, "leaflet_map")
        self.assertEqual(root.get("field_latitude"), "partner_latitude")
        self.assertEqual(root.get("field_longitude"), "partner_longitude")
        self.assertEqual(root.get("field_title"), title)
        self.assertIsNone(root.get("field_address"))
        self.assertFalse(len(root))
        self.assertEqual(data["view_type"], "leaflet_map")
        layout = data["layout"]
        self.assertEqual(layout["root"], "/leaflet_map")
        self.assertEqual(layout["lanes"]["field_latitude"], "partner_latitude")
        self.assertFalse(layout["lanes"]["field_address"])
        self.assertEqual(layout["new_field_types"]["field_latitude"], ["float"])
        self.assertEqual(layout["new_field_types"]["field_title"], ["char"])
        self.assertEqual(layout["new_field_types"]["field_marker_icon_image"], [])
        settable = data["settable"]["leaflet_map"]
        self.assertEqual(settable["field_latitude"], "coordinate_field")
        self.assertEqual(settable["marker_icon_size_x"], "pixels")
        # The renderer reads the zoom attributes without their value.
        self.assertNotIn("default_zoom", settable)
        self.assertEqual(
            data["required_attributes"],
            {"leaflet_map": ["field_latitude", "field_longitude"]},
        )
        choices = data["choices"]
        coordinates = [name for name, _l in choices["coordinate_field"]]
        self.assertIn("partner_latitude", coordinates)
        self.assertNotIn("name", coordinates)
        texts = [name for name, _l in choices["text_field"]]
        self.assertIn("email", texts)
        self.assertNotIn("parent_id", texts)
        self.assertIn("image_128", [name for name, _l in choices["image_field"]])
        palette = {f["name"] for f in data["palette"]}
        self.assertIn("email", palette)
        self.assertNotIn("parent_id", palette)
        self.assertIn("add_field", data["operations"])

    def test_set_attribute(self):
        self.add_map()
        self.set_attribute("field_title", "email")
        self.set_attribute("field_marker_icon_image", "image_128")
        for attribute, value in (
            ("field_latitude", "name"),
            ("field_title", "parent_id"),
            ("field_marker_icon_image", "email"),
            ("marker_icon_size_x", "abc"),
            ("marker_icon_size_x", "600"),
            ("marker_popup_anchor_y", "-513"),
            # The map needs its coordinates.
            ("field_latitude", ""),
            ("default_zoom", "5"),
        ):
            with self.subTest(attribute=attribute, value=value):
                with self.assertRaises(UserError):
                    self.set_attribute(attribute, value)
        self.set_attribute("marker_icon_size_x", " 64 ")
        self.set_attribute("marker_popup_anchor_y", "-40")
        arch = self.draft(self.project, self.resolve())
        self.assertEqual(arch.get("field_title"), "email")
        self.assertEqual(arch.get("field_marker_icon_image"), "image_128")
        self.assertEqual(arch.get("marker_icon_size_x"), "64")
        self.assertEqual(arch.get("marker_popup_anchor_y"), "-40")

    def test_new_field_of_a_lane(self):
        self.add_map()
        before = len(self.project.change_ids)
        change = self.add_lane_field("field_latitude", "float", "Latitude")
        self.assertEqual(len(self.project.change_ids), before + 1)
        name = change.field_name
        self.assertTrue(name.startswith("x_"))
        arch = self.draft(self.project, self.resolve())
        self.assertEqual(arch.get("field_latitude"), name)
        self.assertEqual(arch.xpath("/leaflet_map/field/@name"), [name])
        # The preview leaves the field out while it is not created.
        context = self.preview_key(self.project)
        preview = etree.fromstring(
            self.env["res.partner"]
            .with_context(**context)
            .get_view(False, "leaflet_map")["arch"]
        )
        self.assertIsNone(preview.get("field_latitude"))
        self.assertEqual(preview.get("field_longitude"), "partner_longitude")
        self.assertFalse(preview.xpath("//field"))
        for attribute, ttype in (
            ("field_latitude", "char"),
            ("field_marker_icon_image", "binary"),
            (None, "float"),
        ):
            with self.subTest(attribute=attribute, ttype=ttype):
                with self.assertRaises(UserError):
                    self.add_lane_field(attribute, ttype, "Studio test")
        with self.assertRaises(UserError):
            # Outside a lane, a map ignores the field.
            self.op(
                self.project,
                self.resolve(),
                type="add_field",
                target="/leaflet_map",
                position="inside",
                field={"ttype": "float", "field_description": "Studio test"},
            )
        # Undo takes the field and the attribute back at once.
        self.project.action_undo()
        arch = self.draft(self.project, self.resolve())
        self.assertEqual(arch.get("field_latitude"), "partner_latitude")
        self.assertFalse(arch.xpath("//field"))

    def test_model_without_date_localization(self):
        with self.assertRaisesRegex(UserError, "date_localization"):
            self.Editor.add_view(self.project.id, "res.country", "leaflet_map")
        data = self.Editor.get_editor_data(
            "res.country", False, "list", self.project.id
        )
        entry = next(e for e in data["view_list"] if e["type"] == "leaflet_map")
        self.assertEqual(entry["reason_code"], "needs_field")
        self.assertIn("date_localization", entry["reason"])

    def test_review_blocks_without_coordinates(self):
        """A map whose model has no coordinate field starts without them,
        and Apply waits for both."""
        title = self.env["res.partner"]._rec_name_fallback()
        with patch.object(
            type(self.Project),
            "_studio_leaflet_fields",
            lambda self_, model: {"field_title": title},
        ):
            line, _data = self.add_map()
        self.assertIsNone(etree.fromstring(line.arch).get("field_latitude"))
        review = self.Editor.get_review(self.project.id)
        self.assertIn("latitude and a longitude", review["blocked"])
        with self.assertRaises(UserError):
            self.project.action_apply()
        self.add_lane_field("field_latitude", "float", "Latitude")
        self.assertTrue(self.Editor.get_review(self.project.id)["blocked"])
        self.set_attribute("field_longitude", "partner_longitude")
        self.assertFalse(self.Editor.get_review(self.project.id)["blocked"])

    def test_apply_and_revert(self):
        line, _data = self.add_map()
        self.set_attribute("field_title", "email")
        change = self.add_lane_field("field_address", "char", "Address")
        self.project.action_apply()
        view = line.view_id
        self.assertEqual((view.mode, view.type), ("primary", "leaflet_map"))
        self.assertEqual(self.View.default_view("res.partner", "leaflet_map"), view.id)
        arch = etree.fromstring(
            self.env["res.partner"].get_view(view.id, "leaflet_map")["arch"]
        )
        self.assertEqual(arch.get("field_title"), "email")
        self.assertEqual(arch.get("field_address"), change.field_name)
        self.assertIn(change.field_name, self.env["res.partner"]._fields)
        self.project.action_revert()
        self.assertFalse(view.exists())
        self.assertFalse(self.View.default_view("res.partner", "leaflet_map"))
