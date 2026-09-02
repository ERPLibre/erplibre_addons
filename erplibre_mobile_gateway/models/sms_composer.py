# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from ..tools.sms_api_erplibre import analyse_body, non_gsm7_characters


class SmsComposer(models.TransientModel):
    """Garde-fous de la passerelle, poses AU BON ENDROIT.

    Ils ne peuvent pas vivre dans `_send_sms_batch` : `UserError` herite
    d'`Exception`, et `_send_with_api` (sms_sms.py lignes 206-212) attrape toute
    exception avec `raise_exception=False` -- ce que passe `_process_queue`
    (ligne 167). Un plafond viole y produirait donc un « erreur serveur »
    incomprehensible, ET serait reessaye par tout mecanisme de reprise.

    Le cœur lui-meme place ses propres refus ici (`action_send_sms`, lignes
    179-184) : on suit la meme convention.
    """

    _inherit = "sms.composer"

    erplibre_gateway_id = fields.Many2one(
        "erplibre.sms.gateway", compute="_compute_erplibre_gateway_id",
        help="Passerelle qui traitera cet envoi, si la societe est configuree ainsi.",
    )
    erplibre_estimate = fields.Char(
        "Estimation", compute="_compute_erplibre_estimate",
        help="Duree estimee de l'envoi, imposee par la limite de debit d'Android.",
    )

    @api.depends("composition_mode")
    def _compute_erplibre_gateway_id(self):
        for composer in self:
            company = composer.env.company
            gateway = self.env["erplibre.sms.gateway"]
            if company.sms_provider == "erplibre":
                gateway = gateway.search(
                    [("company_id", "=", company.id), ("active", "=", True)], limit=1
                )
            composer.erplibre_gateway_id = gateway

    @api.depends("body", "recipient_valid_count", "erplibre_gateway_id")
    def _compute_erplibre_estimate(self):
        for composer in self:
            gateway = composer.erplibre_gateway_id
            if not gateway or not composer.body:
                composer.erplibre_estimate = False
                continue
            encoding, segments = analyse_body(composer.body)
            recipients = composer._erplibre_recipient_count()
            total_segments = max(segments, 1) * max(recipients, 1)
            rate = gateway.segments_per_minute or 24
            seconds = int(math.ceil(total_segments / rate * 60))
            label = _(
                "%(recipients)s destinataire(s), %(segments)s segment(s) en %(encoding)s, "
                "environ %(minutes)s min %(seconds)s s d'envoi.",
                recipients=recipients,
                segments=total_segments,
                encoding=encoding.upper(),
                minutes=seconds // 60,
                seconds=seconds % 60,
            )
            if encoding == "ucs2":
                offenders = "".join(non_gsm7_characters(composer.body)[:8])
                label += _(
                    " Les caracteres « %(chars)s » font basculer le message en UCS-2 : "
                    "70 caracteres par segment au lieu de 160, donc deux fois plus de "
                    "temps d'envoi.", chars=offenders,
                )
            composer.erplibre_estimate = label

    def _erplibre_recipient_count(self):
        self.ensure_one()
        if self.composition_mode in ("numbers", "mass"):
            if self.composition_mode == "numbers":
                return len([n for n in (self.numbers or "").split(",") if n.strip()])
            return self.recipient_valid_count or 0
        return 1

    def _erplibre_check_allowed(self):
        """Refuse l'envoi si la personne n'y est pas autorisee, ou si le lot est trop gros."""
        self.ensure_one()
        gateway = self.erplibre_gateway_id
        if not gateway:
            return

        if gateway.alarm_active:
            raise UserError(_(
                "La passerelle SMS « %(name)s » est en alerte : %(reason)s\n\n"
                "Un envoi lance maintenant ne partirait probablement pas. Reglez la "
                "passerelle, ou prevenez par un autre moyen.",
                name=gateway.name, reason=gateway.alarm_reason or _("cause inconnue"),
            ))

        allowed = gateway.allowed_user_ids
        if allowed and self.env.user not in allowed:
            raise AccessError(_(
                "Vous n'etes pas autorise a envoyer des SMS par la passerelle "
                "« %(name)s ». Un SMS coute de l'argent et engage l'organisme : le "
                "droit d'envoi est volontairement restreint.", name=gateway.name,
            ))

        recipients = self._erplibre_recipient_count()
        limit = gateway.max_recipients_per_send or 0
        if limit and recipients > limit:
            raise UserError(_(
                "%(count)s destinataires pour un maximum de %(limit)s par envoi.\n\n"
                "Ce plafond protege contre l'envoi de masse accidentel et contre le "
                "filtrage de l'operateur. Decoupez l'envoi, ou faites relever le "
                "plafond sur la passerelle.",
                count=recipients, limit=limit,
            ))

    def action_send_sms(self):
        self._erplibre_check_allowed()
        return super().action_send_sms()

    def action_send_sms_mass_now(self):
        self._erplibre_check_allowed()
        return super().action_send_sms_mass_now()
