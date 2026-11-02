# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import copy
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import config

from odoo.addons.erplibre_info.tests.common import APPLY, REPO, SERIES

from .. import hooks
from .common import ErplibreInfoGitFetchCase


@tagged("post_install", "-at_install")
class TestServerActions(ErplibreInfoGitFetchCase):
    def setUp(self):
        super().setUp()
        self.env.cr.postcommit.clear()

    def _wizard(self, action, run=None, modules=None, typed=None, understood=True):
        res = self.env["erplibre.code.confirm.wizard"]._action_open(
            action, run=run, modules=modules
        )
        wizard = self.env["erplibre.code.confirm.wizard"].browse(res["res_id"])
        wizard.write(
            {
                "typed_database_name": (self.env.cr.dbname if typed is None else typed),
                "understood": understood,
            }
        )
        return wizard

    def _done_dry_run(self):
        with self.server_actions_allowed():
            self.Run.action_start_dry_run()
        run = self.Run.search([("run_type", "=", "dry_run")])
        self.Run._cron_process()
        return run

    # ── guards ──────────────────────────────────────────────────────────

    def test_flag_off(self):
        with self.server_actions_allowed(flag=False):
            with self.assertRaises(UserError):
                self.Run.action_start_dry_run()
            self.assertFalse(self.Run._git_fetch_allowed())
        self.assertFalse(self.Run.search_count([]))

    def test_no_debug(self):
        with self.server_actions_allowed(debug=False):
            with self.assertRaises(UserError):
                self.env["res.config.settings"].create(
                    {}
                ).action_erplibre_fetch_rebase()

    # ── --dev ───────────────────────────────────────────────────────────

    def test_install_refused_without_dev(self):
        with patch.dict(config.options, {"dev_mode": []}):
            with self.assertRaisesRegex(UserError, "--dev"):
                hooks.post_init_hook(self.env)
        with patch.dict(config.options, {"dev_mode": ["all"]}):
            hooks.post_init_hook(self.env)

    def test_no_dev(self):
        """A server started without --dev refuses fetch + rebase and pull,
        on top of the three conditions of erplibre_info, and says why; the
        restart keeps the three conditions only."""
        with self.server_actions_allowed(dev=False):
            self.assertFalse(self.Run._git_fetch_allowed())
            self.assertTrue(self.Run._server_actions_allowed())
            settings = self.env["res.config.settings"].create({})
            self.assertFalse(settings.erplibre_git_fetch_allowed)
            self.assertIn("--dev", settings.erplibre_git_fetch_problem)
            self.assertTrue(settings.erplibre_server_actions_allowed)
            self.assertFalse(settings.erplibre_server_actions_problem)
            with self.assertRaisesRegex(UserError, "--dev"):
                self.Run._check_git_fetch()
            with self.assertRaisesRegex(UserError, "--dev"):
                self.Run.action_start_dry_run()
            with self.assertRaisesRegex(UserError, "--dev"):
                settings.action_erplibre_fetch_rebase()
            with self.assertRaisesRegex(UserError, "--dev"):
                settings.action_erplibre_pull()
            action = settings.action_erplibre_restart()
        self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")
        self.assertFalse(self.Run.search_count([]))

    def test_no_dev_refused_at_confirmation(self):
        with self.server_actions_allowed():
            dry_run = self._done_dry_run()
            self.assertEqual(dry_run.state, "done", dry_run.log)
            wizard = self._wizard("apply", run=dry_run)
        with self.server_actions_allowed(dev=False):
            with self.assertRaisesRegex(UserError, "--dev"):
                wizard.action_confirm()
        self.assertFalse(self.Run.search_count([("run_type", "=", "apply")]))

    def test_no_dev_restart_allowed(self):
        """The restart, also after an apply, needs no --dev."""
        with self.server_actions_allowed(), patch("odoo.service.server.restart"):
            dry_run = self._done_dry_run()
            self._wizard("apply", run=dry_run).action_confirm()
            self.Run._cron_process()
        apply_run = self.Run.search([("run_type", "=", "apply")])
        self.assertEqual(apply_run.state, "done", apply_run.log)
        with self.server_actions_allowed(dev=False), patch(
            "odoo.service.server.restart"
        ) as restart:
            action = apply_run.action_restart_upgrade()
            wizard = self.env["erplibre.code.confirm.wizard"].browse(action["res_id"])
            wizard.write(
                {"typed_database_name": self.env.cr.dbname, "understood": True}
            )
            wizard.action_confirm()
            self.env.cr.postcommit.run()
            restart.assert_called_once_with()
        self.assertEqual(self.Run.search_count([("run_type", "=", "restart")]), 1)

    def test_no_dev_stops_the_background_step(self):
        """A run queued with --dev stops in the background on a server
        restarted without it: no script runs."""
        with self.server_actions_allowed():
            run = self.Run.browse(self.Run.action_start_dry_run()["res_id"])
        with self.server_actions_allowed(dev=False):
            self.Run._cron_process()
        self.assertEqual(run.state, "failed")
        self.assertIn("--dev", run.log)
        self.assertEqual(self.fake.calls, [])

    # ── fetch + rebase ──────────────────────────────────────────────────

    def test_dry_run_runs_in_background(self):
        with self.server_actions_allowed():
            action = self.Run.action_start_dry_run()
        run = self.Run.browse(action["res_id"])
        self.assertEqual(run.state, "queued")
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(self.cron.active)
        with self.server_actions_allowed():
            self.Run._cron_process()
        self.assertEqual(run.state, "done", run.log)
        self.assertEqual(
            self.fake.scripts(),
            [
                (
                    "repo_upgrade.py",
                    ["--add-remotes", "--version", SERIES, "--json"],
                ),
                (
                    "repo_upgrade.py",
                    ["--diagnostic", "--version", SERIES, "--json"],
                ),
            ],
        )
        self.assertEqual(run.plan_paths, REPO)
        self.assertEqual(run.left_paths, "odooX/conflict")
        self.assertEqual(run.odoo_version, SERIES)
        self.assertIn("a_rebaser", run.report_html)
        self.assertTrue(run.can_apply)

    def test_one_fetch_rebase_at_a_time(self):
        with self.server_actions_allowed():
            self.Run.action_start_dry_run()
            with self.assertRaises(UserError):
                self.Run.action_start_dry_run()

    def test_background_step_rereads_the_flag(self):
        """The flag turned off between the queueing and the run stops the
        run; it is set explicitly, the odoo.conf of the checkout may have
        it on."""
        with self.server_actions_allowed():
            self.Run.action_start_dry_run()
        with self.server_actions_allowed(flag=False):
            self.Run._cron_process()
        run = self.Run.search([("run_type", "=", "dry_run")])
        self.assertEqual(run.state, "failed")
        self.assertEqual(self.fake.calls, [])

    def test_apply_requires_double_validation(self):
        with self.server_actions_allowed():
            dry_run = self._done_dry_run()
        self.assertEqual(dry_run.state, "done", dry_run.log)
        self.fake.calls.clear()
        with self.server_actions_allowed():
            action = dry_run.action_apply()
            self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")
            self.assertFalse(self.Run.search_count([("run_type", "=", "apply")]))
            with self.assertRaises(UserError):
                self._wizard("apply", run=dry_run, typed="x").action_confirm()
            with self.assertRaises(UserError):
                self._wizard("apply", run=dry_run, understood=False).action_confirm()
            self.assertFalse(self.Run.search_count([("run_type", "=", "apply")]))
            action = self._wizard("apply", run=dry_run).action_confirm()
            apply_run = self.Run.browse(action["res_id"])
            self.assertEqual(apply_run.state, "queued")
            self.assertFalse(dry_run.can_apply)
            self.assertEqual(self.fake.calls, [])
            self.Run._cron_process()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        script, args = self.fake.scripts()[0]
        self.assertEqual(script, "repo_apply.py")
        # The plan is pinned to the upstream commit and the HEAD shown.
        self.assertEqual(
            args,
            [
                "--apply",
                "--confirm",
                SERIES,
                "--json",
                "--expect",
                f"{REPO}={'c' * 40}:{'1' * 40}",
            ],
        )
        self.assertNotIn("--publish", " ".join(args))
        self.assertEqual(apply_run.pass_dir, "tasks/git_repo_upgrade/20000101T0000")
        self.assertEqual(apply_run.snapshot_id.trigger, "upgrade")
        self.assertEqual(apply_run.snapshot_id.run_id, apply_run)
        self.assertIn(
            self.env.ref("base.module_erplibre_info"),
            apply_run.upgrade_module_ids,
        )

    def test_apply_with_changed_plan_fails(self):
        with self.server_actions_allowed():
            dry_run = self._done_dry_run()
            self.fake.answers[("repo_apply.py", "--apply")] = (
                4,
                {"error": "plan_changed", "plan": [], "resultats": []},
            )
            self._wizard("apply", run=dry_run).action_confirm()
            self.Run._cron_process()
        apply_run = self.Run.search([("run_type", "=", "apply")])
        self.assertEqual(apply_run.state, "failed")
        self.assertFalse(apply_run.snapshot_id)
        # The upstream moved: this dry run can no longer be applied.
        dry_run.invalidate_recordset()
        self.assertFalse(dry_run.can_apply)
        self.assertTrue(dry_run.apply_note)
        with self.server_actions_allowed(), self.assertRaises(UserError):
            dry_run.action_apply()

    def test_only_the_last_dry_run_applies(self):
        with self.server_actions_allowed():
            first = self._done_dry_run()
            self.assertTrue(first.can_apply)
            self.Run.action_start_dry_run()
            self.Run._cron_process()
        second = self.Run.search([("run_type", "=", "dry_run")], limit=1)
        self.assertNotEqual(first, second)
        first.invalidate_recordset()
        self.assertFalse(first.can_apply)
        self.assertTrue(first.apply_note)
        self.assertTrue(second.can_apply)

    def test_apply_proposes_the_modules_whose_code_changed(self):
        """A rebase that changes a module without a version bump still
        proposes its upgrade; a repository the apply did not move is not
        read."""
        module = self.env.ref("base.module_erplibre_info")
        mod = self.fake.snapshot["repos"][0]["modules"][0]
        mod["version"] = module.latest_version
        self.fake.changed_modules = ["erplibre_info"]
        apply_data = copy.deepcopy(APPLY)
        apply_data["resultats"].append(
            {
                "chemin": "odooX/same",
                "etat": "avance",
                "depart": "e" * 40,
                "arrivee": "e" * 40,
            }
        )
        self.fake.answers[("repo_apply.py", "--apply")] = (0, apply_data)
        with self.server_actions_allowed():
            dry_run = self._done_dry_run()
            self._wizard("apply", run=dry_run).action_confirm()
            self.fake.calls.clear()
            self.Run._cron_process()
        apply_run = self.Run.search([("run_type", "=", "apply")])
        self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertFalse(apply_run.version_pending_module_ids)
        self.assertEqual(apply_run.code_changed_module_ids, module)
        self.assertEqual(apply_run.upgrade_module_ids, module)
        betweens = [a for s_, a in self.fake.scripts() if a[0] == "between"]
        self.assertEqual(
            betweens,
            [["between", REPO, "1" * 40, "c" * 40, "--max", "0", "--paths"]],
        )
