# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import shutil
import subprocess
import tempfile
from unittest.mock import patch

from odoo import Command
from odoo.addons.erplibre_info import runner
from odoo.addons.erplibre_info.tests.common import REPO, SERIES
from odoo.addons.erplibre_info_git.tests.common import ErplibreInfoGitCase
from odoo.exceptions import UserError
from odoo.tests import tagged

from .. import code
from .common import DeveloperCase, DeveloperMixin

MODEL_MODULE = "odoo.addons.erplibre_developer.models.erplibre_developer"


@tagged("post_install", "-at_install")
class TestCodeInfo(DeveloperMixin, ErplibreInfoGitCase):
    """The repository of a module, from a snapshot of erplibre_info_git or
    from ``repo_state.py``, answered by the fake scripts of erplibre_info."""

    def _fake_module(self):
        """A module directory inside a clone of the fake checkout, where
        Odoo is told the module ``erplibre_info`` lives. The fake checkout
        is removed with the test class."""
        clone = os.path.join(self.root, REPO)
        module_dir = os.path.join(clone, "erplibre_info")
        os.makedirs(os.path.join(clone, ".git"), exist_ok=True)
        os.makedirs(module_dir, exist_ok=True)
        return patch(
            f"{MODEL_MODULE}.get_module_path",
            lambda name, display_warning=False: module_dir,
        )

    def test_from_the_last_snapshot(self):
        self.Snapshot._capture("manual", force=True)
        calls = len(self.fake.calls)
        res = self.Dev.get_code_info(["erplibre_info"])
        self.assertEqual(len(self.fake.calls), calls, "no script call")
        entry = res["modules"][0]
        self.assertEqual(entry["name"], "erplibre_info")
        self.assertEqual(entry["state"], "installed")
        self.assertEqual(entry["repo_source"], "snapshot")
        self.assertEqual(entry["repo"]["path"], REPO)
        self.assertEqual(entry["repo"]["state"], "conforme")
        self.assertEqual(entry["repo"]["state_label"], "Matches the manifest")
        self.assertEqual(entry["repo"]["head"], "1" * 40)
        self.assertEqual(entry["repo"]["target"], "1" * 40)
        self.assertEqual(entry["repo"]["ahead"], 0)
        self.assertEqual(entry["repo"]["behind"], 0)
        self.assertEqual(entry["repo"]["alignment"], "conforme")
        self.assertEqual(entry["repo"]["alignment_label"], "Matches the manifest")
        self.assertTrue(res["snapshot_date"])
        self.assertFalse(res["error"])

    def test_gap_with_the_manifest(self):
        """``ahead`` and ``behind`` come with a target; without one they
        are unknown, not zero."""
        vals = self.Dev._repo_vals(
            {
                "state": "sale",
                "alignment": "en_avance",
                "target": "2" * 40,
                "ahead": 2,
                "behind": 0,
                "dirty": True,
            }
        )
        self.assertEqual((vals["ahead"], vals["behind"]), (2, 0))
        self.assertEqual(vals["state"], "sale")
        self.assertEqual(vals["alignment"], "en_avance")
        self.assertEqual(vals["alignment_label"], "Ahead of the manifest")
        vals = self.Dev._repo_vals({"state": "decale", "target": None, "ahead": None})
        self.assertFalse(vals["target"])
        self.assertIs(vals["ahead"], False)
        self.assertIs(vals["behind"], False)

    def test_read_with_repo_state(self):
        with self._fake_module():
            res = self.Dev.get_code_info(["erplibre_info"])
        entry = res["modules"][0]
        self.assertEqual(entry["clone_rel"], REPO)
        self.assertEqual(entry["module_rel"], "erplibre_info")
        self.assertEqual(entry["path_rel"], f"{REPO}/erplibre_info")
        self.assertEqual(entry["repo_source"], "repo_state")
        self.assertEqual(entry["repo"]["state"], "conforme")
        self.assertIn(
            ("repo_state.py", ["snapshot", "--repo", REPO]), self.fake.scripts()
        )

    def test_refresh_reads_the_clones(self):
        self.Snapshot._capture("manual", force=True)
        with self._fake_module():
            res = self.Dev.get_code_info(["erplibre_info"], refresh=True)
        self.assertEqual(res["modules"][0]["repo_source"], "repo_state")

    def test_script_failure_is_reported(self):
        self.fake.answers[("repo_state.py", "snapshot")] = (1, {"error": "broken"})
        with self._fake_module():
            res = self.Dev.get_code_info(["erplibre_info"])
        self.assertIn("broken", res["error"])
        self.assertFalse(res["modules"][0]["repo"])

    def test_state_label_in_the_user_language(self):
        self.Snapshot._capture("manual", force=True)
        self.env["res.lang"]._activate_lang("fr_CA")
        # The repository states are a selection of erplibre_info_git.
        self.env["ir.module.module"].search(
            [("name", "=", "erplibre_info_git")]
        )._update_translations(["fr_CA"])
        res = self.Dev.with_context(lang="fr_CA").get_code_info(["erplibre_info"])
        self.assertEqual(res["modules"][0]["repo"]["state_label"], "Conforme")

    def test_missing_checkout_is_reported(self):
        """A checkout that is not found reads no clone: the snapshot stays
        the source, even on refresh, and the error says why."""
        self.Snapshot._capture("manual", force=True)
        missing = os.path.join(self.root, "no_such_checkout")
        self.env["ir.config_parameter"].sudo().set_param("erplibre_info.root", missing)
        calls = len(self.fake.calls)
        with self._fake_module():
            for refresh in (False, True):
                with self.subTest(refresh=refresh):
                    res = self.Dev.get_code_info(["erplibre_info"], refresh=refresh)
                    self.assertTrue(res["error"])
                    self.assertIn("erplibre_info.root", res["error"])
                    entry = res["modules"][0]
                    self.assertEqual(entry["repo_source"], "snapshot")
                    self.assertEqual(entry["repo"]["path"], REPO)
        self.assertEqual(len(self.fake.calls), calls, "no script call")

    def test_module_outside_the_checkout(self):
        """A clone that is not under the ERPLibre checkout is named by its
        path; no script reads it."""
        calls = len(self.fake.calls)
        res = self.Dev.get_code_info(["erplibre_developer"])
        entry = res["modules"][0]
        self.assertEqual(len(self.fake.calls), calls)
        self.assertFalse(entry["repo"])
        self.assertTrue(entry["path"].endswith("erplibre_developer"))
        self.assertEqual(entry["code_version"], entry["installed_version"])


