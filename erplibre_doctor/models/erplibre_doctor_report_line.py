# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.addons.base.models.ir_module import STATES
from odoo.exceptions import UserError

# The states of ir.module.module, and « absent » for a name the module list
# does not hold: not in the addons path, or the list not updated since.
MODULE_STATES = STATES + [("absent", "Not found")]

# The module states a line can still bring to « installed ».
INSTALLABLE_STATES = ("uninstalled", "to install")


class ErplibreDoctorReportLine(models.Model):
    """One finding of a report. ``state_found`` keeps what the analysis
    saw; ``module_state`` follows the module, so that a line installed
    since no longer offers to install it."""

    _name = "erplibre.doctor.report.line"
    _description = "ERPLibre doctor finding"
    _order = "report_id, sequence, id"

    report_id = fields.Many2one(
        "erplibre.doctor.report", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    check = fields.Selection(
        [("suggested_module", "Suggested module")], required=True
    )
    name = fields.Char(string="Module", required=True)
    module_id = fields.Many2one(
        "ir.module.module",
        string="Module in the database",
        ondelete="set null",
    )
    shortdesc = fields.Char(
        related="module_id.shortdesc", string="Description"
    )
    state_found = fields.Selection(
        MODULE_STATES, string="State at analysis", required=True
    )
    module_state = fields.Selection(
        related="module_id.state", string="Current state"
    )
    problem = fields.Boolean(
        help="The analysis found the module not installed in this database."
    )
    can_install = fields.Boolean(
        string="Can install", compute="_compute_can_install"
    )

    @api.depends("check", "module_id.state")
    def _compute_can_install(self):
        """« to install » counts: a confirmation closed without Confirm or
        Cancel leaves the mark, and only the confirmation takes it back."""
        for line in self:
            line.can_install = (
                line.check == "suggested_module"
                and line.module_id.state in INSTALLABLE_STATES
            )

    @api.model
    def _action_install_modules(self, modules):
        """Mark the « uninstalled » ``modules`` « to install » with their
        dependencies, and return the doctor's confirmation of the scheduled
        changes; those already marked are listed again."""
        modules.filtered(lambda m: m.state == "uninstalled").button_install()
        view = self.env.ref(
            "erplibre_doctor.base_module_upgrade_view_form_doctor"
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Install the suggested modules"),
            "res_model": "base.module.upgrade",
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
        }

    def action_install(self):
        modules = self.filtered("can_install").module_id
        if not modules:
            raise UserError(
                self.env._("This module cannot be installed from here.")
            )
        return self._action_install_modules(modules)

    def action_open_module(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "ir.module.module",
            "res_id": self.module_id.id,
            "view_mode": "form",
            "target": "current",
        }
