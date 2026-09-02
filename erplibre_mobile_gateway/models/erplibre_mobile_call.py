# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Appels telephoniques traces par la passerelle mobile.

Trois origines, et la distinction n'est pas cosmetique : elle decide de ce
qu'on a le droit de faire.

- `manual`   : quelqu'un a compose depuis le telephone. On observe, c'est tout.
- `click`    : quelqu'un a touche « Appeler » dans l'application. Le telephone
               compose, un humain parle. Telephonie CRM ordinaire.
- `queued`   : Odoo a mis l'appel en file et le telephone compose seul.

Le troisieme cas demande de la prudence, et le module la rend explicite. Android
n'injecte PAS de voix dans un appel : personne ne parle au bout du fil. Un tel
appel est, par construction, un appel automatise — encadre au Canada par les
Regles sur les telecommunications non sollicitees du CRTC. Le module le trace
integralement (qui l'a demande, quand, vers qui, combien de temps) pour qu'un
usage se justifie ou se corrige, jamais pour qu'il passe inapercu.
"""
import logging
import time
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

#: Progression d'un appel. Un rang inferieur ne peut pas ecraser un rang
#: superieur : un rapport en retard ne doit pas faire reculer l'etat.
STATE_RANK = {
    "queued": 0,
    "published": 1,
    "dialing": 2,
    "connected": 3,
    "ended": 4,
    "failed": 4,
    "expired": 4,
}

TERMINAL_STATES = {"ended", "failed", "expired"}

#: Origines. `queued` est la seule que le systeme declenche seul.
SOURCES = [
    ("manual", "Compose sur le telephone"),
    ("click", "Depuis l'application"),
    ("queued", "Mis en file par Odoo"),
]


class ErplibreMobileCall(models.Model):
    _name = "erplibre.mobile.call"
    _description = "Appel telephonique trace par la passerelle mobile"
    _order = "id DESC"

    call_uuid = fields.Char(
        "UUID de l'appel", required=True, index=True, readonly=True
    )
    number = fields.Char("Numero", required=True, readonly=True)
    direction = fields.Selection(
        [("out", "Sortant"), ("in", "Entrant")],
        "Sens",
        default="out",
        required=True,
        readonly=True,
    )
    source = fields.Selection(
        SOURCES, "Origine", default="manual", required=True, readonly=True
    )
    partner_id = fields.Many2one(
        "res.partner", "Correspondant", readonly=True, ondelete="set null"
    )
    company_id = fields.Many2one(
        "res.company", "Societe", required=True, readonly=True
    )
    gateway_id = fields.Many2one(
        "erplibre.sms.gateway",
        "Passerelle",
        readonly=True,
        ondelete="set null",
    )
    device_id = fields.Char("Appareil", readonly=True, index=True)

    requested_by_uid = fields.Many2one(
        "res.users", "Demande par", readonly=True, ondelete="set null"
    )
    requested_at = fields.Datetime(
        "Demande le", readonly=True, default=fields.Datetime.now
    )
    published_at = fields.Datetime("Remis au telephone le", readonly=True)
    started_at = fields.Datetime("Debut", readonly=True)
    ended_at = fields.Datetime("Fin", readonly=True)

    state = fields.Selection(
        [
            ("queued", "En file"),
            ("published", "Remis au telephone"),
            ("dialing", "Composition"),
            ("connected", "En communication"),
            ("ended", "Termine"),
            ("failed", "Echec"),
            ("expired", "Expire"),
        ],
        "Etat",
        default="queued",
        required=True,
        readonly=True,
        index=True,
    )
    report_seq = fields.Integer(
        "Sequence du dernier rapport", default=0, readonly=True
    )

    duration_seconds = fields.Integer("Duree (s)", readonly=True, default=0)
    duration_source = fields.Selection(
        [
            ("measured", "Mesuree par l'application"),
            ("call_log", "Journal d'appels Android"),
        ],
        "Origine de la duree",
        readonly=True,
        help=(
            "La mesure de l'application chronometre decroche -> raccroche et"
            " inclut donc la sonnerie. Le journal d'Android compte a partir de"
            " la reponse, comme l'operateur. Les deux chiffres different de"
            " quelques secondes : savoir lequel on lit evite de croire a une"
            " erreur."
        ),
    )
    duration_display = fields.Char(
        "Duree", compute="_compute_duration_display", store=True
    )
    failure_reason = fields.Char("Detail de l'echec", readonly=True)

    _sql_constraints = [
        (
            "call_uuid_unique",
            "unique(call_uuid)",
            "Un appel ne peut etre enregistre deux fois.",
        ),
    ]

    # ------------------------------------------------------------------
    # Affichage
    # ------------------------------------------------------------------

    @api.depends("duration_seconds")
    def _compute_duration_display(self):
        """`mm:ss`, ou `h:mm:ss` au-dela de l'heure.

        Un entier de secondes se lit mal dans une liste : « 187 » demande un
        calcul, « 3:07 » se lit. Le champ est stocke pour rester triable et
        exportable.
        """
        for record in self:
            total = max(0, record.duration_seconds or 0)
            heures, reste = divmod(total, 3600)
            minutes, secondes = divmod(reste, 60)
            if heures:
                record.duration_display = (
                    f"{heures}:{minutes:02d}:{secondes:02d}"
                )
            else:
                record.duration_display = f"{minutes}:{secondes:02d}"

    @api.depends("number", "duration_display")
    def _compute_display_name(self):
        """Libelle d'un appel : le numero, puis sa duree.

        Odoo 18 n'appelle plus `name_get` — le libelle voulu ici n'etait donc
        jamais utilise, et les listes affichaient le nom generique. C'est
        `_compute_display_name` qui fait foi.
        """
        for record in self:
            record.display_name = (
                f"{record.number} — {record.duration_display}"
            )

    # ------------------------------------------------------------------
    # Progression
    # ------------------------------------------------------------------

    def _apply_event(
        self,
        state,
        seq=None,
        at=None,
        duration=None,
        duration_source=None,
        reason=None,
    ):
        """Applique un evenement rapporte par le telephone.

        Meme discipline que pour les SMS, et pour la meme raison : le reseau
        reordonne, le telephone rejoue apres une coupure. Sans garde, un
        `dialing` arrive en retard effacerait un appel deja termine.
        """
        self.ensure_one()
        if self.state in TERMINAL_STATES:
            return False
        if state not in STATE_RANK:
            _logger.warning(
                "erplibre_mobile_gateway: etat d'appel inconnu %r", state
            )
            return False

        server_originated = seq is None
        if server_originated:
            seq = self.report_seq + 1
        elif seq <= self.report_seq:
            return False
        if STATE_RANK[state] < STATE_RANK[self.state]:
            return False

        values = {"state": state, "report_seq": seq}
        horodatage = at or fields.Datetime.now()
        if state == "connected" and not self.started_at:
            values["started_at"] = horodatage
        if state in TERMINAL_STATES:
            values["ended_at"] = horodatage
        if duration is not None:
            values["duration_seconds"] = max(0, int(duration))
            if duration_source:
                values["duration_source"] = duration_source
        if reason:
            values["failure_reason"] = str(reason)[:500]
        self.write(values)
        return True

    # ------------------------------------------------------------------
    # Rappeler
    # ------------------------------------------------------------------

    def action_call_again(self):
        """Rappelle ce numero, depuis la fiche de l'appel.

        Le geste le plus frequent apres avoir consulte un appel manque est de
        rappeler. L'origine devient `click` et non `queued` : c'est un humain
        qui a decide, ici, maintenant — et cette distinction separe la
        telephonie ordinaire de l'appel automatise dans tous les filtres
        d'audit.
        """
        self.ensure_one()
        if not self.number:
            raise UserError(_("Cet appel n'a pas de numero."))

        passerelle = self.gateway_id
        if not passerelle or not passerelle.active:
            passerelle = self.env["erplibre.sms.gateway"].search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
        if not passerelle:
            raise UserError(
                _(
                    "Aucune passerelle active : l'appel ne peut pas etre"
                    " place."
                )
            )
        if passerelle.alarm_active:
            # Mettre un rappel en file vers une passerelle en panne le ferait
            # partir a son retour, peut-etre des heures plus tard, vers
            # quelqu'un qui ne s'y attend plus.
            raise UserError(
                _("La passerelle est en panne : %s")
                % (passerelle.alarm_reason or "")
            )

        nouveau = self.create(
            {
                "call_uuid": uuid.uuid4().hex,
                "number": self.number,
                "direction": "out",
                "source": "click",
                "partner_id": self.partner_id.id or False,
                "company_id": self.company_id.id,
                "gateway_id": passerelle.id,
                "requested_by_uid": self.env.uid,
                "state": "queued",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": nouveau.id,
            "views": [[False, "form"]],
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Appel entrant : retrouver qui appelle, et le montrer
    # ------------------------------------------------------------------

    def _announce_incoming(self):
        """Pousse la fiche de l'appelant vers les ecrans ouverts.

        Le rapprochement est confie a `base_phone.get_record_from_phone_number`,
        qui compare les N derniers chiffres — un numero stocke « 514 555-0142 »
        et un numero presente « +15145550142 » designent la meme personne, et
        une comparaison de chaines les separerait.

        On previent les membres du groupe d'envoi, pas tout le monde : savoir
        qui appelle est une information de travail, pas une donnee a
        diffuser a quiconque a un compte.
        """
        self.ensure_one()
        if self.direction != "in" or not self.number:
            return
        chiffres = "".join(c for c in self.number if c.isdigit())
        if not chiffres:
            return

        trouve = False
        try:
            trouve = self.env["phone.common"].get_record_from_phone_number(
                chiffres
            )
        except Exception as exc:  # noqa: BLE001
            # Un rapprochement qui echoue ne doit pas faire perdre l'appel :
            # mieux vaut annoncer un inconnu que ne rien annoncer.
            _logger.warning(
                "erplibre_mobile_gateway: rapprochement impossible : %s",
                exc,
            )

        charge = {
            "call_id": self.id,
            "number": self.number,
            # Horodatage de l'annonce. A la connexion, le bus rejoue les
            # annonces qu'un navigateur a manquees : sans age, un poste qui
            # ouvre Odoo le matin recevrait des bulles COLLANTES pour des
            # appels termines la veille.
            "at": int(time.time()),
            "model": False,
            "res_id": False,
            "name": False,
        }
        if trouve:
            modele, res_id, nom = trouve
            charge.update({"model": modele, "res_id": res_id, "name": nom})
            if modele == "res.partner":
                self.partner_id = res_id

        groupe = self.env.ref(
            "erplibre_mobile_gateway.group_erplibre_sms_send",
            raise_if_not_found=False,
        )
        destinataires = self.env["res.users"]
        if groupe:
            destinataires = self.env["res.users"].search(
                [
                    ("groups_id", "in", groupe.ids),
                    ("company_ids", "in", self.company_id.ids),
                    ("active", "=", True),
                    ("share", "=", False),
                ]
            )

        if not destinataires:
            # Une annonce qui n'atteint personne est un echec silencieux : le
            # telephone sonne, Odoo travaille, et aucun ecran ne bouge. On le
            # dit, en nommant le groupe a rejoindre — sans quoi on cherche du
            # cote du bus ou du navigateur, ou il n'y a rien.
            _logger.warning(
                "erplibre_mobile_gateway: appel entrant de %s annonce a"
                " PERSONNE — aucun utilisateur interne de la societe %s n'est"
                " dans le groupe « Passerelle mobile / Envoi ».",
                self.number,
                self.company_id.display_name,
            )
            return

        _logger.info(
            "erplibre_mobile_gateway: appel entrant de %s annonce a %s",
            self.number,
            ", ".join(destinataires.mapped("login")),
        )
        for utilisateur in destinataires:
            utilisateur._bus_send("erplibre_incoming_call", charge)

    # ------------------------------------------------------------------
    # File
    # ------------------------------------------------------------------

    @api.model
    def _claim_pending(self, gateway, limit=5):
        """Les appels que le telephone doit passer.

        Volontairement peu nombreux — cinq au plus — et jamais en parallele :
        un telephone ne tient qu'une conversation a la fois, et empiler des
        appels ne ferait qu'allonger une file que personne ne surveille.
        """
        # On ne filtre PAS sur `source` : ce champ dit QUI a demande l'appel,
        # pas s'il faut le composer. Filtrer dessus laissait les appels du
        # bouton « Appeler » en file pour toujours — le clic creait la fiche,
        # et rien ne la ramassait. `manual` est exclu parce que ces appels-la
        # ont deja eu lieu : ils sont observes, pas demandes.
        appels = self.search(
            [
                ("gateway_id", "=", gateway.id),
                ("state", "=", "queued"),
                ("source", "in", ["queued", "click"]),
            ],
            order="requested_at ASC",
            limit=limit,
        )
        if appels:
            appels.write(
                {"state": "published", "published_at": fields.Datetime.now()}
            )
        return appels

    def _payload(self):
        """Ce qu'on transmet au telephone : le strict necessaire."""
        return [
            {
                "uuid": appel.call_uuid,
                "number": appel.number,
            }
            for appel in self
        ]
