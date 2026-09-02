# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
"""Routes par lesquelles le telephone rend compte a Odoo.

Elles sont publiques -- le telephone n'a pas de session Odoo -- mais chaque
requete est authentifiee par une signature HMAC sur le corps BRUT, horodatee, et
protegee du rejeu par un nonce a usage unique.

C'est volontairement plus strict que la route `/sms/status` du module coeur, qui
est `auth="public"` et n'a AUCUNE verification de signature.
"""
import json
import logging
import time

from odoo import http, fields, _
from odoo.http import request

from ..tools import signature

_logger = logging.getLogger(__name__)


def _fail(status, message):
    return request.make_json_response({"ok": False, "error": message}, status=status)


class ErplibreSmsController(http.Controller):

    def _authenticate(self):
        """Verifie signature, fraicheur et nonce. Retourne (payload, gateway) ou (None, reponse)."""
        raw = request.httprequest.get_data()
        header = request.httprequest.headers.get(signature.SIGNATURE_HEADER)

        try:
            if not signature.verify(raw, header):
                _logger.warning("erplibre_mobile_gateway: signature invalide depuis %s",
                                request.httprequest.remote_addr)
                return None, _fail(403, "invalid signature")
        except signature.MissingSecret as exc:
            _logger.error("erplibre_mobile_gateway: %s", exc)
            return None, _fail(503, "gateway secret not configured")

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, _fail(400, "malformed json")

        timestamp = payload.get("ts")
        try:
            skew = abs(time.time() - int(timestamp))
        except (TypeError, ValueError):
            return None, _fail(400, "missing ts")
        if skew > signature.MAX_CLOCK_SKEW:
            _logger.warning("erplibre_mobile_gateway: horodatage hors fenetre (%ss)", int(skew))
            return None, _fail(403, "stale timestamp")

        device_id = payload.get("device")
        if not request.env["erplibre.sms.nonce"].sudo()._consume(payload.get("nonce"), device_id):
            return None, _fail(409, "replayed nonce")

        gateway = request.env["erplibre.sms.gateway"].sudo().search(
            [("device_id", "=", device_id)], limit=1
        )
        if not gateway:
            _logger.warning("erplibre_mobile_gateway: appareil inconnu %r", device_id)
            return None, _fail(404, "unknown device")
        return (payload, gateway), None

    # ------------------------------------------------------------------
    @http.route("/erplibre_sms/report", type="http", auth="public", methods=["POST"], csrf=False)
    def report(self, **kwargs):
        """Rapports d'etat d'envoi remontes par le telephone."""
        authenticated, error = self._authenticate()
        if error:
            return error
        payload, gateway = authenticated

        events = payload.get("events") or []
        dispatch_model = request.env["erplibre.sms.dispatch"].sudo()
        uuids = [event.get("uuid") for event in events if event.get("uuid")]
        dispatches = {
            dispatch.sms_uuid: dispatch
            for dispatch in dispatch_model.search([("sms_uuid", "in", uuids)])
        }

        applied, ignored, unknown, malformed = 0, 0, 0, 0
        for event in events:
            dispatch = dispatches.get(event.get("uuid"))
            if not dispatch:
                unknown += 1
                continue
            # Un rapport sans numero de sequence ne peut pas etre ordonne, donc
            # rien ne prouve qu'il n'est pas un rejeu. On le refuse plutot que de
            # rouvrir la faille : c'est le telephone qui doit numeroter.
            try:
                seq = int(event.get("seq"))
            except (TypeError, ValueError):
                seq = 0
            if seq <= 0:
                malformed += 1
                _logger.warning(
                    "erplibre_mobile_gateway: rapport sans sequence pour %s, refuse",
                    event.get("uuid"),
                )
                continue
            event_time = None
            if event.get("at"):
                try:
                    event_time = fields.Datetime.to_datetime(
                        fields.Datetime.now().fromtimestamp(int(event["at"]))
                    )
                except (TypeError, ValueError, OSError):
                    event_time = None
            if dispatch._apply_event(
                event.get("state"),
                seq=seq,
                android_code=event.get("code"),
                reason=event.get("reason"),
                device_id=gateway.device_id,
                event_time=event_time,
            ):
                applied += 1
            else:
                ignored += 1

        if applied and gateway.alarm_active:
            # Le telephone envoie a nouveau : la panne est terminee.
            gateway._clear_alarm()

        return request.make_json_response({
            "ok": True, "applied": applied, "ignored": ignored,
            "unknown": unknown, "malformed": malformed,
        })

    # ------------------------------------------------------------------
    @http.route("/erplibre_sms/poll", type="http", auth="public", methods=["POST"], csrf=False)
    def poll(self, **kwargs):
        """Le telephone demande s'il y a des SMS a envoyer.

        C'est le cœur de l'architecture : le serveur ne joint jamais le
        telephone, c'est le telephone qui vient. L'appareil peut donc etre
        derriere une IP dynamique et un NAT d'operateur, et aucune
        infrastructure intermediaire n'est necessaire.

        Chaque interrogation vaut AUSSI signal de vie. Fusionner les deux
        supprime un point d'acces et rend la detection de panne exacte : une
        passerelle qui n'interroge plus est hors service, par definition.
        """
        authenticated, error = self._authenticate()
        if error:
            return error
        payload, gateway = authenticated

        gateway._record_poll(payload.get("status") or {})

        dispatches = gateway._claim_pending()
        groups = gateway._payload_for(dispatches)
        deadline = min(dispatches.mapped("send_deadline")) if dispatches else None

        if dispatches:
            _logger.info(
                "erplibre_mobile_gateway: %s SMS remis a la passerelle %s",
                len(dispatches), gateway.device_id,
            )

        return request.make_json_response({
            "ok": True,
            "server_time": int(time.time()),
            # Le serveur pilote le rythme : on peut ralentir une passerelle
            # bavarde ou l'accelerer, sans toucher au telephone.
            "poll_interval": gateway.poll_interval_seconds,
            "segments_per_minute": gateway.segments_per_minute,
            "expires": int(deadline.timestamp()) if deadline else 0,
            "groups": groups,
        })
