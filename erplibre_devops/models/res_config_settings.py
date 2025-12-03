#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)


from odoo import api, fields, models

DEFAULT_TERMINAL_VALUE = "gnome-terminal"
DEFAULT_USE_SEARCH_CMD_VALUE = "locate"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ----------------------------------------------------------
    # Selections
    # ----------------------------------------------------------

    def _system_terminal_selection(self):
        selections = self.env["devops.system"]._fields["terminal"].selection
        return selections

    def _system_use_search_cmd_selection(self):
        selections = (
            self.env["devops.system"]._fields["use_search_cmd"].selection
        )
        return selections

    # ----------------------------------------------------------
    # Database
    # ----------------------------------------------------------

    default_terminal = fields.Selection(
        selection=lambda self: self._system_terminal_selection(),
        default=DEFAULT_TERMINAL_VALUE,
        default_model="devops.system",
        string="Default terminal system",
        help="Default terminal for new system.",
    )

    default_use_search_cmd = fields.Selection(
        selection=lambda self: self._system_use_search_cmd_selection(),
        default=DEFAULT_USE_SEARCH_CMD_VALUE,
        default_model="devops.system",
        string="Default Use search cmd system",
        help="Default cmd to search.",
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def set_values(self):
        res = super(ResConfigSettings, self).set_values()
        param = self.env["ir.config_parameter"].sudo()
        param.set_param(
            "erplibre_devops.default_terminal", self.default_terminal
        )
        param.set_param(
            "erplibre_devops.default_use_search_cmd",
            self.default_use_search_cmd,
        )
        return res

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env["ir.config_parameter"].sudo()
        res.update(
            default_terminal=params.get_param(
                "erplibre_devops.default_terminal", DEFAULT_TERMINAL_VALUE
            )
        )
        res.update(
            default_use_search_cmd=params.get_param(
                "erplibre_devops.default_use_search_cmd",
                DEFAULT_USE_SEARCH_CMD_VALUE,
            )
        )
        return res

    def auto_select_terminal(self):
        params = self.env["ir.config_parameter"].sudo()
        default_value = False
        for key, value in self._system_terminal_selection():
            result = self.env["devops.system"]._execute_process(f"which {key}")
            if result:
                default_value = key
                break
        if default_value:
            params.set_param("erplibre_devops.default_terminal", default_value)
            for rec in self.env["devops.system"].search(
                [("terminal", "=", False)]
            ):
                rec.terminal = default_value

    def auto_select_use_search_cmd(self):
        params = self.env["ir.config_parameter"].sudo()
        default_value = False
        for key, value in self._system_use_search_cmd_selection():
            result = self.env["devops.system"]._execute_process(f"which {key}")
            if result:
                default_value = key
                break
        if default_value:
            params.set_param(
                "erplibre_devops.default_use_search_cmd", default_value
            )
            for rec in self.env["devops.system"].search(
                [("use_search_cmd", "=", False)]
            ):
                rec.use_search_cmd = default_value
