# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.tests.common import StudioCase
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
