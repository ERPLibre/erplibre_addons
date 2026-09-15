# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    no_chantier = fields.Char(string="No chantier", tracking=True)
    is_chantier = fields.Boolean(string="Is chantier", tracking=True)
    doc_soumission_ids = fields.One2many(
        comodel_name="construction.doc_soumission",
        inverse_name="project_id",
    )
    doc_facture_ids = fields.One2many(
        comodel_name="construction.doc_facture",
        inverse_name="project_id",
    )

    company_currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_company_currency_id",
    )
    montant_soumis_total = fields.Monetary(
        compute="_compute_chantier_totals",
        currency_field="company_currency_id",
    )
    montant_paye_total = fields.Monetary(
        compute="_compute_chantier_totals",
        currency_field="company_currency_id",
    )
    chantier_analyze = fields.Text(compute="_compute_chantier_totals")

    @api.depends_context("company")
    def _compute_company_currency_id(self):
        for rec in self:
            rec.company_currency_id = rec.env.company.currency_id

    @api.depends("doc_soumission_ids.montant", "doc_facture_ids.montant_paye")
    def _compute_chantier_totals(self):
        for rec in self:
            rec.montant_soumis_total = sum(
                rec.doc_soumission_ids.mapped("montant")
            )
            rec.montant_paye_total = sum(
                rec.doc_facture_ids.mapped("montant_paye")
            )
            rec.chantier_analyze = "%s soumission(s), %s facture(s)" % (
                len(rec.doc_soumission_ids),
                len(rec.doc_facture_ids),
            )
