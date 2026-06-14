# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo.tests.common import TransactionCase


class TestConstructionAccountMove(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        journal = cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if journal:
            cls.income_account = journal.default_account_id or cls.env[
                "account.account"
            ].search([("account_type", "=", "income")], limit=1)
        else:
            cls.income_account = cls.env["account.account"].create(
                {
                    "name": "Revenu test",
                    "code": "TST4100",
                    "account_type": "income",
                }
            )
            cls.env["account.journal"].create(
                {
                    "name": "Ventes test",
                    "code": "TSALE",
                    "type": "sale",
                    "default_account_id": cls.income_account.id,
                }
            )

    def test_invoice_linked_to_chantier(self):
        project = self.env["project.project"].create(
            {"name": "Chantier Inv", "is_chantier": True}
        )
        partner = self.env["res.partner"].create({"name": "Client Inv"})
        order = self.env["sale.order"].create(
            {"partner_id": partner.id, "chantier_project_id": project.id}
        )
        product = self.env["product.product"].create(
            {"name": "Service chantier", "type": "service"}
        )
        sol = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "product_id": product.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Service chantier",
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.income_account.id,
                            "sale_line_ids": [(6, 0, [sol.id])],
                        },
                    )
                ],
            }
        )
        self.assertEqual(move.chantier_project_id, project)

    def test_invoice_without_chantier_is_empty(self):
        partner = self.env["res.partner"].create({"name": "Client X"})
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Ligne libre",
                            "quantity": 1.0,
                            "price_unit": 50.0,
                            "account_id": self.income_account.id,
                        },
                    )
                ],
            }
        )
        self.assertFalse(move.chantier_project_id)
