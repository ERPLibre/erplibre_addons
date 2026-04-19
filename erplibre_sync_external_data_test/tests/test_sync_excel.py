# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from .common import SyncTestBase, load_file_b64

SHEET = "Données"


# ---------------------------------------------------------------------------
# Scenario A — Excel, 1 line
# ---------------------------------------------------------------------------


class TestExcelSingleLine(SyncTestBase):
    """Excel single-line scenario: one project creates all Odoo entities."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls._make_sync_model(cls, filetype="xlsx", sheet_name=SHEET)
        cls.file_b64 = load_file_b64("test_single.xlsx")

    def test_extraction_creates_one_entry(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        self.assertEqual(len(self._entries_from(se)), 1)

    def test_extraction_project_code(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        self.assertEqual(self._entries_from(se).project_code, "PROJ-001")

    def test_extraction_amount(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        self.assertAlmostEqual(self._entries_from(se).amount, 50000.0, places=2)

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
        self._assert_all_entities_linked(self._entries_from(se))

    def test_transform_crm_lead_name(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        self.assertEqual(self._entries_from(se).crm_lead_id.name, "Système ERP")

    def test_transform_invoice_is_out_invoice(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        self.assertEqual(self._entries_from(se).invoice_id.move_type, "out_invoice")

    def test_excel_same_data_as_csv(self):
        """Excel must extract the same field values as the equivalent CSV row."""
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        entry = self._entries_from(se)
        self.assertEqual(entry.client_name, "Acme Corp")
        self.assertEqual(entry.client_email, "acme@example.com")
        self.assertAlmostEqual(entry.amount, 50000.0, places=2)


# ---------------------------------------------------------------------------
# Scenario B — Excel, multi-line, shared contact
# ---------------------------------------------------------------------------


class TestExcelMultiLine(SyncTestBase):
    """Excel multi-line scenario: 3 projects share the same contact."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls._make_sync_model(cls, filetype="xlsx", sheet_name=SHEET)
        cls.file_b64 = load_file_b64("test_multi.xlsx")

    def test_extraction_creates_three_entries(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        self.assertEqual(len(self._entries_from(se)), 3)

    def test_transform_shared_partner(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        entries = self._entries_from(se)
        partner_ids = set(entries.mapped("partner_id").ids)
        self.assertEqual(len(partner_ids), 1)

    def test_transform_only_one_partner_in_db(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        count = self.env["res.partner"].search_count(
            [("email", "=", "tech@example.com")]
        )
        self.assertEqual(count, 1)

    def test_transform_three_leads(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        self.assertEqual(len(self._entries_from(se).mapped("crm_lead_id")), 3)

    def test_transform_all_entities_linked(self):
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        se.action_process_transform({})
        self._assert_all_entities_linked(self._entries_from(se))

    def test_excel_multi_same_as_csv_multi(self):
        """Excel multi must extract the same project codes as the equivalent CSV."""
        se = self._make_sync_exec(self.sync_model, self.file_b64)
        se.action_process_sync_data()
        xlsx_codes = set(self._entries_from(se).mapped("project_code"))
        self.assertEqual(xlsx_codes, {"PROJ-002", "PROJ-003", "PROJ-004"})
