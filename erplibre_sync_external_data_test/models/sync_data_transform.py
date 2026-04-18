from odoo import models


class SyncDataTransform(models.Model):
    _inherit = "sync.data.transform"

    def action_transform_test_entries(
        self, mirror_ids, model_name, bind_config, bind_field_reverse, do_link=False
    ):
        for entry in mirror_ids:
            partner = self._test_get_or_create_partner(entry)
            entry.partner_id = partner

            if not entry.crm_lead_id:
                entry.crm_lead_id = self._test_create_lead(entry, partner)

            if not entry.sale_order_id:
                entry.sale_order_id = self._test_create_sale_order(
                    entry, partner, entry.crm_lead_id
                )

            if not entry.project_id:
                entry.project_id = self._test_create_project(entry, partner)

            if not entry.invoice_id:
                entry.invoice_id = self._test_create_invoice(entry, partner)

    def _test_get_or_create_partner(self, entry):
        if entry.partner_id:
            return entry.partner_id
        partner = self.env["res.partner"].search(
            [("email", "=", entry.client_email)], limit=1
        )
        if not partner:
            partner = self.env["res.partner"].create(
                {"name": entry.client_name, "email": entry.client_email}
            )
        return partner

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

    def _test_create_sale_order(self, entry, partner, lead):
        vals = {
            "partner_id": partner.id,
            "client_order_ref": entry.project_code,
        }
        if "opportunity_id" in self.env["sale.order"]._fields:
            vals["opportunity_id"] = lead.id
        return self.env["sale.order"].create(vals)

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
