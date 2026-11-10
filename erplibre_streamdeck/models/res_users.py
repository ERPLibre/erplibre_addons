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
            self.env["streamdeck.workstation"].sudo().search(
                [("user_id", "in", self.ids)]
            ).write({"active": False})
        return result
