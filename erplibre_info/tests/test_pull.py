# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import copy
import os
import shutil
import subprocess
import tempfile
import time
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from .. import runner
from .common import (
    PULL_APPLY,
    PULL_DIR,
    PULL_DRY_RUN,
    PULL_STAMP,
    REPO,
    REPO_BUSY,
    REPO_NEW,
    REPO_SHALLOW,
    SERIES,
    ErplibreInfoCase,
)

BACKUP_REPO = f"{SERIES}_avant_pull_{PULL_STAMP}"


@tagged("post_install", "-at_install")
class TestPull(ErplibreInfoCase):
    def setUp(self):
        super().setUp()
        self.env.cr.postcommit.clear()
        self.Wizard = self.env["erplibre.code.pull.wizard"]
        self.Backup = self.env["erplibre.code.pull.backup"]

    # ── helpers ─────────────────────────────────────────────────────────

    def _confirm(self, action, run=None, backup=None, typed=None, **vals):
        res = self.env["erplibre.code.confirm.wizard"]._action_open(
            action, run=run, backup=backup
        )
        wizard = self.env["erplibre.code.confirm.wizard"].browse(res["res_id"])
        wizard.write(
            dict(
                {
                    "typed_database_name": (
                        self.env.cr.dbname if typed is None else typed
                    ),
                    "understood": True,
                },
                **vals,
            )
        )
        return wizard

    def _pull_dry_run(self, **vals):
        """A pull dry run started from the wizard and executed by the cron;
        the server actions must be allowed by the caller."""
        action = self.Wizard._action_open()
        wizard = self.Wizard.browse(action["res_id"])
        if vals:
            wizard.write(vals)
        run = self.Run.browse(wizard.action_start()["res_id"])
        self.Run._cron_process()
        return run

    def _pull_apply(self, **vals):
        dry_run = self._pull_dry_run()
        action = self._confirm("pull_apply", run=dry_run, **vals).action_confirm()
        apply_run = self.Run.browse(action["res_id"])
        self.fake.calls.clear()
        with patch.object(type(self.Run), "_pull_stamp", lambda self_: PULL_STAMP):
            self.Run._cron_process()
        return dry_run, apply_run

    def _pull_args(self, flag):
        return [
            a for s, a in self.fake.scripts() if s == "repo_pull.py" and a[0] == flag
        ]

    def _repo_line(self, branch=None):
        self.fake.snapshot["repos"][0]["branch"] = branch
        snapshot = self.Snapshot._capture("manual", force=True)
        return snapshot.repo_ids.filtered(lambda r: r.path == REPO)

    # ── guards ──────────────────────────────────────────────────────────

    def test_guards(self):
        """Every entry of the pull refuses without the three conditions."""
        line = self._repo_line()
        with self.server_actions_allowed():
            dry_run = self._pull_dry_run()
            _dry, apply_run = self._pull_apply()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        backup = apply_run.backup_ids[:1]
        self.assertTrue(backup)
        user = new_test_user(
            self.env, login="erplibre_info_puller", groups="base.group_user"
        )
        entries = [
            lambda env: env["erplibre.code.pull.wizard"]._action_open(),
            lambda env: env["erplibre.code.snapshot.repo"]
            .browse(line.id)
            .action_pull(),
            lambda env: env["erplibre.code.run"].browse(dry_run.id).action_pull_apply(),
            lambda env: env["erplibre.code.run"]
            .browse(apply_run.id)
            .action_deps_install(),
            lambda env: env["erplibre.code.pull.backup"]
            .browse(backup.id)
            .action_restore(),
            lambda env: env["erplibre.code.pull.backup"]
            .browse(backup.id)
            .action_delete(),
            lambda env: env["res.config.settings"].create({}).action_erplibre_pull(),
        ]
        for entry in entries:
            with self.server_actions_allowed(flag=False), self.assertRaises(UserError):
                entry(self.env)
            with self.server_actions_allowed(debug=False), self.assertRaises(UserError):
                entry(self.env)
            with self.server_actions_allowed(), self.assertRaises(AccessError):
                entry(self.env(user=user))
        self.fake.calls.clear()
        with self.server_actions_allowed():
            wizard = self.Wizard.browse(self.Wizard._action_open()["res_id"])
        with self.server_actions_allowed(flag=False), self.assertRaises(UserError):
            wizard.action_start()
        self.assertEqual(backup.state, "kept")
        self.assertFalse(self._pull_args("--delete-backup"))

    def test_background_step_rereads_the_flag(self):
        with self.server_actions_allowed():
            wizard = self.Wizard.browse(self.Wizard._action_open()["res_id"])
            run = self.Run.browse(wizard.action_start()["res_id"])
        self.Run._cron_process()
        self.assertEqual(run.state, "failed")
        self.assertEqual(self.fake.calls, [])

    def test_one_git_run_at_a_time(self):
        """A fetch + rebase and a pull never run together."""
        with self.server_actions_allowed():
            self.Run.action_start_dry_run()
            with self.assertRaises(UserError):
                self.Wizard.browse(self.Wizard._action_open()["res_id"]).action_start()
            self.Run._cron_process()
            wizard = self.Wizard.browse(self.Wizard._action_open()["res_id"])
            wizard.action_start()
            with self.assertRaises(UserError):
                self.Run.action_start_dry_run()

    # ── strategy ────────────────────────────────────────────────────────

    def test_strategy_default_from_the_settings(self):
        with self.server_actions_allowed():
            wizard = self.Wizard.browse(self.Wizard._action_open()["res_id"])
            self.assertEqual(wizard.strategy, "rebase")
            self.assertEqual(wizard.mode, "manifeste")
            settings = self.env["res.config.settings"].create(
                {"erplibre_pull_strategy": "merge"}
            )
            settings.execute()
            self.assertEqual(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("erplibre_info.pull_strategy"),
                "merge",
            )
            wizard = self.Wizard.browse(self.Wizard._action_open()["res_id"])
            self.assertEqual(wizard.strategy, "merge")
            # The wizard changes the strategy of one pull only.
            run = self._pull_dry_run(strategy="ff")
        self.assertEqual(run.pull_strategy, "ff")
        self.assertIn("ff", self._pull_args("--dry-run")[0])
        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("erplibre_info.pull_strategy"),
            "merge",
        )

    # ── dry run ─────────────────────────────────────────────────────────

    def test_dry_run_runs_in_background(self):
        with self.server_actions_allowed():
            wizard = self.Wizard.browse(self.Wizard._action_open()["res_id"])
            run = self.Run.browse(wizard.action_start()["res_id"])
            self.assertEqual(run.state, "queued")
            self.assertEqual(self.fake.calls, [])
            self.assertTrue(self.cron.active)
            self.Run._cron_process()
        self.assertEqual(run.state, "done", run.log)
        self.assertEqual(
            self.fake.scripts(),
            [
                (
                    "repo_pull.py",
                    [
                        "--dry-run",
                        "--mode",
                        "manifeste",
                        "--strategy",
                        "rebase",
                        "--json",
                    ],
                )
            ],
        )
        self.assertEqual(run.odoo_version, SERIES)
        self.assertEqual(run.plan_paths, f".\n{REPO}")
        self.assertEqual(run.shallow_paths, REPO_SHALLOW)
        self.assertEqual(run.clone_paths, REPO_NEW)
        self.assertEqual(run.left_paths, REPO_BUSY)
        self.assertEqual(run.plan_count, 2)
        self.assertTrue(run.can_apply)
        html = str(run.report_html)
        # A subject is text, never markup.
        self.assertIn("&lt;b&gt;incoming&lt;/b&gt;", html)
        self.assertNotIn("<b>incoming</b>", html)
        self.assertIn("root update", html)
        self.assertIn("example_avant_pull_", html)
        self.assertIn(REPO_NEW, html)
        self.assertIn("poetry install --no-root", html)
        self.assertIn("Only the first", html)

    def test_dry_run_with_nothing_to_pull_cannot_apply(self):
        data = copy.deepcopy(PULL_DRY_RUN)
        data.update(
            plan=[],
            plan_superficiel=[],
            plan_nouveaux=[],
            attendus=[],
            attendus_superficiel=[],
        )
        self.fake.answers[("repo_pull.py", "--dry-run")] = (0, data)
        with self.server_actions_allowed():
            run = self._pull_dry_run()
            self.assertEqual(run.state, "done", run.log)
            self.assertFalse(run.can_apply)
            with self.assertRaises(UserError):
                run.action_pull_apply()

    def test_dry_run_busy(self):
        self.fake.answers[("repo_pull.py", "--dry-run")] = (
            5,
            {"command": "dry-run", "error": "busy"},
        )
        with self.server_actions_allowed():
            run = self._pull_dry_run()
        self.assertEqual(run.state, "failed")
        self.assertIn("Another pull is running", run.log)

    def test_only_the_last_pull_dry_run_applies(self):
        with self.server_actions_allowed():
            first = self._pull_dry_run()
            self.assertTrue(first.can_apply)
            # A newer fetch + rebase dry run is another type: no effect.
            self.Run.action_start_dry_run()
            self.Run._cron_process()
            first.invalidate_recordset()
            self.assertTrue(first.can_apply)
            second = self._pull_dry_run()
        first.invalidate_recordset()
        self.assertFalse(first.can_apply)
        self.assertTrue(first.apply_note)
        self.assertTrue(second.can_apply)
        with self.server_actions_allowed(), self.assertRaises(UserError):
            first.action_pull_apply()

    # ── apply ───────────────────────────────────────────────────────────

    def test_apply_requires_double_validation(self):
        with self.server_actions_allowed():
            dry_run = self._pull_dry_run()
            action = dry_run.action_pull_apply()
            self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")
            with self.assertRaises(UserError):
                self._confirm("pull_apply", run=dry_run, typed="x").action_confirm()
            with self.assertRaises(UserError):
                self._confirm(
                    "pull_apply", run=dry_run, understood=False
                ).action_confirm()
            self.assertFalse(self.Run.search_count([("run_type", "=", "pull_apply")]))
            action = self._confirm("pull_apply", run=dry_run).action_confirm()
            apply_run = self.Run.browse(action["res_id"])
            self.assertEqual(apply_run.state, "queued")
            self.assertFalse(dry_run.can_apply)
            self.fake.calls.clear()
            with patch.object(type(self.Run), "_pull_stamp", lambda self_: PULL_STAMP):
                self.Run._cron_process()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertEqual(
            self._pull_args("--apply"),
            [
                [
                    "--apply",
                    "--mode",
                    "manifeste",
                    "--strategy",
                    "rebase",
                    "--confirm",
                    SERIES,
                    "--pass",
                    PULL_STAMP,
                    "--budget",
                    str(runner.DEFAULT_LONG_TIMEOUT - 900),
                    "--json",
                    "--expect",
                    f".={'d' * 40}:{'0' * 40}",
                    "--expect",
                    f"{REPO}={'c' * 40}:{'1' * 40}",
                ]
            ],
        )
        self.assertFalse(apply_run.approve_deepen)
        self.assertFalse(apply_run.approve_clone)

    def test_apply_with_deepen_and_clone(self):
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply(approve_deepen=True, approve_clone=True)
        self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertTrue(apply_run.approve_deepen)
        self.assertTrue(apply_run.approve_clone)
        args = self._pull_args("--apply")[0]
        self.assertEqual(
            args[args.index("--json") + 1 :],
            [
                "--expect",
                f".={'d' * 40}:{'0' * 40}",
                "--expect",
                f"{REPO}={'c' * 40}:{'1' * 40}",
                "--expect",
                f"{REPO_SHALLOW}={'e' * 40}:{'f' * 40}",
                "--approve-deepen",
                "--approve-clone",
                "--expect-clone",
                REPO_NEW,
            ],
        )

    def test_permissions_need_something_to_allow(self):
        """A box ticked on a dry run without shallow clone or new
        repository allows nothing."""
        data = copy.deepcopy(PULL_DRY_RUN)
        data.update(plan_superficiel=[], plan_nouveaux=[], attendus_superficiel=[])
        self.fake.answers[("repo_pull.py", "--dry-run")] = (0, data)
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply(approve_deepen=True, approve_clone=True)
        self.assertFalse(apply_run.approve_deepen)
        self.assertFalse(apply_run.approve_clone)
        args = self._pull_args("--apply")[0]
        self.assertNotIn("--approve-deepen", args)
        self.assertNotIn("--approve-clone", args)

    def test_apply_plan_changed(self):
        self.fake.answers[("repo_pull.py", "--apply")] = (
            4,
            {
                "command": "apply",
                "error": "plan_changed",
                "derives": [
                    {
                        "chemin": REPO,
                        "cle": "cible_sha",
                        "attendu": "c" * 40,
                        "trouve": "9" * 40,
                    }
                ],
                "resultats": [],
            },
        )
        with self.server_actions_allowed():
            dry_run, apply_run = self._pull_apply()
        self.assertEqual(apply_run.state, "failed")
        self.assertEqual(apply_run.exit_code, 4)
        self.assertIn("out of date", apply_run.log)
        self.assertFalse(apply_run.snapshot_id)
        self.assertFalse(apply_run.backup_ids)
        self.assertIn("9" * 12, str(apply_run.report_html))
        dry_run.invalidate_recordset()
        self.assertFalse(dry_run.can_apply)
        self.assertTrue(dry_run.apply_note)

    def test_apply_busy(self):
        self.fake.answers[("repo_pull.py", "--apply")] = (
            5,
            {"command": "apply", "error": "busy"},
        )
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
        self.assertEqual(apply_run.state, "failed")
        self.assertIn("Another pull is running", apply_run.log)

    def test_apply_done(self):
        module = self.env.ref("base.module_erplibre_info")
        self.fake.snapshot["repos"][0]["modules"][0]["version"] = module.latest_version
        self.fake.changed_modules = ["erplibre_info"]
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertEqual(apply_run.pass_dir, PULL_DIR)
        self.assertEqual(apply_run.snapshot_id.trigger, "upgrade")
        self.assertEqual(apply_run.snapshot_id.run_id, apply_run)
        self.assertEqual(apply_run.code_changed_module_ids, module)
        self.assertEqual(apply_run.upgrade_module_ids, module)
        self.assertTrue(apply_run.deps_to_install)
        self.assertFalse(apply_run.pull_blocked)
        self.assertEqual(
            [s for s, a in self.fake.scripts() if a[0] == "between"],
            ["repo_state.py", "repo_state.py"],
        )
        self.assertEqual(sorted(apply_run.backup_ids.mapped("path")), [".", REPO])
        backup = apply_run.backup_ids.filtered(lambda b: b.path == REPO)
        self.assertEqual(backup.branch_name, BACKUP_REPO)
        self.assertEqual(backup.sha, "1" * 40)
        self.assertTrue(backup.detached)
        self.assertEqual(backup.state, "kept")
        root = apply_run.backup_ids.filtered(lambda b: b.path == ".")
        self.assertEqual(root.original_branch, "example")
        html = str(apply_run.report_html)
        self.assertIn("stash apply", html)
        self.assertIn(BACKUP_REPO, html)
        # Restart without installing stays possible.
        with self.server_actions_allowed():
            action = apply_run.action_restart()
        self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")

    def test_nothing_to_pull_takes_no_snapshot(self):
        data = copy.deepcopy(PULL_APPLY)
        data.update(dossier=None, horodatage=None, resultats=[], manifeste=None)
        data["dependances"]["a_installer"] = False
        self.fake.answers[("repo_pull.py", "--apply")] = (0, data)
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertFalse(apply_run.snapshot_id)
        self.assertIn("Nothing to pull", apply_run.log)

    def test_restore_failed_blocks_the_restart(self):
        data = copy.deepcopy(PULL_APPLY)
        data["resultats"][1]["etat"] = "restauration_echouee"
        self.fake.answers[("repo_pull.py", "--apply")] = (0, data)
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            self.assertEqual(apply_run.state, "done", apply_run.log)
            self.assertTrue(apply_run.pull_blocked)
            self.assertIn("mid-operation", str(apply_run.report_html))
            with self.assertRaises(UserError):
                apply_run.action_restart()
            with self.assertRaises(UserError):
                apply_run.action_restart_upgrade()
            with self.assertRaises(UserError):
                apply_run.action_deps_install()

    # ── dependencies ────────────────────────────────────────────────────

    def test_deps_install(self):
        module = self.env.ref("base.module_erplibre_info")
        self.fake.snapshot["repos"][0]["modules"][0]["version"] = module.latest_version
        self.fake.changed_modules = ["erplibre_info"]
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            action = apply_run.action_deps_install()
            self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")
            action = self._confirm("deps_install", run=apply_run).action_confirm()
            deps_run = self.Run.browse(action["res_id"])
            self.assertEqual(deps_run.state, "queued")
            self.fake.calls.clear()
            self.Run._cron_process()
        self.assertEqual(deps_run.state, "done", deps_run.log)
        self.assertEqual(
            self.fake.scripts(),
            [
                (
                    "repo_pull.py",
                    [
                        "--install-deps",
                        "--confirm",
                        SERIES,
                        "--pass",
                        PULL_STAMP,
                        "--json",
                    ],
                )
            ],
        )
        self.assertEqual(deps_run.parent_id, apply_run)
        self.assertEqual(deps_run.upgrade_module_ids, module)
        self.assertIn("Installing dependencies", str(deps_run.report_html))
        with self.server_actions_allowed():
            action = deps_run.action_restart_upgrade()
        self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")

    def test_deps_install_failure(self):
        self.fake.answers[("repo_pull.py", "--install-deps")] = (
            6,
            {
                "command": "install-deps",
                "code": 1,
                "sortie": "SolverProblemError",
                "error": "poetry install failed",
            },
        )
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            self._confirm("deps_install", run=apply_run).action_confirm()
            self.Run._cron_process()
        deps_run = self.Run.search([("run_type", "=", "deps_install")])
        self.assertEqual(deps_run.state, "failed")
        self.assertEqual(deps_run.exit_code, 6)
        self.assertIn("SolverProblemError", deps_run.log)

    def test_deps_install_needs_changed_deps(self):
        data = copy.deepcopy(PULL_APPLY)
        data["dependances"]["a_installer"] = False
        self.fake.answers[("repo_pull.py", "--apply")] = (0, data)
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            self.assertFalse(apply_run.deps_to_install)
            with self.assertRaises(UserError):
                apply_run.action_deps_install()
            with self.assertRaises(UserError):
                apply_run._launch_deps_install()

    # ── backups ─────────────────────────────────────────────────────────

    def test_restore_backup(self):
        module = self.env.ref("base.module_erplibre_info")
        self.fake.snapshot["repos"][0]["modules"][0]["version"] = module.latest_version
        self.fake.changed_modules = ["erplibre_info"]
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            backup = apply_run.backup_ids.filtered(lambda b: b.path == REPO)
            action = backup.action_restore()
            self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")
            with self.assertRaises(UserError):
                self._confirm(
                    "pull_restore", run=apply_run, backup=backup, typed="x"
                ).action_confirm()
            action = self._confirm(
                "pull_restore", run=apply_run, backup=backup
            ).action_confirm()
            restore_run = self.Run.browse(action["res_id"])
            self.fake.calls.clear()
            self.Run._cron_process()
        self.assertEqual(restore_run.state, "done", restore_run.log)
        self.assertEqual(
            self._pull_args("--restore-backup"),
            [
                [
                    "--restore-backup",
                    f"{REPO}={BACKUP_REPO}",
                    "--confirm",
                    SERIES,
                    "--json",
                ]
            ],
        )
        self.assertEqual(restore_run.backup_id, backup)
        self.assertEqual(backup.state, "restored")
        self.assertEqual(restore_run.upgrade_module_ids, module)
        with self.server_actions_allowed(), self.assertRaises(UserError):
            backup._launch_restore()

    def test_restore_refused(self):
        self.fake.answers[("repo_pull.py", "--restore-backup")] = (
            0,
            {
                "command": "restore-backup",
                "resultats": [
                    {
                        "chemin": REPO,
                        "etat": "refuse_sale",
                        "depart": "c" * 40,
                        "arrivee": None,
                        "sauvegarde": BACKUP_REPO,
                        "manifeste_restaure": False,
                    }
                ],
            },
        )
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            backup = apply_run.backup_ids.filtered(lambda b: b.path == REPO)
            self._confirm("pull_restore", run=apply_run, backup=backup).action_confirm()
            self.Run._cron_process()
        restore_run = self.Run.search([("run_type", "=", "pull_restore")])
        self.assertEqual(restore_run.state, "failed")
        self.assertIn("modified files", restore_run.log)
        self.assertEqual(backup.state, "kept")
        self.assertFalse(restore_run.snapshot_id)

    def test_delete_backup(self):
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            backup = apply_run.backup_ids.filtered(lambda b: b.path == REPO)
            self.fake.calls.clear()
            action = backup.action_delete()
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(
            self._pull_args("--delete-backup"),
            [
                [
                    "--delete-backup",
                    f"{REPO}={BACKUP_REPO}",
                    "--confirm",
                    SERIES,
                    "--json",
                ]
            ],
        )
        self.assertEqual(backup.state, "deleted")
        self.assertTrue(backup.log)
        with self.server_actions_allowed(), self.assertRaises(UserError):
            backup.action_delete()

    def test_delete_missing_backup(self):
        self.fake.answers[("repo_pull.py", "--delete-backup")] = (
            3,
            {
                "command": "delete-backup",
                "resultats": [
                    {
                        "chemin": REPO,
                        "sauvegarde": BACKUP_REPO,
                        "etat": "sauvegarde_absente",
                    }
                ],
            },
        )
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            backup = apply_run.backup_ids.filtered(lambda b: b.path == REPO)
            backup.action_delete()
        self.assertEqual(backup.state, "missing")

    def test_delete_a_restored_backup(self):
        """A restore keeps the branch on disk: its record still deletes
        it."""
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            backup = apply_run.backup_ids.filtered(lambda b: b.path == REPO)
            self._confirm("pull_restore", run=apply_run, backup=backup).action_confirm()
            self.Run._cron_process()
            self.assertEqual(backup.state, "restored")
            backup.action_delete()
        self.assertEqual(backup.state, "deleted")

    def test_restore_refused_when_head_moved(self):
        self.fake.answers[("repo_pull.py", "--restore-backup")] = (
            0,
            {
                "command": "restore-backup",
                "resultats": [
                    {
                        "chemin": REPO,
                        "etat": "head_deplacee",
                        "depart": "9" * 40,
                        "arrivee": None,
                        "sauvegarde": BACKUP_REPO,
                        "manifeste_restaure": False,
                    }
                ],
            },
        )
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
            backup = apply_run.backup_ids.filtered(lambda b: b.path == REPO)
            self._confirm("pull_restore", run=apply_run, backup=backup).action_confirm()
            self.Run._cron_process()
        restore_run = self.Run.search([("run_type", "=", "pull_restore")])
        self.assertEqual(restore_run.state, "failed")
        self.assertIn("HEAD moved since the pull", restore_run.log)
        self.assertEqual(backup.state, "kept")

    # ── budget and timeout ──────────────────────────────────────────────

    def test_budget_below_the_long_timeout(self):
        param = self.env["ir.config_parameter"].sudo()
        self.assertEqual(self.Run._pull_budget(), 3600 - 900)
        param.set_param(runner.PARAM_LONG_TIMEOUT, "600")
        self.assertEqual(self.Run._pull_budget(), 450)

    def test_budget_exhausted_is_reported(self):
        data = copy.deepcopy(PULL_APPLY)
        data["budget_epuise"] = True
        data["resultats"][1].update(etat="saute_delai", arrivee=None, sauvegarde=None)
        self.fake.answers[("repo_pull.py", "--apply")] = (0, data)
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        html = str(apply_run.report_html)
        self.assertIn("time budget of the pass ran out", html)
        self.assertIn("not started: time budget exhausted", html)

    def test_apply_timeout_reads_the_backups_back(self):
        self.fake.answers[("repo_pull.py", "--apply")] = subprocess.TimeoutExpired(
            ["repo_pull.py"], 1
        )
        with self.server_actions_allowed():
            _dry, apply_run = self._pull_apply()
        self.assertEqual(apply_run.state, "failed")
        self.assertIn("did not finish", apply_run.log)
        self.assertIn("read back: 1", apply_run.log)
        self.assertTrue(apply_run.pull_blocked)
        self.assertEqual(apply_run.backup_ids.branch_name, BACKUP_REPO)
        self.assertEqual(apply_run.backup_ids.sha, "1" * 40)
        self.assertEqual(apply_run.backup_ids.state, "kept")
        # The restart waits for a new dry run.
        with self.server_actions_allowed():
            with self.assertRaises(UserError):
                self.env["res.config.settings"].create({}).action_erplibre_restart()
            self._pull_dry_run()
            action = (
                self.env["res.config.settings"].create({}).action_erplibre_restart()
            )
        self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")

    def test_blocked_pull_blocks_every_restart(self):
        data = copy.deepcopy(PULL_APPLY)
        data["resultats"][1]["etat"] = "restauration_echouee"
        self.fake.answers[("repo_pull.py", "--apply")] = (0, data)
        with self.server_actions_allowed(), patch("odoo.service.server.restart"):
            self.Run.action_start_dry_run()
            self.Run._cron_process()
            older = self.Run.search([("run_type", "=", "dry_run")])
            _dry, apply_run = self._pull_apply()
            self.assertTrue(apply_run.pull_blocked)
            with self.assertRaises(UserError):
                self.env["res.config.settings"].create({}).action_erplibre_restart()
            with self.assertRaises(UserError):
                older.action_restart()
            with self.assertRaises(UserError):
                self._confirm("restart").action_confirm()
            with self.assertRaises(UserError):
                self.Run._request_restart()

    # ── creation outside the buttons ────────────────────────────────────

    def test_git_runs_are_created_by_their_buttons_only(self):
        """A Settings administrator calling the ORM, as RPC does, creates
        no git run and changes none."""
        with self.server_actions_allowed():
            dry_run = self._pull_dry_run()
        admin = new_test_user(
            self.env, login="erplibre_info_rpc", groups="base.group_system"
        )
        Run = self.Run.with_user(admin)
        for run_type in ("dry_run", "apply", "pull_dry_run", "pull_apply"):
            with self.assertRaises(AccessError):
                Run.create({"run_type": run_type, "parent_id": dry_run.id})
        self.assertTrue(Run.create({"run_type": "snapshot"}))
        with self.assertRaises(AccessError):
            Run.browse(dry_run.id).write({"approve_clone": True})
        with self.assertRaises(AccessError):
            Run.browse(dry_run.id).write({"state": "queued"})
        Run.browse(dry_run.id).write({"state": "failed"})

    def test_background_step_checks_the_requester(self):
        user = new_test_user(
            self.env, login="erplibre_info_not_admin", groups="base.group_user"
        )
        run = self.Run._create_launched(
            {"run_type": "pull_dry_run", "user_id": user.id}
        )
        with self.server_actions_allowed():
            self.Run._cron_process()
        self.assertEqual(run.state, "failed")
        self.assertIn("Settings administrators", run.log)
        self.assertFalse(self._pull_args("--dry-run"))

    # ── rendering ───────────────────────────────────────────────────────

    def test_dry_run_switch_and_overwritten_files(self):
        data = copy.deepcopy(PULL_DRY_RUN)
        data["depots"][1].update(
            verdict="bascule",
            nos=7,
            locaux=0,
            ecrases=["settings.conf"],
        )
        self.fake.answers[("repo_pull.py", "--dry-run")] = (0, data)
        with self.server_actions_allowed():
            run = self._pull_dry_run()
        html = str(run.report_html)
        self.assertIn("switch to the manifest target", html)
        self.assertIn("settings.conf", html)
        self.assertIn("repo sync restricted to their paths", html)

    # ── one repository ──────────────────────────────────────────────────

    def test_repo_button(self):
        line = self._repo_line(branch=f"{SERIES}_dev")
        with self.server_actions_allowed():
            self.assertTrue(line.server_actions_allowed)
            action = line.action_pull()
            wizard = self.Wizard.browse(action["res_id"])
            self.assertEqual(wizard.path, REPO)
            self.assertEqual(wizard.mode, "branche")
            run = self.Run.browse(wizard.action_start()["res_id"])
            self.Run._cron_process()
        self.assertEqual(run.pull_path, REPO)
        self.assertEqual(
            self._pull_args("--dry-run")[0],
            [
                "--dry-run",
                "--mode",
                "branche",
                "--strategy",
                "rebase",
                "--path",
                REPO,
                "--json",
            ],
        )
        with self.server_actions_allowed():
            self._confirm("pull_apply", run=run).action_confirm()
            self.fake.calls.clear()
            self.Run._cron_process()
        args = self._pull_args("--apply")[0]
        self.assertEqual(
            args[:7],
            ["--apply", "--mode", "branche", "--strategy", "rebase", "--path", REPO],
        )

    def test_repo_button_detached_uses_the_manifest(self):
        line = self._repo_line()
        with self.server_actions_allowed():
            wizard = self.Wizard.browse(line.action_pull()["res_id"])
        self.assertEqual(wizard.mode, "manifeste")


