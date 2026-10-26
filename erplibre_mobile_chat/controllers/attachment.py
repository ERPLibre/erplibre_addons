# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Téléversement idempotent d'une pièce jointe dans un canal."""

from odoo import http
from odoo.addons.mail.controllers.attachment import AttachmentController
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.translate import _
from werkzeug.exceptions import BadRequest, NotFound

from ..models.discuss_channel import (
    LOCK_NAMESPACE_ATTACHMENT,
    erplibre_lock_uuid,
)


class ErplibreAttachmentController(AttachmentController):
    @http.route(
        "/erplibre_mobile_chat/attachment/upload",
        methods=["POST"],
        type="http",
        auth="public",
    )
    def erplibre_attachment_upload(
        self,
        ufile,
        thread_id,
        thread_model,
        client_uuid=None,
        is_pending=False,
        **kwargs,
    ):
        """Téléverse `ufile` comme /mail/attachment/upload, avec deux
        différences : l'image reste l'original (pas de réduction à
        l'enregistrement) et `client_uuid` rend le téléversement idempotent.

        Un renvoi du même `client_uuid` par le même utilisateur rend la
        pièce jointe déjà créée, sans en créer une seconde ni rejouer les
        métadonnées vocales, même si le fil ou le fichier diffèrent. Sinon,
        la route d'Odoo fait le travail : droits sur le fil, société, pièce
        jointe en attente (`is_pending`), `voice` et forme de la réponse.

        Le jeton CSRF est exigé comme pour la route d'Odoo. Seul un
        utilisateur interne est servi : l'utilisateur public (session
        expirée) reçoit NotFound, la réponse d'Odoo à une session expirée,
        et un utilisateur portail aussi, car la lecture d'une pièce jointe
        lui est refusée hors sudo et un renvoi ne pourrait pas lui rendre
        la première. Seul `discuss.channel` est accepté comme fil.
        """
        if (
            not request.env.user._is_internal()
            or thread_model != "discuss.channel"
        ):
            raise NotFound()
        if not client_uuid:
            raise BadRequest()
        erplibre_lock_uuid(request.env, LOCK_NAMESPACE_ATTACHMENT, client_uuid)
        # sudo: ir.attachment - l'index unique porte sur (create_uid,
        # identifiant) quels que soient les droits : une pièce jointe que la
        # recherche de l'utilisateur ne voit plus (fil devenu illisible)
        # doit être trouvée, sinon la création échoue sur l'index. La
        # lecture du résultat se fait avec les droits de l'utilisateur.
        found = (
            request.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("erplibre_client_uuid", "=", client_uuid),
                    ("create_uid", "=", request.env.uid),
                ],
                limit=1,
            )
        )
        if found:
            existing = request.env["ir.attachment"].browse(found.ids)
            try:
                store = Store(existing, extra_fields=["access_token"])
                res = {"data": store.get_result()}
            except AccessError:
                res = {
                    "error": _(
                        "You are not allowed to upload an attachment here."
                    )
                }
            return request.make_json_response(res)
        request.update_context(
            image_no_postprocess=True, erplibre_attachment_uuid=client_uuid
        )
        return self.mail_attachment_upload(
            ufile, thread_id, thread_model, is_pending=is_pending, **kwargs
        )
