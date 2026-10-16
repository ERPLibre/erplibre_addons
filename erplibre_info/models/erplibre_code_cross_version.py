# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import UserError

from .. import runner

PATHS_SHOWN = 100


def _join(parts):
    return Markup("").join(parts)


class ErplibreCodeCrossVersion(models.Model):
    """Cache of ``repo_state.py cross-version``: one record per repository
    path and module, refreshed on demand."""

    _name = "erplibre.code.cross.version"
    _description = "ERPLibre code across Odoo versions"
    _order = "date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    repo_path = fields.Char(
        string="Repository", required=True, index=True, readonly=True
    )
    module_name = fields.Char(string="Module", index=True, readonly=True)
    date = fields.Datetime(readonly=True)
    data_json = fields.Text(string="JSON", readonly=True)
    error = fields.Char(readonly=True)
    other_versions = fields.Char(
        readonly=True, help="Other Odoo versions that hold the path."
    )
    to_port_count = fields.Integer(string="Commits to port", readonly=True)
    report_html = fields.Html(compute="_compute_report_html", sanitize=False)
    full_diff = fields.Text(readonly=True)
    full_diff_date = fields.Datetime(readonly=True)
    full_diff_truncated = fields.Boolean(readonly=True)

    @api.depends("repo_path", "module_name")
    def _compute_name(self):
        for rec in self:
            rec.name = (
                f"{rec.repo_path} › {rec.module_name}"
                if rec.module_name
                else rec.repo_path or ""
            )

    @api.depends("data_json")
    def _compute_report_html(self):
        for rec in self:
            try:
                data = json.loads(rec.data_json) if rec.data_json else None
            except ValueError:
                data = None
            rec.report_html = rec._render(data) if data else False

    # ── computation ─────────────────────────────────────────────────────

    @api.model
    def _args(self, repo_path, module_name=None, full=False):
        args = ["cross-version", repo_path]
        if module_name:
            args += ["--module", module_name]
        if full:
            args.append("--full")
        return args

    @api.model
    def _run(self, repo_path, module_name=None, full=False):
        try:
            return runner.run_json(
                self.env,
                runner.SCRIPT_STATE,
                self._args(repo_path, module_name, full),
                ok_codes=(0, 3),
            )
        except runner.RunnerError as exc:
            raise UserError(str(exc)) from exc

    @api.model
    def _vals_from(self, data, repo_path, module_name=None):
        """The stored values of one script run. The patches of a ``--full``
        run go to ``full_diff``, not to ``data_json``."""
        data = json.loads(json.dumps(data))
        others = data.get("others") or []
        for other in others:
            (other.get("diff") or {}).pop("patch", None)
        return {
            "repo_path": repo_path,
            "module_name": module_name or False,
            "date": fields.Datetime.now(),
            "data_json": json.dumps(data, ensure_ascii=False),
            "error": data.get("error") or False,
            "other_versions": ", ".join(
                o["version"] for o in others if o.get("present")
            )
            or False,
            "to_port_count": sum(len(o.get("to_port") or []) for o in others),
        }

    def _cached_head(self):
        self.ensure_one()
        try:
            data = json.loads(self.data_json or "{}")
        except ValueError:
            return None
        return (data.get("repo") or {}).get("head")

    @api.model
    def _fetch(self, repo_path, module_name=None, refresh=False, head=None, since=None):
        """The cached record of ``repo_path``/``module_name``.

        The script runs when there is none, with ``refresh``, when the
        cached HEAD of this repository is not ``head``, or when the cache is
        older than ``since`` (the date of the last snapshot, which a HEAD
        moved in any odoo<V>/ tree renews).
        """
        rec = self.search(
            [
                ("repo_path", "=", repo_path),
                ("module_name", "=", module_name or False),
            ],
            limit=1,
        )
        stale = bool(
            rec
            and (
                (head and rec._cached_head() != head)
                or (since and (not rec.date or rec.date < since))
            )
        )
        if rec and not refresh and not stale:
            return rec
        data = self._run(repo_path, module_name).data
        vals = dict(
            self._vals_from(data, repo_path, module_name),
            full_diff=False,
            full_diff_date=False,
            full_diff_truncated=False,
        )
        if rec:
            rec.write(vals)
            return rec
        return self.create(vals)

    @api.model
    def _fetch_for(self, repo_line, module_name=None):
        """``_fetch`` for a repository line of a snapshot: the cache must be
        newer than the last snapshot, and, from the last snapshot, carry
        the HEAD of its line."""
        last = self.env["erplibre.code.snapshot"].search([], limit=1)
        head = repo_line.head if repo_line.snapshot_id == last else None
        return self._fetch(
            repo_line.path, module_name, head=head, since=last.date or None
        )

    def action_refresh(self):
        self.ensure_one()
        self._fetch(self.repo_path, self.module_name, refresh=True)
        return self._action_open()

    def action_load_full_diff(self):
        """The complete patch of each other version, bounded by the
        script's ``--max-bytes``. The report is rewritten from the same
        run: both tabs describe the same commits."""
        self.ensure_one()
        data = self._run(self.repo_path, self.module_name, full=True).data
        parts = []
        truncated = False
        for other in data.get("others") or []:
            diff = other.get("diff") or {}
            if diff.get("patch"):
                parts.append(f"# Odoo {other.get('version')} — {other.get('path')}\n")
                parts.append(diff["patch"])
            truncated = truncated or bool(diff.get("patch_truncated"))
        self.write(
            dict(
                self._vals_from(data, self.repo_path, self.module_name),
                full_diff="\n".join(parts) or self.env._("No difference."),
                full_diff_date=fields.Datetime.now(),
                full_diff_truncated=truncated,
            )
        )
        return self._action_open()

    def _action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    # ── rendering ───────────────────────────────────────────────────────

    def _html_table(self, headers, rows):
        head = _join(Markup("<th>%s</th>") % h for h in headers)
        body = _join(
            Markup("<tr>%s</tr>") % _join(Markup("<td>%s</td>") % c for c in row)
            for row in rows
        )
        return Markup(
            "<table class='table table-sm o_erplibre_info_table'>"
            "<thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
        ) % (head, body)

    def _commit_rows(self, commits):
        rows = []
        for c in commits:
            match = c.get("match") or {}
            rows.append(
                (
                    c.get("module") or "",
                    Markup("<code>%s</code>") % (c.get("sha") or "")[:10],
                    c.get("subject") or "",
                    c.get("author") or "",
                    (c.get("date") or "")[:10],
                    (
                        f"{match.get('by')} {(match.get('sha') or '')[:10]}"
                        if match
                        else ""
                    ),
                )
            )
        return rows

    def _p(self, text, css="text-muted"):
        return Markup("<p class='%s'>%s</p>") % (css, text)

    def _commit_headers(self):
        _ = self.env._
        return [
            _("Module"),
            _("Commit"),
            _("Subject"),
            _("Author"),
            _("Date"),
            _("Match"),
        ]

    def _render(self, data):
        if data.get("error") and not data.get("others"):
            return self._p(data["error"], "text-danger")
        parts = [
            self._render_other(other, data.get("version"))
            for other in data.get("others") or []
        ]
        if not parts:
            parts.append(
                self._p(
                    self.env._(
                        "No other Odoo version of this checkout holds this path."
                    )
                )
            )
        return _join(parts)

    def _render_other(self, other, version):
        _ = self.env._
        parts = [
            Markup("<h4>Odoo %s — <code>%s</code></h4>")
            % (other.get("version"), other.get("path"))
        ]
        if not other.get("present"):
            parts.append(self._p(_("Not cloned.")))
            return _join(parts)
        if other.get("error"):
            parts.append(self._p(other["error"], "text-danger"))
        parts.append(
            Markup("<p>HEAD <code>%s</code> %s · %s</p>")
            % (
                (other.get("head") or "")[:12],
                other.get("branch") or "",
                _("fork") if other.get("fork") else _("not a fork"),
            )
        )
        parts.append(Markup("<h5>%s</h5>") % _("Modules"))
        parts.append(
            self._html_table(
                [_("Module"), _("Here"), _("There")],
                [
                    (
                        m.get("name"),
                        (m.get("here") or {}).get("version") or _("absent"),
                        (m.get("there") or {}).get("version") or _("absent"),
                    )
                    for m in other.get("modules") or []
                ],
            )
        )
        parts.append(self._render_commits(other))
        parts.append(self._render_history(other, version))
        parts.append(self._render_diff(other))
        return _join(parts)

    def _render_commits(self, other):
        _ = self.env._
        reasons = {
            "not_a_fork": _("not a fork: no upstream base separates our commits"),
            "upstream_base_unknown": _(
                "the upstream base is unknown (shallow clone or upstream "
                "not fetched)"
            ),
        }
        parts = [Markup("<h5>%s</h5>") % _("Commits to port")]
        to_port = other.get("to_port")
        if to_port is None:
            reason = other.get("to_port_reason")
            parts.append(self._p(reasons.get(reason, reason or "")))
        elif not to_port:
            parts.append(self._p(_("None.")))
        else:
            parts.append(
                self._html_table(self._commit_headers(), self._commit_rows(to_port))
            )
        if other.get("truncated"):
            parts.append(
                self._p(
                    _(
                        "Our commits were read up to the limit: the list may "
                        "be incomplete."
                    )
                )
            )
        ported = other.get("ported") or []
        if ported:
            parts.append(
                Markup("<h5>%s (%s)</h5>") % (_("Already ported"), len(ported))
            )
            parts.append(
                self._html_table(self._commit_headers(), self._commit_rows(ported))
            )
        return _join(parts)

    def _history_cell(self, commit):
        if not commit:
            return ""
        return Markup("<code>%s</code> %s <span class='text-muted'>%s</span>") % (
            (commit.get("sha") or "")[:10],
            commit.get("subject") or "",
            (commit.get("date") or "")[:10],
        )

    def _render_history(self, other, version):
        _ = self.env._
        history = other.get("history") or {}
        if not history:
            return Markup("")
        parts = [Markup("<h5>%s</h5>") % _("History side by side")]
        if other.get("history_truncated"):
            parts.append(
                self._p(
                    _(
                        "Only some modules are shown, those that differ "
                        "first: choose a module for its full history."
                    )
                )
            )
        headers = [
            _("Odoo %(version)s (here)", version=version),
            _("Odoo %(version)s", version=other.get("version")),
        ]
        for module, sides in sorted(history.items()):
            here = sides.get("here") or []
            there = sides.get("there") or []
            rows = [
                [
                    self._history_cell(side[i] if i < len(side) else None)
                    for side in (here, there)
                ]
                for i in range(max(len(here), len(there)))
            ]
            parts.append(Markup("<h6>%s</h6>") % module)
            parts.append(self._html_table(headers, rows))
        return _join(parts)

    def _render_diff(self, other):
        _ = self.env._
        diff = other.get("diff") or {}
        parts = []
        modules = diff.get("modules") or {}
        if modules:
            parts.append(Markup("<h5>%s</h5>") % _("Code difference"))
            rows = [
                (
                    module,
                    stat.get("files") or 0,
                    f"+{stat.get('added') or 0}",
                    f"-{stat.get('removed') or 0}",
                )
                for module, stat in sorted(modules.items())
            ]
            parts.append(
                self._html_table(
                    [_("Module"), _("Files"), _("Added"), _("Removed")], rows
                )
            )
            paths = [
                (
                    p.get("path"),
                    f"+{p.get('added') or 0}",
                    f"-{p.get('removed') or 0}",
                )
                for stat in modules.values()
                for p in stat.get("paths") or []
            ]
            count = sum(stat.get("files") or 0 for stat in modules.values())
            if paths:
                shown = min(len(paths), PATHS_SHOWN)
                table = self._html_table(
                    [_("File"), _("Added"), _("Removed")], paths[:shown]
                )
                if count > shown:
                    table += self._p(
                        _(
                            "%(shown)s of %(count)s files are listed.",
                            shown=shown,
                            count=count,
                        )
                    )
                parts.append(
                    Markup("<details><summary>%s</summary>%s</details>")
                    % (_("%(count)s files", count=count), table)
                )
        if diff.get("error"):
            parts.append(self._p(diff["error"], "text-danger"))
        return _join(parts)
