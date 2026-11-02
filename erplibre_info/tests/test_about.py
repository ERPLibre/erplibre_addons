# © 2021-2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import os
import shutil
import subprocess
import tempfile
from unittest.mock import patch

from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from .. import about, runner
from .common import ErplibreInfoCase

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}

MANIFEST = (
    '<manifest>\n  <remote name="Example" fetch="https://git.example.invalid/"/>\n'
    '  <project name="a.git" path="odooX/a" revision="%s"/>\n</manifest>\n'
)


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@tagged("post_install", "-at_install")
class TestAboutRead(TransactionCase):
    """``about.read`` on a temporary checkout."""

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp(prefix="erplibre_info_about_")
        self.addCleanup(shutil.rmtree, self.root, True)
        env = patch.dict(os.environ, dict(GIT_ENV, GIT_CEILING_DIRECTORIES=self.root))
        env.start()
        self.addCleanup(env.stop)

    def _write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def _write_versions(self):
        self._write(".erplibre-semver-version", "1.2.3\n")
        self._write(".python-odoo-version", "3.0.1\n")
        self._write("conf/python-erplibre-version", "3.0.2\n")
        self._write(".odoo-version", "1.0\n")
        self._write(".poetry-version", "9.9.9\n")
        self._write(
            "conf/supported_version_erplibre.json",
            json.dumps(
                {
                    "odoo0.9_python3.0.1": {
                        "odoo_version": "0.9",
                        "python_version": "3.0.1",
                    },
                    "odoo1.0_python3.0.1": {
                        "odoo_version": "1.0",
                        "python_version": "3.0.1",
                    },
                }
            ),
        )

    def test_missing_files(self):
        """An empty directory: every value is unknown, nothing raises."""
        data = about.read(self.root)
        for key in (
            "semver",
            "python_odoo",
            "python_tooling",
            "odoo_version",
            "poetry_version",
            "extra",
            "version_key",
            "mode",
        ):
            self.assertIsNone(data[key], key)
        self.assertFalse(data["mobile"])
        self.assertEqual(data["installed_versions"], [])
        self.assertEqual(
            data["commit"], {"short": None, "branch": None, "describe": None}
        )

    def test_no_checkout(self):
        data = about.read(None)
        self.assertIsNone(data["semver"])
        self.assertIsNone(data["mobile"])
        self.assertIsNone(data["commit"]["short"])

    def test_values_from_files(self):
        self._write_versions()
        self._write(".repo/installed_odoo_version.txt", "odoo1.0\nodoo0.9\n")
        self._write(
            ".erplibre-state.json",
            json.dumps({"odoo_versions": {"1.0": {"extra": True}}}),
        )
        os.makedirs(os.path.join(self.root, about.MOBILE_PATH))
        data = about.read(self.root)
        self.assertEqual(
            {k: data[k] for k in ("semver", "python_odoo", "python_tooling")},
            {"semver": "1.2.3", "python_odoo": "3.0.1", "python_tooling": "3.0.2"},
        )
        self.assertEqual(data["odoo_version"], "1.0")
        self.assertEqual(data["poetry_version"], "9.9.9")
        self.assertEqual(data["version_key"], "odoo1.0_python3.0.1")
        self.assertEqual(data["installed_versions"], ["odoo0.9", "odoo1.0"])
        self.assertTrue(data["extra"])
        self.assertTrue(data["mobile"])

    def test_extra_inactive_without_a_readable_state(self):
        self._write_versions()
        self.assertFalse(about.read(self.root)["extra"])
        self._write(".erplibre-state.json", "{not json")
        self.assertFalse(about.read(self.root)["extra"])
        self._write(
            ".erplibre-state.json",
            json.dumps({"odoo_versions": {"0.9": {"extra": True}}}),
        )
        self.assertFalse(about.read(self.root)["extra"])

    def test_version_key_without_a_match(self):
        self._write_versions()
        self._write(".python-odoo-version", "3.0.9\n")
        self.assertIsNone(about.read(self.root)["version_key"])
        self._write("conf/supported_version_erplibre.json", "[]")
        self.assertIsNone(about.read(self.root)["version_key"])

    def test_code_mode(self):
        rel = about.LOCAL_MANIFEST
        self._write(rel, MANIFEST % ("a" * 40))
        self.assertEqual(about.read(self.root)["mode"], "frozen")
        self._write(rel, MANIFEST % "main")
        self.assertEqual(about.read(self.root)["mode"], "branches")
        self._write(rel, "<manifest")
        self.assertIsNone(about.read(self.root)["mode"])

    def test_commit(self):
        _git(self.root, "init", "-q")
        self._write("a.txt", "one\n")
        _git(self.root, "add", "a.txt")
        _git(self.root, "commit", "-q", "-m", "one")
        commit = about.read(self.root)["commit"]
        self.assertEqual(
            commit["short"], _git(self.root, "rev-parse", "--short", "HEAD")
        )
        self.assertEqual(commit["branch"], "main")
        # Without a tag, git describe fails: the line is left out.
        self.assertIsNone(commit["describe"])
        _git(self.root, "tag", "v1.0.0")
        self._write("a.txt", "two\n")
        _git(self.root, "commit", "-q", "-am", "two")
        commit = about.read(self.root)["commit"]
        self.assertTrue(commit["describe"].startswith("v1.0.0-1-g"), commit)
        _git(self.root, "checkout", "-q", "--detach")
        self.assertIsNone(about.read(self.root)["commit"]["branch"])

    def test_git_failure(self):
        """A git that is missing, times out or fails leaves the commit
        unknown; the file values stay."""
        self._write_versions()
        os.makedirs(os.path.join(self.root, ".git"))
        for error in (
            FileNotFoundError("git"),
            subprocess.TimeoutExpired(["git"], about.GIT_TIMEOUT),
        ):
            with patch.object(about.subprocess, "run", side_effect=error):
                data = about.read(self.root)
            self.assertEqual(
                data["commit"], {"short": None, "branch": None, "describe": None}
            )
            self.assertEqual(data["semver"], "1.2.3")
        # An empty .git: every command fails.
        self.assertIsNone(about.read(self.root)["commit"]["short"])

    def test_git_writes_nothing(self):
        """Each git command is read-only, bounded, without a prompt, and
        passes safe.directory on its command line instead of storing it."""
        os.makedirs(os.path.join(self.root, ".git"))
        calls = []

        def run(argv, **kw):
            calls.append((argv, kw))
            return subprocess.CompletedProcess(argv, 0, "x\n", "")

        with patch.object(about.subprocess, "run", run):
            about.read(self.root)
        self.assertEqual(
            [argv[5:] for argv, _kw in calls],
            [
                ["rev-parse", "--short", "HEAD"],
                ["symbolic-ref", "--short", "-q", "HEAD"],
                ["describe", "--tags"],
            ],
        )
        for argv, kw in calls:
            self.assertEqual(
                argv[:5], ["git", "-c", "safe.directory=*", "-C", self.root]
            )
            self.assertEqual(kw["timeout"], about.GIT_TIMEOUT)
            self.assertEqual(kw["env"]["GIT_OPTIONAL_LOCKS"], "0")
            self.assertEqual(kw["env"]["GIT_TERMINAL_PROMPT"], "0")


