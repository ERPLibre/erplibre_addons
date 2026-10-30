# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Marque d'un appareil de notification comme celui de l'application."""

import hashlib

from odoo import http
from odoo.http import request

from ..models.mail_push_device import BROWSER_MODES
from ..tools import app_push


class ErplibrePushController(http.Controller):
    @http.route(
        "/erplibre_mobile_chat/push/device",
        methods=["POST"],
        type="json",
        auth="user",
    )
    def erplibre_push_device(
        self, endpoint, quiet_while_online=False, browser_mode=None
    ):
        """Marque l'appareil `endpoint` du partenaire courant comme celui
        de l'application et rend `{"ok": true}` ; `{"ok": false}` quand ce
        partenaire n'a pas d'appareil de ce point de terminaison, celui
        d'un autre partenaire restant intact, ou quand `browser_mode`
        n'est pas un des modes de BROWSER_MODES, sans rien écrire.

        `browser_mode` donné (application 1.6) devient le mode de
        l'appareil, qui reçoit alors la charge v 2 ; absent (application
        1.5), `quiet_while_online` vaut le mode `quiet`, sinon `ring`, et
        l'appareil garde la charge v 1. La marque enregistre aussi le
        SHA-256 hexadécimal de l'id de la session qui appelle, qui
        distingue le bus de l'application de celui d'un navigateur.
        L'application appelle la route après chaque `register_devices` et
        après chaque nouvelle session ; un rappel réécrit les quatre
        champs.
        """
        if browser_mode is None:
            values = {
                "erplibre_browser_mode": (
                    "quiet" if quiet_while_online else "ring"
                ),
                "erplibre_payload_v": app_push.PAYLOAD_VERSION,
            }
        elif browser_mode in [mode for mode, _label in BROWSER_MODES]:
            values = {
                "erplibre_browser_mode": browser_mode,
                "erplibre_payload_v": app_push.MESSAGE_PAYLOAD_VERSION,
            }
        else:
            return {"ok": False}
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
                **values,
                "erplibre_app": True,
                "erplibre_session_hash": hashlib.sha256(
                    request.session.sid.encode()
                ).hexdigest(),
            }
        )
        return {"ok": True}
