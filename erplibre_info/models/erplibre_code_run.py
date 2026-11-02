# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The common run model: a long action on the code, queued then executed
in the background by the ERPLibre cron or by queue_job.

This module declares one run type, the server restart, recorded done when
it is requested. Each module that adds a type extends ``run_type`` with
``selection_add`` and defines ``_execute_<type>``, and optionally
``_render_<type>`` for the report of its JSON result.
"""

import json
import logging
import os

import psycopg2

import odoo
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.service import server as odoo_server
from odoo.tools import config, str2bool

from .. import runner

_logger = logging.getLogger(__name__)

FLAG_SERVER_ACTIONS = "erplibre_info_allow_server_actions"
CRON_XMLID = "erplibre_info.ir_cron_erplibre_code"

# The fields of a run that decide what its background step runs: only the
# launch methods set them, through ``_create_launched``. A module adds its
# own through ``_launch_fields``.
LAUNCH_FIELDS = (
    "run_type",
    "user_id",
)


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
        [("restart", "Server restart")],
        string="Type",
        required=True,
        readonly=True,
    )
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
    report_html = fields.Html(compute="_compute_report_html", sanitize=False)
    server_actions_allowed = fields.Boolean(compute="_compute_server_actions_allowed")

    @api.depends("run_type", "create_date")
    @api.depends_context("lang")
    def _compute_name(self):
        """The type and the creation time. A name is plain text, which the
        web client never converts to the viewer's time zone as it does a
        Datetime field: the time stays in UTC, as stored, and says so."""
        labels = dict(self._fields["run_type"]._description_selection(self.env))
        for run in self:
            date = fields.Datetime.to_string(run.create_date or fields.Datetime.now())
            run.name = f"{labels.get(run.run_type, run.run_type)} {date} UTC"

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

    # ── guards ──────────────────────────────────────────────────────────

    @api.model
    def _git_run_types(self):
        """The run types that run git on the checkout: one of them at a
        time, created only by a launch method. None here; a module that
        adds one extends this tuple."""
        return ()

    @api.model
    def _launch_fields(self):
        """The fields that only a launch method sets (``LAUNCH_FIELDS``);
        a module adds the fields that decide what its run types execute."""
        return LAUNCH_FIELDS

    @api.model_create_multi
    def create(self, vals_list):
        """A run of a git type is created only by a launch method
        (``_create_launched``), after the checks and the confirmations of
        its button: created through the ORM or RPC, its background step
        would skip them."""
        git_types = self._git_run_types()
        if not self.env.su and any(
            vals.get("run_type") in git_types for vals in vals_list
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
            any(field in vals for field in self._launch_fields())
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
    def _flag_problem(self):
        """Why the odoo.conf flag is off, naming the configuration file this
        server read at startup (``config.rcfile``), which is not always the
        one the admin edited; False when the flag is on."""
        if self._flag_enabled():
            return False
        rcfile = config.rcfile
        if not rcfile or not os.path.isfile(rcfile):
            return self.env._(
                "Server actions are disabled: this Odoo server started "
                "without a configuration file. Start it with -c <file>, the "
                "file holding %(flag)s = True.",
                flag=FLAG_SERVER_ACTIONS,
            )
        if FLAG_SERVER_ACTIONS in config.options:
            return self.env._(
                "Server actions are disabled: %(flag)s reads %(value)s in "
                "%(file)s. Set it to True, then restart Odoo.",
                flag=FLAG_SERVER_ACTIONS,
                value=config.options[FLAG_SERVER_ACTIONS],
                file=rcfile,
            )
        return self.env._(
            "Server actions are disabled: add %(flag)s = True to the "
            "[options] section of %(file)s, the configuration file this Odoo "
            "server read at startup, then restart Odoo.",
            flag=FLAG_SERVER_ACTIONS,
            file=rcfile,
        )

    @api.model
    def _server_actions_problem(self):
        """The first of the three conditions that fails, as a translated
        message, or False when the server actions are allowed."""
        flag = self._flag_problem()
        if flag:
            return flag
        if not self.env.user.has_group("base.group_system"):
            return self.env._("Only the Settings administrators run server actions.")
        if not self._is_debug_mode():
            return self.env._("Server actions require the developer mode.")
        return False

    @api.model
    def _check_server_actions(self):
        """Raise unless the three conditions of the server actions hold:
        the odoo.conf flag, the Settings group, the developer mode."""
        flag = self._flag_problem()
        if flag:
            raise UserError(flag)
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                self.env._("Only the Settings administrators run server actions.")
            )
        if not self._is_debug_mode():
            raise UserError(self.env._("Server actions require the developer mode."))

    def _check_flag_in_background(self):
        """The background step of a server action re-reads the odoo.conf
        flag, and the group of its requester: removing either stops a
        queued run."""
        flag = self._flag_problem()
        if flag:
            raise UserError(flag)
        for run in self:
            if not (run.user_id and run.user_id.sudo().has_group("base.group_system")):
                raise AccessError(
                    self.env._("Only the Settings administrators run server actions.")
                )

    @api.model
    def _check_no_git_run(self):
        """One git run at a time, whatever its type: two passes would move
        the same clones concurrently."""
        if self.search_count(
            [
                ("run_type", "in", self._git_run_types()),
                ("state", "in", ("queued", "running")),
            ]
        ):
            raise UserError(self.env._("A git run is already queued or running."))

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
    def _cron_needed(self, states=("queued",)):
        """Whether the cron has work: one of its runs in ``states``. A
        module with periodic work of its own extends it."""
        return bool(self.sudo().search_count(self._cron_runs_domain(states)))

    @api.model
    def _sync_cron(self):
        """The cron is active while ``_cron_needed`` holds for a run that
        waits or executes. Return the cron.

        The write goes through ``try_write``: while the cron executes a job
        it holds a lock on its row, and the write is then skipped instead
        of failing the caller (a Settings save). A run that executes keeps
        the cron needed, so the cron is never switched off under its own
        job; the job switches itself off at its end when nothing needs it.
        """
        cron = self._cron()
        if not cron:
            return cron
        needed = self._cron_needed(("queued", "running"))
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
        requester, then the periodic work of ``_cron_periodic``. The cron
        deactivates itself when nothing else needs it. The runs handed to
        queue_job are left to it."""
        done = 0
        runs = self.with_context(erplibre_info_commit=True)
        for run in runs.search(self._cron_runs_domain(), order="id"):
            run.with_context(lang=run._run_lang())._execute()
            run._commit()
            done += 1
        self._cron_periodic()
        self.env["ir.cron"]._notify_progress(
            done=done, remaining=0, deactivate=not self._cron_needed()
        )
        return done

    @api.model
    def _cron_periodic(self):
        """The periodic work of the cron, after its queued runs: none here.
        A module with periodic work extends it, and ``_cron_needed``."""

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
        """Run one queued run through ``_execute_<run_type>``; record its
        outcome, never raise. Return True when the run went through."""
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

    def action_refresh(self):
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    # ── restart ─────────────────────────────────────────────────────────

    def _execute_restart(self):
        """A restart run is recorded done when it is requested."""

    def _check_restart_allowed(self):
        """Raise when the server must not restart now; nothing blocks it
        here. A module whose runs can leave the code mid-operation extends
        it."""

    def action_restart(self):
        self._check_server_actions()
        self._check_restart_allowed()
        return self.env["erplibre.code.confirm.wizard"]._action_open(
            "restart", run=self[:1]
        )

    @api.model
    def _request_restart(self, modules=None):
        """Record the restart, mark ``modules`` to upgrade, and restart the
        server once the transaction is committed. Return the notification
        of the web client.

        A module marked « to upgrade » is upgraded by the next registry
        load, so it runs with the code on disk; an immediate upgrade would
        run it with the Python already loaded in this process.
        """
        self._check_server_actions()
        self._check_restart_allowed()
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
