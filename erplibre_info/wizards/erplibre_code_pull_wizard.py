# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from ..models.erplibre_code_run import (
    PARAM_PULL_STRATEGY,
    PULL_MODES,
    PULL_STRATEGIES,
)


class ErplibreCodePullWizard(models.TransientModel):
    """The choices of a pull before its dry run: the mode, the strategy,
    and optionally one repository."""

    _name = "erplibre.code.pull.wizard"
    _description = "ERPLibre pull of the code"

    mode = fields.Selection(
        PULL_MODES,
        required=True,
        default="manifeste",
        help="Manifest: the ERPLibre root is pulled, the local manifest is "
        "regenerated, then each repository integrates its new target. "
        "Branches: each repository pulls the branch it tracks.",
    )
    strategy = fields.Selection(
        PULL_STRATEGIES,
        required=True,
        default=lambda self: self._default_strategy(),
        help="How a repository with commits of its own integrates its "
        "target. A repository that is only behind is fast-forwarded "
        "whatever the strategy.",
    )
    repo_line_id = fields.Many2one(
        "erplibre.code.snapshot.repo", string="Repository", readonly=True
    )
    path = fields.Char(related="repo_line_id.path")

    @api.model
    def _default_strategy(self):
        value = self.env["ir.config_parameter"].sudo().get_param(PARAM_PULL_STRATEGY)
        return value if value in dict(PULL_STRATEGIES) else "rebase"

    @api.model
    def _action_open(self, repo_line=None):
        self.env["erplibre.code.run"]._check_server_actions()
        vals = {"repo_line_id": repo_line.id if repo_line else False}
        if repo_line and repo_line.branch:
            vals["mode"] = "branche"
        wizard = self.create(vals)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "name": self.env._("Pull the code"),
        }

    def action_start(self):
        """Queue the dry run of the pull and open it."""
        self.ensure_one()
        Run = self.env["erplibre.code.run"]
        Run._check_server_actions()
        Run._check_no_git_run()
        run = Run._create_launched(
            {
                "run_type": "pull_dry_run",
                "pull_mode": self.mode,
                "pull_strategy": self.strategy,
                "pull_path": self.path or False,
            }
        )
        run._enqueue()
        return run._action_open()
