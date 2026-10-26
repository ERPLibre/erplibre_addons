# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — signature de l'utilisateur dans sign_oca",
    "summary": "Proposer la signature du profil dans une case de signature"
    " de sign_oca, et y enregistrer celle qu'on dessine",
    "description": """
Signature de l'utilisateur dans sign_oca
========================================

Un signataire connecté qui ouvre une case de signature d'un document
``sign_oca`` retrouve dans la fenêtre de signature :

* la signature de son profil, que le bouton « Adopt my signature » pose dans
  la case sans rien dessiner ;
* la case « Save as my signature », qui enregistre dans son profil la
  signature qu'il vient de dessiner.

La signature n'est proposée qu'à l'utilisateur qui signe pour le
signataire (``_is_user_signature_signer``) ; un signataire anonyme garde le
comportement de ``sign_oca``.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        "erplibre_user_signature",
        "sign_oca",
    ],
    "assets": {
        "web.assets_backend": [
            "erplibre_user_signature_sign_oca/static/src/*.xml",
            "erplibre_user_signature_sign_oca/static/src/*.esm.js",
        ],
        "oca_sign.assets_frontend_sign": [
            "erplibre_user_signature_sign_oca/static/src/*.xml",
            "erplibre_user_signature_sign_oca/static/src/*.esm.js",
        ],
    },
    "installable": True,
    "application": False,
}
