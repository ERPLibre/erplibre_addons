# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""La signature du profil, offerte au signataire connecté par ``get_info``."""

from odoo import models
from odoo.http import request
from odoo.tools.image import base64_to_image, image_data_uri, image_to_base64


class SignOcaRequestSigner(models.Model):
    _inherit = "sign.oca.request.signer"

    def get_info(self, access_token=False):
        """Ajoute ``user_signature`` aux données de la page de signature :
        ce que rend ``_get_user_signature_info``."""
        info = super().get_info(access_token=access_token)
        info["user_signature"] = self._get_user_signature_info()
        return info

    def _get_user_signature_info(self):
        """Rend la signature de profil que la page offre à ce signataire.

        :return: False quand l'utilisateur de la session est anonyme ou que
            ``_is_user_signature_signer`` ne le reconnaît pas comme ce
            signataire ; sinon ``{"image": uri}``, où ``uri`` est la
            signature de son profil en URI de données PNG, ou False s'il n'en
            a pas.

        Seule la signature de ``_get_user_signature_user()`` est lue, en
        superutilisateur puisque son champ est réservé aux administrateurs.
        Aucun paramètre ne désigne un autre utilisateur.
        """
        self.ensure_one()
        user = self._get_user_signature_user()
        if user._is_public() or not self._is_user_signature_signer(user):
            return False
        signature = user.sudo().with_context(bin_size=False).digital_signature
        return {
            "image": signature and self._get_user_signature_png_uri(signature)
        }

    def _is_user_signature_signer(self, user):
        """Rend vrai quand ``user`` signe pour ce signataire.

        Avec ``sign_oca_login``, c'est ``_is_login_user`` qui en décide,
        avec ce que d'autres modules y ajoutent : tout réviseur d'un palier
        de ``sign_oca_tier_validation``, par exemple. Sans lui, le
        partenaire de ``user`` doit être celui du signataire.
        """
        self.ensure_one()
        if hasattr(self, "_is_login_user"):
            return self._is_login_user(user)
        return user.partner_id == self.sudo().partner_id

    def _get_user_signature_user(self):
        """Rend l'utilisateur de la session : celui de la requête HTTP, ou
        celui de l'environnement hors requête.

        Les routes ``/sign_oca/*`` lisent le signataire par
        ``_document_check_access``, qui passe à l'utilisateur
        ``SUPERUSER_ID`` : ``self.env.user`` n'y est plus celui qui signe.
        Sans session, ``request.env.user`` est l'utilisateur public.
        """
        return request.env.user if request else self.env.user

    def _get_user_signature_png_uri(self, signature):
        """Rend ``signature``, une image en base64, en URI de données PNG.

        La case de signature de sign_oca préfixe d'office
        ``data:image/png;base64,`` à toute valeur qui ne le porte pas : un
        JPEG y est donc converti en PNG.
        """
        image = base64_to_image(signature)
        if image.format != "PNG":
            signature = image_to_base64(image.convert("RGBA"), "PNG")
        return image_data_uri(signature)
