# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Modification gardée d'un message par empreinte du corps."""

import hashlib
from unittest.mock import patch

from markupsafe import Markup
from odoo.addons.mail.tools.discuss import Store
from odoo.tests import JsonRpcException, new_test_user, tagged
from odoo.tests.common import HttpCase

GUARDED_URL = "/erplibre_mobile_chat/message/update_content"
ODOO_URL = "/mail/message/update_content"
EDITED = '<span class="o-mail-Message-edited"></span>'


def _sha256(text):
    return hashlib.sha256(str(text or "").encode()).hexdigest()


def _sql(query):
    return str(getattr(query, "code", query))


@tagged("post_install", "-at_install")
class TestErplibreGuardedEdit(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env, login="chat_user_a", groups="base.group_user"
        )
        cls.user_b = new_test_user(
            cls.env, login="chat_user_b", groups="base.group_user"
        )
        partners = (cls.user_a | cls.user_b).partner_id
        cls.channel = cls.env["discuss.channel"].create(
            {
                "name": "chat",
                "channel_type": "group",
                "channel_member_ids": [
                    (0, 0, {"partner_id": p.id}) for p in partners
                ],
            }
        )

    def _message(self, body="Bonjour café", attachments=0, user=None):
        """Publie `body` dans le canal comme `user` (user_a par défaut),
        avec `attachments` pièces jointes, et rend le message en sudo pour
        que le test lise tous ses champs."""
        user = user or self.user_a
        attachment_ids = [
            self.env["ir.attachment"]
            .with_user(user)
            .create(
                {
                    "name": f"note{index}.txt",
                    "raw": b"hello",
                    "res_model": "mail.compose.message",
                    "res_id": 0,
                }
            )
            .id
            for index in range(attachments)
        ]
        message = self.channel.with_user(user).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachment_ids=attachment_ids,
        )
        return message.sudo()

    def _rpc(self, login, url, message, body, **params):
        """Appelle `url` comme `login` pour le message et rend le résultat
        JSON-RPC ; le cache de l'environnement du test est invalidé pour
        relire ce que la requête a écrit."""
        self.authenticate(login, login)
        try:
            return self.make_jsonrpc_request(
                url, {"message_id": message.id, "body": body, **params}
            )
        finally:
            self.env.invalidate_all()

    def _guarded(self, message, body, fingerprint, login="chat_user_a"):
        return self._rpc(
            login,
            GUARDED_URL,
            message,
            body,
            expected_fingerprint=fingerprint,
        )

    def _guard_params(self, url, message):
        """L'empreinte attendue pour la route gardée, rien pour celle
        d'Odoo."""
        if url != GUARDED_URL:
            return {}
        return {"expected_fingerprint": message.erplibre_body_fingerprint}

    def test_fingerprint_matches_store_body(self):
        message = self._message(Markup("Ligne une<br>ligne deux — café"))
        store_body = Store(message).get_result()["mail.message"][0]["body"]
        self.assertEqual(
            message.erplibre_body_fingerprint, _sha256(store_body)
        )
        self.authenticate("chat_user_b", "chat_user_b")
        data = self.make_jsonrpc_request(
            "/mail/thread/messages",
            {"thread_model": "discuss.channel", "thread_id": self.channel.id},
        )
        fetched = next(
            m for m in data["data"]["mail.message"] if m["id"] == message.id
        )
        self.assertEqual(
            message.erplibre_body_fingerprint, _sha256(fetched["body"])
        )

    def test_guarded_edit_applies_when_unchanged(self):
        message = self._message()
        data = self._guarded(
            message, "Texte modifié", message.erplibre_body_fingerprint
        )
        self.assertNotIn("erplibre_conflict", data)
        self.assertEqual(message.body, f"<p>Texte modifié{EDITED}</p>")
        self.assertEqual(data["mail.message"][0]["body"], message.body)

    def test_guarded_edit_refused_when_changed(self):
        message = self._message()
        fingerprint = message.erplibre_body_fingerprint
        self._rpc(
            "chat_user_a", ODOO_URL, message, "Navigateur", attachment_ids=None
        )
        browser_body = message.body
        data = self._guarded(message, "Téléphone", fingerprint)
        self.assertEqual(data["erplibre_conflict"], "changed")
        self.assertEqual(message.body, browser_body)
        self.assertEqual(data["mail.message"][0]["body"], browser_body)

    def test_guarded_edit_refused_when_deleted(self):
        message = self._message()
        fingerprint = message.erplibre_body_fingerprint
        self._rpc("chat_user_a", ODOO_URL, message, "", attachment_ids=[])
        self.assertTrue(message._filter_empty())
        data = self._guarded(message, "Téléphone", fingerprint)
        self.assertEqual(data["erplibre_conflict"], "deleted")
        self.assertTrue(message._filter_empty())

    def test_guarded_edit_refused_on_emptied_message_same_fingerprint(self):
        message = self._message()
        self._rpc("chat_user_a", ODOO_URL, message, "", attachment_ids=[])
        data = self._guarded(
            message, "Téléphone", message.erplibre_body_fingerprint
        )
        self.assertEqual(data["erplibre_conflict"], "deleted")
        self.assertTrue(message._filter_empty())

    def test_guarded_delete_applies_when_unchanged(self):
        message = self._message(attachments=1)
        self.authenticate("chat_user_a", "chat_user_a")
        data = self.make_jsonrpc_request(
            GUARDED_URL,
            {
                "message_id": message.id,
                "body": "",
                "expected_fingerprint": message.erplibre_body_fingerprint,
                "attachment_ids": [],
            },
        )
        self.env.invalidate_all()
        self.assertNotIn("erplibre_conflict", data)
        self.assertTrue(message._filter_empty())

    def test_guarded_edit_other_author_not_found(self):
        message = self._message()
        body = message.body
        with self.assertRaises(JsonRpcException) as caught:
            self._guarded(
                message,
                "Autre",
                message.erplibre_body_fingerprint,
                login="chat_user_b",
            )
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(message.body, body)

    def test_guarded_edit_missing_message_not_found(self):
        missing = self.env["mail.message"].browse(999999999)
        with self.assertRaises(JsonRpcException) as caught:
            self._guarded(missing, "Autre", _sha256(""))
        self.assertEqual(caught.exception.code, 404)

    def test_guarded_edit_portal_user_not_found(self):
        portal = new_test_user(
            self.env, login="chat_portal", groups="base.group_portal"
        )
        self.channel.channel_member_ids = [
            (0, 0, {"partner_id": portal.partner_id.id})
        ]
        message = self.channel.sudo().message_post(
            body="Portail",
            author_id=portal.partner_id.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        body = message.body
        with self.assertRaises(JsonRpcException) as caught:
            self._guarded(
                message,
                "Autre",
                message.erplibre_body_fingerprint,
                login="chat_portal",
            )
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(message.body, body)

    def test_guarded_edit_locks_the_message_row(self):
        message = self._message()
        fingerprint = message.erplibre_body_fingerprint
        with patch.object(
            self.env.cr, "execute", wraps=self.env.cr.execute
        ) as execute:
            self._guarded(message, "Texte modifié", fingerprint)
        queries = [_sql(c.args[0]) for c in execute.call_args_list]
        lock = next(
            i
            for i, q in enumerate(queries)
            if "FOR UPDATE" in q and "mail_message" in q
        )
        write = next(
            i
            for i, q in enumerate(queries)
            if q.lstrip().startswith('UPDATE "mail_message"')
        )
        self.assertLess(lock, write)

    def test_fingerprint_field_in_fields_get_for_internal_user(self):
        fields = (
            self.env["mail.message"]
            .with_user(self.user_b)
            .fields_get(["erplibre_body_fingerprint"])
        )
        self.assertIn("erplibre_body_fingerprint", fields)

    def test_null_attachment_ids_keeps_attachments(self):
        for url in (ODOO_URL, GUARDED_URL):
            with self.subTest(url=url):
                message = self._message(attachments=2)
                ids = sorted(message.attachment_ids.ids)
                self.assertEqual(len(ids), 2)
                self._rpc(
                    "chat_user_a",
                    url,
                    message,
                    "Texte seul",
                    attachment_ids=None,
                    **self._guard_params(url, message),
                )
                self.assertEqual(sorted(message.attachment_ids.ids), ids)
                self.assertIn("Texte seul", message.body)

    def test_empty_attachment_ids_deletes_them(self):
        for url in (ODOO_URL, GUARDED_URL):
            with self.subTest(url=url):
                message = self._message(attachments=2)
                ids = message.attachment_ids.ids
                self._rpc(
                    "chat_user_a",
                    url,
                    message,
                    "Texte seul",
                    attachment_ids=[],
                    **self._guard_params(url, message),
                )
                self.assertFalse(message.attachment_ids)
                self.assertFalse(
                    self.env["ir.attachment"].browse(ids).exists()
                )
