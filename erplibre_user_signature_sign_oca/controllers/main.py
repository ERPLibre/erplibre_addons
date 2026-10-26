# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""La route qui enregistre dans son profil la signature qu'un signataire
connecté dessine dans un document sign_oca.

L'écriture passe par ``res.users`` sans privilège, sur l'utilisateur de la
session : ``res.users.write`` n'élève ses droits que pour l'utilisateur
lui-même et les champs de SELF_WRITEABLE_FIELDS, et la contrainte de
``erplibre_user_signature`` refuse ce qui n'est ni PNG ni JPEG.
"""

import binascii

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class UserSignatureSignOca(http.Controller):
    @http.route("/sign_oca/user_signature/save", type="json", auth="user")
    def sign_oca_user_signature_save(self, signature=None, **kw):
        """Enregistre ``signature`` dans le profil de l'utilisateur connecté.

        :param str signature: l'image en base64, nue ou en URI de données
        :return: ``{"saved": True}``, ou ``{"error": message}`` quand elle
            est vide ou n'est pas une image PNG ou JPEG lisible
        """
        if signature and signature.startswith("data:"):
            signature = signature.partition(",")[2]
        if not signature:
            return {"error": request.env._("The signature is empty.")}
        try:
            with request.env.cr.savepoint():
                request.env["res.users"].browse(request.env.uid).write(
                    {"digital_signature": signature}
                )
        except (UserError, ValueError, binascii.Error):
            return {
                "error": request.env._(
                    "The signature cannot be read as an image."
                )
            }
        return {"saved": True}
