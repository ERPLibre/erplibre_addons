# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import base64
import os
from unittest import mock

from odoo.tests.common import TransactionCase

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _b64(filename):
    with open(os.path.join(DATA_DIR, filename), "rb") as fh:
        return base64.b64encode(fh.read())


class TestConstructionSync(TransactionCase):
    def setUp(self):
        super().setUp()
        # Run the transform inline (queue_job is server_wide) and avoid
        # the env.cr.commit done by _link_tracking_values + the live DNS
        # MX lookup in crm.lead email validation. (Phase 0 lessons.)
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

    def _run(self, filename, sync_xmlid):
        sync_model = self.env.ref(sync_xmlid)
        exec_rec = self.env["sync.data.exec"].create(
            {
                "name": filename,
                "file": _b64(filename),
                "filename": filename,
                "sync_model_ids": [(6, 0, sync_model.ids)],
            }
        )
        exec_rec.action_process_sync_data()
        return exec_rec

    def test_xlsx_soumission_import_and_bind(self):
        self._run(
            "Suivi-Chantiers.xlsx",
            "erplibre_construction_qc_demo"
            ".sync_model_construction_doc_soumission",
        )
        soumissions = self.env["construction.doc_soumission"].search([])
        self.assertEqual(len(soumissions), 15)
        sou1 = soumissions.filtered(lambda s: s.numero_soumission == "SOU-001")
        self.assertEqual(
            sou1.nom_chantier, "Réfection pont de la Rivière-aux-Cailloux"
        )
        self.assertTrue(sou1.actif)
        self.assertFalse(
            soumissions.filtered(
                lambda s: s.numero_soumission == "SOU-002"
            ).actif
        )
        # Coordonnée géographique importée puis parsée en lat/lon
        # (prête pour une carte Leaflet).
        self.assertEqual(sou1.coordonnees_gps, "45.5017, -73.5673")
        self.assertAlmostEqual(sou1.latitude, 45.5017, places=4)
        self.assertAlmostEqual(sou1.longitude, -73.5673, places=4)
        self.assertTrue(
            all(soumissions.mapped("coordonnees_gps")),
            "chaque soumission doit avoir une coordonnée",
        )

    def test_csv_facture_import(self):
        self._run(
            "Factures.csv",
            "erplibre_construction_qc_demo"
            ".sync_model_construction_doc_facture",
        )
        factures = self.env["construction.doc_facture"].search([])
        self.assertEqual(len(factures), 22)
        self.assertEqual(
            factures.filtered(
                lambda f: f.no_facture == "FAC-001"
            ).numero_soumission,
            "SOU-001",
        )

    def test_transform_creates_chantier(self):
        exec_rec = self._run(
            "Suivi-Chantiers.xlsx",
            "erplibre_construction_qc_demo"
            ".sync_model_construction_doc_soumission",
        )
        exec_rec.action_process_transform({})
        # The declarative bind_field_model path stages sync.data.transform.exec
        # rows (dry run); action_write_all applies them. (The method_call path
        # would create directly, but this example uses the declarative bind.)
        exec_rec.transform_id.action_write_all()
        projects = self.env["project.project"].search(
            [("is_chantier", "=", True)]
        )
        self.assertTrue(projects)
        # The bind sets no_chantier from code_projet (is_sync key).
        self.assertIn("CH-2026-01", projects.mapped("no_chantier"))
        # Each imported soumission is linked back via project_id.
        linked = self.env["construction.doc_soumission"].search(
            [("project_id", "!=", False)]
        )
        self.assertEqual(len(linked), 15)
