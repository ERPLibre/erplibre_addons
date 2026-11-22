# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import sql

from ..arch import GEO_TYPES
from .common import StudioCase

MODULE = "studio_test_geo"
ITEM_MODEL = "x_studio_test_geo_item"
SQUARE = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"


@tagged("post_install", "-at_install")
class TestGeoFields(StudioCase):
    """Geometry fields of base_geoengine on the contacts, when it is
    installed: a form only, a shape chosen until Apply, a PostGIS column
    with its GiST index once applied."""

    def setUp(self):
        super().setUp()
        if not self.Project._studio_geo_available():
            self.skipTest("base_geoengine is not installed")
        if self.env["ir.ui.view"].search_count(
            [("model", "=", "res.partner"), ("type", "=", "geoengine")]
        ):
            self.skipTest("res.partner has a geoengine view in this database")
        self.project = self.make_project(MODULE)

    def add_geo(self, view=None, ttype="geo_point", label="Area", **drop):
        drop = drop or {"target": "//field[@name='vat']", "position": "after"}
        return self.op(
            self.project,
            view or self.form,
            type="add_field",
            field={"ttype": ttype, "field_description": label},
            **drop,
        )

    def update(self, name, **values):
        return self.op(
            self.project, self.form, type="update_field", field_name=name, field=values
        )

    def geometry_column(self, table, name):
        self.env.cr.execute(
            "SELECT srid, type FROM geometry_columns "
            "WHERE f_table_name = %s AND f_geometry_column = %s",
            (table, name),
        )
        return self.env.cr.fetchone()

    def test_payload_offers_the_geo_types(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.form.id, "form", self.project.id
        )
        for ttype in GEO_TYPES:
            self.assertIn(ttype, data["field_types"])
        self.assertIn("char", data["field_types"])
        self.assertTrue(data["geo_view_missing"])

    def test_form_only(self):
        change = self.add_geo()
        self.assertEqual(change.field_name, "x_area")
        self.assertEqual(change._payload()["field"]["ttype"], "geo_point")
        self.assertNotIn("index", change._payload()["field"])
        with self.assertRaisesRegex(UserError, "in a form only"):
            self.add_geo(
                self.list,
                label="Zone",
                target="//field[@name='email']",
                position="after",
            )
        # No option of FIELD_OPTIONS: the field class makes its GiST index.
        with self.assertRaisesRegex(UserError, "does not take the option"):
            self.update("x_area", index=True)

    def test_shape_until_apply(self):
        self.add_geo()
        change = self.update("x_area", ttype="geo_polygon")
        self.assertEqual(change._payload()["field"]["ttype"], "geo_polygon")
        with self.assertRaisesRegex(UserError, "type of a field cannot change"):
            self.update("x_area", ttype="char")
        self.project.action_apply()
        field = self.env["ir.model.fields"]._get("res.partner", "x_area")
        self.assertEqual((field.ttype, field.state), ("geo_polygon", "manual"))
        self.assertEqual(
            self.geometry_column("res_partner", "x_area"), (3857, "POLYGON")
        )
        self.assertTrue(sql.index_exists(self.env.cr, "res_partner_x_area_gist_index"))
        with self.assertRaisesRegex(UserError, "shape is set before Apply only"):
            self.update("x_area", ttype="geo_point")

        partner = self.env["res.partner"].create({"name": "Geo", "x_area": SQUARE})
        partner.invalidate_recordset()
        shape = json.loads(partner.read(["x_area"])[0]["x_area"])
        self.assertEqual(shape["type"], "Polygon")
        self.assertEqual(shape["coordinates"][0][2], [10.0, 10.0])

        # An applied geo field of the model stays out of a list.
        with self.assertRaisesRegex(UserError, "in a form only"):
            self.op(
                self.project,
                self.list,
                type="add_existing_field",
                target="//field[@name='email']",
                position="after",
                field_name="x_area",
            )

        self.project.action_revert()
        self.assertFalse(self.env["ir.model.fields"]._get("res.partner", "x_area"))
        self.assertFalse(sql.column_exists(self.env.cr, "res_partner", "x_area"))

    def test_on_a_model_of_the_project(self):
        line = self.make_model(self.project, "Studio geo item", model=ITEM_MODEL)
        self.project.action_apply()
        form = line._studio_views()["form"]
        self.add_geo(
            form,
            ttype="geo_line",
            label="Route",
            target="//group[@name='studio_left']",
            position="inside",
        )
        self.project.action_apply()
        field = self.env["ir.model.fields"]._get(ITEM_MODEL, "x_route")
        self.assertEqual((field.ttype, field.state), ("geo_line", "manual"))
        table = self.env[ITEM_MODEL]._table
        self.assertEqual(self.geometry_column(table, "x_route"), (3857, "LINESTRING"))
        item = self.env[ITEM_MODEL].create(
            {"x_name": "Route", "x_route": "LINESTRING(0 0, 5 5)"}
        )
        self.assertEqual(item.x_route.geom_type, "LineString")

    def test_review_warns_without_geoengine_view(self):
        change = self.add_geo()
        review = self.Editor.get_review(self.project.id)
        items = [item for group in review["groups"] for item in group["items"]]
        item = next(i for i in items if i["key"] == f"change:{change.id}")
        self.assertFalse(item["error"])
        self.assertIn("GeoEngine view", item["warning"])
        self.assertIn("Area", item["warning"])
        self.assertFalse(review["blocked"])
        others = [i for i in items if i["key"] != item["key"]]
        self.assertFalse([i for i in others if i["warning"]])

        self.make_view("geoengine", '<geoengine><field name="name"/></geoengine>')
        review = self.Editor.get_review(self.project.id)
        items = [item for group in review["groups"] for item in group["items"]]
        self.assertFalse([i for i in items if i["warning"]])
        data = self.Editor.get_editor_data(
            "res.partner", self.form.id, "form", self.project.id
        )
        self.assertFalse(data["geo_view_missing"])


@tagged("post_install", "-at_install")
class TestGeoFieldsAbsent(StudioCase):
    """Without base_geoengine the studio offers no geometry type."""

    def setUp(self):
        super().setUp()
        if self.Project._studio_geo_available():
            self.skipTest("base_geoengine is installed")
        self.project = self.make_project(MODULE)

    def test_no_geo_type(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.form.id, "form", self.project.id
        )
        self.assertFalse(set(GEO_TYPES) & set(data["field_types"]))
        self.assertFalse(data["geo_view_missing"])
        with self.assertRaisesRegex(UserError, "Unknown field type"):
            self.op(
                self.project,
                self.form,
                type="add_field",
                target="//field[@name='vat']",
                position="after",
                field={"ttype": "geo_point", "field_description": "Area"},
            )
