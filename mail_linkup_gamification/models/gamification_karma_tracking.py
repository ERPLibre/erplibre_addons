# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class GamificationKarmaTracking(models.Model):
    _inherit = "gamification.karma.tracking"

    def _get_origin_selection_values(self):
        """The karma of LinkUp comes from a reflection, or from a link for
        the events of a pair that no reflection carries."""
        return super()._get_origin_selection_values() + [
            (
                "linkup.reflet",
                self.env["ir.model"]._get("linkup.reflet").display_name,
            ),
            (
                "linkup.link",
                self.env["ir.model"]._get("linkup.link").display_name,
            ),
        ]
