# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import hashlib
import json
import os
import re

from odoo import api, fields, models, release
from odoo.exceptions import UserError
from odoo.modules.module import adapt_version, get_module_path

from .. import runner
from .erplibre_code_run import TRIGGERS

PARAM_DIRTY = "erplibre_info.check_dirty"

REPO_STATES = [
    ("conforme", "Matches the manifest"),
    ("en_avance", "Ahead of the manifest"),
    ("decale", "Off the manifest"),
    ("sale", "Modified"),
    ("absent", "Missing"),
    ("hors_manifeste", "Not in the manifest"),
    ("erreur", "Unreadable"),
]

# « odoo18.0/addons/OCA_web » → « 18.0 ».
_VERSION_PREFIX = re.compile(r"^odoo(\d+\.\d+)/")


def odoo_version_of(path):
    match = _VERSION_PREFIX.match(path or "")
    return match.group(1) if match else False


def safe_version(version):
    """The full version Odoo stores for a manifest version, or False."""
    if not version:
        return False
    try:
        return adapt_version(str(version))
    except ValueError:
        return str(version)


class ErplibreCodeSnapshot(models.Model):
    _name = "erplibre.code.snapshot"
    _description = "ERPLibre code snapshot"
    _order = "date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    trigger = fields.Selection(TRIGGERS, required=True, readonly=True)
    user_id = fields.Many2one(
        "res.users", default=lambda self: self.env.user, readonly=True
    )
    run_id = fields.Many2one("erplibre.code.run", readonly=True, ondelete="set null")
    previous_id = fields.Many2one(
        "erplibre.code.snapshot",
        string="Previous snapshot",
        readonly=True,
        ondelete="set null",
    )
    erplibre_version = fields.Char(string="ERPLibre version", readonly=True)
    erplibre_commit = fields.Char(string="ERPLibre commit", readonly=True)
    erplibre_head = fields.Char(string="ERPLibre HEAD", readonly=True)
    erplibre_branch = fields.Char(string="ERPLibre branch", readonly=True)
    erplibre_dirty = fields.Boolean(string="ERPLibre modified", readonly=True)
    odoo_version = fields.Char(string="Odoo version", readonly=True)
    odoo_python = fields.Char(string="Python version", readonly=True)
    mode = fields.Selection(
        [("branches", "Branches"), ("frozen", "Frozen")],
        readonly=True,
        help="Branches: the manifest follows branches. Frozen: it pins commits.",
    )
    mode_pinned = fields.Integer(string="Pinned repositories", readonly=True)
    mode_total = fields.Integer(string="Manifest repositories", readonly=True)
    local_manifest = fields.Boolean(readonly=True)
    dirty_checked = fields.Boolean(string="Modified trees checked", readonly=True)
    fingerprint = fields.Char(
        index=True,
        readonly=True,
        help="Code fingerprint plus the installed module versions: two "
        "snapshots of the same state share it.",
    )
    code_fingerprint = fields.Char(readonly=True)
    duration_ms = fields.Integer(string="Duration (ms)", readonly=True)
    errors = fields.Text(readonly=True)
    repo_count = fields.Integer(string="Repository count", readonly=True)
    code_module_count = fields.Integer(string="Modules in the code", readonly=True)
    count_conforme = fields.Integer(string="Matching", readonly=True)
    count_en_avance = fields.Integer(string="Ahead", readonly=True)
    count_decale = fields.Integer(string="Off", readonly=True)
    count_sale = fields.Integer(string="Modified", readonly=True)
    count_absent = fields.Integer(string="Missing", readonly=True)
    count_hors_manifeste = fields.Integer(string="Not in manifest", readonly=True)
    count_erreur = fields.Integer(string="Unreadable", readonly=True)
    changed_repo_count = fields.Integer(string="Changed repositories", readonly=True)
    removed_repo_paths = fields.Text(string="Removed repositories", readonly=True)
    pending_update_count = fields.Integer(string="Modules to upgrade", readonly=True)
    raw_json = fields.Binary(string="JSON", attachment=True, readonly=True)
    raw_json_filename = fields.Char(compute="_compute_raw_json_filename")
    repo_ids = fields.One2many(
        "erplibre.code.snapshot.repo", "snapshot_id", string="Repositories"
    )
    module_ids = fields.One2many(
        "erplibre.code.snapshot.module",
        "snapshot_id",
        string="Installed modules",
    )
    changed_repo_ids = fields.One2many(
        "erplibre.code.snapshot.repo",
        compute="_compute_changed_repo_ids",
        string="Changes",
    )
    pending_module_ids = fields.One2many(
        "erplibre.code.snapshot.module",
        compute="_compute_pending_module_ids",
        string="Pending upgrades",
    )
    state_summary = fields.Char(compute="_compute_state_summary")

    @api.depends("date", "trigger")
    def _compute_name(self):
        for snap in self:
            snap.name = fields.Datetime.to_string(snap.date) if snap.date else ""

    def _compute_raw_json_filename(self):
        for snap in self:
            stamp = (snap.name or "").replace(" ", "_").replace(":", "")
            snap.raw_json_filename = f"erplibre_snapshot_{stamp}.json"

    @api.depends("repo_ids.change")
    def _compute_changed_repo_ids(self):
        for snap in self:
            snap.changed_repo_ids = snap.repo_ids.filtered(
                lambda r: r.change in ("new", "changed")
            )

    @api.depends("module_ids.pending_update")
    def _compute_pending_module_ids(self):
        for snap in self:
            snap.pending_module_ids = snap.module_ids.filtered("pending_update")

    def _compute_state_summary(self):
        field = self.env["erplibre.code.snapshot.repo"]._fields["state"]
        labels = dict(field._description_selection(self.env))
        for snap in self:
            parts = [
                f"{labels[key]} {snap[f'count_{key}']}"
                for key, _label in REPO_STATES
                if snap[f"count_{key}"]
            ]
            snap.state_summary = " · ".join(parts)

    # ── capture ─────────────────────────────────────────────────────────

    @api.model
    def _capture(self, trigger, run=None, force=False):
        """Read the code with ``repo_state.py snapshot`` and store it.

        Without ``force``, return an empty recordset when the fingerprint
        equals the one of the last snapshot. Raise ``runner.RunnerError``
        when the script cannot run.
        """
        args = ["snapshot"]
        if runner.param_bool(self.env, PARAM_DIRTY):
            args.append("--dirty")
        res = runner.run_json(self.env, runner.SCRIPT_STATE, args)
        return self._create_from_json(res.data, trigger, run=run, force=force)

    @api.model
    def _installed_modules(self):
        return (
            self.env["ir.module.module"]
            .sudo()
            .search([("state", "in", ("installed", "to upgrade"))], order="name")
        )

    @api.model
    def _fingerprint(self, code_fingerprint, modules):
        lines = [code_fingerprint or ""] + [
            f"{m.name}={m.latest_version or ''}/{m.state}" for m in modules
        ]
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    @api.model
    def _create_from_json(self, data, trigger, run=None, force=False):
        data = runner.scrub(data)
        modules = self._installed_modules()
        fingerprint = self._fingerprint(data.get("fingerprint"), modules)
        last = self.search([], order="id desc", limit=1)
        if not force and last and last.fingerprint == fingerprint:
            return self.browse()
        erplibre = data.get("erplibre") or {}
        odoo_info = data.get("odoo") or {}
        detail = data.get("mode_detail") or {}
        states = (data.get("counts") or {}).get("states") or {}
        previous = {r.path: r.head for r in last.repo_ids}
        repos = data.get("repos") or []
        repo_vals = [self._repo_vals(r, previous) for r in repos]
        present = {r.get("path") for r in repos}
        vals = {
            "trigger": trigger,
            "run_id": run.id if run else False,
            "previous_id": last.id,
            "erplibre_version": erplibre.get("version"),
            "erplibre_commit": erplibre.get("commit"),
            "erplibre_head": erplibre.get("head"),
            "erplibre_branch": erplibre.get("branch"),
            "erplibre_dirty": bool(erplibre.get("dirty")),
            "odoo_version": odoo_info.get("version"),
            "odoo_python": odoo_info.get("python"),
            "mode": data.get("mode") or False,
            "mode_pinned": detail.get("pinned") or 0,
            "mode_total": detail.get("total") or 0,
            "local_manifest": bool(data.get("local_manifest")),
            "dirty_checked": bool(data.get("dirty_checked")),
            "fingerprint": fingerprint,
            "code_fingerprint": data.get("fingerprint"),
            "duration_ms": data.get("duration_ms") or 0,
            "errors": "\n".join(str(e) for e in data.get("errors") or []) or False,
            "repo_count": len(repos),
            "code_module_count": (data.get("counts") or {}).get("modules") or 0,
            "changed_repo_count": len(
                [v for v in repo_vals if v["change"] in ("new", "changed")]
            ),
            "removed_repo_paths": (
                "\n".join(sorted(set(previous) - present)) if last else False
            ),
            "raw_json": base64.b64encode(
                json.dumps(data, ensure_ascii=False, indent=1).encode()
            ),
            "repo_ids": [fields.Command.create(v) for v in repo_vals],
        }
        for key, _label in REPO_STATES:
            vals[f"count_{key}"] = states.get(key, 0)
        snapshot = self.create(vals)
        snapshot._create_module_lines(data, modules)
        return snapshot

    @api.model
    def _repo_vals(self, repo, previous):
        upstream = repo.get("upstream") or {}
        path = repo.get("path") or ""
        if not previous:
            change = "same"
        elif path not in previous:
            change = "new"
        elif previous[path] != repo.get("head"):
            change = "changed"
        else:
            change = "same"
        version = odoo_version_of(path)
        return {
            "path": path,
            "name": repo.get("name"),
            "odoo_version": version,
            "is_active_version": version == release.series,
            "remote": repo.get("remote"),
            "url": runner.strip_credentials(repo.get("url")),
            "revision": repo.get("revision"),
            "manifest_branch": repo.get("manifest_branch"),
            "freeze_revision": repo.get("freeze_revision"),
            "upstream_remote": upstream.get("remote"),
            "upstream_name": upstream.get("name"),
            "upstream_branch": upstream.get("branch"),
            "upstream_freeze_revision": upstream.get("freeze_revision"),
            "upstream_declared": bool(upstream.get("declared")),
            "upstream_url": runner.strip_credentials(upstream.get("url")),
            "head": repo.get("head"),
            "branch": repo.get("branch"),
            "target": repo.get("target"),
            "ahead": repo.get("ahead") or 0,
            "behind": repo.get("behind") or 0,
            "alignment": repo.get("alignment") or False,
            "state": repo.get("state") or False,
            "dirty": bool(repo.get("dirty")),
            "module_count": len(repo.get("modules") or []),
            "error": repo.get("error"),
            "previous_head": (previous.get(path) if change == "changed" else False),
            "change": change,
        }

    def _create_module_lines(self, data, modules):
        """One line per installed module, linked to the repository that
        holds the code Odoo loads.

        The module is found by the path Odoo resolves on its addons path,
        then by name among the repositories of the running Odoo version:
        the trees of the other versions hold modules of the same name.
        """
        self.ensure_one()
        root = os.path.realpath(data.get("root") or "")
        by_path = {}
        by_name = {}
        series_prefix = f"odoo{release.series}/"
        for repo in data.get("repos") or []:
            for mod in repo.get("modules") or []:
                entry = (repo.get("path"), mod)
                by_path[mod.get("path")] = entry
                if (repo.get("path") or "").startswith(series_prefix):
                    by_name.setdefault(mod.get("name"), entry)
        lines = {line.path: line for line in self.repo_ids}
        vals_list = []
        for module in modules:
            entry = None
            module_path = get_module_path(module.name, display_warning=False)
            if module_path and root:
                rel = os.path.relpath(os.path.realpath(module_path), root)
                entry = by_path.get(rel)
            entry = entry or by_name.get(module.name)
            repo_path, mod = entry if entry else (False, {})
            code_version = safe_version(mod.get("version")) if entry else False
            installed = module.latest_version or False
            vals_list.append(
                {
                    "snapshot_id": self.id,
                    "module_id": module.id,
                    "name": module.name,
                    "module_state": module.state,
                    "installed_version": installed,
                    "code_version": code_version,
                    "path": mod.get("path") or False,
                    "repo_line_id": (
                        lines[repo_path].id if repo_path in lines else False
                    ),
                    "found_in_code": bool(entry),
                    "pending_update": bool(
                        code_version and installed and code_version != installed
                    ),
                }
            )
        created = self.env["erplibre.code.snapshot.module"].create(vals_list)
        self.pending_update_count = len(created.filtered("pending_update"))
        return created

    # ── actions ─────────────────────────────────────────────────────────

    def action_capture_now(self):
        """The manual snapshot: always stored, read synchronously (about a
        second; the script bounds every git call).

        A record method, not ``@api.model``: the list and form buttons pass
        the ids of the records shown, which ``call_kw`` hands to an
        ``@api.model`` method as an extra argument. Those records are
        ignored."""
        try:
            snapshot = self._capture("manual", force=True)
        except runner.RunnerError as exc:
            raise UserError(str(exc)) from exc
        return snapshot._action_open()

    def _action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_repos(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "erplibre_info.erplibre_code_snapshot_repo_action"
        )
        action["domain"] = [("snapshot_id", "=", self.id)]
        action["context"] = {"search_default_active_version": 1}
        return action

    def action_open_modules(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "erplibre_info.erplibre_code_snapshot_module_action"
        )
        action["domain"] = [("snapshot_id", "=", self.id)]
        action["context"] = {}
        return action
