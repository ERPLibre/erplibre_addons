# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Présence d'un navigateur des utilisateurs, pour les appareils de
l'application qui se taisent pendant ce temps."""

from datetime import timedelta

from odoo import fields, models
from odoo.addons.bus.models.bus_presence import AWAY_TIMER, DISCONNECTION_TIMER


class ResUsers(models.Model):
    _inherit = "res.users"

    def _erplibre_browser_online(self):
        """Rend vrai quand un navigateur d'un de ces utilisateurs est en
        ligne ; le bus de l'application ne compte pas comme un navigateur
        (voir ir.websocket._update_bus_presence).

        En ligne : un sondage depuis moins de DISCONNECTION_TIMER secondes
        (`erplibre_browser_poll`) et une activité depuis moins de AWAY_TIMER
        secondes (`erplibre_browser_presence`), les délais d'Odoo pour
        « hors ligne » et « absent ».
        """
        if not self:
            return False
        now = fields.Datetime.now()
        # sudo: bus.presence - seules les présences de ces utilisateurs sont
        # comptées, sans rien en rendre.
        return bool(
            self.env["bus.presence"]
            .sudo()
            .search_count(
                [
                    ("user_id", "in", self.ids),
                    (
                        "erplibre_browser_poll",
                        ">=",
                        now - timedelta(seconds=DISCONNECTION_TIMER),
                    ),
                    (
                        "erplibre_browser_presence",
                        ">=",
                        now - timedelta(seconds=AWAY_TIMER),
                    ),
                ],
                limit=1,
            )
        )
