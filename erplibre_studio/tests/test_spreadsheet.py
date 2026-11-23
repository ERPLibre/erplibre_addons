# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from lxml import etree
from odoo.addons.base.models.ir_module import Module
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .. import arch as studio_arch
from .common import PIVOT_ARCH, StudioCase

MODULE = "studio_test_sheet"
SHEET_MODEL = "x_studio_test_sheet"
GRAPH_LINE = """
<graph type="line">
    <field name="country_id"/>
    <field name="color" type="measure"/>
</graph>
"""


class SpreadsheetMixin:
    def fields_info(self, model="res.partner"):
        return {
            name: {**info, "name": name}
            for name, info in self.env[model].fields_get().items()
        }

    def source(self, view, model="res.partner"):
        """What ``arch.spreadsheet_source`` reads of ``view`` as the
        database serves it."""
        arch = self.env[model].get_view(view.id, view.type)["arch"]
        return studio_arch.spreadsheet_source(
            etree.fromstring(arch), view.type, self.fields_info(model)
        )

    def send(self, project, view, model="res.partner"):
        return self.Editor.send_to_spreadsheet(
            project.id, model, view.id if view else False, view.type
        )


@tagged("post_install", "-at_install")
class TestStudioSpreadsheet(SpreadsheetMixin, StudioCase):
    """Send to a spreadsheet: the import data spreadsheet_oca reads from a
    list, a pivot or a graph view, the sheet it creates, and Revert."""

    def setUp(self):
        super().setUp()
        if "spreadsheet.spreadsheet" not in self.env:
            self.skipTest("spreadsheet_oca is not installed")
        self.project = self.make_project(MODULE)
        self.Sheet = self.env["spreadsheet.spreadsheet"]

    def test_list_columns_are_the_visible_fields(self):
        source = self.source(self.list)
        names = [column["name"] for column in source["columns"]]
        self.assertEqual(names[0], "complete_name")
        self.assertIn("email", names)
        # column_invisible, optional « hide »: not shown by default.
        self.assertNotIn("display_name", names)
        self.assertNotIn("mobile", names)
        fields_info = self.fields_info()
        for column in source["columns"]:
            self.assertEqual(column["type"], fields_info[column["name"]]["type"])
            self.assertNotIn(column["type"], ("binary", "json"))
        root = etree.fromstring("""<list default_order="name desc, id">
                <field name="sequence" widget="handle"/>
                <field name="name"/>
                <field name="ref" invisible="1"/>
                <field name="vat" column_invisible="True"/>
                <field name="email" invisible="not is_company"/>
                <field name="image_128"/>
            </list>""")
        source = studio_arch.spreadsheet_source(root, "list", fields_info)
        self.assertEqual(
            source["columns"],
            [
                {"name": "name", "type": "char"},
                {"name": "email", "type": "char"},
            ],
        )
        self.assertEqual(
            source["orderBy"],
            [{"name": "name", "asc": False}, {"name": "id", "asc": True}],
        )

    def test_pivot_axes_and_measures(self):
        pivot = self.make_view("pivot", PIVOT_ARCH)
        source = self.source(pivot)
        self.assertEqual(source["rowGroupBys"], ["country_id"])
        self.assertEqual(source["colGroupBys"], [])
        self.assertEqual(source["activeMeasures"], ["partner_latitude"])
        self.assertEqual(source["title"], "Partners")
        pivot = self.make_view(
            "pivot",
            """<pivot>
                <field name="create_date" type="row" interval="month"/>
                <field name="country_id" type="col"/>
            </pivot>""",
        )
        source = self.source(pivot)
        self.assertEqual(source["rowGroupBys"], ["create_date:month"])
        self.assertEqual(source["colGroupBys"], ["country_id"])
        self.assertEqual(source["activeMeasures"], ["__count"])
        self.assertIsNone(source["title"])

    def test_graph_mode_group_bys_and_measure(self):
        graph = self.make_view("graph", GRAPH_LINE)
        source = self.source(graph)
        self.assertEqual(source["mode"], "line")
        self.assertEqual(source["groupBy"], ["country_id"])
        self.assertEqual(source["measure"], "color")
        # The defaults of the graph view.
        self.assertEqual(
            (source["stacked"], source["cumulated"], source["order"]),
            (True, False, None),
        )
        graph = self.make_view(
            "graph",
            """<graph order="desc" stacked="0">
                <field name="create_date" interval="week"/>
                <field name="name" type="row"/>
            </graph>""",
        )
        source = self.source(graph)
        self.assertEqual(source["mode"], "bar")
        self.assertEqual(source["groupBy"], ["create_date:week", "name"])
        self.assertEqual(source["measure"], "__count")
        self.assertEqual((source["order"], source["stacked"]), ("DESC", False))

    def test_send_a_list(self):
        answer = self.send(self.project, self.list)
        action = answer["action"]
        self.assertEqual(action["tag"], "action_spreadsheet_oca")
        params = action["params"]
        self.assertEqual(params["model"], "spreadsheet.spreadsheet")
        sheet = self.Sheet.browse(params["spreadsheet_id"])
        self.assertTrue(sheet.exists())
        self.assertEqual(sheet.owner_id, self.env.user)
        data = params["import_data"]
        self.assertEqual((data["mode"], data["new"]), ("list", 1))
        self.assertEqual(data["name"], sheet.name)
        self.assertEqual(data["metaData"]["model"], "res.partner")
        self.assertEqual(data["metaData"]["domain"], "[]")
        self.assertEqual(data["metaData"]["columns"], self.source(self.list)["columns"])
        self.assertEqual(data["metaData"]["fields"]["email"]["name"], "email")
        self.assertEqual(
            data["dyn_number_of_rows"],
            min(self.env["res.partner"].search_count([]), 80),
        )
        self.assertNotIn("actionXmlId", data)
        self.assertFalse(answer["notice"])
        row = self.project.spreadsheet_ids
        self.assertEqual(len(row), 1)
        self.assertEqual(
            (row.model, row.view_type, row.view_id, row.sheet_id),
            ("res.partner", "list", self.list, sheet.id),
        )

    def test_send_a_pivot_and_a_graph(self):
        pivot = self.make_view("pivot", PIVOT_ARCH)
        data = self.send(self.project, pivot)["action"]["params"]["import_data"]
        self.assertEqual(data["mode"], "pivot")
        meta = data["metaData"]
        self.assertEqual(meta["resModel"], "res.partner")
        self.assertEqual(meta["rowGroupBys"], ["country_id"])
        self.assertEqual(meta["activeMeasures"], ["partner_latitude"])
        self.assertEqual(data["searchParams"], {"domain": "[]", "context": {}})
        graph = self.make_view("graph", GRAPH_LINE)
        data = self.send(self.project, graph)["action"]["params"]["import_data"]
        self.assertEqual(data["mode"], "graph")
        meta = data["metaData"]
        self.assertEqual(
            (meta["mode"], meta["groupBy"], meta["measure"]),
            ("line", ["country_id"], "color"),
        )
        self.assertEqual(meta["title"], "Contact")
        self.assertEqual(
            data["searchParams"],
            {"context": {}, "domain": "[]", "groupBy": [], "orderBy": []},
        )
        self.assertEqual(
            self.project.spreadsheet_ids.mapped("view_type"),
            ["pivot", "graph"],
        )

    def test_draft_changes_are_not_in_the_sheet(self):
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='email']",
            value="Mail",
        )
        answer = self.send(self.project, self.list)
        self.assertIn("draft changes are not in it", answer["notice"])
        self.project.action_apply()
        self.assertFalse(self.send(self.project, self.list)["notice"])

    def test_refusals(self):
        with self.assertRaisesRegex(UserError, "list, a pivot or a graph"):
            self.send(self.project, self.form)
        self.make_model(self.project, "Studio test sheet", model=SHEET_MODEL)
        with self.assertRaisesRegex(UserError, "Apply first"):
            self.Editor.send_to_spreadsheet(self.project.id, SHEET_MODEL, False, "list")
        user = new_test_user(
            self.env,
            login="studio_test_sheet_no_group",
            groups="base.group_user,base.group_system",
        )
        user.groups_id -= self.env.ref("spreadsheet_oca.group_user")
        self.assertFalse(user.has_group("spreadsheet_oca.group_user"))
        with self.assertRaisesRegex(UserError, "spreadsheet_oca"):
            self.Editor.with_user(user).send_to_spreadsheet(
                self.project.id, "res.partner", self.list.id, "list"
            )
        self.assertFalse(self.project.spreadsheet_ids)

    def test_editor_payload_says_available(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.list.id, "list", self.project.id
        )
        self.assertTrue(data["spreadsheet_available"])

    def test_revert_deletes_the_sheets_of_its_models(self):
        line = self.make_model(self.project, "Studio test sheet", model=SHEET_MODEL)
        self.project.action_apply()
        listing = line._studio_views()["list"]
        own = self.send(self.project, listing, SHEET_MODEL)
        data = own["action"]["params"]["import_data"]
        self.assertEqual(data["actionXmlId"], f"{MODULE}.action_{SHEET_MODEL}")
        own_sheet = self.Sheet.browse(own["action"]["params"]["spreadsheet_id"])
        partner = self.send(self.project, self.list)
        partner_sheet = self.Sheet.browse(partner["action"]["params"]["spreadsheet_id"])
        answer = self.project._studio_revert_report()
        self.assertEqual(
            answer["report"]["spreadsheets"],
            [
                {
                    "name": own_sheet.name,
                    "model": SHEET_MODEL,
                    "deleted": True,
                },
                {
                    "name": partner_sheet.name,
                    "model": "res.partner",
                    "deleted": False,
                },
            ],
        )
        self.assertEqual(
            self.Editor.get_revert_report(self.project.id)["digest"],
            answer["digest"],
        )
        # A sheet deleted by hand leaves the report.
        extra = self.send(self.project, self.list)["action"]["params"]
        self.Sheet.browse(extra["spreadsheet_id"]).unlink()
        self.assertEqual(
            len(self.project._studio_revert_report()["report"]["spreadsheets"]),
            2,
        )
        admin = self.env.ref("base.user_admin")
        project = self.project.with_user(admin)
        with self.assertRaisesRegex(UserError, "review it again"):
            with self.env.cr.savepoint():
                project.action_revert(digest=answer["digest"] + "0")
        project.action_revert(digest=self.project._studio_revert_report()["digest"])
        self.assertNotIn(SHEET_MODEL, self.env)
        self.assertFalse(own_sheet.exists())
        self.assertTrue(partner_sheet.exists())
        self.assertFalse(self.project.spreadsheet_ids)
        self.assertEqual(
            self.project._studio_revert_report()["report"]["spreadsheets"], []
        )

    def sheets_of_a_model(self):
        """A model of the project applied, a sheet sent from its list and
        one from the contacts: (model line, its sheet, the contacts')."""
        line = self.make_model(self.project, "Studio test sheet", model=SHEET_MODEL)
        self.project.action_apply()
        own = self.send(self.project, line._studio_views()["list"], SHEET_MODEL)
        partner = self.send(self.project, self.list)
        return (
            line,
            self.Sheet.browse(own["action"]["params"]["spreadsheet_id"]),
            self.Sheet.browse(partner["action"]["params"]["spreadsheet_id"]),
        )

    def test_apply_deletes_the_sheets_of_a_removed_model(self):
        line, own_sheet, partner_sheet = self.sheets_of_a_model()
        self.assertFalse(self.project._studio_apply_report()["report"]["spreadsheets"])
        line.unlink()
        answer = self.project._studio_apply_report()
        self.assertEqual(
            answer["report"]["spreadsheets"],
            [{"name": own_sheet.name, "model": SHEET_MODEL, "deleted": True}],
        )
        # An empty model goes without a question; its sheet does not.
        self.assertTrue(answer["confirm"])
        self.project.action_apply()
        self.assertNotIn(SHEET_MODEL, self.env)
        self.assertFalse(own_sheet.exists())
        self.assertTrue(partner_sheet.exists())
        self.assertEqual(self.project.spreadsheet_ids.mapped("model"), ["res.partner"])
        report = self.project._studio_revert_report()["report"]
        self.assertEqual(
            [item["model"] for item in report["spreadsheets"]], ["res.partner"]
        )

    def test_uninstall_deletes_the_sheets_of_its_models(self):
        _line, own_sheet, partner_sheet = self.sheets_of_a_model()
        module = self.env["ir.module.module"].create(
            {"name": MODULE, "state": "installed"}
        )
        report = module._studio_uninstall_report({MODULE})
        self.assertEqual(
            report["spreadsheets"],
            [{"name": own_sheet.name, "model": SHEET_MODEL, "deleted": True}],
        )
        wizard = self.env["base.module.uninstall"].create({"module_id": module.id})
        self.assertIn("Spreadsheets", str(wizard.studio_report))
        with patch.object(Module, "module_uninstall", lambda self: True):
            module.module_uninstall()
        self.assertFalse(own_sheet.exists())
        self.assertTrue(partner_sheet.exists())
        self.assertFalse(self.project.spreadsheet_ids)

    def test_revert_report_html_lists_the_sheets(self):
        self.send(self.project, self.list)
        action = self.project.action_revert_wizard()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        html = str(wizard.report_html)
        self.assertIn("Spreadsheets", html)
        self.assertIn("kept, columns of removed fields show errors", html)


@tagged("post_install", "-at_install")
class TestStudioSpreadsheetAbsent(SpreadsheetMixin, StudioCase):
    """Without spreadsheet_oca: nothing offered, nothing reported."""

    def setUp(self):
        super().setUp()
        if "spreadsheet.spreadsheet" in self.env:
            self.skipTest("spreadsheet_oca is installed")
        self.project = self.make_project(MODULE)

    def test_nothing_without_spreadsheet_oca(self):
        self.assertFalse(self.Project._studio_spreadsheet_available())
        data = self.Editor.get_editor_data(
            "res.partner", self.list.id, "list", self.project.id
        )
        self.assertFalse(data["spreadsheet_available"])
        with self.assertRaisesRegex(UserError, "spreadsheet_oca"):
            self.send(self.project, self.list)
        self.make_model(self.project, "Studio test sheet", model=SHEET_MODEL)
        self.project.action_apply()
        report = self.project._studio_revert_report()["report"]
        self.assertEqual(report["spreadsheets"], [])
