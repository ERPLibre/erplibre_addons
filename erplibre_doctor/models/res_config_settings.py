# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    erplibre_doctor_report_id = fields.Many2one(
        "erplibre.doctor.report",
        string="Last doctor report",
        compute="_compute_erplibre_doctor",
    )
    erplibre_doctor_summary = fields.Char(
        string="Doctor summary", compute="_compute_erplibre_doctor"
    )

    @api.model
    def _erplibre_status(self):
        """Adds the last report and its summary, read from the database."""
        status = super()._erplibre_status()
        report = self.env["erplibre.doctor.report"].search([], limit=1)
        if not report:
            summary = self.env._("No analysis yet.")
        elif report.state == "error":
            summary = self.env._("The last analysis is incomplete.")
        elif report.problem_count:
            summary = self.env._(
                "Problems found by the last analysis: %(count)s.",
                count=report.problem_count,
            )
        else:
            summary = self.env._("Every suggested module is installed.")
        status.update(
            erplibre_doctor_report_id=report.id or False,
            erplibre_doctor_summary=summary,
        )
        return status

    def _compute_erplibre_doctor(self):
        self._erplibre_assign(
            ["erplibre_doctor_report_id", "erplibre_doctor_summary"]
        )

    def action_erplibre_doctor_start(self):
        return self.env["erplibre.doctor.report"].action_new_analysis()

    def action_erplibre_doctor_open_report(self):
        report = self.env["erplibre.doctor.report"].search([], limit=1)
        if not report:
            return self.action_erplibre_doctor_open_reports()
        return report._action_open_form()

    def action_erplibre_doctor_open_reports(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "erplibre_doctor.erplibre_doctor_report_action"
        )
