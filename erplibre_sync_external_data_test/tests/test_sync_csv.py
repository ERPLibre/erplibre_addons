# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo.tests.common import TransactionCase


class TestMirrorModel(TransactionCase):
    def test_model_exists(self):
        self.assertIn("erplibre.sync.test.entry", self.env)

    def test_required_fields_exist(self):
        model = self.env["erplibre.sync.test.entry"]
        for field in [
            "project_code",
            "client_name",
            "client_email",
            "opportunity_name",
            "amount",
            "expected_date",
            "file_no_line",
            "partner_id",
            "crm_lead_id",
            "sale_order_id",
            "project_id",
            "invoice_id",
        ]:
            self.assertIn(field, model._fields, f"Missing field: {field}")


class TestFileField(TransactionCase):
    def test_file_field_on_sync_data_exec(self):
        field = self.env["sync.data.exec"]._fields.get("file")
        self.assertIsNotNone(field, "Field 'file' missing on sync.data.exec")
        self.assertEqual(field.type, "binary")


class TestTransformMethod(TransactionCase):
    def test_action_transform_test_entries_exists(self):
        self.assertTrue(
            hasattr(
                self.env["sync.data.transform"],
                "action_transform_test_entries",
            )
        )
