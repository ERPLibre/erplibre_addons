# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Présence d'un navigateur des utilisateurs, pour les appareils de
l'application qui attendent ou se taisent pendant ce temps."""

from datetime import timedelta

from odoo import fields, models
from odoo.addons.bus.models.bus_presence import DISCONNECTION_TIMER

# Délai, en secondes, après la dernière activité d'un navigateur au-delà
# duquel il ne compte plus comme actif. Le statut qu'Odoo affiche garde son
# propre délai (AWAY_TIMER).
BROWSER_ACTIVE_S = 300


class ResUsers(models.Model):
    _inherit = "res.users"

    def _erplibre_browser_domain(self):
        """Rend le domaine des présences de bus.presence qui disent un
        navigateur d'un de ces utilisateurs en ligne ; le bus de
        l'application ne compte pas comme un navigateur (voir
        ir.websocket._update_bus_presence).

        En ligne : un sondage depuis moins de DISCONNECTION_TIMER secondes
        (`erplibre_browser_poll`), le délai d'Odoo pour « hors ligne », et
        une activité depuis moins de BROWSER_ACTIVE_S secondes
        (`erplibre_browser_presence`). L'utilisateur comparé est celui du
        navigateur qui a écrit (`erplibre_browser_user_id`), jamais le
        `user_id` de la présence, que tout utilisateur peut changer.
        """
        now = fields.Datetime.now()
        return [
            ("erplibre_browser_user_id", "in", self.ids),
            (
                "erplibre_browser_poll",
                ">=",
                now - timedelta(seconds=DISCONNECTION_TIMER),
            ),
            (
                "erplibre_browser_presence",
                ">=",
                now - timedelta(seconds=BROWSER_ACTIVE_S),
            ),
        ]

    def _erplibre_browser_online(self):
        """Rend vrai quand un navigateur d'un de ces utilisateurs est en
        ligne (voir _erplibre_browser_domain)."""
        if not self:
            return False
        # sudo: bus.presence - seules les présences de ces utilisateurs sont
        # comptées, sans rien en rendre.
        return bool(
            self.env["bus.presence"]
            .sudo()
            .search_count(self._erplibre_browser_domain(), limit=1)
        )

    def _erplibre_browser_online_users(self):
        """Rend, en une recherche, ceux de ces utilisateurs dont un
        navigateur est en ligne (voir _erplibre_browser_domain)."""
        if not self:
            return self.browse()
        # sudo: bus.presence - seules les présences de ces utilisateurs sont
        # lues, et seul leur utilisateur en est rendu.
        presences = (
            self.env["bus.presence"]
            .sudo()
            .search_fetch(
                self._erplibre_browser_domain(), ["erplibre_browser_user_id"]
            )
        )
        return self.browse(presences.erplibre_browser_user_id.ids)
