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

        # Les evenements d'appel voyagent dans le MEME rapport, sous une cle
        # distincte : meme signature, meme anti-rejeu, un seul aller-retour.
        calls_applied, calls_created = self._apply_call_events(
            payload.get("calls") or [], gateway
        )

        if (applied or calls_applied) and gateway.alarm_active:
            # Le telephone envoie a nouveau : la panne est terminee.
            gateway._clear_alarm()

        return request.make_json_response({
            "ok": True, "applied": applied, "ignored": ignored,
            "unknown": unknown, "malformed": malformed,
            "calls_applied": calls_applied, "calls_created": calls_created,
        })

    # ------------------------------------------------------------------
    def _apply_call_events(self, events, gateway):
        """Applique les evenements d'appel, en creant ceux qu'on decouvre.

        Un appel compose a la main sur le telephone n'existe pas encore cote
        serveur : c'est le rapport qui le fait naitre. On ne le refuse donc
        pas comme « inconnu », contrairement a un SMS — un SMS inconnu serait
        un rejeu ou une erreur, un appel inconnu est simplement un appel que
        personne n'avait demande.
        """
        Call = request.env["erplibre.mobile.call"].sudo()
        applied = created = 0
        for event in events:
            uuid = event.get("uuid")
            if not uuid:
                continue
            try:
                seq = int(event.get("seq"))
            except (TypeError, ValueError):
                seq = 0
            if seq <= 0:
                continue

            appel = Call.search([("call_uuid", "=", uuid)], limit=1)
            if not appel:
                numero = (event.get("number") or "").strip()
                if not numero:
                    continue
                appel = Call.create({
                    "call_uuid": uuid,
                    "number": numero,
                    "direction": "in" if event.get("direction") == "in" else "out",
                    "source": event.get("source") or "manual",
                    "company_id": gateway.company_id.id,
                    "gateway_id": gateway.id,
                    "device_id": gateway.device_id,
                    "state": "queued",
                })
                created += 1
                # A la NAISSANCE de l'appel, pas a sa fin : l'interet d'afficher
                # la fiche de l'appelant est de l'avoir sous les yeux pendant
                # qu'il parle, pas apres avoir raccroche.
                appel._announce_incoming()

            horodatage = None
            if event.get("at"):
                try:
                    horodatage = fields.Datetime.to_datetime(
                        fields.Datetime.now().fromtimestamp(int(event["at"]))
                    )
                except (TypeError, ValueError, OSError):
                    horodatage = None

            duree = event.get("duration")
            if duree is not None:
                try:
                    duree = int(duree)
                except (TypeError, ValueError):
                    duree = None

            if appel._apply_event(
                event.get("state"),
                seq=seq,
                at=horodatage,
                duration=duree,
                duration_source=event.get("duration_source"),
                reason=event.get("reason"),
            ):
                applied += 1
        return applied, created

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

        # Les appels voyagent par le MEME echange que les SMS : un telephone
        # qui ne tient qu'une conversation a la fois n'a aucun besoin d'un
        # second canal, et en ajouter un doublerait la surface a authentifier.
        calls = request.env["erplibre.mobile.call"].sudo()._claim_pending(gateway)
        if calls:
            _logger.info(
                "erplibre_mobile_gateway: %s appel(s) remis a la"
                " passerelle %s",
                len(calls), gateway.device_id,
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
            "calls": calls._payload(),
        })

    # ------------------------------------------------------------------
    @http.route("/erplibre_sms/inbound", type="http", auth="public", methods=["POST"], csrf=False)
    def inbound(self, **kwargs):
        """SMS recus par le telephone, dont les desabonnements."""
        authenticated, error = self._authenticate()
        if error:
            return error
        payload, gateway = authenticated

        inbound_model = request.env["erplibre.sms.inbound"].sudo()
        recorded, opt_outs = 0, 0
        for message in payload.get("messages") or []:
            record = inbound_model._record(gateway, message)
            if record:
                recorded += 1
                if record.is_opt_out:
                    opt_outs += 1
        return request.make_json_response({
            "ok": True, "recorded": recorded, "opt_outs": opt_outs,
        })

    # ------------------------------------------------------------------
    @http.route(
        "/erplibre_sms/voicemail",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def voicemail(self, **kwargs):
        """Etat de la boite vocale de l'operateur, lu sur la SIM du modem.

        Le service ne transmet que les changements, plus l'etat au demarrage :
        la fiche porte donc l'etat courant sans interrogation periodique.
        """
        authenticated, error = self._authenticate()
        if error:
            return error
        payload, gateway = authenticated
        if "attente" not in payload:
            return _fail(400, "missing attente")
        change = gateway._signaler_messagerie(
            payload.get("attente"), payload.get("lu_le") or None
        )
        return request.make_json_response({"ok": True, "changed": change})
