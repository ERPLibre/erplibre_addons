# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
"""Marque-page personnel des appels deja consultes.

Sans marque-page, la pastille du systray ne pouvait vivre que dans l'onglet :
elle repartait a zero a chaque rechargement, et un appel arrive pendant que le
navigateur etait ferme ne laissait aucune trace. C'est precisement l'appel
qu'on veut retrouver — celui qu'on a manque.

Le marqueur est un identifiant, pas un compteur : deux onglets ouverts sur la
meme session ne peuvent pas se decrementer mutuellement, et rejouer la mise a
jour est sans effet.
"""
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    erplibre_call_seen_id = fields.Integer(
        "Dernier appel consulte",
        default=0,
        copy=False,
        groups="base.group_system",
        help="Identifiant du dernier appel deja vu dans le menu telephone.",
    )

    def _erplibre_call_autorise(self):
        """L'utilisateur voit-il les appels de la passerelle ?"""
        return self.env.user.has_group(
            "erplibre_mobile_gateway.group_erplibre_sms_send"
        )

    @api.model
    def erplibre_call_unseen(self):
        """Appels entrants arrives depuis la derniere consultation.

        Renvoie 0 plutot que de lever pour qui n'a pas le droit : la barre
        systeme est chargee pour tout le monde, et une erreur RPC a chaque
        ouverture de page serait un bruit sans rapport avec l'appel.
        """
        if not self._erplibre_call_autorise():
            return 0
        vu = self.env.user.sudo().erplibre_call_seen_id or 0
        return self.env["erplibre.mobile.call"].search_count(
            [("id", ">", vu), ("direction", "=", "in")]
        )

    @api.model
    def erplibre_call_mark_seen(self):
        """Marque tous les appels actuels comme vus. Renvoie le nouveau seuil."""
        if not self._erplibre_call_autorise():
            return 0
        dernier = self.env["erplibre.mobile.call"].search(
            [], limit=1, order="id desc"
        )
        self.env.user.sudo().erplibre_call_seen_id = dernier.id or 0
        return dernier.id or 0
