# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from unittest.mock import patch

import odoo
from odoo import release
from odoo.tests import TransactionCase, tagged
from odoo.tools import config

from .. import runner

SERIES = release.series
CLONE = f"odoo{SERIES}/addons/Example_pull"


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@tagged("post_install", "-at_install")
class TestPullRealRepositories(TransactionCase):
    """The real ``repo_pull.py`` on a throwaway checkout.

    A temporary directory holds an ERPLibre root and one addons clone,
    each on a branch that tracks a bare repository beside them. The
    ``script`` directory and the ERPLibre interpreter of the checkout that
    runs this Odoo are symbolic links in that root: the scripts resolve
    their root from their own path, so every git call stays in the
    temporary directory. Git runs without the global and system
    configuration.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.real_root = runner.find_root(os.path.dirname(odoo.__file__))
        if (
            not cls.real_root
            or not os.access(os.path.join(cls.real_root, runner.PYTHON), os.X_OK)
            or not os.path.isfile(os.path.join(cls.real_root, runner.SCRIPT_PULL))
            or not shutil.which("git")
        ):
            cls.real_root = None

    def setUp(self):
        super().setUp()
        if not self.real_root:
            self.skipTest("no ERPLibre checkout with repo_pull.py around this Odoo")
        self.env.cr.postcommit.clear()
        self.base = tempfile.mkdtemp(prefix="erplibre_info_pull_")
        self.addCleanup(shutil.rmtree, self.base, True)
        env = patch.dict(
            os.environ,
            {
                "GIT_CEILING_DIRECTORIES": self.base,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.remotes = os.path.join(self.base, "remotes")
        os.makedirs(self.remotes)
        self.sources = {}
        for name in ("root", "addons"):
            self._remote(name)
        self.root = os.path.join(self.base, "root")
        _git(self.base, "clone", "-q", "-b", SERIES, self._url("root"), self.root)
        for link in ("script", ".venv.erplibre"):
            os.symlink(
                os.path.join(self.real_root, link), os.path.join(self.root, link)
            )
        with open(os.path.join(self.root, ".odoo-version"), "w") as fh:
            fh.write(f"{SERIES}\n")
        _git(
            self.base,
            "clone",
            "-q",
            "-o",
            "Example",
            "-b",
            SERIES,
            self._url("addons"),
            os.path.join(self.root, CLONE),
        )
        manifest = os.path.join(self.root, ".repo", "local_manifests")
        os.makedirs(manifest)
        with open(os.path.join(manifest, "erplibre_manifest.xml"), "w") as fh:
            fh.write(
                "<manifest>\n"
                f'  <remote name="Example" fetch="{self.remotes}/"/>\n'
                f'  <default remote="Example" revision="{SERIES}"/>\n'
                f'  <project name="addons.git" path="{CLONE}" '
                f'revision="{SERIES}"/>\n'
                "</manifest>\n"
            )
        self.env["ir.config_parameter"].sudo().set_param(runner.PARAM_ROOT, self.root)
        self.Run = self.env["erplibre.code.run"]

    def _url(self, name):
        return os.path.join(self.remotes, f"{name}.git")

    def _remote(self, name):
        _git(self.remotes, "init", "-q", "--bare", f"{name}.git")
        source = os.path.join(self.base, "sources", name)
        os.makedirs(source)
        _git(source, "init", "-q")
        self._commit(
            name,
            source,
            {
                ".gitignore": "/script\n/.venv.erplibre\n/.repo/\n/tasks/\n"
                "/odoo*/\n/.odoo-version\n",
                "a.txt": f"{name} one\n",
            },
        )
        self.sources[name] = source

    def _commit(self, name, source, files):
        for path, text in files.items():
            with open(os.path.join(source, path), "w") as fh:
                fh.write(text)
            _git(source, "add", path)
        _git(source, "commit", "-q", "-m", f"{name} change")
        _git(source, "push", "-q", "-f", self._url(name), f"HEAD:{SERIES}")
        return _git(source, "rev-parse", "HEAD")

    def _head(self, path=CLONE):
        return _git(os.path.join(self.root, path), "rev-parse", "HEAD")

    @contextmanager
    def allowed(self):
        with patch.dict(
            config.options, {"erplibre_info_allow_server_actions": "True"}
        ), patch.object(type(self.Run), "_is_debug_mode", lambda self_: True):
            yield

    def _confirm(self, action, **kw):
        Wizard = self.env["erplibre.code.confirm.wizard"]
        wizard = Wizard.browse(Wizard._action_open(action, **kw)["res_id"])
        wizard.write({"typed_database_name": self.env.cr.dbname, "understood": True})
        return wizard.action_confirm()

    def test_pull_restore_delete(self):
        start = self._head()
        target = self._commit("addons", self.sources["addons"], {"a.txt": "two\n"})
        with self.allowed():
            Wizard = self.env["erplibre.code.pull.wizard"]
            wizard = Wizard.browse(Wizard._action_open()["res_id"])
            wizard.mode = "branche"
            dry_run = self.Run.browse(wizard.action_start()["res_id"])
            self.Run._cron_process()
            self.assertEqual(dry_run.state, "done", dry_run.log)
            # The dry run only fetches.
            self.assertEqual(self._head(), start)
            self.assertEqual(dry_run.plan_paths, CLONE)
            self.assertIn("addons change", str(dry_run.report_html))

            apply_run = self.Run.browse(
                self._confirm("pull_apply", run=dry_run)["res_id"]
            )
            self.Run._cron_process()
            self.assertEqual(apply_run.state, "done", apply_run.log)
            self.assertEqual(self._head(), target)
            self.assertTrue(apply_run.pass_dir.startswith("tasks/git_repo_pull/"))
            self.assertTrue(
                os.path.isfile(
                    os.path.join(self.root, apply_run.pass_dir, "passe.json")
                )
            )
            self.assertTrue(apply_run.snapshot_id, apply_run.log)
            backup = apply_run.backup_ids
            self.assertEqual(backup.path, CLONE)
            self.assertEqual(backup.sha, start)
            self.assertEqual(backup.original_branch, SERIES)

            restore_run = self.Run.browse(
                self._confirm("pull_restore", run=apply_run, backup=backup)["res_id"]
            )
            self.Run._cron_process()
            self.assertEqual(restore_run.state, "done", restore_run.log)
            self.assertEqual(backup.state, "restored")
            self.assertEqual(self._head(), start)
            self.assertEqual(
                _git(os.path.join(self.root, CLONE), "branch", "--show-current"),
                SERIES,
            )

            # A restored backup is kept on disk, and deleted from its own
            # record.
            backup.action_delete()
            self.assertEqual(backup.state, "deleted", backup.log)
        branches = _git(
            os.path.join(self.root, CLONE), "for-each-ref", "--format=%(refname:short)"
        ).split()
        self.assertNotIn(backup.branch_name, branches)
