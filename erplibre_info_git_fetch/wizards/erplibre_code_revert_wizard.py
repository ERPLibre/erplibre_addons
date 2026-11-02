# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from odoo import api, fields, models


class ErplibreCodeRevertWizard(models.TransientModel):
    """The choices of a return to a snapshot before its dry run: the
    snapshot, and whether the ERPLibre root goes back too."""

    _name = "erplibre.code.revert.wizard"
    _description = "ERPLibre return to a snapshot"

    snapshot_id = fields.Many2one(
        "erplibre.code.snapshot",
        string="Snapshot",
        required=True,
        readonly=True,
    )
    include_root = fields.Boolean(
        string="Also return the ERPLibre root",
        default=True,
        help="The ERPLibre root goes back to the commit of the snapshot, "
        "after the other repositories; the local manifest is then "
        "regenerated.",
    )
    erplibre_head = fields.Char(related="snapshot_id.erplibre_head")
    erplibre_branch = fields.Char(related="snapshot_id.erplibre_branch")
    repo_count = fields.Integer(
        string="Repositories to compare", compute="_compute_revert_preview"
    )
    newer_modules_html = fields.Html(
        string="Newer modules",
        compute="_compute_revert_preview",
        sanitize=False,
    )

    @api.depends("snapshot_id")
    def _compute_revert_preview(self):
        Run = self.env["erplibre.code.run"]
        for wizard in self:
            snapshot = wizard.snapshot_id
            wizard.repo_count = (
                len(snapshot._revert_targets(False)["depots"]) if snapshot else 0
            )
            wizard.newer_modules_html = (
                Run._render_newer_modules(snapshot._revert_newer_modules())
                if snapshot
                else False
            ) or False

    @api.model
    def _action_open(self, snapshot):
        self.env["erplibre.code.run"]._check_git_fetch()
        wizard = self.create({"snapshot_id": snapshot.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "name": self.env._("Return to this snapshot"),
        }

    def action_start(self):
        """Queue the dry run of the return and open it. The targets are
        frozen in the run: its apply step reads the same."""
        self.ensure_one()
        Run = self.env["erplibre.code.run"]
        Run._check_git_fetch()
        Run._check_no_git_run()
        targets = self.snapshot_id._revert_targets(self.include_root)
        run = Run._create_launched(
            {
                "run_type": "snapshot_revert_dry_run",
                "revert_snapshot_id": self.snapshot_id.id,
                "revert_root": bool(targets["racine"]),
                "revert_targets": json.dumps(targets, indent=1, sort_keys=True),
            }
        )
        run._enqueue()
        return run._action_open()
