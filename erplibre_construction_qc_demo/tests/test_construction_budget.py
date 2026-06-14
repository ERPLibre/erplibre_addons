# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo.tests.common import TransactionCase


class TestConstructionBudget(TransactionCase):
    def test_chantier_totals(self):
        project = self.env["project.project"].create(
            {"name": "Chantier X", "is_chantier": True}
        )
        self.env["construction.doc_soumission"].create(
            [
                {
                    "numero_soumission": "S1",
                    "montant": 1000.0,
                    "project_id": project.id,
                },
                {
                    "numero_soumission": "S2",
                    "montant": 2500.0,
                    "project_id": project.id,
                },
            ]
        )
        self.env["construction.doc_facture"].create(
            {
                "no_facture": "F1",
                "montant_paye": 400.0,
                "project_id": project.id,
            }
        )
        self.assertEqual(project.montant_soumis_total, 3500.0)
        self.assertEqual(project.montant_paye_total, 400.0)
        self.assertIn("2 soumission", project.chantier_analyze)
        self.assertTrue(project.company_currency_id)
