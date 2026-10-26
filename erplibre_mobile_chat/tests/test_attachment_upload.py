# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Téléversement idempotent d'une pièce jointe par identifiant client."""

import hashlib
import io
from unittest.mock import ANY, patch

from odoo import http
from odoo.addons.erplibre_mobile_chat.models import discuss_channel as dc
from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger
from PIL import Image
from psycopg2 import IntegrityError

UPLOAD_URL = "/erplibre_mobile_chat/attachment/upload"
LOCK_TARGET = (
    "odoo.addons.erplibre_mobile_chat.controllers.attachment"
    ".erplibre_lock_uuid"
)


def _jpeg(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (40, 120, 200)).save(buffer, "JPEG")
    return buffer.getvalue()


@tagged("post_install", "-at_install")
class TestErplibreAttachmentUpload(HttpCase):
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

    def _upload(
        self,
        login,
        uuid=None,
        content=b"hello",
        name="note.txt",
        url=UPLOAD_URL,
        **fields,
    ):
        """Téléverse `content` comme le navigateur, en attente par défaut,
        et rend la réponse HTTP."""
        self.authenticate(login, login)
        data = {
            "csrf_token": http.Request.csrf_token(self),
            "thread_id": self.channel.id,
            "thread_model": "discuss.channel",
            "is_pending": "true",
            **fields,
        }
        if uuid:
            data["client_uuid"] = uuid
        return self.url_open(url, data, files={"ufile": (name, content)})

    def _attachment_id(self, response):
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]["ir.attachment"][0]["id"]

    def _with_uuid(self, uuid):
        return (
            self.env["ir.attachment"]
            .sudo()
            .search([("erplibre_client_uuid", "=", uuid)])
        )

    def test_upload_same_uuid_twice_gives_one_attachment(self):
        first = self._attachment_id(self._upload("chat_user_a", "a-1"))
        second = self._attachment_id(self._upload("chat_user_a", "a-1"))
        self.assertEqual(first, second)
        self.assertEqual(self._with_uuid("a-1").ids, [first])

    def test_uuid_of_other_user_not_adopted(self):
        first = self._attachment_id(self._upload("chat_user_a", "a-2"))
        second = self._attachment_id(self._upload("chat_user_b", "a-2"))
        self.assertNotEqual(first, second)
        attachments = self._with_uuid("a-2")
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments.browse(second).create_uid, self.user_b)

    def test_upload_without_uuid_refused(self):
        count = self.env["ir.attachment"].sudo().search_count([])
        response = self._upload("chat_user_a")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.env["ir.attachment"].sudo().search_count([]), count
        )

    def test_public_user_gets_not_found(self):
        self.authenticate(None, None)
        response = self.url_open(
            UPLOAD_URL,
            {
                "csrf_token": http.Request.csrf_token(self),
                "thread_id": self.channel.id,
                "thread_model": "discuss.channel",
                "client_uuid": "a-3",
            },
            files={"ufile": ("note.txt", b"hello")},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self._with_uuid("a-3"))

    def test_upload_without_csrf_token_refused(self):
        self.authenticate("chat_user_a", "chat_user_a")
        response = self.url_open(
            UPLOAD_URL,
            {
                "thread_id": self.channel.id,
                "thread_model": "discuss.channel",
                "is_pending": "true",
                "client_uuid": "a-14",
            },
            files={"ufile": ("note.txt", b"hello")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self._with_uuid("a-14"))

    def test_portal_user_gets_not_found(self):
        portal = new_test_user(
            self.env, login="chat_portal", groups="base.group_portal"
        )
        self.channel.channel_member_ids = [
            (0, 0, {"partner_id": portal.partner_id.id})
        ]
        for _attempt in range(2):
            response = self._upload("chat_portal", "a-15")
            self.assertEqual(response.status_code, 404)
        self.assertFalse(self._with_uuid("a-15"))

    def test_other_thread_model_gets_not_found(self):
        response = self._upload(
            "chat_user_a",
            "a-5",
            thread_model="res.partner",
            thread_id=self.user_a.partner_id.id,
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self._with_uuid("a-5"))

    def test_pending_upload_is_placeholder(self):
        attachment = self.env["ir.attachment"].browse(
            self._attachment_id(self._upload("chat_user_a", "a-6"))
        )
        self.assertEqual(attachment.res_model, "mail.compose.message")
        self.assertEqual(attachment.res_id, 0)
        self.assertEqual(attachment.create_uid, self.user_a)

    def test_large_jpeg_kept_original(self):
        content = _jpeg(2400, 1600)
        attachment = self.env["ir.attachment"].browse(
            self._attachment_id(
                self._upload("chat_user_a", "a-7", content, "photo.jpg")
            )
        )
        self.assertEqual(
            attachment.checksum, hashlib.sha1(content).hexdigest()
        )
        self.assertEqual(Image.open(io.BytesIO(attachment.raw)).width, 2400)

    def test_odoo_route_reduces_large_jpeg(self):
        attachment = self.env["ir.attachment"].browse(
            self._attachment_id(
                self._upload(
                    "chat_user_a",
                    content=_jpeg(2400, 1600),
                    name="photo.jpg",
                    url="/mail/attachment/upload",
                )
            )
        )
        size = Image.open(io.BytesIO(attachment.raw)).size
        self.assertEqual(max(size), 1920)

    def test_voice_sets_voice_metadata(self):
        response = self._upload(
            "chat_user_a", "a-8", name="voice.mp3", voice="true"
        )
        attachment = self.env["ir.attachment"].browse(
            self._attachment_id(response)
        )
        self.assertTrue(attachment.voice_ids)
        self.assertIs(
            response.json()["data"]["ir.attachment"][0]["voice"], True
        )

    def test_retry_does_not_add_voice_metadata(self):
        for _attempt in range(2):
            response = self._upload(
                "chat_user_a", "a-9", name="voice.mp3", voice="true"
            )
        attachment = self.env["ir.attachment"].browse(
            self._attachment_id(response)
        )
        self.assertEqual(len(attachment.voice_ids), 1)
        self.assertIs(
            response.json()["data"]["ir.attachment"][0]["voice"], True
        )

    def test_upload_takes_advisory_lock(self):
        # Un test à deux curseurs ne tient pas dans la transaction unique
        # du test ; on vérifie que le téléversement demande le verrou de
        # l'identifiant dans l'espace des pièces jointes.
        with patch(LOCK_TARGET, wraps=dc.erplibre_lock_uuid) as lock:
            self._attachment_id(self._upload("chat_user_a", "a-10"))
        lock.assert_called_once_with(ANY, dc.LOCK_NAMESPACE_ATTACHMENT, "a-10")

    def test_unique_index_refuses_duplicate_attachment(self):
        vals = {"name": "d", "raw": b"x", "erplibre_client_uuid": "a-11"}
        model = self.env["ir.attachment"].with_user(self.user_a)
        model.create(vals)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                model.create(vals)

    def test_upgrade_clears_duplicate_uuids(self):
        cr = self.env.cr
        index = "ir_attachment_erplibre_client_uuid_uniq"
        cr.execute(f"DROP INDEX {index}")
        ids = []
        for _row in range(2):
            cr.execute(
                "INSERT INTO ir_attachment (name, type, create_uid,"
                " erplibre_client_uuid) VALUES ('d', 'binary', %s, 'dup')"
                " RETURNING id",
                (self.user_a.id,),
            )
            ids.append(cr.fetchone()[0])
        self.env["ir.attachment"].init()
        cr.execute(
            "SELECT id FROM ir_attachment WHERE id IN %s"
            " AND erplibre_client_uuid = 'dup'",
            (tuple(ids),),
        )
        self.assertEqual([r[0] for r in cr.fetchall()], [min(ids)])
        cr.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,))
        self.assertTrue(cr.fetchone())

    def test_post_links_uploaded_attachment(self):
        attachment_id = self._attachment_id(
            self._upload("chat_user_a", "a-12")
        )
        data = self.make_jsonrpc_request(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": self.channel.id,
                "post_data": {
                    "body": "hi",
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_comment",
                    "attachment_ids": [attachment_id],
                },
                "attachment_tokens": [False],
            },
        )
        message = self.env["mail.message"].browse(
            data["mail.message"][0]["id"]
        )
        attachment = self.env["ir.attachment"].browse(attachment_id)
        self.assertEqual(message.attachment_ids, attachment)
        self.assertEqual(attachment.res_model, "discuss.channel")
        self.assertEqual(attachment.res_id, self.channel.id)

    def test_retry_without_read_access_answers_error(self):
        self._attachment_id(
            self._upload("chat_user_a", "a-13", is_pending="false")
        )
        self.channel.channel_member_ids.filtered(
            lambda m: m.partner_id == self.user_a.partner_id
        ).unlink()
        response = self._upload("chat_user_a", "a-13", is_pending="false")
        self.assertEqual(response.status_code, 200)
        self.assertIn("error", response.json())
        self.assertEqual(len(self._with_uuid("a-13")), 1)
