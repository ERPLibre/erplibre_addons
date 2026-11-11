# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def write(self, vals):
        """Archiving users archives their workstations, which clears the
        workstations' tokens; the workstations, their decks and their
        events stay readable by the manager."""
        result = super().write(vals)
        if "active" in vals and not vals["active"]:
            self._streamdeck_depart()
        return result

    def action_archive(self):
        """Odoo deletes the open activities of the users it archives
        before it archives them: the departure runs first, so that the
        monitoring activities are closed and stay done. `write` runs it
        again, finding nothing left to do."""
        self._streamdeck_depart()
        return super().action_archive()

    def _streamdeck_depart(self):
        """Archive the workstations of these users, which closes the
        monitoring activities of the workstations and of their decks for
        every recipient, then close the monitoring activities still
        assigned to these users."""
        self.env["streamdeck.workstation"].sudo().search(
            [("user_id", "in", self.ids)]
        ).write({"active": False})
        self.env["streamdeck.monitor"]._resolve_assigned(self, "user_archived")
