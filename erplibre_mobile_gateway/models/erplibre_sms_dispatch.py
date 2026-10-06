# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

#: Rang de chaque etat. Un rapport ne peut jamais faire REGRESSER un envoi.
STATE_RANK = {
    "queued": 0,
    "published": 1,
    "submitted": 2,
    "delivered": 3,
    "failed": 3,
    "expired": 3,
}

#: Etats terminaux. Une fois atteints, plus aucun rapport n'est applique.
#: C'est ce qui empeche un `delivered` rejoue d'ecraser un `failed` et de faire
#: croire a l'expediteur qu'il a prevenu ses destinataires.
TERMINAL_STATES = {"delivered", "failed", "expired"}

#: Codes d'erreur Android -> `provider_error` du coeur Odoo.
#:
#: Contrainte non negociable : `sms.tracker._action_update_from_provider_error`
#: calcule `failure_type = f"sms_{provider_error}"` et le remplace par
#: `"unknown"` s'il n'appartient pas a `sms.sms.DELIVERY_ERRORS`, qui vaut
#: {sms_expired, sms_not_delivered, sms_invalid_destination, sms_not_allowed,
#: sms_rejected}. Tout code hors de cette liste serait donc aplati en
#: « Unknown error » cote utilisateur. Le detail fin reste sur cet
#: enregistrement, dans `android_code`.
ANDROID_CODE_TO_PROVIDER_ERROR = {
    # Erreurs remontees par SmsManager
    "RESULT_ERROR_GENERIC_FAILURE": "not_delivered",
    "RESULT_ERROR_NO_SERVICE": "not_delivered",
    "RESULT_ERROR_RADIO_OFF": "not_delivered",
    "RESULT_ERROR_NULL_PDU": "rejected",
    "RESULT_ERROR_LIMIT_EXCEEDED": "not_allowed",
    "RESULT_ERROR_FDN_CHECK_FAILURE": "not_allowed",
    "RESULT_ERROR_SHORT_CODE_NOT_ALLOWED": "not_allowed",
    "RESULT_ERROR_SHORT_CODE_NEVER_ALLOWED": "not_allowed",
    "RESULT_ERROR_NO_DEFAULT_SMS_APP": "not_allowed",
    "RESULT_NETWORK_REJECT": "rejected",
    "RESULT_INVALID_ARGUMENTS": "rejected",
    "RESULT_INVALID_STATE": "not_delivered",
    "RESULT_NO_MEMORY": "not_delivered",
    "RESULT_INVALID_SMS_FORMAT": "rejected",
    "RESULT_SYSTEM_ERROR": "not_delivered",
    "RESULT_MODEM_ERROR": "not_delivered",
    "RESULT_NETWORK_ERROR": "not_delivered",
    "RESULT_ENCODING_ERROR": "rejected",
    "RESULT_INVALID_SMSC_ADDRESS": "rejected",
    "RESULT_OPERATION_NOT_ALLOWED": "not_allowed",
    "RESULT_NO_RESOURCES": "not_delivered",
    "RESULT_CANCELLED": "not_delivered",
    "RESULT_REQUEST_NOT_SUPPORTED": "not_allowed",
    "RESULT_NO_BLUETOOTH_SERVICE": "not_delivered",
    "RESULT_RIL_RADIO_NOT_AVAILABLE": "not_delivered",
    "RESULT_RIL_NETWORK_REJECT": "rejected",
    "RESULT_RIL_SIM_ABSENT": "not_delivered",
    # Codes propres a la passerelle
    "GATEWAY_NO_PERMISSION": "not_allowed",
    "GATEWAY_SIM_ABSENT": "not_delivered",
    "GATEWAY_INVALID_NUMBER": "invalid_destination",
    "GATEWAY_DEADLINE": "expired",
    "GATEWAY_ABANDONED": "expired",
    "GATEWAY_BLACKLISTED": "not_allowed",
}


