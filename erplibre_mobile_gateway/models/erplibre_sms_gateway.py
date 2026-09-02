# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import json
import logging
import secrets
from datetime import timedelta

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

#: Delai d'attente des appels sortants d'escalade. Court volontairement : ces
#: appels partent depuis un cron, dont le temps est plafonne
#: (`limit_time_real_cron`, qui retombe sur `limit_time_real` = 120 s par
#: defaut). Une escalade lente tuerait le worker cron.
ESCALATION_TIMEOUT = 5

#: Limite de debit d'Android, verifiee dans les sources AOSP
#: (`SmsUsageMonitor.java`, etiquettes android-15.0.0_r36 et android-16.0.0_r3) :
#: DEFAULT_SMS_MAX_COUNT = 30 sur DEFAULT_SMS_CHECK_PERIOD = 60000 ms, compte
#: PAR NOM DE PAQUET et EN SEGMENTS. Au-dela, Android empile un AlertDialog
#: systeme -- sur un telephone que personne ne regarde, cela veut dire que rien
#: ne part. On garde une marge.
ANDROID_SEGMENTS_PER_MINUTE = 30
DEFAULT_SEGMENTS_PER_MINUTE = 24


class ErplibreSmsGateway(models.Model):
    """Une passerelle = un telephone Android qui envoie les SMS.

    Le telephone INTERROGE le serveur en HTTPS sortant : Odoo n'a jamais besoin
    de le joindre. C'est ce qui rend l'architecture insensible a une IP
    dynamique, a un NAT d'operateur, et supprime toute infrastructure
    intermediaire.
    """

    _name = "erplibre.sms.gateway"
    _description = "Passerelle mobile"
    _inherit = ["mail.thread"]
    _order = "sequence, id"

    name = fields.Char("Nom", required=True, default="Passerelle du studio")
    sequence = fields.Integer("Sequence", default=10)
    active = fields.Boolean("Actif", default=True)
    company_id = fields.Many2one(
        "res.company", "Societe", required=True, default=lambda self: self.env.company
    )
    device_id = fields.Char(
        "Identifiant de l'appareil", required=True, copy=False,
        default=lambda self: secrets.token_hex(8),
        help="Identifiant que le telephone presente a chaque interrogation.",
    )

    # -- Rythme d'interrogation ----------------------------------------
    poll_interval_seconds = fields.Integer(
        "Intervalle d'interrogation (secondes)", default=60,
        help="Rythme auquel le telephone demande s'il y a des SMS a envoyer. "
             "C'est la latence maximale d'une alerte : a 60 secondes, une "
             "annulation saisie a 18 h 00 part au plus tard a 18 h 01.",
    )
    redelivery_seconds = fields.Integer(
        "Delai avant nouvelle offre (secondes)", default=300,
        help="Un SMS remis au telephone mais jamais confirme est reproposé apres "
             "ce delai. C'est ce qui rattrape un telephone mort entre la "
             "reception et l'enregistrement du travail.",
    )
    last_poll_at = fields.Datetime("Derniere interrogation", readonly=True, index=True)

    # -- Garde-fous ----------------------------------------------------
    max_recipients_per_send = fields.Integer(
        "Destinataires maximum par envoi", default=60,
        help="Refuse a la composition, pas a l'envoi : une erreur levee dans "
             "l'API est avalee par `_process_queue` et ressort en « erreur "
             "serveur », puis est reessayee.",
    )
    segments_per_minute = fields.Integer(
        "Segments par minute", default=DEFAULT_SEGMENTS_PER_MINUTE,
        help="Consigne d'etalement transmise au telephone. Android bloque a 30 "
             "segments par minute et par application ; on garde une marge.",
    )
    send_deadline_seconds = fields.Integer(
        "Echeance d'envoi (secondes)", default=900,
        help="Au-dela, un envoi non confirme est declare expire et une alerte "
             "est levee.",
    )
    max_jobs_per_poll = fields.Integer(
        "Travaux remis par interrogation", default=25,
        help="Borne la taille d'une reponse. Le reste part a l'interrogation "
             "suivante.",
    )

    # -- Etat rapporte par le telephone --------------------------------
    last_status_json = fields.Text("Dernier etat rapporte", readonly=True)
    sms_permission_ok = fields.Boolean("Permission SEND_SMS accordee", readonly=True)
    sim_ready = fields.Boolean("Carte SIM prete", readonly=True)
    outbox_pending = fields.Integer("En attente sur le telephone", readonly=True)
    battery_percent = fields.Integer("Batterie (%)", readonly=True)
    battery_charging = fields.Boolean("En charge", readonly=True)
    app_version = fields.Char("Version de l'application", readonly=True)
    doze_exempt = fields.Boolean(
        "Dispense d'economie de batterie",
        readonly=True,
        help=(
            "Sans cette dispense, Android regroupe les reveils de"
            " l'application : mesure sur Pixel 2 XL, un cycle regle a 30 s"
            " tient 30 s en regime normal mais s'ouvre a plus de deux minutes"
            " des que l'appareil s'assoupit. La passerelle n'est pas en panne,"
            " elle est simplement en retard — ce qui, sur un canal d'alerte,"
            " revient au meme."
        ),
    )
    exact_alarms = fields.Boolean(
        "Alarmes exactes autorisees",
        readonly=True,
        help=(
            "Android 12 et suivants exigent une permission pour les alarmes"
            " exactes. Sans elle, les cycles se regroupent."
        ),
    )
    pacing_degraded = fields.Boolean(
        "Cadencement degrade",
        compute="_compute_pacing_degraded",
        store=True,
        help="Vrai des qu'un des deux reglages de cadencement manque.",
    )

    @api.depends("doze_exempt", "exact_alarms", "last_poll_at")
    def _compute_pacing_degraded(self):
        for record in self:
            # Tant que le telephone n'a jamais parle, on ne sait rien : ne pas
            # afficher un probleme de cadencement la ou il n'y a qu'un silence.
            record.pacing_degraded = bool(record.last_poll_at) and not (
                record.doze_exempt and record.exact_alarms
            )

    alarm_active = fields.Boolean("En alerte", readonly=True, index=True)
    alarm_since = fields.Datetime("En alerte depuis", readonly=True)
    alarm_reason = fields.Char("Motif de l'alerte", readonly=True)
    alarm_webhook_url = fields.Char(
        "Point d'acces d'escalade independant",
        help="Appele quand la passerelle est declaree muette. C'est ici qu'on "
             "branche un fournisseur de SMS payant. Sans lui, l'alerte de panne "
             "part par courriel -- c'est-a-dire par le canal meme dont "
             "l'insuffisance justifiait la passerelle. Un canal d'urgence dont "
             "le detecteur de panne est le canal qu'il remplace n'a pas de "
             "detecteur de panne.",
    )

    allowed_user_ids = fields.Many2many(
        "res.users", "erplibre_sms_gateway_user_rel", "gateway_id", "user_id",
        string="Utilisateurs autorises a envoyer",
        help="Vide = tous les membres du groupe « Passerelle mobile / Envoi ».",
    )

    is_healthy = fields.Boolean("En bonne sante", compute="_compute_is_healthy")
    dispatch_count = fields.Integer("Envois suivis", compute="_compute_dispatch_count")
    silence_seconds = fields.Integer("Silence (secondes)", compute="_compute_is_healthy")

    _sql_constraints = [
        ("device_id_unique", "unique(device_id)", "Cet identifiant d'appareil est deja utilise."),
    ]

    @api.depends("alarm_active", "last_poll_at", "sms_permission_ok", "sim_ready")
    def _compute_is_healthy(self):
        now = fields.Datetime.now()
        for gateway in self:
            if gateway.last_poll_at:
                gateway.silence_seconds = int((now - gateway.last_poll_at).total_seconds())
            else:
                gateway.silence_seconds = 0
            gateway.is_healthy = bool(
                not gateway.alarm_active
                and gateway.last_poll_at
                and gateway.sms_permission_ok
                and gateway.sim_ready
            )

    def _compute_dispatch_count(self):
        counts = dict(self.env["erplibre.sms.dispatch"]._read_group(
            [("gateway_id", "in", self.ids)], ["gateway_id"], ["__count"],
        ))
        for gateway in self:
            gateway.dispatch_count = counts.get(gateway, 0)

    @api.constrains("segments_per_minute")
    def _check_segments_per_minute(self):
        for gateway in self:
            if gateway.segments_per_minute > ANDROID_SEGMENTS_PER_MINUTE:
                raise UserError(_(
                    "Android bloque a %(limit)s segments par minute et par application. "
                    "Au-dela, un dialogue systeme apparait sur le telephone et les "
                    "messages ne partent pas.", limit=ANDROID_SEGMENTS_PER_MINUTE,
                ))

    @api.constrains("poll_interval_seconds")
    def _check_poll_interval(self):
        for gateway in self:
            if gateway.poll_interval_seconds < 15:
                raise UserError(_(
                    "Un intervalle sous 15 secondes noie le serveur sans gagner de "
                    "latence utile : la limite de debit d'Android impose de toute "
                    "facon plusieurs minutes pour un groupe."
                ))

    # ------------------------------------------------------------------
    # Remise des travaux
    # ------------------------------------------------------------------
    def _claim_pending(self):
        """Travaux a remettre au telephone lors d'une interrogation.

        Deux familles : ceux qui n'ont jamais ete remis, et ceux qui l'ont ete
        mais que le telephone n'a jamais confirmes -- il a pu mourir entre la
        reception et l'enregistrement. Sans cette seconde famille, un SMS
        disparaitrait en silence, ce qui est le mode de defaillance qu'on
        s'interdit.

        Le doublon est impossible cote telephone : sa file est indexee par
        l'identifiant du SMS et ignore les insertions en double.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        retry_before = now - timedelta(seconds=self.redelivery_seconds or 300)
        dispatches = self.env["erplibre.sms.dispatch"].sudo().search(
            [
                ("gateway_id", "=", self.id),
                "|",
                ("state", "=", "queued"),
                "&", ("state", "=", "published"), ("published_at", "<=", retry_before),
            ],
            order="requested_at asc",
            limit=self.max_jobs_per_poll or 25,
        )
        if dispatches:
            dispatches.write({"state": "published", "published_at": now})
        return dispatches

    @api.model
    def _payload_for(self, dispatches):
        """Regroupe par corps de message : le texte n'est ecrit qu'une fois."""
        grouped = {}
        for dispatch in dispatches:
            grouped.setdefault(dispatch.body or "", []).append(
                {"u": dispatch.sms_uuid, "n": dispatch.number}
            )
        return [{"body": body, "to": recipients} for body, recipients in grouped.items()]

    # ------------------------------------------------------------------
    # Vivacite et alertes
    # ------------------------------------------------------------------
    def _record_poll(self, status):
        """Enregistre une interrogation. Chaque appel vaut signal de vie.

        Fusionner le signal de vie dans l'interrogation supprime un point
        d'acces et rend la detection de panne exacte : une passerelle qui
        n'interroge plus EST hors service, par definition.
        """
        self.ensure_one()
        status = status or {}
        values = {
            "last_poll_at": fields.Datetime.now(),
            "last_status_json": json.dumps(status, indent=1, ensure_ascii=False),
            "sms_permission_ok": bool(status.get("sms_permission")),
            "sim_ready": bool(status.get("sim_ready")),
            "outbox_pending": int(status.get("outbox_pending") or 0),
            "battery_percent": int(status.get("battery") or 0),
            "battery_charging": bool(status.get("charging")),
            "app_version": status.get("app_version") or False,
            "doze_exempt": bool(status.get("doze_exempt")),
            "exact_alarms": bool(status.get("exact_alarms")),
        }
        self.sudo().write(values)
        # Une permission revoquee ou une SIM absente est une panne, meme si le
        # telephone parle : il parle pour dire qu'il ne peut pas envoyer.
        if not values["sms_permission_ok"]:
            self.sudo()._raise_alarm(
                _("La permission d'envoi de SMS n'est plus accordee sur le telephone.")
            )
        elif not values["sim_ready"]:
            self.sudo()._raise_alarm(_("La carte SIM du telephone n'est pas prete."))
        elif self.alarm_active:
            self.sudo()._clear_alarm()
        return True

    def _raise_alarm(self, reason):
        self.ensure_one()
        if self.alarm_active and self.alarm_reason == reason:
            return True
        self.write({
            "alarm_active": True,
            "alarm_since": self.alarm_since or fields.Datetime.now(),
            "alarm_reason": reason[:256],
        })
        self.message_post(body=_("Passerelle mobile en alerte : %s", reason))
        self._escalate(reason)
        return True

    def _clear_alarm(self):
        self.ensure_one()
        if self.alarm_active:
            self.write({"alarm_active": False, "alarm_since": False, "alarm_reason": False})
            self.message_post(body=_("Passerelle mobile revenue en service."))
        return True

    def _escalate(self, reason):
        """Alerte sur un canal INDEPENDANT de celui qui est surveille."""
        self.ensure_one()
        if self.alarm_webhook_url:
            try:
                requests.post(
                    self.alarm_webhook_url,
                    json={"gateway": self.name, "device": self.device_id, "reason": reason},
                    timeout=ESCALATION_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001 - une escalade ne doit jamais propager
                _logger.error("erplibre_mobile_gateway: escalade par point d'acces echouee : %s", exc)
        else:
            _logger.error(
                "erplibre_mobile_gateway: passerelle %s en alerte et AUCUN canal d'escalade "
                "independant configure. L'alerte ne partira que par courriel, "
                "c'est-a-dire par le canal que la passerelle etait censee "
                "remplacer. Motif : %s", self.name, reason,
            )
        return True

    @api.model
    def _cron_check_heartbeat(self):
        """Declare muette toute passerelle qui n'interroge plus.

        La tolerance vaut trois intervalles : deux interrogations manquees
        peuvent tenir a une coupure reseau passagere, trois signalent une panne.
        """
        now = fields.Datetime.now()
        alarmed = 0
        for gateway in self.search([]):
            grace = max((gateway.poll_interval_seconds or 60) * 3, 180)
            if not gateway.last_poll_at:
                gateway._raise_alarm(_("La passerelle n'a jamais interroge le serveur."))
                alarmed += 1
                continue
            silence = (now - gateway.last_poll_at).total_seconds()
            if silence > grace:
                gateway._raise_alarm(_(
                    "Aucune interrogation depuis %(minutes)s minutes.",
                    minutes=int(silence // 60),
                ))
                alarmed += 1
        return alarmed
