# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class BaseModuleUpgrade(models.TransientModel):
    _inherit = "base.module.upgrade"

    def action_erplibre_doctor_confirm(self):
        """Apply the scheduled module changes, as Odoo's Confirm does, then
        reload the web client: the menus and assets of the modules just
        installed load only with a new page. Odoo's own Confirm closes the
        dialog only."""
        self.upgrade_module()
        return {"type": "ir.actions.client", "tag": "reload"}
