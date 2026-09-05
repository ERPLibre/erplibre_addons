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
        }
