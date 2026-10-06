# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import logging
import math
import secrets
from datetime import timedelta

from odoo import fields, _
from odoo.addons.sms.tools.sms_api import SmsApiBase

_logger = logging.getLogger(__name__)

#: Alphabet GSM 03.38 de base, recopie de la definition qui fait autorite DANS
#: ce depot : la regex de `_extractEncoding` dans
#: odoo18.0/odoo/addons/sms/static/src/components/sms_widget/fields_sms_widget.js.
#:
#: Piege a connaitre pour un client francophone : `Ç` MAJUSCULE y est, `ç`
#: minuscule N'Y EST PAS -- c'est conforme a la norme (0x09 = Ç seulement).
#: Consequence : « recu », « ca », « lecon », « francais », « garcon » ecrits
#: correctement avec la cedille basculent en UCS-2, donc a 70 caracteres par
#: segment au lieu de 160. En francais du Quebec, la bascule est le cas normal.
GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
#: Caracteres de la table d'extension : ils comptent DOUBLE en GSM-7.
GSM7_EXTENDED = set("^{}\\[~]|€")


def analyse_body(body):
    """Retourne (encodage, nombre_de_segments) pour un corps de message.

    Les quatre bornes 160 / 153 / 70 / 67 sont celles de `_countSMS` du widget
    du cœur : on reste volontairement aligne sur ce que l'utilisatrice voit
    dans le compositeur, sinon le compteur affiche et l'estimation serveur
    divergeraient.
    """
    body = body or ""
    if all(char in GSM7_BASIC or char in GSM7_EXTENDED for char in body):
        septets = sum(2 if char in GSM7_EXTENDED else 1 for char in body)
        if septets == 0:
            return "gsm7", 0
        segments = 1 if septets <= 160 else math.ceil(septets / 153)
        return "gsm7", segments
    units = len(body.encode("utf-16-le")) // 2
    if units == 0:
        return "ucs2", 0
    segments = 1 if units <= 70 else math.ceil(units / 67)
    return "ucs2", segments


def non_gsm7_characters(body):
    """Caracteres qui font basculer un message en UCS-2. Sert a l'expliquer."""
    return sorted({c for c in (body or "") if c not in GSM7_BASIC and c not in GSM7_EXTENDED})


