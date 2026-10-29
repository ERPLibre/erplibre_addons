# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Présence d'un navigateur des utilisateurs, pour les appareils de
l'application qui se taisent pendant ce temps."""

from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _erplibre_browser_online(self):
        """Rend vrai quand un navigateur d'un de ces utilisateurs est en
        ligne ; le bus de l'application ne compte pas comme un navigateur.

        Sans suivi de la présence des navigateurs, rend toujours faux :
        aucun appareil n'est alors tu.
        """
        return False
