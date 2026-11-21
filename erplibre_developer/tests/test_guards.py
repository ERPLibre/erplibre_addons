# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import tempfile
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import DeveloperCase


@tagged("post_install", "-at_install")
class TestGuards(DeveloperCase):
    def setUp(self):
        super().setUp()
        self.env.cr.postcommit.clear()
        self.user = new_test_user(
            self.env, login="erplibre_developer_user", groups="base.group_user"
        )
        self.erp_manager = new_test_user(
            self.env,
            login="erplibre_developer_manager",
            groups="base.group_user,base.group_erp_manager",
        )

    def _public_calls(self, dev):
        return [
            lambda: dev.get_view_info("res.partner", False, "form"),
            lambda: dev.get_code_info(["base"]),
            lambda: dev.get_module_commits("base"),
            lambda: dev.action_reload_assets(),
            lambda: dev.action_upgrade_module("base"),
            lambda: dev.action_open_in_ide(__file__, 1),
        ]

    def test_settings_group_required(self):
        for user in (self.user, self.erp_manager):
            for call in self._public_calls(self.Dev.with_user(user)):
                with self.assertRaises(AccessError):
                    call()

    def test_developer_mode_required(self):
        self._debug = False
        for call in self._public_calls(self.Dev):
            with self.assertRaises(UserError):
                call()

    def _without_ide(self):
        """The base module alone: a bridge module may register an IDE."""
        return patch.object(type(self.Dev), "_ide_available", lambda self_: False)

    def test_payload_flags(self):
        with self.server_actions(flag=False), self._without_ide():
            info = self.Dev.get_view_info("res.partner", False, "form")
            self.assertFalse(info["server_actions_allowed"])
            self.assertFalse(info["ide_available"])
        with self.server_actions():
            info = self.Dev.get_view_info("res.partner", False, "form")
            self.assertTrue(info["server_actions_allowed"])

    def test_ide_offered_only_with_the_server_actions(self):
        """An IDE opener alone is not enough: opening it is a server
        action, refused without the odoo.conf flag."""
        with patch.object(type(self.Dev), "_ide_available", lambda self_: True):
            with self.server_actions(flag=False):
                info = self.Dev.get_view_info("res.partner", False, "form")
                self.assertFalse(info["ide_available"])
            with self.server_actions():
                info = self.Dev.get_view_info("res.partner", False, "form")
                self.assertTrue(info["ide_available"])

    def test_upgrade_needs_the_odoo_conf_flag(self):
        with self.server_actions(flag=False):
            with self.assertRaises(UserError):
                self.Dev.action_upgrade_module("erplibre_developer")

    def test_upgrade_opens_the_erplibre_info_confirmation(self):
        """The upgrade goes through the erplibre_info confirmation: nothing
        is marked nor restarted before it is confirmed."""
        module = self.env["ir.module.module"].search(
            [("name", "=", "erplibre_developer")]
        )
        with self.server_actions(), patch("odoo.service.server.restart") as restart:
            action = self.Dev.action_upgrade_module("erplibre_developer")
            self.env.cr.postcommit.run()
        restart.assert_not_called()
        self.assertEqual(action["res_model"], "erplibre.code.confirm.wizard")
        self.assertEqual(action["target"], "new")
        wizard = self.env["erplibre.code.confirm.wizard"].browse(action["res_id"])
        self.assertEqual(wizard.action, "restart_upgrade")
        self.assertEqual(wizard.module_ids, module)
        self.assertEqual(module.state, "installed")

    def test_upgrade_confirmed_marks_and_restarts(self):
        module = self.env["ir.module.module"].search(
            [("name", "=", "erplibre_developer")]
        )
        with self.server_actions(), patch("odoo.service.server.restart") as restart:
            action = self.Dev.action_upgrade_module("erplibre_developer")
            wizard = self.env["erplibre.code.confirm.wizard"].browse(action["res_id"])
            wizard.write(
                {"typed_database_name": self.env.cr.dbname, "understood": True}
            )
            wizard.action_confirm()
            restart.assert_not_called()
            self.env.cr.postcommit.run()
        restart.assert_called_once_with()
        self.assertEqual(module.state, "to upgrade")

    def test_upgrade_unknown_module(self):
        with self.server_actions(), self.assertRaises(UserError):
            self.Dev.action_upgrade_module("no_such_module_erplibre")

    def test_reload_assets(self):
        Attachment = type(self.env["ir.attachment"])
        with patch.object(Attachment, "regenerate_assets_bundles") as regenerate:
            self.assertTrue(self.Dev.action_reload_assets())
        regenerate.assert_called_once()

    def test_open_in_ide_without_bridge(self):
        with self.server_actions(), self._without_ide(), self.assertRaises(UserError):
            self.Dev.action_open_in_ide(__file__, 3)

    def test_open_in_ide_refuses_a_file_outside_the_code(self):
        Dev = type(self.Dev)
        with tempfile.NamedTemporaryFile(suffix=".py") as outside, patch.object(
            Dev, "_ide_available", lambda self_: True
        ), patch.object(Dev, "_ide_open", lambda self_, path, line: (path, line)):
            with self.server_actions():
                with self.assertRaises(UserError):
                    self.Dev.action_open_in_ide(outside.name, 1)
                with self.assertRaises(UserError):
                    self.Dev.action_open_in_ide(os.path.dirname(__file__), 1)
                self.assertEqual(
                    self.Dev.action_open_in_ide(__file__, "7"),
                    (os.path.realpath(__file__), 7),
                )
            with self.server_actions(flag=False), self.assertRaises(UserError):
                self.Dev.action_open_in_ide(__file__, 1)
