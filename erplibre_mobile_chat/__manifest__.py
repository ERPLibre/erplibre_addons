# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — Clavardage mobile",
    "summary": "Publication et téléversement idempotents par identifiant"
    " client dans Discuss et le fil d'un enregistrement, modification"
    " gardée, recherche, favoris",
    "description": """
Clavardage mobile
=================

L'application mobile publie avec un identifiant client (uuid), dans Discuss
comme dans le fil d'un enregistrement (réponse dans le chatter). Si la
réponse du serveur se perd et que l'application renvoie le même message, le
serveur rend le message déjà publié au lieu d'en créer un second.

Le téléversement d'une pièce jointe, dans un canal ou sur un enregistrement,
suit la même règle et garde l'image originale, sans la réduction qu'Odoo
lui applique d'ordinaire.

La modification gardée d'un message n'écrit que si son corps n'a pas changé
depuis que l'application l'a lu : une modification envoyée hors ligne
n'écrase pas une modification plus récente et ne fait pas renaître un
message supprimé.

La recherche de messages ne parcourt que les canaux dont l'utilisateur est
membre et ne marque rien comme lu. La mise en favori fixe l'état voulu : un
renvoi ne la défait pas.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.4.0",
    "license": "AGPL-3",
    "depends": ["mail"],
    "installable": True,
    "application": False,
}
