# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import base64
import os
from unittest import mock

from odoo.tests.common import TransactionCase

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class TestConstructionIntervenant(TransactionCase):
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

    def _run(self):
        with open(os.path.join(DATA_DIR, "Intervenants.csv"), "rb") as fh:
            file_b64 = base64.b64encode(fh.read())
        sync_model = self.env.ref(
            "erplibre_construction_qc_demo"
            ".sync_model_construction_doc_intervenant"
        )
        exec_rec = self.env["sync.data.exec"].create(
            {
                "name": "Intervenants.csv",
                "file": file_b64,
                "filename": "Intervenants.csv",
                "sync_model_ids": [(6, 0, sync_model.ids)],
            }
        )
        exec_rec.action_process_sync_data()
        exec_rec.action_process_transform({})
        return exec_rec

    def test_intervenants_create_partners(self):
        exec_rec = self._run()
        intervenants = self.env["construction.doc_intervenant"].search([])
        self.assertEqual(len(intervenants), 14)
        # The method_call bind now STAGES sync.data.transform.exec rows
        # (validation step); partners are not created until action_write_all().
        self.assertFalse(
            any(intervenants.mapped("partner_id")),
            "partners must be staged, not written before validation",
        )
        staged = self.env["sync.data.transform.exec"].search(
            [("sync_data_transform_id", "=", exec_rec.transform_id.id)]
        )
        self.assertTrue(
            staged.filtered(lambda r: r.to_model_name == "res.partner"),
            "res.partner creation should be staged",
        )
        # Validation step: apply the staged rows.
        exec_rec.transform_id.action_write_all()
        self.assertTrue(all(intervenants.mapped("partner_id")))
        partner = intervenants.filtered(
            lambda i: i.courriel
            == "jean.tremblay@constructions-aurora.example"
        ).partner_id
        self.assertEqual(partner.name, "Jean Tremblay")
        self.assertEqual(partner.function, "Contremaître")
