# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo.tests.common import TransactionCase

from .common import SyncTestBase, load_file_b64


# ---------------------------------------------------------------------------
# Infrastructure tests (Tasks 3, 4, 5)
# ---------------------------------------------------------------------------


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
            hasattr(self.env["sync.data.transform"], "action_transform_test_entries")
        )


# ---------------------------------------------------------------------------
# Scenario A — CSV, 1 line
# ---------------------------------------------------------------------------


class TestCsvSingleLine(SyncTestBase):
    """CSV single-line scenario: one project creates all Odoo entities."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls._make_sync_model(cls, filetype="csv")
        cls.file_b64 = load_file_b64("test_single.csv")

    def test_extraction_creates_one_entry(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        self.assertEqual(len(self._entries_from(se)), 1)

    def test_extraction_state_is_summary(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        self.assertEqual(se.state, "summary")

    def test_extraction_create_count(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        self.assertEqual(se.create_count, 1)

    def test_extraction_project_code(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        entry = self._entries_from(se)
        self.assertEqual(entry.project_code, "PROJ-001")

    def test_extraction_client_name(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        entry = self._entries_from(se)
        self.assertEqual(entry.client_name, "Acme Corp")

    def test_extraction_amount(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        entry = self._entries_from(se)
        self.assertAlmostEqual(entry.amount, 50000.0, places=2)

    def test_upsert_no_duplicate_on_rerun(self):
        se1 = self._make_sync_exec(self.sync_model, self.file_b64)
        se1.action_process_sync_data()
        se2 = self._make_sync_exec(self.sync_model, self.file_b64)
        se2.action_process_sync_data()
        count = self.env[self.mirror_model].search_count(
            [("project_code", "=", "PROJ-001")]
        )
        self.assertEqual(count, 1)

    def test_transform_creates_all_entities(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        self._assert_all_entities_linked(entries)

    def test_transform_partner_email(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entry = self._entries_from(se)
        self.assertEqual(entry.partner_id.email, "acme@example.com")

    def test_transform_crm_lead_name(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entry = self._entries_from(se)
        self.assertEqual(entry.crm_lead_id.name, "Système ERP")

    def test_transform_crm_lead_revenue(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entry = self._entries_from(se)
        self.assertAlmostEqual(entry.crm_lead_id.expected_revenue, 50000.0, places=2)

    def test_transform_sale_order_ref(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entry = self._entries_from(se)
        self.assertEqual(entry.sale_order_id.client_order_ref, "PROJ-001")

    def test_transform_invoice_origin(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entry = self._entries_from(se)
        self.assertEqual(entry.invoice_id.invoice_origin, "PROJ-001")
        self.assertEqual(entry.invoice_id.move_type, "out_invoice")

    def test_transform_idempotent(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        se.action_process_transform({})
        count = self.env["res.partner"].search_count(
            [("email", "=", "acme@example.com")]
        )
        self.assertEqual(count, 1)


# ---------------------------------------------------------------------------
# Scenario B — CSV, multi-line, shared contact
# ---------------------------------------------------------------------------


class TestCsvMultiLine(SyncTestBase):
    """CSV multi-line scenario: 3 projects share the same contact."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls._make_sync_model(cls, filetype="csv")
        cls.file_b64 = load_file_b64("test_multi.csv")

    def test_extraction_creates_three_entries(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        self.assertEqual(len(self._entries_from(se)), 3)

    def test_extraction_all_project_codes_present(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        codes = self._entries_from(se).mapped("project_code")
        self.assertIn("PROJ-002", codes)
        self.assertIn("PROJ-003", codes)
        self.assertIn("PROJ-004", codes)

    def test_transform_creates_three_leads(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        self.assertEqual(len(entries.mapped("crm_lead_id")), 3)

    def test_transform_shared_partner(self):
        """All 3 mirror records must share a single res.partner (same email)."""
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        partner_ids = entries.mapped("partner_id").ids
        self.assertEqual(
            len(set(partner_ids)),
            1,
            f"Expected 1 shared partner, got {len(set(partner_ids))}",
        )

    def test_transform_only_one_partner_created(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        count = self.env["res.partner"].search_count(
            [("email", "=", "tech@example.com")]
        )
        self.assertEqual(count, 1)

    def test_transform_three_sale_orders(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        self.assertEqual(len(entries.mapped("sale_order_id")), 3)

    def test_transform_three_projects(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        self.assertEqual(len(entries.mapped("project_id")), 3)

    def test_transform_three_invoices(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        self.assertEqual(len(entries.mapped("invoice_id")), 3)

    def test_transform_all_invoices_out_invoice(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        for entry in entries:
            self.assertEqual(entry.invoice_id.move_type, "out_invoice")

    def test_transform_partner_linked_to_all_entities(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        self._assert_all_entities_linked(entries)
        shared_partner = entries[0].partner_id
        for entry in entries:
            self.assertEqual(entry.crm_lead_id.partner_id, shared_partner)
            self.assertEqual(entry.sale_order_id.partner_id, shared_partner)
            self.assertEqual(entry.invoice_id.partner_id, shared_partner)
