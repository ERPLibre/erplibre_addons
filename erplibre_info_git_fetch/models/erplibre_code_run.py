# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The run types that write the checkout: the fetch + rebase of the forks,
the pull of the code (``erplibre_code_run_pull.py``) and the return to a
snapshot (``erplibre_code_run_revert.py``).

Every one of them is a server action that, on top of the three conditions
of ``erplibre_info`` (odoo.conf flag, Settings group, developer mode),
requires a server started with ``--dev``: ``_check_git_fetch`` at each
launch, ``_check_git_fetch_in_background`` in the background step. The
restart of ``erplibre_info`` keeps its three conditions only.
"""

import json
import logging

from markupsafe import Markup
from odoo import api, fields, models, release
from odoo.exceptions import UserError
from odoo.tools import config

from odoo.addons.erplibre_info import runner

_logger = logging.getLogger(__name__)

PARAM_PULL_STRATEGY = "erplibre_info.pull_strategy"

# Verdicts of « repo_upgrade.py --diagnostic » that the apply step takes:
# no conflict predicted. The others go to the TODO menu.
VERDICTS_CLEAN = ("a_rebaser", "en_retard")
VERDICTS_MENU = ("en_conflit", "absorbe")

PULL_MODES = [("manifeste", "Manifest"), ("branche", "Branches")]
PULL_STRATEGIES = [
    ("rebase", "Rebase"),
    ("ff", "Fast-forward only"),
    ("merge", "Merge"),
]

# The run types that run git on the checkout: one of them at a time.
GIT_RUN_TYPES = (
    "dry_run",
    "apply",
    "pull_dry_run",
    "pull_apply",
    "pull_restore",
    "deps_install",
    "snapshot_revert_dry_run",
    "snapshot_revert",
)

# The apply type of each dry run type.
APPLY_OF = {
    "dry_run": "apply",
    "pull_dry_run": "pull_apply",
    "snapshot_revert_dry_run": "snapshot_revert",
}

# The dry runs and applies of « repo_pull.py » that move the clones: the
# last finished one decides whether a restart waits (``pull_blocked``).
PULL_LIKE_TYPES = (
    "pull_dry_run",
    "pull_apply",
    "snapshot_revert_dry_run",
    "snapshot_revert",
)

# The fields of these run types that decide what their background step
# runs, on top of the ``LAUNCH_FIELDS`` of erplibre_info.
FETCH_LAUNCH_FIELDS = (
    "parent_id",
    "backup_id",
    "pull_mode",
    "pull_strategy",
    "pull_path",
    "approve_deepen",
    "approve_clone",
    "revert_snapshot_id",
    "revert_root",
    "revert_targets",
    "approve_modules",
)

# The exit code of « repo_apply.py » and « repo_pull.py » when the plan or
# a pinned commit changed since the dry run: nothing is written.
EXIT_PLAN_CHANGED = 4


class ErplibreCodeRun(models.Model):
    _inherit = "erplibre.code.run"

    run_type = fields.Selection(
        selection_add=[
            ("dry_run", "Fetch + rebase: dry run"),
            ("apply", "Fetch + rebase: apply"),
            ("restart",),
            ("pull_dry_run", "Pull: dry run"),
            ("pull_apply", "Pull: apply"),
            ("pull_restore", "Pull: restore a backup"),
            ("deps_install", "Python dependencies install"),
            ("snapshot_revert_dry_run", "Return to a snapshot: dry run"),
            ("snapshot_revert", "Return to a snapshot: apply"),
        ],
        ondelete={
            "dry_run": "cascade",
            "apply": "cascade",
            "pull_dry_run": "cascade",
            "pull_apply": "cascade",
            "pull_restore": "cascade",
            "deps_install": "cascade",
            "snapshot_revert_dry_run": "cascade",
            "snapshot_revert": "cascade",
        },
    )
    parent_id = fields.Many2one(
        "erplibre.code.run",
        string="Dry run",
        readonly=True,
        ondelete="set null",
    )
    child_ids = fields.One2many("erplibre.code.run", "parent_id", string="Applied")
    odoo_version = fields.Char(readonly=True)
    plan_paths = fields.Text(
        string="Repositories to apply",
        readonly=True,
        help="The repositories that the apply step integrates, one per line.",
    )
    plan_count = fields.Integer(compute="_compute_plan_count")
    left_paths = fields.Text(
        string="Repositories left as they are",
        readonly=True,
        help="A fork with a predicted conflict, resolved in the TODO menu; "
        "a pull that the chosen strategy cannot make, or a repository "
        "with an operation in progress. The apply step never touches "
        "them.",
    )
    pull_mode = fields.Selection(PULL_MODES, string="Pull mode", readonly=True)
    pull_strategy = fields.Selection(
        PULL_STRATEGIES, string="Pull strategy", readonly=True
    )
    pull_path = fields.Char(
        string="Single repository",
        readonly=True,
        help="The pull is restricted to this repository.",
    )
    shallow_paths = fields.Text(
        string="Shallow clones to deepen",
        readonly=True,
        help="Shallow clones without a known common base with their target: "
        "the apply step deepens them only when it is allowed to.",
    )
    clone_paths = fields.Text(
        string="New repositories to clone",
        readonly=True,
        help="Projects of the regenerated manifest not cloned yet: the "
        "apply step clones them only when it is allowed to.",
    )
    approve_deepen = fields.Boolean(string="Deepening allowed", readonly=True)
    approve_clone = fields.Boolean(string="Cloning allowed", readonly=True)
    auto_apply = fields.Boolean(
        string="Apply after the dry run",
        readonly=True,
        help="Started by Apply in the pull wizard: once the dry run is done, "
        "its apply step is queued at once, pinned to what it found, with "
        "the permissions given at the click.",
    )
    deps_to_install = fields.Boolean(
        string="Python dependencies to install",
        readonly=True,
        help="The pull changed the Python dependencies of the Odoo "
        "virtual environment.",
    )
    pull_blocked = fields.Boolean(
        string="A repository is left mid-operation",
        readonly=True,
        help="Putting a repository back where it was failed: it is fixed "
        "in a terminal before the server restarts.",
    )
    backup_ids = fields.One2many(
        "erplibre.code.pull.backup", "run_id", string="Backups"
    )
    backup_id = fields.Many2one(
        "erplibre.code.pull.backup",
        string="Restored backup",
        readonly=True,
        ondelete="set null",
    )
    pass_dir = fields.Char(string="Pass record", readonly=True)
    can_apply = fields.Boolean(compute="_compute_can_apply")
    apply_note = fields.Char(compute="_compute_can_apply")
    git_fetch_allowed = fields.Boolean(compute="_compute_git_fetch_allowed")

    def _compute_git_fetch_allowed(self):
        allowed = self._git_fetch_allowed()
        for run in self:
            run.git_fetch_allowed = allowed

    @api.depends("plan_paths")
    def _compute_plan_count(self):
        for run in self:
            run.plan_count = len(run._plan())

    @api.depends(
        "run_type",
        "state",
        "plan_paths",
        "shallow_paths",
        "clone_paths",
        "child_ids.run_type",
        "child_ids.state",
        "child_ids.exit_code",
    )
    def _compute_can_apply(self):
        """A dry run is applied once, while it is the last done dry run of
        its type and no apply found the remote moved since (exit code 4)."""
        for run in self:
            run.can_apply = False
            run.apply_note = False
            apply_type = APPLY_OF.get(run.run_type)
            if not apply_type or run.state != "done":
                continue
            applies = run.child_ids.filtered(lambda c: c.run_type == apply_type)
            if applies.filtered(
                lambda c: c.state == "failed" and c.exit_code == EXIT_PLAN_CHANGED
            ):
                run.apply_note = (
                    self.env._(
                        "The upstream moved since this dry run: run a new dry run."
                    )
                    if run.run_type == "dry_run"
                    else self.env._(
                        "A remote or a HEAD moved since this dry run: run a "
                        "new dry run."
                    )
                )
            elif run.id and self.search_count(
                [
                    ("run_type", "=", run.run_type),
                    ("state", "=", "done"),
                    ("id", ">", run.id),
                ]
            ):
                run.apply_note = self.env._("A newer dry run exists: apply that one.")
            run.can_apply = (
                not run.apply_note
                and run._has_work()
                and not applies.filtered(
                    lambda c: c.state in ("queued", "running", "done")
                )
            )

    @api.model
    def _lines(self, text):
        return [p for p in (text or "").splitlines() if p.strip()]

    def _plan(self):
        self.ensure_one()
        return self._lines(self.plan_paths)

    def _has_work(self):
        """Whether the apply step of this dry run has something to do: a
        repository of its plan, and for a pull a shallow clone to deepen
        or a new repository to clone, both subject to approval."""
        self.ensure_one()
        if self.run_type == "pull_dry_run":
            return bool(
                self._plan()
                or self._lines(self.shallow_paths)
                or self._lines(self.clone_paths)
            )
        return bool(self._plan())

    # ── guards ──────────────────────────────────────────────────────────

    @api.model
    def _git_run_types(self):
        return super()._git_run_types() + GIT_RUN_TYPES

    @api.model
    def _launch_fields(self):
        return super()._launch_fields() + FETCH_LAUNCH_FIELDS

    @api.model
    def _dev_mode_problem(self):
        """Why the server refuses the actions of this module: it runs
        without ``--dev`` (``config["dev_mode"]`` is empty); False when it
        runs with it."""
        if config.get("dev_mode"):
            return False
        return self.env._(
            "Fetch + rebase, pull, return to a snapshot and stash reapply "
            "require an Odoo server started with --dev (for example "
            "--dev=all): erplibre_info_git_fetch writes the git clones of "
            "the checkout."
        )

    @api.model
    def _git_fetch_allowed(self):
        return self._server_actions_allowed() and not self._dev_mode_problem()

    @api.model
    def _git_fetch_problem(self):
        """The first condition of the actions of this module that fails, as
        a translated message, or False when they are allowed."""
        return self._server_actions_problem() or self._dev_mode_problem()

    @api.model
    def _check_git_fetch(self):
        """Raise unless the actions of this module are allowed: the three
        conditions of the server actions, then ``--dev``."""
        self._check_server_actions()
        problem = self._dev_mode_problem()
        if problem:
            raise UserError(problem)

    def _check_git_fetch_in_background(self):
        """The background step re-reads the odoo.conf flag, the group of its
        requester and ``--dev``: a queued run stops on a server restarted
        without it."""
        self._check_flag_in_background()
        problem = self._dev_mode_problem()
        if problem:
            raise UserError(problem)

    # ── execution ───────────────────────────────────────────────────────

    def _execute(self):
        """A pull dry run started by Apply queues its apply step once it is
        done (see ``_chain_apply``)."""
        res = super()._execute()
        if res and self.state == "done" and self.auto_apply:
            self._chain_apply()
        return res

    def _execute_dry_run(self):
        self._check_git_fetch_in_background()
        long_timeout = runner.timeout(self.env, long=True)
        remotes = runner.run(
            self.env,
            runner.SCRIPT_UPGRADE,
            ["--add-remotes", "--version", release.series, "--json"],
            long_timeout,
        )
        log = [remotes.command, remotes.stderr.strip()]
        if not isinstance(remotes.data, dict):
            raise runner.RunnerError(
                self.env._(
                    "%(command)s failed (exit code %(code)s): %(detail)s",
                    command=remotes.command,
                    code=remotes.returncode,
                    detail=remotes.stderr.strip()[-2000:],
                )
            )
        diagnostic = runner.run_json(
            self.env,
            runner.SCRIPT_UPGRADE,
            ["--diagnostic", "--version", release.series, "--json"],
            long_timeout,
        )
        log += [diagnostic.command, diagnostic.stderr.strip()]
        forks = diagnostic.data.get("forks") or []
        plan = sorted(f["chemin"] for f in forks if f.get("verdict") in VERDICTS_CLEAN)
        left = sorted(f["chemin"] for f in forks if f.get("verdict") in VERDICTS_MENU)
        self.write(
            {
                "odoo_version": diagnostic.data.get("version"),
                "plan_paths": "\n".join(plan),
                "left_paths": "\n".join(left),
                "exit_code": diagnostic.returncode,
                "result_json": json.dumps(
                    {"remotes": remotes.data, "diagnostic": diagnostic.data},
                    ensure_ascii=False,
                ),
                "log": self._append_log("\n".join(x for x in log if x)),
            }
        )

    def _expected_args(self):
        """The ``--expect`` values of the plan: each path pinned to the
        upstream commit and the HEAD that the dry run showed, so the apply
        refuses a state nobody reviewed. A path the dry run did not pin
        stays bare."""
        self.ensure_one()
        try:
            data = json.loads(self.parent_id.result_json or "{}")
        except ValueError:
            data = {}
        forks = {
            f.get("chemin"): f
            for f in (data.get("diagnostic") or {}).get("forks") or []
        }
        values = []
        for path in self._plan():
            fork = forks.get(path) or {}
            target, head = fork.get("cible_sha"), fork.get("head")
            values.append(f"{path}={target}:{head}" if target and head else path)
        return values

    def _execute_apply(self):
        self._check_git_fetch_in_background()
        args = ["--apply", "--confirm", self.odoo_version or "", "--json"]
        for value in self._expected_args():
            args += ["--expect", value]
        res = runner.run_json(
            self.env,
            runner.SCRIPT_APPLY,
            args,
            runner.timeout(self.env, long=True),
            ok_codes=(0, 4),
        )
        vals = {
            "exit_code": res.returncode,
            "result_json": json.dumps(res.data, ensure_ascii=False),
            "pass_dir": res.data.get("dossier"),
            "log": self._append_log(
                "\n".join(x for x in (res.command, res.stderr) if x)
            ),
        }
        if res.returncode == 4:
            vals.update(
                state="failed",
                date_end=fields.Datetime.now(),
                log=self._append_log(
                    self.env._(
                        "The dry run is out of date: the upstream changed the "
                        "list of repositories to apply, or the commits shown. "
                        "Nothing was written; run a new dry run."
                    )
                ),
            )
            self.write(vals)
            return
        self.write(vals)
        self._record_code_change(res.data)

    # ── actions ─────────────────────────────────────────────────────────

    @api.model
    def action_start_dry_run(self):
        self._check_git_fetch()
        self._check_no_git_run()
        run = self._create_launched({"run_type": "dry_run"})
        run._enqueue()
        return run._action_open()

    def action_apply(self):
        """Open the confirmation of the apply step: the first validation."""
        self.ensure_one()
        self._check_git_fetch()
        if not self.can_apply:
            raise UserError(self.env._("This dry run has nothing left to apply."))
        return self.env["erplibre.code.confirm.wizard"]._action_open("apply", run=self)

    def _launch_apply(self):
        """Queue the apply step of this dry run; called by the confirmed
        wizard, the second validation."""
        self.ensure_one()
        self._check_git_fetch()
        if not self.can_apply:
            raise UserError(self.env._("This dry run has nothing left to apply."))
        self._check_no_git_run()
        run = self._create_launched(
            {
                "run_type": "apply",
                "parent_id": self.id,
                "odoo_version": self.odoo_version,
                "plan_paths": self.plan_paths,
                "left_paths": self.left_paths,
            }
        )
        run._enqueue()
        return run._action_open()

    def _check_restart_allowed(self):
        """A restart waits while a pull left a repository mid-operation."""
        super()._check_restart_allowed()
        if self.filtered("pull_blocked"):
            raise UserError(
                self.env._(
                    "A repository is left mid-operation: fix it in a terminal "
                    "before restarting."
                )
            )
        self._check_no_blocked_pull()

    @api.model
    def _check_no_blocked_pull(self):
        """Refuse a restart while the last pull or return to a snapshot
        left a repository mid-operation, whichever button asks for it: the
        last finished dry run or apply of either is an apply marked
        ``pull_blocked``. A new dry run, after the repository is fixed in a
        terminal, lifts it."""
        last = self.sudo().search(
            [
                ("run_type", "in", PULL_LIKE_TYPES),
                ("state", "in", ("done", "failed")),
            ],
            order="id desc",
            limit=1,
        )
        if last.run_type in ("pull_apply", "snapshot_revert") and last.pull_blocked:
            raise UserError(
                self.env._(
                    "The last pull left a repository mid-operation: fix it in "
                    "a terminal, then run a new pull dry run before "
                    "restarting."
                )
            )

    # ── rendering ───────────────────────────────────────────────────────

    def _render_dry_run(self, data):
        forks = (data.get("diagnostic") or {}).get("forks") or []
        rows = []
        for fork in sorted(
            forks,
            key=lambda f: (f.get("verdict") or "", f.get("chemin") or ""),
        ):
            verdict = fork.get("verdict") or ""
            if verdict in VERDICTS_CLEAN:
                decision = self.env._("applied")
                css = "text-success"
            elif verdict in VERDICTS_MENU:
                decision = self.env._("TODO menu")
                css = "text-danger"
            else:
                decision = ""
                css = "text-muted"
            rows.append(
                Markup(
                    "<tr><td>%s</td><td class='%s'>%s</td><td>%s</td>"
                    "<td class='text-end'>%s</td><td class='text-end'>%s</td>"
                    "<td>%s</td></tr>"
                )
                % (
                    fork.get("chemin") or "",
                    css,
                    verdict,
                    decision,
                    fork.get("nos") or 0,
                    fork.get("amont_avance") or 0,
                    fork.get("motif") or ", ".join(fork.get("conflits") or []),
                )
            )
        remotes = (data.get("remotes") or {}).get("remotes") or []
        failed = [
            r
            for r in remotes
            if r.get("issue") in ("autre_url", "refuse", "fetch_echoue")
        ]
        head = Markup(
            "<table class='table table-sm o_erplibre_info_table'><thead><tr>"
            "<th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th>"
            "</tr></thead><tbody>"
        ) % (
            self.env._("Repository"),
            self.env._("Verdict"),
            self.env._("Decision"),
            self.env._("Ours"),
            self.env._("Upstream ahead"),
            self.env._("Reason / conflicts"),
        )
        html = head + Markup("").join(rows) + Markup("</tbody></table>")
        if failed:
            items = Markup("").join(
                Markup("<li>%s: %s</li>") % (r.get("chemin") or "", r.get("issue"))
                for r in failed
            )
            html += Markup("<p>%s</p><ul>%s</ul>") % (
                self.env._("Upstream remotes not fetched:"),
                items,
            )
        return html

    def _render_apply(self, data):
        rows = Markup("").join(
            Markup("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>")
            % (
                res.get("chemin") or "",
                res.get("etat") or "",
                res.get("branche") or "",
                (res.get("depart") or "")[:12],
                (res.get("arrivee") or "")[:12],
            )
            for res in data.get("resultats") or []
        )
        html = Markup(
            "<table class='table table-sm o_erplibre_info_table'><thead><tr>"
            "<th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th>"
            "</tr></thead><tbody>%s</tbody></table>"
        ) % (
            self.env._("Repository"),
            self.env._("Result"),
            self.env._("Dated branch"),
            self.env._("From"),
            self.env._("To"),
            rows,
        )
        if data.get("error"):
            html = Markup("<p class='text-danger'>%s</p>") % data["error"] + html
        return html
