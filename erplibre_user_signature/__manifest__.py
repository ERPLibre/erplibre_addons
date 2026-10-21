# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — signature de l'utilisateur",
    "summary": "Signature manuscrite dans « Mon profil », lisible par son seul"
    " propriétaire et les administrateurs",
    "description": """
Signature manuscrite de l'utilisateur
=====================================

``base_user_signature`` (OCA) ajoute à ``res.users`` une image de signature,
dessinée ou importée dans « Mon profil », sous « Signature e-mail ». Tout
utilisateur interne peut y lire la signature d'un autre.

Ce module :

* réserve la lecture et l'écriture de la signature à son propriétaire et aux
  administrateurs ; un rapport qui doit l'imprimer la lit en superutilisateur ;
* garde le libellé « Signature » dans « Mon profil » pour chacun ;
* retire le bouton d'effacement du formulaire d'administration à qui ne peut
  pas écrire le champ.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        "base_user_signature",
    ],
    "data": [
        "views/res_users_view.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "erplibre_user_signature/static/tests/tours/*.js",
        ],
    },
    "installable": True,
    "application": False,
}
