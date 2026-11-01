# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — Identifiants TURN temporaires",
    "summary": "Chaque participant d'un appel Odoo reçoit des identifiants"
    " TURN signés par un secret partagé avec coturn, valides pour une durée"
    " réglable",
    "description": """
Identifiants TURN temporaires
=============================

À chaque entrée dans un appel, Odoo remet au navigateur, invités compris,
des identifiants TURN calculés selon le mécanisme de secret partagé de
coturn : nom ``<expiration>:<identifiant>``, mot de passe
``base64(HMAC-SHA1(secret, nom))``. L'identifiant vaut ``odoo-u<id>`` pour
un utilisateur et ``odoo-guest`` pour un invité, jamais l'identifiant de
connexion.

Le secret, la liste des URL (``stun:``, ``turn:``, ``turns:``) et la durée
de validité sont des paramètres système : ``erplibre_turn.secret``,
``erplibre_turn.urls`` et ``erplibre_turn.ttl_hours`` (24 heures par
défaut, réglable dans Configuration › Discuss). Twilio activé, secret ou
liste vide : Odoo rend sa propre liste, inchangée.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["mail"],
    "data": ["views/res_config_settings_views.xml"],
    "installable": True,
    "application": False,
}
