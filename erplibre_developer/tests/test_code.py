# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import shutil
import subprocess
import tempfile
from unittest.mock import patch

from odoo.addons.erplibre_info.tests.common import REPO, ErplibreInfoCase
from odoo.tests import tagged

from .. import code
from .common import DeveloperCase, DeveloperMixin

MODEL_MODULE = "odoo.addons.erplibre_developer.models.erplibre_developer"


@tagged("post_install", "-at_install")
class TestCodeInfo(DeveloperMixin, ErplibreInfoCase):
    """The repository of a module, from a snapshot of erplibre_info or
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
        self.assertTrue(res["snapshot_date"])
        self.assertFalse(res["error"])

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
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env["ir.module.module"].search(
            [("name", "=", "erplibre_info")]
        )._update_translations(["fr_FR"])
        res = self.Dev.with_context(lang="fr_FR").get_code_info(["erplibre_info"])
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
