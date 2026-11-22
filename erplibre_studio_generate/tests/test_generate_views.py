# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.tests.common import (
    PIVOT_ARCH,
    TIMELINE_ARCH,
    StudioCase,
)
from odoo.tests import tagged

MODULE = "studio_test_generate_views"


@tagged("post_install", "-at_install")
class TestGenerateViews(StudioCase):
    """Generation of a project that edits kanban, search, pivot and, with
    web_timeline, timeline views."""

    def setUp(self):
        super().setUp()
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.kanban = self.env.ref("base.res_partner_kanban_view")
        self.search = self.env.ref("base.view_res_partner_filter")
        # A generated module inherits a view by its external id: the test
        # views get one.
        self.pivot = self.make_view(
            "pivot", PIVOT_ARCH, xml_id="base.erplibre_studio_test_pivot"
        )
        self.project = self.make_project(MODULE, destination=self.destination)
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
        self.foreign = self.foreign_field()
        self.op(
            self.project,
            self.search,
            type="add_filter",
            target="//filter[@name='type_company']",
            position="after",
            label="Studio filter",
            conditions=[{"field": self.foreign.name, "operator": "set"}],
        )
        self.op(
            self.project,
            self.search,
            type="hide",
            target="//filter[@name='inactive']",
            value=True,
        )
        self.op(
            self.project,
            self.pivot,
            type="move",
            source="//field[@name='country_id']",
            target="/pivot",
            position="inside",
            axis="col",
        )
        self.timeline = None
        if self.timeline_available():
            self.timeline = self.make_view(
                "timeline", TIMELINE_ARCH, xml_id="base.erplibre_studio_test_timeline"
            )
            self.op(
                self.project,
                self.timeline,
                type="set_attribute",
                target="/timeline",
                attribute="mode",
                value="week",
            )
        self.project.action_apply()

    def foreign_field(self):
        """A stored, searchable field of res.partner that a module other
        than base defines (code_generator brings mail)."""
        Fields = self.env["ir.model.fields"]
        for field in Fields.search(
            [
                ("model", "=", "res.partner"),
                ("store", "=", True),
                ("ttype", "in", ("char", "integer", "boolean", "many2one")),
            ],
            order="id",
        ):
            module = self.Project._module_of("ir.model.fields", field.id)
            if module and module != "base":
                return field
        self.skipTest("No module other than base adds a field to res.partner")

    def read(self, *parts):
        with open(
            os.path.join(self.destination, MODULE, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_dependencies(self):
        names = self.project._dependencies()
        self.assertIn("base", names)
        foreign_module = self.Project._module_of("ir.model.fields", self.foreign.id)
        self.assertIn(foreign_module, names)
        if self.timeline:
            # The timeline view is a base view in this test: web_timeline
            # comes from its view type.
            self.assertEqual(
                self.Project._module_of("ir.ui.view", self.timeline.id), "base"
            )
            self.assertIn("web_timeline", names)
        else:
            self.assertNotIn("web_timeline", names)
        self.assertNotIn(MODULE, names)

    def test_activity_dependency(self):
        """A project that only edits the activity view of the contacts
        depends on mail, the module of the view and of its view type."""
        if "activity" not in self.Project._view_types():
            self.skipTest("mail is not installed")
        self.assertEqual(self.Project._view_type_module("activity"), "mail")
        activity = self.env.ref("mail.res_partner_view_activity")
        project = self.make_project(
            "studio_test_generate_activity", destination=self.destination
        )
        self.op(
            project,
            activity,
            type="add_existing_field",
            target="//div[@t-name='activity-box']",
            position="inside",
            field_name="phone",
        )
        names = project._dependencies()
        self.assertIn("mail", names)
        self.assertIn("base", names)

    def test_groups_dependency(self):
        """A field shown for a group of another installed module: the
        generated module depends on that module."""
        form = self.make_view(
            "form",
            "<form><sheet><group><field name='name'/></group></sheet></form>",
            xml_id="base.erplibre_studio_test_form",
        )
        group = self.env["res.groups"].create({"name": "Studio test auditor"})
        self.bind_group(group, "studio_test_other_module", "group_auditor")
        self.op(
            self.project,
            form,
            type="set_attribute",
            target="//field[@name='name']",
            attribute="groups",
            value=["studio_test_other_module.group_auditor"],
        )
        self.assertIn("studio_test_other_module", self.project._dependencies())

    def test_advanced_attributes_written(self):
        """The widget, the options, the domain and the groups of a field,
        and a separator, reach the views file; the module of the comodel
        field the domain names, or an option, is a dependency."""
        form = self.make_view(
            "form",
            "<form><sheet><group name='g'><field name='name'/>"
            "<field name='parent_id'/><field name='type'/></group></sheet></form>",
            xml_id="base.erplibre_studio_test_form",
        )
        module = f"{MODULE}_attrs"
        project = self.make_project(module, destination=self.destination)
        app = project._studio_save_app({"name": "Studio test attrs"})
        line = project._studio_save_group(
            {"name": "Studio test reviewer", "app_id": app.id}
        )
        project.action_apply()
        own = line._studio_full_xmlid()
        domain = f"[('{self.foreign.name}', '!=', False)]"
        for name, attribute, value in (
            ("type", "widget", "radio"),
            ("parent_id", "domain", domain),
            ("name", "groups", f"base.group_system,{own}"),
        ):
            self.op(
                project,
                form,
                type="set_attribute",
                target=f"//field[@name='{name}']",
                attribute=attribute,
                value=value,
            )
        self.op(
            project,
            form,
            type="set_attribute",
            target="//field[@name='parent_id']",
            attribute="options",
            value={"no_create": True},
        )
        foreign_module = self.Project._module_of("ir.model.fields", self.foreign.id)
        # An option that names a comodel field: its module is a dependency.
        self.assertIn(
            foreign_module,
            project._attribute_dependencies(
                {"option_model": "res.partner", "option_fields": [self.foreign.name]}
            ),
        )
        self.assertNotIn(
            foreign_module,
            project._attribute_dependencies({"option_model": "res.partner"}),
        )
        self.op(
            project,
            form,
            type="add_separator",
            target="//field[@name='type']",
            position="after",
            label="Studio separator",
        )
        self.assertNotEqual(foreign_module, "base")
        self.assertIn(foreign_module, project._dependencies())
        project.action_apply()
        with self.server_actions():
            project.action_generate()
        with open(
            os.path.join(
                self.destination, module, "views", "erplibre_studio_views.xml"
            ),
            encoding="utf-8",
        ) as fh:
            views = etree.fromstring(fh.read().encode())
        record = views.find("record[@id='base_erplibre_studio_test_form_studio']")
        arch = record.find("field[@name='arch']")

        def attribute(name, attribute):
            return arch.xpath(
                f".//xpath[@expr=\"//field[@name='{name}']\"]"
                f"/attribute[@name='{attribute}']"
            )[0].text

        self.assertEqual(attribute("type", "widget"), "radio")
        self.assertEqual(attribute("parent_id", "domain"), domain)
        self.assertEqual(attribute("parent_id", "options"), "{'no_create': True}")
        self.assertEqual(attribute("name", "groups"), f"base.group_system,{own}")
        separator = arch.xpath(".//separator")
        self.assertEqual([s.get("string") for s in separator], ["Studio separator"])

    def test_generate(self):
        with self.server_actions():
            self.project.action_generate()
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertEqual(sorted(manifest["depends"]), self.project._dependencies())
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        records = {r.get("id"): r for r in views.findall("record")}
        expected = {
            "base_res_partner_kanban_view_studio",
            "base_view_res_partner_filter_studio",
            "base_erplibre_studio_test_pivot_studio",
        }
        if self.timeline:
            expected.add("base_erplibre_studio_test_timeline_studio")
        self.assertEqual(set(records), expected)
        search = records["base_view_res_partner_filter_studio"]
        self.assertTrue(search.xpath(".//xpath[@position='replace']"))
        studio_filter = search.xpath(".//filter[@name='studio_filter_studio_filter']")[
            0
        ]
        self.assertEqual(
            studio_filter.get("domain"), f"[('{self.foreign.name}', '!=', False)]"
        )
        # The move to the columns: two specs of the arch, not a nested data.
        pivot = records["base_erplibre_studio_test_pivot_studio"]
        arch = pivot.find("field[@name='arch']/data")
        self.assertEqual(
            [spec.get("position") for spec in arch], ["inside", "attributes"]
        )
        self.assertFalse(arch.findall("data"))
        kanban = records["base_res_partner_kanban_view_studio"]
        self.assertTrue(kanban.xpath(".//attribute[@name='default_group_by']"))
        # Each record applies alone on the arch of the view it inherits.
        self.project.action_revert()
        for record in records.values():
            parent = self.env.ref(record.find("field[@name='inherit_id']").get("ref"))
            arch = etree.tostring(record.find("field[@name='arch']/data"))
            self.env["ir.ui.view"].create(
                {
                    "name": "erplibre_studio generated arch check",
                    "model": parent.model,
                    "inherit_id": parent.id,
                    "arch": arch,
                    "active": True,
                }
            )._check_xml()
