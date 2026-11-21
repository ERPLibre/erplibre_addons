# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ErplibreStudioRevertWizard(models.TransientModel):
    """The confirmation of Revert, or of an Apply that removes data, from
    the project form: the report of what leaves the database, and its
    digest, which the action compares with the report it computes again."""

    _name = "erplibre.studio.revert.wizard"
    _description = "ERPLibre studio confirmation of what leaves the database"

    project_id = fields.Many2one(
        "erplibre.studio.project", required=True, ondelete="cascade"
    )
    mode = fields.Selection(
        [("revert", "Revert"), ("apply", "Apply")], required=True, default="revert"
    )
    report_html = fields.Html(string="Report", readonly=True)
    digest = fields.Char(readonly=True)
    refused = fields.Char(readonly=True)

    def action_confirm(self):
        self.ensure_one()
        if self.mode == "apply":
            result = self.project_id.action_apply(digest=self.digest)
        else:
            result = self.project_id.action_revert(digest=self.digest)
        if isinstance(result, dict):
            return result
        return {"type": "ir.actions.act_window_close"}
