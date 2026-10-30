# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — cachet de signature et sceau PAdES",
    "summary": "Agrandir le champ de signature PAdES au cachet placé sous"
    " la case",
    "description": """
Cachet de signature et sceau PAdES
==================================

``sign_oca_pades`` fait d'une case de signature un champ de signature PDF,
dont l'apparence s'arrête au rectangle du champ. Un cachet dont les lignes
vont sous la case en serait coupé : ce module donne au champ le rectangle
de tout le cachet.

S'installe de lui-même avec ``erplibre_sign_oca_signature_stamp`` et
``sign_oca_pades``.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        "erplibre_sign_oca_signature_stamp",
        "sign_oca_pades",
    ],
    "auto_install": True,
    "installable": True,
    "application": False,
}
