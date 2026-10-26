# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Modification d'un message gardée par l'empreinte de son corps."""

from odoo import http
from odoo.addons.mail.controllers.thread import ThreadController
from odoo.addons.mail.tools.discuss import Store
from odoo.http import request
from werkzeug.exceptions import NotFound


class ErplibreMessageController(ThreadController):
    @http.route(
        "/erplibre_mobile_chat/message/update_content",
        methods=["POST"],
        type="json",
        auth="user",
    )
    def erplibre_update_content(
        self,
        message_id,
        body,
        expected_fingerprint,
        attachment_ids=None,
        attachment_tokens=None,
        partner_ids=None,
        **kwargs,
    ):
        """Modifie le message comme /mail/message/update_content, seulement
        si son corps n'a pas changé depuis que l'application l'a lu.

        `expected_fingerprint` est le `erplibre_body_fingerprint` lu par
        l'application. Une empreinte différente, ou un message vidé
        (supprimé) qui recevrait un corps non vide, n'écrit rien et rend
        `erplibre_conflict` (« deleted » si le message est vide, sinon
        « changed ») avec le message actuel au format de la réponse
        d'Odoo. Sinon la route d'Odoo fait le travail : contrôle des
        pièces jointes, assainissement, marque « modifié », bus et réponse.

        `attachment_ids` à None garde les pièces jointes ; [] les supprime
        toutes, comme chez Odoo. Le verrou de ligne pris en premier fait
        attendre une modification concurrente entre la comparaison et
        l'écriture ; en isolation REPEATABLE READ, celle qui attendait
        échoue en sérialisation et Odoo rejoue la requête, qui relit alors
        le corps à jour. Seul un utilisateur interne est servi ; un message
        absent, illisible ou que l'utilisateur ne peut modifier selon Odoo
        rend NotFound.
        """
        if not request.env.user._is_internal():
            raise NotFound()
        request.env.cr.execute(
            "SELECT id FROM mail_message WHERE id = %s FOR UPDATE",
            (int(message_id),),
        )
        message = request.env["mail.message"]._get_with_access(
            message_id, "create", **kwargs
        )
        if not message or not self._is_message_editable(message, **kwargs):
            raise NotFound()
        # sudo: mail.message - accès vérifié par _get_with_access et
        # _is_message_editable, comme la route d'Odoo avant sa réponse.
        message = message.sudo()
        emptied = bool(message._filter_empty())
        if message.erplibre_body_fingerprint != expected_fingerprint or (
            emptied and body
        ):
            return {
                "erplibre_conflict": "deleted" if emptied else "changed",
                **Store(message, for_current_user=True).get_result(),
            }
        return self.mail_message_update_content(
            message_id,
            body,
            attachment_ids,
            attachment_tokens=attachment_tokens,
            partner_ids=partner_ids,
            **kwargs,
        )
