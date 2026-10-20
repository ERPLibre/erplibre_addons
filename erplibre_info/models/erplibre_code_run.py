# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import logging
import os
import zlib

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

import odoo
from markupsafe import Markup
from odoo import SUPERUSER_ID, api, fields, models, release, sql_db
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.service import server as odoo_server
from odoo.tools import config, str2bool

from .. import runner

_logger = logging.getLogger(__name__)

FLAG_SERVER_ACTIONS = "erplibre_info_allow_server_actions"
PARAM_STARTUP = "erplibre_info.snapshot_on_startup"
PARAM_PERIODIC = "erplibre_info.snapshot_periodic"
PARAM_STARTUP_KEY = "erplibre_info.startup_key"
CRON_XMLID = "erplibre_info.ir_cron_erplibre_code"
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
)

# The apply type of each dry run type.
APPLY_OF = {"dry_run": "apply", "pull_dry_run": "pull_apply"}

# The fields of a run that decide what its background step runs: only the
# launch methods set them, through ``_create_launched``.
LAUNCH_FIELDS = (
    "run_type",
    "parent_id",
    "backup_id",
    "pull_mode",
    "pull_strategy",
    "pull_path",
    "approve_deepen",
    "approve_clone",
    "user_id",
)

# The exit code of « repo_apply.py » and « repo_pull.py » when the plan or
# a pinned commit changed since the dry run: nothing is written.
EXIT_PLAN_CHANGED = 4

TRIGGERS = [
    ("manual", "Manual"),
    ("cron", "Periodic"),
    ("startup", "Server start"),
    ("upgrade", "Upgrade"),
]

# Databases of this process whose startup snapshot is already decided: a
# registry reload (module install, upgrade) in the same process skips it.
_STARTUP_DONE = set()

# Key of the PostgreSQL advisory lock that serialises the startup decision
# between the workers of a multi-process server.
_STARTUP_LOCK = zlib.crc32(b"erplibre_info.startup")


def _restart_server():
    odoo_server.restart()


