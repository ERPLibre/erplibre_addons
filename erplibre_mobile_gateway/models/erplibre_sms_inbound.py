# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

#: Mots-cles de desabonnement. La LCAP exige qu'un desabonnement soit traite
#: dans les dix jours ouvrables ; l'automatiser est la seule facon de le
#: garantir sur un canal ou personne ne lit les reponses.
OPT_OUT_KEYWORDS = {
    "stop", "arret", "arrêt", "desabonnement", "désabonnement",
    "unsubscribe", "cancel", "quit", "end", "fin", "non",
}


class ErplibreSmsInbound(models.Model):
    """SMS recu par la passerelle.

    Conserve integralement, parce que c'est la piece justificative d'un
    desabonnement : sans trace horodatee, l'organisme ne peut pas demontrer
    qu'il a traite un STOP.
    """

    _name = "erplibre.sms.inbound"
    _description = "SMS entrant recu par la passerelle"
    _order = "received_at DESC, id DESC"
    _rec_name = "number"

    gateway_id = fields.Many2one("erplibre.sms.gateway", "Passerelle", readonly=True, ondelete="set null")
    device_id = fields.Char("Appareil", readonly=True, index=True)
    number = fields.Char("Numero", required=True, readonly=True, index=True)
    body = fields.Text("Contenu", readonly=True)
    received_at = fields.Datetime("Recu le", required=True, readonly=True, index=True)
    partner_id = fields.Many2one("res.partner", "Contact", readonly=True, ondelete="set null")
    is_opt_out = fields.Boolean("Desabonnement", readonly=True, index=True)
    blacklist_id = fields.Many2one("phone.blacklist", "Liste noire", readonly=True, ondelete="set null")
    external_id = fields.Char(
        "Identifiant du telephone", readonly=True, index=True,
        help="Identifiant attribue par le telephone, utilise pour ne pas "
             "enregistrer deux fois le meme message.",
    )

    _sql_constraints = [
        ("external_id_unique", "unique(external_id)", "Ce message entrant est deja enregistre."),
    ]

    @api.model
    def _record(self, gateway, payload):
        """Enregistre un message entrant et traite un eventuel desabonnement."""
        external_id = payload.get("id")
        if external_id and self.search_count([("external_id", "=", external_id)]):
            return self.browse()

        number = (payload.get("from") or "").strip()
        body = payload.get("body") or ""
        received_at = fields.Datetime.now()
        if payload.get("at"):
            try:
                received_at = fields.Datetime.to_datetime(
                    fields.Datetime.now().fromtimestamp(int(payload["at"]))
                )
            except (TypeError, ValueError, OSError):
                pass

        partner = self.env["res.partner"].sudo().search(
            ["|", ("phone", "=", number), ("mobile", "=", number)], limit=1
        ) if number else self.env["res.partner"]

        first_word = body.strip().split()[0].lower().strip(".,!;:") if body.strip() else ""
        is_opt_out = first_word in OPT_OUT_KEYWORDS

        record = self.create({
            "gateway_id": gateway.id if gateway else False,
            "device_id": gateway.device_id if gateway else payload.get("device"),
            "number": number or _("inconnu"),
            "body": body,
            "received_at": received_at,
            "partner_id": partner.id,
            "is_opt_out": is_opt_out,
            "external_id": external_id or False,
        })

        if is_opt_out and number:
            blacklist = self.env["phone.blacklist"].sudo().add(
                number, message=_("Desabonnement recu par SMS le %s.", received_at)
            )
            record.blacklist_id = blacklist
            _logger.info("erplibre_mobile_gateway: %s ajoute a la liste noire SMS", number)

        if partner:
            partner.sudo().message_post(
                body=_("SMS recu du %(number)s : %(body)s", number=number, body=body),
                message_type="comment",
            )
        return record
