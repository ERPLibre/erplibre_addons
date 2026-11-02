# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.exceptions import UserError


class ErplibreCodeSnapshotModule(models.Model):
    _name = "erplibre.code.snapshot.module"
    _description = "ERPLibre code snapshot installed module"
    _order = "snapshot_id desc, name"

    snapshot_id = fields.Many2one(
        "erplibre.code.snapshot", required=True, ondelete="cascade", index=True
    )
    module_id = fields.Many2one(
        "ir.module.module", string="Module", ondelete="set null", readonly=True
    )
    name = fields.Char(string="Technical name", required=True, readonly=True)
    module_state = fields.Char(string="Module state", readonly=True)
    installed_version = fields.Char(
        readonly=True, help="Version recorded in the database."
    )
    code_version = fields.Char(
        readonly=True,
        help="Version of the manifest on disk, as Odoo stores it.",
    )
    pending_update = fields.Boolean(
        string="Upgrade pending",
        readonly=True,
        index=True,
        help="The code on disk carries another version than the database: "
        "the module waits for an upgrade (-u).",
    )
    found_in_code = fields.Boolean(readonly=True)
    path = fields.Char(readonly=True)
    repo_line_id = fields.Many2one(
        "erplibre.code.snapshot.repo",
        string="Repository",
        ondelete="set null",
        readonly=True,
    )
    repo_path = fields.Char(related="repo_line_id.path", string="Repository path")

    def action_cross_version(self):
        self.ensure_one()
        if not self.repo_line_id:
            raise UserError(
                self.env._("No repository of the manifest holds this module.")
            )
        cache = self.env["erplibre.code.cross.version"]._fetch_for(
            self.repo_line_id, self.name
        )
        return cache._action_open()
