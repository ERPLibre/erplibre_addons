# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError


class ErplibreCodeConfirmWizard(models.TransientModel):
    """Second validation of a server action: tick the box and type the
    database name again."""

    _name = "erplibre.code.confirm.wizard"
    _description = "ERPLibre server action confirmation"

    action = fields.Selection(
        [
            ("restart", "Restart the server"),
            ("restart_upgrade", "Upgrade the modules and restart the server"),
            ("apply", "Apply the rebase"),
            ("pull_apply", "Apply the pull"),
            ("pull_restore", "Restore the backup"),
            ("deps_install", "Install the Python dependencies"),
        ],
        required=True,
        readonly=True,
    )
    run_id = fields.Many2one("erplibre.code.run", readonly=True)
    module_ids = fields.Many2many("ir.module.module", string="Modules to upgrade")
    plan_paths = fields.Text(related="run_id.plan_paths")
    shallow_paths = fields.Text(related="run_id.shallow_paths")
    clone_paths = fields.Text(related="run_id.clone_paths")
    approve_deepen = fields.Boolean(
        string="Deepen the shallow clones",
        help="Deepening downloads history from the remote, by steps, until "
        "the common base appears.",
    )
    approve_clone = fields.Boolean(string="Clone the new repositories")
    backup_id = fields.Many2one("erplibre.code.pull.backup", readonly=True)
    database_name = fields.Char(compute="_compute_database_name")
    typed_database_name = fields.Char(string="Type the database name")
    understood = fields.Boolean(string="I understand what this action does")

    def _compute_database_name(self):
        for wizard in self:
            wizard.database_name = self.env.cr.dbname

    @api.model
    def _action_open(self, action, run=None, modules=None, backup=None):
        wizard = self.create(
            {
                "action": action,
                "run_id": run.id if run else False,
                "backup_id": backup.id if backup else False,
                "module_ids": [fields.Command.set(modules.ids if modules else [])],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "name": dict(self._fields["action"]._description_selection(self.env))[
                action
            ],
        }

    def action_confirm(self):
        self.ensure_one()
        Run = self.env["erplibre.code.run"]
        Run._check_server_actions()
        if not self.understood:
            raise UserError(self.env._("Tick the box to confirm."))
        if (self.typed_database_name or "").strip() != self.env.cr.dbname:
            raise UserError(
                self.env._("The typed name is not the name of this database.")
            )
        if self.action == "apply":
            if not self.run_id:
                raise UserError(self.env._("No dry run to apply."))
            return self.run_id._launch_apply()
        if self.action == "pull_apply":
            if not self.run_id:
                raise UserError(self.env._("No dry run to apply."))
            return self.run_id._launch_pull_apply(
                approve_deepen=self.approve_deepen,
                approve_clone=self.approve_clone,
            )
        if self.action == "pull_restore":
            if not self.backup_id:
                raise UserError(self.env._("No backup to restore."))
            return self.backup_id._launch_restore()
        if self.action == "deps_install":
            if not self.run_id:
                raise UserError(self.env._("No pull to install the dependencies of."))
            return self.run_id._launch_deps_install()
        modules = self.module_ids if self.action == "restart_upgrade" else None
        return Run._request_restart(modules)
