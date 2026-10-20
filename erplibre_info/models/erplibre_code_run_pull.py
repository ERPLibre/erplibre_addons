# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The pull of the deployed code, run by ``script/git/repo_pull.py``.

Four run types: ``pull_dry_run`` fetches and shows what a pull would do,
``pull_apply`` pulls the repositories pinned to the commits the dry run
showed, ``pull_restore`` moves a repository back to a backup branch, and
``deps_install`` runs ``poetry install`` in the Odoo virtual environment.
The script owns every git call; these methods build its arguments, record
its JSON and render it.

The apply step gives the script a time budget below the timeout of its
call, and the stamp of its pass: past the budget the script starts nothing
new and still answers, and a call killed anyway leaves its backup branches
under a known stamp, which ``--list-backups`` reads back.
"""

import datetime
import json
import os

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import UserError

from .. import runner
from .erplibre_code_run import EXIT_PLAN_CHANGED

# Exit codes of « repo_pull.py ».
EXIT_NOT_FOUND = 3
EXIT_BUSY = 5
EXIT_DEPS = 6

# The states of a pulled repository whose HEAD moved.
STATES_MOVED = ("avance", "tire", "stash_garde")

# How many incoming commits a dry run shows per repository, at most.
INCOMING_SHOWN = 50

# The seconds of the long timeout kept back from the budget of an apply, at
# most: the repository in progress when the budget runs out finishes within
# them. A quarter of the timeout is kept back when it is shorter.
BUDGET_MARGIN = 900


def _short(ref):
    """A target for a table cell: the remote branch without its
    ``refs/remotes/`` prefix, a tag without the namespace the script
    fetches it into, a commit as 12 characters."""
    ref = ref or ""
    for prefix in (
        "refs/remotes/",
        "refs/heads/",
        "refs/repo_pull/tags/",
        "refs/tags/",
    ):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    if len(ref) == 40 and all(c in "0123456789abcdef" for c in ref):
        return ref[:12]
    return ref


class ErplibreCodeRunPull(models.Model):
    _inherit = "erplibre.code.run"

    # ── script calls ────────────────────────────────────────────────────

    @api.model
    def _pull_budget(self):
        """The seconds the apply script may spend: the long timeout minus
        ``BUDGET_MARGIN``, or minus a quarter when that is less."""
        long_timeout = runner.timeout(self.env, long=True)
        return max(1, long_timeout - min(BUDGET_MARGIN, long_timeout // 4))

    @api.model
    def _pull_stamp(self):
        """The stamp of a new pass, as the script writes it: local time to
        the minute."""
        return datetime.datetime.now().strftime("%Y%m%dT%H%M")

    def _run_pull(self, args, ok_codes=(0,)):
        """``repo_pull.py`` with ``args`` under the long timeout; return the
        ``runner.Result``. Raise ``runner.RunnerError`` on an exit code
        outside ``ok_codes``; the lock held by another pass of the same
        checkout has its own message."""
        res = runner.run_json(
            self.env,
            runner.SCRIPT_PULL,
            args,
            runner.timeout(self.env, long=True),
            ok_codes=tuple(ok_codes) + (EXIT_BUSY,),
        )
        if res.returncode == EXIT_BUSY and EXIT_BUSY not in ok_codes:
            raise runner.RunnerError(
                self.env._("Another pull is running on this checkout.")
            )
        return res

    def _script_log(self, res):
        return self._append_log(
            "\n".join(x for x in (res.command, (res.stderr or "").strip()) if x)
        )

    def _parent_data(self):
        self.ensure_one()
        try:
            data = json.loads(self.parent_id.result_json or "{}")
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    def _execute_pull_dry_run(self):
        self._check_flag_in_background()
        args = [
            "--dry-run",
            "--mode",
            self.pull_mode or "manifeste",
            "--strategy",
            self.pull_strategy or "rebase",
        ]
        if self.pull_path:
            args += ["--path", self.pull_path]
        args.append("--json")
        res = self._run_pull(args)
        data = res.data
        repos = data.get("depots") or []
        left = sorted(
            r.get("chemin") or ""
            for r in repos
            if (r.get("verdict") == "diverge" and not r.get("applicable"))
            or r.get("verdict") == "operation_en_cours"
        )
        self.write(
            {
                "odoo_version": data.get("version"),
                "plan_paths": "\n".join(data.get("plan") or []),
                "shallow_paths": "\n".join(data.get("plan_superficiel") or []),
                "clone_paths": "\n".join(data.get("plan_nouveaux") or []),
                "left_paths": "\n".join(left),
                "exit_code": res.returncode,
                "result_json": json.dumps(data, ensure_ascii=False),
                "log": self._script_log(res),
            }
        )

    def _pull_args(self, stamp):
        """The arguments of the apply step: the mode, strategy and single
        repository of the dry run, the Odoo version typed again, the stamp
        and the time budget of the pass, and each path of the plan pinned
        to the target and the HEAD the dry run showed. The shallow clones
        and the new repositories join only when the confirmation allowed
        them."""
        self.ensure_one()
        data = self._parent_data()
        args = [
            "--apply",
            "--mode",
            self.pull_mode or "manifeste",
            "--strategy",
            self.pull_strategy or "rebase",
        ]
        if self.pull_path:
            args += ["--path", self.pull_path]
        args += [
            "--confirm",
            self.odoo_version or "",
            "--pass",
            stamp,
            "--budget",
            str(self._pull_budget()),
            "--json",
        ]
        expected = list(data.get("attendus") or [])
        if self.approve_deepen:
            expected += data.get("attendus_superficiel") or []
        for value in expected:
            args += ["--expect", value]
        if self.approve_deepen:
            args.append("--approve-deepen")
        if self.approve_clone:
            args.append("--approve-clone")
            for path in data.get("plan_nouveaux") or []:
                args += ["--expect-clone", path]
        return args

    def _import_pull_backups(self, stamp):
        """Record the backup branches of the pass ``stamp`` that this run
        does not hold yet, read with ``--list-backups``. Return them."""
        self.ensure_one()
        try:
            res = runner.run_json(
                self.env, runner.SCRIPT_PULL, ["--list-backups", "--json"]
            )
        except runner.RunnerError as exc:
            self.log = self._append_log(str(exc))
            return self.env["erplibre.code.pull.backup"]
        known = {(b.path, b.branch_name) for b in self.backup_ids}
        return self.env["erplibre.code.pull.backup"].create(
            [
                {
                    "run_id": self.id,
                    "path": b.get("chemin"),
                    "branch_name": b.get("nom"),
                    "sha": b.get("sha"),
                    "original_branch": b.get("branche"),
                    "detached": bool(b.get("detache")),
                }
                for b in res.data.get("sauvegardes") or []
                if b.get("horodatage") == stamp
                and b.get("chemin")
                and (b.get("chemin"), b.get("nom")) not in known
            ]
        )

    def _pull_apply_failed(self, stamp, error):
        """Record an apply whose script call failed: the backups its pass
        made are read back, and a call killed by its timeout may have left
        a repository mid-operation, so the restart stays blocked until a
        new dry run."""
        self.ensure_one()
        backups = self._import_pull_backups(stamp)
        log = [str(error)]
        if backups:
            log.append(
                self.env._(
                    "Backup branches of this pass read back: %(count)s.",
                    count=len(backups),
                )
            )
        root = runner.erplibre_root(self.env)
        pass_dir = os.path.join("tasks", "git_repo_pull", stamp)
        self.write(
            {
                "state": "failed",
                "date_end": fields.Datetime.now(),
                "pass_dir": (
                    pass_dir
                    if root and os.path.isdir(os.path.join(root, pass_dir))
                    else False
                ),
                "pull_blocked": isinstance(error, runner.RunnerTimeout),
                "log": self._append_log("\n".join(log)),
            }
        )

    def _execute_pull_apply(self):
        self._check_flag_in_background()
        stamp = self._pull_stamp()
        try:
            res = self._run_pull(
                self._pull_args(stamp), ok_codes=(0, EXIT_PLAN_CHANGED)
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
                                "The dry run is out of date: a remote or a "
                                "HEAD moved, or the list of repositories "
                                "changed. Nothing was written; run a new dry "
                                "run."
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
        if not data.get("dossier"):
            self.log = self._append_log(
                self.env._("Nothing to pull: nothing was written.")
            )
            return
        self._record_code_change(data)

    def _execute_pull_restore(self):
        self._check_flag_in_background()
        backup = self.backup_id
        if not backup:
            raise UserError(self.env._("No backup to restore."))
        res = self._run_pull(
            [
                "--restore-backup",
                f"{backup.path}={backup.branch_name}",
                "--confirm",
                self.odoo_version or "",
                "--json",
            ],
            ok_codes=(0, EXIT_NOT_FOUND),
        )
        data = res.data
        result = (data.get("resultats") or [{}])[0]
        state = result.get("etat")
        self.write(
            {
                "exit_code": res.returncode,
                "result_json": json.dumps(data, ensure_ascii=False),
                "log": self._script_log(res),
            }
        )
        label = self._pull_state_label(state) if state else data.get("error")
        backup.log = "\n".join(
            x
            for x in (
                backup.log,
                f"{fields.Datetime.to_string(fields.Datetime.now())} "
                f"{self.name}: {label or ''}",
            )
            if x
        )
        if state == "revenu":
            backup.state = "restored"
        elif state == "sauvegarde_absente" or res.returncode == EXIT_NOT_FOUND:
            backup.state = "missing"
        if state != "revenu":
            self.write(
                {
                    "state": "failed",
                    "date_end": fields.Datetime.now(),
                    "log": self._append_log(
                        self.env._(
                            "The backup was not restored: %(reason)s",
                            reason=label or "",
                        )
                    ),
                }
            )
            return
        self._record_code_change(data)

    def _execute_deps_install(self):
        self._check_flag_in_background()
        args = ["--install-deps", "--confirm", self.odoo_version or ""]
        stamp = os.path.basename(self.parent_id.pass_dir or "")
        if stamp:
            args += ["--pass", stamp]
        args.append("--json")
        res = self._run_pull(args, ok_codes=(0, EXIT_DEPS))
        vals = {
            "exit_code": res.returncode,
            "result_json": json.dumps(res.data, ensure_ascii=False),
            "log": self._script_log(res),
        }
        if res.returncode == EXIT_DEPS:
            vals.update(
                state="failed",
                date_end=fields.Datetime.now(),
                log=self._append_log(
                    "\n".join(
                        x
                        for x in (
                            vals["log"],
                            res.data.get("error"),
                            res.data.get("sortie"),
                        )
                        if x
                    )
                ),
            )
        self.write(vals)

    # ── actions ─────────────────────────────────────────────────────────

    def _check_pull_applicable(self):
        self.ensure_one()
        if self.run_type != "pull_dry_run" or not self.can_apply:
            raise UserError(self.env._("This dry run has nothing left to apply."))

    def action_pull_apply(self):
        """Open the confirmation of the pull: the first validation."""
        self.ensure_one()
        self._check_server_actions()
        self._check_pull_applicable()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "pull_apply", run=self
        )

    def _launch_pull_apply(self, approve_deepen=False, approve_clone=False):
        """Queue the apply step of this pull dry run; called by the
        confirmed wizard, the second validation. A permission is kept only
        when the dry run has something it allows."""
        self.ensure_one()
        self._check_server_actions()
        self._check_pull_applicable()
        self._check_no_git_run()
        run = self._create_launched(
            {
                "run_type": "pull_apply",
                "parent_id": self.id,
                "odoo_version": self.odoo_version,
                "pull_mode": self.pull_mode,
                "pull_strategy": self.pull_strategy,
                "pull_path": self.pull_path,
                "plan_paths": self.plan_paths,
                "shallow_paths": self.shallow_paths,
                "clone_paths": self.clone_paths,
                "left_paths": self.left_paths,
                "approve_deepen": bool(approve_deepen and self.shallow_paths),
                "approve_clone": bool(approve_clone and self.clone_paths),
            }
        )
        run._enqueue()
        return run._action_open()

    def _check_deps_installable(self):
        self.ensure_one()
        if not (
            self.run_type == "pull_apply"
            and self.state == "done"
            and self.deps_to_install
            and not self.pull_blocked
        ):
            raise UserError(
                self.env._("This run has no Python dependencies to install.")
            )

    def action_deps_install(self):
        self.ensure_one()
        self._check_server_actions()
        self._check_deps_installable()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "deps_install", run=self
        )

    def _launch_deps_install(self):
        """Queue ``poetry install`` after this pull; the modules it proposes
        to upgrade carry over."""
        self.ensure_one()
        self._check_server_actions()
        self._check_deps_installable()
        self._check_no_git_run()
        run = self._create_launched(
            {
                "run_type": "deps_install",
                "parent_id": self.id,
                "odoo_version": self.odoo_version,
                "upgrade_module_ids": [fields.Command.set(self.upgrade_module_ids.ids)],
                "code_changed_module_ids": [
                    fields.Command.set(self.code_changed_module_ids.ids)
                ],
                "version_pending_module_ids": [
                    fields.Command.set(self.version_pending_module_ids.ids)
                ],
            }
        )
        run._enqueue()
        return run._action_open()

    # ── labels ──────────────────────────────────────────────────────────

    def _pull_verdict_labels(self):
        """{verdict: (label, css class)} of a repository in a dry run."""
        _ = self.env._
        return {
            "a_jour": (_("up to date"), "text-muted"),
            "en_avance": (_("ahead of the target"), "text-muted"),
            "avance_rapide": (_("fast-forward possible"), "text-success"),
            "diverge": (_("diverged"), "text-success"),
            "bascule": (_("switch to the manifest target"), "text-success"),
            "superficiel": (_("shallow: deepening needed"), "text-warning"),
            "detache": (_("detached HEAD: skipped"), "text-muted"),
            "sans_cible": (_("no target"), "text-muted"),
            "cible_absente": (_("target missing"), "text-danger"),
            "fetch_echoue": (_("fetch failed"), "text-danger"),
            "operation_en_cours": (
                _("operation in progress: skipped"),
                "text-danger",
            ),
            "absent": (_("not cloned"), "text-muted"),
            "erreur": (_("error"), "text-danger"),
        }

    def _pull_state_labels(self):
        """{state: (label, css class)} of a repository after a pull, a
        clone, a restore or a delete."""
        _ = self.env._
        return {
            "avance": (_("fast-forwarded"), "text-success"),
            "tire": (_("pulled"), "text-success"),
            "a_jour": (_("up to date"), "text-muted"),
            "conflit_annule": (_("conflict: put back"), "text-warning"),
            "stash_garde": (_("stash kept"), "text-warning"),
            "refuse_ff": (_("diverged: fast-forward refused"), "text-warning"),
            "saute_detache": (_("detached HEAD: skipped"), "text-muted"),
            "saute_superficiel": (_("shallow: not deepened"), "text-muted"),
            "saute_delai": (
                _("not started: time budget exhausted"),
                "text-warning",
            ),
            "saute_operation": (
                _("operation in progress: skipped"),
                "text-danger",
            ),
            "superficiel_sans_base": (
                _("shallow: no base found"),
                "text-warning",
            ),
            "sauvegarde_existante": (
                _("backup already exists"),
                "text-warning",
            ),
            "restauration_echouee": (
                _("restore failed: fix by hand"),
                "text-danger",
            ),
            "erreur": (_("error"), "text-danger"),
            "clone": (_("cloned"), "text-success"),
            "clone_echoue": (_("clone failed"), "text-danger"),
            "clone_refuse": (_("clone refused"), "text-warning"),
            "clone_chemin_occupe": (_("path already occupied"), "text-warning"),
            "revenu": (_("restored"), "text-success"),
            "refuse_sale": (
                _("refused: the tree has modified files"),
                "text-warning",
            ),
            "branche_changee": (
                _("refused: the repository is on another branch"),
                "text-warning",
            ),
            "head_deplacee": (
                _(
                    "refused: HEAD moved since the pull, its new commits "
                    "would leave the branch"
                ),
                "text-warning",
            ),
            "sauvegarde_absente": (_("backup missing"), "text-warning"),
            "supprime": (_("deleted"), "text-muted"),
            "refuse_courante": (
                _("refused: the backup branch is checked out"),
                "text-warning",
            ),
        }

    def _pull_state_label(self, state):
        return self._pull_state_labels().get(state, (state, ""))[0]

    # ── rendering ───────────────────────────────────────────────────────

    def _html_table(self, headers, rows):
        head = Markup("").join(Markup("<th>%s</th>") % h for h in headers)
        return Markup(
            "<table class='table table-sm o_erplibre_info_table'><thead><tr>%s"
            "</tr></thead><tbody>%s</tbody></table>"
        ) % (head, Markup("").join(rows))

    def _html_section(self, title, body):
        return Markup("<h5 class='mt-3'>%s</h5>%s") % (title, body)

    def _html_list(self, items):
        return Markup("<ul>%s</ul>") % Markup("").join(
            Markup("<li>%s</li>") % i for i in items
        )

    def _incoming_html(self, repo):
        commits = repo.get("entrants") or []
        rows = [
            Markup("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>")
            % (
                (c.get("sha") or "")[:12],
                c.get("date") or "",
                c.get("author") or "",
                c.get("subject") or "",
            )
            for c in commits
        ]
        note = Markup("")
        if repo.get("entrants_tronques"):
            note = Markup("<p class='text-muted'>%s</p>") % self.env._(
                "Only the first %(max)s commits are shown.",
                max=len(commits) or INCOMING_SHOWN,
            )
        return Markup("<details><summary>%s</summary>%s%s</details>") % (
            self.env._(
                "%(count)s incoming commits",
                count=repo.get("entrants_total") or len(commits),
            ),
            note,
            self._html_table(
                [
                    self.env._("Commit"),
                    self.env._("Date"),
                    self.env._("Author"),
                    self.env._("Subject"),
                ],
                rows,
            ),
        )

    def _render_pull_dry_run(self, data):
        _ = self.env._
        verdicts = self._pull_verdict_labels()
        modes = dict(self._fields["pull_mode"]._description_selection(self.env))
        strategies = dict(
            self._fields["pull_strategy"]._description_selection(self.env)
        )
        header = [
            _("Mode: %(mode)s", mode=modes.get(data.get("mode"), data.get("mode"))),
            _(
                "Strategy: %(strategy)s",
                strategy=strategies.get(data.get("strategie"), data.get("strategie")),
            ),
        ]
        if data.get("chemin_seul"):
            header.append(_("Single repository: %(path)s", path=data["chemin_seul"]))
        html = Markup("<p>%s</p>") % Markup(" · ").join(header)
        for error in data.get("errors") or []:
            html += Markup("<p class='text-danger'>%s</p>") % error
        rows = []
        for repo in data.get("depots") or []:
            verdict = repo.get("verdict") or ""
            label, css = verdicts.get(verdict, (verdict, "text-muted"))
            if verdict == "diverge" and not repo.get("applicable"):
                css = "text-warning"
            reason = repo.get("motif") or repo.get("erreur")
            branch = repo.get("branche") or _("detached")
            target = _short(repo.get("cible"))
            modified = []
            if repo.get("sale"):
                modified.append(
                    _("yes (stash)") if repo.get("stash_prevu") else _("yes")
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
            ours = repo.get("locaux")
            if ours is None:
                ours = repo.get("nos")
            backup = ""
            if repo.get("applicable") or repo.get("approfondissement_requis"):
                backup = Markup("<code>%s</code>%s") % (
                    repo.get("sauvegarde_prefixe") or "",
                    _("<date of the apply>"),
                )
            rows.append(
                Markup(
                    "<tr><td>%s</td><td>%s</td><td class='%s'>%s%s</td>"
                    "<td class='text-end'>%s</td><td class='text-end'>%s</td>"
                    "<td>%s</td><td>%s</td><td>%s</td></tr>"
                )
                % (
                    repo.get("chemin") or "",
                    f"{branch} → {target}" if target else branch,
                    css,
                    label,
                    (
                        Markup("<br/><small>%s</small>") % reason
                        if reason
                        else Markup("")
                    ),
                    repo.get("retard") or 0,
                    ours or 0,
                    ", ".join(modified),
                    _("yes") if repo.get("superficiel") else "",
                    backup,
                )
            )
            if repo.get("entrants"):
                rows.append(
                    Markup("<tr><td colspan='8'>%s</td></tr>")
                    % self._incoming_html(repo)
                )
        html += self._html_table(
            [
                _("Repository"),
                _("Branch → target"),
                _("Verdict"),
                _("Incoming"),
                _("Ours"),
                _("Modified"),
                _("Shallow"),
                _("Backup"),
            ],
            rows,
        )
        if data.get("plan_superficiel"):
            html += Markup(
                "<div class='alert alert-warning' role='alert'>%s%s</div>"
            ) % (
                _(
                    "Deepening downloads history: tick the box at the apply "
                    "to allow it."
                ),
                self._html_list(data["plan_superficiel"]),
            )
        html += self._render_pull_manifest(data.get("manifeste"))
        new = data.get("nouveaux") or []
        if new:
            items = []
            for repo in new:
                text = " · ".join(
                    x
                    for x in (
                        repo.get("chemin"),
                        repo.get("url"),
                        repo.get("revision"),
                    )
                    if x
                )
                if repo.get("occupe"):
                    text += " — " + _("path already occupied")
                items.append(text)
            html += self._html_section(
                _("New repositories"),
                Markup("<p class='text-muted'>%s</p>%s")
                % (
                    _(
                        "Cloned only when it is allowed at the apply, by a "
                        "repo sync restricted to their paths."
                    ),
                    self._html_list(items),
                ),
            )
        if data.get("retires"):
            html += self._html_section(
                _("Retired from the manifest (kept on disk)"),
                self._html_list(data["retires"]),
            )
        html += self._render_pull_deps(data.get("dependances"))
        return html

    def _render_pull_manifest(self, manifest):
        _ = self.env._
        if not manifest:
            return Markup("")
        notes = []
        if manifest.get("erreur") == "manifeste_different":
            notes.append(
                Markup("<p class='text-danger'>%s</p>")
                % _(
                    "The regenerated manifest differs from the dry run: it "
                    "was not written and no clone was integrated."
                )
            )
        elif manifest.get("erreur"):
            notes.append(Markup("<p class='text-danger'>%s</p>") % manifest["erreur"])
        if manifest.get("ecrit"):
            notes.append(
                Markup("<p>%s</p>")
                % _(
                    "The local manifest was written; the previous one is "
                    "kept in %(path)s.",
                    path=manifest.get("copie_avant") or "",
                )
            )
        kinds = {
            "change": _("changed"),
            "ajout": _("added"),
            "retrait": _("removed"),
        }
        changes = manifest.get("changements") or []
        rows = [
            Markup("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>")
            % (
                c.get("chemin") or "",
                kinds.get(c.get("genre"), c.get("genre") or ""),
                c.get("avant") or "",
                c.get("apres") or "",
            )
            for c in changes
        ]
        body = Markup("").join(notes)
        if rows:
            body += self._html_table(
                [_("Repository"), _("Change"), _("Before"), _("After")], rows
            )
        elif manifest.get("regenere"):
            body += Markup("<p class='text-muted'>%s</p>") % _(
                "The regenerated manifest equals the local manifest."
            )
        return self._html_section(_("Regenerated manifest"), body)

    def _render_pull_deps(self, deps):
        _ = self.env._
        if not deps or not (deps.get("fichiers") or deps.get("requirements_addons")):
            return Markup("")
        body = Markup("")
        if deps.get("fichiers"):
            body += self._html_list(deps["fichiers"])
        if deps.get("changement_de_version"):
            body += Markup("<p class='text-danger'>%s</p>") % _(
                "The Python/Odoo couple changes: run make install."
            )
        if deps.get("a_installer"):
            body += Markup("<p>%s <code>%s</code></p>") % (
                _("Installed only when approved after the apply:"),
                deps.get("commande") or "",
            )
        if deps.get("venv_erplibre_a_revoir"):
            body += Markup("<p class='text-warning'>%s</p>") % _(
                "The requirements of the ERPLibre virtual environment "
                "changed: review it."
            )
        if deps.get("requirements_addons"):
            body += Markup("<p>%s</p>%s") % (
                _("A requirements.txt changes in:"),
                self._html_list(deps["requirements_addons"]),
            )
        return self._html_section(_("Python dependencies"), body)

    def _render_pull_apply(self, data):
        _ = self.env._
        states = self._pull_state_labels()
        html = Markup("")
        if data.get("error"):
            html += Markup("<p class='text-danger'>%s</p>") % data["error"]
        if data.get("budget_epuise"):
            html += Markup(
                "<div class='alert alert-warning' role='alert'>%s</div>"
            ) % _(
                "The time budget of the pass ran out: the repositories marked "
                "« not started » were left as they are; run a new pull for them."
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
            rows.append(
                Markup(
                    "<tr><td>%s</td><td class='%s'>%s%s</td><td><code>%s</code></td>"
                    "<td><code>%s</code></td><td><code>%s</code></td>"
                    "<td>%s</td><td>%s</td></tr>"
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
                    res.get("sauvegarde") or "",
                    (res.get("depart") or "")[:12],
                    (res.get("arrivee") or "")[:12],
                    stash_cell,
                    ", ".join(res.get("conflits") or []),
                )
            )
            if res.get("manifeste_restaure"):
                rows.append(
                    Markup("<tr><td colspan='7' class='text-muted'>%s</td></tr>")
                    % _("The local manifest of before the pull is put back.")
                )
        if rows:
            html += self._html_table(
                [
                    _("Repository"),
                    _("Result"),
                    _("Backup"),
                    _("From"),
                    _("To"),
                    _("Stash"),
                    _("Conflicts"),
                ],
                rows,
            )
        elif data.get("command") == "apply" and not data.get("error"):
            html += Markup("<p class='text-muted'>%s</p>") % _(
                "Nothing to pull: nothing was written."
            )
        html += self._render_pull_manifest(data.get("manifeste"))
        clone_rows = []
        for clone in data.get("clones") or []:
            label, css = states.get(clone.get("etat"), (clone.get("etat") or "", ""))
            clone_rows.append(
                Markup("<tr><td>%s</td><td class='%s'>%s</td><td>%s</td></tr>")
                % (clone.get("chemin") or "", css, label, clone.get("motif") or "")
            )
        if clone_rows:
            html += self._html_section(
                _("New repositories"),
                self._html_table(
                    [_("Repository"), _("Result"), _("Reason")], clone_rows
                ),
            )
        deps = data.get("dependances") or {}
        html += self._render_pull_deps(deps)
        if deps.get("a_installer") and not data.get("deps"):
            html += Markup("<p class='text-muted'>%s</p>") % _(
                "Install them with « Install the Python dependencies », or "
                "restart without installing."
            )
        if data.get("deps"):
            html += self._render_deps_install(data["deps"])
        return html

    def _render_pull_restore(self, data):
        return self._render_pull_apply(data)

    def _render_deps_install(self, data):
        _ = self.env._
        html = Markup("<p><code>%s</code></p>") % (data.get("commande") or "")
        if data.get("error"):
            html += Markup("<p class='text-danger'>%s</p>") % data["error"]
        elif data.get("code") == 0:
            html += Markup("<p class='text-success'>%s</p>") % _(
                "The Python dependencies are installed."
            )
        if data.get("sortie"):
            html += Markup("<pre>%s</pre>") % data["sortie"]
        return html
