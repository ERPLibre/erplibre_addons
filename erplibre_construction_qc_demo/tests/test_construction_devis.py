# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import base64
import os
from unittest import mock

from odoo.tests.common import TransactionCase

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class TestConstructionDevis(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env = self.env(
            context=dict(self.env.context, queue_job__no_delay=True)
        )
        self.env.cr.commit = lambda: None
        patcher = mock.patch(
            "odoo.addons.mail.tools.mail_validation.mail_validate",
            return_value=True,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # Fresh DB has no sale journal; account.move not needed here, but a
        # sale.order confirm is not triggered, so no journal is required.

    def test_devis_method_call_creates_lead_and_order(self):
        with open(os.path.join(DATA_DIR, "Devis.csv"), "rb") as fh:
            file_b64 = base64.b64encode(fh.read())
        sync_model = self.env.ref(
            "erplibre_construction_qc_demo.sync_model_construction_doc_devis"
        )
        exec_rec = self.env["sync.data.exec"].create(
            {
                "name": "Devis.csv",
                "file": file_b64,
                "filename": "Devis.csv",
                "sync_model_ids": [(6, 0, sync_model.ids)],
            }
        )
        exec_rec.action_process_sync_data()
        devis = self.env["construction.doc_devis"].search([])
        self.assertEqual(len(devis), 12)
        # The method_call bind now STAGES sync.data.transform.exec rows
        # (validation step); nothing is written until action_write_all().
        exec_rec.action_process_transform({})
        dev1 = devis.filtered(lambda d: d.numero_devis == "DEV-001")
        self.assertFalse(
            dev1.partner_id, "must be staged, not written before validation"
        )
        staged = self.env["sync.data.transform.exec"].search(
            [("sync_data_transform_id", "=", exec_rec.transform_id.id)]
        )
        self.assertTrue(staged, "transform should stage exec rows")
        self.assertTrue(
            staged.filtered(lambda r: r.to_model_name == "crm.lead"),
            "crm.lead creation should be staged",
        )
        # Validation step: apply the staged rows.
        exec_rec.transform_id.action_write_all()
        self.assertTrue(dev1.partner_id)
        self.assertTrue(dev1.crm_lead_id)
        self.assertTrue(dev1.sale_order_id)
        self.assertEqual(len(dev1.sale_order_id.order_line), 2)
