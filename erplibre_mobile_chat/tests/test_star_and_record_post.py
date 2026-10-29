# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Favori idempotent, publication idempotente sur un enregistrement et
niveau du module."""

from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase


@tagged("post_install", "-at_install")
class TestErplibreStarAndRecordPost(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env,
            login="chat_user_a",
            groups="base.group_user,base.group_partner_manager",
        )
        cls.user_b = new_test_user(
            cls.env, login="chat_user_b", groups="base.group_user"
        )
        cls.user_c = new_test_user(
            cls.env, login="chat_user_c", groups="base.group_user"
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
        cls.record = cls.env["res.partner"].create({"name": "Alice Martin"})
        cls.record2 = cls.env["res.partner"].create({"name": "Contact démo"})

    def _message(self):
        return self.channel.with_user(self.user_b).message_post(
            body="Bonjour",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def _post_on(self, record, uuid, login="chat_user_a"):
        self.authenticate(login, login)
        data = self.make_jsonrpc_request(
            "/mail/message/post",
            {
                "thread_model": record._name,
                "thread_id": record.id,
                "post_data": {
                    "body": "Réponse au fil",
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_note",
                    "erplibre_client_uuid": uuid,
                },
            },
        )
        return data["mail.message"][0]["id"]

    def _record_messages(self, record, uuid):
        return (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("erplibre_client_uuid", "=", uuid),
                ]
            )
        )

    def test_set_starred_is_idempotent_and_sends_bus_once(self):
        # user_b n'a que le groupe interne : aucun droit d'écriture sur
        # res.partner.
        message = self._message().with_user(self.user_b)
        users = type(self.env["res.users"])
        with patch.object(users, "_bus_send") as bus:
            for _attempt in range(2):
                result = message.erplibre_set_starred(True)
            self.assertTrue(message.starred)
            self.assertEqual(
                result["mail.message"][0],
                {"id": message.id, "starred": True},
            )
            bus.assert_called_once_with(
                "mail.message/toggle_star",
                {"message_ids": [message.id], "starred": True},
            )
            bus.reset_mock()
            for _attempt in range(2):
                message.erplibre_set_starred(False)
            self.assertFalse(message.starred)
            bus.assert_called_once_with(
                "mail.message/toggle_star",
                {"message_ids": [message.id], "starred": False},
            )

    def test_set_starred_refuses_unreadable_message(self):
        message = self._message().with_user(self.user_c)
        with self.assertRaises(AccessError):
            message.erplibre_set_starred(True)
        self.assertFalse(message.sudo().starred_partner_ids)

    def test_record_post_dedup_on_partner(self):
        first = self._post_on(self.record, "r-1")
        second = self._post_on(self.record, "r-1")
        self.assertEqual(first, second)
        self.assertEqual(
            self._record_messages(self.record, "r-1").ids, [first]
        )

    def test_record_post_dedup_ignores_other_record(self):
        first = self._post_on(self.record, "r-2")
        second = self._post_on(self.record2, "r-2")
        self.assertNotEqual(first, second)
        self.assertEqual(
            self._record_messages(self.record, "r-2").ids, [first]
        )
        self.assertEqual(
            self._record_messages(self.record2, "r-2").ids, [second]
        )

    def test_record_post_dedup_keeps_post_access(self):
        self._post_on(self.record, "r-3")
        self.user_a.groups_id -= self.env.ref("base.group_partner_manager")
        with self.assertRaises(AccessError):
            self.record.with_user(self.user_a).message_post(
                body="Réponse au fil",
                message_type="comment",
                erplibre_client_uuid="r-3",
            )

    def test_level_field_selection_in_fields_get_for_internal_user(self):
        self.authenticate("chat_user_b", "chat_user_b")
        fields = self.make_jsonrpc_request(
            "/web/dataset/call_kw/mail.message/fields_get",
            {
                "model": "mail.message",
                "method": "fields_get",
                "args": [["erplibre_chat_level"]],
                "kwargs": {"attributes": ["selection", "type"]},
            },
        )
        self.assertEqual(
            fields["erplibre_chat_level"]["selection"],
            [["1.4", "1.4"], ["1.5", "1.5"]],
        )
        message = self._message().with_user(self.user_b)
        self.assertEqual(message.erplibre_chat_level, "1.5")
