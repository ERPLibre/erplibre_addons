# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models, release
from odoo.exceptions import UserError

from .. import runner


class ErplibreCodePullBackup(models.Model):
    """A backup branch that a pull put on the HEAD of a repository before
    moving it: ``<branch>_avant_pull_<stamp>``. The branch lives in the
    clone; this record restores or deletes it through ``repo_pull.py``."""

    _name = "erplibre.code.pull.backup"
    _description = "ERPLibre pull backup branch"
    _order = "id desc"
    _rec_name = "branch_name"

    run_id = fields.Many2one(
        "erplibre.code.run",
        string="Pull",
        required=True,
        ondelete="cascade",
        readonly=True,
        index=True,
    )
    path = fields.Char(string="Repository", required=True, readonly=True)
    branch_name = fields.Char(string="Backup branch", required=True, readonly=True)
    sha = fields.Char(string="Commit", readonly=True)
    original_branch = fields.Char(
        string="Branch",
        readonly=True,
        help="The branch the repository was on before the pull; empty "
        "for a detached HEAD.",
    )
    detached = fields.Boolean(string="Detached HEAD", readonly=True)
    state = fields.Selection(
        [
            ("kept", "Kept"),
            ("restored", "Restored"),
            ("deleted", "Deleted"),
            ("missing", "Missing"),
        ],
        default="kept",
        required=True,
        readonly=True,
    )
    log = fields.Text(readonly=True)

    def _designation(self):
        self.ensure_one()
        return f"{self.path}={self.branch_name}"

    def _odoo_version(self):
        self.ensure_one()
        return self.run_id.odoo_version or release.series

    def action_restore(self):
        """Open the confirmation of the restore: the first validation."""
        self.ensure_one()
        self.env["erplibre.code.run"]._check_server_actions()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "pull_restore", run=self.run_id, backup=self
        )

    def _launch_restore(self):
        """Queue the restore of this backup; called by the confirmed
        wizard, the second validation."""
        self.ensure_one()
        Run = self.env["erplibre.code.run"]
        Run._check_server_actions()
        if self.state != "kept":
            raise UserError(self.env._("This backup branch is no longer kept."))
        Run._check_no_git_run()
        run = Run._create_launched(
            {
                "run_type": "pull_restore",
                "parent_id": self.run_id.id,
                "backup_id": self.id,
                "odoo_version": self._odoo_version(),
            }
        )
        run._enqueue()
        return run._action_open()

    def action_delete(self):
        """Delete the backup branch in its clone, synchronously: a single
        ``git branch -D`` that never moves HEAD. A restored backup keeps
        its branch on disk, so it can be deleted too."""
        self.ensure_one()
        Run = self.env["erplibre.code.run"]
        Run._check_server_actions()
        if self.state not in ("kept", "restored"):
            raise UserError(self.env._("This backup branch is no longer kept."))
        Run._check_no_git_run()
        try:
            res = runner.run_json(
                self.env,
                runner.SCRIPT_PULL,
                [
                    "--delete-backup",
                    self._designation(),
                    "--confirm",
                    self._odoo_version(),
                    "--json",
                ],
                ok_codes=(0, 3),
            )
        except runner.RunnerError as exc:
            raise UserError(str(exc)) from exc
        result = (res.data.get("resultats") or [{}])[0]
        etat = result.get("etat")
        label = Run._pull_state_label(etat) if etat else res.data.get("error") or ""
        vals = {
            "log": "\n".join(
                x
                for x in (
                    self.log,
                    f"{fields.Datetime.to_string(fields.Datetime.now())} "
                    f"{res.command}: {label}",
                )
                if x
            )
        }
        if etat == "supprime":
            vals["state"] = "deleted"
        elif res.returncode == 3:
            vals["state"] = "missing"
        self.write(vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.branch_name,
                "message": label,
                "type": "success" if etat == "supprime" else "warning",
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
