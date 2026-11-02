# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os

import odoo
from odoo import api, fields, models

from .. import about, runner


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    erplibre_server_actions_allowed = fields.Boolean(
        compute="_compute_erplibre_server_actions_allowed"
    )
    erplibre_server_actions_problem = fields.Char(
        compute="_compute_erplibre_server_actions_allowed"
    )
    erplibre_checkout_problem = fields.Char(
        string="ERPLibre checkout problem",
        compute="_compute_erplibre_checkout_problem",
    )

    @api.model
    def _erplibre_status(self):
        """The values of the computed ERPLibre fields, by field name; a
        module that adds such fields extends it.

        They also go through ``get_values``: the first ``onchange`` of the
        Settings form puts False in cache for every field of the view that
        has no default, and recomputes only what depends on a changed
        field. A compute without dependency is never run there, and the
        form would show it empty.

        The checkout problem reads the file system; no script runs.
        """
        Run = self.env["erplibre.code.run"]
        allowed = Run._server_actions_allowed()
        return {
            "erplibre_checkout_problem": runner.checkout_problem(self.env) or False,
            "erplibre_server_actions_allowed": allowed,
            "erplibre_server_actions_problem": (
                False if allowed else Run._server_actions_problem()
            ),
        }

    def _erplibre_assign(self, names):
        status = self._erplibre_status()
        for settings in self:
            for name in names:
                settings[name] = status[name]

    def _compute_erplibre_checkout_problem(self):
        self._erplibre_assign(["erplibre_checkout_problem"])

    def _compute_erplibre_server_actions_allowed(self):
        self._erplibre_assign(
            ["erplibre_server_actions_allowed", "erplibre_server_actions_problem"]
        )

    @api.model
    def get_values(self):
        res = super().get_values()
        res.update(self._erplibre_status())
        return res

    @api.model
    def erplibre_about(self):
        """The values of the ERPLibre block of the About section, read from
        the checkout by ``about.read``: file reads and read-only git
        commands, nothing written. The checkout is the one the scripts run
        in, else the one above the running Odoo that holds env_var.sh."""
        self.check_access("read")
        root = runner.erplibre_root(self.env) or runner.find_root(
            os.path.dirname(odoo.__file__), runner.CHECKOUT_MARKER
        )
        return about.read(root)

    def action_erplibre_restart(self):
        run = self.env["erplibre.code.run"]
        run._check_server_actions()
        run._check_restart_allowed()
        return self.env["erplibre.code.confirm.wizard"]._action_open("restart")

    def action_erplibre_open_runs(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "erplibre_info.erplibre_code_run_action"
        )
