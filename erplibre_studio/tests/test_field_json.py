# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import sql

from .. import arch as studio_arch
from .common import PIVOT_ARCH, StudioCase

VAT = "//field[@name='vat']"


@tagged("post_install", "-at_install")
class TestFieldJson(StudioCase):
    """A new JSON field (fields.Json): read-only through the widget
    « jsonb » in a form or a list, refused elsewhere, never offered to
    search, sort or group by."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_field_json")

    def add(self, view, target=VAT, position="after", **field):
        return self.op(
            self.project,
            view,
            type="add_field",
            target=target,
            position=position,
            field={"field_description": "Studio data", "ttype": "json", **field},
        )

    def test_form_takes_it_read_only(self):
        change = self.add(self.form)
        payload = change._payload()
        self.assertEqual(payload["field"]["ttype"], "json")
        self.assertEqual(payload["node_attrs"], {"widget": "jsonb"})
        self.assertNotIn("node_children", payload)
        data = self.Editor.get_editor_data(
            "res.partner", self.form.id, "form", self.project.id
        )
        self.assertIn("json", data["field_types"])
        node = self.draft(self.project, self.form).xpath(
            f"//field[@name='{change.field_name}']"
        )
        self.assertEqual(node[0].get("widget"), "jsonb")

    def test_list_takes_it(self):
        change = self.add(self.list, target="//field[@name='email']")
        self.assertEqual(change._payload()["node_attrs"], {"widget": "jsonb"})

    def test_other_views_refuse_it(self):
        kanban = self.env.ref("base.res_partner_kanban_view")
        search = self.env.ref("base.view_res_partner_filter")
        pivot = self.make_view("pivot", PIVOT_ARCH)
        with self.assertRaisesRegex(
            UserError, "A JSON field shows in a form or a list only."
        ):
            self.add(kanban, target="//field[@name='email']")
        # A search or a pivot takes no new field at all.
        for view, target, position in (
            (search, "//field[@name='email']", "after"),
            (pivot, "/pivot", "inside"),
        ):
            with self.subTest(view=view.type), self.assertRaises(UserError):
                self.add(view, target=target, position=position)
        self.assertFalse(self.project.change_ids)
        refusal = studio_arch.field_type_refusal("kanban", "json")
        self.assertEqual(refusal.code, "json_view")
        self.assertIsNone(studio_arch.field_type_refusal("list", "json"))
        # The x2many gate reads the same table.
        self.assertEqual(
            studio_arch.x2many_refusal("list", "one2many").code, "x2many_view"
        )
        self.assertIsNone(studio_arch.x2many_refusal("kanban", "json"))

    def test_apply_creates_a_jsonb_column(self):
        change = self.add(self.form)
        name = change.field_name
        self.project.action_apply()
        field = self.env["ir.model.fields"]._get("res.partner", name)
        self.assertEqual((field.ttype, field.state), ("json", "manual"))
        column = sql.table_columns(self.env.cr, "res_partner")[name]
        self.assertEqual(column["udt_name"], "jsonb")
        partner = self.env["res.partner"].create({"name": "Studio json"})
        value = {"a": 1, "b": [1, 2]}
        partner.write({name: value})
        partner.invalidate_recordset([name])
        self.assertEqual(partner[name], value)
        # Odoo neither searches, sorts nor groups by it, whatever its flags.
        info = self.Project._field_info("res.partner", name)
        self.assertFalse(info["searchable"] or info["sortable"] or info["groupable"])
        search = self.env.ref("base.view_res_partner_filter")
        data = self.Editor.get_editor_data(
            "res.partner", search.id, "search", self.project.id
        )
        self.assertNotIn(name, [item["name"] for item in data["palette"]])
        for kind in ("search_field", "group_field", "sort_field"):
            with self.subTest(kind=kind):
                self.assertNotIn(name, [value for value, _l in data["choices"][kind]])
        kanban = self.env.ref("base.res_partner_kanban_view")
        data = self.Editor.get_editor_data(
            "res.partner", kanban.id, "kanban", self.project.id
        )
        self.assertNotIn(name, [item["name"] for item in data["palette"]])
        data = self.Editor.get_editor_data(
            "res.partner", self.list.id, "list", self.project.id
        )
        self.assertIn(name, [item["name"] for item in data["palette"]])
        # An existing JSON field dropped into a kanban is refused too.
        with self.assertRaisesRegex(UserError, "A JSON field shows in a form"):
            self.op(
                self.project,
                kanban,
                type="add_existing_field",
                field_name=name,
                target="//field[@name='email']",
                position="after",
            )

    def test_revert_drops_it(self):
        change = self.add(self.form)
        name = change.field_name
        self.project.action_apply()
        partner = self.env["res.partner"].create({"name": "Studio json"})
        partner.write({name: {"key": "value"}})
        report = self.project._studio_revert_report()
        fields_info = {
            (f["model"], f["name"]): f["filled"] for f in report["report"]["fields"]
        }
        self.assertEqual(fields_info[("res.partner", name)], 1)
        self.project.action_revert(digest=report["digest"])
        self.assertFalse(self.env["ir.model.fields"]._get("res.partner", name))
        self.assertNotIn(name, self.env["res.partner"]._fields)
