# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import collections
import hashlib
import itertools
from unittest import mock

from odoo.exceptions import UserError

from ..dolibarr_site import pipeline
from ..dolibarr_site.model import PageError, SourceError
from ..dolibarr_site.tests.fixtures import demo_zip_bytes
from ..models import dolibarr_website_import as run_module
from ..models import dolibarr_website_import_writer as writer_module
from ..models.dolibarr_website_import import error_text
from .common import DolibarrImportCase

# Invented secrets, each after a form that error_text() must mask.
SECRET_PROBES = (
    ("PGPASSWORD=example-a1", "example-a1"),
    ("db_password=example-b2", "example-b2"),
    ("access_token=example-c3", "example-c3"),
    ("Authorization: Bearer example-d4", "example-d4"),
    ("authorization: Basic example-e5", "example-e5"),
    ('password="example-f6 more-f6"', "more-f6"),
    ("api_key: 'example-g7 more-g7'", "more-g7"),
    ("https://example-h8@dolibarr.example.test/x", "example-h8"),
    ("https://user:example-i9@x@dolibarr.example.test/", "example-i9"),
)


class TestProcess(DolibarrImportCase):
    def counts(self):
        domain = [("website_id", "=", self.website.id)]
        return (
            self.env["website.page"].search_count(domain),
            self.env["blog.post"].search_count(domain),
            self.env["ir.attachment"].search_count(domain),
            self.env["website.menu"].search_count(domain),
        )

    def rows(self, run):
        return {row.ref: row for row in run.page_ids}

    def test_analysis_stops_for_review_and_writes_nothing(self):
        before = self.counts()
        run = self.make_run(review_before_import=True)
        run.action_start()
        self.assertEqual(run.state, "to_review")
        self.assertEqual(self.counts(), before)
        rows = self.rows(run)
        self.assertEqual(
            (rows["standalone-fr"].status, rows["standalone-fr"].include),
            ("foreign_unlinked", False),
        )
        self.assertEqual(rows["about-fr"].status, "translation")
        self.assertEqual(rows["legacy"].php_plan, "remove")
        self.assertGreater(rows["legacy"].php_removed_bytes, 0)
        self.assertEqual(rows["blog"].target_url, "/blog-page")
        self.assertTrue(
            run.message_ids.filtered(
                lambda m: "Analysis finished" in (m.body or "")
            )
        )
        self.assertEqual(
            (run.dolibarr_version, run.main_lang), ("24.0.1", "en")
        )

    def test_import_after_review_applies_choices(self):
        run = self.make_run(review_before_import=True)
        run.action_start()
        self.rows(run)["standalone-fr"].include = True
        run.action_import()
        self.assertEqual(run.state, "done")
        self.assertTrue(run.import_done)
        self.assertTrue(
            self.env["website.page"].search(
                [
                    ("website_id", "=", self.website.id),
                    ("url", "=", "/standalone-fr"),
                ]
            )
        )
        self.assertTrue(self.run_lines(run, "foreign_lang_page"))

    def test_cli_style_run_imports_in_one_call(self):
        run = self.make_run()
        self.assertEqual(run.with_context(lang="en_US")._process(), (1, 0))
        self.assertEqual(run.state, "done")
        self.assertTrue(self.run_lines(run, "foreign_lang_skipped"))
        self.assertFalse(
            self.env["website.page"].search(
                [
                    ("url", "=", "/standalone-fr"),
                    ("website_id", "=", self.website.id),
                ]
            )
        )

    def test_analyse_only(self):
        before = self.counts()
        run = self.make_run(analyse_only=True)
        run._process()
        self.assertEqual((run.state, run.import_done), ("done", False))
        self.assertEqual(self.counts(), before)

    def test_budget_resumes(self):
        run = self.make_run()
        self.assertEqual(run._process(budget=0), (0, 1))
        self.assertEqual((run.state, run.phase), ("draft", "import"))
        self.assertEqual(run._process(), (1, 0))
        self.assertEqual(run.state, "done")
        self.assertEqual(len(self.run_lines(run, "footer_not_imported")), 1)

    def test_concurrency(self):
        self.make_run(state="running")
        with self.assertRaises(UserError):
            self.make_run().action_start()

    def test_source_error(self):
        run = self.make_run(zip_bytes=b"not a zip")
        run.action_start()
        self.assertEqual(run.state, "failed")
        self.assertTrue(self.run_lines(run, "source_error"))

    def test_zip_changed_since_analysis(self):
        run = self.make_run(review_before_import=True)
        run.action_start()
        run.zip_sha256 = "0" * 64
        run.action_import()
        self.assertEqual(run.state, "failed")

    def test_reimport_copies_choices_and_resets_options(self):
        run = self.make_run(
            review_before_import=True, overwrite_local_edits=True
        )
        run.action_start()
        self.rows(run)["standalone-fr"].include = True
        run.action_import()
        action = run.action_reimport()
        new = self.env["dolibarr.website.import"].browse(action["res_id"])
        self.assertEqual(new.state, "to_review")
        self.assertFalse(new.overwrite_local_edits)
        self.assertFalse(new.keep_scripts)
        self.assertEqual(new._refs(new.include_page_refs), ["standalone-fr"])
        row = self.rows(new)["standalone-fr"]
        self.assertTrue(row.include and row.imported_before)

    def test_keep_scripts_changes_only_in_review(self):
        run = self.make_run()
        with self.assertRaises(UserError):
            run.keep_scripts = True
        self.set_state(run, "to_review")
        run.keep_scripts = True
        self.assertTrue(run.keep_scripts)

    def test_keep_scripts_may_be_set_at_creation(self):
        self.assertTrue(self.make_run(keep_scripts=True).keep_scripts)

    def test_budget_stop_is_kept_and_resumed(self):
        run = self.make_run()
        self.set_state(run, "running")
        clock = itertools.count()
        fake_time = mock.Mock(monotonic=lambda: float(next(clock)))
        with mock.patch.object(
            run_module, "time", fake_time
        ), mock.patch.object(writer_module, "time", fake_time):
            self.assertEqual(run._run_inline(3), (0, 1))
        self.assertEqual((run.state, run.phase), ("running", "import"))
        maps = self.env["dolibarr.website.import.map"].search(
            [("website_id", "=", self.website.id)]
        )
        self.assertTrue(maps.filtered(lambda line: line.kind == "media"))
        for line in maps:
            record = self.env[line.res_model].browse(line.res_id)
            self.assertTrue(record.exists(), line.ref)
        media = self.env["ir.attachment"].search(
            [
                ("website_id", "=", self.website.id),
                ("url", "=like", "/medias/%"),
            ]
        )
        self.assertEqual(
            set(media.ids),
            set(
                maps.filtered(lambda line: line.kind == "media").mapped(
                    "res_id"
                )
            ),
        )
        run.action_resume()
        self.assertEqual(run.state, "done")
        again = self.env["ir.attachment"].search(
            [
                ("website_id", "=", self.website.id),
                ("url", "=like", "/medias/%"),
            ]
        )
        self.assertEqual(again & media, media)
        self.assertEqual(len(self.run_lines(run, "footer_not_imported")), 1)

    def test_inline_failure_keeps_a_short_message(self):
        run = self.make_run(review_before_import=True)
        original = type(run)._run_analyse

        def broken(self):
            original(self)
            raise RuntimeError(
                "boom password=example-secret"
                " https://user:example-pass@dolibarr.example.test/\n"
                "Traceback (most recent call last):\n  File x"
            )

        with mock.patch.object(
            type(run), "_run_analyse", broken
        ), self.assertLogs(run_module._logger.name, "ERROR") as logs:
            run.action_start()
        self.assertIn("Traceback", logs.output[0])
        self.assertEqual(run.state, "failed")
        self.assertIn("RuntimeError: boom", run.error)
        for text in ("example-secret", "example-pass", "Traceback"):
            self.assertNotIn(text, run.error)
            self.assertNotIn(text, self.run_lines(run, "run_error").message)
        self.assertFalse(self.run_lines(run, "source_error"))
        self.assertFalse(run.page_ids)

    def test_import_is_refused_while_another_run_is_running(self):
        run = self.make_run(review_before_import=True)
        run.action_start()
        self.make_run(state="running")
        with self.assertRaises(UserError):
            run.action_import()
        self.assertEqual(run.state, "to_review")

    def test_other_key_or_website_does_not_block(self):
        other = self.env["website"].create({"name": "Other site"})
        self.make_run(state="running", source_key="othersite")
        self.make_run(state="running", website_id=other.id)
        run = self.make_run(review_before_import=True)
        run.action_start()
        self.assertEqual(run.state, "to_review")

    def test_reanalysis_recreates_the_rows(self):
        run = self.make_run(review_before_import=True)
        run.action_start()
        row = self.rows(run)["standalone-fr"]
        row.include = True
        self.set_state(run, "failed")
        run.action_resume()
        self.assertEqual(run.state, "to_review")
        self.assertFalse(row.exists())
        self.assertFalse(self.rows(run)["standalone-fr"].include)

    def test_cancelled_review_resumes_to_review(self):
        run = self.make_run(review_before_import=True)
        run.action_start()
        rows = run.page_ids
        run.action_cancel()
        self.assertEqual(run.state, "cancelled")
        run.action_resume()
        self.assertEqual(run.state, "to_review")
        self.assertEqual(run.page_ids, rows)

    def test_failed_import_resumes_with_the_same_choices(self):
        run = self.make_run(review_before_import=True)
        run.action_start()
        self.rows(run)["standalone-fr"].include = True
        digest = run.zip_sha256
        run.zip_sha256 = "0" * 64
        run.action_import()
        self.assertEqual((run.state, run.phase), ("failed", "import"))
        run.zip_sha256 = digest
        run.action_resume()
        self.assertEqual(run.state, "done")
        self.assertTrue(self.run_lines(run, "foreign_lang_page"))

    def test_site_level_findings(self):
        def broken(*args, **kwargs):
            raise PageError("htmlheader.html", "site head too large")

        run = self.make_run()
        with mock.patch.object(pipeline.html2arch, "head_arch", broken):
            self.assertEqual(run._process(), (1, 0))
        refs = set(run.page_ids.mapped("ref"))
        error = self.run_lines(run, "page_error").filtered(
            lambda line: line.page_ref == "htmlheader.html"
        )
        self.assertTrue(error)
        self.assertFalse(error.res_id)
        self.assertNotIn("htmlheader.html", refs)
        layout = self.run_lines(run, "layout_detected")
        self.assertTrue(layout)
        self.assertFalse(any(layout.mapped("page_ref")))
        self.assertFalse(any(layout.mapped("res_id")))

    def test_language_mismatch(self):
        run = self.make_run(analyse_only=True)
        run._process()
        self.assertFalse(self.run_lines(run, "language_mismatch"))
        french = self.env["res.lang"]._activate_lang("fr_FR")
        self.website.write(
            {"language_ids": [(4, french.id)], "default_lang_id": french.id}
        )
        run = self.make_run(analyse_only=True)
        run._process()
        line = self.run_lines(run, "language_mismatch")
        self.assertEqual(len(line), 1)
        self.assertFalse(line.page_ref)

    def test_open_actions(self):
        run = self.make_run()
        run._process()
        website = run.action_open_website()
        self.assertEqual(
            website["url"],
            self.website.get_base_url() + self.website.homepage_url,
        )
        blog = run.action_open_blog()
        self.assertTrue(blog["url"].startswith(self.website.get_base_url()))
        self.assertIn("/blog/", blog["url"])
        self.assertEqual(run._form_action()["res_id"], run.id)

    def codes(self, run):
        return collections.Counter(run.line_ids.mapped("code"))

    def test_split_run_reports_like_one_batch(self):
        whole = self.make_run()
        self.assertEqual(whole._process(), (1, 0))
        other = self.env["website"].create(
            {"name": "Other site", "company_id": self.company.id}
        )
        split = self.make_run(website_id=other.id)
        results = [split._process(budget=0)]
        while results[-1] == (0, 1) and len(results) < 100:
            results.append(split._process(budget=0))
        self.assertEqual(results[-1], (1, 0))
        self.assertEqual(split.state, "done")
        self.assertGreater(len(results), 2)
        written = self.env["dolibarr.website.import.map"].search_count(
            [("website_id", "=", other.id)]
        )
        self.assertLessEqual(len(results), written + 1)
        self.assertIn("url_conflict", self.codes(split))
        self.assertEqual(self.codes(split), self.codes(whole))

    def test_start_is_refused_unless_draft(self):
        run = self.make_run()
        run._process()
        lines = run.line_ids
        with self.assertRaises(UserError):
            run.action_start()
        self.assertEqual((run.state, run.line_ids), ("done", lines))
        stopped = self.make_run(state="running", source_key="othersite")
        with self.assertRaises(UserError):
            stopped.action_start()

    def test_error_text_masks_secrets(self):
        for text, secret in SECRET_PROBES:
            out = error_text(RuntimeError("fail " + text))
            self.assertNotIn(secret, out, text)
            self.assertTrue(out.startswith("RuntimeError: fail "), out)
            if "://" in text:
                self.assertIn("dolibarr.example.test", out)

    def test_error_text_keeps_the_class_name_readable(self):
        self.assertEqual(error_text(KeyError("arch")), "KeyError: 'arch'")
        self.assertEqual(
            error_text(KeyError("token=abc")), "KeyError: 'token=***"
        )

    def test_changed_zip_points_to_reimport_or_start_over(self):
        run = self.make_run()
        run._zip_bytes(analyse=True)
        run.zip_file = base64.b64encode(demo_zip_bytes() + b"x")
        with self.assertRaises(SourceError) as caught:
            run._zip_bytes()
        self.assertIn("Reimport", str(caught.exception))
        self.assertIn("Start over", str(caught.exception))

    def test_source_error_text_is_masked(self):
        run = self.make_run()
        with mock.patch.object(
            pipeline,
            "build_from_zip",
            side_effect=run_module.SourceError("bad password=example-j0"),
        ):
            run._process()
        self.assertEqual(run.state, "failed")
        self.assertNotIn("example-j0", run.error)
        self.assertNotIn(
            "example-j0", self.run_lines(run, "source_error").message
        )

    def test_replaced_zip_is_analysed_again(self):
        run = self.make_run(zip_bytes=b"not a zip", review_before_import=True)
        run.action_start()
        self.assertEqual(run.state, "failed")
        data = demo_zip_bytes()
        run.zip_file = base64.b64encode(data)
        run.action_resume()
        self.assertEqual(run.state, "to_review")
        self.assertEqual(run.zip_sha256, hashlib.sha256(data).hexdigest())

    def test_state_is_set_by_the_actions_only(self):
        run = self.make_run()
        with self.assertRaises(UserError):
            run.write({"state": "to_review"})
        with self.assertRaises(UserError):
            run.keep_scripts = True
        with self.assertRaises(UserError):
            self.env["dolibarr.website.import"].create(
                {
                    "website_id": self.website.id,
                    "source_key": "exemplesite",
                    "state": "done",
                }
            )
        run.write({"state": "draft"})
        self.assertEqual(run.state, "draft")
