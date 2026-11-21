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


CATEGORY = "res.partner.category"
VAT = "//field[@name='vat']"
M_ORDER = "x_studio_test_m2o_order"
M_LINE = "x_studio_test_m2o_line"
LINES = "x_studio_test_line_ids"


@tagged("post_install", "-at_install")
class TestMany2oneInverse(StudioCase):
    """A new many2one may create a one2many on its comodel: the records of
    its model that point to a record, named and labelled after the model,
    renamed through the definition of the many2one until Apply."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_m2o_inverse")
        self.category_form = self.env.ref("base.view_partner_category_form")

    def add_sponsor(self, project=None, **field):
        return self.op(
            project or self.project,
            self.form,
            type="add_field",
            target=VAT,
            position="after",
            field={
                "ttype": "many2one",
                "field_description": "Sponsor",
                "relation": CATEGORY,
                **field,
            },
        )

    def update(self, name, **field):
        return self.op(
            self.project, self.form, type="update_field", field_name=name, field=field
        )

    def pending_models(self):
        """(order form, line form): the default forms of two models of the
        project, not created yet."""
        self.make_model(self.project, "Studio test order", model=M_ORDER)
        self.make_model(self.project, "Studio test line", model=M_LINE)
        pending = self.Editor._resolve_view
        return (
            pending(M_ORDER, False, "form", self.project),
            pending(M_LINE, False, "form", self.project),
        )

    def add_order(self, line_form):
        """The many2one « x_order » of the line to the order, with its
        inverse one2many on the order."""
        return self.op(
            self.project,
            line_form,
            type="add_field",
            target=LEFT,
            position="inside",
            field={
                "ttype": "many2one",
                "field_description": "Order",
                "relation": M_ORDER,
                "inverse_o2m": {"create": True},
            },
        )

    def show_inverse(self, order_form):
        return self.op(
            self.project,
            order_form,
            type="add_existing_field",
            target=LEFT,
            position="inside",
            field_name=LINES,
        )

    def test_the_inverse_is_a_field_of_the_comodel(self):
        change = self.add_sponsor(inverse_o2m={"create": True})
        self.assertEqual(change.field_name, "x_sponsor")
        self.assertEqual(
            change._payload()["field"]["inverse_o2m"],
            {
                "name": "x_contact_ids",
                "field_description": "Contact",
                "relation_field": "x_sponsor",
            },
        )
        definition, owner = self.project._studio_field_definitions(CATEGORY)[
            "x_contact_ids"
        ]
        self.assertEqual(owner, change)
        self.assertEqual(
            (
                definition["ttype"],
                definition["relation"],
                definition["relation_field"],
            ),
            ("one2many", "res.partner", "x_sponsor"),
        )
        # The comodel shows it, pending, its name not following a label.
        info = self.Editor._fields_payload(CATEGORY, self.project)["x_contact_ids"]
        self.assertTrue(info["pending"])
        self.assertFalse(info["name_auto"])
        sponsor = self.Editor._fields_payload("res.partner", self.project)["x_sponsor"]
        self.assertFalse(sponsor["inverse_protected"])
        self.assertIn(
            CATEGORY,
            [m["model"] for m in self.Editor._touched_models(self.project)],
        )
        # Its name is taken on the comodel, for this project and the others.
        self.assertIn("x_contact_ids", self.project._taken_field_names(CATEGORY))
        other = self.make_project("studio_test_m2o_other")
        owner = other._studio_field_name_owner(CATEGORY, "x_contact_ids")
        self.assertEqual(owner["kind"], "other")
        # The one2many comes after its many2one.
        order = [
            (model, name)
            for model, name, *_rest in self.project._studio_all_definitions()
        ]
        self.assertEqual(
            order, [("res.partner", "x_sponsor"), (CATEGORY, "x_contact_ids")]
        )

    def test_no_inverse_on_a_protected_model(self):
        with self.assertRaisesRegex(UserError, "does not add fields to res.users"):
            with self.env.cr.savepoint():
                self.add_sponsor(relation="res.users", inverse_o2m={"create": True})
        self.add_sponsor(relation="res.users")
        sponsor = self.Editor._fields_payload("res.partner", self.project)["x_sponsor"]
        self.assertTrue(sponsor["inverse_protected"])
        with self.assertRaisesRegex(UserError, "does not add fields to res.users"):
            with self.env.cr.savepoint():
                self.update("x_sponsor", inverse_o2m={"create": True})
        self.assertNotIn("inverse_o2m", self.project.change_ids._payload()["field"])

    def test_comodel_changes_once_the_inverse_is_removed(self):
        change = self.add_sponsor(inverse_o2m={"create": True})
        with self.assertRaisesRegex(UserError, "Remove the inverse field x_contact"):
            with self.env.cr.savepoint():
                self.update("x_sponsor", relation="res.country")
        self.update("x_sponsor", inverse_o2m=False)
        self.assertNotIn("inverse_o2m", change._payload()["field"])
        self.assertNotIn("x_contact_ids", self.project._taken_field_names(CATEGORY))
        self.update("x_sponsor", relation="res.country")
        definition = change._payload()["field"]
        self.assertEqual(definition["relation"], "res.country")
        # Added again, with a name and a label of its own; on_delete set.
        self.update(
            "x_sponsor",
            inverse_o2m={"name": "x_sponsored_ids", "field_description": "Sponsored"},
            on_delete="restrict",
        )
        definition = change._payload()["field"]
        self.assertEqual(definition["on_delete"], "restrict")
        self.assertEqual(
            definition["inverse_o2m"],
            {
                "name": "x_sponsored_ids",
                "field_description": "Sponsored",
                "relation_field": "x_sponsor",
            },
        )
        # A new label keeps the name.
        self.update(
            "x_sponsor",
            inverse_o2m={"name": "x_sponsored_ids", "field_description": "Godchildren"},
        )
        self.assertEqual(
            change._payload()["field"]["inverse_o2m"]["name"], "x_sponsored_ids"
        )

    def test_inverse_name_taken_on_the_comodel(self):
        for name, message in (
            ("contacts", "Prefix x_"),
            ("x_bad name", "Invalid format"),
            ("x_sponsor", "already exists"),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(UserError, message):
                with self.env.cr.savepoint():
                    self.add_sponsor(
                        relation="res.partner" if name == "x_sponsor" else CATEGORY,
                        inverse_o2m={"name": name},
                    )
        other = self.make_project("studio_test_m2o_other")
        self.op(
            other,
            self.category_form,
            type="add_field",
            target="//field[@name='name']",
            position="after",
            field={"ttype": "char", "field_description": "Contacts list"},
        )
        with self.assertRaisesRegex(UserError, "another project"):
            with self.env.cr.savepoint():
                self.add_sponsor(inverse_o2m={"name": "x_contacts_list"})
        self.assertFalse(self.project.change_ids)
        # The proposed name skips the names taken.
        self.add_sponsor(inverse_o2m={"field_description": "Contacts list"})
        self.assertEqual(
            self.project.change_ids._payload()["field"]["inverse_o2m"]["name"],
            "x_contacts_list_ids",
        )

    def test_apply_creates_both_and_revert_removes_both(self):
        self.add_sponsor(inverse_o2m={"create": True})
        self.project.action_apply()
        Fields = self.env["ir.model.fields"]
        sponsor = Fields._get("res.partner", "x_sponsor")
        contacts = Fields._get(CATEGORY, "x_contact_ids")
        self.assertEqual(
            (contacts.ttype, contacts.relation, contacts.relation_field),
            ("one2many", "res.partner", "x_sponsor"),
        )
        self.assertLess(sponsor.id, contacts.id)
        self.assertEqual(self.project.field_ids, sponsor | contacts)
        tag = self.env[CATEGORY].create({"name": "Studio test tag"})
        partner = self.env["res.partner"].create(
            {"name": "Studio test partner", "x_sponsor": tag.id}
        )
        self.assertEqual(tag.x_contact_ids, partner)
        # Applied: the inverse is neither removed nor renamed.
        for inverse in (False, {"name": "x_other_ids"}):
            with self.assertRaisesRegex(UserError, "only before Apply"):
                with self.env.cr.savepoint():
                    self.update("x_sponsor", inverse_o2m=inverse)
        with self.assertRaisesRegex(UserError, "once applied"):
            with self.env.cr.savepoint():
                self.op(
                    self.project,
                    self.category_form,
                    type="rename_field",
                    field_name="x_contact_ids",
                    new_name="x_other_ids",
                )
        self.project.action_revert()
        self.assertFalse(sponsor.exists())
        self.assertFalse(contacts.exists())

    def test_renaming_the_many2one_moves_the_inverse(self):
        change = self.add_sponsor(inverse_o2m={"create": True})
        self.op(
            self.project,
            self.form,
            type="rename_field",
            field_name="x_sponsor",
            new_name="x_godparent",
        )
        inverse = change._payload()["field"]["inverse_o2m"]
        self.assertEqual(inverse["relation_field"], "x_godparent")
        definition, _owner = self.project._studio_field_definitions(CATEGORY)[
            "x_contact_ids"
        ]
        self.assertEqual(definition["relation_field"], "x_godparent")

    def test_renaming_the_inverse_rewrites_its_many2one(self):
        order_form, line_form = self.pending_models()
        change = self.add_order(line_form)
        shown = self.show_inverse(order_form)
        self.op(
            self.project,
            order_form,
            type="rename_field",
            field_name=LINES,
            new_name="x_lines",
        )
        self.assertEqual(change._payload()["field"]["inverse_o2m"]["name"], "x_lines")
        self.assertEqual(shown.field_name, "x_lines")
        arch, errors = self.project._draft_arch(order_form)
        self.assertFalse(errors)
        self.assertTrue(arch.xpath(f"{LEFT}/field[@name='x_lines']"))
        check = self.Editor.check_field_name(
            self.project.id, M_ORDER, "x_lines", field_name="x_lines"
        )
        self.assertEqual((check["status"], check["proposed"]), ("available", LINES))
        # Back to the name its label proposes.
        self.op(
            self.project,
            order_form,
            type="rename_field",
            field_name="x_lines",
            auto=True,
        )
        self.assertEqual(change._payload()["field"]["inverse_o2m"]["name"], LINES)
        self.assertEqual(shown.field_name, LINES)
        with self.assertRaisesRegex(UserError, "Prefix x_"):
            self.op(
                self.project,
                order_form,
                type="rename_field",
                field_name=LINES,
                new_name="lines",
            )
        # The inverse many2one of a one2many is renamed the same way.
        others = self.op(
            self.project,
            order_form,
            type="add_field",
            target=LEFT,
            position="inside",
            field={
                "ttype": "one2many",
                "field_description": "Other lines",
                "relation": M_LINE,
                "inverse": {"create": True},
            },
        )
        old = others._payload()["field"]["relation_field"]
        self.op(
            self.project,
            line_form,
            type="rename_field",
            field_name=old,
            new_name="x_other_order",
        )
        definition = others._payload()["field"]
        self.assertEqual(
            (definition["relation_field"], definition["inverse_new"]["name"]),
            ("x_other_order", "x_other_order"),
        )

    def test_removing_the_many2one_removes_what_shows_the_inverse(self):
        order_form, line_form = self.pending_models()
        for leave in ("remove", "undo"):
            with self.subTest(leave=leave):
                self.add_order(line_form)
                self.show_inverse(order_form)
                self.assertEqual(len(self.project.change_ids), 2)
                if leave == "undo":
                    self.project.action_undo(line_form)
                else:
                    self.op(
                        self.project,
                        line_form,
                        type="remove",
                        target=f"{LEFT}/field[@name='x_order']",
                    )
                self.assertFalse(self.project.change_ids)
