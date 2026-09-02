# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — passerelle mobile",
    "summary": "Envoi de SMS par une passerelle Android auto-hébergée, en HTTPS",
    "description": """
Passerelle mobile auto-hébergée
============================

Ajoute un fournisseur SMS ``erplibre`` qui n'utilise ni Odoo IAP ni aucun
agrégateur externe. Les SMS sont mis en file ; un téléphone Android exécutant
l'application ERPLibre **interroge** ce serveur en HTTPS sortant, récupère les
demandes, les envoie par sa propre carte SIM, puis rend compte.

Aucune infrastructure intermédiaire, aucun port à ouvrir, aucune URL publique
à exposer : tout part du téléphone. L'appareil peut donc vivre derrière une IP
dynamique et un NAT d'opérateur, ce qui est le cas d'une connexion résidentielle
ordinaire.

Chaque interrogation vaut signal de vie : une passerelle qui n'interroge plus
est hors service, par définition, et l'alerte part sur un canal indépendant.

Ce que ce module garantit, et pourquoi c'est important
------------------------------------------------------

Un canal d'alerte qui échoue en silence est plus dangereux qu'un canal absent.
Le module est donc construit autour de la détection de panne :

* chaque envoi est suivi par un enregistrement ``erplibre.sms.dispatch``
  indépendant du ``sms.sms``, qui est éphémère par conception dans Odoo ;
* toute transition d'état est séquencée, ce qui rend un rapport arrivé hors
  ordre incapable de faire régresser un échec en succès ;
* une échéance d'envoi déclenche une alerte si le téléphone n'a pas confirmé ;
* un signal de vie périodique du téléphone est exigé, et son absence est
  escaladée sur un canal indépendant de celui qui est surveillé.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        "sms",
        # `sms_twilio` est le module coeur qui INTRODUIT le champ
        # `res.company.sms_provider` (models/res_company.py lignes 12-19). Le
        # coeur `sms` ne fournit que `_get_sms_api_class()`, pas le champ. On en
        # depend donc pour pouvoir faire un `selection_add` : sans lui, Odoo
        # refuse de charger avec « Field res.company.sms_provider without
        # selection ». Sa presence ajoute une option « Send via Twilio » qui
        # reste simplement inutilisee.
        "sms_twilio",
        "phone_validation",
        # Fournit le bouton « Appeler » et le point de surcharge `click2dial`
        # que ce module branche sur la passerelle.
        "base_phone",
        "mail",
    ],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/erplibre_mobile_gateway_security.xml",
        "security/ir.model.access.csv",
        "data/mail_template_data.xml",
        "data/ir_cron_data.xml",
        "views/erplibre_sms_gateway_views.xml",
        "views/erplibre_sms_dispatch_views.xml",
        "views/sms_composer_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
