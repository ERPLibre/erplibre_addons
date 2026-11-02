# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import os

from odoo.tests import tagged

from .test_pull_real import CLONE, SERIES, RealRepositoriesCase, _git


@tagged("post_install", "-at_install")
class TestRevertRealRepositories(RealRepositoriesCase):
    """The real ``repo_pull.py --mode instantane`` on the throwaway
    checkout of ``RealRepositoriesCase``: a clone that got a local commit
    and a modified tracked file since the snapshot goes back to it, its
    stash is kept and listed, then reapplied."""

    def _read(self, name):
        with open(os.path.join(self.root, CLONE, name)) as fh:
            return fh.read()

    def _write(self, name, text):
        with open(os.path.join(self.root, CLONE, name), "w") as fh:
            fh.write(text)

    def test_revert_keeps_and_reapplies_the_stash(self):
        clone = os.path.join(self.root, CLONE)
        start = self._head()
        original = self._read("a.txt")
        with self.allowed():
            snapshot = self.env["erplibre.code.snapshot"]._capture("manual", force=True)
        line = snapshot.repo_ids.filtered(lambda r: r.path == CLONE)
        self.assertEqual((line.head, line.branch), (start, SERIES))

        # A commit that no remote has, then a modified tracked file.
        self._write("c.txt", "local\n")
        _git(clone, "add", "c.txt")
        _git(clone, "commit", "-q", "-m", "local change")
        local = self._head()
        self._write("a.txt", "modified\n")

        with self.allowed():
            Wizard = self.env["erplibre.code.revert.wizard"]
            wizard = Wizard.browse(snapshot.action_revert()["res_id"])
            self.assertTrue(wizard.include_root)
            dry_run = self.Run.browse(wizard.action_start()["res_id"])
            self.Run._cron_process()
            self.assertEqual(dry_run.state, "done", dry_run.log)
            # The dry run only reads; the root is already on its commit.
            self.assertEqual(self._head(), local)
            self.assertEqual(self._read("a.txt"), "modified\n")
            self.assertEqual(dry_run.plan_paths, CLONE)
            repos = {r["chemin"]: r for r in json.loads(dry_run.result_json)["depots"]}
            self.assertEqual(repos["."]["verdict"], "a_jour")
            repo = repos[CLONE]
            self.assertEqual(repo["verdict"], "recul")
            self.assertEqual((repo["quittes"], repo["locaux"]), (1, 1))
            self.assertTrue(repo["stash_prevu"])
            html = str(dry_run.report_html)
            self.assertIn("back to an older commit", html)
            self.assertIn("yes (stash kept)", html)

            apply_run = self.Run.browse(
                self._confirm("snapshot_revert", run=dry_run)["res_id"]
            )
            self.Run._cron_process()
            self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertEqual(self._head(), start)
        self.assertEqual(_git(clone, "branch", "--show-current"), SERIES)
        self.assertEqual(self._read("a.txt"), original)
        self.assertFalse(_git(clone, "status", "--porcelain", "--untracked-files=no"))
        self.assertTrue(apply_run.snapshot_id, apply_run.log)
        self.assertTrue(apply_run.pass_dir.startswith("tasks/git_repo_pull/"))
        # The local commit survives in the backup branch.
        backup = apply_run.backup_ids
        self.assertEqual((backup.path, backup.sha), (CLONE, local))
        self.assertEqual(_git(clone, "rev-parse", backup.branch_name), local)
        # The stash is kept in the clone and listed.
        stash = apply_run.stash_ids
        self.assertEqual((stash.path, stash.state), (CLONE, "kept"))
        self.assertIn(stash.sha, _git(clone, "stash", "list", "--format=%H").split())
        self.assertIn(stash.sha, stash.command)
        self.assertIn(stash, self.env["erplibre.code.stash"].search([]))

        with self.allowed():
            self._confirm("stash_apply", run=apply_run, stash=stash)
        self.assertEqual(stash.state, "applied", stash.log)
        self.assertEqual(self._read("a.txt"), "modified\n")
        self.assertEqual(self._head(), start)
        # Reapplied, the stash stays in the list.
        self.assertIn(stash.sha, _git(clone, "stash", "list", "--format=%H").split())
