# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsCgModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module = cls.env["devops.cg.module"].create(
            {"name": "test_module"}
        )

    def _create_model(self, vals=None):
        defaults = {"name": "test.model", "module_id": self.module.id}
        if vals:
            defaults.update(vals)
        return self.env["devops.cg.model"].create(defaults)

    # ── Defaults ──

    def test_default_active(self):
        model = self._create_model()
        self.assertTrue(model.active)

    def test_default_sequence(self):
        model = self._create_model()
        self.assertEqual(model.sequence, 10)

    def test_default_booleans_false(self):
        model = self._create_model()
        self.assertFalse(model.is_inherit)
        self.assertFalse(model.is_activity)
        self.assertFalse(model.is_all_tracking)
        self.assertFalse(model.is_to_remove)
        self.assertFalse(model.is_method_compute_company_currency_id)

    # ── Error propagation from fields ──

    def test_no_fields_no_error(self):
        model = self._create_model()
        self.assertFalse(model.has_error)
        self.assertEqual(model.has_error_msg, "")

    def test_field_with_error_propagates_to_model(self):
        model = self._create_model()
        self.env["devops.cg.field"].create(
            {
                "name": "bad_field",
                "type": "many2one",
                "model_id": model.id,
            }
        )
        self.assertTrue(model.has_error)
        self.assertIn("bad_field", model.has_error_msg)
        self.assertIn("many2one", model.has_error_msg)

    def test_multiple_field_errors_aggregated(self):
        model = self._create_model()
        self.env["devops.cg.field"].create(
            {
                "name": "field_a",
                "type": "many2one",
                "model_id": model.id,
            }
        )
        self.env["devops.cg.field"].create(
            {
                "name": "field_b",
                "type": "monetary",
                "model_id": model.id,
            }
        )
        self.assertTrue(model.has_error)
        self.assertIn("field_a", model.has_error_msg)
        self.assertIn("field_b", model.has_error_msg)

    def test_valid_fields_no_error(self):
        model = self._create_model()
        self.env["devops.cg.field"].create(
            {
                "name": "title",
                "type": "char",
                "model_id": model.id,
            }
        )
        self.env["devops.cg.field"].create(
            {
                "name": "count",
                "type": "integer",
                "model_id": model.id,
            }
        )
        self.assertFalse(model.has_error)

    def test_error_clears_when_field_fixed(self):
        model = self._create_model()
        field = self.env["devops.cg.field"].create(
            {
                "name": "partner_id",
                "type": "many2one",
                "model_id": model.id,
            }
        )
        self.assertTrue(model.has_error)
        # Fix the field by adding a relation
        other_model = self._create_model({"name": "res.partner"})
        field.write({"relation": other_model.id})
        self.assertFalse(model.has_error)

    # ── get_field_dct() ──

    def test_get_field_dct_empty(self):
        model = self._create_model()
        dct = model.get_field_dct()
        self.assertEqual(dct, {})

    def test_get_field_dct_with_fields(self):
        model = self._create_model()
        self.env["devops.cg.field"].create(
            {
                "name": "title",
                "type": "char",
                "model_id": model.id,
                "help": "Title help",
            }
        )
        self.env["devops.cg.field"].create(
            {
                "name": "active",
                "type": "boolean",
                "model_id": model.id,
            }
        )
        dct = model.get_field_dct()
        self.assertIn("title", dct)
        self.assertIn("active", dct)
        self.assertEqual(dct["title"]["ttype"], "char")
        self.assertEqual(dct["title"]["help"], "Title help")
        self.assertEqual(dct["active"]["ttype"], "boolean")

    # ── Cascade delete ──

    def test_fields_deleted_on_model_delete(self):
        model = self._create_model()
        field = self.env["devops.cg.field"].create(
            {
                "name": "test_f",
                "type": "char",
                "model_id": model.id,
            }
        )
        field_id = field.id
        model.unlink()
        self.assertFalse(
            self.env["devops.cg.field"].search([("id", "=", field_id)])
        )
