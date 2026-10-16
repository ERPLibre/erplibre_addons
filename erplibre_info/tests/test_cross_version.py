# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import copy
import json

from odoo import fields
from odoo.tests import tagged

from .common import CROSS_VERSION, REPO, ErplibreInfoCase


@tagged("post_install", "-at_install")
class TestCrossVersion(ErplibreInfoCase):
    def test_cache(self):
        snap = self.Snapshot._capture("manual")
        line = snap.module_ids.filtered(lambda m: m.name == "erplibre_info")
        self.fake.calls.clear()
        action = line.action_cross_version()
        rec = self.env["erplibre.code.cross.version"].browse(action["res_id"])
        self.assertEqual(
            self.fake.scripts(),
            [
                (
                    "repo_state.py",
                    ["cross-version", REPO, "--module", "erplibre_info"],
                )
            ],
        )
        self.assertEqual(rec.to_port_count, 1)
        self.assertEqual(rec.other_versions, "1.0")
        self.assertIn("1.0.1.0.0", rec.report_html)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", rec.report_html)
        line.action_cross_version()
        self.assertEqual(len(self.fake.calls), 1)
        rec.action_refresh()
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual(self.env["erplibre.code.cross.version"].search_count([]), 1)

    def test_full_diff_on_demand(self):
        rec = self.env["erplibre.code.cross.version"]._fetch(REPO, "erplibre_info")
        self.assertFalse(rec.full_diff)
        self.assertEqual(rec.to_port_count, 1)
        rec.action_load_full_diff()
        self.assertEqual(self.fake.scripts()[-1][1][-1], "--full")
        self.assertIn("diff --git", rec.full_diff)
        # The report comes from the same run as the diff; the patch is
        # stored once, in the full diff.
        self.assertEqual(rec.to_port_count, 0)
        self.assertEqual(json.loads(rec.data_json)["others"][0]["to_port"], [])
        self.assertNotIn("patch", json.loads(rec.data_json)["others"][0]["diff"])

    def test_cache_follows_the_snapshots(self):
        snap = self.Snapshot._capture("manual")
        line = snap.repo_ids.filtered(lambda r: r.path == REPO)
        rec = self.env["erplibre.code.cross.version"].browse(
            line.action_cross_version()["res_id"]
        )
        line.action_cross_version()
        self.assertEqual(len(self.fake.calls), 2)  # snapshot, cross-version
        # The HEAD of the repository moved: a new snapshot, a new report.
        self.fake.snapshot["repos"][0]["head"] = "9" * 40
        self.fake.snapshot["fingerprint"] = "e" * 64
        rec.date = fields.Datetime.subtract(fields.Datetime.now(), hours=1)
        snap2 = self.Snapshot._capture("manual")
        line2 = snap2.repo_ids.filtered(lambda r: r.path == REPO)
        line2.action_cross_version()
        self.assertEqual(len(self.fake.calls), 4)
        # From the last snapshot, a cache newer than it but of another HEAD
        # is read again.
        rec.date = fields.Datetime.add(fields.Datetime.now(), days=1)
        line2.action_cross_version()
        self.assertEqual(len(self.fake.calls), 5)
        # An older snapshot never forces a new read by its HEAD.
        line.action_cross_version()
        self.assertEqual(len(self.fake.calls), 5)

    def test_truncated_file_list(self):
        data = copy.deepcopy(CROSS_VERSION)
        stat = data["others"][0]["diff"]["modules"]["erplibre_info"]
        stat["files"] = 250
        stat["paths_truncated"] = True
        self.fake.answers[("repo_state.py", "cross-version")] = (0, data)
        rec = self.env["erplibre.code.cross.version"]._fetch(REPO)
        self.assertIn("250 files", rec.report_html)
        self.assertIn("1 of 250 files are listed.", rec.report_html)

    def test_repository_without_module(self):
        snap = self.Snapshot._capture("manual")
        line = snap.repo_ids.filtered(lambda r: r.path == REPO)
        line.action_cross_version()
        self.assertEqual(
            self.fake.scripts()[-1], ("repo_state.py", ["cross-version", REPO])
        )
