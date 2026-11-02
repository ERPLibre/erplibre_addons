# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError


class ErplibreCodeConfirmWizard(models.TransientModel):
    """Second validation of a server action: tick the box and type the
    database name again. A module that adds an action extends ``action``
    with ``selection_add`` and ``_confirm_action``."""

    _name = "erplibre.code.confirm.wizard"
    _description = "ERPLibre server action confirmation"

    action = fields.Selection(
        [
            ("restart", "Restart the server"),
            ("restart_upgrade", "Upgrade the modules and restart the server"),
        ],
        required=True,
        readonly=True,
    )
    run_id = fields.Many2one("erplibre.code.run", readonly=True)
    module_ids = fields.Many2many("ir.module.module", string="Modules to upgrade")
    database_name = fields.Char(compute="_compute_database_name")
    typed_database_name = fields.Char(string="Type the database name")
    understood = fields.Boolean(string="I understand what this action does")

    def _compute_database_name(self):
        for wizard in self:
            wizard.database_name = self.env.cr.dbname

    @api.model
    def _action_open_vals(self, action, run=None, modules=None, **kw):
        """The values of a new wizard for ``action``; a module that opens
        the wizard with more keyword arguments extends it."""
        return {
            "action": action,
            "run_id": run.id if run else False,
            "module_ids": [fields.Command.set(modules.ids if modules else [])],
        }

    @api.model
    def _action_open(self, action, run=None, modules=None, **kw):
        wizard = self.create(
            self._action_open_vals(action, run=run, modules=modules, **kw)
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "name": dict(self._fields["action"]._description_selection(self.env))[
                action
            ],
        }

    def action_confirm(self):
        self.ensure_one()
        self.env["erplibre.code.run"]._check_server_actions()
        if not self.understood:
            raise UserError(self.env._("Tick the box to confirm."))
        if (self.typed_database_name or "").strip() != self.env.cr.dbname:
            raise UserError(
                self.env._("The typed name is not the name of this database.")
            )
        return self._confirm_action()

    def _confirm_action(self):
        """Run the confirmed action: here the restart, with the modules to
        upgrade for ``restart_upgrade``."""
        self.ensure_one()
        modules = self.module_ids if self.action == "restart_upgrade" else None
        return self.env["erplibre.code.run"]._request_restart(modules)