class ErplibreCodeRun(models.Model):
    _name = "erplibre.code.run"
    _description = "ERPLibre code run"
    _order = "id desc"
    _rec_names_search = ["run_type"]

    # Computed at read time: the type label follows the viewer's language.
    name = fields.Char(compute="_compute_name")
    run_type = fields.Selection(
        [
            ("snapshot", "Snapshot"),
            ("dry_run", "Fetch + rebase: dry run"),
            ("apply", "Fetch + rebase: apply"),
            ("restart", "Server restart"),
            ("pull_dry_run", "Pull: dry run"),
            ("pull_apply", "Pull: apply"),
            ("pull_restore", "Pull: restore a backup"),
            ("deps_install", "Python dependencies install"),
        ],
        string="Type",
        required=True,
        readonly=True,
    )
    trigger = fields.Selection(TRIGGERS, readonly=True)
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("running", "Running"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="queued",
        required=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Requested by",
        default=lambda self: self.env.user,
        readonly=True,
    )
    executor = fields.Selection(
        [("cron", "Cron"), ("queue_job", "queue_job")],
        default="cron",
        required=True,
        readonly=True,
        help="Who executes the queued run: the ERPLibre cron, or a queue_job "
        "job. Each one only takes its own runs.",
    )
    date_start = fields.Datetime(string="Started", readonly=True)
    date_end = fields.Datetime(string="Ended", readonly=True)
    log = fields.Text(readonly=True)
    result_json = fields.Text(string="JSON result", readonly=True)
    exit_code = fields.Integer(readonly=True)
    parent_id = fields.Many2one(
        "erplibre.code.run",
        string="Dry run",
        readonly=True,
        ondelete="set null",
    )
    child_ids = fields.One2many("erplibre.code.run", "parent_id", string="Applied")
    snapshot_id = fields.Many2one(
        "erplibre.code.snapshot", readonly=True, ondelete="set null"
    )
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
    upgrade_module_ids = fields.Many2many(
        "ir.module.module",
        string="Modules to upgrade",
        readonly=True,
        help="The modules whose code the apply changed, plus those whose "
        "version waits for an upgrade.",
    )
    code_changed_module_ids = fields.Many2many(
        "ir.module.module",
        relation="erplibre_code_run_code_changed_module_rel",
        column1="run_id",
        column2="module_id",
        string="Code changed by the apply",
        readonly=True,
    )
    version_pending_module_ids = fields.Many2many(
        "ir.module.module",
        relation="erplibre_code_run_version_pending_module_rel",
        column1="run_id",
        column2="module_id",
        string="Version pending",
        readonly=True,
    )
    report_html = fields.Html(compute="_compute_report_html", sanitize=False)
    can_apply = fields.Boolean(compute="_compute_can_apply")
    apply_note = fields.Char(compute="_compute_can_apply")
    server_actions_allowed = fields.Boolean(compute="_compute_server_actions_allowed")

    @api.depends("run_type", "create_date")
    @api.depends_context("lang")
    def _compute_name(self):
        labels = dict(self._fields["run_type"]._description_selection(self.env))
        for run in self:
            date = fields.Datetime.to_string(run.create_date or fields.Datetime.now())
            run.name = f"{labels.get(run.run_type, run.run_type)} {date}"

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

    def _compute_server_actions_allowed(self):
        allowed = self._server_actions_allowed()
        for run in self:
            run.server_actions_allowed = allowed

    @api.depends("result_json", "run_type")
    def _compute_report_html(self):
        for run in self:
            try:
                data = json.loads(run.result_json) if run.result_json else None
            except ValueError:
                data = None
            render = getattr(run, f"_render_{run.run_type}", None)
            run.report_html = render(data) if data and render else False

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

    @api.model_create_multi
    def create(self, vals_list):
        """A run of a git type is created only by a launch method
        (``_create_launched``), after the checks and the confirmations of
        its button: created through the ORM or RPC, its background step
        would skip them."""
        if not self.env.su and any(
            vals.get("run_type") in GIT_RUN_TYPES for vals in vals_list
        ):
            raise AccessError(
                self.env._(
                    "A git run is started only from its button, after its "
                    "confirmations."
                )
            )
        return super().create(vals_list)

    def write(self, vals):
        """The fields that decide what a run executes, and its return to
        the queue, are set only by the launch methods."""
        if not self.env.su and (
            any(field in vals for field in LAUNCH_FIELDS)
            or vals.get("state") == "queued"
        ):
            raise AccessError(
                self.env._(
                    "What a run executes is set when it is started, never "
                    "changed afterwards."
                )
            )
        return super().write(vals)

    @api.model
    def _create_launched(self, vals):
        """Create the run ``vals`` of a launch method, which checked the
        server actions and the confirmations before; the requester stays
        the current user. Return the run, in the caller's environment."""
        vals = dict(vals)
        vals.setdefault("user_id", self.env.user.id)
        return self.sudo().create(vals).with_env(self.env)

    @api.model
    def _flag_enabled(self):
        """The odoo.conf option that allows the server actions."""
        return str2bool(str(config.get(FLAG_SERVER_ACTIONS) or "False"), False)

    @api.model
    def _is_debug_mode(self):
        """Developer mode of the HTTP session; False outside a request."""
        try:
            return bool(request and request.session.debug)
        except RuntimeError:
            return False

    @api.model
    def _server_actions_allowed(self):
        return bool(
            self._flag_enabled()
            and self.env.user.has_group("base.group_system")
            and self._is_debug_mode()
        )

    @api.model
    def _check_server_actions(self):
        """Raise unless the three conditions of the server actions hold:
        the odoo.conf flag, the Settings group, the developer mode."""
        if not self._flag_enabled():
            raise UserError(
                self.env._(
                    "Server actions are disabled. Set %(flag)s = True in the "
                    "Odoo configuration file to allow them.",
                    flag=FLAG_SERVER_ACTIONS,
                )
            )
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                self.env._("Only the Settings administrators run server actions.")
            )
        if not self._is_debug_mode():
            raise UserError(self.env._("Server actions require the developer mode."))

    # ── background execution ────────────────────────────────────────────

    @api.model
    def _use_queue_job(self):
        """queue_job runs the jobs only when it is installed AND loaded as
        a server-wide module; otherwise its jobs would wait forever."""
        if "queue.job" not in self.env:
            return False
        if "queue_job" not in (odoo.conf.server_wide_modules or []):
            return False
        return bool(
            self.env["ir.module.module"]
            .sudo()
            .search_count([("name", "=", "queue_job"), ("state", "=", "installed")])
        )

    @api.model
    def _cron(self):
        return self.env.ref(CRON_XMLID, raise_if_not_found=False)

    @api.model
    def _cron_runs_domain(self, states=("queued",)):
        return [("state", "in", list(states)), ("executor", "=", "cron")]

    @api.model
    def _sync_cron(self):
        """The cron is active while the periodic snapshot is on or one of
        its runs waits or executes. Return the cron.

        The write goes through ``try_write``: while the cron executes a job
        it holds a lock on its row, and the write is then skipped instead
        of failing the caller (a Settings save). A run that executes keeps
        the cron needed, so the cron is never switched off under its own
        job; the job switches itself off at its end when nothing needs it.
        """
        cron = self._cron()
        if not cron:
            return cron
        needed = runner.param_bool(self.env, PARAM_PERIODIC) or bool(
            self.sudo().search_count(self._cron_runs_domain(("queued", "running")))
        )
        if cron.sudo().active != needed:
            cron.sudo().try_write({"active": needed})
        return cron

    @api.model
    def _default_lang(self):
        """The language of runs without a requester: the administrator's,
        else English."""
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        return (admin.sudo().lang if admin else False) or "en_US"

    def _run_lang(self):
        """The language the run writes its log in: its requester's."""
        self.ensure_one()
        return self.user_id.sudo().lang or self._default_lang()

    def _enqueue(self):
        """Hand the queued runs to queue_job, or trigger the cron once."""
        if not self:
            return
        if self._use_queue_job():
            self.write({"executor": "queue_job"})
            for run in self:
                run.with_context(lang=run._run_lang()).with_delay(
                    description=run.name
                )._execute()
            return
        cron = self._sync_cron()
        if not cron:
            raise UserError(self.env._("The ERPLibre cron is missing."))
        cron.sudo()._trigger()

    def _commit(self):
        """Commit in the cron, so the state of a run is visible while it
        runs; never in a test, nor in a queue_job job, which owns its
        transaction."""
        if (
            self.env.context.get("erplibre_info_commit")
            and not odoo.modules.module.current_test
        ):
            self.env.cr.commit()  # pylint: disable=invalid-commit

    @api.model
    def _cron_process(self):
        """Run the queued runs of the cron, each in the language of its
        requester, then the periodic snapshot when it is on. The cron
        deactivates itself when nothing else needs it. The runs handed to
        queue_job are left to it."""
        done = 0
        runs = self.with_context(erplibre_info_commit=True)
        for run in runs.search(self._cron_runs_domain(), order="id"):
            run.with_context(lang=run._run_lang())._execute()
            run._commit()
            done += 1
        if runner.param_bool(self.env, PARAM_PERIODIC):
            snapshots = self.env["erplibre.code.snapshot"].with_context(
                lang=self._default_lang()
            )
            try:
                snapshots._capture("cron")
            except runner.RunnerError as exc:
                _logger.warning("ERPLibre periodic snapshot: %s", exc)
                self._record_periodic_failure(str(exc))
        needed = runner.param_bool(self.env, PARAM_PERIODIC) or bool(
            self.search_count(self._cron_runs_domain())
        )
        self.env["ir.cron"]._notify_progress(
            done=done, remaining=0, deactivate=not needed
        )
        return done

    @api.model
    def _record_periodic_failure(self, message):
        """Record a periodic snapshot that cannot run as a failed run, the
        only trace the Settings page shows. A lasting outage keeps one
        run: the same failure since the last snapshot only moves its end
        date. Return the run."""
        log = runner.strip_credentials(message or "")
        now = fields.Datetime.now()
        last = self.sudo().search(
            [("run_type", "=", "snapshot"), ("trigger", "=", "cron")],
            limit=1,
        )
        snapshot = self.env["erplibre.code.snapshot"].sudo().search([], limit=1)
        if (
            last
            and last.state == "failed"
            and last.log == log
            and not (snapshot and snapshot.date > last.date_start)
        ):
            last.date_end = now
            return last
        return self.sudo().create(
            {
                "run_type": "snapshot",
                "trigger": "cron",
                "user_id": False,
                "state": "failed",
                "date_start": now,
                "date_end": now,
                "log": log,
            }
        )

    def _claim(self):
        """Move this run from queued to running in one statement; False when
        it is no longer queued or another executor holds its row. A run is
        thus executed once, whoever dispatches it twice."""
        self.ensure_one()
        self.flush_recordset()
        now = fields.Datetime.now()
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(
                    """
                    UPDATE erplibre_code_run
                       SET state = 'running', date_start = %s,
                           write_date = %s, write_uid = %s
                     WHERE id = (
                        SELECT id FROM erplibre_code_run
                         WHERE id = %s AND state = 'queued'
                           FOR NO KEY UPDATE SKIP LOCKED)
                    RETURNING id
                    """,
                    [now, now, self.env.uid, self.id],
                    log_exceptions=False,
                )
                claimed = bool(self.env.cr.fetchone())
        except psycopg2.OperationalError:
            # Updated by another transaction since this one began.
            claimed = False
        self.invalidate_recordset(["state", "date_start", "write_date", "write_uid"])
        return claimed

    def _execute(self):
        """Run one queued run; record its outcome, never raise."""
        self.ensure_one()
        if not self._claim():
            return False
        self._commit()
        try:
            with self.env.cr.savepoint():
                getattr(self, f"_execute_{self.run_type}")()
        except Exception as exc:  # noqa: BLE001 - the run records the failure
            if not isinstance(exc, (runner.RunnerError, UserError)):
                _logger.exception("ERPLibre run %s failed", self.id)
            self.invalidate_recordset()
            self.write(
                {
                    "state": "failed",
                    "log": self._append_log(str(exc)),
                    "date_end": fields.Datetime.now(),
                }
            )
            return False
        if self.state == "running":
            self.write({"state": "done", "date_end": fields.Datetime.now()})
        return True

    def _append_log(self, text):
        self.ensure_one()
        text = runner.strip_credentials(text or "")
        return "\n".join(x for x in (self.log, text) if x)

    def _execute_snapshot(self):
        snapshot = self.env["erplibre.code.snapshot"]._capture(
            self.trigger or "manual",
            run=self,
            force=self.trigger in ("manual", "upgrade"),
        )
        self.write(
            {
                "snapshot_id": snapshot.id,
                "log": self._append_log(
                    self.env._("Snapshot %(name)s created.", name=snapshot.name)
                    if snapshot
                    else self.env._("The code did not change: no new snapshot.")
                ),
            }
        )

    def _execute_dry_run(self):
        self._check_flag_in_background()
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

    def _changed_modules(self, data, snapshot):
        """The installed modules of ``snapshot`` whose files differ between
        the start and the end commit of a repository the apply moved."""
        modules = self.env["ir.module.module"]
        for res in data.get("resultats") or []:
            path, start, end = (
                res.get("chemin"),
                res.get("depart"),
                res.get("arrivee"),
            )
            if not (path and start and end) or start == end:
                continue
            try:
                between = runner.run_json(
                    self.env,
                    runner.SCRIPT_STATE,
                    ["between", path, start, end, "--max", "0", "--paths"],
                    ok_codes=(0, 3),
                )
            except runner.RunnerError as exc:
                self.log = self._append_log(str(exc))
                continue
            names = set(between.data.get("changed_modules") or [])
            if between.data.get("error"):
                self.log = self._append_log(f"{path}: {between.data['error']}")
            modules |= snapshot.module_ids.filtered(
                lambda m, path=path: m.repo_line_id.path == path
                and m.name in names
                and m.module_state in ("installed", "to upgrade")
            ).module_id
        return modules

    def _execute_apply(self):
        self._check_flag_in_background()
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

    def _record_code_change(self, data):
        """After a run that moved repositories: take a snapshot, then
        record the installed modules whose code changed (from the
        ``chemin``/``depart``/``arrivee`` of ``data["resultats"]``) and
        those whose version waits for an upgrade.

        The pass is already on disk: a snapshot that fails must not erase
        its record, so the failure only goes to the log.
        """
        self.ensure_one()
        try:
            snapshot = self.env["erplibre.code.snapshot"]._capture(
                "upgrade", run=self, force=True
            )
        except runner.RunnerError as exc:
            self.log = self._append_log(str(exc))
            return
        changed = self._changed_modules(data, snapshot)
        pending = snapshot.module_ids.filtered("pending_update").module_id
        self.write(
            {
                "snapshot_id": snapshot.id,
                "code_changed_module_ids": [fields.Command.set(changed.ids)],
                "version_pending_module_ids": [fields.Command.set(pending.ids)],
                "upgrade_module_ids": [fields.Command.set((changed | pending).ids)],
            }
        )

    def _execute_restart(self):
        """A restart run is recorded done when it is requested."""

    def _check_flag_in_background(self):
        """The background step of a server action re-reads the odoo.conf
        flag, and the group of its requester: removing either stops a
        queued run."""
        if not self._flag_enabled():
            raise UserError(
                self.env._(
                    "Server actions are disabled. Set %(flag)s = True in the "
                    "Odoo configuration file to allow them.",
                    flag=FLAG_SERVER_ACTIONS,
                )
            )
        for run in self:
            if not (run.user_id and run.user_id.sudo().has_group("base.group_system")):
                raise AccessError(
                    self.env._("Only the Settings administrators run server actions.")
                )

    # ── actions ─────────────────────────────────────────────────────────

    def _action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def action_start_dry_run(self):
        self._check_server_actions()
        self._check_no_git_run()
        run = self._create_launched({"run_type": "dry_run"})
        run._enqueue()
        return run._action_open()

    @api.model
    def _check_no_git_run(self):
        """One git run at a time, whatever its type: two passes would move
        the same clones concurrently."""
        if self.search_count(
            [
                ("run_type", "in", GIT_RUN_TYPES),
                ("state", "in", ("queued", "running")),
            ]
        ):
            raise UserError(self.env._("A git run is already queued or running."))

    def action_apply(self):
        """Open the confirmation of the apply step: the first validation."""
        self.ensure_one()
        self._check_server_actions()
        if not self.can_apply:
            raise UserError(self.env._("This dry run has nothing left to apply."))
        return self.env["erplibre.code.confirm.wizard"]._action_open("apply", run=self)

    def _launch_apply(self):
        """Queue the apply step of this dry run; called by the confirmed
        wizard, the second validation."""
        self.ensure_one()
        self._check_server_actions()
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

    def _check_not_blocked(self):
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
        """Refuse a restart while the last pull left a repository
        mid-operation, whichever button asks for it: the last finished
        pull dry run or apply is an apply marked ``pull_blocked``. A new
        dry run, after the repository is fixed in a terminal, lifts it."""
        last = self.sudo().search(
            [
                ("run_type", "in", ("pull_dry_run", "pull_apply")),
                ("state", "in", ("done", "failed")),
            ],
            order="id desc",
            limit=1,
        )
        if last.run_type == "pull_apply" and last.pull_blocked:
            raise UserError(
                self.env._(
                    "The last pull left a repository mid-operation: fix it in "
                    "a terminal, then run a new pull dry run before "
                    "restarting."
                )
            )

    def action_restart(self):
        self._check_server_actions()
        self._check_not_blocked()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "restart", run=self[:1]
        )

    def action_restart_upgrade(self):
        self.ensure_one()
        self._check_server_actions()
        self._check_not_blocked()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "restart_upgrade", run=self, modules=self.upgrade_module_ids
        )

    def action_refresh(self):
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    @api.model
    def _request_restart(self, modules=None):
        """Record the restart, mark ``modules`` to upgrade, and restart the
        server once the transaction is committed.

        A module marked « to upgrade » is upgraded by the next registry
        load, so it runs with the code on disk; an immediate upgrade would
        run it with the Python already loaded in this process.
        """
        self._check_server_actions()
        self._check_no_blocked_pull()
        modules = modules or self.env["ir.module.module"]
        log = self.env._("Restart requested by %(user)s.", user=self.env.user.name)
        if modules:
            modules.button_upgrade()
            log += "\n" + self.env._(
                "Modules marked to upgrade: %(names)s",
                names=", ".join(sorted(modules.mapped("name"))),
            )
        run = self.create(
            {
                "run_type": "restart",
                "state": "done",
                "date_start": fields.Datetime.now(),
                "date_end": fields.Datetime.now(),
                "log": log,
            }
        )
        # The restarted process is a new server start for the startup
        # snapshot, even when the operating system keeps its pid.
        self.env["ir.config_parameter"].sudo().set_param(PARAM_STARTUP_KEY, "")
        self.env.cr.postcommit.add(_restart_server)
        _logger.info("ERPLibre: server restart requested (run %s)", run.id)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Restarting"),
                "message": self.env._(
                    "The server restarts. Reload the page in a few seconds."
                ),
                "sticky": True,
                "type": "warning",
            },
        }

    # ── startup snapshot ────────────────────────────────────────────────

    def _register_hook(self):
        res = super()._register_hook()
        try:
            self._schedule_startup_snapshot()
        except Exception:  # noqa: BLE001 - never break the registry load
            _logger.exception("ERPLibre: startup snapshot not scheduled")
        return res

    @api.model
    def _server_start_key(self):
        """Identity of the server process: the pid of the main process and
        its start time. Workers forked from it share it."""
        main = getattr(odoo_server, "server", None)
        pid = getattr(main, "pid", None) or os.getpid()
        try:
            import psutil

            started = psutil.Process(pid).create_time()
        except Exception:  # noqa: BLE001 - psutil missing or pid gone
            started = 0
        return f"{pid}:{started}"

    @api.model
    def _serves_http(self, main):
        """Whether this process serves HTTP: the threaded server once its
        HTTP thread is spawned, the prefork master once its socket is open.
        A registry loaded by ``odoo shell`` or a script has neither."""
        return bool(
            main and (getattr(main, "httpd", None) or getattr(main, "socket", None))
        )

    @api.model
    def _schedule_startup_snapshot(self):
        """Queue one snapshot per server start when the option is on.

        Nothing runs here: the snapshot is a queued run that the cron or
        queue_job executes later. Only a process that serves HTTP decides:
        the longpolling process (``odoo.evented``) and a registry loaded
        without a server (``odoo shell``) queue nothing. In the server
        process itself, a set of database names skips registry reloads. A
        forked worker loads its own registry: the key of the main process,
        kept in a parameter, lets only the first one queue the run (see
        ``_claim_startup_snapshot``). Return the queued run, or an empty
        recordset.
        """
        dbname = self.env.cr.dbname
        if dbname in _STARTUP_DONE:
            return self.browse()
        _STARTUP_DONE.add(dbname)
        if config.get("stop_after_init") and not self.env.context.get(
            "erplibre_info_force_startup"
        ):
            return self.browse()
        if odoo.evented:
            return self.browse()
        if not runner.param_bool(self.env, PARAM_STARTUP):
            return self.browse()
        main = getattr(odoo_server, "server", None)
        forked = bool(main and getattr(main, "pid", None) not in (None, os.getpid()))
        if forked:
            run = self.browse(self._claim_startup_snapshot(self._server_start_key()))
        elif not self._serves_http(main):
            return self.browse()
        else:
            # A savepoint: a failure here never aborts the registry load.
            with self.env.cr.savepoint():
                run = self._queue_startup_run()
        if run:
            _logger.info("ERPLibre: startup snapshot queued (run %s)", run.id)
        return run

    @api.model
    def _queue_startup_run(self):
        run = self.sudo().create(
            {"run_type": "snapshot", "trigger": "startup", "user_id": False}
        )
        run._enqueue()
        return run

    @api.model
    def _startup_cursor(self):
        """A new cursor on this database, apart from the registry load, in
        READ COMMITTED: each statement sees what other workers committed
        before it."""
        cr = self.pool.cursor()
        if isinstance(cr, sql_db.Cursor):
            cr.connection.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
        return cr

    @api.model
    def _claim_startup_snapshot(self, key):
        """Decide and queue the startup run of a forked worker in a short
        transaction of its own. Return the id of the queued run, or False
        when another worker of the same server start already queued it.

        The advisory lock is the first statement of that transaction, which
        reads in READ COMMITTED (see ``_startup_cursor``): once the lock is
        held, the key that the previous holder committed is visible,
        whatever the age of the registry-load transaction. That transaction
        never reads nor writes the key, so a failure here cannot abort it.
        """
        with self._startup_cursor() as cr:
            cr.execute("SELECT pg_try_advisory_xact_lock(%s)", [_STARTUP_LOCK])
            if not cr.fetchone()[0]:
                return False
            cr.execute(
                "SELECT value FROM ir_config_parameter WHERE key = %s",
                [PARAM_STARTUP_KEY],
            )
            row = cr.fetchone()
            if row and row[0] == key:
                return False
            env = api.Environment(cr, SUPERUSER_ID, {})
            env["ir.config_parameter"].set_param(PARAM_STARTUP_KEY, key)
            run = env[self._name]._queue_startup_run()
            env.flush_all()
            return run.id

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