class SmsApiErplibre(SmsApiBase):
    """Fournisseur SMS adosse a la passerelle mobile."""

    PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {
        "gateway_missing": "sms_acc",
        "gateway_inactive": "sms_acc",
        "gateway_down": "sms_server",
        "blacklisted": "sms_blacklist",
        "quota_exceeded": "sms_credit",
    }

    def _get_sms_api_error_messages(self):
        messages = super()._get_sms_api_error_messages()
        messages.update({
            "gateway_missing": _("Aucune passerelle SMS n'est configuree pour cette societe."),
            "gateway_inactive": _(
                "La passerelle choisie pour cette societe est archivee ou "
                "appartient a une autre societe. Aucune autre n'a ete prise a "
                "sa place : le message serait parti depuis un autre numero."
            ),
            "gateway_down": _("La demande n'a pas pu etre publiee vers la passerelle SMS."),
            "blacklisted": _("Ce numero s'est desabonne des SMS."),
            "quota_exceeded": _("Le quota quotidien de SMS de la passerelle est atteint."),
        })
        return messages

    def _get_gateway(self):
        """Voir `erplibre.sms.gateway._for_company` : la regle vit la-bas."""
        return self.env["erplibre.sms.gateway"]._for_company(self.company)

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        """Met le lot en file, en attente que le telephone vienne le chercher.

        Rien n'est envoye ici : le telephone INTERROGE le serveur en HTTPS
        sortant a intervalle regulier. Cette methode ne fait donc aucun appel
        reseau -- ce qui la rend rapide et, surtout, incapable de faire depasser
        au worker cron sa limite de temps, ce qu'une boucle de 40 requetes
        sortantes ferait.

        `delivery_reports_url` est ignore : le cœur le force vers `/sms/status`,
        route publique et NON signee. La passerelle rapporte plutot vers
        `/erplibre_sms/report`, dont le corps est signe en HMAC.

        Retourne `processing`, ce qui est exact : le message est pris en charge,
        pas encore envoye. Le cœur en deduira `state = 'process'` et posera
        `to_delete = True` sur le `sms.sms` -- sans consequence ici puisque
        l'audit vit sur `erplibre.sms.dispatch` et que les `sms.tracker`
        survivent.
        """
        gateway = self._get_gateway()
        flat = [
            {"uuid": number["uuid"], "number": number["number"], "content": message["content"]}
            for message in messages
            for number in message["numbers"]
        ]
        if not gateway:
            # Distinguer « aucune » de « celle qu'on a choisie ne repond plus
            # aux conditions » : la premiere se repare en creant une
            # passerelle, la seconde en corrigeant un choix. Un seul message
            # pour les deux enverrait chercher au mauvais endroit.
            etat = (
                "gateway_inactive"
                if self.company.erplibre_gateway_id
                else "gateway_missing"
            )
            _logger.error(
                "erplibre_mobile_gateway: aucune passerelle utilisable pour %s (%s)",
                self.company.display_name, etat,
            )
            return [{"uuid": item["uuid"], "state": etat} for item in flat]

        blacklist = set(
            self.env["phone.blacklist"].sudo().search([
                ("number", "in", [item["number"] for item in flat]),
                ("active", "=", True),
            ]).mapped("number")
        )

        quota_left = self._quota_left(gateway)
        results, to_queue = [], []
        dispatch_values, batch_id = [], secrets.token_hex(12)
        deadline = fields.Datetime.now() + timedelta(seconds=gateway.send_deadline_seconds or 900)

        sms_by_uuid = {
            sms.uuid: sms
            for sms in self.env["sms.sms"].sudo().search([("uuid", "in", [i["uuid"] for i in flat])])
        }

        for item in flat:
            if item["number"] in blacklist:
                results.append({"uuid": item["uuid"], "state": "blacklisted"})
                continue
            if not item["number"] or not item["number"].strip().startswith("+"):
                # La passerelle envoie depuis une SIM : le format E.164 est exige.
                results.append({"uuid": item["uuid"], "state": "wrong_number_format"})
                continue
            if quota_left is not None and quota_left <= 0:
                results.append({"uuid": item["uuid"], "state": "quota_exceeded"})
                continue
            if quota_left is not None:
                quota_left -= 1

            encoding, segments = analyse_body(item["content"])
            to_queue.append(item["uuid"])
            sms = sms_by_uuid.get(item["uuid"])
            dispatch_values.append({
                "sms_uuid": item["uuid"],
                "batch_id": batch_id,
                "number": item["number"].strip(),
                "body": item["content"],
                "partner_id": sms.partner_id.id if sms else False,
                "company_id": self.company.id,
                "gateway_id": gateway.id,
                "requested_by_uid": self.env.uid,
                "state": "queued",
                "send_deadline": deadline,
                "segments_total": segments,
                "encoding": encoding,
            })

        if not to_queue:
            return results

        self.env["erplibre.sms.dispatch"].sudo().create(dispatch_values)

        if gateway.alarm_active:
            # On met quand meme en file -- le telephone rattrapera s'il revient
            # avant l'echeance -- mais on le dit, sans quoi l'utilisatrice
            # croirait son message parti.
            _logger.warning(
                "erplibre_mobile_gateway: %s SMS mis en file alors que la passerelle %s est "
                "en alerte : %s", len(to_queue), gateway.name, gateway.alarm_reason,
            )

        results.extend({"uuid": uuid, "state": "processing"} for uuid in to_queue)
        return results

    def _quota_left(self, gateway):
        """Nombre de SMS encore autorises aujourd'hui, ou None si pas de quota."""
        limit = int(self.env["ir.config_parameter"].sudo().get_param("erplibre_mobile_gateway.daily_quota", 0))
        if limit <= 0:
            return None
        since = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        used = self.env["erplibre.sms.dispatch"].sudo().search_count([
            ("gateway_id", "=", gateway.id),
            ("requested_at", ">=", since),
            ("state", "!=", "failed"),
        ])
        return max(limit - used, 0)
