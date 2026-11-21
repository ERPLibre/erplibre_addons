# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.tools import config


class DeveloperMixin:
    """The developer mode of a request, and the erplibre_info guard."""

    def setUp(self):
        super().setUp()
        self.Dev = self.env["erplibre.developer"]
        self.Run = self.env["erplibre.code.run"]
        self._debug = True
        patcher = patch.object(
            type(self.Run), "_is_debug_mode", lambda run: self._debug
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextmanager
    def server_actions(self, flag=True):
        with patch.dict(
            config.options, {"erplibre_info_allow_server_actions": str(flag)}
        ):
            yield

    def read_line(self, path, line):
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()[line - 1]

    def module_installed(self, name):
        return bool(
            self.env["ir.module.module"].search_count(
                [("name", "=", name), ("state", "=", "installed")]
            )
        )


class DeveloperCase(DeveloperMixin, TransactionCase):
    pass