@tagged("post_install", "-at_install")
class TestAboutSettings(ErplibreInfoCase):
    """The method of the Settings form, and the view that places the
    block."""

    def test_reads_the_checkout_of_the_scripts(self):
        path = os.path.join(self.root, about.SEMVER_FILE)
        with open(path, "w") as fh:
            fh.write("1.2.3\n")
        self.addCleanup(os.unlink, path)
        data = self.env["res.config.settings"].erplibre_about()
        self.assertEqual(data["semver"], "1.2.3")
        self.assertEqual(runner.erplibre_root(self.env), self.root)

    def test_settings_administrators_only(self):
        user = new_test_user(
            self.env, login="erplibre_info_about_user", groups="base.group_user"
        )
        with self.assertRaises(AccessError):
            self.env["res.config.settings"].with_user(user).erplibre_about()

    def test_block_after_odoo_block(self):
        arch = etree.fromstring(
            self.env["res.config.settings"].get_view(
                self.env.ref("base.res_config_settings_view_form").id, "form"
            )["arch"]
        )
        widgets = [
            w.get("name")
            for w in arch.xpath("//block[@name='about_setting_container']/widget")
        ]
        self.assertIn("res_config_edition", widgets)
        self.assertEqual(
            widgets[widgets.index("res_config_edition") + 1], "erplibre_about"
        )


@tagged("post_install", "-at_install")
class TestAboutTour(HttpCase):
    def test_about_block(self):
        self.start_tour("/odoo/settings", "erplibre_info_about", login="admin")
