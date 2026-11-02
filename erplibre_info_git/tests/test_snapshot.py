# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import json

from odoo import fields
from odoo.api import call_kw
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.erplibre_info import runner
from odoo.addons.erplibre_info.tests.common import (
    PERMISSIONS,
    REPO,
    REPO_CORE,
    SERIES,
)

from .common import ErplibreInfoGitCase


@tagged("post_install", "-at_install")
class TestSnapshot(ErplibreInfoGitCase):
    def test_install_runs_nothing(self):
        """Installing the module stores nothing, keeps the cron inactive,
        and the registry hook runs no script while the options are off."""
        self.assertFalse(self.Snapshot.search_count([]))
        self.assertFalse(self.Run.search_count([]))
        self.assertFalse(self.cron.active)
        self.Run._register_hook()
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.Run.search_count([]))

    def test_script_call(self):
        self.Snapshot._capture("manual")
        ((script, args, kwargs),) = self.fake.calls
        self.assertEqual(script, "repo_state.py")
        self.assertEqual(args, ["snapshot"])
        self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertNotIn("PYTHONPATH", kwargs["env"])
        self.assertEqual(kwargs["cwd"], self.root)
        self.assertGreater(kwargs["timeout"], 0)

    def test_name_says_its_time_is_utc(self):
        """The name is plain text: the web client never converts it to the
        viewer's time zone, so it says the time is UTC."""
        snap = self.Snapshot._capture("manual")
        self.assertEqual(snap.name, f"{fields.Datetime.to_string(snap.date)} UTC")
        self.assertTrue(snap.raw_json_filename.endswith("_UTC.json"))

    def test_dirty_option(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "erplibre_info.check_dirty", "True"
        )
        self.Snapshot._capture("manual")
        self.assertEqual(self.fake.scripts()[0][1], ["snapshot", "--dirty"])

    def test_fingerprint_dedup(self):
        first = self.Snapshot._capture("cron")
        self.assertTrue(first)
        self.assertFalse(self.Snapshot._capture("cron"))
        self.assertEqual(self.Snapshot.search_count([]), 1)
        self.fake.snapshot["repos"][0]["head"] = "c" * 40
        self.fake.snapshot["fingerprint"] = "e" * 64
        second = self.Snapshot._capture("cron")
        self.assertTrue(second)
        self.assertEqual(second.previous_id, first)
        moved = second.repo_ids.filtered(lambda r: r.path == REPO)
        self.assertEqual(moved.change, "changed")
        self.assertEqual(moved.previous_head, "1" * 40)
        self.assertEqual(second.changed_repo_ids, moved)

    def test_installed_versions_are_part_of_the_fingerprint(self):
        first = self.Snapshot._capture("cron")
        module = self.env.ref("base.module_base_setup")
        module.latest_version = "0.0.0"
        second = self.Snapshot._capture("cron")
        self.assertTrue(second)
        self.assertNotEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.code_fingerprint, second.code_fingerprint)

    def test_manual_always_creates(self):
        settings = self.env["res.config.settings"].create({})
        settings.action_erplibre_capture_now()
        action = settings.action_erplibre_capture_now()
        self.assertEqual(self.Snapshot.search_count([]), 2)
        self.assertEqual(action["res_model"], "erplibre.code.snapshot")

    def test_content(self):
        snap = self.Snapshot._capture("manual")
        self.assertEqual(snap.trigger, "manual")
        self.assertEqual(snap.erplibre_commit, "v0.0.0-1-gaaaaaaa")
        self.assertEqual(snap.mode, "branches")
        self.assertEqual(snap.repo_count, 3)
        self.assertEqual(snap.count_conforme, 2)
        self.assertEqual(snap.count_decale, 1)
        core = snap.repo_ids.filtered(lambda r: r.path == REPO_CORE)
        self.assertEqual(core.state, "decale")
        self.assertEqual(core.behind, 2)
        self.assertTrue(core.is_active_version)
        other = snap.repo_ids.filtered(lambda r: not r.is_active_version)
        self.assertEqual(other.odoo_version, "1.0")
        stored = json.loads(base64.b64decode(snap.raw_json))
        self.assertEqual(stored["fingerprint"], "f" * 64)

    def test_url_credentials_never_stored(self):
        snap = self.Snapshot._capture("manual")
        line = snap.repo_ids.filtered(lambda r: r.path == REPO)
        self.assertEqual(line.url, "https://git.example.invalid/addons.git")
        self.assertNotIn(b"secret-token", base64.b64decode(snap.raw_json))
        self.assertEqual(
            runner.strip_credentials("fatal: https://u:p@h.invalid/x and ssh://k@h"),
            "fatal: https://h.invalid/x and ssh://h",
        )

    def test_module_lines(self):
        """The code version comes from the repository of the running Odoo
        version; the same module under another tree is ignored."""
        snap = self.Snapshot._capture("manual")
        info = snap.module_ids.filtered(lambda m: m.name == "erplibre_info")
        self.assertEqual(info.code_version, f"{SERIES}.99.0.0")
        self.assertTrue(info.pending_update)
        self.assertEqual(info.repo_line_id.path, REPO)
        setup = snap.module_ids.filtered(lambda m: m.name == "base_setup")
        self.assertEqual(setup.code_version, f"{SERIES}.1.0")
        self.assertEqual(setup.repo_line_id.path, REPO_CORE)
        self.assertEqual(snap.pending_update_count, len(snap.pending_module_ids))
        self.assertIn(info, snap.pending_module_ids)
        base = snap.module_ids.filtered(lambda m: m.name == "base")
        self.assertFalse(base.found_in_code)
        self.assertFalse(base.pending_update)

    def test_commits_between(self):
        self.Snapshot._capture("cron")
        self.fake.snapshot["repos"][0]["head"] = "c" * 40
        self.fake.snapshot["fingerprint"] = "e" * 64
        snap = self.Snapshot._capture("cron")
        line = snap.repo_ids.filtered(lambda r: r.path == REPO)
        line.action_load_commits()
        self.assertEqual(
            self.fake.scripts()[-1],
            (
                "repo_state.py",
                ["between", REPO, "1" * 40, "c" * 40, "--max", "200"],
            ),
        )
        self.assertEqual(line.between_count, 2)
        self.assertIn("two", line.between_html)
        unchanged = snap.repo_ids.filtered(lambda r: r.path == REPO_CORE)
        with self.assertRaises(UserError):
            unchanged.action_load_commits()

    def test_missing_checkout(self):
        self.env["ir.config_parameter"].sudo().set_param(
            runner.PARAM_ROOT, self.root + "/absent"
        )
        with self.assertRaises(runner.RunnerError):
            self.Snapshot._capture("cron")
        with self.assertRaises(UserError):
            self.Snapshot.action_capture_now()
        self.assertEqual(self.fake.calls, [])

    def test_fork_upstream_and_its_gap(self):
        """The upstream of a fork and its gap reach the repository line; a
        repository without fork-upstream is not a fork."""
        snap = self.Snapshot._capture("manual")
        fork = snap.repo_ids.filtered(lambda r: r.path == REPO)
        self.assertTrue(fork.is_fork)
        self.assertEqual(fork.upstream_remote, "Upstream")
        self.assertEqual(fork.upstream_base, "b" * 40)
        self.assertEqual(fork.upstream_base_source, "upstream_freeze")
        self.assertEqual((fork.upstream_ahead, fork.upstream_behind), (3, 7))
        self.assertEqual(fork.upstream_tracking, f"refs/remotes/Upstream/{SERIES}")
        other = snap.repo_ids - fork
        self.assertTrue(other)
        self.assertFalse(any(other.mapped("is_fork")))
        Repo = self.env["erplibre.code.snapshot.repo"]
        self.assertEqual(Repo.search([("is_fork", "=", True)]), fork)

    def test_capture_now_from_the_buttons(self):
        """The buttons go through ``call_kw`` with the ids shown: none from
        the list header, the open snapshot from the form."""
        action = call_kw(self.Snapshot, "action_capture_now", [[]], {})
        first = self.Snapshot.browse(action["res_id"])
        self.assertEqual(first.trigger, "manual")
        action = call_kw(self.Snapshot, "action_capture_now", [first.ids], {})
        self.assertNotEqual(action["res_id"], first.id)
        self.assertEqual(self.Snapshot.search_count([]), 2)

    def test_script_failure(self):
        self.fake.answers[("repo_state.py", "snapshot")] = (
            1,
            {"error": "boom"},
        )
        with self.assertRaisesRegex(runner.RunnerError, "boom"):
            self.Snapshot._capture("cron")

    def test_permission_warning_stored_and_shown(self):
        self.fake.snapshot["permissions"] = PERMISSIONS
        with self.assertLogs(
            "odoo.addons.erplibre_info_git.models.erplibre_code_snapshot", "WARNING"
        ):
            snap = self.Snapshot._capture("manual")
        self.assertIn("chmod -R go+rX", snap.permission_warning)
        self.fake.snapshot["permissions"] = None
        snap = self.Snapshot._capture("manual", force=True)
        self.assertFalse(snap.permission_warning)
