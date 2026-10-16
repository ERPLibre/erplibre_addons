# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
from contextlib import contextmanager
from unittest.mock import patch

import odoo
from odoo import sql_db
from odoo.tests import new_test_user, tagged

from .. import runner
from ..models import erplibre_code_run
from .common import ErplibreInfoCase


class _Server:
    """Stand-in for ``odoo.service.server.server``."""

    def __init__(self, pid=None, httpd=True):
        self.pid = os.getpid() if pid is None else pid
        self.httpd = object() if httpd else None


@tagged("post_install", "-at_install")
class TestSettings(ErplibreInfoCase):
    def _save(self, **vals):
        settings = self.env["res.config.settings"].create(vals)
        settings.execute()
        return settings

    @contextmanager
    def same_cursor(self):
        """The startup decision of a forked worker on the test transaction:
        a savepoint stands for its own committed transaction."""

        @contextmanager
        def cursor(self_):
            with self.env.cr.savepoint():
                yield self.env.cr

        with patch.object(type(self.Run), "_startup_cursor", cursor):
            yield

    @contextmanager
    def server(self, **kw):
        with patch.object(
            erplibre_code_run.odoo_server, "server", _Server(**kw), create=True
        ), patch.object(erplibre_code_run, "_STARTUP_DONE", set()):
            yield

    def _startup_on(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "erplibre_info.snapshot_on_startup", "True"
        )
        return self.Run.with_context(erplibre_info_force_startup=True)

    def test_periodic_toggles_cron(self):
        self._save(
            erplibre_snapshot_periodic=True,
            erplibre_snapshot_interval_number=6,
            erplibre_snapshot_interval_type="hours",
        )
        self.assertTrue(self.cron.active)
        self.assertEqual(self.cron.interval_number, 6)
        self.assertEqual(self.cron.interval_type, "hours")
        values = self.env["res.config.settings"].create({})
        self.assertTrue(values.erplibre_snapshot_periodic)
        self.assertEqual(values.erplibre_snapshot_interval_number, 6)
        self._save(erplibre_snapshot_periodic=False)
        self.assertFalse(self.cron.active)
        self.assertEqual(self.fake.calls, [])

    def test_summary_reads_the_last_snapshot(self):
        settings = self.env["res.config.settings"].create({})
        self.assertFalse(settings.erplibre_last_snapshot_id)
        snap = self.Snapshot._capture("manual")
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.erplibre_last_snapshot_id, snap)
        self.assertEqual(settings.erplibre_commit, "v0.0.0-1-gaaaaaaa")
        self.assertIn("2", settings.erplibre_state_summary)

    def test_startup_schedules_one_run(self):
        Run = self._startup_on()
        with self.server():
            run = Run._schedule_startup_snapshot()
            self.assertEqual(run.trigger, "startup")
            self.assertEqual(run.state, "queued")
            self.assertTrue(self.cron.active)
            triggers = self.env["ir.cron.trigger"].search(
                [("cron_id", "=", self.cron.id)]
            )
            self.assertTrue(triggers)
            self.assertFalse(Run._schedule_startup_snapshot())
            self.Run._register_hook()
        self.assertEqual(self.Run.search_count([("trigger", "=", "startup")]), 1)
        # Nothing ran during the registry load: the cron runs it later.
        self.assertEqual(self.fake.calls, [])
        self.Run._cron_process()
        self.assertEqual(run.state, "done")
        self.assertTrue(run.snapshot_id)
        self.assertEqual(run.snapshot_id.trigger, "startup")

    def test_startup_off_schedules_nothing(self):
        Run = self.Run.with_context(erplibre_info_force_startup=True)
        with self.server():
            self.assertFalse(Run._schedule_startup_snapshot())
        self.assertFalse(self.cron.active)

    def test_startup_skips_processes_without_http(self):
        """The longpolling process and an ``odoo shell`` load the registry
        too; neither is a server start."""
        Run = self._startup_on()
        with self.server(), patch.object(odoo, "evented", True):
            self.assertFalse(Run._schedule_startup_snapshot())
        with self.server(httpd=False):
            self.assertFalse(Run._schedule_startup_snapshot())
        with patch.object(
            erplibre_code_run.odoo_server, "server", None, create=True
        ), patch.object(erplibre_code_run, "_STARTUP_DONE", set()):
            self.assertFalse(Run._schedule_startup_snapshot())
        self.assertFalse(self.Run.search_count([("trigger", "=", "startup")]))

    def test_startup_key_committed_after_the_load_snapshot(self):
        """Worker A commits the key after worker B began its registry load:
        B decides on a transaction of its own, sees the key and queues
        nothing; its load transaction stays usable."""
        key = "erplibre_info_test:1"
        db = sql_db.db_connect(self.env.cr.dbname)
        select = "SELECT value FROM ir_config_parameter WHERE key = %s"
        load_cr = db.cursor()
        self.addCleanup(load_cr.close)
        load_cr.execute("SET LOCAL lock_timeout = '10s'")
        load_cr.execute(select, [erplibre_code_run.PARAM_STARTUP_KEY])
        before = load_cr.fetchone()
        self.assertNotEqual(before and before[0], key)

        def cleanup():
            with db.cursor() as cr:
                cr.execute("SET LOCAL lock_timeout = '10s'")
                cr.execute(
                    "DELETE FROM ir_config_parameter WHERE key = %s AND value = %s",
                    [erplibre_code_run.PARAM_STARTUP_KEY, key],
                )

        with db.cursor() as other:
            other.execute("SET LOCAL lock_timeout = '10s'")
            other.execute(
                "INSERT INTO ir_config_parameter (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                [erplibre_code_run.PARAM_STARTUP_KEY, key],
            )
        self.addCleanup(cleanup)

        # The decision opens a cursor of its own: a new transaction of the
        # database, whose first statement takes the lock. Queuing a run
        # there would be committed: it fails the test, and rolls back.
        with patch.object(
            type(self.Run),
            "_queue_startup_run",
            side_effect=AssertionError("a second startup run"),
        ):
            self.assertFalse(self.Run._claim_startup_snapshot(key))
        # The load transaction still reads its own snapshot, and runs SQL.
        load_cr.execute(select, [erplibre_code_run.PARAM_STARTUP_KEY])
        self.assertEqual(load_cr.fetchone(), before)
        self.assertFalse(self.Run.search_count([("trigger", "=", "startup")]))

    def test_forked_worker_uses_the_server_key(self):
        Run = self._startup_on()
        with self.same_cursor(), self.server(pid=-1):
            run = Run._schedule_startup_snapshot()
            self.assertTrue(run)
            self.assertEqual(run.trigger, "startup")
        # Another worker of the same server: a new process, same key.
        with self.same_cursor(), self.server(pid=-1):
            self.assertFalse(Run._schedule_startup_snapshot())
        self.assertEqual(self.Run.search_count([("trigger", "=", "startup")]), 1)

    def test_cron_periodic_snapshot(self):
        self._save(erplibre_snapshot_periodic=True)
        self.Run._cron_process()
        self.Run._cron_process()
        self.assertEqual(self.Snapshot.search([]).mapped("trigger"), ["cron"])

    def test_running_run_keeps_the_cron(self):
        """While the cron executes a run, a Settings save never writes the
        cron row, which the executing job holds locked."""
        self.cron.active = True
        run = self.Run.create({"run_type": "snapshot", "trigger": "manual"})
        run.write({"state": "running"})
        Cron = type(self.cron)
        with patch.object(Cron, "try_write") as try_write, patch.object(
            Cron, "write"
        ) as write:
            self.Run._sync_cron()
            self._save(erplibre_snapshot_periodic=False)
        try_write.assert_not_called()
        write.assert_not_called()

    def test_save_while_the_cron_is_locked(self):
        """A cron row locked by its job makes ``try_write`` skip the write:
        the Settings save still succeeds."""
        self._save(erplibre_snapshot_periodic=True)
        with patch.object(
            type(self.cron), "try_write", return_value=False
        ) as try_write:
            self._save(
                erplibre_snapshot_periodic=False,
                erplibre_snapshot_interval_number=3,
            )
        self.assertTrue(try_write.called)
        self.assertEqual(self.cron.interval_number, 1)

    def test_periodic_failure_is_recorded_once(self):
        self._save(erplibre_snapshot_periodic=True)
        error = runner.RunnerError("The ERPLibre checkout was not found.")
        with patch.object(runner, "run_json", side_effect=error):
            self.Run._cron_process()
            self.Run._cron_process()
        failed = self.Run.search([("trigger", "=", "cron")])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed.state, "failed")
        self.assertEqual(failed.run_type, "snapshot")
        self.assertIn("not found", failed.log)
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.erplibre_last_failed_run_id, failed)
        self.assertIn("not found", settings.erplibre_last_failed_log)
        # A snapshot that succeeds hides the failure.
        self.Run._cron_process()
        settings = self.env["res.config.settings"].create({})
        self.assertFalse(settings.erplibre_last_failed_run_id)

    def test_checkout_problem_is_shown(self):
        settings = self.env["res.config.settings"].create({})
        self.assertFalse(settings.erplibre_checkout_problem)
        self.env["ir.config_parameter"].sudo().set_param(
            runner.PARAM_ROOT, os.path.join(self.root, "missing")
        )
        settings = self.env["res.config.settings"].create({})
        self.assertIn(runner.PARAM_ROOT, settings.erplibre_checkout_problem)

    def test_runs_log_in_the_requester_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env["ir.module.module"]._load_module_terms(["erplibre_info"], ["fr_FR"])
        user = new_test_user(
            self.env,
            login="erplibre_info_fr",
            groups="base.group_system",
            lang="fr_FR",
        )
        self.Snapshot._capture("manual")
        run = self.Run.with_user(user).create(
            {"run_type": "snapshot", "trigger": "cron"}
        )
        run._enqueue()
        self.Run.sudo()._cron_process()
        self.assertEqual(run.state, "done", run.log)
        self.assertIn("Le code n'a pas changé", run.log)
        self.assertIn(
            "Instantané",
            run.with_context(lang="fr_FR").name,
        )
        self.assertIn("Snapshot", run.with_context(lang="en_US").name)
