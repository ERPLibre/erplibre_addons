# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StudioCase

MODULE = "studio_test_geoengine"
SITE = "x_studio_test_site"
ZONE = "x_studio_test_zone"
INFO_BOX = "//t[@t-name='info_box']"


@tagged("post_install", "-at_install")
class TestGeoengineStudio(StudioCase):
    """A GeoEngine view added to the contacts, when base_geoengine is
    installed: two geo fields made for the test, a view that loads the
    first one, an OpenStreetMap background and a vector layer on it,
    written to base_geoengine by Apply and removed by Revert."""

    def setUp(self):
        super().setUp()
        if "geoengine" not in self.Project._view_types():
            self.skipTest("base_geoengine is not installed")
        self.View = self.env["ir.ui.view"]
        if self.View.search_count(
            [("model", "=", "res.partner"), ("type", "=", "geoengine")]
        ):
            self.skipTest("res.partner has a geoengine view in this database")
        model_id = self.env["ir.model"]._get_id("res.partner")
        self.env["ir.model.fields"].create(
            [
                {
                    "name": SITE,
                    "model_id": model_id,
                    "ttype": "geo_point",
                    "state": "manual",
                    "field_description": "Test site",
                },
                {
                    "name": ZONE,
                    "model_id": model_id,
                    "ttype": "geo_polygon",
                    "state": "manual",
                    "field_description": "Test zone",
                },
            ]
        )
        self.project = self.make_project(MODULE)

    def add_map(self):
        data = self.Editor.add_view(self.project.id, "res.partner", "geoengine")
        return self.project.view_line_ids, data

    def resolve(self):
        return self.Editor._resolve_view(
            "res.partner", False, "geoengine", self.project
        )

    def add_existing(self, name, target, position="inside"):
        return self.op(
            self.project,
            self.resolve(),
            type="add_existing_field",
            target=target,
            position=position,
            field_name=name,
        )

    def layers(self, res_model):
        data = self.module_records(MODULE, res_model)
        return self.env[res_model].browse(data.mapped("res_id"))

    def test_needs_a_geo_field(self):
        model = "res.partner.category"
        data = self.Editor.get_editor_data(model, False, "list", self.project.id)
        entry = next(e for e in data["view_list"] if e["type"] == "geoengine")
        self.assertEqual(entry["reason_code"], "needs_geo_field")
        self.assertIn("needs a geo field", entry["reason"])
        with self.assertRaisesRegex(UserError, "needs a geo field"):
            self.project._studio_add_view(model, "geoengine")
        self.assertFalse(self.project.view_line_ids)

    def test_add_view(self):
        data = self.Editor.get_editor_data(
            "res.partner", False, "list", self.project.id
        )
        entry = next(e for e in data["view_list"] if e["type"] == "geoengine")
        self.assertEqual(entry["reason_code"], "no_view")
        line, data = self.add_map()
        root = etree.fromstring(line.arch)
        name = self.env["res.partner"]._rec_name_fallback()
        self.assertEqual(root.tag, "geoengine")
        loaded = [n.get("name") for n in root.iterchildren("field")]
        self.assertEqual(loaded, ["display_name", name, SITE])
        box = root.find("templates/t[@t-name='info_box']")
        self.assertEqual([n.get("name") for n in box.iter("field")], [name])
        raster, vector = line.layer_ids.sorted("kind")
        self.assertEqual(
            (raster.kind, raster.name, raster.raster_type),
            ("raster", "OpenStreetMap", "osm"),
        )
        self.assertEqual(
            (vector.kind, vector.name, vector.geo_field, vector.geo_repr),
            ("vector", "Test site", SITE, "basic"),
        )
        self.assertTrue(vector.active_on_startup)
        self.assertEqual(raster._studio_xml_name(), "res_partner_geo_raster_10")
        layout = data["layout"]
        self.assertEqual(layout["card"], INFO_BOX)
        self.assertEqual(layout["loaded_fields"], ["display_name", name, SITE])
        self.assertEqual(data["settable"], {"geoengine": {"editable": "bool_number"}})
        self.assertNotIn("add_field", data["operations"])
        layers = data["view"]["added"]["layers"]
        self.assertEqual(
            sorted((item["kind"], item["geo_field"]) for item in layers),
            [("raster", False), ("vector", SITE)],
        )
        palette = {item["name"] for item in data["palette"]}
        self.assertIn(ZONE, palette)
        self.assertNotIn(SITE, palette)
        # One GeoEngine view per model: base_geoengine reads the first.
        with self.assertRaisesRegex(UserError, "already adds"):
            self.project._studio_add_view("res.partner", "geoengine")

    def test_info_box_and_loaded_fields(self):
        self.add_map()
        self.add_existing("email", INFO_BOX)
        with self.assertRaisesRegex(UserError, "not in its info box"):
            self.add_existing(ZONE, INFO_BOX)
        with self.assertRaisesRegex(UserError, "not in its info box"):
            self.add_existing(ZONE, "//field[@name='email']", "after")
        self.add_existing(ZONE, "/geoengine")
        arch = self.draft(self.project, self.resolve())
        self.assertEqual(arch.xpath("/geoengine/field[last()]/@name"), [ZONE])
        self.assertEqual(
            arch.xpath("//t[@t-name='info_box']/field/@name")[-1:], ["email"]
        )

    def test_editable(self):
        self.add_map()
        view = self.resolve()
        self.op(
            self.project,
            view,
            type="set_attribute",
            target="/geoengine",
            attribute="editable",
            value="1",
        )
        self.assertEqual(self.draft(self.project, view).get("editable"), "1")
        # Off is the arch without the attribute: the change leaves.
        self.op(
            self.project,
            view,
            type="set_attribute",
            target="/geoengine",
            attribute="editable",
            value="",
        )
        self.assertIsNone(self.draft(self.project, view).get("editable"))
        self.assertFalse(self.project.change_ids)

    def test_apply_and_revert(self):
        line, _data = self.add_map()
        self.project.action_apply()
        view = self.View.browse(self.View.default_view("res.partner", "geoengine"))
        self.assertEqual(view, line.view_id)
        rasters = self.layers("geoengine.raster.layer")
        vectors = self.layers("geoengine.vector.layer")
        self.assertEqual(len(rasters), 1)
        self.assertEqual(len(vectors), 1)
        self.assertEqual((rasters.view_id, rasters.raster_type), (view, "osm"))
        self.assertEqual(vectors.view_id, view)
        self.assertEqual(vectors.geo_field_id.name, SITE)
        self.assertTrue(vectors.active_on_startup)
        found = self.env["res.partner"].get_geoengine_layers()
        self.assertEqual(len(found["backgrounds"]), 1)
        self.assertEqual(len(found["actives"]), 1)
        self.assertEqual(found["actives"][0]["geo_field_id"][1], SITE)
        # The geo field of the form no longer misses its GeoEngine view.
        data = self.Editor.get_editor_data(
            "res.partner", self.form.id, "form", self.project.id
        )
        self.assertFalse(data["geo_view_missing"])
        # A second Apply writes nothing new.
        self.project.action_apply()
        self.assertEqual(self.layers("geoengine.vector.layer"), vectors)

        self.project.action_revert()
        self.assertFalse(rasters.exists())
        self.assertFalse(vectors.exists())
        self.assertFalse(view.exists())
        self.assertFalse(self.module_records(MODULE))
        # The field the test made stays: the project did not create it.
        self.assertTrue(self.env["ir.model.fields"]._get("res.partner", SITE))
        # Back to a draft with its layers.
        self.assertEqual(len(line.layer_ids), 2)

    def test_apply_removes_the_view_left_out(self):
        line, _data = self.add_map()
        self.project.action_apply()
        view = line.view_id
        rasters = self.layers("geoengine.raster.layer")
        vectors = self.layers("geoengine.vector.layer")
        self.assertEqual((len(rasters), len(vectors)), (1, 1))
        removals = self.project._studio_apply_removals()
        self.assertFalse(removals.get("raster_layers"))
        self.assertFalse(removals.get("vector_layers"))
        self.project._studio_remove_view(line)
        removals = self.project._studio_apply_removals()
        self.assertEqual(len(removals["raster_layers"]), 1)
        self.assertEqual(len(removals["vector_layers"]), 1)
        self.project.action_apply()
        self.assertFalse(rasters.exists())
        self.assertFalse(vectors.exists())
        self.assertFalse(view.exists())

    def test_discard_restores_the_layers(self):
        line, _data = self.add_map()
        self.project.action_apply()
        self.project._studio_remove_view(line)
        self.assertFalse(self.project.view_line_ids)
        self.project.action_discard()
        line = self.project.view_line_ids
        self.assertEqual(line.view_type, "geoengine")
        self.assertEqual(sorted(line.layer_ids.mapped("kind")), ["raster", "vector"])
        self.assertEqual(
            line.layer_ids.filtered(lambda layer: layer.kind == "vector").geo_field,
            SITE,
        )

    def test_remove_view_before_apply(self):
        line, _data = self.add_map()
        layers = line.layer_ids
        self.assertEqual(len(layers), 2)
        self.project._studio_remove_view(line)
        self.assertFalse(line.exists())
        self.assertFalse(layers.exists())
