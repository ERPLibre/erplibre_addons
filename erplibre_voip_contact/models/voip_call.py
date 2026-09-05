# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Relie un appel VoIP a la fiche de son correspondant.

`voip_oca` rapproche l'appel de la fiche par EGALITE DE CHAINE sur `phone` ou
`mobile`. Un numero presente « 15555550142 » et une fiche qui porte
« +1 555-555-0142 » designent la meme personne, et l'egalite les separe : tout
appel arrive alors sans contact.

Ce qui suit n'est pas cosmetique. Le bouton qui ouvre la fiche est conditionne
a la presence du contact, donc il disparait. Et RAPPELER depuis un appel sans
contact part sans numero : le softphone se rabat sur le mobile de la fiche, qui
n'est pas la, et la creation de l'appel echoue sur un champ obligatoire vide.

On rapproche donc par les CHIFFRES, comme `base_phone` le fait deja pour
annoncer un appel entrant, avant de laisser `voip_oca` tenter son egalite.
"""
import logging

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

#: Combien d'appels passes le panneau montre. Au-dela, l'onglet des appels est
#: a un clic, et un panneau de softphone n'a pas la hauteur d'un journal.
LIMITE_HISTORIQUE = 8


class VoipCall(models.Model):
    _inherit = "voip.call"

    @api.model
    def create_call(self, values):
        """Cree l'appel, en completant ce que l'ecran n'a pas su fournir.

        Le rapprochement precede `super` plutot que de le corriger apres coup :
        `create_call` rend l'appel deja formate pour l'ecran, et un contact
        pose ensuite n'y figurerait pas.
        """
        values = dict(values)
        if not values.get("phone_number"):
            values["phone_number"] = self._numero_du_partenaire(
                values.get("partner_id")
            )
        if not values.get("partner_id"):
            partenaire = self._partenaire_du_numero(values.get("phone_number"))
            if partenaire:
                values["partner_id"] = partenaire
        return super().create_call(values)

    @api.model
    def _numero_du_partenaire(self, partner_id):
        """Le numero de la fiche, quand l'ecran n'en a pas transmis.

        Un appel sans numero ne peut pas etre cree : `phone_number` est
        obligatoire, et l'echec se presente comme « un champ obligatoire n'est
        pas rempli », qui ne dit ni lequel manque ni pourquoi. Tant que la
        fiche porte un numero, il n'y a rien a demander a personne ; quand
        elle n'en porte pas, on le dit dans ces mots-la.

        Le mobile prime sur le fixe : c'est celui qui joint la personne
        plutot que le lieu.
        """
        contact = self.env["res.partner"].browse(partner_id) if partner_id else None
        numero = contact and (contact.mobile or contact.phone)
        if numero:
            return numero
        raise UserError(
            _(
                "Aucun numero a composer. La fiche selectionnee n'en porte"
                " pas, et l'appel n'en a pas transmis : ouvrez la fiche pour"
                " y inscrire un numero, ou composez-le au clavier."
            )
        )

    @api.model
    def _partenaire_du_numero(self, numero):
        """L'id du `res.partner` que ce numero designe, ou False.

        Le rapprochement de `base_phone` connait d'autres modeles qu'une fiche
        contact — une piste, par exemple. On en prend alors le contact
        associe ; un modele qui n'en porte pas ne rend rien, plutot qu'un id
        pris dans une autre table, qui pointerait sur la mauvaise fiche.
        """
        if not numero:
            return False
        trouve = self.env["phone.common"].get_record_from_phone_number(numero)
        if not trouve:
            return False
        modele, identifiant = trouve[0], trouve[1]
        if modele == "res.partner":
            return identifiant
        enregistrement = self.env[modele].browse(identifiant)
        if "partner_id" not in enregistrement._fields:
            return False
        return enregistrement.partner_id.id or False

    def rattacher_le_contact(self):
        """Rejoue le rapprochement sur cet appel et rend sa forme d'ecran.

        Appelee quand une fiche vient d'etre creee depuis le panneau : l'appel
        est en cours, son numero n'a pas change, mais la fiche qu'il designe
        existe desormais.
        """
        self.ensure_one()
        if not self.partner_id:
            partenaire = self._partenaire_du_numero(self.phone_number)
            if partenaire:
                self.partner_id = partenaire
        return self.format_call()

    @api.model
    def historique_du_correspondant(
        self, phone_number=False, partner_id=False, exclude_id=False, limit=None
    ):
        """Les appels precedents avec le meme correspondant.

        Le CONTACT prime sur le numero : quelqu'un qui appelle tantot de son
        mobile tantot d'un poste fixe reste une seule personne, et son
        historique doit reunir les deux. Sans contact, on se rabat sur les
        chiffres du numero.

        La liste est bornee a l'utilisateur courant, comme celle de l'onglet
        des appels : le panneau ne montre pas ce qu'un collegue a recu.
        """
        limite = limit or LIMITE_HISTORIQUE
        domaine = [("user_id", "=", self.env.uid)]
        if exclude_id:
            domaine.append(("id", "!=", exclude_id))
        if partner_id:
            domaine.append(("partner_id", "=", partner_id))
        else:
            identifiants = self._appels_par_chiffres(phone_number, limite, exclude_id)
            if not identifiants:
                return []
            domaine.append(("id", "in", identifiants))
        appels = self.search(domaine, limit=limite, order="create_date DESC")
        return [appel.format_call() for appel in appels]

    @api.model
    def _appels_par_chiffres(self, numero, limite, exclude_id=False):
        """Les ids des appels dont le numero se termine par les memes chiffres.

        `regexp_replace` retire tout ce qui n'est pas un chiffre des DEUX
        cotes : c'est la seule comparaison qui survive au formatage, un meme
        numero s'ecrivant avec ou sans indicatif, tirets ou parentheses.

        La comparaison porte sur la FIN, dont la longueur est celle que la
        societe declare : un numero compose sans indicatif regional et le meme
        numero stocke au format international ne partagent que leur fin.
        """
        chiffres = "".join(c for c in str(numero or "") if c.isdigit())
        if not chiffres:
            return []
        longueur = self.env.company.number_of_digits_to_match_from_end or 8
        fin = chiffres[-longueur:] if len(chiffres) >= longueur else chiffres
        # La requete SQL ne voit pas le cache de l'ORM : sans ce vidage,
        # un appel cree dans la meme transaction resterait invisible.
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT id FROM voip_call WHERE user_id = %s AND id != %s AND "
            "regexp_replace(phone_number, '[^0-9]', '', 'g') LIKE %s "
            "ORDER BY create_date DESC LIMIT %s",
            (self.env.uid, exclude_id or 0, "%" + fin, limite),
        )
        return [ligne[0] for ligne in self.env.cr.fetchall()]
