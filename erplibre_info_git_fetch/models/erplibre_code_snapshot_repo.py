# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ErplibreCodeSnapshotRepo(models.Model):
    _inherit = "erplibre.code.snapshot.repo"

    git_fetch_allowed = fields.Boolean(compute="_compute_git_fetch_allowed")

    def _compute_git_fetch_allowed(self):
        allowed = self.env["erplibre.code.run"]._git_fetch_allowed()
        for line in self:
            line.git_fetch_allowed = allowed

    def action_pull(self):
        """Open the pull wizard restricted to this repository."""
        self.ensure_one()
        return self.env["erplibre.code.pull.wizard"]._action_open(repo_line=self)
