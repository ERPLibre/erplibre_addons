# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The server restart: a server action under the three conditions, after
the confirmation of the wizard. It never requires --dev."""

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ErplibreInfoCase


@tagged("post_install", "-at_install")
class TestRestart(ErplibreInfoCase):
    def setUp(self):
        super().setUp()
        self.env.cr.postcommit.clear()

    def _wizard(self, action, run=None, modules=None, typed=None, understood=True):
        res = self.env["erplibre.code.confirm.wizard"]._action_open(
            action, run=run, modules=modules
        )
        wizard = self.env["erplibre.code.confirm.wizard"].browse(res["res_id"])
        wizard.write(
            {
                "typed_database_name": (self.env.cr.dbname if typed is None else typed),
                "understood": understood,
            }
        )
        return wizard

    def test_restart_requires_the_database_name(self):
        with self.server_actions_allowed(), patch(
            "odoo.service.server.restart"
        ) as restart:
            wizard = self._wizard("restart", typed="other_database")
            with self.assertRaises(UserError):
                wizard.action_confirm()
            wizard = self._wizard("restart", understood=False)
            with self.assertRaises(UserError):
                wizard.action_confirm()
            self.env.cr.postcommit.run()
            restart.assert_not_called()
            self.assertFalse(self.Run.search_count([("run_type", "=", "restart")]))

            self._wizard("restart").action_confirm()
            restart.assert_not_called()
            self.env.cr.postcommit.run()
            restart.assert_called_once_with()
        run = self.Run.search([("run_type", "=", "restart")])
        self.assertEqual(run.state, "done")

    def test_restart_guarded_at_confirmation(self):
        with self.server_actions_allowed():
            wizard = self._wizard("restart")
        with self.server_actions_allowed(flag=False), patch(
            "odoo.service.server.restart"
        ) as restart:
            with self.assertRaises(UserError):
                wizard.action_confirm()
            self.env.cr.postcommit.run()
            restart.assert_not_called()

    def test_restart_upgrade_marks_modules(self):
        module = self.env.ref("base.module_erplibre_info")
        with self.server_actions_allowed(), patch("odoo.service.server.restart"):
            self._wizard("restart_upgrade", modules=module).action_confirm()
        self.assertEqual(module.state, "to upgrade")

    def test_no_debug(self):
        with self.server_actions_allowed(debug=False):
            with self.assertRaises(UserError):
                self.env["res.config.settings"].create({}).action_erplibre_restart()

    def test_without_dev(self):
        """A server started without --dev restarts all the same."""
        with self.server_actions_allowed(dev=False), patch(
            "odoo.service.server.restart"
        ) as restart:
            action = (
                self.env["res.config.settings"].create({}).action_erplibre_restart()
            )
            wizard = self.env["erplibre.code.confirm.wizard"].browse(action["res_id"])
            self.assertEqual(wizard.action, "restart")
            wizard.write(
                {"typed_database_name": self.env.cr.dbname, "understood": True}
            )
            wizard.action_confirm()
            self.env.cr.postcommit.run()
            restart.assert_called_once_with()
        run = self.Run.search([("run_type", "=", "restart")])
        self.assertEqual(run.state, "done")
