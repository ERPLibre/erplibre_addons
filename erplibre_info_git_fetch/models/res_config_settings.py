# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from .erplibre_code_run import PARAM_PULL_STRATEGY, PULL_STRATEGIES


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    erplibre_pull_strategy = fields.Selection(
        PULL_STRATEGIES,
        string="Pull strategy",
        default="rebase",
        config_parameter=PARAM_PULL_STRATEGY,
        help="How a repository with commits of its own integrates its "
        "target when the code is pulled. The pull wizard starts with it "
        "and lets it change for one pull.",
    )
    erplibre_git_fetch_allowed = fields.Boolean(
        compute="_compute_erplibre_git_fetch_allowed"
    )
    erplibre_git_fetch_problem = fields.Char(
        compute="_compute_erplibre_git_fetch_allowed"
    )

    @api.model
    def _erplibre_status(self):
        status = super()._erplibre_status()
        Run = self.env["erplibre.code.run"]
        allowed = Run._git_fetch_allowed()
        status.update(
            erplibre_git_fetch_allowed=allowed,
            erplibre_git_fetch_problem=False if allowed else Run._git_fetch_problem(),
        )
        return status

    def _compute_erplibre_git_fetch_allowed(self):
        self._erplibre_assign(
            ["erplibre_git_fetch_allowed", "erplibre_git_fetch_problem"]
        )

    def action_erplibre_fetch_rebase(self):
        return self.env["erplibre.code.run"].action_start_dry_run()

    def action_erplibre_pull(self):
        return self.env["erplibre.code.pull.wizard"]._action_open()
