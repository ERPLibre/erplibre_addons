# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""``module`` command: module operations from the command line."""

import argparse
import logging
import sys
from pathlib import Path

from odoo.cli import Command
from odoo.exceptions import UserError
from odoo.modules.registry import Registry

from . import _common

_logger = logging.getLogger(__name__)


class Module(Command):
    """Uninstall modules with their downstream dependencies"""

    name = "module"

    def run(self, cmdargs):
        parser = argparse.ArgumentParser(
            prog=f"{Path(sys.argv[0]).name} {self.name}",
            description=self.__doc__.strip(),
        )
        subs = parser.add_subparsers(metavar="ACTION")
        uninstall = subs.add_parser(
            "uninstall",
            help="Uninstall modules and every installed module that"
            " depends on them.",
            description=(
                "Uninstall the installed modules of MODULES and their"
                " installed downstream dependencies. Names that are not"
                " installed are skipped."
            ),
        )
        _common.add_global_options(uninstall)
        uninstall.add_argument(
            "-d", "--database", required=True, help="database to change"
        )
        uninstall.add_argument(
            "modules", help="comma-separated module names, like a,b"
        )
        uninstall.set_defaults(handler=self._uninstall)

        args = parser.parse_args(cmdargs)
        if not hasattr(args, "handler"):
            parser.print_help(sys.stderr)
            sys.exit(1)
        args.handler(args)

    def _uninstall(self, args):
        """Mark the modules ``to remove``, commit, then reload the registry.

        Loading the registry with ``update_module`` uninstalls the marked
        modules, as the server's loading does. button_immediate_uninstall
        is not used: it first locks ir_cron with NOWAIT and fails while a
        running server processes a scheduled action on the same database.
        """
        _common.parse_odoo_config(args, setup_logging=True)
        names = [n.strip() for n in args.modules.split(",") if n.strip()]
        with _common.open_env(args.database) as env:
            modules = env["ir.module.module"].search(
                [("name", "in", names), ("state", "=", "installed")]
            )
            if not modules:
                _common.eprint(f"Module(s) not installed: {','.join(names)}")
                return
            _logger.info(
                "Uninstalling modules (including all dependencies"
                " installed) %s",
                (modules + modules.downstream_dependencies()).mapped("name"),
            )
            try:
                modules.button_uninstall()
            except UserError as error:
                _common.fail(str(error.args[0]) if error.args else str(error))
        Registry.new(args.database, update_module=True)
