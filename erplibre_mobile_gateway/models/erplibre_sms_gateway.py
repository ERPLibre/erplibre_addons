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

#: Ce qui distingue un materiel d'un autre, et rien de plus.
#:
#: Le module a d'abord ete ecrit pour un telephone Android, et jugeait donc
#: TOUTE passerelle sur des criteres Android : dispense d'economie de batterie,
#: alarmes exactes, niveau de batterie, plafond de debit par application.
#: Applique a un modem USB, ce jugement est faux de bout en bout — il n'a rien
#: de tout cela, et se serait affiche « cadencement degrade », batterie a zero,
#: brise a trente segments par minute pour une limite qui ne le concerne pas.
#:
#: Chaque entree ne dit donc que les traits qui CHANGENT selon l'appareil. Ce
#: qui ne change pas — interroger, envoyer, rendre compte — n'a pas a figurer
#: ici, et l'ajout d'un troisieme materiel ne devrait toucher que ce
#: dictionnaire.
MATERIELS = {
    "mobile": {
        "libelle": "Telephone Android",
        # Doze et alarmes exactes : deux reglages du systeme, sans equivalent
        # ailleurs, qui font glisser les reveils quand ils manquent.
        "cadencement_systeme": True,
        "batterie": True,
        # Plafond impose par l'appareil, en segments par minute. 0 = aucun.
        "plafond_segments": ANDROID_SEGMENTS_PER_MINUTE,
        # L'appel se MET EN FILE : l'application le prend a son tour
        # d'interrogation, et il part depuis le telephone.
        "appels_en_file": True,
        "sans_envoi": (
            "La permission d'envoi de SMS n'est plus accordee sur " "le telephone."
        ),
        "sans_sim": "La carte SIM du telephone n'est pas prete.",
    },
    "modem": {
        "libelle": "Modem USB",
        "cadencement_systeme": False,
        "batterie": False,
        "plafond_segments": 0,
        # L'appel NE se met PAS en file : le softphone du navigateur le place
        # en direct, et le service de voix compose sur la SIM. Le mettre en
        # file le confierait a l'agent des SMS, qui refuse les appels — le
        # cycle doit rendre la main en quelques secondes quand un appel dure
        # des minutes.
        "appels_en_file": False,
        "sans_envoi": "L'agent ne peut plus commander le modem.",
        "sans_sim": "La carte SIM du modem n'est pas enregistree au reseau.",
    },
}

MATERIEL_DEFAUT = "mobile"


