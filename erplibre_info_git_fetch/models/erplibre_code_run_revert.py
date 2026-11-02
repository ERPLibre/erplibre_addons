# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The return to a snapshot, run by ``script/git/repo_pull.py --mode
instantane``.

Two run types: ``snapshot_revert_dry_run`` classifies each repository
against the commit, the branch or the detached HEAD the snapshot recorded,
and ``snapshot_revert`` moves them there, pinned to what the dry run
showed. The targets are frozen in ``revert_targets`` when the dry run is
started, and written to a temporary JSON file for each script call: the
apply step reads the same targets as its dry run.

The apply step keeps the stash of a modified tree, never reapplied: each
one becomes an ``erplibre.code.stash`` record, reapplied on request with
``--apply-stash``.
"""

import contextlib
import json
import os
import tempfile

from markupsafe import Markup
from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.erplibre_info import runner
from .erplibre_code_run import EXIT_PLAN_CHANGED
from .erplibre_code_run_pull import _short

# The verdicts of a dry run that leave a repository where it is.
VERDICTS_LEFT = (
    "commit_introuvable",
    "operation_en_cours",
    "erreur",
    "fetch_echoue",
    "absent",
)


class ErplibreCodeRunRevert(models.Model):
    _inherit = "erplibre.code.run"

    revert_snapshot_id = fields.Many2one(
        "erplibre.code.snapshot",
        string="Snapshot to return to",
        readonly=True,
        ondelete="set null",
    )
    revert_root = fields.Boolean(
        string="ERPLibre root returned too",
        readonly=True,
        help="The ERPLibre root goes back to the commit of the snapshot, "
        "after the other repositories; the local manifest is then "
        "regenerated.",
    )
    revert_targets = fields.Text(
        string="Snapshot targets",
        readonly=True,
        help="The JSON file of targets given to repo_pull.py: the commit, "
        "branch and remote of each repository of the snapshot.",
    )
    approve_modules = fields.Boolean(
        string="Newer modules accepted",
        readonly=True,
        help="Modules installed with a newer version than the snapshot "
        "were listed, and the return was confirmed anyway.",
    )
    stash_ids = fields.One2many("erplibre.code.stash", "run_id", string="Stashes")

    # ── script calls ────────────────────────────────────────────────────

    @contextlib.contextmanager
    def _revert_targets_file(self):
        """Yield the path of a temporary file holding ``revert_targets``,
        removed once the script call returns."""
        self.ensure_one()
        handle, path = tempfile.mkstemp(prefix="erplibre_revert_", suffix=".json")
        try:
            with os.fdopen(handle, "w") as fh:
                fh.write(self.revert_targets or "{}")
            yield path
        finally:
            with contextlib.suppress(OSError):
                os.unlink(path)

    def _execute_snapshot_revert_dry_run(self):
        self._check_git_fetch_in_background()
        with self._revert_targets_file() as path:
            res = self._run_pull(
                ["--dry-run", "--mode", "instantane", "--targets", path, "--json"]
            )
        data = res.data
        repos = data.get("depots") or []
        left = sorted(
            r.get("chemin") or "" for r in repos if r.get("verdict") in VERDICTS_LEFT
        )
        snapshot = self.revert_snapshot_id
        data["odoo_modules"] = snapshot._revert_newer_modules() if snapshot else []
        self.write(
            {
                "odoo_version": data.get("version"),
                "plan_paths": "\n".join(data.get("plan") or []),
                "left_paths": "\n".join(left),
                "exit_code": res.returncode,
                "result_json": json.dumps(data, ensure_ascii=False),
                "log": self._script_log(res),
            }
        )

    def _revert_args(self, path, stamp):
        """The arguments of the apply step: the targets file ``path``, the
        Odoo version typed again, the stamp and the time budget of the
        pass, and each path of the plan pinned to the target and the HEAD
        the dry run showed."""
        self.ensure_one()
        args = [
            "--apply",
            "--mode",
            "instantane",
            "--targets",
            path,
            "--confirm",
            self.odoo_version or "",
            "--pass",
            stamp,
            "--budget",
            str(self._pull_budget()),
            "--json",
        ]
        for value in self._parent_data().get("attendus") or []:
            args += ["--expect", value]
        return args

    def _execute_snapshot_revert(self):
        self._check_git_fetch_in_background()
        stamp = self._pull_stamp()
        try:
            with self._revert_targets_file() as path:
                res = self._run_pull(
                    self._revert_args(path, stamp), ok_codes=(0, EXIT_PLAN_CHANGED)
                )
        except runner.RunnerError as exc:
            self._pull_apply_failed(stamp, exc)
            return
        data = res.data
        results = data.get("resultats") or []
        vals = {
            "exit_code": res.returncode,
            "result_json": json.dumps(data, ensure_ascii=False),
            "pass_dir": data.get("dossier"),
            "deps_to_install": bool((data.get("dependances") or {}).get("a_installer")),
            "pull_blocked": any(
                r.get("etat") == "restauration_echouee" for r in results
            ),
            "log": self._script_log(res),
        }
        if res.returncode == EXIT_PLAN_CHANGED:
            vals.update(
                state="failed",
                date_end=fields.Datetime.now(),
                deps_to_install=False,
                log=self._append_log(
                    "\n".join(
                        [
                            vals["log"],
                            self.env._(
                                "The dry run is out of date: a HEAD moved, or "
                                "the list of repositories to return changed. "
                                "Nothing was written; run a new dry run."
                            ),
                        ]
                    )
                ),
            )
            self.write(vals)
            return
        self.write(vals)
        self.env["erplibre.code.pull.backup"].create(
            [
                {
                    "run_id": self.id,
                    "path": r.get("chemin"),
                    "branch_name": r["sauvegarde"],
                    "sha": r.get("depart"),
                    "original_branch": r.get("branche"),
                    "detached": bool(r.get("detache")),
                }
                for r in results
                if r.get("sauvegarde")
            ]
        )
        self._import_kept_stashes(results)
        if not data.get("dossier"):
            self.log = self._append_log(
                self.env._("Nothing to return: nothing was written.")
            )
            return
        self._record_code_change(data)

    def _import_kept_stashes(self, results):
        """Record the stashes that the results of a pass keep in their
        clone (``stash.etat`` « garde »), once per path and commit. Return
        the new records."""
        self.ensure_one()
        known = {(s.path, s.sha) for s in self.stash_ids}
        vals_list = []
        for res in results or []:
            stash = res.get("stash") or {}
            key = (res.get("chemin"), stash.get("sha"))
            if stash.get("etat") != "garde" or not all(key) or key in known:
                continue
            known.add(key)
            vals_list.append(
                {
                    "run_id": self.id,
                    "path": key[0],
                    "sha": key[1],
                    "message": stash.get("message") or False,
                    "command": stash.get("commande") or False,
                }
            )
        return self.env["erplibre.code.stash"].create(vals_list)

    # ── actions ─────────────────────────────────────────────────────────

    def _check_revert_applicable(self):
        self.ensure_one()
        if self.run_type != "snapshot_revert_dry_run" or not self.can_apply:
            raise UserError(self.env._("This dry run has nothing left to apply."))

    def _revert_newer_modules(self):
        """The modules installed with a newer version than the snapshot of
        this dry run (see ``erplibre.code.snapshot._revert_newer_modules``),
        read now; the list recorded by the dry run when its snapshot is
        gone."""
        self.ensure_one()
        if self.revert_snapshot_id:
            return self.revert_snapshot_id._revert_newer_modules()
        return self._result_data().get("odoo_modules") or []

    def _result_data(self):
        """The JSON result of this run, ``{}`` when it is unreadable."""
        self.ensure_one()
        try:
            data = json.loads(self.result_json or "{}")
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    def action_snapshot_revert(self):
        """Open the confirmation of the return: the first validation."""
        self.ensure_one()
        self._check_git_fetch()
        self._check_revert_applicable()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "snapshot_revert", run=self
        )

    def _launch_snapshot_revert(self, approve_modules=False):
        """Queue the apply step of this dry run; called by the confirmed
        wizard, the second validation. A module installed with a newer
        version than the snapshot requires ``approve_modules``."""
        self.ensure_one()
        self._check_git_fetch()
        self._check_revert_applicable()
        newer = self._revert_newer_modules()
        if newer and not approve_modules:
            raise UserError(
                self.env._(
                    "Modules are installed with a newer version than the "
                    "snapshot: tick the box that accepts them."
                )
            )
        self._check_no_git_run()
        run = self._create_launched(
            {
                "run_type": "snapshot_revert",
                "parent_id": self.id,
                "odoo_version": self.odoo_version,
                "plan_paths": self.plan_paths,
                "left_paths": self.left_paths,
                "revert_snapshot_id": self.revert_snapshot_id.id,
                "revert_root": self.revert_root,
                "revert_targets": self.revert_targets,
                "approve_modules": bool(newer and approve_modules),
            }
        )
        run._enqueue()
        return run._action_open()

    # ── labels ──────────────────────────────────────────────────────────

    def _revert_verdict_labels(self):
        """{verdict: (label, css class)} of a repository in a dry run."""
        _ = self.env._
        return {
            "a_jour": (_("already on the snapshot"), "text-muted"),
            "recul": (_("back to an older commit"), "text-success"),
            "deplacement": (
                _("move off the current history"),
                "text-warning",
            ),
            "commit_introuvable": (
                _("commit not found: skipped"),
                "text-danger",
            ),
            "absent": (_("not cloned"), "text-muted"),
            "operation_en_cours": (
                _("operation in progress: skipped"),
                "text-danger",
            ),
            "erreur": (_("error"), "text-danger"),
            "fetch_echoue": (_("fetch failed"), "text-danger"),
        }

    def _revert_state_labels(self):
        """{state: (label, css class)} of a repository after a return."""
        _ = self.env._
        labels = dict(self._pull_state_labels())
        labels.update(
            recule=(_("returned to the snapshot"), "text-success"),
            a_jour=(_("already on the snapshot"), "text-muted"),
            saute_introuvable=(_("commit not found: skipped"), "text-danger"),
        )
        return labels

    # ── rendering ───────────────────────────────────────────────────────

    def _target_text(self, repo):
        """« branch @ commit » of a target, « detached @ commit » without a
        branch."""
        branch = repo.get("cible_branche") or self.env._("detached")
        return f"{branch} @ {_short(repo.get('cible_sha'))}"

    def _render_newer_modules(self, modules):
        """The red list of the modules installed with a newer version than
        the snapshot; empty markup without one."""
        _ = self.env._
        if not modules:
            return Markup("")
        rows = [
            Markup("<tr><td>%s</td><td>%s</td><td>%s</td></tr>")
            % (
                m.get("name") or "",
                m.get("snapshot_version") or _("not installed"),
                m.get("installed_version") or "",
            )
            for m in modules
        ]
        return Markup(
            "<div class='alert alert-danger' role='alert'><p>%s</p>%s</div>"
        ) % (
            _(
                "These modules are installed with a newer version than the "
                "snapshot: the returned code is older than their data. The "
                "return asks for one more confirmation."
            ),
            self._html_table(
                [_("Module"), _("Snapshot version"), _("Installed version")],
                rows,
            ),
        )

    def _render_snapshot_revert_dry_run(self, data):
        _ = self.env._
        verdicts = self._revert_verdict_labels()
        header = []
        if self.revert_snapshot_id:
            header.append(
                _(
                    "Snapshot: %(name)s",
                    name=self.revert_snapshot_id.display_name,
                )
            )
        header.append(
            _("ERPLibre root returned too")
            if self.revert_root
            else _("ERPLibre root left as it is")
        )
        html = Markup("<p>%s</p>") % Markup(" · ").join(header)
        if data.get("error"):
            html += Markup("<p class='text-danger'>%s</p>") % data["error"]
        for error in data.get("errors") or []:
            html += Markup("<p class='text-danger'>%s</p>") % error
        html += self._render_newer_modules(data.get("odoo_modules"))
        rows = []
        for repo in data.get("depots") or []:
            verdict = repo.get("verdict") or ""
            label, css = verdicts.get(verdict, (verdict, "text-muted"))
            reason = repo.get("motif") or repo.get("erreur")
            branch = repo.get("branche") or _("detached")
            modified = []
            if repo.get("sale"):
                modified.append(
                    _("yes (stash kept)") if repo.get("stash_prevu") else _("yes")
                )
            if repo.get("non_suivis"):
                modified.append(_("%(count)s untracked", count=repo.get("non_suivis")))
            if repo.get("ecrases"):
                modified.append(
                    _(
                        "ignored files the target overwrites, copied first: "
                        "%(files)s",
                        files=", ".join(repo["ecrases"]),
                    )
                )
            local = repo.get("locaux") or 0
            backup = ""
            if repo.get("applicable"):
                backup = Markup("<code>%s</code>%s") % (
                    repo.get("sauvegarde_prefixe") or "",
                    _("<date of the apply>"),
                )
            rows.append(
                Markup(
                    "<tr><td>%s</td><td>%s</td><td class='%s'>%s%s</td>"
                    "<td class='text-end'>%s</td><td class='text-end %s'>%s</td>"
                    "<td>%s</td><td>%s</td></tr>"
                )
                % (
                    repo.get("chemin") or "",
                    f"{branch} → {self._target_text(repo)}",
                    css,
                    label,
                    (
                        Markup("<br/><small>%s</small>") % reason
                        if reason
                        else Markup("")
                    ),
                    repo.get("quittes") or 0,
                    "text-danger" if local else "",
                    local,
                    ", ".join(modified),
                    backup,
                )
            )
        html += self._html_table(
            [
                _("Repository"),
                _("Branch → target"),
                _("Verdict"),
                _("Commits left behind"),
                _("Local commits only in the backup"),
                _("Modified"),
                _("Backup"),
            ],
            rows,
        )
        if any(
            r.get("locaux") and r.get("applicable") for r in data.get("depots") or []
        ):
            html += Markup("<p class='text-warning'>%s</p>") % _(
                "Local commits are on no remote: after the return, only the "
                "backup branch keeps them."
            )
        if any(r.get("stash_prevu") for r in data.get("depots") or []):
            html += Markup("<p class='text-muted'>%s</p>") % _(
                "A modified tree is stashed before the return and the stash is "
                "kept, never reapplied: it is listed in Stashes, where it can "
                "be reapplied."
            )
        if data.get("hors_instantane"):
            html += self._html_section(
                _("Repositories outside the snapshot (left as they are)"),
                self._html_list(data["hors_instantane"]),
            )
        html += self._render_pull_deps(data.get("dependances"))
        return html

    def _render_snapshot_revert(self, data):
        _ = self.env._
        states = self._revert_state_labels()
        html = Markup("")
        if data.get("error"):
            html += Markup("<p class='text-danger'>%s</p>") % data["error"]
        if data.get("budget_epuise"):
            html += Markup(
                "<div class='alert alert-warning' role='alert'>%s</div>"
            ) % _(
                "The time budget of the pass ran out: the repositories marked "
                "« not started » were left as they are; run a new dry run for "
                "them."
            )
        results = data.get("resultats") or []
        if any(r.get("etat") == "restauration_echouee" for r in results):
            html += Markup("<div class='alert alert-danger' role='alert'>%s</div>") % _(
                "A repository is left mid-operation: fix it in a terminal "
                "before restarting."
            )
        for drift in data.get("derives") or []:
            html += Markup("<p class='text-danger'>%s: %s — %s → %s</p>") % (
                drift.get("chemin") or "",
                drift.get("cle") or "",
                drift.get("attendu") or "",
                drift.get("trouve") or "",
            )
        rows = []
        for res in results:
            label, css = states.get(res.get("etat"), (res.get("etat") or "", ""))
            stash = res.get("stash") or {}
            if stash.get("etat") == "garde":
                stash_cell = Markup("%s<br/><code>%s</code>") % (
                    _("kept"),
                    stash.get("commande") or stash.get("sha") or "",
                )
            elif stash.get("etat") == "reapplique":
                stash_cell = _("reapplied")
            else:
                stash_cell = ""
            backups = Markup("<br/>").join(
                Markup("<code>%s</code>") % name
                for name in (
                    res.get("sauvegarde"),
                    res.get("sauvegarde_cible"),
                )
                if name
            )
            reason = res.get("motif")
            if res.get("ecrases") and res.get("copie_ecrases"):
                reason = " ".join(
                    x
                    for x in (
                        reason,
                        _(
                            "Ignored files overwritten, copied first to "
                            "%(path)s: %(files)s",
                            path=res["copie_ecrases"],
                            files=", ".join(res["ecrases"]),
                        ),
                    )
                    if x
                )
            arrival = res.get("branche_arrivee")
            if res.get("etat") == "recule" and not arrival:
                arrival = _("detached")
            rows.append(
                Markup(
                    "<tr><td>%s</td><td class='%s'>%s%s</td><td>%s</td>"
                    "<td>%s</td><td><code>%s</code></td><td><code>%s</code></td>"
                    "<td>%s</td></tr>"
                )
                % (
                    res.get("chemin") or "",
                    css,
                    label,
                    (
                        Markup("<br/><small>%s</small>") % reason
                        if reason
                        else Markup("")
                    ),
                    arrival or "",
                    backups,
                    (res.get("depart") or "")[:12],
                    (res.get("arrivee") or "")[:12],
                    stash_cell,
                )
            )
        if rows:
            html += self._html_table(
                [
                    _("Repository"),
                    _("Result"),
                    _("Branch"),
                    _("Backup"),
                    _("From"),
                    _("To"),
                    _("Stash"),
                ],
                rows,
            )
        elif data.get("command") == "apply" and not data.get("error"):
            html += Markup("<p class='text-muted'>%s</p>") % _(
                "Nothing to return: nothing was written."
            )
        html += self._render_pull_manifest(data.get("manifeste"))
        deps = data.get("dependances") or {}
        html += self._render_pull_deps(deps)
        if deps.get("a_installer"):
            html += Markup("<p class='text-muted'>%s</p>") % _(
                "Install them with « Install the Python dependencies », or "
                "restart without installing."
            )
        return html
