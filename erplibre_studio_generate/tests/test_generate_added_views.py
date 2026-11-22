# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.exceptions import UserError
from odoo.tests import tagged

MODULE = "studio_test_generate_added"


@tagged("post_install", "-at_install")
class TestGenerateAddedViews(StudioCase):
    """Generation of a project that adds a pivot view to the contacts, which
    have none, and changes it."""

    def setUp(self):
        super().setUp()
        if self.env["ir.ui.view"].default_view("res.partner", "pivot"):
            self.skipTest("res.partner has a pivot view in this database")
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(MODULE, destination=self.destination)
        self.Editor.add_view(self.project.id, "res.partner", "pivot")
        self.line = self.project.view_line_ids
        view = self.Editor._resolve_view("res.partner", False, "pivot", self.project)
        self.op(
            self.project,
            view,
            type="add_existing_field",
            target="/pivot",
            position="inside",
            field_name="create_date",
            axis="col",
            interval="month",
        )

    def read(self, *parts):
        with open(
            os.path.join(self.destination, MODULE, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_generate(self):
        with self.server_actions():
            self.project.action_apply()
            self.project.action_generate()
        self.assertIn("base", self.project._dependencies())
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        records = [r.get("id") for r in views.findall("record")]
        xml_name = "res_partner_view_pivot"
        studio_name = f"{MODULE}_{xml_name}_studio"
        # The view comes before the inherited view that refers to it.
        self.assertEqual(records, [xml_name, studio_name])
        primary = views.find(f"record[@id='{xml_name}']")
        self.assertEqual(primary.find("field[@name='model']").text, "res.partner")
        self.assertEqual(primary.find("field[@name='type']").text, "pivot")
        self.assertEqual(primary.find("field[@name='priority']").text, "16")
        self.assertEqual(primary.find("field[@name='arch']/pivot").tag, "pivot")
        studio = views.find(f"record[@id='{studio_name}']")
        self.assertEqual(
            studio.find("field[@name='inherit_id']").get("ref"),
            f"{MODULE}.{xml_name}",
        )
        self.assertIn(xml_name, self.read("readme", "DESCRIPTION.md"))


@tagged("post_install", "-at_install")
class TestGenerateAddedGraph(StudioCase):
    """Generation of a project that adds a graph view to the contacts, which
    have none, and changes it."""

    module = "studio_test_generate_graph"

    def setUp(self):
        super().setUp()
        if self.env["ir.ui.view"].default_view("res.partner", "graph"):
            self.skipTest("res.partner has a graph view in this database")
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(self.module, destination=self.destination)
        self.Editor.add_view(self.project.id, "res.partner", "graph")
        view = self.Editor._resolve_view("res.partner", False, "graph", self.project)
        self.op(
            self.project,
            view,
            type="add_existing_field",
            target="/graph",
            position="inside",
            field_name="partner_latitude",
            axis="measure",
        )

    def read(self, *parts):
        with open(
            os.path.join(self.destination, self.module, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_generate(self):
        with self.server_actions():
            self.project.action_apply()
            self.project.action_generate()
        self.assertIn("base", self.project._dependencies())
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        records = [r.get("id") for r in views.findall("record")]
        xml_name = "res_partner_view_graph"
        studio_name = f"{self.module}_{xml_name}_studio"
        self.assertEqual(records, [xml_name, studio_name])
        primary = views.find(f"record[@id='{xml_name}']")
        self.assertEqual(primary.find("field[@name='type']").text, "graph")
        graph = primary.find("field[@name='arch']/graph")
        self.assertEqual(graph.get("type"), "bar")
        self.assertEqual(
            [f.get("name") for f in graph.findall("field")], ["create_date"]
        )
        studio = views.find(f"record[@id='{studio_name}']")
        self.assertEqual(
            studio.find("field[@name='inherit_id']").get("ref"),
            f"{self.module}.{xml_name}",
        )
        self.assertIn("partner_latitude", etree.tostring(studio).decode())


@tagged("post_install", "-at_install")
class TestGenerateAddedCalendar(StudioCase):
    """Generation of a project that adds a calendar view to the contacts,
    which have none, and colors its events."""

    module = "studio_test_generate_calendar"

    def setUp(self):
        super().setUp()
        if self.env["ir.ui.view"].default_view("res.partner", "calendar"):
            self.skipTest("res.partner has a calendar view in this database")
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(self.module, destination=self.destination)
        self.Editor.add_view(self.project.id, "res.partner", "calendar")
        view = self.Editor._resolve_view("res.partner", False, "calendar", self.project)
        self.op(
            self.project,
            view,
            type="set_attribute",
            target="/calendar",
            attribute="color",
            value="user_id",
        )

    def read(self, *parts):
        with open(
            os.path.join(self.destination, self.module, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_generate(self):
        date, _readonly = self.project._studio_calendar_date("res.partner")
        with self.server_actions():
            self.project.action_apply()
            self.project.action_generate()
        self.assertIn("base", self.project._dependencies())
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        records = [r.get("id") for r in views.findall("record")]
        xml_name = "res_partner_view_calendar"
        studio_name = f"{self.module}_{xml_name}_studio"
        self.assertEqual(records, [xml_name, studio_name])
        primary = views.find(f"record[@id='{xml_name}']")
        self.assertEqual(primary.find("field[@name='type']").text, "calendar")
        calendar = primary.find("field[@name='arch']/calendar")
        self.assertEqual(
            (calendar.get("date_start"), calendar.get("mode")), (date, "month")
        )
        self.assertEqual([f.get("name") for f in calendar.findall("field")], ["name"])
        studio = views.find(f"record[@id='{studio_name}']")
        self.assertEqual(
            studio.find("field[@name='inherit_id']").get("ref"),
            f"{self.module}.{xml_name}",
        )
        self.assertIn('name="color">user_id<', etree.tostring(studio).decode())


@tagged("post_install", "-at_install")
class TestGenerateAddedHierarchy(StudioCase):
    """Generation of a project that adds a hierarchy view to the contacts,
    which have none, and gives it a children field, when web_hierarchy is
    installed."""

    module = "studio_test_generate_hierarchy"

    def setUp(self):
        super().setUp()
        if not self.hierarchy_available():
            self.skipTest("web_hierarchy is not installed")
        if self.env["ir.ui.view"].default_view("res.partner", "hierarchy"):
            self.skipTest("res.partner has a hierarchy view in this database")
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(self.module, destination=self.destination)
        self.Editor.add_view(self.project.id, "res.partner", "hierarchy")
        view = self.Editor._resolve_view(
            "res.partner", False, "hierarchy", self.project
        )
        self.op(
            self.project,
            view,
            type="set_attribute",
            target="/hierarchy",
            attribute="child_field",
            value="child_ids",
        )

    def read(self, *parts):
        with open(
            os.path.join(self.destination, self.module, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_generate(self):
        with self.server_actions():
            self.project.action_apply()
            self.project.action_generate()
        self.assertIn("web_hierarchy", self.project._dependencies())
        manifest = self.read("__manifest__.py")
        self.assertIn("web_hierarchy", manifest)
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        records = [r.get("id") for r in views.findall("record")]
        xml_name = "res_partner_view_hierarchy"
        studio_name = f"{self.module}_{xml_name}_studio"
        self.assertEqual(records, [xml_name, studio_name])
        primary = views.find(f"record[@id='{xml_name}']")
        self.assertEqual(primary.find("field[@name='type']").text, "hierarchy")
        hierarchy = primary.find("field[@name='arch']/hierarchy")
        self.assertEqual(hierarchy.get("parent_field"), "parent_id")
        self.assertEqual(
            [f.get("name") for f in hierarchy.findall("field")], ["parent_id"]
        )
        self.assertEqual(
            len(hierarchy.xpath("templates/t[@t-name='hierarchy-box']")), 1
        )
        studio = views.find(f"record[@id='{studio_name}']")
        self.assertEqual(
            studio.find("field[@name='inherit_id']").get("ref"),
            f"{self.module}.{xml_name}",
        )
        text = etree.tostring(studio).decode()
        # The children field, and the field loaded for web_hierarchy.
        self.assertIn('name="child_field">child_ids<', text)
        self.assertIn('<field name="child_ids"/>', text)


@tagged("post_install", "-at_install")
class TestGenerateAddedLeaflet(StudioCase):
    """Generation of a project that adds a map to the contacts, which have
    none, and gives it a popup title and a new address field, when
    web_view_leaflet_map is installed."""

    module = "studio_test_generate_leaflet"

    def setUp(self):
        super().setUp()
        if "leaflet_map" not in self.Project._view_types():
            self.skipTest("web_view_leaflet_map is not installed")
        if self.env["ir.ui.view"].default_view("res.partner", "leaflet_map"):
            self.skipTest("res.partner has a leaflet_map view in this database")
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(self.module, destination=self.destination)
        self.Editor.add_view(self.project.id, "res.partner", "leaflet_map")
        view = self.Editor._resolve_view(
            "res.partner", False, "leaflet_map", self.project
        )
        self.op(
            self.project,
            view,
            type="set_attribute",
            target="/leaflet_map",
            attribute="field_title",
            value="email",
        )
        self.address = self.op(
            self.project,
            view,
            type="add_field",
            target="/leaflet_map",
            position="inside",
            attribute="field_address",
            field={"ttype": "char", "field_description": "Map address"},
        ).field_name

    def read(self, *parts):
        with open(
            os.path.join(self.destination, self.module, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_generate(self):
        with self.server_actions():
            self.project.action_apply()
            self.project.action_generate()
        self.assertIn("web_view_leaflet_map", self.project._dependencies())
        self.assertIn("web_view_leaflet_map", self.read("__manifest__.py"))
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        records = [r.get("id") for r in views.findall("record")]
        xml_name = "res_partner_view_leaflet_map"
        studio_name = f"{self.module}_{xml_name}_studio"
        self.assertEqual(records, [xml_name, studio_name])
        primary = views.find(f"record[@id='{xml_name}']")
        self.assertEqual(primary.find("field[@name='type']").text, "leaflet_map")
        leaflet = primary.find("field[@name='arch']/leaflet_map")
        self.assertEqual(leaflet.get("field_latitude"), "partner_latitude")
        self.assertEqual(leaflet.get("field_longitude"), "partner_longitude")
        text = etree.tostring(views.find(f"record[@id='{studio_name}']")).decode()
        self.assertIn('name="field_title">email<', text)
        self.assertIn(f'name="field_address">{self.address}<', text)
        self.assertIn(self.address, self.read("models", "res_partner.py"))


@tagged("post_install", "-at_install")
class TestGenerateLeafletDate(StudioCase):
    """A map added to the industries, which have no date_localization, on a
    development database: Add a view creates the field with the map, Apply
    creates both, Revert removes both, and the generated module defines
    the field, when web_view_leaflet_map is installed."""

    module = "studio_test_generate_leaflet_date"
    model = "res.partner.industry"
    date = "date_localization"
    # The rule this module reads from the database.
    production_rule_pinned = False

    def setUp(self):
        super().setUp()
        if "leaflet_map" not in self.Project._view_types():
            self.skipTest("web_view_leaflet_map is not installed")
        if self.Project._studio_field_name_rule()["prefix_required"]:
            self.skipTest("the database requires the x_ prefix")
        self.View = self.env["ir.ui.view"]
        if self.View.default_view(self.model, "leaflet_map"):
            self.skipTest(f"{self.model} has a leaflet_map view in this database")
        if self.date in self.env[self.model]._fields:
            self.skipTest(f"{self.model} has {self.date} in this database")
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(self.module, destination=self.destination)

    def entry(self):
        data = self.Editor.get_editor_data(self.model, False, "list", self.project.id)
        return next(e for e in data["view_list"] if e["type"] == "leaflet_map")

    def resolve(self):
        return self.Editor._resolve_view(self.model, False, "leaflet_map", self.project)

    def add_map(self):
        """The map, and its two coordinates as new fields of its lanes."""
        self.Editor.add_view(self.project.id, self.model, "leaflet_map")
        line = self.project.view_line_ids
        for attribute, label in (
            ("field_latitude", "Map latitude"),
            ("field_longitude", "Map longitude"),
        ):
            self.op(
                self.project,
                self.resolve(),
                type="add_field",
                target="/leaflet_map",
                position="inside",
                attribute=attribute,
                field={"ttype": "float", "field_description": label},
            )
        return line

    def date_change(self):
        return self.project.change_ids.filtered(lambda c: c.field_name == self.date)

    def test_add_view_creates_the_field(self):
        entry = self.entry()
        self.assertEqual((entry["reason_code"], entry["editable"]), ("no_view", False))
        self.assertIn(self.date, entry["description"])
        self.Editor.add_view(self.project.id, self.model, "leaflet_map")
        line = self.project.view_line_ids
        change = self.project.change_ids
        self.assertEqual(len(change), 1)
        self.assertEqual(
            (change.change_type, change.view_line_id, change.xpath, change.position),
            ("add_field", line, "/leaflet_map", "inside"),
        )
        payload = change._payload()
        self.assertEqual(payload["field_name"], self.date)
        self.assertFalse(payload["name_auto"])
        self.assertNotIn("root_attribute", payload)
        self.assertEqual(
            (payload["field"]["ttype"], payload["field"]["field_description"]),
            ("date", "Geolocation Date"),
        )
        arch = self.draft(self.project, self.resolve())
        self.assertEqual(arch.xpath("/leaflet_map/field/@name"), [self.date])
        self.assertNotIn(self.date, arch.attrib.values())
        # Not a lane: the lanes name the root attributes only.
        layout = self.Editor.get_editor_data(
            self.model, False, "leaflet_map", self.project.id
        )["layout"]
        self.assertNotIn(self.date, layout["lanes"].values())
        # The renderer reads the field by its name: a rename is refused, a
        # new label keeps it. A map takes neither operation: they come from
        # another view of the model.
        view = self.Editor._resolve_view(self.model, False, "list", self.project)
        for op in (
            {"type": "rename_field", "field_name": self.date, "new_name": "geo_date"},
            {"type": "rename_field", "field_name": self.date, "auto": True},
        ):
            with self.subTest(op=op), self.assertRaisesRegex(UserError, self.date):
                self.op(self.project, view, **op)
        self.op(
            self.project,
            view,
            type="update_field",
            field_name=self.date,
            field={"field_description": "Map date"},
        )
        self.assertEqual(self.date_change().field_name, self.date)

    def test_production_rule_refuses(self):
        with self.production_rule():
            entry = self.entry()
            self.assertEqual(entry["reason_code"], "needs_field")
            self.assertFalse(entry["description"])
            with self.assertRaisesRegex(UserError, self.date):
                self.Editor.add_view(self.project.id, self.model, "leaflet_map")
        self.assertFalse(self.project.view_line_ids)

    def test_apply_and_revert(self):
        line = self.add_map()
        self.project.action_apply()
        Model = self.env[self.model]
        self.assertEqual(Model._fields[self.date].type, "date")
        field = self.env["ir.model.fields"]._get(self.model, self.date)
        self.assertEqual((field.state, field.ttype), ("manual", "date"))
        view = line.view_id
        self.assertEqual(self.View.default_view(self.model, "leaflet_map"), view.id)
        arch = etree.fromstring(Model.get_view(view.id, "leaflet_map")["arch"])
        self.assertEqual(arch.xpath("//field/@name").count(self.date), 1)
        self.project.action_revert()
        self.assertFalse(view.exists())
        self.assertNotIn(self.date, self.env[self.model]._fields)
        self.assertFalse(self.env["ir.model.fields"]._get(self.model, self.date))

    def test_apply_waits_for_the_field(self):
        """A map whose date field left the draft (an undo, a removal) is
        refused at Apply: its markers would read a missing field."""
        self.add_map()
        self.date_change().unlink()
        self.assertIn(self.date, self.Editor.get_review(self.project.id)["blocked"])
        with self.assertRaisesRegex(UserError, self.date):
            self.project.action_apply()

    def test_generate(self):
        self.add_map()
        with self.server_actions():
            self.project.action_apply()
            self.project.action_generate()
        self.assertIn("web_view_leaflet_map", self.project._dependencies())
        with open(
            os.path.join(self.destination, self.module, "__manifest__.py"),
            encoding="utf-8",
        ) as fh:
            self.assertIn("web_view_leaflet_map", fh.read())
        path = os.path.join(
            self.destination, self.module, "models", "res_partner_industry.py"
        )
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        self.assertRegex(source, rf"{self.date} = fields\.Date\(")
        self.assertIn("Geolocation Date", source)
