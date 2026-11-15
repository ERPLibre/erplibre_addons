# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import contextlib
import io
import json
import os
import pathlib
import tempfile
import threading
from unittest import mock

from odoo.exceptions import AccessError, UserError
from odoo.service.model import get_public_method
from odoo.sql_db import db_connect

from ..cli import dolibarr_website_import as command_module
from ..cli.dolibarr_website_import import (
    build_parser,
    check_paths,
    exit_code,
    lock_key,
    run_import,
    vals_from_args,
)
from ..dolibarr_site.model import SourceError
from ..dolibarr_site.tests.fixtures import FILENAME, demo_zip_bytes
from .common import DolibarrImportCase

MODEL = "dolibarr.website.import"


class TestCli(DolibarrImportCase):
    def cli_run(self, **opts):
        values = {
            "website_id": self.website.id,
            "zip_bytes": demo_zip_bytes(),
            "zip_filename": FILENAME,
        }
        values.update(opts)
        run = self.env[MODEL]._create_from_cli(values)
        run._process()
        return run

    def page_exists(self, url):
        return bool(
            self.env["website.page"].search(
                [("website_id", "=", self.website.id), ("url", "=", url)]
            )
        )

    def command(self, *argv):
        return build_parser().parse_args(
            ["-d", "exemple_db", "--website-id", str(self.website.id)]
            + list(argv)
        )

    def invoke(self, *argv):
        """(exit code, stderr) of run_import on the test environment."""
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = run_import(self.env, self.command(*argv))
        return code, errors.getvalue()

    def write_zip(self, folder, name=FILENAME):
        path = pathlib.Path(folder) / name
        path.write_bytes(demo_zip_bytes())
        return str(path)

    def test_parser(self):
        args = build_parser().parse_args(
            [
                "-d", "exemple_db", "--website-id", "3",
                "--zip", "/srv/exports/" + FILENAME,
                "--no-menu", "--keep-scripts",
                "--include-page", "standalone-fr", "--skip-page", "x",
                "--overwrite-local-edits", "--analyse-only",
                "--report-json", "out.json",
            ]
        )  # fmt: skip
        vals = vals_from_args(args)
        self.assertEqual(vals["website_id"], 3)
        self.assertEqual(vals["zip_path"], "/srv/exports/" + FILENAME)
        self.assertFalse(vals["import_menu"])
        self.assertTrue(vals["set_homepage"])
        self.assertTrue(vals["keep_scripts"])
        self.assertEqual(vals["include_page_refs"], ["standalone-fr"])
        self.assertEqual(vals["skip_page_refs"], ["x"])
        self.assertTrue(vals["overwrite_local_edits"] and vals["analyse_only"])

    def test_default_skips_unlinked_pages(self):
        run = self.cli_run()
        self.assertEqual(
            (run.state, run.review_before_import), ("done", False)
        )
        self.assertFalse(self.page_exists("/standalone-fr"))
        self.assertTrue(self.run_lines(run, "foreign_lang_skipped"))
        self.assertEqual(exit_code(run), 0)

    def test_choice_order(self):
        self.cli_run(
            include_unlinked_langs=True, skip_page_refs=["standalone-fr"]
        )
        self.assertFalse(self.page_exists("/standalone-fr"))
        run = self.cli_run(
            include_page_refs=["standalone-fr", "about-fr", "nope"]
        )
        self.assertTrue(self.page_exists("/standalone-fr"))
        ignored = sorted(
            self.run_lines(run, "choice_ignored").mapped("page_ref")
        )
        self.assertEqual(ignored, ["about-fr", "nope"])
        self.assertTrue(self.page_exists("/about"))

    def test_report_dict_and_analyse_only(self):
        run = self.cli_run(analyse_only=True)
        report = run._report_dict()
        self.assertEqual(report["run"]["state"], "done")
        pages = {row["ref"]: row for row in report["pages"]}
        self.assertEqual(pages["standalone-fr"]["status"], "foreign_unlinked")
        self.assertFalse(pages["standalone-fr"]["include"])
        self.assertEqual(
            sorted(pages["about"]),
            sorted(
                [
                    "ref", "lang", "source_url", "target_url", "status",
                    "include", "imported_before", "php_plan",
                    "php_unknown_blocks", "php_removed_bytes", "script_count",
                ]
            ),
        )  # fmt: skip
        self.assertTrue(report["lines"])
        json.dumps(report)
        self.assertFalse(self.page_exists("/about"))

    def test_exit_code_failed(self):
        failed = self.cli_run(zip_bytes=b"not a zip")
        self.assertEqual(failed.state, "failed")
        self.assertEqual(exit_code(failed), 1)

    def test_exit_code_done_and_done_with_errors(self):
        done = self.cli_run(analyse_only=True)
        self.assertEqual(exit_code(done), 0)
        done.line_ids.create(
            {"import_id": done.id, "severity": "error", "code": "page_error"}
        )
        done.invalidate_recordset()
        self.assertEqual(done.state, "done")
        self.assertEqual(exit_code(done), 2)

    def test_lang_defaults_to_website_language(self):
        run = self.env[MODEL]._create_from_cli(
            {
                "website_id": self.website.id,
                "zip_bytes": demo_zip_bytes(),
                "zip_filename": FILENAME,
            }
        )
        self.assertEqual(run.lang, self.website.default_lang_id.code)
        self.assertEqual(run.source_key, "exemplesite")
        self.assertEqual(run.state, "draft")

    def test_zip_path_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.env[MODEL]._create_from_cli(
                {
                    "website_id": self.website.id,
                    "zip_path": self.write_zip(tmp),
                }
            )
        self.assertEqual(run.zip_filename, FILENAME)
        self.assertEqual(run.source_key, "exemplesite")

    def test_zip_path_refuses_non_regular_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            fifo = os.path.join(tmp, "pipe.zip")
            os.mkfifo(fifo)
            for path in (fifo, tmp, "/dev/null"):
                with self.assertRaises(SourceError, msg=path) as caught:
                    self.env[MODEL]._create_from_cli(
                        {
                            "website_id": self.website.id,
                            "zip_path": path,
                            "source_key": "exemplesite",
                        }
                    )
                self.assertIn("regular file", str(caught.exception))

    def test_zip_path_over_limit_is_refused(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "erplibre_website_import_from_dolibarr.zip_max_total", "1000"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_zip(tmp)
            with self.assertRaises(SourceError) as caught:
                self.env[MODEL]._create_from_cli(
                    {"website_id": self.website.id, "zip_path": path}
                )
        self.assertIn("limit", str(caught.exception))

    def test_zip_path_read_is_bounded(self):
        """A file that grows after its stat is still cut at limit + 1."""
        self.env["ir.config_parameter"].sudo().set_param(
            "erplibre_website_import_from_dolibarr.zip_max_total", "1000"
        )
        real_stat = os.stat
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_zip(tmp)

            def small(name, *a, **kw):
                info = real_stat(name, *a, **kw)
                if str(name) == path:
                    return os.stat_result((info.st_mode,) + (0,) * 9)
                return info

            with mock.patch("os.stat", small):
                with self.assertRaises(SourceError) as caught:
                    self.env[MODEL]._create_from_cli(
                        {"website_id": self.website.id, "zip_path": path}
                    )
        self.assertIn("over the 1000-byte limit", str(caught.exception))

    def test_create_from_cli_sets_no_state(self):
        Run = type(self.env[MODEL])
        with mock.patch.object(Run, "_set_state", autospec=True) as spy:
            run = self.env[MODEL]._create_from_cli(
                {
                    "website_id": self.website.id,
                    "zip_bytes": demo_zip_bytes(),
                    "zip_filename": FILENAME,
                }
            )
        spy.assert_not_called()
        self.assertEqual(run.state, "draft")
        with self.assertRaises(UserError):
            run.write({"state": "running"})

    def test_run_import_sets_state_through_set_state(self):
        Run = type(self.env[MODEL])
        real = Run._set_state
        seen = []

        def spy(run, vals):
            seen.append(vals.get("state"))
            return real(run, vals)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(Run, "_set_state", spy):
                code, err = self.invoke("--zip", self.write_zip(tmp))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(seen[0], "running")
        self.assertEqual(seen[-1], "done")

    def test_cli_private_methods_are_not_remote(self):
        for name in ("_create_from_cli", "_report_dict"):
            with self.assertRaises(AccessError, msg=name):
                get_public_method(self.env[MODEL], name)

    def test_create_from_cli_needs_admin_without_su(self):
        user = self.env["res.users"].create(
            {"name": "Example Plain", "login": "example_plain"}
        )
        with self.assertRaises(AccessError):
            self.env[MODEL].with_user(user)._create_from_cli(
                {
                    "website_id": self.website.id,
                    "zip_bytes": demo_zip_bytes(),
                    "zip_filename": FILENAME,
                }
            )

    def test_run_import_exit_codes_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = os.path.join(tmp, "report.json")
            code, err = self.invoke(
                "--zip", self.write_zip(tmp), "--analyse-only",
                "--report-json", report,
            )  # fmt: skip
            self.assertEqual((code, err), (0, ""))
            data = json.loads(pathlib.Path(report).read_text("utf-8"))
            self.assertEqual(data["run"]["state"], "done")
            self.assertTrue(data["pages"])
            bad = pathlib.Path(tmp) / "bad.zip"
            bad.write_bytes(b"not a zip")
            code, err = self.invoke(
                "--zip", str(bad), "--source-key", "exemplesite"
            )
            self.assertEqual(code, 1)
            self.assertEqual(len(err.splitlines()), 1)
            self.assertIn("SourceError", err)
            self.assertNotIn("Traceback", err)
            run = self.env[MODEL].search([], limit=1)
            self.assertEqual(run.state, "failed")
            self.assertEqual(exit_code(run), 1)

    def test_run_import_done_with_error_lines_is_2(self):
        Run = type(self.env[MODEL])
        real = Run._process

        def process(run, budget=None):
            result = real(run, budget)
            run.line_ids.create(
                {
                    "import_id": run.id,
                    "severity": "error",
                    "code": "page_error",
                }
            )
            return result

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(Run, "_process", process):
                code, err = self.invoke(
                    "--zip", self.write_zip(tmp), "--analyse-only"
                )
        self.assertEqual((code, err), (2, ""))

    def test_errors_are_one_masked_line_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.mkfifo(os.path.join(tmp, "pipe.zip"))
            cases = [
                (os.path.join(tmp, "pipe.zip"), "regular file"),
                (os.path.join(tmp, "absent.zip"), "FileNotFoundError"),
            ]
            for zip_path, needle in cases:
                code, err = self.invoke(
                    "--zip", zip_path, "--source-key", "exemplesite"
                )
                self.assertEqual(code, 1, zip_path)
                self.assertEqual(len(err.splitlines()), 1, err)
                self.assertNotIn("Traceback", err)
                self.assertIn(needle, err)

    def test_error_line_masks_secrets(self):
        with mock.patch.object(
            type(self.env[MODEL]),
            "_create_from_cli",
            side_effect=UserError(
                "failed, token=abc123 for https://u:pw@host/x"
            ),
        ):
            code, err = self.invoke("--zip", "unused.zip")
        self.assertEqual(code, 1)
        self.assertNotIn("abc123", err)
        self.assertNotIn("u:pw", err)
        self.assertIn("token=***", err)

    def test_unknown_website_and_bad_key_exit_1(self):
        args = build_parser().parse_args(
            ["-d", "x", "--website-id", "999999", "--zip", "unused.zip"]
        )
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(run_import(self.env, args), 1)
        self.assertIn("not found", errors.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_zip(tmp)
            code, err = self.invoke("--zip", path, "--source-key", "bad key!")
        self.assertEqual(code, 1)
        self.assertIn("Invalid source key", err)

    def test_langs_dir_reaches_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            Run = type(self.env[MODEL])
            contexts = []
            real = Run._process

            def process(run, budget=None):
                contexts.append(run.env.context.get("dolibarr_langs_dir"))
                return real(run, budget)

            with mock.patch.object(Run, "_process", process):
                code, _err = self.invoke(
                    "--zip", self.write_zip(tmp), "--analyse-only",
                    "--langs-dir", tmp,
                )  # fmt: skip
        self.assertEqual((code, contexts), (0, [tmp]))

    def test_run_import_names_the_database_of_the_thread(self):
        """The routing map needs the thread's dbname, as odoo shell sets."""
        Run = type(self.env[MODEL])
        seen = []
        real = Run._process
        thread = threading.current_thread()

        def process(run, budget=None):
            seen.append(getattr(thread, "dbname", None))
            return real(run, budget)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(Run, "_process", process):
                with mock.patch.object(thread, "dbname", "other", create=True):
                    self.invoke("--zip", self.write_zip(tmp), "--analyse-only")
        self.assertEqual(seen, [self.env.cr.dbname])

    def test_unexpected_routing_error_fails_the_run_without_hanging(self):
        """Only NotFound reads as "no route"; any other error propagates."""
        Http = type(self.env["ir.http"])
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                Http, "routing_map", side_effect=RuntimeError("no map")
            ):
                code, err = self.invoke("--zip", self.write_zip(tmp))
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn("RuntimeError", err)
        run = self.env[MODEL].search([], limit=1)
        self.assertEqual(run.state, "failed")
        self.assertFalse(self.page_exists("/about"))

    def test_every_candidate_taken_skips_the_page_and_finishes(self):
        Run = type(self.env[MODEL])
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(Run, "_path_taken", return_value=True):
                code, err = self.invoke("--zip", self.write_zip(tmp))
        run = self.env[MODEL].search([], limit=1)
        self.assertEqual((run.state, err), ("done", ""))
        self.assertEqual(code, 2)
        errors = self.run_lines(run, "page_error")
        self.assertTrue(errors)
        self.assertIn("No free URL", errors[0].detail or errors[0].message)
        self.assertFalse(self.page_exists("/about"))
        self.assertFalse(
            run.page_ids.filtered(lambda r: r.ref == "about").target_url
        )

    def test_inactive_language_is_one_line_and_stores_no_run(self):
        before = self.env[MODEL].search_count([])
        with tempfile.TemporaryDirectory() as tmp:
            code, err = self.invoke(
                "--zip", self.write_zip(tmp), "--lang", "xx_XX"
            )
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn("xx_XX", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(self.env[MODEL].search_count([]), before)

    def test_no_exception_escapes_the_run(self):
        Run = type(self.env[MODEL])
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                Run, "_run_inline", side_effect=RuntimeError("boom")
            ):
                code, err = self.invoke("--zip", self.write_zip(tmp))
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn("RuntimeError", err)

    def test_lock_key_is_stable_and_per_site_and_key(self):
        key = lock_key(1, "exemplesite")
        self.assertEqual(key, lock_key(1, "exemplesite"))
        self.assertNotEqual(key, lock_key(2, "exemplesite"))
        self.assertNotEqual(key, lock_key(1, "autresite"))
        self.assertTrue(-(2**63) <= key < 2**63)

    def test_second_run_of_a_site_is_refused(self):
        key = lock_key(self.website.id, "exemplesite")
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_zip(tmp)
            holder = db_connect(self.env.cr.dbname).cursor()
            try:
                holder.execute("SELECT pg_advisory_lock(%s)", [key])
                code, err = self.invoke("--zip", path)
                holder.execute("SELECT pg_advisory_unlock(%s)", [key])
            finally:
                holder.close()
            self.assertEqual(code, 1)
            self.assertEqual(
                err,
                "dolibarr_website_import: another import of this site"
                " is running\n",
            )
            code, err = self.invoke("--zip", path, "--analyse-only")
        self.assertEqual((code, err), (0, ""))

    def test_refused_lock_creates_no_run(self):
        before = self.env[MODEL].search_count([])
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                command_module, "_try_lock", return_value=False
            ):
                code, err = self.invoke("--zip", self.write_zip(tmp))
        self.assertEqual(code, 1)
        self.assertIn("another import", err)
        self.assertEqual(self.env[MODEL].search_count([]), before)

    def test_report_path_is_a_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.command("--zip", "z.zip", "--report-json", tmp)
            with self.assertRaises(SystemExit) as caught:
                check_paths(build_parser(), args)
        self.assertEqual(caught.exception.code, 1)

    def test_report_write_failure_keeps_the_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = os.path.join(tmp, "absent", "report.json")
            code, err = self.invoke(
                "--zip", self.write_zip(tmp), "--analyse-only",
                "--report-json", report,
            )  # fmt: skip
        self.assertEqual(code, 0)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn("warning: report not written", err)

    def test_usage_errors_exit_1(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            with self.assertRaises(SystemExit) as caught:
                build_parser().parse_args([])
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("error:", errors.getvalue())

    def test_missing_source_key_points_to_the_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, err = self.invoke("--zip", self.write_zip(tmp, "export.zip"))
        self.assertEqual(code, 1)
        self.assertIn("--source-key", err)
        self.assertIn("carries no source key", err)
        self.assertNotIn("***", err)

    def test_thread_dbname_is_restored(self):
        thread = threading.current_thread()
        saved = getattr(thread, "dbname", None)
        self.addCleanup(setattr, thread, "dbname", saved)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_zip(tmp)
            thread.dbname = "before"
            self.invoke("--zip", path, "--analyse-only")
            self.assertEqual(thread.dbname, "before")
            del thread.dbname
            self.invoke("--zip", path, "--analyse-only")
        self.assertFalse(hasattr(thread, "dbname"))
