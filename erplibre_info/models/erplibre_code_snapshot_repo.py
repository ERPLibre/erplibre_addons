# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import UserError

from .. import runner
from .erplibre_code_snapshot import REPO_STATES

BETWEEN_MAX = 200


class ErplibreCodeSnapshotRepo(models.Model):
    _name = "erplibre.code.snapshot.repo"
    _description = "ERPLibre code snapshot repository"
    _order = "snapshot_id desc, path"
    _rec_name = "path"

    snapshot_id = fields.Many2one(
        "erplibre.code.snapshot", required=True, ondelete="cascade", index=True
    )
    snapshot_date = fields.Datetime(related="snapshot_id.date", store=True)
    path = fields.Char(required=True, index=True, readonly=True)
    name = fields.Char(string="Project", readonly=True)
    odoo_version = fields.Char(readonly=True)
    is_active_version = fields.Boolean(
        string="Running Odoo version",
        readonly=True,
        help="The repository lies under the tree of the Odoo version that "
        "runs this database.",
    )
    remote = fields.Char(readonly=True)
    url = fields.Char(string="URL", readonly=True)
    revision = fields.Char(readonly=True)
    manifest_branch = fields.Char(readonly=True)
    freeze_revision = fields.Char(readonly=True)
    upstream_remote = fields.Char(readonly=True)
    upstream_name = fields.Char(readonly=True)
    upstream_branch = fields.Char(readonly=True)
    upstream_freeze_revision = fields.Char(string="Upstream base", readonly=True)
    upstream_declared = fields.Boolean(readonly=True)
    upstream_url = fields.Char(string="Upstream URL", readonly=True)
    head = fields.Char(string="HEAD", readonly=True)
    branch = fields.Char(readonly=True)
    target = fields.Char(readonly=True)
    ahead = fields.Integer(readonly=True)
    behind = fields.Integer(readonly=True)
    alignment = fields.Selection(REPO_STATES, readonly=True)
    state = fields.Selection(REPO_STATES, readonly=True, index=True)
    dirty = fields.Boolean(string="Modified", readonly=True)
    module_count = fields.Integer(string="Modules", readonly=True)
    error = fields.Char(readonly=True)
    change = fields.Selection(
        [("same", "Unchanged"), ("new", "New"), ("changed", "HEAD moved")],
        string="Since the previous snapshot",
        readonly=True,
        index=True,
    )
    previous_head = fields.Char(string="Previous HEAD", readonly=True)
    head_short = fields.Char(compute="_compute_short", string="HEAD (short)")
    previous_head_short = fields.Char(compute="_compute_short")
    between_json = fields.Text(readonly=True)
    between_count = fields.Integer(string="Commits", readonly=True)
    between_loaded = fields.Boolean(readonly=True)
    between_html = fields.Html(
        compute="_compute_between_html",
        sanitize=False,
        string="Commits between",
    )
    module_line_ids = fields.One2many(
        "erplibre.code.snapshot.module",
        "repo_line_id",
        string="Installed modules",
    )

    @api.depends("head", "previous_head")
    def _compute_short(self):
        for line in self:
            line.head_short = (line.head or "")[:12]
            line.previous_head_short = (line.previous_head or "")[:12]

    @api.depends("between_json")
    def _compute_between_html(self):
        for line in self:
            try:
                data = json.loads(line.between_json) if line.between_json else None
            except ValueError:
                data = None
            line.between_html = line._render_between(data) if data else False

    def _render_between(self, data):
        rows = Markup("").join(
            Markup("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>")
            % (
                (c.get("sha") or "")[:12],
                c.get("date") or "",
                c.get("author") or "",
                c.get("subject") or "",
            )
            for c in data.get("commits") or []
        )
        notes = []
        if data.get("error"):
            notes.append(data["error"])
        if not data.get("old_known"):
            notes.append(self.env._("The previous HEAD is no longer in the clone."))
        if data.get("ancestor") is False:
            notes.append(
                self.env._(
                    "The previous HEAD is not an ancestor: %(count)s commits "
                    "left the history.",
                    count=data.get("removed") or 0,
                )
            )
        if data.get("truncated"):
            notes.append(
                self.env._(
                    "Only the first %(max)s commits are shown.",
                    max=data.get("max"),
                )
            )
        html = Markup("").join(
            Markup("<p class='text-muted'>%s</p>") % n for n in notes
        )
        return html + Markup(
            "<table class='table table-sm o_erplibre_info_table'><thead><tr>"
            "<th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr></thead>"
            "<tbody>%s</tbody></table>"
        ) % (
            self.env._("Commit"),
            self.env._("Date"),
            self.env._("Author"),
            self.env._("Subject"),
            rows,
        )

    def action_load_commits(self):
        """Read the commits between the previous HEAD and this one with
        ``repo_state.py between``, bounded to BETWEEN_MAX."""
        self.ensure_one()
        if not (self.previous_head and self.head):
            raise UserError(
                self.env._("This repository has no previous HEAD to compare.")
            )
        try:
            res = runner.run_json(
                self.env,
                runner.SCRIPT_STATE,
                [
                    "between",
                    self.path,
                    self.previous_head,
                    self.head,
                    "--max",
                    str(BETWEEN_MAX),
                ],
                ok_codes=(0, 3),
            )
        except runner.RunnerError as exc:
            raise UserError(str(exc)) from exc
        self.write(
            {
                "between_json": json.dumps(res.data, ensure_ascii=False),
                "between_count": res.data.get("count") or 0,
                "between_loaded": True,
            }
        )
        return self._action_open()

    def action_cross_version(self):
        self.ensure_one()
        cache = self.env["erplibre.code.cross.version"]._fetch_for(self)
        return cache._action_open()

    def _action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }
