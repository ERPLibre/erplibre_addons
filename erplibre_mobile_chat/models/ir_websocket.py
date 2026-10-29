# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Mise à jour de la présence des navigateurs à chaque mise à jour de
présence du bus."""

import hashlib

from odoo import models
from odoo.addons.bus.websocket import wsrequest
from odoo.http import request


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _update_bus_presence(self, inactivity_period, im_status_ids_by_model):
        """Après la mise à jour d'Odoo, écrit la présence d'un navigateur
        de l'utilisateur connecté (`erplibre_update_browser_presence` de
        bus.presence), sauf quand la session du bus est celle qui a marqué
        un de ses appareils de l'application (`erplibre_session_hash`) : le
        bus de l'application ne compte jamais comme un navigateur.

        La session est celle de la requête websocket, ou de la requête HTTP
        de /websocket/update_bus_presence.
        """
        super()._update_bus_presence(inactivity_period, im_status_ids_by_model)
        user = self.env.user
        if not user or user._is_public():
            return
        req = request or wsrequest
        sid = getattr(req and req.session, "sid", None)
        if not sid:
            return
        session_hash = hashlib.sha256(sid.encode()).hexdigest()
        devices = self.env["mail.push.device"]._erplibre_app_devices(
            user.partner_id.ids
        )
        if session_hash in devices.mapped("erplibre_session_hash"):
            return
        # sudo: bus.presence - la ligne de l'utilisateur courant, seule
        # cherchée, est écrite quels que soient ses droits.
        self.env["bus.presence"].sudo().erplibre_update_browser_presence(
            int(inactivity_period), user.id
        )
