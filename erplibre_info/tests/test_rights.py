# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The three conditions of the server actions: the odoo.conf flag, the
Settings group, the developer mode."""

import os
import tempfile
from contextlib import contextmanager
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tools import config

from ..models.erplibre_code_run import FLAG_SERVER_ACTIONS
from .common import ErplibreInfoCase


@tagged("post_install", "-at_install")
class TestServerActionRights(ErplibreInfoCase):
    def test_flag_off(self):
        with self.server_actions_allowed(flag=False):
            with self.assertRaises(UserError):
                self.Run._check_server_actions()
            self.assertFalse(self.Run._server_actions_allowed())

    @contextmanager
    def _rcfile(self, flag=None, exists=True):
        """``config.rcfile`` on an invented file, the flag absent from the
        options unless ``flag`` gives its value."""
        with tempfile.TemporaryDirectory() as tmp:
            rcfile = os.path.join(tmp, "odoo.conf")
            if exists:
                open(rcfile, "w").close()
            with patch.object(config, "rcfile", rcfile), patch.dict(config.options):
                config.options.pop(FLAG_SERVER_ACTIONS, None)
                if flag is not None:
                    config.options[FLAG_SERVER_ACTIONS] = flag
                yield rcfile

    def test_flag_absent_names_the_file_read(self):
        with self._rcfile() as rcfile:
            problem = self.Run._flag_problem()
            with self.assertRaisesRegex(UserError, "\\[options\\]"):
                self.Run._check_server_actions()
        self.assertIn(rcfile, problem)
        self.assertIn(FLAG_SERVER_ACTIONS, problem)

    def test_flag_false_gives_its_value(self):
        with self._rcfile(flag=False) as rcfile:
            problem = self.Run._flag_problem()
        self.assertIn("reads False", problem)
        self.assertIn(rcfile, problem)

    def test_no_configuration_file(self):
        with self._rcfile(exists=False):
            problem = self.Run._flag_problem()
        self.assertIn("without a configuration file", problem)

    def test_settings_show_the_failing_condition(self):
        with self._rcfile() as rcfile:
            settings = self.env["res.config.settings"].create({})
            self.assertIn(rcfile, settings.erplibre_server_actions_problem)
        with self.server_actions_allowed(debug=False):
            settings = self.env["res.config.settings"].create({})
            self.assertIn("developer mode", settings.erplibre_server_actions_problem)
        with self.server_actions_allowed():
            settings = self.env["res.config.settings"].create({})
            self.assertFalse(settings.erplibre_server_actions_problem)

    def test_no_debug(self):
        with self.server_actions_allowed(debug=False):
            with self.assertRaises(UserError):
                self.Run._check_server_actions()

    def test_debug_outside_a_request(self):
        """Without an HTTP request there is no developer mode."""
        self.assertFalse(self.Run._is_debug_mode())

    def test_not_admin(self):
        user = new_test_user(
            self.env, login="erplibre_info_user", groups="base.group_user"
        )
        with self.server_actions_allowed():
            with self.assertRaises(AccessError):
                self.Run.with_user(user)._check_server_actions()
            self.assertFalse(self.Run.with_user(user)._server_actions_allowed())

    def test_all_conditions(self):
        with self.server_actions_allowed():
            self.Run._check_server_actions()
            self.assertTrue(self.Run._server_actions_allowed())
            settings = self.env["res.config.settings"].create({})
            self.assertTrue(settings.erplibre_server_actions_allowed)
