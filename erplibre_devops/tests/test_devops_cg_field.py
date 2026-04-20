# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsCgField(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module = cls.env["devops.cg.module"].create(
            {"name": "test_module"}
        )
        cls.model = cls.env["devops.cg.model"].create(
            {
                "name": "test.model",
                "module_id": cls.module.id,
            }
        )

    def _create_field(self, vals):
        defaults = {"model_id": self.model.id, "name": "test_field"}
        defaults.update(vals)
        return self.env["devops.cg.field"].create(defaults)

    # ── Type defaults ──

    def test_default_type_is_char(self):
        field = self._create_field({})
        self.assertEqual(field.type, "char")

    def test_default_sequence(self):
        field = self._create_field({})
        self.assertEqual(field.sequence, 10)

    # ── Error detection: relational fields ──

    def test_many2one_without_relation_has_error(self):
        field = self._create_field({"name": "partner_id", "type": "many2one"})
        self.assertTrue(field.has_error)
        self.assertIn("Missing relation", field.has_error_msg)

    def test_many2one_with_relation_no_error(self):
        other_model = self.env["devops.cg.model"].create(
            {"name": "other.model", "module_id": self.module.id}
        )
        field = self._create_field(
            {
                "name": "partner_id",
                "type": "many2one",
                "relation": other_model.id,
            }
        )
        self.assertFalse(field.has_error)

    def test_many2one_with_relation_manual_no_error(self):
        field = self._create_field(
            {
                "name": "partner_id",
                "type": "many2one",
                "relation_manual": "res.partner",
            }
        )
        self.assertFalse(field.has_error)

    def test_many2many_without_relation_has_error(self):
        field = self._create_field(
            {"name": "tag_ids", "type": "many2many"}
        )
        self.assertTrue(field.has_error)

    def test_many2many_with_relation_no_error(self):
        other_model = self.env["devops.cg.model"].create(
            {"name": "tag.model", "module_id": self.module.id}
        )
        field = self._create_field(
            {
                "name": "tag_ids",
                "type": "many2many",
                "relation": other_model.id,
            }
        )
        self.assertFalse(field.has_error)

    def test_one2many_without_relation_has_error(self):
        field = self._create_field(
            {"name": "line_ids", "type": "one2many"}
        )
        self.assertTrue(field.has_error)

    def test_one2many_without_inverse_has_error(self):
        other_model = self.env["devops.cg.model"].create(
            {"name": "line.model", "module_id": self.module.id}
        )
        field = self._create_field(
            {
                "name": "line_ids",
                "type": "one2many",
                "relation": other_model.id,
            }
        )
        self.assertTrue(field.has_error)

    def test_one2many_with_relation_and_inverse_no_error(self):
        other_model = self.env["devops.cg.model"].create(
            {"name": "line.model2", "module_id": self.module.id}
        )
        inverse_field = self.env["devops.cg.field"].create(
            {
                "name": "parent_id",
                "type": "many2one",
                "model_id": other_model.id,
                "relation": self.model.id,
            }
        )
        field = self._create_field(
            {
                "name": "line_ids",
                "type": "one2many",
                "relation": other_model.id,
                "field_relation": inverse_field.id,
            }
        )
        self.assertFalse(field.has_error)

    def test_one2many_with_manual_inverse_no_error(self):
        other_model = self.env["devops.cg.model"].create(
            {"name": "line.model3", "module_id": self.module.id}
        )
        field = self._create_field(
            {
                "name": "line_ids",
                "type": "one2many",
                "relation": other_model.id,
                "field_relation_manual": "parent_id",
            }
        )
        self.assertFalse(field.has_error)

    # ── Error detection: monetary ──

    def test_monetary_without_currency_has_error(self):
        field = self._create_field(
            {"name": "amount", "type": "monetary"}
        )
        self.assertTrue(field.has_error)
        self.assertIn("Missing currency_field", field.has_error_msg)

    def test_monetary_with_currency_no_error(self):
        field = self._create_field(
            {
                "name": "amount",
                "type": "monetary",
                "currency_field": "currency_id",
            }
        )
        self.assertFalse(field.has_error)

    # ── No error for non-relational types ──

    def test_char_field_no_error(self):
        field = self._create_field({"name": "title", "type": "char"})
        self.assertFalse(field.has_error)

    def test_boolean_field_no_error(self):
        field = self._create_field({"name": "active", "type": "boolean"})
        self.assertFalse(field.has_error)

    def test_integer_field_no_error(self):
        field = self._create_field({"name": "count", "type": "integer"})
        self.assertFalse(field.has_error)

    def test_text_field_no_error(self):
        field = self._create_field({"name": "description", "type": "text"})
        self.assertFalse(field.has_error)

    def test_date_field_no_error(self):
        field = self._create_field({"name": "start_date", "type": "date"})
        self.assertFalse(field.has_error)

    def test_html_field_no_error(self):
        field = self._create_field({"name": "body", "type": "html"})
        self.assertFalse(field.has_error)

    def test_json_field_no_error(self):
        field = self._create_field({"name": "data", "type": "json"})
        self.assertFalse(field.has_error)

    # ── get_dct() ──

    def test_get_dct_basic_char(self):
        field = self._create_field({"name": "title", "type": "char"})
        dct = field.get_dct()
        self.assertEqual(dct["ttype"], "char")
        self.assertNotIn("relation", dct)

    def test_get_dct_with_help(self):
        field = self._create_field(
            {"name": "desc", "type": "char", "help": "A description"}
        )
        dct = field.get_dct()
        self.assertEqual(dct["help"], "A description")

    def test_get_dct_with_string(self):
        field = self._create_field(
            {"name": "desc", "type": "char", "string": "Description"}
        )
        dct = field.get_dct()
        self.assertEqual(dct["field_description"], "Description")

    def test_get_dct_with_compute(self):
        field = self._create_field(
            {
                "name": "full_name",
                "type": "char",
                "compute_method": "_compute_full_name",
            }
        )
        dct = field.get_dct()
        self.assertEqual(dct["compute"], "_compute_full_name")

    def test_get_dct_with_tracking(self):
        field = self._create_field(
            {"name": "status", "type": "char", "tracking": True}
        )
        dct = field.get_dct()
        self.assertTrue(dct["tracking"])

    def test_get_dct_many2one_with_relation(self):
        other_model = self.env["devops.cg.model"].create(
            {"name": "res.partner", "module_id": self.module.id}
        )
        field = self._create_field(
            {
                "name": "partner_id",
                "type": "many2one",
                "relation": other_model.id,
            }
        )
        dct = field.get_dct()
        self.assertEqual(dct["ttype"], "many2one")
        self.assertEqual(dct["relation"], "res.partner")

    def test_get_dct_many2one_with_relation_manual(self):
        field = self._create_field(
            {
                "name": "partner_id",
                "type": "many2one",
                "relation_manual": "res.partner",
            }
        )
        dct = field.get_dct()
        self.assertEqual(dct["relation"], "res.partner")

    def test_get_dct_one2many_with_inverse(self):
        other_model = self.env["devops.cg.model"].create(
            {"name": "sale.line", "module_id": self.module.id}
        )
        inverse_field = self.env["devops.cg.field"].create(
            {
                "name": "order_id",
                "type": "many2one",
                "model_id": other_model.id,
                "relation": self.model.id,
            }
        )
        field = self._create_field(
            {
                "name": "line_ids",
                "type": "one2many",
                "relation": other_model.id,
                "field_relation": inverse_field.id,
            }
        )
        dct = field.get_dct()
        self.assertEqual(dct["ttype"], "one2many")
        self.assertEqual(dct["relation"], "sale.line")
        self.assertEqual(dct["relation_field"], "order_id")

    def test_get_dct_one2many_with_manual_inverse(self):
        other_model = self.env["devops.cg.model"].create(
            {"name": "sale.line2", "module_id": self.module.id}
        )
        field = self._create_field(
            {
                "name": "line_ids",
                "type": "one2many",
                "relation": other_model.id,
                "field_relation_manual": "order_id",
            }
        )
        dct = field.get_dct()
        self.assertEqual(dct["relation_field"], "order_id")

    def test_get_dct_monetary_with_currency(self):
        field = self._create_field(
            {
                "name": "amount",
                "type": "monetary",
                "currency_field": "currency_id",
            }
        )
        dct = field.get_dct()
        self.assertEqual(dct["ttype"], "monetary")
        self.assertEqual(dct["currency_field"], "currency_id")

    def test_get_dct_sequence_in_output(self):
        field = self._create_field(
            {"name": "test_f", "type": "char", "sequence": 25}
        )
        dct = field.get_dct()
        self.assertEqual(dct["code_generator_list_view_sequence"], 25)

    def test_get_dct_precompute(self):
        field = self._create_field(
            {
                "name": "cached",
                "type": "char",
                "precompute": True,
                "compute_method": "_compute_cached",
            }
        )
        dct = field.get_dct()
        self.assertTrue(dct["precompute"])

    # ── All 16 field types can be created ──

    def test_all_field_types_creatable(self):
        types = [
            "char", "boolean", "integer", "float", "text", "html",
            "datetime", "date", "selection", "binary", "monetary",
            "many2one", "many2onereference", "many2many", "one2many",
            "json",
        ]
        for i, ftype in enumerate(types):
            field = self._create_field(
                {"name": f"field_{ftype}_{i}", "type": ftype}
            )
            self.assertEqual(field.type, ftype)