@tagged("post_install", "-at_install")
class TestPullRestart(ErplibreInfoCase):
    """The restart after a pull: the modules marked to upgrade."""

    def setUp(self):
        super().setUp()
        self.env.cr.postcommit.clear()

    def test_restart_upgrade_after_a_pull(self):
        module = self.env.ref("base.module_erplibre_info")
        self.fake.snapshot["repos"][0]["modules"][0]["version"] = module.latest_version
        self.fake.changed_modules = ["erplibre_info"]
        with self.server_actions_allowed(), patch("odoo.service.server.restart"):
            wizard = self.env["erplibre.code.pull.wizard"]
            run = self.Run.browse(
                wizard.browse(wizard._action_open()["res_id"]).action_start()["res_id"]
            )
            self.Run._cron_process()
            confirm = self.env["erplibre.code.confirm.wizard"]
            res = confirm._action_open("pull_apply", run=run)
            confirm.browse(res["res_id"]).write(
                {"typed_database_name": self.env.cr.dbname, "understood": True}
            )
            apply_run = self.Run.browse(
                confirm.browse(res["res_id"]).action_confirm()["res_id"]
            )
            self.Run._cron_process()
            action = apply_run.action_restart_upgrade()
            wizard = confirm.browse(action["res_id"])
            wizard.write(
                {"typed_database_name": self.env.cr.dbname, "understood": True}
            )
            wizard.action_confirm()
        self.assertEqual(module.state, "to upgrade")


