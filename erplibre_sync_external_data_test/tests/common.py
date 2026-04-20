# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import base64
import os

import orjson
from odoo.tests.common import TransactionCase

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

SYNC_METADATA = {
    "index_line_header": 0,
    "nb_line_header": 1,
    "header": [
        ["Code projet", "project_code"],
        ["Nom client", "client_name"],
        ["Courriel client", "client_email"],
        ["Opportunité", "opportunity_name"],
        ["Montant", "amount"],
        ["Date prévue", "expected_date"],
        # file_no_line is intentionally absent: the extraction engine appends it
        # automatically as ("File no line", "file_no_line") for every sync.
    ],
    "sync": ["project_code"],
    "bind": [
        {
            "bind_field_reverse": "crm_lead_id",
            "method_call": "action_transform_test_entries",
            "order_lines": [
                {
                    "product_name": "Services conseil",
                    "qty": 10,
                    "price_unit": 150.0,
                },
                {
                    "product_name": "Formation",
                    "qty": 2,
                    "price_unit": 500.0,
                },
            ],
        }
    ],
}


def load_file_b64(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read())


class SyncTestBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mirror_model = "erplibre.sync.test.entry"
        cls._ensure_sale_journal()

    @classmethod
    def _ensure_sale_journal(cls):
        if cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", cls.env.company.id)], limit=1
        ):
            return
        # Fresh DB without demo data has no chart of accounts; create the minimum
        # needed so account.move.create() can find a sale journal.
        revenue_account = cls.env["account.account"].create(
            {"name": "Revenue", "code": "TST4000", "account_type": "income"}
        )
        cls.env["account.journal"].create(
            {
                "name": "Customer Invoices (test)",
                "code": "STEST",
                "type": "sale",
                "default_account_id": revenue_account.id,
            }
        )

    def setUp(self):
        super().setUp()
        # _link_tracking_values in the parent module calls env.cr.commit()
        # which is forbidden inside TransactionCase (raises AssertionError).
        # Replace with no-op for test isolation.
        self.env.cr.commit = lambda: None

    def _make_sync_model(self, filetype, sheet_name=""):
        metadata = dict(SYNC_METADATA)
        metadata["filetype"] = filetype
        # xlsx uses 1-based row numbering; CSV uses 0-based (engine applies index -= 1)
        metadata["index_line_header"] = 1 if filetype == "xlsx" else 0
        if sheet_name:
            metadata["sheet_name"] = sheet_name
        return self.env["sync.model"].create(
            {
                "name": f"Test {filetype.upper()}",
                "model_name": self.mirror_model,
                "spreadsheet_extraction_metadata": orjson.dumps(metadata).decode(),
            }
        )

    def _make_sync_exec(self, sync_model, file_b64):
        return self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [sync_model.id])],
                "file": file_b64,
            }
        )

    def _entries_from(self, sync_exec):
        return self.env[self.mirror_model].search(
            [("id", "in", sync_exec.sync_data_create_ids.mapped("res_id"))]
        )

    def _assert_all_entities_linked(self, entries):
        for entry in entries:
            self.assertTrue(entry.partner_id, f"{entry.project_code}: missing partner")
            self.assertTrue(
                entry.crm_lead_id, f"{entry.project_code}: missing crm.lead"
            )
            self.assertTrue(
                entry.sale_order_id, f"{entry.project_code}: missing sale.order"
            )
            self.assertTrue(entry.project_id, f"{entry.project_code}: missing project")
            self.assertTrue(entry.invoice_id, f"{entry.project_code}: missing invoice")
