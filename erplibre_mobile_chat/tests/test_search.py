# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Recherche de messages limitée aux canaux dont l'utilisateur est membre."""

from markupsafe import Markup
from odoo.tests import JsonRpcException, new_test_user, tagged
from odoo.tests.common import HttpCase

SEARCH_URL = "/erplibre_mobile_chat/message/search"


@tagged("post_install", "-at_install")
class TestErplibreMessageSearch(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Une adresse propre : Odoo ne notifie pas un partenaire dont
        # l'adresse est celle de l'auteur, et new_test_user dérive la même
        # adresse de chaque identifiant « chat_… ».
        cls.user_a = new_test_user(
            cls.env,
            login="chat_user_a",
            groups="base.group_user",
            email="user.a@example.com",
        )
        cls.user_a.notification_type = "inbox"
        cls.user_b = new_test_user(
            cls.env, login="chat_user_b", groups="base.group_user"
        )
        cls.user_c = new_test_user(
            cls.env, login="chat_user_c", groups="base.group_user"
        )
        cls.admin = new_test_user(
            cls.env, login="chat_admin", groups="base.group_system"
        )
        partners = (cls.user_a | cls.user_b).partner_id
        cls.channel = cls.env["discuss.channel"].create(
            {
                "name": "#général-test",
                "channel_type": "group",
                "channel_member_ids": [
                    (0, 0, {"partner_id": p.id}) for p in partners
                ],
            }
        )

    def _post(self, body, channel=None, user=None, **kwargs):
        """Publie `body` dans `channel` (le groupe par défaut) comme `user`
        (user_b par défaut) et rend le message."""
        channel = channel or self.channel
        return channel.with_user(user or self.user_b).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            **kwargs,
        )

    def _search(self, login, search_term, **params):
        self.authenticate(login, login)
        return self.make_jsonrpc_request(
            SEARCH_URL, {"search_term": search_term, **params}
        )

    def _ids(self, login, search_term, **params):
        return self._search(login, search_term, **params)["messages"]

    def test_search_matches_body_subject_attachment(self):
        by_body = self._post("Rapport trimestriel prêt")
        by_subject = self._post("Voir le sujet", subject="Budget annuel")
        attachment = (
            self.env["ir.attachment"]
            .with_user(self.user_b)
            .create(
                {
                    "name": "plan-étage-démo.pdf",
                    "raw": b"%PDF",
                    "res_model": "mail.compose.message",
                    "res_id": 0,
                }
            )
        )
        by_file = self._post("Fichier", attachment_ids=[attachment.id])
        self._post("Autre chose")
        self.assertEqual(
            self._ids("chat_user_a", "rapport trimestriel"), [by_body.id]
        )
        self.assertEqual(
            self._ids("chat_user_a", "budget annuel"), [by_subject.id]
        )
        data = self._search("chat_user_a", "étage-démo")
        self.assertEqual(data["messages"], [by_file.id])
        self.assertEqual(data["count"], 1)
        self.assertEqual(
            [m["id"] for m in data["data"]["mail.message"]], [by_file.id]
        )

    def test_search_blank_term_answers_empty(self):
        self._post("Bonjour")
        for term in ("", "   ", None):
            with self.subTest(term=term):
                self.assertEqual(
                    self._search("chat_user_a", term),
                    {"count": 0, "messages": [], "data": {}},
                )

    def test_search_escapes_entities_and_wildcards(self):
        ampersand = self._post(Markup("<p>l'eau &amp; co</p>"))
        self.assertIn("l'eau &amp; co", ampersand.body)
        percent = self._post("taux 100% atteint")
        thousand = self._post("total 1000 unités")
        underscore = self._post("clé a_b trouvée")
        other = self._post("clé axb trouvée")
        attachment = (
            self.env["ir.attachment"]
            .with_user(self.user_b)
            .create(
                {
                    "name": "r&d.pdf",
                    "raw": b"%PDF",
                    "res_model": "mail.compose.message",
                    "res_id": 0,
                }
            )
        )
        by_file = self._post("Fichier", attachment_ids=[attachment.id])
        self.assertEqual(
            self._ids("chat_user_a", "l'eau & co"), [ampersand.id]
        )
        self.assertEqual(self._ids("chat_user_a", "100%"), [percent.id])
        self.assertNotIn(thousand.id, self._ids("chat_user_a", "100%"))
        self.assertEqual(self._ids("chat_user_a", "a_b"), [underscore.id])
        self.assertNotIn(other.id, self._ids("chat_user_a", "a_b"))
        self.assertEqual(self._ids("chat_user_a", "r&d"), [by_file.id])
        # Le sujet est un texte brut : il prend le terme non échappé.
        by_subject = self._post("Voir le sujet", subject="Projet Q&A démo")
        self.assertEqual(self._ids("chat_user_a", "Q&A"), [by_subject.id])

    def test_search_never_returns_non_member_public_channel(self):
        public = self.env["discuss.channel"].create(
            {"name": "#public-démo", "channel_type": "channel"}
        )
        message = self._post("mot public unique", channel=public.sudo())
        # Les règles d'Odoo laissent user_a lire ce message.
        self.assertTrue(
            self.env["mail.message"]
            .with_user(self.user_a)
            .search([("id", "=", message.id)])
        )
        self.assertEqual(self._ids("chat_user_a", "mot public unique"), [])

    def test_search_admin_does_not_see_others_chats(self):
        chat = (
            self.env["discuss.channel"]
            .with_user(self.user_b)
            .channel_get([self.user_c.partner_id.id])
        )
        message = self._post("échange confidentiel démo", channel=chat)
        self.assertTrue(
            self.env["mail.message"]
            .with_user(self.admin)
            .search([("id", "=", message.id)])
        )
        self.assertEqual(
            self._ids("chat_admin", "échange confidentiel démo"), []
        )

    def test_search_does_not_mark_done(self):
        message = self._post(
            "mention à lire plus tard",
            partner_ids=[self.user_a.partner_id.id],
        )
        self.assertTrue(message.with_user(self.user_a).needaction)
        self.assertEqual(
            self._ids("chat_user_a", "mention à lire"), [message.id]
        )
        self.env.invalidate_all()
        self.assertTrue(message.with_user(self.user_a).needaction)

    def test_search_pages_with_before_and_count(self):
        ids = [self._post(f"page démo {index}").id for index in range(5)]
        ids.reverse()
        first = self._search("chat_user_a", "page démo", limit=2)
        self.assertEqual(first["count"], 5)
        self.assertEqual(first["messages"], ids[:2])
        second = self._search(
            "chat_user_a", "page démo", limit=2, before=ids[1]
        )
        self.assertEqual(second["count"], 5)
        self.assertEqual(second["messages"], ids[2:4])
        self.assertEqual(
            self._ids("chat_user_a", "page démo", limit=0), ids[:1]
        )
        self.assertEqual(
            self._ids("chat_user_a", "page démo", limit=None), ids
        )

    def test_search_refuses_portal_user(self):
        portal = new_test_user(
            self.env, login="chat_portal", groups="base.group_portal"
        )
        self.channel.channel_member_ids = [
            (0, 0, {"partner_id": portal.partner_id.id})
        ]
        self._post("message pour portail")
        with self.assertRaises(JsonRpcException) as caught:
            self._search("chat_portal", "message pour portail")
        self.assertEqual(caught.exception.code, 404)
