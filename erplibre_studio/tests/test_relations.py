# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import sql

from .. import arch as studio_arch
from .common import StudioCase

MODULE = "studio_test_relations"
ORDER = "x_studio_test_order"
LINE = "x_studio_test_line"
LEFT = "//group[@name='studio_left']"


@tagged("post_install", "-at_install")
class TestRelations(StudioCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.order = self.make_model(self.project, "Studio test order", model=ORDER)
        self.line = self.make_model(self.project, "Studio test line", model=LINE)

    def apply_models(self):
        self.project.action_apply()
        return (
            self.order._studio_views()["form"],
            self.line._studio_views()["form"],
        )

    def add(self, view, target=LEFT, position="inside", **field):
        return self.op(
            self.project,
            view,
            type="add_field",
            target=target,
            position=position,
            field=field,
        )

    def fields_of(self, model):
        return self.env["ir.model.fields"].search([("model", "=", model)])

    def test_one2many_with_a_new_inverse(self):
        order_form, _line_form = self.apply_models()
        change = self.add(
            order_form,
            ttype="one2many",
            field_description="Lines",
            relation=LINE,
            inverse={"create": True},
        )
        payload = change._payload()
        definition = payload["field"]
        self.assertEqual(
            (definition["relation"], definition["relation_field"]),
            (LINE, "x_studio_test_order_id"),
        )
        self.assertEqual(
            definition["inverse_new"],
            {
                "name": "x_studio_test_order_id",
                "field_description": "Studio test order",
                "on_delete": "cascade",
            },
        )
        self.assertEqual(
            payload["node_children"],
            [
                {
                    "tag": "list",
                    "attrs": {"editable": "bottom"},
                    "children": [{"tag": "field", "attrs": {"name": "x_name"}}],
                }
            ],
        )
        arch = self.draft(self.project, order_form)
        self.assertTrue(arch.xpath(f"{LEFT}/field[@name='x_lines']/list/field"))
        # The comodel offers the inverse before Apply.
        choices = self.Editor.get_relation_choices(
            self.project.id, ORDER, LINE, "one2many"
        )
        self.assertIn(
            "x_studio_test_order_id", [c["name"] for c in choices["inverses"]]
        )
        self.assertEqual(choices["inverse_name"], "x_studio_test_order_id_2")
        self.project.action_apply()
        inverse = self.env["ir.model.fields"]._get(LINE, "x_studio_test_order_id")
        self.assertEqual(
            (inverse.ttype, inverse.relation, inverse.on_delete),
            ("many2one", ORDER, "cascade"),
        )
        lines = self.env["ir.model.fields"]._get(ORDER, "x_lines")
        self.assertEqual(
            (lines.ttype, lines.relation, lines.relation_field),
            ("one2many", LINE, "x_studio_test_order_id"),
        )
        self.assertEqual(self.project.field_ids, inverse | lines)
        record = self.env[ORDER].create(
            {
                "x_name": "First",
                "x_lines": [
                    Command.create({"x_name": "A"}),
                    Command.create({"x_name": "B"}),
                ],
            }
        )
        items = record.x_lines
        self.assertEqual(len(items), 2)
        view = etree.fromstring(self.env[ORDER].get_view(order_form.id, "form")["arch"])
        self.assertTrue(
            view.xpath("//field[@name='x_lines']/list/field[@name='x_name']")
        )
        record.unlink()
        self.assertFalse(items.exists())
        # Removed: the one2many, then its inverse, in this order.
        self.op(
            self.project,
            order_form,
            type="remove",
            target=f"{LEFT}/field[@name='x_lines']",
        )
        self.assertFalse(self.project._project_field_changes())
        self.project.action_apply()
        self.assertFalse(self.env["ir.model.fields"]._get(ORDER, "x_lines"))
        self.assertFalse(
            self.env["ir.model.fields"]._get(LINE, "x_studio_test_order_id")
        )

    def test_one2many_with_an_existing_inverse(self):
        order_form, line_form = self.apply_models()
        with self.assertRaisesRegex(UserError, "x_order"):
            with self.env.cr.savepoint():
                self.add(
                    order_form,
                    ttype="one2many",
                    field_description="Lines",
                    relation=LINE,
                    relation_field="x_order",
                )
        self.add(
            line_form,
            ttype="many2one",
            field_description="Order",
            relation=ORDER,
            on_delete="cascade",
        )
        change = self.add(
            order_form,
            ttype="one2many",
            field_description="Lines",
            relation=LINE,
            relation_field="x_order",
        )
        self.assertNotIn("inverse_new", change._payload()["field"])
        # The relation of an x2many does not change once in the draft.
        with self.assertRaisesRegex(UserError, "relation"):
            with self.env.cr.savepoint():
                self.op(
                    self.project,
                    order_form,
                    type="update_field",
                    field_name="x_lines",
                    field={"relation_field": "x_other"},
                )
        self.project.action_apply()
        order = self.env["ir.model.fields"]._get(LINE, "x_order")
        self.assertEqual(order.on_delete, "cascade")
        self.assertEqual(
            self.env["ir.model.fields"]._get(ORDER, "x_lines").relation_field, "x_order"
        )
        # Removed, the one2many leaves; the many2one it showed stays.
        self.op(
            self.project,
            order_form,
            type="remove",
            target=f"{LEFT}/field[@name='x_lines']",
        )
        self.project.action_apply()
        self.assertFalse(self.env["ir.model.fields"]._get(ORDER, "x_lines"))
        self.assertTrue(self.env["ir.model.fields"]._get(LINE, "x_order"))

    def test_inverse_taken_by_another_one2many(self):
        order_form, _line_form = self.apply_models()
        self.add(
            order_form,
            ttype="one2many",
            field_description="Lines",
            relation=LINE,
            inverse={"create": True},
        )
        self.add(
            order_form,
            ttype="one2many",
            field_description="Other lines",
            relation=LINE,
            relation_field="x_studio_test_order_id",
        )
        with self.assertRaisesRegex(UserError, "x_other_lines"):
            with self.env.cr.savepoint():
                self.op(
                    self.project,
                    order_form,
                    type="remove",
                    target=f"{LEFT}/field[@name='x_lines']",
                )
        self.project.action_apply()
        self.assertEqual(
            self.env[ORDER]._fields["x_other_lines"].inverse_name,
            "x_studio_test_order_id",
        )

    def test_one2many_to_an_existing_model(self):
        order_form, _line_form = self.apply_models()
        change = self.add(
            order_form,
            ttype="one2many",
            field_description="Contacts",
            relation="res.partner",
            inverse={"create": True, "field_description": "Studio order"},
        )
        inverse = change._payload()["field"]["inverse_new"]
        self.assertEqual(
            (inverse["name"], inverse["on_delete"], inverse["field_description"]),
            ("x_studio_test_order_id", "set null", "Studio order"),
        )
        with self.assertRaisesRegex(UserError, "res.users"):
            with self.env.cr.savepoint():
                self.add(
                    order_form,
                    ttype="one2many",
                    field_description="Users",
                    relation="res.users",
                    inverse={"create": True},
                )
        # A one2many shows in a form only.
        with self.assertRaisesRegex(UserError, "form only"):
            with self.env.cr.savepoint():
                self.add(
                    self.list,
                    target="//field[@name='email']",
                    position="after",
                    ttype="one2many",
                    field_description="Orders",
                    relation=ORDER,
                    inverse={"create": True},
                )
        self.project.action_apply()
        field = self.env["ir.model.fields"]._get(
            "res.partner", "x_studio_test_order_id"
        )
        self.assertEqual((field.relation, field.on_delete), (ORDER, "set null"))
        # The new fields of the project on the partner show in its editor.
        fields_info = self.Editor.get_editor_data(
            "res.partner", False, "form", self.project.id
        )["fields"]
        self.assertTrue(fields_info["x_studio_test_order_id"]["project"])

    def test_many2many(self):
        order_form, _line_form = self.apply_models()
        names = self.Editor.get_relation_choices(
            self.project.id, ORDER, LINE, "many2many", "Tags"
        )
        change = self.add(
            order_form, ttype="many2many", field_description="Tags", relation=LINE
        )
        definition = change._payload()["field"]
        table = f"x_{MODULE}_studio_test_order_tags_rel"
        self.assertEqual(
            (
                definition["relation_table"],
                definition["column1"],
                definition["column2"],
            ),
            (table, f"{ORDER}_id", f"{LINE}_id"),
        )
        self.assertEqual(
            names,
            {
                "relation_table": table,
                "column1": f"{ORDER}_id",
                "column2": f"{LINE}_id",
            },
        )
        self.assertEqual(
            change._payload()["node_children"][0]["children"][0]["attrs"]["name"],
            "x_name",
        )
        # From an existing model, in a list: tags; the client names nothing.
        partner = self.add(
            self.list,
            target="//field[@name='email']",
            position="after",
            ttype="many2many",
            field_description="Orders",
            relation=ORDER,
            relation_table="x_studio_test_forced_rel",
        )
        payload = partner._payload()
        self.assertEqual(payload["node_attrs"], {"widget": "many2many_tags"})
        self.assertEqual(
            payload["field"]["relation_table"], f"x_{MODULE}_res_partner_orders_rel"
        )
        self.assertEqual(payload["field"]["column1"], "res_partner_id")
        self.project.action_apply()
        tags = self.env["ir.model.fields"]._get(ORDER, "x_tags")
        self.assertEqual(
            (tags.relation_table, tags.column1, tags.column2),
            (table, f"{ORDER}_id", f"{LINE}_id"),
        )
        self.assertTrue(sql.table_exists(self.env.cr, table))
        line = self.env[LINE].create({"x_name": "Tag"})
        order = self.env[ORDER].create({"x_name": "Order", "x_tags": [(4, line.id)]})
        self.assertEqual(order.x_tags, line)
        report = self.project._studio_revert_report()["report"]
        self.assertIn(table, report["tables"])
        self.op(
            self.project,
            order_form,
            type="remove",
            target=f"{LEFT}/field[@name='x_tags']",
        )
        self.project.action_apply()
        self.assertFalse(sql.table_exists(self.env.cr, table))

    def test_many2many_names(self):
        table, column1, column2 = studio_arch.many2many_names(
            "studio_test_relations", ORDER, ORDER, "x_parents", set()
        )
        self.assertEqual(
            (table, column1, column2),
            ("x_studio_test_relations_studio_test_order_parents_rel", "id1", "id2"),
        )
        taken = {table}
        again, _c1, _c2 = studio_arch.many2many_names(
            "studio_test_relations", ORDER, ORDER, "x_parents", taken
        )
        self.assertEqual(
            again, "x_studio_test_relations_studio_test_order_parents_2_rel"
        )
        long_table, _c1, _c2 = studio_arch.many2many_names(
            "studio_test_a_very_long_module_name",
            "x_" + "b" * 45,
            "res.partner",
            "x_" + "c" * 40,
            set(),
        )
        self.assertTrue(long_table.startswith("x_studio_test_a_very_long_"))
        self.assertNotIn("b" * 10, long_table)
        self.assertLessEqual(len(long_table), studio_arch.TABLE_NAME_SIZE)

    def test_the_inverse_leaves_with_its_one2many(self):
        """Undo, or removing the node of a one2many whose inverse the studio
        creates, takes the changes that show that inverse with it: they
        could no longer apply. On a pending view, a change of a field the
        model will not have is an error of the draft."""
        pending = self.Editor._resolve_view
        for leave in ("undo", "remove"):
            with self.subTest(leave=leave):
                order_form = pending(ORDER, False, "form", self.project)
                line_form = pending(LINE, False, "form", self.project)
                self.add(
                    order_form,
                    ttype="one2many",
                    field_description="Lines",
                    relation=LINE,
                    inverse={"create": True},
                )
                self.op(
                    self.project,
                    line_form,
                    type="add_existing_field",
                    target=LEFT,
                    position="inside",
                    field_name="x_studio_test_order_id",
                )
                self.assertEqual(len(self.project.change_ids), 2)
                if leave == "undo":
                    self.project.action_undo(order_form)
                else:
                    self.op(
                        self.project,
                        order_form,
                        type="remove",
                        target=f"{LEFT}/field[@name='x_lines']",
                    )
                self.assertFalse(self.project.change_ids)
        change = self.env["erplibre.studio.change"].create(
            {
                "project_id": self.project.id,
                "change_type": "add_existing_field",
                "model": LINE,
                "model_line_id": self.line.id,
                "view_type": "form",
                "xpath": LEFT,
                "position": "inside",
                "payload": '{"field_name": "x_studio_test_order_id"}',
            }
        )
        _arch, errors = self.project._draft_arch(line_form)
        self.assertIn("x_studio_test_order_id", errors[change.id])

    def test_the_relation_comes_from_the_server(self):
        """What a payload rewritten over RPC says of a relation is checked
        again: the inverse of a one2many on a model of the database never
        deletes its records in cascade; a many2many never writes into a
        table of the database."""
        order_form, _line_form = self.apply_models()
        change = self.add(
            order_form,
            ttype="one2many",
            field_description="Contacts",
            relation="res.partner",
            inverse={"create": True},
        )
        payload = change._payload()
        payload["field"]["inverse_new"]["on_delete"] = "cascade"
        change._set_payload(payload)
        inverse = self.project._studio_inverse_definition(ORDER, payload["field"])
        self.assertEqual(inverse[1]["on_delete"], "set null")
        tags = self.add(
            order_form, ttype="many2many", field_description="Tags", relation=LINE
        )
        payload = tags._payload()
        # The table of a model.
        payload["field"]["relation_table"] = LINE
        tags._set_payload(payload)
        with self.assertRaisesRegex(UserError, f"{LINE} is not a valid relation table"):
            with self.env.cr.savepoint():
                self.project.action_apply()
        payload["field"]["relation_table"] = f"x_{MODULE}_studio_test_order_tags_rel"
        payload["field"]["column2"] = payload["field"]["column1"]
        tags._set_payload(payload)
        with self.assertRaisesRegex(UserError, "not a valid relation table"):
            with self.env.cr.savepoint():
                self.project.action_apply()
        self.project.action_undo(order_form)
        self.project.action_apply()
        field = self.env["ir.model.fields"]._get(
            "res.partner", "x_studio_test_order_id"
        )
        self.assertEqual(field.on_delete, "set null")
