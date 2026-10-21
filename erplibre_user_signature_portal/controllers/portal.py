# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Les routes du portail qui lisent, enregistrent et effacent la signature de
l'utilisateur connecté.

``request.env.user`` est en superutilisateur : chaque écriture passe plutôt
par ``_current_user``, sans privilège, pour que ``res.users.write`` n'élève
ses droits que pour l'utilisateur lui-même et les champs de
SELF_WRITEABLE_FIELDS. Viser un autre utilisateur ou un autre champ lève
alors une erreur d'accès au lieu de réussir.
"""

import binascii

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import UserError
from odoo.http import request, route
from odoo.tools.image import image_data_uri


class UserSignaturePortal(CustomerPortal):
    def _current_user(self):
        return request.env["res.users"].browse(request.env.uid)

    @route()
    def account(self, redirect=None, **post):
        """Ajoute ``user_digital_signature`` au rendu de ``/my/account`` :
        l'URI de données de la signature, ou False. Une redirection, après
        l'enregistrement des coordonnées, n'a pas de rendu à compléter."""
        response = super().account(redirect=redirect, **post)
        if getattr(response, "qcontext", None) is not None:
            signature = request.env.user.digital_signature
            response.qcontext["user_digital_signature"] = (
                signature and image_data_uri(signature) or False
            )
        return response

    @route("/my/signature", type="json", auth="user")
    def portal_user_signature_save(self, name=None, signature=None, **kw):
        """Enregistre ``signature``, une image en base64 envoyée par le
        composant ``portal.signature_form``. Rend ``error`` quand elle est
        vide ou illisible, sinon de quoi recharger ``/my/account``."""
        if not signature:
            return {"error": request.env._("The signature is empty.")}
        try:
            with request.env.cr.savepoint():
                self._current_user().write({"digital_signature": signature})
        except (UserError, ValueError, binascii.Error):
            return {
                "error": request.env._(
                    "The signature cannot be read as an image."
                )
            }
        return {"force_refresh": True, "redirect_url": "/my/account"}

    @route("/my/signature/delete", type="http", auth="user", methods=["POST"])
    def portal_user_signature_delete(self, **kw):
        self._current_user().write({"digital_signature": False})
        return request.redirect("/my/account")
