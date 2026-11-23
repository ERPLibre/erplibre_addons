# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.tests import tagged

MODULE = "studio_test_generate_geo"


@tagged("post_install", "-at_install")
class TestGenerateGeo(StudioCase):
    """Generation of a project that adds a geometry field to the contact
    form, when base_geoengine is installed: the module declares the field
    with the class base_geoengine adds to odoo.fields, and depends on it."""

    def setUp(self):
        super().setUp()
        if not self.Project._studio_geo_available():
            self.skipTest("base_geoengine is not installed")
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(MODULE, destination=self.destination)
        self.name = self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={"ttype": "geo_point", "field_description": "Site"},
        ).field_name

    def read(self, *parts):
        with open(
            os.path.join(self.destination, MODULE, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_field_type_module(self):
        self.assertEqual(self.Project._field_type_module("geo_point"), "base_geoengine")
        self.assertEqual(self.Project._field_type_module("char"), "base")
        self.assertFalse(self.Project._field_type_module("no_such_type"))
        self.assertIn("base_geoengine", self.project._dependencies())

    def test_generate(self):
        with self.server_actions():
            self.project.action_apply()
            self.project.action_generate()
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertIn("base_geoengine", manifest["depends"])
        model = self.read("models", "res_partner.py")
        compile(model, "res_partner.py", "exec")
        self.assertIn(f"{self.name} = fields.GeoPoint(", model)
        self.assertIn('string="Site"', model)

    def test_generate_geoengine_view(self):
        """A GeoEngine view added once the geo field is applied: the views
        file writes its layers after the view, each under the external id
        Apply gave it, the vector layer naming the field by the external id
        the module gives it."""
        if "geoengine" not in self.Project._view_types():
            self.skipTest("base_geoengine is not installed")
        if self.env["ir.ui.view"].search_count(
            [("model", "=", "res.partner"), ("type", "=", "geoengine")]
        ):
            self.skipTest("res.partner has a geoengine view in this database")
        with self.server_actions():
            self.project.action_apply()
            self.Editor.add_view(self.project.id, "res.partner", "geoengine")
            self.project.action_apply()
            self.project.action_generate()
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertIn("base_geoengine", manifest["depends"])
        root = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        records = root.xpath("/odoo/record")
        ids = [record.get("id") for record in records]
        view = "res_partner_view_geoengine"
        raster, vector = "res_partner_geo_raster_10", "res_partner_geo_vector_10"
        self.assertLess(ids.index(view), ids.index(raster))
        self.assertLess(ids.index(view), ids.index(vector))
        by_id = {record.get("id"): record for record in records}
        self.assertEqual(by_id[raster].get("model"), "geoengine.raster.layer")
        self.assertEqual(by_id[vector].get("model"), "geoengine.vector.layer")
        for name in (raster, vector):
            self.assertEqual(by_id[name].xpath("field[@name='view_id']/@ref"), [view])
        self.assertEqual(
            by_id[raster].xpath("field[@name='raster_type']/text()"), ["osm"]
        )
        self.assertEqual(
            by_id[vector].xpath("field[@name='geo_field_id']/@ref"),
            [f"field_res_partner__{self.name}"],
        )
        self.assertEqual(
            by_id[vector].xpath("field[@name='active_on_startup']/@eval"), ["True"]
        )
        arch = by_id[view].xpath("field[@name='arch']/geoengine")[0]
        self.assertEqual(arch.xpath("field/@name")[-1], self.name)
        self.assertEqual(arch.xpath("templates/t/@t-name"), ["info_box"])
