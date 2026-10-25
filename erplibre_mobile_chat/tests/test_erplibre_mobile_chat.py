# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Publication idempotente dans Discuss par identifiant client."""

from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase


@tagged("post_install", "-at_install")
class TestErplibreMobileChat(HttpCase):
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
        cls.channel2 = cls.env["discuss.channel"].create(
            {
                "name": "chat2",
                "channel_type": "group",
                "channel_member_ids": [
                    (0, 0, {"partner_id": p.id}) for p in partners
                ],
            }
        )

    def _post(self, login, channel, uuid=None):
        self.authenticate(login, login)
        post_data = {
            "body": "hi",
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_comment",
        }
        if uuid:
            post_data["erplibre_client_uuid"] = uuid
        return self.make_jsonrpc_request(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": channel.id,
                "post_data": post_data,
            },
        )

    def _with_uuid(self, channel, uuid):
        return channel.message_ids.filtered(
            lambda m: m.erplibre_client_uuid == uuid
        )

    def test_post_same_uuid_twice_gives_one_message(self):
        r1 = self._post("chat_user_a", self.channel, "u-1")
        r2 = self._post("chat_user_a", self.channel, "u-1")
        self.assertEqual(len(self._with_uuid(self.channel, "u-1")), 1)
        self.assertEqual(
            r1["mail.message"][0]["id"], r2["mail.message"][0]["id"]
        )

    def test_other_uuid_posts_again(self):
        self._post("chat_user_a", self.channel, "u-1")
        self._post("chat_user_a", self.channel, "u-2")
        self.assertEqual(len(self._with_uuid(self.channel, "u-1")), 1)
        self.assertEqual(len(self._with_uuid(self.channel, "u-2")), 1)

    def test_uuid_of_other_author_not_adopted(self):
        r1 = self._post("chat_user_a", self.channel, "u-1")
        r2 = self._post("chat_user_b", self.channel, "u-1")
        msgs = self._with_uuid(self.channel, "u-1")
        self.assertEqual(len(msgs), 2)
        self.assertNotEqual(
            r1["mail.message"][0]["id"], r2["mail.message"][0]["id"]
        )
        self.assertEqual(
            msgs.filtered(
                lambda m: m.id == r2["mail.message"][0]["id"]
            ).author_id,
            self.user_b.partner_id,
        )

    def test_uuid_in_other_channel_not_adopted(self):
        self._post("chat_user_a", self.channel, "u-1")
        self._post("chat_user_a", self.channel2, "u-1")
        self.assertEqual(len(self._with_uuid(self.channel, "u-1")), 1)
        self.assertEqual(len(self._with_uuid(self.channel2, "u-1")), 1)

    def test_post_without_uuid_unchanged(self):
        r = self._post("chat_user_a", self.channel)
        msg = self.env["mail.message"].browse(r["mail.message"][0]["id"])
        self.assertTrue(msg.exists())
        self.assertFalse(msg.erplibre_client_uuid)

    def test_public_user_never_adopts(self):
        # Quiconque publie sans compte le fait sous ce même partenaire
        public = self.env.ref("base.public_user")
        channel = self.channel.with_user(public).sudo()
        post = {
            "body": "hi",
            "message_type": "comment",
            "erplibre_client_uuid": "u-guest",
        }
        first = channel.message_post(**post)
        second = channel.message_post(**post)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self._with_uuid(self.channel, "u-guest")), 2)