@tagged("post_install", "-at_install")
class TestRunnerProcessGroup(TransactionCase):
    """``runner._run_process`` itself, on a real process."""

    def test_timeout_kills_the_process_group(self):
        directory = tempfile.mkdtemp(prefix="erplibre_info_runner_")
        self.addCleanup(shutil.rmtree, directory, True)
        pid_file = os.path.join(directory, "child.pid")
        with self.assertRaises(subprocess.TimeoutExpired):
            runner._run_process(
                ["sh", "-c", f"sleep 30 & echo $! > {pid_file}; wait"],
                cwd=directory,
                env=dict(os.environ),
                timeout=1,
            )
        with open(pid_file) as fh:
            child = int(fh.read())
        for _attempt in range(100):
            try:
                with open(f"/proc/{child}/stat") as fh:
                    state = fh.read().split(")")[-1].split()[0]
            except (FileNotFoundError, ProcessLookupError):
                break
            if state == "Z":
                break
            time.sleep(0.05)
        else:
            self.fail("the child process outlives the timeout")

    def test_output_is_captured(self):
        done = runner._run_process(
            ["sh", "-c", "echo out; echo err >&2; exit 3"],
            cwd=os.getcwd(),
            env=dict(os.environ),
            timeout=10,
        )
        self.assertEqual(
            (done.returncode, done.stdout, done.stderr), (3, "out\n", "err\n")
        )
