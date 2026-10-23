# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Report lines of an import run."""

from odoo import fields, models

from ..dolibarr_site.messages import CODES


class DolibarrWebsiteImportLine(models.Model):
    _name = "dolibarr.website.import.line"
    _description = "Dolibarr website import report line"
    _order = "id"

    import_id = fields.Many2one(
        "dolibarr.website.import",
        required=True,
        ondelete="cascade",
        index=True,
    )
    severity = fields.Selection(
        [("info", "Information"), ("warning", "Warning"), ("error", "Error")],
        required=True,
        default="info",
    )
    code = fields.Selection([(code, code) for code in CODES], required=True)
    phase = fields.Selection(
        [("analyse", "Analysis"), ("import", "Import")], default="analyse"
    )
    page_ref = fields.Char()
    lang = fields.Char()
    url = fields.Char()
    message = fields.Char()
    detail = fields.Char(size=300)
    res_model = fields.Char()
    res_id = fields.Many2oneReference(model_field="res_model")

    def action_open(self):
        """Form of the record that the line concerns; False when the
        line concerns no record (site-level lines, most codes)."""
        self.import_id._check_import_access()
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
        }
