# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Modification d'un message gardée par l'empreinte de son corps et
recherche de messages dans les canaux dont l'utilisateur est membre."""

from odoo import http
from odoo.addons.mail.controllers.thread import ThreadController
from odoo.addons.mail.tools.discuss import Store
from odoo.http import request
from werkzeug.exceptions import NotFound

SEARCH_LIMIT_MAX = 100


def erplibre_like_term(raw):
    """Rend `raw` prêt pour `ilike` : `\\`, `%` et `_` précédés d'une barre
    oblique inverse, pour que PostgreSQL les lise comme des caractères et
    non des jokers, puis chaque espace changée en `%`, comme le fait
    `_message_fetch` d'Odoo pour ne pas exiger l'espacement exact."""
    for char in ("\\", "%", "_"):
        raw = raw.replace(char, "\\" + char)
    return raw.replace(" ", "%")


def erplibre_html_term(raw):
    """Rend `raw` comme `erplibre_like_term`, pour le corps HTML stocké :
    l'assainisseur y garde les apostrophes, les guillemets et les accents
    tels quels et n'écrit en entités que `&`, `<` et `>`, que le terme
    reçoit donc aussi, `&` d'abord pour ne pas réécrire les entités
    produites."""
    for char, entity in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")):
        raw = raw.replace(char, entity)
    return erplibre_like_term(raw)


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
        toutes, comme chez Odoo. Seul un utilisateur interne est servi ; un
        `message_id` non numérique, un message absent, illisible ou que
        l'utilisateur ne peut modifier selon Odoo rend NotFound, sans
        verrou. Le verrou de ligne, pris après ces contrôles et avant la
        relecture du corps, fait attendre une modification concurrente
        entre la comparaison et l'écriture ; en isolation REPEATABLE READ,
        celle qui attendait échoue en sérialisation et Odoo rejoue la
        requête, qui relit alors le corps à jour.
        """
        if not request.env.user._is_internal():
            raise NotFound()
        try:
            message_id = int(message_id)
        except (TypeError, ValueError):
            raise NotFound() from None
        message = request.env["mail.message"]._get_with_access(
            message_id, "create", **kwargs
        )
        if not message or not self._is_message_editable(message, **kwargs):
            raise NotFound()
        request.env.cr.execute(
            "SELECT id FROM mail_message WHERE id = %s FOR UPDATE",
            (message_id,),
        )
        # Les contrôles ont lu le message avant le verrou : le corps et les
        # pièces jointes sont relus après lui.
        message.invalidate_recordset()
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

    @http.route(
        "/erplibre_mobile_chat/message/search",
        methods=["POST"],
        type="json",
        auth="user",
        readonly=True,
    )
    def erplibre_search_messages(self, search_term, before=None, limit=30):
        """Cherche `search_term` dans les messages des canaux dont
        l'utilisateur est membre et rend `{count, messages, data}` au format
        des routes de boîte d'Odoo : `count` compte toutes les
        correspondances, sans tenir compte de `before` ; `messages` porte
        les ids de la page, du plus récent au plus ancien ; `data` est le
        Store de ces messages pour l'utilisateur courant.

        Un message correspond par son corps, son sujet ou le nom d'une de
        ses pièces jointes, `ilike` sur chacun (voir erplibre_html_term et
        erplibre_like_term). `before` borne la page aux ids inférieurs ;
        `limit` est ramené entre 1 et SEARCH_LIMIT_MAX. Les canaux sont ceux
        dont le partenaire courant est membre : ni un canal public où il
        n'est pas, ni la discussion d'autres personnes, même pour un
        administrateur que les règles d'Odoo laisseraient lire. La
        recherche passe en plus par les droits de l'utilisateur
        (`mail.message._search`). Rien n'est marqué lu : la route n'appelle
        pas `set_message_done`, contrairement aux routes de fil d'Odoo.

        Seul un utilisateur interne est servi ; un terme vide rend une
        réponse vide, des paramètres non numériques rendent NotFound.
        """
        if not request.env.user._is_internal():
            raise NotFound()
        try:
            before = int(before) if before else None
            limit = max(1, min(int(limit), SEARCH_LIMIT_MAX))
        except (TypeError, ValueError):
            raise NotFound() from None
        raw = str(search_term or "").strip()
        if not raw:
            return {"count": 0, "messages": [], "data": {}}
        like = erplibre_like_term(raw)
        channel_ids = (
            request.env["discuss.channel"]
            .search([("is_member", "=", True)])
            .ids
        )
        # sudo: ir.attachment - comme _message_fetch, le nom est cherché
        # dans toutes les pièces jointes ; l'intersection avec les messages
        # lisibles des canaux de l'utilisateur borne le résultat.
        attachments = (
            request.env["ir.attachment"]
            .sudo()
            ._search([("name", "ilike", like)])
        )
        domain = [
            ("model", "=", "discuss.channel"),
            ("res_id", "in", channel_ids),
            ("message_type", "!=", "user_notification"),
            "|",
            "|",
            ("body", "ilike", erplibre_html_term(raw)),
            ("subject", "ilike", like),
            ("attachment_ids", "in", attachments),
        ]
        Message = request.env["mail.message"]
        count = Message.search_count(domain)
        if before:
            domain = [*domain, ("id", "<", before)]
        messages = Message.search(domain, limit=limit, order="id DESC")
        return {
            "count": count,
            "messages": Store.many_ids(messages),
            "data": Store(messages, for_current_user=True).get_result(),
        }
