# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Engine command line: python -m dolibarr_site <command>.

Run with the module folder on PYTHONPATH; it needs neither Odoo nor a
database.
"""

import argparse
import json
import pathlib
import sys

from . import langs, pipeline, zipsource
from .model import Options, SourceError


def _add_choice_options(parser):
    parser.add_argument("--include-page", action="append", default=[])
    parser.add_argument("--skip-page", action="append", default=[])
    parser.add_argument("--include-unlinked-langs", action="store_true")


def _read_zip(path, opts):
    """Bytes of the zip, read under the size limit of the options."""
    limit = zipsource.ZipLimits.from_options(opts.zip_limits).max_total
    return zipsource.read_zip_file(path, limit)


def inspect(args):
    """Print the analysis of a zip as JSON; 1 with one stderr line on error."""
    path = pathlib.Path(args.zip)
    opts = Options(
        filename=path.name,
        langs_dir=args.langs_dir or "",
        include_page_refs=args.include_page,
        skip_page_refs=args.skip_page,
        include_unlinked_langs=args.include_unlinked_langs,
    )
    try:
        site = pipeline.build_from_zip(_read_zip(path, opts), opts)
    except (OSError, SourceError) as exc:
        sys.stderr.write("inspect: %s\n" % exc)
        return 1
    rows = pipeline.analyse(site, opts)
    json.dump(
        {
            "site": site.to_json(),
            "findings": [f.to_json() for f in pipeline.all_findings(site)],
            "pages": [row.to_json() for row in rows],
        },
        sys.stdout,
        indent=1,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m dolibarr_site")
    sub = parser.add_subparsers(dest="command", required=True)
    refresh = sub.add_parser(
        "langs-refresh", help="copy or check the bundled .lang files"
    )
    refresh.add_argument("--htdocs", required=True)
    refresh.add_argument("--check", action="store_true")
    inspect_cmd = sub.add_parser("inspect", help="analyse an export zip")
    inspect_cmd.add_argument("--zip", required=True)
    inspect_cmd.add_argument("--langs-dir", default="")
    _add_choice_options(inspect_cmd)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "langs-refresh":
        return langs.refresh(pathlib.Path(args.htdocs), check=args.check)
    if args.command == "inspect":
        return inspect(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
