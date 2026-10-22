# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""ERPLibre's ``db`` command, an extension of Odoo's.

The class inherits Odoo's Db and keeps its name, so registering it replaces
Odoo's command. Odoo's parser still parses load, dump, duplicate and
rename; this class adds create, list, list-incompatible and version,
replaces drop, resolves ``--image`` on load and dump, and checks the master
password before ``-f`` deletes an existing database.
"""

import argparse
import os
import sys
from pathlib import Path

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


class Db(odoo_db.Db):
    """Create, list, drop, dump, load databases"""

    name = "db"

    def run(self, cmdargs):
        index = _argv.split_subcommand(cmdargs)
        sub = cmdargs[index] if index is not None else None
        if sub in OWN_SUBCOMMANDS:
            args = self._parser().parse_args(cmdargs)
            args.handler(args)
        elif sub in _argv.IMAGE_SUBCOMMANDS:
            head, rest = cmdargs[: index + 1], cmdargs[index + 1 :]
            if "-h" in rest or "--help" in rest:
                try:
                    super().run(cmdargs)
                except SystemExit:
                    print(IMAGE_HELP)
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
            ("load", "Load a dump file; --image NAME loads an image."),
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

    def _check_target(self, target, *, delete_if_exists):
        """Check the master password before ``-f`` deletes ``target``.

        create, and Odoo's load, duplicate and rename, all reach this
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
