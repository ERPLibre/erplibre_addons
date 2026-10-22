# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Odoo-dependent helpers shared by the commands of this module.

Exit codes of every command: 0 success, 1 operational failure (message on
stderr), 2 usage error (argparse).
"""

import contextlib
import sys
import threading
from functools import partial

from odoo import SUPERUSER_ID, api
from odoo.modules.registry import Registry
from odoo.tools import config

eprint = partial(print, file=sys.stderr, flush=True)

# Argument dests forwarded to config.parse_config, as Odoo's Db.run does.
# The commands' own dests never take these names nor the db_/pg_ prefixes.
_FORWARDED_DESTS = {
    "config": "--config",
    "data_dir": "--data-dir",
    "addons_path": "--addons-path",
}


def add_global_options(parser):
    """Declare on ``parser`` the connection options of Odoo's ``db``."""
    parser.add_argument("-c", "--config", help="configuration file")
    parser.add_argument("-D", "--data-dir", help="filestore root")
    parser.add_argument("--addons-path", help="addons paths, comma-separated")
    parser.add_argument("-r", "--db_user", help="PostgreSQL user")
    parser.add_argument("-w", "--db_password", help="PostgreSQL password")
    parser.add_argument("--pg_path", help="directory of the PostgreSQL tools")
    parser.add_argument("--db_host", help="PostgreSQL host")
    parser.add_argument("--db_port", help="PostgreSQL port")
    parser.add_argument("--db_sslmode", help="PostgreSQL SSL mode")


def parse_odoo_config(namespace, setup_logging):
    """Load Odoo's configuration from the global options of ``namespace``.

    Without ``-c``, the configuration file is the one of ODOO_RC (else
    ~/.odoorc). With ``setup_logging`` False, logging stays unconfigured
    and no configuration report is printed: only WARNING and above reach
    stderr, through logging.lastResort, so stdout and stderr carry data
    alone.
    """
    argv = []
    for key, value in vars(namespace).items():
        if value is None:
            continue
        if key in _FORWARDED_DESTS:
            argv += [_FORWARDED_DESTS[key], value]
        elif key.startswith(("db_", "pg_")):
            argv += [f"--{key}", value]
    config.parse_config(argv, setup_logging=setup_logging)
    if setup_logging:
        from odoo.cli.server import report_configuration

        report_configuration()


@contextlib.contextmanager
def open_env(dbname):
    """Yield a superuser environment on ``dbname``.

    The cursor commits when the block ends normally and rolls back when it
    raises, SystemExit included. Server-wide modules are loaded first, as
    the server does before opening a registry.
    """
    from odoo.service.server import load_server_wide_modules

    load_server_wide_modules()
    threading.current_thread().dbname = dbname
    registry = Registry(dbname)
    with registry.cursor() as cr:
        yield api.Environment(cr, SUPERUSER_ID, {})


def fail(message, code=1):
    """Print ``message`` on stderr and exit with ``code``."""
    eprint(message)
    sys.exit(code)
