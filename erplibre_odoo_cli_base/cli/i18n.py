# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""``i18n`` command: export the translation files of an installed module.

optparse keeps the command line of the former ERPLibre core command:
``i18n -d DB --module NAME --addons_path OUTPUT [--lang LANG]``.
"""

import base64
import optparse
import os
import sys
from pathlib import Path

from odoo.cli import Command
from odoo.tools import config

from . import _common


class I18n(Command):
    """Export the .pot and .po files of an installed module"""

    name = "i18n"

    def run(self, cmdargs):
        parser = optparse.OptionParser(
            prog=f"{Path(sys.argv[0]).name} {self.name}",
            description=self.__doc__.strip(),
        )
        parser.add_option("-c", "--config", help="configuration file")
        parser.add_option(
            "-d", "--database", dest="database", help="database to read"
        )
        parser.add_option(
            "--lang",
            default="fr_CA",
            help="language of the .po file, default fr_CA",
        )
        parser.add_option("--module", help="installed module to export")
        parser.add_option(
            "--addons_path",
            dest="output_path",
            help=(
                "output root: files go to OUTPUT/MODULE/i18n/ (this is not"
                " Odoo's addons path)"
            ),
        )
        opt, _args = parser.parse_args(cmdargs)

        config.parse_config(
            ["-c", opt.config] if opt.config else [], setup_logging=True
        )
        if not opt.database:
            _common.fail("Need a database name, use -d.")
        if not opt.module:
            _common.fail("Need a module name, use --module.")
        if not opt.output_path:
            _common.fail("Need an output directory, use --addons_path.")

        with _common.open_env(opt.database) as env:
            module = env["ir.module.module"].search(
                [("name", "=", opt.module), ("state", "=", "installed")]
            )
            if not module:
                _common.fail(f"Module '{opt.module}' not installed.")
            i18n_path = os.path.join(opt.output_path, opt.module, "i18n")
            os.makedirs(i18n_path, exist_ok=True)
            self._export(
                env, module, None, os.path.join(i18n_path, f"{opt.module}.pot")
            )
            self._export(
                env,
                module,
                opt.lang,
                os.path.join(i18n_path, f"{opt.lang}.po"),
            )

    @staticmethod
    def _export(env, module, lang, path):
        """Write to ``path`` the PO export of ``module``.

        ``lang`` None gives the template (.pot); a language code must be
        installed in the database, as the export wizard requires.
        """
        values = {"format": "po", "modules": [(6, 0, module.ids)]}
        if lang:
            values["lang"] = lang
        export = env["base.language.export"].create(values)
        export.act_getfile()
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(base64.b64decode(export.data).decode("utf-8"))
        _common.eprint(f"Wrote {path}")
