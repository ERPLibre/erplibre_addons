# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The snapshot run: a capture of the code in the background, queued by a
button, at server start or by the periodic cron. It only reads the
clones."""

import logging
import os
import zlib

from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

import odoo
from odoo import SUPERUSER_ID, api, fields, models, sql_db
from odoo.service import server as odoo_server
from odoo.tools import config

from odoo.addons.erplibre_info import runner

_logger = logging.getLogger(__name__)

PARAM_STARTUP = "erplibre_info.snapshot_on_startup"
PARAM_PERIODIC = "erplibre_info.snapshot_periodic"
PARAM_STARTUP_KEY = "erplibre_info.startup_key"

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


class ErplibreCodeRun(models.Model):
    _inherit = "erplibre.code.run"

    run_type = fields.Selection(
        selection_add=[("snapshot", "Snapshot"), ("restart",)],
        ondelete={"snapshot": "cascade"},
    )
    trigger = fields.Selection(TRIGGERS, readonly=True)
    snapshot_id = fields.Many2one(
        "erplibre.code.snapshot", readonly=True, ondelete="set null"
    )
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

    # ── cron ────────────────────────────────────────────────────────────

    @api.model
    def _cron_needed(self, states=("queued",)):
        """The periodic snapshot keeps the cron needed while it is on."""
        return runner.param_bool(self.env, PARAM_PERIODIC) or super()._cron_needed(
            states
        )

    @api.model
    def _cron_periodic(self):
        """The periodic snapshot, when it is on: stored only when the code
        changed. A snapshot that cannot run is recorded as a failed run."""
        super()._cron_periodic()
        if not runner.param_bool(self.env, PARAM_PERIODIC):
            return
        snapshots = self.env["erplibre.code.snapshot"].with_context(
            lang=self._default_lang()
        )
        try:
            snapshots._capture("cron")
        except runner.RunnerError as exc:
            _logger.warning("ERPLibre periodic snapshot: %s", exc)
            self._record_periodic_failure(str(exc))

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

    # ── execution ───────────────────────────────────────────────────────

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

    # ── restart ─────────────────────────────────────────────────────────

    def action_restart_upgrade(self):
        """Open the confirmation of a restart that upgrades the modules of
        ``upgrade_module_ids`` first."""
        self.ensure_one()
        self._check_server_actions()
        self._check_restart_allowed()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "restart_upgrade", run=self, modules=self.upgrade_module_ids
        )

    @api.model
    def _request_restart(self, modules=None):
        """The restarted process is a new server start for the startup
        snapshot, even when the operating system keeps its pid: its key is
        cleared."""
        res = super()._request_restart(modules)
        self.env["ir.config_parameter"].sudo().set_param(PARAM_STARTUP_KEY, "")
        return res

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
