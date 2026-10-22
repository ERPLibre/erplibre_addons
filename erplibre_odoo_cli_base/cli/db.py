# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""ERPLibre's ``db`` command, an extension of Odoo's.

The class inherits Odoo's Db and keeps its name, so registering it replaces
Odoo's command. Odoo's parser still parses load, dump, duplicate and
rename; this class adds create, list, list-incompatible and version,
replaces drop, resolves ``--image`` on load and dump, adds ``--move`` to
load, and checks the master password before ``-f`` deletes an existing
database.
"""

import argparse
import io
import os
import sys
import urllib.parse
import zipfile
from pathlib import Path

import requests
from odoo.cli import db as odoo_db
from odoo.exceptions import AccessDenied
from odoo.service import db as service_db
from odoo.tools import config

from . import _argv, _common

OWN_SUBCOMMANDS = ("create", "list", "list-incompatible", "version", "drop")

IMAGE_HELP = (
    "  --image NAME          ERPLibre: ./image_db/NAME.zip, or a path"
    " (.zip appended)"
)

# Odoo 17's load has no --move: run() takes the flag out of the arguments
# before Odoo's parser sees them, and load() restores accordingly.
MOVE_OPTION = "--move"
MOVE_HELP = (
    "  --move                ERPLibre: restore as a moved database, keeping"
    " its UUID instead of generating a new one"
)


class Db(odoo_db.Db):
    """Create, list, drop, dump, load databases"""

    name = "db"

    # load() restores as a copy (new UUID) unless run() saw --move.
    _copy = True

    def run(self, cmdargs):
        index = _argv.split_subcommand(cmdargs)
        sub = cmdargs[index] if index is not None else None
        if sub in OWN_SUBCOMMANDS:
            args = self._parser().parse_args(cmdargs)
            args.handler(args)
        elif sub in _argv.IMAGE_SUBCOMMANDS:
            head, rest = cmdargs[: index + 1], cmdargs[index + 1 :]
            if sub == "load":
                self._copy = MOVE_OPTION not in rest
                rest = [token for token in rest if token != MOVE_OPTION]
            if "-h" in rest or "--help" in rest:
                try:
                    super().run(head + rest)
                except SystemExit:
                    print(IMAGE_HELP)
                    if sub == "load":
                        print(MOVE_HELP)
                    raise
            try:
                rest = _argv.replace_image_option(sub, rest)
            except ValueError as error:
                _common.fail(f"db {sub}: {error}", code=2)
            super().run(head + rest)
        elif sub is None:
            if "-h" in cmdargs or "--help" in cmdargs:
                self._parser().print_help()
                sys.exit(0)
            self._parser().print_help(sys.stderr)
            sys.exit(1)
        else:
            super().run(cmdargs)

    def _parser(self):
        """Build the parser of the subcommands this class handles.

        load, dump, duplicate and rename appear for the help only: run()
        hands them to Odoo's parser. Global options come before the
        subcommand, as with Odoo: ``db -c FILE list``.
        """
        parser = argparse.ArgumentParser(
            prog=f"{Path(sys.argv[0]).name} {self.name}",
            description=self.__doc__.strip(),
        )
        _common.add_global_options(parser)
        subs = parser.add_subparsers(metavar="SUBCOMMAND")

        create = subs.add_parser(
            "create",
            help="Create and initialize a database.",
            description=(
                "Create a database and initialize it with base. Replaces"
                " the old `db --create --database DB` with --demo,"
                " --user_lang, --user_login, --user_password, --user_phone"
                " and --user_country_code."
            ),
        )
        create.set_defaults(handler=self._create)
        create.add_argument(
            "-f",
            "--force",
            action="store_true",
            help="delete `database` before creating it if it exists, after"
            " checking the master password (MASTER_PWD)",
        )
        create.add_argument(
            "--demo", action="store_true", help="load the demo data"
        )
        create.add_argument(
            "--lang", default="fr_CA", help="language, default fr_CA"
        )
        create.add_argument(
            "--login", default="admin", help="admin login, default admin"
        )
        create.add_argument(
            "--password",
            default="admin",
            help="admin password, default admin",
        )
        create.add_argument("--phone", help="phone of the admin user")
        create.add_argument(
            "--country",
            default="ca",
            help="country code of the main company, default ca",
        )
        create.add_argument("database", help="database to create")

        listing = subs.add_parser(
            "list",
            help="List the databases, one name per line.",
            description=(
                "Print the databases, one name per line on stdout, with"
                " no log line."
            ),
        )
        listing.set_defaults(handler=self._list)

        incompatible = subs.add_parser(
            "list-incompatible",
            help="List the databases of another Odoo version.",
        )
        incompatible.set_defaults(handler=self._list_incompatible)

        version = subs.add_parser("version", help="Print the Odoo version.")
        version.set_defaults(handler=self._version)

        for name, text in (
            (
                "load",
                "Load a dump file; --image NAME loads an image, --move"
                " keeps its UUID.",
            ),
            ("dump", "Create a dump with filestore; --image NAME too."),
            ("duplicate", "Duplicate a database including filestore."),
            ("rename", "Rename a database including filestore."),
        ):
            subs.add_parser(
                name,
                help=f"{text} See `db {name} --help`.",
                add_help=False,
            )

        drop = subs.add_parser(
            "drop",
            help="Delete a database including filestore.",
            description=(
                "Delete a database after checking the master password,"
                " read from the MASTER_PWD environment variable (admin"
                " when unset)."
            ),
        )
        drop.set_defaults(handler=self._drop)
        drop.add_argument(
            "--if-exists",
            action="store_true",
            help="succeed when the database does not exist",
        )
        drop.add_argument("database", help="database to delete")
        return parser

    def _create(self, args):
        _common.parse_odoo_config(args, setup_logging=True)
        config["list_db"] = True
        self._check_target(args.database, delete_if_exists=args.force)
        service_db.exp_create_database(
            args.database,
            args.demo,
            args.lang,
            user_password=args.password,
            login=args.login,
            country_code=args.country,
            phone=args.phone,
        )

    def _list(self, args):
        _common.parse_odoo_config(args, setup_logging=False)
        config["list_db"] = True
        for name in service_db.list_dbs(True):
            print(name)

    def _list_incompatible(self, args):
        _common.parse_odoo_config(args, setup_logging=False)
        config["list_db"] = True
        databases = service_db.list_dbs(True)
        for name in service_db.list_db_incompatible(databases):
            print(name)

    def _version(self, args):
        _common.parse_odoo_config(args, setup_logging=False)
        print(service_db.exp_server_version())

    def _drop(self, args):
        """Drop a database, master password first.

        The password is checked before the existence of the database, so a
        wrong password fails the same way whether the database exists or
        not.
        """
        _common.parse_odoo_config(args, setup_logging=True)
        self._check_master_password()
        config["list_db"] = True
        if service_db.exp_drop(args.database):
            return
        if args.if_exists:
            _common.eprint(
                f"Database {args.database} does not exist, nothing to drop."
            )
            return
        _common.fail(f"Database {args.database} does not exist.")

    def load(self, args):
        """Odoo's load, restoring as a moved database after ``--move``.

        Odoo 17's load always restores as a copy, which gives the database
        a new UUID; the body is Odoo's, with ``copy`` taken from run().
        """
        db_name = args.database or Path(args.dump_file).stem
        self._check_target(db_name, delete_if_exists=args.force)

        url = urllib.parse.urlparse(args.dump_file)
        if url.scheme:
            _common.eprint(f"Fetching {args.dump_file}...", end="")
            response = requests.get(args.dump_file, timeout=10)
            if not response.ok:
                _common.fail(
                    f" unable to fetch {args.dump_file}: {response.reason}"
                )
            _common.eprint(" done")
            dump_file = io.BytesIO(response.content)
        else:
            _common.eprint(f"Restoring {args.dump_file}...")
            dump_file = args.dump_file

        if not zipfile.is_zipfile(dump_file):
            _common.fail(
                "Not a zipped dump file, use `pg_restore` to restore raw"
                " dumps, and `psql` to execute sql dumps or scripts."
            )

        service_db.restore_db(
            db=db_name,
            dump_file=dump_file,
            copy=self._copy,
            neutralize_database=args.neutralize,
        )

    def _check_target(self, target, *, delete_if_exists):
        """Check the master password before ``-f`` deletes ``target``.

        create, load, and Odoo's duplicate and rename, all reach this
        method through ``self``; Odoo's version drops an existing target
        without any password. A target that does not exist, or ``-f`` absent,
        needs no password.
        """
        if delete_if_exists and service_db.exp_db_exist(target):
            self._check_master_password()
        super()._check_target(target, delete_if_exists=delete_if_exists)

    @staticmethod
    def _check_master_password():
        """Exit 1 unless MASTER_PWD (admin when unset) is the master password.

        The password comes from the environment only: an argv option is
        readable by every user of the machine in /proc.
        """
        password = os.environ.get("MASTER_PWD") or "admin"
        try:
            service_db.check_super(password)
        except AccessDenied:
            _common.fail(
                "AccessDenied: the master password is refused;"
                " set MASTER_PWD."
            )
