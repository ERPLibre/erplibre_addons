# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — Clavardage mobile",
    "summary": "Publication idempotente dans Discuss par identifiant client",
    "description": """
Clavardage mobile
=================

L'application mobile publie dans Discuss avec un identifiant client (uuid).
Si la réponse du serveur se perd et que l'application renvoie le même
message, le serveur rend le message déjà publié au lieu d'en créer un second.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.1.0",
    "license": "AGPL-3",
    "depends": ["mail"],
    "installable": True,
    "application": False,
}
