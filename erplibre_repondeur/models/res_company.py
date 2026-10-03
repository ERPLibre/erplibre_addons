# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Les reglages du repondeur, tels qu'Odoo les tient.

Le service en garde une copie sur disque et s'en sert quand Odoo ne repond
pas : une panne du serveur ne doit pas rendre la ligne muette. Ce qui est ici
FAIT AUTORITE quand il repond.
"""
from odoo import api, fields, models

#: Une sonnerie complete dure six secondes — deux de courant, quatre de
#: silence. La boite vocale de l'operateur prend l'appel vers trente : au-dela
#: de cinq sonneries, le repondeur ne decrocherait jamais, et la panne se lit
#: « il ne marche pas » sans autre indice.
SONNERIES_MIN = 1
SONNERIES_MAX = 5
SONNERIES_DEFAUT = 4


class ResCompany(models.Model):
    _inherit = "res.company"

    repondeur_actif = fields.Boolean(
        "Repondeur actif",
        help="Eteint par defaut : decrocher a la place de quelqu'un s'entend, "
        "et une machine qui repond sur une ligne dont le proprietaire "
        "ignore qu'elle en a une est une surprise desagreable.",
    )
    repondeur_sonneries = fields.Integer(
        "Sonneries avant de decrocher",
        default=SONNERIES_DEFAUT,
        help="Une sonnerie dure six secondes et la boite vocale de "
        "l'operateur repond vers trente : au-dela de cinq, le repondeur "
        "ne decrocherait jamais.",
    )
    repondeur_duree_max = fields.Integer(
        "Duree maximale d'un message (s)",
        default=120,
        help="Une ligne laissee ouverte se facture, et un appelant qui pose "
        "son combine sans raccrocher la tient aussi longtemps qu'on "
        "l'accepte.",
    )
    repondeur_annonce = fields.Binary(
        "Annonce",
        attachment=True,
        help="WAV joue a l'appelant avant l'enregistrement. Sans annonce, le "
        "repondeur enregistre quand meme : mieux vaut un message sans "
        "invite qu'un appel perdu.",
    )
    repondeur_annonce_filename = fields.Char("Nom de l'annonce")
    repondeur_notify_user_ids = fields.Many2many(
        "res.users",
        "erplibre_repondeur_notify_rel",
        "company_id",
        "user_id",
        string="Prevenir a la reception",
        help="Un repondeur dont personne n'apprend qu'il a recu quelque chose "
        "ne vaut pas mieux que pas de repondeur.",
    )

    operateur_releve_auto = fields.Boolean(
        "Relever la boite vocale de l'operateur",
        default=True,
        help="Le service appelle la boite vocale des que la carte SIM annonce "
        "un message. Le declencheur est ce drapeau et non une horloge : un "
        "relevement OCCUPE la ligne, et il n'a de raison de partir que s'il "
        "y a quelque chose a prendre.",
    )
    operateur_releve_efface = fields.Boolean(
        "Effacer le message chez l'operateur",
        default=True,
        help="Un message releve et laisse en place maintient le drapeau leve, "
        "et le relevement repartirait sans fin. L'effacement est "
        "IRREVERSIBLE : la boite de l'operateur n'a pas de corbeille, et une "
        "decoupe ratee perd le message. Eteint, le service ecoute sans rien "
        "effacer, ce qui laisse le drapeau leve.",
    )
    operateur_releve_demande = fields.Datetime(
        "Relevement demande le",
        readonly=True,
        help="Pose par le bouton. Le service compare cette date a la derniere "
        "qu'il a traitee : une date nouvelle vaut un relevement, et rejouer "
        "la meme n'en declenche pas un second.",
    )

    def action_relever_la_messagerie(self):
        """Demande UN relevement au service, a sa prochaine interrogation.

        Odoo ne peut pas appeler : le modem est ailleurs, et le service vient
        chercher ses reglages chaque minute. Le bouton pose donc une date, et
        c'est le service qui agit — d'ou le delai, qui est normal.
        """
        self.ensure_one()
        self.sudo().operateur_releve_demande = fields.Datetime.now()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Relevement demande"),
                "message": self.env._(
                    "Le service appellera la boite vocale a sa prochaine "
                    "interrogation, dans la minute. La ligne sera occupee "
                    "pendant l'appel."
                ),
                "type": "success",
            },
        }

    @api.constrains("repondeur_sonneries", "repondeur_duree_max")
    def _verifier_les_bornes(self):
        """Refuse ce que le service corrigerait en silence.

        Le service ramene une valeur hors bornes dans sa plage plutot que de
        refuser de demarrer. Ici on refuse : une saisie a l'ecran a un humain
        devant elle, et lui dire vaut mieux que changer son chiffre sans le
        prevenir.
        """
        for company in self:
            if not company.repondeur_actif:
                continue
            if not SONNERIES_MIN <= company.repondeur_sonneries <= SONNERIES_MAX:
                raise models.ValidationError(
                    self.env._(
                        "Le nombre de sonneries doit tenir entre %(min)s et "
                        "%(max)s. Une sonnerie dure six secondes, et la boite "
                        "vocale de l'operateur prend l'appel vers trente : "
                        "au-dela, le repondeur ne decrocherait jamais.",
                        min=SONNERIES_MIN,
                        max=SONNERIES_MAX,
                    )
                )
            if company.repondeur_duree_max <= 0:
                raise models.ValidationError(
                    self.env._("La duree maximale d'un message doit etre positive.")
                )

    def reglages_du_repondeur(self):
        """Ce que le service a besoin de savoir, en une structure.

        Le nom du fichier d'annonce accompagne le son : le service l'ecrit sur
        disque, et un fichier sans extension ne se joue pas.
        """
        self.ensure_one()
        return {
            "actif": bool(self.repondeur_actif),
            "sonneries": self.repondeur_sonneries or SONNERIES_DEFAUT,
            "duree_max_secondes": self.repondeur_duree_max or 120,
            "annonce_nom": self.repondeur_annonce_filename or "annonce.wav",
            "annonce_b64": (
                (self.repondeur_annonce or b"").decode("ascii")
                if self.repondeur_annonce
                else ""
            ),
            "operateur_releve_auto": bool(self.operateur_releve_auto),
            "operateur_releve_efface": bool(self.operateur_releve_efface),
            # En texte et non en horodatage : le service la COMPARE a la
            # derniere traitee, il ne la lit pas. Un format qui se compare
            # caractere par caractere evite d'accorder deux fuseaux.
            "operateur_releve_demande": (
                self.operateur_releve_demande.isoformat()
                if self.operateur_releve_demande
                else ""
            ),
        }
