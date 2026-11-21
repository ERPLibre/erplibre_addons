# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import sql

from .common import StudioCase

VAT = "//field[@name='vat']"


@tagged("post_install", "-at_install")
class TestFieldOptions(StudioCase):
    """The options of a new field set before Apply: translatable, indexed,
    maximum size."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_field_options")

    def add(self, **field):
        return self.op(
            self.project,
            self.form,
            type="add_field",
            target=VAT,
            position="after",
            field={"field_description": "Studio option", **field},
        )

    def update(self, name, **field):
        return self.op(
            self.project, self.form, type="update_field", field_name=name, field=field
        )

    def test_options_by_type(self):
        for field in (
            {"ttype": "integer", "translate": True},
            {"ttype": "text", "size": 20},
            {"ttype": "html", "index": True},
            {"ttype": "many2many", "relation": "res.partner.category", "index": True},
            {"ttype": "char", "size": -1},
            {"ttype": "char", "size": 10001},
            {"ttype": "char", "size": "big"},
            {"ttype": "char", "size": True},
            {"ttype": "char", "translate": True, "index": True},
        ):
            with self.subTest(field=field), self.assertRaises(UserError):
                self.add(**field)
        self.assertFalse(self.project.change_ids)
        change = self.add(ttype="char", translate=True, size="25")
        self.assertEqual(
            {k: change._payload()["field"].get(k) for k in ("translate", "size")},
            {"translate": True, "size": 25},
        )
        change = self.add(ttype="integer", index=True, translate=False, size=0)
        definition = change._payload()["field"]
        self.assertTrue(definition["index"])
        self.assertNotIn("translate", definition)
        self.assertNotIn("size", definition)

    def test_apply_writes_options(self):
        change = self.add(ttype="char", translate=True, size=30)
        indexed = self.add(
            ttype="char", field_description="Studio code", index=True, size=12
        )
        self.project.action_apply()
        Fields = self.env["ir.model.fields"]
        field = Fields._get("res.partner", change.field_name)
        self.assertEqual((field.translate, field.index, field.size), (True, False, 30))
        registry_field = self.env["res.partner"]._fields[change.field_name]
        self.assertTrue(registry_field.translate)
        self.assertEqual(registry_field.size, 30)
        field = Fields._get("res.partner", indexed.field_name)
        self.assertEqual((field.translate, field.index, field.size), (False, True, 12))
        self.assertTrue(self.env["res.partner"]._fields[indexed.field_name].index)
        # The column: a varchar of 12, under an index.
        self.env.cr.execute(
            """SELECT character_maximum_length FROM information_schema.columns
                WHERE table_name = 'res_partner' AND column_name = %s""",
            [indexed.field_name],
        )
        self.assertEqual(self.env.cr.fetchone()[0], 12)
        index = sql.make_index_name("res_partner", indexed.field_name)
        self.assertTrue(sql.index_exists(self.env.cr, index))

    def test_frozen_after_apply(self):
        change = self.add(ttype="char", size=30)
        name = change.field_name
        self.update(name, index=True, size=40)
        self.assertEqual(change._payload()["field"]["size"], 40)
        self.project.action_apply()
        for values in ({"translate": True}, {"index": False}, {"size": 50}):
            with self.subTest(values=values):
                with self.assertRaisesRegex(UserError, "before Apply only"):
                    self.update(name, **values)
        self.update(name, field_description="Studio renamed", help="A tooltip")
        definition = change._payload()["field"]
        self.assertEqual(
            (definition["field_description"], definition["help"]),
            ("Studio renamed", "A tooltip"),
        )
        self.assertEqual((definition["index"], definition["size"]), (True, 40))
        self.project.action_apply()
        field = self.env["ir.model.fields"]._get("res.partner", name)
        self.assertEqual(
            (field.field_description, field.index, field.size),
            ("Studio renamed", True, 40),
        )

    def test_old_payload_unchanged(self):
        change = self.add(ttype="char")
        definition = change._payload()["field"]
        for key in ("translate", "index", "size"):
            self.assertNotIn(key, definition)
        self.project.action_apply()
        field = self.env["ir.model.fields"]._get("res.partner", change.field_name)
        self.assertEqual((field.translate, field.index, field.size), (False, False, 0))
        log = []
        self.project._apply_fields(log)
        self.assertEqual([line for line in log if line.endswith(": updated")], [])