class ErplibreSmsDispatch(models.Model):
    """Suivi d'un SMS confie a la passerelle mobile.

    Cet enregistrement existe parce que `sms.sms` est ephemere : des qu'un
    fournisseur retourne un etat de succes, `_send_with_api` positionne
    `to_delete = True` (sms_sms.py ligne 223, `unlink_sent` valant True par
    defaut et etant ce que passe `_process_queue`), et l'autovacuum
    `_gc_device` supprime physiquement la ligne. Or l'etat « remis au telephone »
    EST un succes du point de vue du cœur : la piste d'audit disparaitrait donc
    avant meme que le telephone ait vu la demande.

    C'est ici que vivent l'utilisateur demandeur, le corps du message, l'etat
    reel et l'historique -- c'est-a-dire le registre exigible au titre de la
    Loi 25 pour un envoi a des personnes physiques.
    """

    _name = "erplibre.sms.dispatch"
    _description = "SMS confie a la passerelle mobile"
    _order = "id DESC"
    _rec_name = "number"

    sms_uuid = fields.Char("UUID du SMS", required=True, index=True, readonly=True)
    batch_id = fields.Char("Lot d'envoi", index=True, readonly=True)
    number = fields.Char("Numero", required=True, readonly=True)
    body = fields.Text("Contenu", readonly=True)
    partner_id = fields.Many2one("res.partner", "Destinataire", readonly=True, ondelete="set null")
    company_id = fields.Many2one("res.company", "Societe", required=True, readonly=True)
    gateway_id = fields.Many2one("erplibre.sms.gateway", "Passerelle", readonly=True, ondelete="set null")

    # Audit : conserve ici parce que `sms.sms` ne survit pas.
    requested_by_uid = fields.Many2one("res.users", "Demande par", readonly=True, ondelete="set null")
    requested_at = fields.Datetime("Demande le", readonly=True, default=fields.Datetime.now)

    state = fields.Selection(
        [
            ("queued", "En file"),
            ("published", "Remis au telephone"),
            ("submitted", "Remis au reseau"),
            ("delivered", "Recu par le destinataire"),
            ("failed", "Echec"),
            ("expired", "Expire sans envoi"),
        ],
        "Etat", default="queued", required=True, readonly=True, index=True,
    )
    #: Numero de sequence du dernier rapport applique, attribue par le telephone.
    #: Un rapport dont la sequence n'est pas strictement superieure est ignore :
    #: c'est la protection contre le rejeu et contre l'arrivee hors ordre, que
    #: la garde de monotonie du cœur n'assure PAS (pour un nouveau statut
    #: `sent`, sa liste d'ignorance ne contient que `sent`, donc un `sent`
    #: tardif ecrase un `bounce`).
    report_seq = fields.Integer("Sequence du dernier rapport", default=0, readonly=True)

    published_at = fields.Datetime("Remis au telephone le", readonly=True)
    send_deadline = fields.Datetime(
        "Echeance d'envoi", readonly=True, index=True,
        help="Passe cette date sans confirmation du telephone, l'envoi est declare expire "
             "et une alerte est levee. C'est le seul filet qui empeche un silence indefini.",
    )
    submitted_at = fields.Datetime("Remis au reseau le", readonly=True)
    delivered_at = fields.Datetime("Recu le", readonly=True)
    ended_at = fields.Datetime("Termine le", readonly=True)

    segments_total = fields.Integer("Segments", readonly=True, default=0)
    encoding = fields.Selection(
        [("gsm7", "GSM-7"), ("ucs2", "UCS-2")], "Encodage", readonly=True,
        help="Un message contenant un caractere hors alphabet GSM 03.38 -- dont "
             "le « c » cedille minuscule -- bascule en UCS-2 et tombe a "
             "70 caracteres par segment au lieu de 160.",
    )
    android_code = fields.Char(
        "Code Android", readonly=True,
        help="Code brut renvoye par le telephone. Conserve ici parce que le cœur "
             "d'Odoo aplatit tout code inconnu en « Unknown error ».",
    )
    failure_reason = fields.Char("Detail de l'echec", readonly=True)
    device_id = fields.Char("Appareil", readonly=True, index=True)

    _sql_constraints = [
        ("sms_uuid_unique", "unique(sms_uuid)", "Un suivi existe deja pour ce SMS."),
    ]

    # ------------------------------------------------------------------
    # Machine a etats
    # ------------------------------------------------------------------
    def _apply_event(self, state, seq=None, android_code=None, reason=None,
                     device_id=None, event_time=None):
        """Applique un rapport de la passerelle, si et seulement s'il progresse.

        Retourne True si l'evenement a ete applique, False s'il a ete ignore.
        Un evenement ignore n'est pas une erreur : c'est le cas normal d'un
        reprise ou d'un rapport arrive en retard.

        :param seq: numero de sequence attribue par le telephone, qui doit etre
            STRICTEMENT superieur au dernier applique. `None` signifie
            « transition decidee par le serveur » (expiration, echec de
            publication) et prend automatiquement le rang suivant.

            Une valeur de 0 ou absente venant d'un rapport est REJETEE. C'est
            volontaire : un rapport sans sequence ne peut pas etre ordonne, donc
            rien ne garantit qu'il n'est pas un rejeu. L'accepter rouvrirait
            exactement la faille que cette sequence existe pour fermer -- un
            `delivered` rejoue apres un `failed` ferait croire a l'expediteur
            qu'il a prevenu ses destinataires.
        """
        self.ensure_one()
        if state not in STATE_RANK:
            _logger.warning("erplibre_mobile_gateway: etat inconnu %r pour %s", state, self.sms_uuid)
            return False

        if self.state in TERMINAL_STATES:
            _logger.info(
                "erplibre_mobile_gateway: rapport %r ignore pour %s, deja terminal en %r",
                state, self.sms_uuid, self.state,
            )
            return False

        server_originated = seq is None
        if server_originated:
            seq = self.report_seq + 1
        elif seq <= self.report_seq:
            _logger.info(
                "erplibre_mobile_gateway: rapport %r ignore pour %s, sequence %s <= %s",
                state, self.sms_uuid, seq, self.report_seq,
            )
            return False

        if STATE_RANK[state] < STATE_RANK[self.state]:
            _logger.info(
                "erplibre_mobile_gateway: rapport %r ignore pour %s, regression depuis %r",
                state, self.sms_uuid, self.state,
            )
            return False

        now = event_time or fields.Datetime.now()
        values = {"state": state, "report_seq": seq}
        if android_code:
            values["android_code"] = android_code
        if reason:
            values["failure_reason"] = reason[:512]
        if device_id:
            values["device_id"] = device_id
        if state == "submitted":
            values["submitted_at"] = now
        elif state == "delivered":
            values["delivered_at"] = now
            values["ended_at"] = now
        elif state in ("failed", "expired"):
            values["ended_at"] = now
        self.write(values)
        self._notify_core_tracker(state, android_code=android_code, reason=reason)
        return True

    def _notify_core_tracker(self, state, android_code=None, reason=None):
        """Repercute l'etat sur le `sms.tracker`, donc sur les notifications.

        Les trackers sont volontairement dissocies des `sms.sms` par le cœur
        (docstring de `sms.tracker`) : ils survivent a la suppression du SMS,
        ce qui rend la mise a jour asynchrone possible.
        """
        self.ensure_one()
        tracker = self.env["sms.tracker"].search([("sms_uuid", "=", self.sms_uuid)], limit=1)
        if not tracker:
            return
        if state == "submitted":
            tracker._action_update_from_sms_state("pending")
        elif state == "delivered":
            tracker._action_update_from_sms_state("sent")
        elif state in ("failed", "expired"):
            provider_error = ANDROID_CODE_TO_PROVIDER_ERROR.get(
                android_code or "", "expired" if state == "expired" else "not_delivered"
            )
            tracker.with_context(
                sms_known_failure_reason=reason or android_code or _("Passerelle mobile")
            )._action_update_from_provider_error(provider_error)

    # ------------------------------------------------------------------
    # Echeances
    # ------------------------------------------------------------------
    @api.model
    def _cron_expire_stale(self):
        """Declare expires les envois que le telephone n'a jamais confirmes.

        Sans ce cron, un telephone eteint produit un silence indefini : Odoo
        croit avoir envoye, personne n'a rien recu, et rien ne l'indique.
        """
        stale = self.search([
            ("state", "in", ["queued", "published"]),
            ("send_deadline", "<=", fields.Datetime.now()),
        ], limit=1000)
        for dispatch in stale:
            dispatch._apply_event(
                "expired",
                android_code="GATEWAY_DEADLINE",
                reason=_("Le telephone n'a pas confirme avant l'echeance d'envoi."),
            )
        if not stale:
            return 0

        _logger.warning(
            "erplibre_mobile_gateway: %s envois expires sans confirmation",
            len(stale),
        )

        # On met en alerte la passerelle RESPONSABLE, jamais une au hasard.
        #
        # Un envoi porte parfois une passerelle vide : jamais renseignee, ou
        # effacee par le `ondelete="set null"` du champ. L'ancien repli
        # `search([], limit=1)` ignorait alors la societe et pouvait mettre en
        # alerte le telephone SAIN d'un autre organisme — et une alerte bloque
        # tous ses envois. La societe, elle, est toujours connue (`company_id`
        # est requis) : on retombe donc sur la passerelle que cette societe
        # aurait utilisee, par la MEME resolution que l'envoi.
        cibles = {}

        def viser(passerelle, envois):
            """Cumule les envois par passerelle, pour n'alerter qu'une fois."""
            precedent = cibles.get(passerelle.id)
            cibles[passerelle.id] = (
                passerelle,
                (precedent[1] | envois) if precedent else envois,
            )

        for passerelle in stale.gateway_id:
            viser(
                passerelle,
                stale.filtered(lambda d, g=passerelle: d.gateway_id == g),
            )

        orphelins = stale.filtered(lambda d: not d.gateway_id)
        for societe in orphelins.company_id:
            concernes = orphelins.filtered(
                lambda d, s=societe: d.company_id == s
            )
            passerelle = self.env["erplibre.sms.gateway"]._for_company(societe)
            if not passerelle:
                # Rien a alerter : le dire, plutot que de choisir une
                # passerelle etrangere pour avoir l'air d'agir.
                _logger.warning(
                    "erplibre_mobile_gateway: %s envois expires sans"
                    " passerelle pour %s, et aucune passerelle utilisable"
                    " dans cette societe : aucune alerte levee.",
                    len(concernes),
                    societe.display_name,
                )
                continue
            viser(passerelle, concernes)

        for passerelle, concernes in cibles.values():
            passerelle._raise_alarm(
                reason=_(
                    "%(count)s SMS n'ont pas ete confirmes par la passerelle"
                    " avant leur echeance.",
                    count=len(concernes),
                ),
            )
        return len(stale)
