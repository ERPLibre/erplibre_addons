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
            ("snapshot_revert", "Return to the snapshot"),
            ("stash_apply", "Reapply the stash"),
        ],
        ondelete={
            "apply": "cascade",
            "pull_apply": "cascade",
            "pull_restore": "cascade",
            "deps_install": "cascade",
            "snapshot_revert": "cascade",
            "stash_apply": "cascade",
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
    stash_id = fields.Many2one("erplibre.code.stash", string="Stash", readonly=True)
    stash_path = fields.Char(related="stash_id.path")
    revert_snapshot_id = fields.Many2one(related="run_id.revert_snapshot_id")
    revert_root = fields.Boolean(related="run_id.revert_root")
    has_newer_modules = fields.Boolean(compute="_compute_newer_modules")
    newer_modules_html = fields.Html(
        string="Newer modules", compute="_compute_newer_modules", sanitize=False
    )
    approve_modules = fields.Boolean(
        string="Return anyway: these modules run on older code",
        help="Their data was written by a newer version than the code of "
        "the snapshot. An upgrade of the module does not migrate it back.",
    )

    @api.depends("action", "run_id")
    def _compute_newer_modules(self):
        """The modules installed with a newer version than the snapshot of
        a return, read now."""
        for wizard in self:
            newer = []
            if wizard.action == "snapshot_revert" and wizard.run_id:
                newer = wizard.run_id._revert_newer_modules()
            wizard.has_newer_modules = bool(newer)
            wizard.newer_modules_html = (
                wizard.run_id._render_newer_modules(newer) if newer else False
            )

    @api.model
    def _action_open_vals(
        self, action, run=None, modules=None, backup=None, stash=None, **kw
    ):
        vals = super()._action_open_vals(action, run=run, modules=modules, **kw)
        vals["backup_id"] = backup.id if backup else False
        vals["stash_id"] = stash.id if stash else False
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
        if self.action == "snapshot_revert":
            if not self.run_id:
                raise UserError(self.env._("No dry run to apply."))
            return self.run_id._launch_snapshot_revert(
                approve_modules=self.approve_modules
            )
        if self.action == "stash_apply":
            if not self.stash_id:
                raise UserError(self.env._("No stash to reapply."))
            return self.stash_id._launch_reapply()
        return super()._confirm_action()
