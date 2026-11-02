# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError


class ErplibreCodeConfirmWizard(models.TransientModel):
    """The confirmation of the actions that write the checkout; each one
    checks ``--dev`` again through its launch method."""

    _inherit = "erplibre.code.confirm.wizard"

    action = fields.Selection(
        selection_add=[
            ("apply", "Apply the rebase"),
            ("pull_apply", "Apply the pull"),
            ("pull_restore", "Restore the backup"),
            ("deps_install", "Install the Python dependencies"),
        ],
        ondelete={
            "apply": "cascade",
            "pull_apply": "cascade",
            "pull_restore": "cascade",
            "deps_install": "cascade",
        },
    )
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

    @api.model
    def _action_open_vals(self, action, run=None, modules=None, backup=None, **kw):
        vals = super()._action_open_vals(action, run=run, modules=modules, **kw)
        vals["backup_id"] = backup.id if backup else False
        return vals

    def _confirm_action(self):
        self.ensure_one()
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
        return super()._confirm_action()
