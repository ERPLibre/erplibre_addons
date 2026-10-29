# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Marque d'un appareil de notification comme celui de l'application."""

import hashlib

from odoo import http
from odoo.http import request


class ErplibrePushController(http.Controller):
    @http.route(
        "/erplibre_mobile_chat/push/device",
        methods=["POST"],
        type="json",
        auth="user",
    )
    def erplibre_push_device(self, endpoint, quiet_while_online=False):
        """Marque l'appareil `endpoint` du partenaire courant comme celui
        de l'application et rend `{"ok": true}` ; `{"ok": false}` quand ce
        partenaire n'a pas d'appareil de ce point de terminaison, celui
        d'un autre partenaire restant intact.

        La marque enregistre `quiet_while_online` tel quel et le SHA-256
        hexadécimal de l'id de la session qui appelle, qui distingue le bus
        de l'application de celui d'un navigateur. L'application appelle la
        route après chaque `register_devices` et après chaque nouvelle
        session ; un rappel réécrit les trois champs.
        """
        # sudo: mail.push.device - le modèle n'est lisible que par
        # l'administrateur ; la recherche est bornée au partenaire courant.
        device = (
            request.env["mail.push.device"]
            .sudo()
            .search(
                [
                    ("endpoint", "=", endpoint),
                    ("partner_id", "=", request.env.user.partner_id.id),
                ],
                limit=1,
            )
        )
        if not device:
            return {"ok": False}
        device.write(
            {
                "erplibre_app": True,
                "erplibre_quiet_while_online": bool(quiet_while_online),
                "erplibre_session_hash": hashlib.sha256(
                    request.session.sid.encode()
                ).hexdigest(),
            }
        )
        return {"ok": True}
