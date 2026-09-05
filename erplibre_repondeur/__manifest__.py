# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — repondeur de la ligne cellulaire",
    "summary": "Prendre les messages que personne n'a pris, et les lire dans Odoo",
    "description": """
Repondeur de la ligne cellulaire
================================

La boite vocale de l'operateur prend l'appel au bout d'une trentaine de
secondes, et ce qu'elle garde n'est consultable qu'en l'appelant : aucune
commande AT ne liste ses messages, et le modem n'a aucun stockage amovible.
Repondre AVANT elle est la seule facon d'avoir un historique.

Le service ``erplibre_sip_go`` decroche quand le softphone renonce, joue
l'annonce et enregistre. Ce module lui donne ses reglages et recoit ses
messages :

* le nombre de sonneries avant de decrocher, borne par la course contre
  l'operateur — une sonnerie dure six secondes, sa boite vocale repond vers
  trente ;
* l'annonce, deposee ici et servie au service ;
* les messages, rapproches de leur fiche contact par les chiffres du numero,
  ecoutables dans le navigateur, marquables comme entendus.

Le service garde ses propres reglages sur disque et s'en sert quand Odoo ne
repond pas : une panne du serveur ne doit pas rendre la ligne muette.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        # Le rapprochement d'un numero avec sa fiche, par les chiffres.
        "erplibre_voip_contact",
        # `sms` porte l'ecran de reglages ou le repondeur se greffe, et la
        # signature HMAC des routes vient d'`erplibre_mobile_gateway`, qui en
        # depend deja.
        "sms",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/erplibre_repondeur_message_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
