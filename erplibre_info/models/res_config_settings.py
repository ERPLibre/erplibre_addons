# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from .. import runner
from .erplibre_code_run import PARAM_PERIODIC, PARAM_STARTUP
from .erplibre_code_snapshot import PARAM_DIRTY


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    erplibre_snapshot_on_startup = fields.Boolean(
        string="Snapshot at server start",
        config_parameter=PARAM_STARTUP,
        help="Queue one snapshot each time the server starts. It runs in "
        "the background, after the registry is loaded.",
    )
    erplibre_snapshot_periodic = fields.Boolean(
        string="Periodic snapshot",
        config_parameter=PARAM_PERIODIC,
        help="Activate the cron that takes a snapshot at each interval. A "
        "snapshot is stored only when the code changed.",
    )
    erplibre_snapshot_interval_number = fields.Integer(
        string="Snapshot every", default=1
    )
    erplibre_snapshot_interval_type = fields.Selection(
        [("hours", "Hours"), ("days", "Days"), ("weeks", "Weeks")],
        string="Snapshot interval unit",
        default="days",
    )
    erplibre_snapshot_check_dirty = fields.Boolean(
        string="Check modified trees",
        config_parameter=PARAM_DIRTY,
        help="Also run git status in every clone: slower, and shows "
        "uncommitted changes.",
    )
    erplibre_last_snapshot_id = fields.Many2one(
        "erplibre.code.snapshot",
        string="Last ERPLibre snapshot",
        compute="_compute_erplibre_last_snapshot",
    )
    erplibre_last_snapshot_date = fields.Datetime(
        related="erplibre_last_snapshot_id.date",
        string="Last ERPLibre snapshot date",
    )
    erplibre_version = fields.Char(
        related="erplibre_last_snapshot_id.erplibre_version",
        string="ERPLibre version",
    )
    erplibre_commit = fields.Char(
        related="erplibre_last_snapshot_id.erplibre_commit",
        string="ERPLibre commit",
    )
    erplibre_mode = fields.Selection(
        related="erplibre_last_snapshot_id.mode", string="ERPLibre mode"
    )
    erplibre_state_summary = fields.Char(
        related="erplibre_last_snapshot_id.state_summary",
        string="ERPLibre repositories",
    )
    erplibre_pending_update_count = fields.Integer(
        related="erplibre_last_snapshot_id.pending_update_count",
        string="ERPLibre modules to upgrade",
    )
    erplibre_server_actions_allowed = fields.Boolean(
        compute="_compute_erplibre_server_actions_allowed"
    )
    erplibre_last_failed_run_id = fields.Many2one(
        "erplibre.code.run",
        string="Last failed ERPLibre snapshot",
        compute="_compute_erplibre_last_snapshot",
    )
    erplibre_last_failed_log = fields.Text(
        related="erplibre_last_failed_run_id.log",
        string="Last ERPLibre snapshot failure",
    )
    erplibre_checkout_problem = fields.Char(
        string="ERPLibre checkout problem",
        compute="_compute_erplibre_checkout_problem",
    )

    def _compute_erplibre_last_snapshot(self):
        """The last snapshot, and the last snapshot run that failed after
        it: a periodic or startup snapshot that cannot run leaves only this
        trace."""
        last = self.env["erplibre.code.snapshot"].search([], limit=1)
        domain = [("run_type", "=", "snapshot"), ("state", "=", "failed")]
        if last:
            domain.append(("date_end", ">", last.date))
        failed = self.env["erplibre.code.run"].search(
            domain, order="date_end desc, id desc", limit=1
        )
        for settings in self:
            settings.erplibre_last_snapshot_id = last
            settings.erplibre_last_failed_run_id = failed

    def _compute_erplibre_checkout_problem(self):
        """Why the snapshot script cannot run, read on the file system; no
        script runs."""
        problem = runner.checkout_problem(self.env) or False
        for settings in self:
            settings.erplibre_checkout_problem = problem

    def _compute_erplibre_server_actions_allowed(self):
        allowed = self.env["erplibre.code.run"]._server_actions_allowed()
        for settings in self:
            settings.erplibre_server_actions_allowed = allowed

    @api.model
    def get_values(self):
        res = super().get_values()
        cron = self.env["erplibre.code.run"]._cron()
        if cron:
            res.update(
                erplibre_snapshot_interval_number=cron.sudo().interval_number,
                erplibre_snapshot_interval_type=(
                    cron.sudo().interval_type
                    if cron.sudo().interval_type in ("hours", "days", "weeks")
                    else "days"
                ),
            )
        return res

    def set_values(self):
        super().set_values()
        cron = self.env["erplibre.code.run"]._cron()
        if not cron:
            return
        vals = {
            "interval_number": max(1, self.erplibre_snapshot_interval_number or 1),
            "interval_type": self.erplibre_snapshot_interval_type or "days",
        }
        # ``try_write``: while the cron executes a job its row is locked,
        # and a plain write would fail the whole Settings save. The
        # interval then keeps its value until the next save.
        if any(cron.sudo()[k] != v for k, v in vals.items()):
            cron.sudo().try_write(vals)
        self.env["erplibre.code.run"]._sync_cron()

    def action_erplibre_capture_now(self):
        return self.env["erplibre.code.snapshot"].action_capture_now()

    def action_erplibre_open_snapshots(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "erplibre_info.erplibre_code_snapshot_action"
        )

    def action_erplibre_open_runs(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "erplibre_info.erplibre_code_run_action"
        )

    def action_erplibre_restart(self):
        run = self.env["erplibre.code.run"]
        run._check_server_actions()
        return self.env["erplibre.code.confirm.wizard"]._action_open("restart")

    def action_erplibre_fetch_rebase(self):
        return self.env["erplibre.code.run"].action_start_dry_run()
