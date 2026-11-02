# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models, release
from odoo.exceptions import UserError

from odoo.addons.erplibre_info import runner

# Exit codes of « repo_pull.py --apply-stash ».
EXIT_NOT_FOUND = 3
EXIT_BUSY = 5


class ErplibreCodeStash(models.Model):
    """A stash that a pass of ``repo_pull.py`` kept in a clone: the
    modified files of a tree it moved, saved by ``git stash push``. The
    entry lives in the stash list of the clone; this record reapplies it
    with ``--apply-stash``, which never removes it from the list."""

    _name = "erplibre.code.stash"
    _description = "ERPLibre kept stash"
    _order = "id desc"
    _rec_name = "sha"

    run_id = fields.Many2one(
        "erplibre.code.run",
        string="Run",
        required=True,
        ondelete="cascade",
        readonly=True,
        index=True,
    )
    path = fields.Char(string="Repository", required=True, readonly=True)
    sha = fields.Char(string="Stash commit", required=True, readonly=True)
    message = fields.Char(readonly=True)
    command = fields.Char(
        string="Reapply command",
        readonly=True,
        help="The git command that reapplies the stash from a terminal, in "
        "the ERPLibre root.",
    )
    date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    state = fields.Selection(
        [
            ("kept", "Kept"),
            ("applied", "Reapplied"),
            ("conflict", "Conflict: tree put back"),
            ("missing", "Missing"),
        ],
        default="kept",
        required=True,
        readonly=True,
        help="Reapplied or not, the stash stays in the list of its clone.",
    )
    log = fields.Text(readonly=True)
    git_fetch_allowed = fields.Boolean(compute="_compute_git_fetch_allowed")

    def _compute_git_fetch_allowed(self):
        allowed = self.env["erplibre.code.run"]._git_fetch_allowed()
        for stash in self:
            stash.git_fetch_allowed = allowed

    def _check_reapplicable(self):
        self.ensure_one()
        if self.state not in ("kept", "conflict"):
            raise UserError(self.env._("This stash cannot be reapplied."))

    def action_reapply(self):
        """Open the confirmation of the reapply: the first validation."""
        self.ensure_one()
        self.env["erplibre.code.run"]._check_git_fetch()
        self._check_reapplicable()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "stash_apply", run=self.run_id, stash=self
        )

    def _launch_reapply(self):
        """Reapply the stash in its clone, synchronously, after the second
        validation: a single ``git stash apply`` on a clean tree. A
        conflict puts the tree back on HEAD; the stash stays in the list
        whatever the outcome."""
        self.ensure_one()
        Run = self.env["erplibre.code.run"]
        Run._check_git_fetch()
        self._check_reapplicable()
        Run._check_no_git_run()
        try:
            res = runner.run_json(
                self.env,
                runner.SCRIPT_PULL,
                [
                    "--apply-stash",
                    f"{self.path}={self.sha}",
                    "--confirm",
                    self.run_id.odoo_version or release.series,
                    "--json",
                ],
                ok_codes=(0, EXIT_NOT_FOUND, EXIT_BUSY),
            )
        except runner.RunnerError as exc:
            raise UserError(str(exc)) from exc
        if res.returncode == EXIT_BUSY:
            raise UserError(self.env._("Another pull is running on this checkout."))
        etat = res.data.get("etat")
        labels = {
            "applique": self.env._("reapplied"),
            "conflit": self.env._("conflict: the tree is put back on HEAD"),
            "introuvable": self.env._("not a stash of the clone"),
            "refuse_sale": self.env._("refused: the tree has modified files"),
        }
        label = labels.get(etat) or res.data.get("error") or etat or ""
        reason = res.data.get("motif")
        if reason:
            label = f"{label} ({reason})"
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
        state = {
            "applique": "applied",
            "conflit": "conflict",
            "introuvable": "missing",
        }.get(etat)
        if not state and res.returncode == EXIT_NOT_FOUND:
            state = "missing"
        if state:
            vals["state"] = state
        self.write(vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.path,
                "message": label,
                "type": "success" if etat == "applique" else "warning",
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