class ErplibreSmsGateway(models.Model):
    """Une passerelle = un appareil qui envoie les SMS par sa propre carte SIM.

    Un telephone Android ou un modem USB : voir `MATERIELS` pour ce qui les
    distingue, qui tient en quatre traits. Le PROTOCOLE, lui, est le meme —
    rien dans les trois routes n'est propre a Android.

    L'appareil INTERROGE le serveur en HTTPS sortant : Odoo n'a jamais besoin
    de le joindre. C'est ce qui rend l'architecture insensible a une IP
    dynamique, a un NAT d'operateur, et supprime toute infrastructure
    intermediaire.
    """

    _name = "erplibre.sms.gateway"
    _description = "Passerelle mobile"
    _inherit = ["mail.thread"]
    _order = "sequence, id"

    name = fields.Char("Nom", required=True, default="Passerelle du studio")
    kind = fields.Selection(
        [(cle, trait["libelle"]) for cle, trait in MATERIELS.items()],
        "Materiel",
        required=True,
        default=MATERIEL_DEFAUT,
        help="Decide des criteres de sante appliques a cette passerelle. Un "
        "modem juge sur les criteres d'un telephone se declare en panne "
        "sans l'etre.",
    )
    sequence = fields.Integer("Sequence", default=10)
    active = fields.Boolean("Actif", default=True)
    company_id = fields.Many2one(
        "res.company", "Societe", required=True, default=lambda self: self.env.company
    )
    device_id = fields.Char(
        "Identifiant de l'appareil",
        required=True,
        copy=False,
        default=lambda self: secrets.token_hex(8),
        help="Identifiant que l'appareil presente a chaque interrogation.",
    )

    # -- Rythme d'interrogation ----------------------------------------
    poll_interval_seconds = fields.Integer(
        "Intervalle d'interrogation (secondes)",
        default=60,
        help="Rythme auquel l'appareil demande s'il y a des SMS a envoyer. "
        "C'est la latence maximale d'une alerte : a 60 secondes, une "
        "annulation saisie a 18 h 00 part au plus tard a 18 h 01.",
    )
    redelivery_seconds = fields.Integer(
        "Delai avant nouvelle offre (secondes)",
        default=300,
        help="Un SMS remis a l'appareil mais jamais confirme est reproposé apres "
        "ce delai. C'est ce qui rattrape un appareil mort entre la "
        "reception et l'enregistrement du travail.",
    )
    last_poll_at = fields.Datetime("Derniere interrogation", readonly=True, index=True)

    # -- Garde-fous ----------------------------------------------------
    max_recipients_per_send = fields.Integer(
        "Destinataires maximum par envoi",
        default=60,
        help="Refuse a la composition, pas a l'envoi : une erreur levee dans "
        "l'API est avalee par `_process_queue` et ressort en « erreur "
        "serveur », puis est reessayee.",
    )
    segments_per_minute = fields.Integer(
        "Segments par minute",
        default=DEFAULT_SEGMENTS_PER_MINUTE,
        help="Consigne d'etalement transmise a l'appareil. Android bloque a 30 "
        "segments par minute et par application ; on garde une marge. Un "
        "modem n'a pas ce plafond, et le sien vient du reseau.",
    )
    send_deadline_seconds = fields.Integer(
        "Echeance d'envoi (secondes)",
        default=900,
        help="Au-dela, un envoi non confirme est declare expire et une alerte "
        "est levee.",
    )
    max_jobs_per_poll = fields.Integer(
        "Travaux remis par interrogation",
        default=25,
        help="Borne la taille d'une reponse. Le reste part a l'interrogation "
        "suivante.",
    )

    # -- Etat rapporte par le telephone --------------------------------
    last_status_json = fields.Text("Dernier etat rapporte", readonly=True)
    sms_permission_ok = fields.Boolean(
        "Envoi autorise par l'appareil",
        readonly=True,
        help="Sous Android, la permission SEND_SMS. Pour un modem, la capacite "
        "de l'agent a le commander. Dans les deux cas : cet appareil "
        "peut-il, en ce moment, remettre un SMS au reseau.",
    )
    sim_ready = fields.Boolean("Carte SIM prete", readonly=True)
    # La boite vocale de l'OPERATEUR, lue sur la SIM par le service du modem.
    # Le drapeau dit « au moins un message », jamais combien : le reseau peut
    # laisser le compte a zero.
    voicemail_waiting = fields.Boolean(
        "Message dans la boite vocale",
        readonly=True,
        index=True,
        help="Lu sur la carte SIM, dans le fichier ou le reseau inscrit qu'un "
        "message attend chez l'operateur. Retombe quand la boite est videe.",
    )
    voicemail_since = fields.Datetime(
        "Message signale depuis",
        readonly=True,
        help="Premiere lecture du drapeau leve. A une minute pres : le service "
        "relit la SIM a cette cadence, et le drapeau lui-meme se leve une "
        "vingtaine de secondes apres le depot.",
    )
    voicemail_checked_at = fields.Datetime(
        "Boite vocale lue le",
        readonly=True,
        help="Derniere transmission du service. Seuls les changements sont "
        "transmis : une date ancienne ne dit donc pas que la lecture a "
        "cesse, seulement que rien n'a change depuis.",
    )
    outbox_pending = fields.Integer("En attente sur l'appareil", readonly=True)
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

    @api.depends("doze_exempt", "exact_alarms", "last_poll_at", "kind")
    def _compute_pacing_degraded(self):
        for record in self:
            # Tant que l'appareil n'a jamais parle, on ne sait rien : ne pas
            # afficher un probleme de cadencement la ou il n'y a qu'un silence.
            #
            # Et ne le juger que la ou le systeme peut le degrader : un
            # processus sur un hote n'a ni Doze ni permission d'alarme a
            # demander, et l'y declarer degrade signalerait une panne qui ne
            # peut pas s'y produire.
            record.pacing_degraded = (
                bool(record.last_poll_at)
                and record._trait("cadencement_systeme")
                and not (record.doze_exempt and record.exact_alarms)
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

    notify_user_ids = fields.Many2many(
        "res.users",
        "erplibre_sms_gateway_notify_rel",
        "gateway_id",
        "user_id",
        string="Utilisateurs prevenus",
        help="Qui voit arriver un SMS ou un appel entrant. Vide = tous les "
        "membres du groupe « Passerelle mobile / Envoi » de la societe.",
    )

    allowed_user_ids = fields.Many2many(
        "res.users",
        "erplibre_sms_gateway_user_rel",
        "gateway_id",
        "user_id",
        string="Utilisateurs autorises a envoyer",
        help="Vide = tous les membres du groupe « Passerelle mobile / Envoi ».",
    )

    is_healthy = fields.Boolean("En bonne sante", compute="_compute_is_healthy")
    dispatch_count = fields.Integer("Envois suivis", compute="_compute_dispatch_count")
    silence_seconds = fields.Integer(
        "Silence (secondes)", compute="_compute_is_healthy"
    )
    montre_batterie = fields.Boolean(compute="_compute_traits_affiches")
    montre_cadencement = fields.Boolean(compute="_compute_traits_affiches")
    is_company_default = fields.Boolean(
        "Envoie pour la societe",
        compute="_compute_is_company_default",
        help="Vrai pour la passerelle que la societe utilise reellement. Sans "
        "choix explicite dans les reglages, c'est la premiere active par "
        "sequence.",
    )

    _sql_constraints = [
        (
            "device_id_unique",
            "unique(device_id)",
            "Cet identifiant d'appareil est deja utilise.",
        ),
    ]

    @api.depends("alarm_active", "last_poll_at", "sms_permission_ok", "sim_ready")
    def _compute_is_healthy(self):
        now = fields.Datetime.now()
        for gateway in self:
            if gateway.last_poll_at:
                gateway.silence_seconds = int(
                    (now - gateway.last_poll_at).total_seconds()
                )
            else:
                gateway.silence_seconds = 0
            gateway.is_healthy = bool(
                not gateway.alarm_active
                and gateway.last_poll_at
                and gateway.sms_permission_ok
                and gateway.sim_ready
            )

    @api.depends("kind")
    def _compute_traits_affiches(self):
        """Ce que la fiche a le droit de montrer, decide par le materiel.

        La vue interroge ces deux champs plutot que de comparer `kind` a une
        valeur ecrite en dur : un troisieme materiel ne doit toucher que
        `MATERIELS`, pas le XML.
        """
        for gateway in self:
            gateway.montre_batterie = gateway._trait("batterie")
            gateway.montre_cadencement = gateway._trait("cadencement_systeme")

    def _trait(self, nom):
        """Un trait du materiel de cette passerelle.

        Retombe sur le materiel par defaut plutot que de lever : un
        enregistrement dont le champ serait vide — importe, ou cree par du code
        anterieur a ce champ — doit rester lisible.
        """
        self.ensure_one()
        defaut = MATERIELS[MATERIEL_DEFAUT]
        return MATERIELS.get(self.kind or MATERIEL_DEFAUT, defaut)[nom]

    @api.depends("company_id.erplibre_gateway_id", "active", "sequence")
    def _compute_is_company_default(self):
        """Dit LAQUELLE envoie, a l'endroit ou on les compare.

        Non stocke : la valeur depend du choix de la societe et de l'ordre des
        AUTRES passerelles, que rien ne peut declarer en dependance. Une
        societe en compte quelques-unes, le recalcul a chaque lecture ne coute
        rien.
        """
        retenue = {}
        for gateway in self:
            societe = gateway.company_id
            if not societe:
                gateway.is_company_default = False
                continue
            if societe.id not in retenue:
                retenue[societe.id] = self._for_company(societe)
            gateway.is_company_default = gateway == retenue[societe.id]

    def _compute_dispatch_count(self):
        counts = dict(
            self.env["erplibre.sms.dispatch"]._read_group(
                [("gateway_id", "in", self.ids)],
                ["gateway_id"],
                ["__count"],
            )
        )
        for gateway in self:
            gateway.dispatch_count = counts.get(gateway, 0)

    @api.constrains("segments_per_minute", "kind")
    def _check_segments_per_minute(self):
        """N'oppose a l'appareil que le plafond que l'appareil impose.

        Celui d'Android vient de son systeme, pas du reseau : le refuser a un
        modem le briderait pour une raison qui ne le concerne pas.
        """
        for gateway in self:
            plafond = gateway._trait("plafond_segments")
            if plafond and gateway.segments_per_minute > plafond:
                raise UserError(
                    _(
                        "Android bloque a %(limit)s segments par minute et par application. "
                        "Au-dela, un dialogue systeme apparait sur le telephone et les "
                        "messages ne partent pas.",
                        limit=plafond,
                    )
                )

    @api.constrains("poll_interval_seconds")
    def _check_poll_interval(self):
        for gateway in self:
            if gateway.poll_interval_seconds < 15:
                raise UserError(
                    _(
                        "Un intervalle sous 15 secondes noie le serveur sans gagner "
                        "de latence utile : l'envoi d'un groupe prend de toute facon "
                        "plusieurs minutes."
                    )
                )

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    @api.model
    def _for_company(self, company):
        """La passerelle qui envoie pour cette societe, ou un ensemble vide.

        Point de resolution UNIQUE : l'envoi, le compositeur et le repli du
        cron d'expiration passent tous par ici. Trois regles separees
        finiraient par diverger, et un message partirait alors par un materiel
        pendant que l'alerte de sa panne se poserait sur un autre.

        Le choix explicite de la societe l'emporte. Sans choix, on retombe sur
        la premiere active par `sequence, id` : c'etait la seule regle avant
        que le choix existe, et elle reste juste tant qu'il n'y a qu'une
        passerelle.

        Une passerelle choisie mais archivee ne se remplace PAS en silence.
        Substituer l'autre materiel ferait partir le message depuis une autre
        carte SIM, donc depuis un autre numero : le destinataire le voit,
        repond a ce numero-la, et personne ne l'avait demande. Un refus visible
        vaut mieux qu'un envoi juste en apparence.
        """
        if not company:
            return self.browse()
        choisie = company.erplibre_gateway_id
        if choisie:
            if choisie.active and choisie.company_id == company:
                return choisie
            _logger.error(
                "erplibre_mobile_gateway: la passerelle choisie par %s est "
                "inutilisable (archivee ou d'une autre societe) ; aucune "
                "substitution n'est faite.",
                company.display_name,
            )
            return self.browse()
        return self.search(
            [("company_id", "=", company.id), ("active", "=", True)], limit=1
        )

    def action_set_as_company_default(self):
        """Fait de cette passerelle celle qui envoie, pour sa societe.

        Le choix se pose sur la societe et non sur la passerelle : deux
        passerelles marquees ne voudraient rien dire, et l'unicite est gratuite
        quand elle est portee par un seul champ. Reserve a l'administration --
        le bouton est masque ailleurs -- parce qu'il ecrit sur `res.company`.
        """
        self.ensure_one()
        if not self.active:
            raise UserError(
                _(
                    "Une passerelle archivee n'envoie rien. Reactivez-la avant "
                    "de la choisir."
                )
            )
        self.company_id.erplibre_gateway_id = self.id
        return True

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
        dispatches = (
            self.env["erplibre.sms.dispatch"]
            .sudo()
            .search(
                [
                    ("gateway_id", "=", self.id),
                    "|",
                    ("state", "=", "queued"),
                    "&",
                    ("state", "=", "published"),
                    ("published_at", "<=", retry_before),
                ],
                order="requested_at asc",
                limit=self.max_jobs_per_poll or 25,
            )
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
        return [
            {"body": body, "to": recipients} for body, recipients in grouped.items()
        ]

    def _destinataires_notification(self, company=None):
        """Les utilisateurs internes a prevenir d'un evenement entrant.

        La liste explicite l'emporte ; vide, ce sont les membres du groupe
        d'envoi de la societe. Prevenir tout le monde diffuserait un numero de
        telephone et le texte d'un message a quiconque a un compte, alors que
        savoir qui ecrit est une information de travail.

        Accepte une societe pour les cas ou la passerelle est inconnue : un
        appel compose a la main nait sans fiche, et il faut quand meme
        l'annoncer.

        Une liste NOMMEE dont tout le monde est parti rend un ensemble vide,
        et non le groupe entier. La lire sans `active_test` est ce qui permet
        de faire la difference entre « personne n'a ete choisi » et « ceux
        qu'on avait choisis sont archives » : retomber sur le groupe enverrait
        le texte d'un message a des gens que personne n'a designes, et
        l'appelant dit deja qu'une annonce sans destinataire est une panne.
        """
        passerelle = self[:1]
        societe = passerelle.company_id or company or self.env.company
        nommes = passerelle.with_context(active_test=False).notify_user_ids
        if nommes:
            vivants = nommes.filtered("active")
            if not vivants:
                _logger.warning(
                    "erplibre_mobile_gateway: la passerelle %s ne nomme que"
                    " des utilisateurs archives : plus personne n'est"
                    " prevenu.",
                    passerelle.display_name,
                )
            return vivants
        groupe = self.env.ref(
            "erplibre_mobile_gateway.group_erplibre_sms_send",
            raise_if_not_found=False,
        )
        if not groupe:
            return self.env["res.users"]
        return self.env["res.users"].search(
            [
                ("groups_id", "in", groupe.ids),
                ("company_ids", "in", societe.ids),
                ("active", "=", True),
                ("share", "=", False),
            ]
        )

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
            "app_version": status.get("app_version") or False,
        }
        # Ce qu'un materiel ne connait pas est remis a neutre plutot que laisse
        # tel quel : une fiche passee de telephone a modem afficherait sinon la
        # derniere batterie relevee, pour un appareil qui n'en a pas.
        batterie = self._trait("batterie")
        values["battery_percent"] = int(status.get("battery") or 0) if batterie else 0
        values["battery_charging"] = bool(status.get("charging")) if batterie else False
        cadence = self._trait("cadencement_systeme")
        values["doze_exempt"] = bool(status.get("doze_exempt")) if cadence else False
        values["exact_alarms"] = bool(status.get("exact_alarms")) if cadence else False

        self.sudo().write(values)
        self._verifier_le_materiel(status.get("kind"))
        # Un envoi devenu impossible ou une SIM absente est une panne, meme si
        # l'appareil parle : il parle pour dire qu'il ne peut pas envoyer.
        if not values["sms_permission_ok"]:
            self.sudo()._raise_alarm(self._trait("sans_envoi"))
        elif not values["sim_ready"]:
            self.sudo()._raise_alarm(self._trait("sans_sim"))
        elif self.alarm_active:
            self.sudo()._clear_alarm()
        return True

    def _verifier_le_materiel(self, declare):
        """Signale une fiche qui ne decrit pas l'appareil qui interroge.

        Le materiel se choisit a la main : rien n'empeche de laisser
        « telephone » sur une fiche qu'un modem interroge, et la passerelle
        serait alors jugee sur des criteres qui ne la concernent pas. On le dit
        une fois, dans le fil de discussion, sans rien changer d'autorite — une
        fiche qui se reecrirait toute seule serait pire que le desaccord.
        """
        self.ensure_one()
        if not declare or declare == self.kind or declare not in MATERIELS:
            return False
        _logger.warning(
            "erplibre_mobile_gateway: la passerelle %s est declaree %r et "
            "interrogee par un appareil qui se dit %r",
            self.device_id,
            self.kind,
            declare,
        )
        self.sudo().message_post(
            body=_(
                "L'appareil qui interroge se declare « %(declare)s », alors que "
                "cette fiche porte « %(fiche)s ». Les criteres de sante appliques "
                "ne sont pas les siens.",
                declare=MATERIELS[declare]["libelle"],
                fiche=self._trait("libelle"),
            )
        )
        return True

    def action_reevaluer_alerte(self):
        """Rejuge l'alerte sur l'etat courant, sans attendre l'agent.

        Une alerte ne se leve toute seule qu'a la prochaine interrogation. Quand
        l'appareil est reparti mais que son agent ne tourne pas encore, la fiche
        reste rouge pour une raison qui n'existe plus, et rien ne permet de le
        constater — sinon attendre.

        Les memes criteres que l'interrogation et la surveillance, dans le meme
        ORDRE : le silence d'abord, car un appareil muet rend tout le reste
        perime. Rien n'est efface d'autorite ; ce qui tient encore est
        simplement redit avec un motif a jour.
        """
        self.ensure_one()
        maintenant = fields.Datetime.now()
        if not self.last_poll_at:
            motif = _("La passerelle n'a jamais interroge le serveur.")
        else:
            silence = (maintenant - self.last_poll_at).total_seconds()
            grace = max((self.poll_interval_seconds or 60) * 3, 180)
            if silence > grace:
                motif = _(
                    "Aucune interrogation depuis %(minutes)s minutes.",
                    minutes=int(silence // 60),
                )
            elif not self.sms_permission_ok:
                motif = self._trait("sans_envoi")
            elif not self.sim_ready:
                motif = self._trait("sans_sim")
            else:
                motif = ""

        if motif:
            self.sudo()._raise_alarm(motif)
            titre, type_ = _("La passerelle est toujours en alerte"), "warning"
            # Le motif est ecrit pour le MATERIEL DECLARE sur la fiche. Quand
            # c'est un autre appareil qui interroge, il parle donc du mauvais :
            # « la SIM du modem » pour un telephone dont la SIM est absente
            # envoie chercher la panne la ou elle n'est pas. On nomme donc ce
            # qui a repondu, sans quoi le motif seul induit en erreur.
            message = motif
            appareil = self._appareil_qui_interroge()
            if appareil:
                message = _(
                    "%(motif)s\n\nCe motif decrit l'appareil qui interroge :"
                    " %(appareil)s.",
                    motif=motif,
                    appareil=appareil,
                )
        else:
            etait = self.alarm_active
            self.sudo()._clear_alarm()
            titre = _("Passerelle en service")
            type_ = "success"
            message = (
                _("L'alerte est levee.")
                if etait
                else _("Aucune alerte n'etait active.")
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": titre,
                "message": message,
                "type": type_,
                "sticky": False,
            },
        }

    def _signaler_messagerie(self, attente, lu_le=None):
        """Enregistre l'etat de la boite vocale et l'annonce quand il se leve.

        Seule la LEVEE est annoncee aux destinataires : c'est elle qui demande
        un geste. La retombee s'inscrit au fil sans nommer personne — prevenir
        chacun qu'une boite a ete videe, par quelqu'un qui le sait deja,
        noierait l'annonce qui compte.

        Rend vrai quand l'etat a change.
        """
        self.ensure_one()
        attente = bool(attente)
        lu_le = lu_le or fields.Datetime.now()
        change = attente != self.voicemail_waiting
        valeurs = {"voicemail_checked_at": lu_le}
        if change:
            valeurs["voicemail_waiting"] = attente
            valeurs["voicemail_since"] = lu_le if attente else False
        self.sudo().write(valeurs)
        if not change:
            return False

        if attente:
            destinataires = self._destinataires_notification()
            if not destinataires:
                _logger.warning(
                    "erplibre_mobile_gateway: message dans la boite vocale de"
                    " %s annonce a PERSONNE — aucun destinataire designe.",
                    self.display_name,
                )
            self.sudo().message_post(
                body=_(
                    "Un message attend dans la boite vocale de l'operateur. "
                    "Il se consulte en appelant la messagerie ; le drapeau "
                    "retombera une fois la boite videe."
                ),
                partner_ids=destinataires.partner_id.ids,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        else:
            self.sudo().message_post(
                body=_("La boite vocale de l'operateur est videe."),
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )
        return True

    def _appareil_qui_interroge(self):
        """Le modele de l'appareil du dernier releve, ou une chaine vide.

        Il ne se deduit pas de la fiche : le materiel s'y choisit a la main, et
        rien n'empeche qu'un autre appareil interroge la meme passerelle.
        """
        self.ensure_one()
        try:
            releve = json.loads(self.last_status_json or "{}")
        except ValueError:
            return ""
        return releve.get("device_model") or ""

    def _raise_alarm(self, reason):
        self.ensure_one()
        if self.alarm_active and self.alarm_reason == reason:
            return True
        self.write(
            {
                "alarm_active": True,
                "alarm_since": self.alarm_since or fields.Datetime.now(),
                "alarm_reason": reason[:256],
            }
        )
        self.message_post(body=_("Passerelle mobile en alerte : %s", reason))
        self._escalate(reason)
        return True

    def _clear_alarm(self):
        self.ensure_one()
        if self.alarm_active:
            self.write(
                {"alarm_active": False, "alarm_since": False, "alarm_reason": False}
            )
            self.message_post(body=_("Passerelle mobile revenue en service."))
        return True

    def _escalate(self, reason):
        """Alerte sur un canal INDEPENDANT de celui qui est surveille."""
        self.ensure_one()
        if self.alarm_webhook_url:
            try:
                reponse = requests.post(
                    self.alarm_webhook_url,
                    json={
                        "gateway": self.name,
                        "device": self.device_id,
                        "reason": reason,
                    },
                    timeout=ESCALATION_TIMEOUT,
                )
                # Le CODE et pas seulement l'absence d'exception : un POST
                # refuse rend une reponse, il ne leve pas. Un point d'acces
                # qui rejette l'alerte se lisait donc comme un point d'acces
                # qui l'accepte — sur le seul canal dont le travail est de
                # prevenir, et qu'on ne regarde que le jour ou il a servi.
                if not reponse.ok:
                    _logger.error(
                        "erplibre_mobile_gateway: escalade refusee par le"
                        " point d'acces (%s) : %s",
                        reponse.status_code, (reponse.text or "")[:200],
                    )
                else:
                    _logger.info(
                        "erplibre_mobile_gateway: escalade transmise au"
                        " point d'acces (%s)", reponse.status_code,
                    )
            except (
                Exception
            ) as exc:  # noqa: BLE001 - une escalade ne doit jamais propager
                _logger.error(
                    "erplibre_mobile_gateway: escalade par point d'acces echouee : %s",
                    exc,
                )
        else:
            _logger.error(
                "erplibre_mobile_gateway: passerelle %s en alerte et AUCUN canal d'escalade "
                "independant configure. L'alerte ne partira que par courriel, "
                "c'est-a-dire par le canal que la passerelle etait censee "
                "remplacer. Motif : %s",
                self.name,
                reason,
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
                gateway._raise_alarm(
                    _("La passerelle n'a jamais interroge le serveur.")
                )
                alarmed += 1
                continue
            silence = (now - gateway.last_poll_at).total_seconds()
            if silence > grace:
                gateway._raise_alarm(
                    _(
                        "Aucune interrogation depuis %(minutes)s minutes.",
                        minutes=int(silence // 60),
                    )
                )
                alarmed += 1
        return alarmed
