# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import json

from odoo import api, fields, models


class SyncDataTransform(models.Model):
    _inherit = "sync.data.transform"

    context_name = fields.Selection(
        selection_add=[
            ("QC-CONSTRUCTION - update", "QC construction - update")
        ],
        ondelete={"QC-CONSTRUCTION - update": "set null"},
    )

    @api.depends("context_name")
    def _compute_context_name(self):
        super()._compute_context_name()
        for rec in self:
            if (
                rec.context_name == "QC-CONSTRUCTION - update"
                and not rec.default_option_no_match
            ):
                rec.default_option_no_match = json.dumps(
                    {"ignore_associate_chantier": True}
                )

    def _stage_exec(self, vals):
        """Create one sync.data.transform.exec staging row attached to this
        transform. The row is NOT applied here: action_write_all() materializes
        it later (resolving #REPLACE.<token> dependencies), which is the
        validation step the method_call binds must go through (same staging
        the declarative bind_field_model path uses)."""
        vals.setdefault("sync_data_transform_id", self.id)
        return self.env["sync.data.transform.exec"].create([vals])

    def action_transform_construction_devis(
        self,
        mirror_ids,
        model_name,
        bind_config,
        bind_field_reverse,
        metadata,
        do_link=False,
    ):
        """Stage res.partner + crm.lead + sale.order(+lines) creation and the
        devis back-links as sync.data.transform.exec rows instead of creating
        directly. Chained records reference their parents through the parent
        row's id_depend_name (#REPLACE token); action_write_all() resolves the
        tokens and writes everything in dependency order."""
        self.ensure_one()
        order_lines_cfg = bind_config.get("order_lines", [])
        lead_field = bind_field_reverse or "crm_lead_id"
        product_rows = {}
        for entry in mirror_ids:
            if entry.partner_id and entry.crm_lead_id and entry.sale_order_id:
                continue
            partner_row = self._stage_exec(
                {
                    "from_model_name": model_name,
                    "from_id_ref": entry.id,
                    "to_model_name": "res.partner",
                    "method": "create",
                    "modification_json": {
                        "name": entry.client_name,
                        "email": entry.client_email,
                    },
                    "associate_key": "res.partner.create.%s"
                    % (entry.client_email or entry.numero_devis),
                }
            )
            lead_row = self._stage_exec(
                {
                    "from_model_name": model_name,
                    "from_id_ref": entry.id,
                    "to_model_name": "crm.lead",
                    "method": "create",
                    "modification_json": {
                        "name": entry.nom_chantier or entry.numero_devis,
                        "partner_id": partner_row.id_depend_name,
                        "type": "opportunity",
                        "expected_revenue": entry.montant,
                    },
                    "depend_ids": [(6, 0, partner_row.ids)],
                    "associate_key": "crm.lead.create.%s" % entry.numero_devis,
                }
            )
            order_row = self._stage_exec(
                {
                    "from_model_name": model_name,
                    "from_id_ref": entry.id,
                    "to_model_name": "sale.order",
                    "method": "create",
                    "modification_json": {
                        "partner_id": partner_row.id_depend_name,
                        "client_order_ref": entry.numero_devis,
                    },
                    "depend_ids": [(6, 0, partner_row.ids)],
                    "associate_key": "sale.order.create.%s"
                    % entry.numero_devis,
                }
            )
            for line in order_lines_cfg:
                pname = line["product_name"]
                prod_row = product_rows.get(pname)
                if not prod_row:
                    prod_row = self._stage_exec(
                        {
                            "to_model_name": "product.product",
                            "method": "create",
                            "modification_json": {
                                "name": pname,
                                "type": "service",
                                "list_price": line.get("price_unit", 0.0),
                            },
                            "associate_key": "product.product.create.%s"
                            % pname,
                        }
                    )
                    product_rows[pname] = prod_row
                self._stage_exec(
                    {
                        "from_model_name": model_name,
                        "from_id_ref": entry.id,
                        "to_model_name": "sale.order.line",
                        "method": "create",
                        "modification_json": {
                            "order_id": order_row.id_depend_name,
                            "product_id": prod_row.id_depend_name,
                            "product_uom_qty": line.get("qty", 1.0),
                            "price_unit": line.get("price_unit", 0.0),
                        },
                        "depend_ids": [(6, 0, (order_row + prod_row).ids)],
                    }
                )
            self._stage_exec(
                {
                    "from_model_name": model_name,
                    "from_id_ref": entry.id,
                    "to_model_name": model_name,
                    "to_id_ref": entry.id,
                    "method": "write",
                    "modification_json": {
                        "partner_id": partner_row.id_depend_name,
                        lead_field: lead_row.id_depend_name,
                        "sale_order_id": order_row.id_depend_name,
                    },
                    "depend_ids": [
                        (6, 0, (partner_row + lead_row + order_row).ids)
                    ],
                    "associate_key": "%s.write.%s"
                    % (model_name, entry.numero_devis),
                }
            )

    def action_transform_construction_intervenant(
        self,
        mirror_ids,
        model_name,
        bind_config,
        bind_field_reverse,
        metadata,
        do_link=False,
    ):
        """Stage res.partner creation (deduped by email) + the partner_id
        back-link as sync.data.transform.exec rows instead of writing directly.
        An existing partner is linked through a staged write; a new one is
        staged as a create row that the back-link write depends on via its
        #REPLACE token. action_write_all() applies the staged rows."""
        self.ensure_one()
        partner_field = bind_field_reverse or "partner_id"
        pending = {}  # email -> staged res.partner create row (this batch)
        for entry in mirror_ids:
            if entry.partner_id:
                continue
            existing = self.env["res.partner"]
            if entry.courriel:
                existing = existing.search(
                    [("email", "=", entry.courriel)], limit=1
                )
            if existing:
                self._stage_exec(
                    {
                        "from_model_name": model_name,
                        "from_id_ref": entry.id,
                        "to_model_name": model_name,
                        "to_id_ref": entry.id,
                        "method": "write",
                        "modification_json": {partner_field: existing.id},
                        "associate_key": "%s.write.%s.%s"
                        % (
                            model_name,
                            partner_field,
                            entry.courriel or entry.id,
                        ),
                    }
                )
                continue
            partner_row = (
                pending.get(entry.courriel) if entry.courriel else None
            )
            if not partner_row:
                partner_row = self._stage_exec(
                    {
                        "from_model_name": model_name,
                        "from_id_ref": entry.id,
                        "to_model_name": "res.partner",
                        "method": "create",
                        "modification_json": {
                            "name": entry.nom,
                            "email": entry.courriel,
                            "function": entry.role,
                        },
                        "associate_key": "res.partner.create.%s"
                        % (entry.courriel or entry.nom or entry.id),
                    }
                )
                if entry.courriel:
                    pending[entry.courriel] = partner_row
            self._stage_exec(
                {
                    "from_model_name": model_name,
                    "from_id_ref": entry.id,
                    "to_model_name": model_name,
                    "to_id_ref": entry.id,
                    "method": "write",
                    "modification_json": {
                        partner_field: partner_row.id_depend_name
                    },
                    "depend_ids": [(6, 0, partner_row.ids)],
                    "associate_key": "%s.write.%s.%s"
                    % (model_name, partner_field, entry.courriel or entry.id),
                }
            )

    def action_match_chantier_tickets(self):
        """Fan out one queue_job worker per ticket to match it to a chantier
        by its no_chantier appearing in the ticket text. Simplified vs the
        helpdesk_fci PDF/queue_job pipeline (text-only)."""
        self.ensure_one()
        tickets = self.env["helpdesk.ticket"].search(
            [
                ("ignore_associate_chantier", "=", False),
                ("chantier_project_id", "=", False),
            ]
        )
        chantiers = self.env["project.project"].search(
            [("is_chantier", "=", True), ("no_chantier", "!=", False)]
        )
        no_chantiers = chantiers.mapped("no_chantier")
        for ticket in tickets:
            self.with_delay()._match_one_ticket(ticket.id, no_chantiers)

    def _match_one_ticket(self, ticket_id, no_chantiers):
        ticket = self.env["helpdesk.ticket"].browse(ticket_id)
        if not ticket.exists():
            return
        text = " ".join(filter(None, [ticket.name, ticket.description or ""]))
        for no_chantier in no_chantiers:
            if no_chantier and no_chantier in text:
                ticket.chantier_project_id = self.env[
                    "project.project"
                ].search([("no_chantier", "=", no_chantier)], limit=1)
                break
