# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import models


class SyncDataTransform(models.Model):
    _inherit = "sync.data.transform"

    def action_transform_test_entries(
        self, mirror_ids, model_name, bind_config, bind_field_reverse, do_link=False
    ):
        order_lines_cfg = bind_config.get("order_lines", [])
        for entry in mirror_ids:
            partner = self._test_get_or_create_partner(entry)
            entry.partner_id = partner

            if not entry.crm_lead_id:
                entry.crm_lead_id = self._test_create_lead(entry, partner)

            if not entry.sale_order_id:
                entry.sale_order_id = self._test_create_sale_order(
                    entry, partner, entry.crm_lead_id, order_lines_cfg
                )

            if not entry.project_id:
                entry.project_id = self._test_create_project(entry, partner)

            if not entry.invoice_id:
                entry.invoice_id = self._test_create_invoice(entry, partner)

    def _test_get_or_create_partner(self, entry):
        if entry.partner_id:
            return entry.partner_id
        return self._transform_find_or_create(
            "res.partner",
            [("email", "=", entry.client_email)],
            {"name": entry.client_name, "email": entry.client_email},
        )

    def _test_get_or_create_product(self, product_name, price_unit=0.0):
        return self._transform_find_or_create(
            "product.product",
            [("name", "=", product_name)],
            {"name": product_name, "type": "service", "list_price": price_unit},
        )

    def _test_create_lead(self, entry, partner):
        vals = {
            "name": entry.opportunity_name or entry.project_code,
            "partner_id": partner.id,
            "expected_revenue": entry.amount,
            "type": "opportunity",
        }
        if entry.expected_date:
            vals["date_deadline"] = entry.expected_date
        return self.env["crm.lead"].create(vals)

    def _test_create_sale_order(self, entry, partner, lead, order_lines_cfg=None):
        vals = {
            "partner_id": partner.id,
            "client_order_ref": entry.project_code,
        }
        if "opportunity_id" in self.env["sale.order"]._fields:
            vals["opportunity_id"] = lead.id
        order = self.env["sale.order"].create(vals)
        for line_cfg in order_lines_cfg or []:
            product = self._test_get_or_create_product(
                line_cfg["product_name"], line_cfg.get("price_unit", 0.0)
            )
            self.env["sale.order.line"].create(
                {
                    "order_id": order.id,
                    "product_id": product.id,
                    "product_uom_qty": line_cfg.get("qty", 1.0),
                    "price_unit": line_cfg.get("price_unit", 0.0),
                }
            )
        return order

    def _test_create_project(self, entry, partner):
        return self.env["project.project"].create(
            {
                "name": entry.opportunity_name or entry.project_code,
                "partner_id": partner.id,
            }
        )

    def _test_create_invoice(self, entry, partner):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "invoice_origin": entry.project_code,
            }
        )
