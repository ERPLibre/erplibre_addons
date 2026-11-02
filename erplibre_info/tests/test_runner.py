# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import shutil
import subprocess
import tempfile
import time

from odoo.tests import TransactionCase, tagged

from .. import runner


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
