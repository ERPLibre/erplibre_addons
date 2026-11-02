# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import copy
import json
import os
import subprocess
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.erplibre_info import runner
from odoo.addons.erplibre_info.tests.common import (
    PULL_STAMP,
    REPO,
    REPO_CORE,
    REPO_OTHER,
    SERIES,
)

from .common import (
    REVERT_APPLY,
    REVERT_DRY_RUN,
    STASH_APPLIED,
    STASH_SHA,
    ErplibreInfoGitFetchCase,
)

PULL = "repo_pull.py"


@tagged("post_install", "-at_install")
class TestRevert(ErplibreInfoGitFetchCase):
    def setUp(self):
        super().setUp()
        self.env.cr.postcommit.clear()
        self.Wizard = self.env["erplibre.code.revert.wizard"]
        self.Stash = self.env["erplibre.code.stash"]
        self.fake.answers[(PULL, "--dry-run")] = (
            0,
            copy.deepcopy(REVERT_DRY_RUN),
        )
        self.fake.answers[(PULL, "--apply")] = (0, copy.deepcopy(REVERT_APPLY))
        self.fake.answers[(PULL, "--apply-stash")] = (0, dict(STASH_APPLIED))
        # The targets file of each script call, read while it exists.
        self.targets_read = []
        fake = self.fake

        def run_process(cmd, **kwargs):
            if "--targets" in cmd:
                path = cmd[cmd.index("--targets") + 1]
                with open(path) as fh:
                    self.targets_read.append((path, json.load(fh)))
            return fake(cmd, **kwargs)

        patcher = patch.object(runner, "_run_process", run_process)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ── helpers ─────────────────────────────────────────────────────────

    def _snapshot(self):
        return self.Snapshot._capture("manual", force=True)

    def _confirm(self, action, typed=None, **kw):
        vals = {k: kw.pop(k) for k in ("approve_modules",) if k in kw}
        res = self.env["erplibre.code.confirm.wizard"]._action_open(action, **kw)
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

    def _dry_run(self, snapshot=None, include_root=True):
        """A dry run of the return started from the snapshot button and
        executed by the cron; the server actions must be allowed by the
        caller."""
        snapshot = snapshot or self._snapshot()
        wizard = self.Wizard.browse(snapshot.action_revert()["res_id"])
        wizard.include_root = include_root
        run = self.Run.browse(wizard.action_start()["res_id"])
        self.Run._cron_process()
        return run

    def _apply(self, **vals):
        dry_run = self._dry_run()
        action = self._confirm("snapshot_revert", run=dry_run, **vals).action_confirm()
        apply_run = self.Run.browse(action["res_id"])
        self.fake.calls.clear()
        with patch.object(type(self.Run), "_pull_stamp", lambda self_: PULL_STAMP):
            self.Run._cron_process()
        return dry_run, apply_run

    def _pull_args(self, flag):
        return [a for s, a in self.fake.scripts() if s == PULL and a[0] == flag]

    # ── guards ──────────────────────────────────────────────────────────

    def test_guards(self):
        """Every entry of the return refuses without the three conditions,
        or on a server started without --dev."""
        snapshot = self._snapshot()
        with self.server_actions_allowed():
            dry_run, apply_run = self._apply()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        stash = apply_run.stash_ids
        self.assertEqual(len(stash), 1)
        user = new_test_user(
            self.env, login="erplibre_info_reverter", groups="base.group_user"
        )
        entries = [
            lambda env: env["erplibre.code.snapshot"]
            .browse(snapshot.id)
            .action_revert(),
            lambda env: env["erplibre.code.revert.wizard"]._action_open(
                env["erplibre.code.snapshot"].browse(snapshot.id)
            ),
            lambda env: env["erplibre.code.run"]
            .browse(dry_run.id)
            .action_snapshot_revert(),
            lambda env: env["erplibre.code.stash"].browse(stash.id).action_reapply(),
        ]
        for entry in entries:
            with self.server_actions_allowed(flag=False), self.assertRaises(UserError):
                entry(self.env)
            with self.server_actions_allowed(debug=False), self.assertRaises(UserError):
                entry(self.env)
            with self.server_actions_allowed(dev=False), self.assertRaisesRegex(
                UserError, "--dev"
            ):
                entry(self.env)
            with self.server_actions_allowed(), self.assertRaises(AccessError):
                entry(self.env(user=user))
        with self.server_actions_allowed():
            wizard = self.Wizard.browse(snapshot.action_revert()["res_id"])
        self.fake.calls.clear()
        with self.server_actions_allowed(dev=False), self.assertRaises(UserError):
            wizard.action_start()
        with self.server_actions_allowed(dev=False), self.assertRaises(UserError):
            self._confirm("stash_apply", run=apply_run, stash=stash).action_confirm()
        self.assertFalse(self._pull_args("--apply-stash"))
        self.assertEqual(stash.state, "kept")

    def test_background_step_rereads_dev(self):
        """A queued dry run stops on a server restarted without --dev."""
        with self.server_actions_allowed():
            snapshot = self._snapshot()
            wizard = self.Wizard.browse(snapshot.action_revert()["res_id"])
            run = self.Run.browse(wizard.action_start()["res_id"])
        with self.server_actions_allowed(dev=False):
            self.Run._cron_process()
        self.assertEqual(run.state, "failed")
        self.assertIn("--dev", run.log)
        self.assertFalse(self._pull_args("--dry-run"))

    def test_runs_only_from_their_button(self):
        with self.assertRaises(AccessError):
            self.Run.with_user(self.env.ref("base.user_admin")).create(
                {"run_type": "snapshot_revert_dry_run"}
            )

    # ── targets ─────────────────────────────────────────────────────────

    def test_targets_file(self):
        """The targets name every repository of the snapshot with a commit,
        and the root last in the engine's order, or null without the
        option. The file exists for the call only."""
        self.fake.snapshot["repos"][2]["state"] = "absent"
        snapshot = self._snapshot()
        with self.server_actions_allowed():
            run = self._dry_run(snapshot)
        self.assertEqual(run.state, "done", run.log)
        self.assertTrue(run.revert_root)
        targets = json.loads(run.revert_targets)
        self.assertEqual(targets["racine"], {"head": "a" * 40, "branch": "example"})
        self.assertEqual(
            targets["depots"],
            {
                REPO: {"head": "1" * 40, "branch": None, "remote": "Example"},
                REPO_CORE: {
                    "head": "2" * 40,
                    "branch": None,
                    "remote": "Example",
                },
            },
        )
        args = self._pull_args("--dry-run")[0]
        self.assertEqual(args[:3], ["--dry-run", "--mode", "instantane"])
        path, read = self.targets_read[-1]
        self.assertEqual(args[args.index("--targets") + 1], path)
        self.assertEqual(read, targets)
        self.assertFalse(os.path.exists(path))

        with self.server_actions_allowed():
            run = self._dry_run(snapshot, include_root=False)
        self.assertFalse(run.revert_root)
        self.assertIsNone(json.loads(run.revert_targets)["racine"])
        self.assertIsNone(self.targets_read[-1][1]["racine"])

    # ── dry run ─────────────────────────────────────────────────────────

    def test_dry_run_report(self):
        with self.server_actions_allowed():
            run = self._dry_run()
        self.assertEqual(run.state, "done", run.log)
        self.assertEqual(run.plan_paths, f".\n{REPO}")
        self.assertEqual(run.left_paths, REPO_OTHER)
        self.assertEqual(run.odoo_version, SERIES)
        self.assertTrue(run.can_apply)
        html = str(run.report_html)
        for text in (
            "back to an older commit",
            "move off the current history",
            "already on the snapshot",
            "commit not found: skipped",
            "commit not found on Example",
            "Commits left behind",
            "Local commits only in the backup",
            "yes (stash kept)",
            f"{SERIES}_avant_retour_",
            "odooX/outside",
            "only the backup branch keeps them",
        ):
            self.assertIn(text, html)
        self.assertNotIn("alert-danger", html)
        # The dry run only reads.
        self.assertFalse(self._pull_args("--apply"))

    def test_dry_run_without_plan_cannot_apply(self):
        data = copy.deepcopy(REVERT_DRY_RUN)
        data.update(plan=[], attendus=[])
        for repo in data["depots"]:
            repo["applicable"] = False
        self.fake.answers[(PULL, "--dry-run")] = (0, data)
        with self.server_actions_allowed():
            run = self._dry_run()
            self.assertFalse(run.can_apply)
            with self.assertRaises(UserError):
                run.action_snapshot_revert()

    # ── newer modules ───────────────────────────────────────────────────

    def test_newer_modules_need_their_own_box(self):
        """A module installed with a newer version than the snapshot is
        listed in red, and the apply needs one more box."""
        snapshot = self._snapshot()
        line = snapshot.module_ids.filtered(lambda m: m.name == "erplibre_info")
        self.assertTrue(line)
        line.installed_version = "1.0"
        self.assertEqual(
            [m["name"] for m in snapshot._revert_newer_modules()],
            ["erplibre_info"],
        )
        with self.server_actions_allowed():
            wizard = self.Wizard.browse(snapshot.action_revert()["res_id"])
            self.assertIn("erplibre_info", str(wizard.newer_modules_html))
            dry_run = self._dry_run(snapshot)
            self.assertIn("alert-danger", str(dry_run.report_html))
            self.assertIn("erplibre_info", str(dry_run.report_html))
            confirm = self._confirm("snapshot_revert", run=dry_run)
            self.assertTrue(confirm.has_newer_modules)
            with self.assertRaisesRegex(UserError, "newer version"):
                confirm.action_confirm()
            self.assertFalse(self.Run.search([("run_type", "=", "snapshot_revert")]))
            confirm.approve_modules = True
            apply_run = self.Run.browse(confirm.action_confirm()["res_id"])
        self.assertTrue(apply_run.approve_modules)

    def test_no_newer_module_no_box(self):
        snapshot = self._snapshot()
        self.assertEqual(snapshot._revert_newer_modules(), [])
        with self.server_actions_allowed():
            dry_run = self._dry_run(snapshot)
            confirm = self._confirm("snapshot_revert", run=dry_run)
            self.assertFalse(confirm.has_newer_modules)
            apply_run = self.Run.browse(confirm.action_confirm()["res_id"])
        self.assertFalse(apply_run.approve_modules)

    def test_module_missing_from_snapshot_is_newer(self):
        snapshot = self._snapshot()
        snapshot.module_ids.filtered(lambda m: m.name == "base").unlink()
        newer = snapshot._revert_newer_modules()
        self.assertEqual([m["name"] for m in newer], ["base"])
        self.assertFalse(newer[0]["snapshot_version"])

    # ── apply ───────────────────────────────────────────────────────────

    def test_apply(self):
        with self.server_actions_allowed():
            dry_run, apply_run = self._apply()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertEqual(apply_run.parent_id, dry_run)
        self.assertEqual(apply_run.revert_targets, dry_run.revert_targets)
        args = self._pull_args("--apply")[0]
        self.assertEqual(args[:4], ["--apply", "--mode", "instantane", "--targets"])
        self.assertEqual(args[args.index("--confirm") + 1], SERIES)
        self.assertEqual(args[args.index("--pass") + 1], PULL_STAMP)
        self.assertIn("--budget", args)
        expected = [args[i + 1] for i, a in enumerate(args) if a == "--expect"]
        self.assertEqual(expected, REVERT_DRY_RUN["attendus"])
        self.assertEqual(self.targets_read[-1][1], json.loads(dry_run.revert_targets))
        # The backups of HEAD, the kept stash, the new snapshot.
        self.assertEqual(
            sorted(apply_run.backup_ids.mapped("branch_name")),
            sorted(
                [
                    f"{SERIES}_avant_retour_{PULL_STAMP}",
                    f"example_avant_retour_{PULL_STAMP}",
                ]
            ),
        )
        stash = apply_run.stash_ids
        self.assertEqual(
            (stash.path, stash.sha, stash.state, stash.message, stash.command),
            (
                REPO,
                STASH_SHA,
                "kept",
                f"repo_pull retour {PULL_STAMP}",
                f"git -C {REPO} stash apply {STASH_SHA}",
            ),
        )
        self.assertEqual(apply_run.snapshot_id.trigger, "upgrade")
        self.assertEqual(apply_run.snapshot_id.run_id, apply_run)
        self.assertTrue(apply_run.deps_to_install)
        self.assertFalse(dry_run.can_apply)
        html = str(apply_run.report_html)
        for text in (
            "returned to the snapshot",
            "commit not found: skipped",
            f"git -C {REPO} stash apply",
            "Regenerated manifest",
            "Install the Python dependencies",
        ):
            self.assertIn(text, html)
        # The dependencies are proposed as after a pull.
        with self.server_actions_allowed():
            action = apply_run.action_deps_install()
            self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")
            deps = self.Run.browse(
                self._confirm("deps_install", run=apply_run).action_confirm()["res_id"]
            )
        self.assertEqual(deps.parent_id, apply_run)
        self.assertEqual(deps.run_type, "deps_install")

    def test_apply_needs_both_validations(self):
        with self.server_actions_allowed():
            dry_run = self._dry_run()
            self.assertEqual(
                dry_run.action_snapshot_revert()["res_model"],
                "erplibre.code.confirm.wizard",
            )
            self.assertFalse(self.Run.search([("run_type", "=", "snapshot_revert")]))
            with self.assertRaises(UserError):
                self._confirm(
                    "snapshot_revert", run=dry_run, typed="other"
                ).action_confirm()
        self.assertFalse(self.Run.search([("run_type", "=", "snapshot_revert")]))

    def test_apply_plan_changed(self):
        self.fake.answers[(PULL, "--apply")] = (
            4,
            {"command": "apply", "error": "plan_changed", "resultats": []},
        )
        with self.server_actions_allowed():
            dry_run, apply_run = self._apply()
        self.assertEqual(apply_run.state, "failed")
        self.assertIn("out of date", apply_run.log)
        self.assertFalse(apply_run.stash_ids)
        self.assertFalse(apply_run.snapshot_id)
        self.assertFalse(dry_run.can_apply)
        self.assertIn("moved since this dry run", dry_run.apply_note)

    def test_apply_left_mid_operation_blocks_the_restart(self):
        data = copy.deepcopy(REVERT_APPLY)
        data["resultats"][0]["etat"] = "restauration_echouee"
        self.fake.answers[(PULL, "--apply")] = (0, data)
        with self.server_actions_allowed():
            _dry, apply_run = self._apply()
            self.assertTrue(apply_run.pull_blocked)
            with self.assertRaises(UserError):
                apply_run.action_restart()
            with self.assertRaises(UserError):
                self.Run.browse()._check_no_blocked_pull()
            # A new dry run, once the repository is fixed, lifts it.
            self._dry_run()
            self.Run.browse()._check_no_blocked_pull()

    def test_apply_timeout_reads_backups_back(self):
        self.fake.answers[(PULL, "--apply")] = subprocess.TimeoutExpired([PULL], 1)
        with self.server_actions_allowed():
            _dry, apply_run = self._apply()
        self.assertEqual(apply_run.state, "failed")
        self.assertTrue(apply_run.pull_blocked)
        self.assertIn("did not finish", apply_run.log)
        self.assertIn("read back: 1", apply_run.log)
        self.assertEqual(len(apply_run.backup_ids), 1)

    # ── stashes ─────────────────────────────────────────────────────────

    def test_stash_reapply(self):
        with self.server_actions_allowed():
            _dry, apply_run = self._apply()
            stash = apply_run.stash_ids
            action = stash.action_reapply()
            self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")
            self.assertFalse(self._pull_args("--apply-stash"))
            with self.assertRaises(UserError):
                self._confirm(
                    "stash_apply", run=apply_run, stash=stash, typed="other"
                ).action_confirm()
            self.assertFalse(self._pull_args("--apply-stash"))
            self._confirm("stash_apply", run=apply_run, stash=stash).action_confirm()
        self.assertEqual(
            self._pull_args("--apply-stash"),
            [
                [
                    "--apply-stash",
                    f"{REPO}={STASH_SHA}",
                    "--confirm",
                    SERIES,
                    "--json",
                ]
            ],
        )
        self.assertEqual(stash.state, "applied")
        self.assertIn("reapplied", stash.log)
        with self.server_actions_allowed(), self.assertRaises(UserError):
            stash.action_reapply()

    def test_stash_conflict_and_missing(self):
        with self.server_actions_allowed():
            _dry, apply_run = self._apply()
            stash = apply_run.stash_ids
            self.fake.answers[(PULL, "--apply-stash")] = (
                0,
                dict(
                    STASH_APPLIED,
                    etat="conflit",
                    motif="CONFLICT",
                    conflits=["a"],
                ),
            )
            self._confirm("stash_apply", run=apply_run, stash=stash).action_confirm()
            self.assertEqual(stash.state, "conflict")
            self.assertIn("CONFLICT", stash.log)
            self.fake.answers[(PULL, "--apply-stash")] = (
                0,
                dict(
                    STASH_APPLIED,
                    etat="refuse_sale",
                    motif="modified tracked files",
                ),
            )
            self._confirm("stash_apply", run=apply_run, stash=stash).action_confirm()
            self.assertEqual(stash.state, "conflict")
            self.assertIn("modified tracked files", stash.log)
            self.fake.answers[(PULL, "--apply-stash")] = (
                3,
                dict(STASH_APPLIED, etat="introuvable"),
            )
            self._confirm("stash_apply", run=apply_run, stash=stash).action_confirm()
            self.assertEqual(stash.state, "missing")

    def test_stash_reapply_waits_for_a_git_run(self):
        with self.server_actions_allowed():
            _dry, apply_run = self._apply()
            stash = apply_run.stash_ids
            # A queued dry run holds the checkout.
            self.Wizard.browse(
                self._snapshot().action_revert()["res_id"]
            ).action_start()
            with self.assertRaisesRegex(UserError, "already queued"):
                self._confirm(
                    "stash_apply", run=apply_run, stash=stash
                ).action_confirm()
        self.assertEqual(stash.state, "kept")

    def test_pull_apply_records_its_kept_stash(self):
        """A pull whose stash pop conflicts keeps the stash: it is listed
        with the stashes of the returns."""
        self.fake.answers.pop((PULL, "--dry-run"))
        self.fake.answers.pop((PULL, "--apply"))
        with self.server_actions_allowed():
            Wizard = self.env["erplibre.code.pull.wizard"]
            wizard = Wizard.browse(Wizard._action_open()["res_id"])
            dry_run = self.Run.browse(wizard.action_start()["res_id"])
            self.Run._cron_process()
            apply_run = self.Run.browse(
                self._confirm("pull_apply", run=dry_run).action_confirm()["res_id"]
            )
            self.Run._cron_process()
        self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertEqual(apply_run.stash_ids.path, REPO)
        self.assertEqual(apply_run.stash_ids.sha, "5" * 40)
        self.assertIn(apply_run.stash_ids, self.Stash.search([]))
