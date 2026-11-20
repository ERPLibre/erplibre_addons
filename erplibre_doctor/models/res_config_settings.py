# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, api, fields, models


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

    erplibre_doctor_daily = fields.Boolean(
        string="Daily analysis",
        help="The scheduled action « ERPLibre: doctor » runs an analysis "
        "every day.",
    )
    erplibre_doctor_notify_user_ids = fields.Many2many(
        "res.users",
        relation="erplibre_doctor_settings_notify_user_rel",
        column1="settings_id",
        column2="user_id",
        string="Notify",
        domain=[("share", "=", False)],
        help="Internal users who receive a message when the daily analysis "
        "finds a problem or is incomplete.",
    )

    def _erplibre_doctor_cron(self):
        return self.env.ref(
            "erplibre_doctor.ir_cron_erplibre_doctor", raise_if_not_found=False
        )

    @api.model
    def get_values(self):
        res = super().get_values()
        cron = self._erplibre_doctor_cron()
        users = self.env["erplibre.doctor.report"]._notify_users()
        res.update(
            erplibre_doctor_daily=bool(cron and cron.sudo().active),
            erplibre_doctor_notify_user_ids=[Command.set(users.ids)],
        )
        return res

    def set_values(self):
        super().set_values()
        self.env["erplibre.doctor.report"]._set_notify_users(
            self.erplibre_doctor_notify_user_ids
        )
        cron = self._erplibre_doctor_cron()
        if cron and cron.sudo().active != self.erplibre_doctor_daily:
            cron.sudo().active = self.erplibre_doctor_daily

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
