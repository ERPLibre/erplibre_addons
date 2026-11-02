# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import subprocess
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.erplibre_info import runner
from .test_pull_real import CLONE, RealRepositoriesMixin, _git


@tagged("post_install", "-at_install")
class TestRevertTour(RealRepositoriesMixin, HttpCase):
    """The return to a snapshot clicked through in the browser, on the
    throwaway checkout of ``RealRepositoriesMixin``.

    The HTTP server of the test runs in this process: the patches of the
    environment, of the server action conditions and of the runner apply
    to its requests as well. A queued run is executed while the request
    that queued it is answered, as the cron would execute it, so the form
    the browser opens next shows the finished run. Every script call is
    recorded and must run in the temporary root.
    """

    def setUp(self):
        super().setUp()
        self.calls = []
        run_process = runner._run_process

        def recorded(argv, cwd, env, timeout):
            self.calls.append((list(argv), cwd))
            return run_process(argv, cwd=cwd, env=env, timeout=timeout)

        for patcher in (
            patch.object(runner, "_run_process", recorded),
            patch.object(
                type(self.Run),
                "_enqueue",
                lambda runs: runs.env["erplibre.code.run"].sudo()._cron_process(),
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _write(self, name, text):
        with open(os.path.join(self.root, CLONE, name), "w") as fh:
            fh.write(text)

    def _real_branch_exists(self, name):
        """Whether the checkout that runs this Odoo has the branch
        ``name``."""
        return not subprocess.run(
            ["git", "-C", self.real_root, "rev-parse", "--verify", "-q", name],
            capture_output=True,
        ).returncode

    def test_revert_tour(self):
        clone = os.path.join(self.root, CLONE)
        start = self._head()
        with self.allowed():
            snapshot = self.env["erplibre.code.snapshot"]._capture("manual", force=True)
        # A commit that no remote has, then a modified tracked file.
        self._write("c.txt", "local\n")
        _git(clone, "add", "c.txt")
        _git(clone, "commit", "-q", "-m", "local change")
        local = self._head()
        self._write("a.txt", "modified\n")

        with self.allowed():
            self.start_tour(
                "/odoo/action-erplibre_info_git.erplibre_code_snapshot_action/"
                f"{snapshot.id}?debug=1",
                "erplibre_info_git_fetch_snapshot_revert",
                login="admin",
                timeout=180,
            )

        apply_run = self.Run.search(
            [("run_type", "=", "snapshot_revert")], order="id desc", limit=1
        )
        self.assertEqual(apply_run.state, "done", apply_run.log)
        self.assertEqual(self._head(), start)
        backup = apply_run.backup_ids.filtered(lambda b: b.path == CLONE)
        self.assertEqual(_git(clone, "rev-parse", backup.branch_name), local)
        stash = apply_run.stash_ids
        self.assertEqual((stash.path, stash.state), (CLONE, "kept"))
        self.assertIn(stash.sha, _git(clone, "stash", "list", "--format=%H").split())

        # Every script ran from the temporary root, on its own scripts, and
        # the checkout that runs this Odoo got neither the pass nor the
        # backup branch.
        self.assertTrue(self.calls)
        for argv, cwd in self.calls:
            self.assertEqual(cwd, self.root, argv)
            self.assertTrue(argv[1].startswith(self.root + os.sep), argv)
        self.assertFalse(
            os.path.exists(os.path.join(self.real_root, apply_run.pass_dir))
        )
        self.assertFalse(self._real_branch_exists(backup.branch_name))
