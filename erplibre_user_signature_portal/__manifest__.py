# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — signature de l'utilisateur au portail",
    "summary": "Dessiner, importer ou effacer sa signature depuis « Mon compte »"
    " du portail",
    "description": """
Signature de l'utilisateur au portail
=====================================

Un utilisateur du portail n'a pas accès à « Mon profil » du back-office, où
``erplibre_user_signature`` place la signature. Ce module l'ajoute à la page
des coordonnées du portail (``/my/account``) :

* la signature actuelle s'y affiche, avec un bouton pour l'effacer ;
* le composant de signature du portail — dessin, signature automatique ou
  image importée — l'enregistre, convertie en PNG par le navigateur ;
* chaque route n'écrit que la signature de l'utilisateur connecté.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        "portal",
        "erplibre_user_signature",
    ],
    "data": [
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "erplibre_user_signature_portal/static/tests/tours/*.js",
        ],
    },
    "installable": True,
    "application": False,
}
