# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Les deux routes que le service `erplibre_sip_go` appelle.

Meme protection que la passerelle SMS, et pour la meme raison : ces routes
sont publiques au sens d'Odoo — le service n'a pas de session — donc c'est la
SIGNATURE qui authentifie, avec un horodatage et un jeton a usage unique
contre le rejeu.

Le secret est lu dans l'environnement du processus, jamais dans la base ni
dans le depot : ce code est publie sous AGPL-3.
"""
import json
import logging
import time

from odoo import http
from odoo.http import request

from odoo.addons.erplibre_mobile_gateway.tools import signature

_logger = logging.getLogger(__name__)


def _refus(code, motif):
    return request.make_json_response({"ok": False, "error": motif}, status=code)


class RepondeurController(http.Controller):

    def _authentifier(self):
        """Signature, fraicheur, jeton. Rend (charge, None) ou (None, refus).

        Il n'y a PAS de fiche d'appareil a retrouver ici, contrairement a la
        passerelle SMS : le repondeur est le service lui-meme, et exiger une
        fiche obligerait a en creer une pour une machine qui n'envoie rien.
        """
        brut = request.httprequest.get_data()
        entete = request.httprequest.headers.get(signature.SIGNATURE_HEADER)
        try:
            if not signature.verify(brut, entete):
                _logger.warning(
                    "erplibre_repondeur: signature invalide depuis %s",
                    request.httprequest.remote_addr,
                )
                return None, _refus(403, "invalid signature")
        except signature.MissingSecret as exc:
            _logger.error("erplibre_repondeur: %s", exc)
            return None, _refus(503, "secret not configured")

        try:
            charge = json.loads(brut.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, _refus(400, "malformed json")

        try:
            ecart = abs(time.time() - int(charge.get("ts")))
        except (TypeError, ValueError):
            return None, _refus(400, "missing ts")
        if ecart > signature.MAX_CLOCK_SKEW:
            return None, _refus(403, "stale timestamp")

        appareil = charge.get("device") or "repondeur"
        if (
            not request.env["erplibre.sms.nonce"]
            .sudo()
            ._consume(charge.get("nonce"), appareil)
        ):
            return None, _refus(409, "replayed nonce")
        return charge, None

    @http.route(
        "/erplibre_repondeur/reglages",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def reglages(self, **_kwargs):
        """Ce que le service doit savoir pour decrocher.

        L'annonce voyage AVEC les reglages plutot que par une seconde route :
        le service la reecrit sur disque a chaque demarrage, et deux appels
        qui peuvent reussir separement laisseraient une annonce d'hier avec
        des sonneries d'aujourd'hui.
        """
        _charge, refus = self._authentifier()
        if refus:
            return refus
        # La societe par defaut : une requete publique n'a pas d'utilisateur,
        # donc pas de societe choisie. Une installation multi-societe qui
        # partagerait une seule ligne cellulaire devrait nommer laquelle, et
        # ce jour-la la charge portera son identifiant.
        societe = request.env.company.sudo()
        return request.make_json_response(
            {"ok": True, "reglages": societe.reglages_du_repondeur()}
        )

    @http.route(
        "/erplibre_repondeur/message",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def message(self, **_kwargs):
        """Recoit un message enregistre.

        Rend l'identifiant cree — le meme si le service reessaie apres une
        reponse perdue, sans quoi il televerserait en boucle et la liste se
        remplirait de doublons de la meme voix.
        """
        charge, refus = self._authentifier()
        if refus:
            return refus
        if not charge.get("numero") or not charge.get("recu_le"):
            return _refus(400, "missing numero or recu_le")
        identifiant = (
            request.env["erplibre.repondeur.message"]
            .sudo()
            .enregistrer_depuis_le_service(charge)
        )
        return request.make_json_response({"ok": True, "id": identifiant})
