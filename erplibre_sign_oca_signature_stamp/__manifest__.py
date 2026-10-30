# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — cachet de signature dans sign_oca",
    "summary": "Encadrer chaque signature d'un document sign_oca d'un"
    " guilloché, d'un emblème et de ses méta-données",
    "description": """
Cachet de signature dans sign_oca
=================================

Quand le cachet est activé, chaque case de signature d'un document
``sign_oca`` signé porte, au choix :

* un cadre guilloché de deux ondes et l'emblème sceau-plume ;
* le nom du signataire, son rôle, la date de signature avec son fuseau ;
* le code de la signature : les 16 premiers caractères d'un SHA-256 gardé
  sur le signataire, qui retrouve la demande depuis le PDF imprimé.

Le réglage vit dans les paramètres de Signer, par société ; un modèle peut
forcer le cachet ou l'interdire.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        "sign_oca",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/sign_oca_template_views.xml",
        "views/sign_oca_request_views.xml",
    ],
    "installable": True,
    "application": False,
}
