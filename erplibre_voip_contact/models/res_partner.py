# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""L'historique d'un correspondant : ce qu'on s'est deja dit, par tous les
canaux.

Le softphone montrait un appel sans rien autour. Or ce qui aide a decrocher
n'est pas l'appel en cours — on l'a sous les yeux — mais ce qui l'a precede :
trois appels manques cette semaine, un SMS reste sans reponse.

L'historique appartient au CORRESPONDANT et non a l'appel : il se consulte
aussi apres avoir raccroche, et pendant qu'on compose un numero, deux moments
ou aucun appel n'existe.
"""
from odoo import api, fields, models
from odoo.osv import expression

#: Combien d'elements chaque liste montre. Au-dela, les vues completes sont a
#: un clic, et un panneau de softphone n'a pas la hauteur d'un journal.
LIMITE_HISTORIQUE = 8

#: En deca de ce nombre de chiffres, un numero en cours de frappe ne designe
#: personne. Le rapprochement compare des FINS de numero : « 514 » se termine
#: comme la moitie du carnet, et proposer cet historique-la desinforme.
CHIFFRES_MINIMUM = 7


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def historique_correspondant(
        self, phone_number=False, partner_id=False, exclude_call_id=False, limit=None
    ):
        """Les appels et les SMS echanges avec ce correspondant.

        Un seul aller-retour rend les deux : le panneau les affiche ensemble,
        et deux requetes pour un seul ecran doublent la latence au moment ou
        quelqu'un decroche.
        """
        limite = limit or LIMITE_HISTORIQUE
        fin = self._fin_du_numero(phone_number)
        if not partner_id and not fin:
            return {"appels": [], "sms": []}
        return {
            "appels": self._historique_appels(fin, partner_id, exclude_call_id, limite),
            "sms": self._historique_sms(fin, partner_id, limite),
        }

    @api.model
    def _fin_du_numero(self, numero):
        """Les derniers chiffres a comparer, ou une chaine vide.

        Comparer les CHIFFRES SEULS est la seule facon qui survive au
        formatage : un meme numero s'ecrit avec ou sans indicatif, avec
        tirets, points ou parentheses. La longueur retenue est celle que la
        societe declare, un numero compose sans indicatif regional et le meme
        numero stocke au format international ne partageant que leur fin.
        """
        chiffres = "".join(c for c in str(numero or "") if c.isdigit())
        if len(chiffres) < CHIFFRES_MINIMUM:
            return ""
        longueur = self.env.company.number_of_digits_to_match_from_end or 8
        return chiffres[-longueur:] if len(chiffres) >= longueur else chiffres

    @api.model
    def _ids_par_chiffres(self, table, colonne, fin, limite, condition=""):
        """Les ids d'une table dont un numero se termine par ces chiffres.

        En SQL parce que la comparaison porte sur le numero DEPOUILLE de sa
        mise en forme, ce que l'ORM ne sait pas exprimer.
        """
        # La requete ne voit pas le cache de l'ORM : sans ce vidage, une ligne
        # ecrite dans la meme transaction resterait invisible.
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT id FROM {table} WHERE {condition}"
            " regexp_replace({colonne}, '[^0-9]', '', 'g') LIKE %s"
            " ORDER BY id DESC LIMIT %s".format(
                table=table, colonne=colonne, condition=condition
            ),
            ("%" + fin, limite),
        )
        return [ligne[0] for ligne in self.env.cr.fetchall()]

    @api.model
    def _historique_appels(self, fin, partner_id, exclude_call_id, limite):
        """Les appels precedents, bornes a l'utilisateur courant.

        Comme la liste de l'onglet des appels : le panneau ne montre pas ce
        qu'un collegue a recu.
        """
        appels = self.env["voip.call"]
        # La fiche ET les chiffres : un appel enregistre avant que la fiche
        # n'existe ne porte aucun contact, et le chercher par la seule fiche
        # ferait disparaitre les plus anciens.
        conditions = []
        if partner_id:
            conditions.append([("partner_id", "=", partner_id)])
        if fin:
            identifiants = self._ids_par_chiffres(
                "voip_call",
                "phone_number",
                fin,
                limite,
                condition="user_id = %d AND" % self.env.uid,
            )
            if identifiants:
                conditions.append([("id", "in", identifiants)])
        if not conditions:
            return []
        domaine = expression.AND(
            [[("user_id", "=", self.env.uid)], expression.OR(conditions)]
        )
        if exclude_call_id:
            domaine = expression.AND([domaine, [("id", "!=", exclude_call_id)]])
        trouves = appels.search(domaine, limit=limite, order="create_date DESC")
        return [appel.format_call() for appel in trouves]

    @api.model
    def _historique_sms(self, fin, partner_id, limite):
        """Les SMS echanges, envoyes et recus confondus, du plus recent.

        PAS de filtre sur l'utilisateur, contrairement aux appels : un SMS
        est un echange de l'organisation avec la personne, pas d'une personne
        avec une autre. Celui qu'un collegue a envoye explique souvent
        l'appel qui suit.
        """
        lignes = []
        lignes += self._lignes_sms(
            "erplibre.sms.dispatch", "out", "requested_at", fin, partner_id, limite
        )
        lignes += self._lignes_sms(
            "erplibre.sms.inbound", "in", "received_at", fin, partner_id, limite
        )
        lignes.sort(key=lambda ligne: ligne["date"] or "", reverse=True)
        return lignes[:limite]

    @api.model
    def _lignes_sms(self, modele, sens, champ_date, fin, partner_id, limite):
        """Une moitie de l'historique SMS, envoyee ou recue.

        Un utilisateur sans droit de lecture sur les SMS n'en voit aucun,
        plutot que de recevoir une erreur : le panneau reste utilisable, et
        ce qu'il ne montre pas est ce a quoi il n'a pas droit.
        """
        objet = self.env[modele]
        if not objet.has_access("read"):
            return []

        # La fiche ET les chiffres, et non l'une OU les autres. Un SMS recu
        # avant que la fiche n'existe ne porte aucun contact : le chercher par
        # la seule fiche laisserait justement disparaitre les plus anciens,
        # ceux qu'on veut relire. Le meme numero les rattache.
        conditions = []
        if partner_id:
            conditions.append([("partner_id", "=", partner_id)])
        if fin:
            identifiants = self._ids_par_chiffres(objet._table, "number", fin, limite)
            if identifiants:
                conditions.append([("id", "in", identifiants)])
        if not conditions:
            return []
        domaine = expression.OR(conditions)
        trouves = objet.search(domaine, limit=limite, order=champ_date + " DESC")
        return [
            {
                # L'identifiant porte le sens : les deux tables numerotent
                # chacune de leur cote, et un « 12 » venant des deux ferait
                # disparaitre une ligne de l'affichage.
                "id": "%s-%s" % (sens, sms.id),
                "sens": sens,
                "date": fields.Datetime.to_string(sms[champ_date]),
                "texte": sms.body or "",
                "etat": sms.state if sens == "out" else "",
            }
            for sms in trouves
        ]
