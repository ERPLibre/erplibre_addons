# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""odoo-bin dolibarr_website_import: import a Dolibarr export zip.

Odoo imports odoo.addons.<module> for the addons that have a cli/ folder,
which registers this command. It analyses, applies the page choices given
as options and imports in one process, as superuser and without a time
budget, then commits once. Exit code: 0 done, 2 done with error lines,
1 failed. A failure before or outside the run prints one masked line on
stderr, without traceback, and exits 1.

No option carries a secret, so argv holds none. In odoo shell the same
import runs with
env["dolibarr.website.import"]._create_from_cli(opts), then
_set_state({"state": "running"}) and _process().
"""

import argparse
import hashlib
import json
import os
import pathlib
import sys
import threading

import odoo
from odoo.cli import Command
from odoo.fields import Datetime
from odoo.modules.registry import Registry
from odoo.tools import config

from ..dolibarr_site import zipsource
from ..models.dolibarr_website_import import error_text


class _Parser(argparse.ArgumentParser):
    """Usage errors exit 1, like every other failure of the command."""

    def error(self, message):
        self.exit(1, "%s: error: %s\n" % (self.prog, message))


def build_parser():
    parser = _Parser(
        prog="odoo-bin dolibarr_website_import",
        description="Import a Dolibarr website export zip into a website.",
        allow_abbrev=False,
    )
    parser.add_argument("-d", "--database", required=True)
    parser.add_argument("--website-id", type=int, required=True)
    parser.add_argument("--zip", required=True)
    parser.add_argument("--source-key", default="")
    parser.add_argument("--lang", default="")
    parser.add_argument("--langs-dir", default="")
    parser.add_argument("--blog-name", default="Blog")
    parser.add_argument("--no-menu", action="store_true")
    parser.add_argument("--no-homepage", action="store_true")
    parser.add_argument("--no-style-blog-posts", action="store_true")
    parser.add_argument("--keep-scripts", action="store_true")
    parser.add_argument("--max-media", type=int, default=2000)
    parser.add_argument("--include-page", action="append", default=[])
    parser.add_argument("--skip-page", action="append", default=[])
    parser.add_argument("--include-unlinked-langs", action="store_true")
    parser.add_argument("--overwrite-local-edits", action="store_true")
    parser.add_argument("--analyse-only", action="store_true")
    parser.add_argument("--report-json", default="")
    return parser


def vals_from_args(args):
    """The opts dict of dolibarr.website.import._create_from_cli."""
    return {
        "website_id": args.website_id,
        "zip_path": args.zip,
        "source_key": args.source_key,
        "lang": args.lang,
        "blog_name": args.blog_name,
        "import_menu": not args.no_menu,
        "set_homepage": not args.no_homepage,
        "style_blog_posts": not args.no_style_blog_posts,
        "keep_scripts": args.keep_scripts,
        "max_media": args.max_media,
        "include_page_refs": list(args.include_page),
        "skip_page_refs": list(args.skip_page),
        "include_unlinked_langs": args.include_unlinked_langs,
        "overwrite_local_edits": args.overwrite_local_edits,
        "analyse_only": args.analyse_only,
    }


def exit_code(run):
    """1 failed, 2 done with error lines, 0 done."""
    if run.state == "failed":
        return 1
    return 2 if run.error_count else 0


def _fail_line(exc):
    """The one stderr line of an error; the text is masked."""
    sys.stderr.write("dolibarr_website_import: %s\n" % error_text(exc))
    return 1


def lock_key(website_id, source_key):
    """Signed 64-bit advisory lock key of a (website, source key) pair."""
    digest = hashlib.sha256(
        ("%d:%s" % (website_id, source_key)).encode()
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _try_lock(env, key):
    """Take the transaction-scoped advisory lock; False when it is held.

    The lock lives until the transaction ends, so two commands on the
    same (website, source key) cannot both run: a run set to running in
    an uncommitted transaction is invisible to the other process.
    """
    env.cr.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
    return bool(env.cr.fetchone()[0])


def _source_key(args):
    return args.source_key or zipsource.key_from_filename(
        os.path.basename(args.zip)
    )


def _warn(text):
    sys.stderr.write("dolibarr_website_import: warning: %s\n" % text)


def check_paths(parser, args):
    """Refuse the option paths that cannot work, before any import."""
    if args.langs_dir and not os.path.isdir(args.langs_dir):
        parser.error("--langs-dir is not a directory")
    if args.report_json:
        if os.path.isdir(args.report_json):
            parser.error("--report-json is a directory")
        folder = os.path.dirname(os.path.abspath(args.report_json))
        if not os.access(folder, os.W_OK):
            parser.error("--report-json folder is not writable")


def run_import(env, args, commit=None):
    """Create, run and report; returns the exit code.

    env is a superuser environment. commit, when given, is called once
    after the run ends, failed or not; a run that could not be created,
    or that another run of the same key blocks, is never committed. Any
    error outside the run prints one masked line on stderr and gives 1.
    A report that cannot be written only warns: the exit code stays the
    run's own.
    """
    # The routing map, which the writer reads to keep a page off a
    # controller route, finds its registry through this thread attribute.
    thread = threading.current_thread()
    missing = object()
    previous = getattr(thread, "dbname", missing)
    thread.dbname = env.cr.dbname
    try:
        return _run_import(env, args, commit)
    finally:
        if previous is missing:
            del thread.dbname
        else:
            thread.dbname = previous


def _run_import(env, args, commit):
    model = env["dolibarr.website.import"]
    if args.langs_dir:
        model = model.with_context(dolibarr_langs_dir=args.langs_dir)
    key = _source_key(args)
    try:
        if key and not _try_lock(env, lock_key(args.website_id, key)):
            sys.stderr.write(
                "dolibarr_website_import: another import of this site"
                " is running\n"
            )
            return 1
        run = model._create_from_cli(vals_from_args(args))
        run._check_no_running_other()
        run._set_state({"state": "running", "date_start": Datetime.now()})
        run._run_inline(None)
    except Exception as exc:
        return _fail_line(exc)
    code = exit_code(run)
    if code == 1:
        sys.stderr.write(
            "dolibarr_website_import: %s\n"
            % (run.error or "failed").splitlines()[0]
        )
    if commit:
        commit()
    if args.report_json:
        try:
            pathlib.Path(args.report_json).write_text(
                json.dumps(run._report_dict(), indent=1, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            _warn("report not written: %s" % error_text(exc))
    return code


class DolibarrWebsiteImport(Command):
    """Import a Dolibarr website export zip into an Odoo website"""

    name = "dolibarr_website_import"

    def run(self, cmdargs):
        parser = build_parser()
        args, rest = parser.parse_known_args(cmdargs)
        check_paths(parser, args)
        config.parse_config(
            rest + ["--database", args.database], setup_logging=True
        )
        registry = Registry(args.database)
        with registry.cursor() as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            code = run_import(env, args, commit=cr.commit)
            cr.rollback()
        sys.exit(code)