@tagged("post_install", "-at_install")
class TestModuleCommits(DeveloperCase):
    """``git log`` on a throw-away clone."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clone = tempfile.mkdtemp(prefix="erplibre_developer_git_")
        cls.addClassCleanup(shutil.rmtree, cls.clone, True)
        env = dict(
            os.environ,
            GIT_AUTHOR_NAME="Example",
            GIT_AUTHOR_EMAIL="example@example.invalid",
            GIT_COMMITTER_NAME="Example",
            GIT_COMMITTER_EMAIL="example@example.invalid",
        )

        def git(*args):
            subprocess.run(
                ["git", "-C", cls.clone, *args],
                env=env,
                check=True,
                capture_output=True,
            )

        git("init", "-q")
        os.makedirs(os.path.join(cls.clone, "my_module"))
        for name, subject in (
            ("my_module/a.py", "[ADD] my_module: first"),
            ("other.txt", "[ADD] other file"),
            ("my_module/b.py", "[IMP] my_module: second"),
        ):
            with open(os.path.join(cls.clone, name), "w") as fh:
                fh.write(subject)
            git("add", name)
            git("commit", "-q", "-m", subject)

    def _patch_path(self):
        module_dir = os.path.join(self.clone, "my_module")
        return patch(
            f"{MODEL_MODULE}.get_module_path",
            lambda name, display_warning=False: module_dir,
        )

    def test_commits_of_the_module_only(self):
        with self._patch_path():
            res = self.Dev.get_module_commits("my_module")
        self.assertFalse(res["error"])
        self.assertEqual(
            [c["subject"] for c in res["commits"]],
            ["[IMP] my_module: second", "[ADD] my_module: first"],
        )
        self.assertEqual(len(res["commits"][0]["sha"]), 40)
        self.assertEqual(res["commits"][0]["author"], "Example")

    def test_limit(self):
        with self._patch_path():
            res = self.Dev.get_module_commits("my_module", limit=1)
        self.assertEqual(len(res["commits"]), 1)

    def test_timeout_is_reported(self):
        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))

        with self._patch_path(), patch.object(code.subprocess, "run", slow):
            res = self.Dev.get_module_commits("my_module")
        self.assertEqual(res["commits"], [])
        self.assertIn("git log", res["error"])

    def test_not_a_clone(self):
        outside = tempfile.mkdtemp(prefix="erplibre_developer_plain_")
        self.addCleanup(shutil.rmtree, outside, True)
        with patch(
            f"{MODEL_MODULE}.get_module_path",
            lambda name, display_warning=False: outside,
        ), patch.object(code, "repository_of", lambda path, stop=None: None):
            res = self.Dev.get_module_commits("my_module")
        self.assertTrue(res["error"])

    def test_helpers(self):
        sub = os.path.join(self.clone, "my_module")
        self.assertEqual(code.repository_of(sub), os.path.realpath(self.clone))
        self.assertEqual(code.relative_to(sub, self.clone), "my_module")
        self.assertEqual(code.relative_to("/elsewhere/x", self.clone), "/elsewhere/x")
        self.assertTrue(code.is_sha("a1b2c3d"))
        for value in ("HEAD", "--all", "a1b2c3d..HEAD", "abc", False, 7):
            self.assertFalse(code.is_sha(value), value)


GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Example",
    GIT_AUTHOR_EMAIL="example@example.invalid",
    GIT_COMMITTER_NAME="Example",
    GIT_COMMITTER_EMAIL="example@example.invalid",
)


@tagged("post_install", "-at_install")
class TestRepoDetails(DeveloperCase):
    """``get_repo_details`` on a throw-away checkout holding one clone."""

    REL = f"odoo{SERIES}/addons/Example_dev"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = os.path.realpath(tempfile.mkdtemp(prefix="erplibre_developer_root_"))
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        script = os.path.join(cls.root, runner.SCRIPT_STATE)
        os.makedirs(os.path.dirname(script))
        open(script, "w").close()
        cls.clone = os.path.join(cls.root, cls.REL)
        os.makedirs(os.path.join(cls.clone, "my_module"))
        cls.git("init", "-q")
        cls.shas = []
        for index in range(3):
            name = f"my_module/f{index}.py"
            with open(os.path.join(cls.clone, name), "w") as fh:
                fh.write(str(index))
            cls.git("add", name)
            cls.git("commit", "-q", "-m", f"[ADD] my_module: step {index}")
            cls.shas.append(cls.git("rev-parse", "HEAD").strip())
        # Uncommitted: one tracked file changed, more untracked files than
        # the list keeps.
        with open(os.path.join(cls.clone, "my_module/f0.py"), "w") as fh:
            fh.write("changed")
        for index in range(code.MAX_DIRTY_FILES + 2):
            open(os.path.join(cls.clone, f"new_{index:02}.txt"), "w").close()

    @classmethod
    def git(cls, *args):
        return subprocess.run(
            ["git", "-C", cls.clone, *args],
            env=GIT_ENV,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(runner.PARAM_ROOT, self.root)

    def test_dirty_files_capped_with_the_total(self):
        res = self.Dev.get_repo_details(self.REL)
        self.assertFalse(res["error"])
        self.assertEqual(res["repo"], self.REL)
        self.assertEqual(res["dirty_count"], code.MAX_DIRTY_FILES + 3)
        self.assertEqual(len(res["dirty_files"]), code.MAX_DIRTY_FILES)
        self.assertIn({"status": " M", "path": "my_module/f0.py"}, res["dirty_files"])
        self.assertIn({"status": "??", "path": "new_00.txt"}, res["dirty_files"])

    def test_commits_marked_ahead_of_the_target(self):
        res = self.Dev.get_repo_details(self.REL, target=self.shas[0])
        self.assertEqual(res["target"], self.shas[0])
        self.assertEqual(
            [(c["sha"], c["ahead"]) for c in res["commits"]],
            [(self.shas[2], True), (self.shas[1], True), (self.shas[0], False)],
        )
        self.assertEqual(res["commits"][0]["subject"], "[ADD] my_module: step 2")
        res = self.Dev.get_repo_details(self.REL, target=self.shas[2], limit=2)
        self.assertEqual([c["ahead"] for c in res["commits"]], [False, False])

    def test_target_from_the_last_snapshot(self):
        self.env["erplibre.code.snapshot"].sudo().create(
            {
                "trigger": "manual",
                "repo_ids": [
                    Command.create({"path": self.REL, "target": self.shas[1]})
                ],
            }
        )
        res = self.Dev.get_repo_details(self.REL)
        self.assertEqual(res["target"], self.shas[1])
        self.assertEqual([c["ahead"] for c in res["commits"]], [True, False, False])

    def test_unknown_target(self):
        """Without a target, or with a value that is not a commit name, no
        commit is marked; an unknown commit is reported, not raised."""
        for target in (False, "HEAD~1", "--all"):
            with self.subTest(target=target):
                res = self.Dev.get_repo_details(self.REL, target=target)
                self.assertFalse(res["target"])
                self.assertEqual(len(res["commits"]), 3)
                self.assertTrue(all(c["ahead"] is None for c in res["commits"]))
                self.assertFalse(res["error"])
        res = self.Dev.get_repo_details(self.REL, target="0" * 40)
        self.assertTrue(res["error"])
        self.assertEqual(len(res["commits"]), 3)
        self.assertTrue(all(c["ahead"] is None for c in res["commits"]))

    def test_only_the_clones_of_the_server(self):
        outside = tempfile.mkdtemp(prefix="erplibre_developer_outside_")
        self.addCleanup(shutil.rmtree, outside, True)
        os.makedirs(os.path.join(outside, ".git"))
        for repo in (
            outside,
            os.path.relpath(outside, self.root),
            f"{self.REL}/my_module",
            "",
            False,
        ):
            with self.subTest(repo=repo), self.assertRaises(UserError):
                self.Dev.get_repo_details(repo)
        res = self.Dev.get_repo_details(self.clone)
        self.assertEqual(res["repo"], self.REL)

    def test_git_failure_is_reported(self):
        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))

        with patch.object(code.subprocess, "run", slow):
            res = self.Dev.get_repo_details(self.REL, target=self.shas[0])
        self.assertIn("git status", res["error"])
        self.assertIn("git log", res["error"])
        self.assertEqual(res["commits"], [])
        self.assertEqual(res["dirty_count"], 0)

    def test_read_only(self):
        """Reading the details changes nothing in the clone."""
        index = os.path.join(self.clone, ".git", "index")
        status = self.git("status", "--porcelain")
        before = os.stat(index).st_mtime_ns
        self.Dev.get_repo_details(self.REL, target=self.shas[0])
        self.assertEqual(os.stat(index).st_mtime_ns, before)
        self.assertEqual(self.git("status", "--porcelain"), status)


@tagged("post_install", "-at_install")
class TestRecentRuns(DeveloperCase):
    def _run(self, **vals):
        return (
            self.env["erplibre.code.run"]
            .sudo()
            .create(dict({"run_type": "restart"}, **vals))
        )

    def test_recent_runs_as_recorded(self):
        Run = self.env["erplibre.code.run"]
        Run.search([]).unlink()
        older = self._run(state="failed", log="Restart requested by Example.")
        newer = self._run(
            state="done",
            log="Restart requested by Example.\n"
            "Modules marked to upgrade: base, no_such_module_erplibre, web",
        )
        runs = self.Dev.get_recent_runs()
        self.assertEqual([r["id"] for r in runs], [newer.id, older.id])
        self.assertEqual(runs[0]["state"], "done")
        self.assertEqual(runs[0]["state_label"], "Done")
        self.assertEqual(runs[0]["run_type"], "restart")
        self.assertEqual(runs[0]["type_label"], "Server restart")
        self.assertEqual(runs[0]["modules"], ["base", "web"])
        self.assertEqual(runs[0]["user"], self.env.user.name)
        self.assertTrue(runs[0]["date"])
        self.assertEqual(runs[1]["state"], "failed")
        self.assertEqual(runs[1]["modules"], [])
        self.assertEqual(len(self.Dev.get_recent_runs(limit=1)), 1)
