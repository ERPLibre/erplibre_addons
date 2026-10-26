# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — Clavardage mobile",
    "summary": "Publication et téléversement idempotents dans Discuss par"
    " identifiant client",
    "description": """
Clavardage mobile
=================

L'application mobile publie dans Discuss avec un identifiant client (uuid).
Si la réponse du serveur se perd et que l'application renvoie le même
message, le serveur rend le message déjà publié au lieu d'en créer un second.

Le téléversement d'une pièce jointe suit la même règle et garde l'image
originale, sans la réduction qu'Odoo applique à l'enregistrement.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.2.0",
    "license": "AGPL-3",
    "depends": ["mail"],
    "installable": True,
    "application": False,
}
