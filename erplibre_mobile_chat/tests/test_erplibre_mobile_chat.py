# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Publication idempotente dans Discuss par identifiant client."""

from unittest.mock import patch

from odoo.addons.bus.models.bus import channel_with_db, json_dump
from odoo.addons.erplibre_mobile_chat.models import discuss_channel as dc
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


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
        self.assertFalse(first.erplibre_client_uuid)
        self.assertFalse(second.erplibre_client_uuid)


@tagged("post_install", "-at_install")
class TestErplibreMobileChatCreate(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env, login="chat_user_a", groups="base.group_user"
        )
        cls.user_b = new_test_user(
            cls.env, login="chat_user_b", groups="base.group_user"
        )
        cls.user_c = new_test_user(
            cls.env, login="chat_user_c", groups="base.group_user"
        )
        cls.admin = new_test_user(
            cls.env, login="chat_admin", groups="base.group_system"
        )

    def _channels(self, uuid):
        return (
            self.env["discuss.channel"]
            .sudo()
            .search([("erplibre_client_uuid", "=", uuid)])
        )

    def _group(self, user, uuid, partners):
        model = self.env["discuss.channel"].with_user(user)
        if uuid:
            model = model.with_context(erplibre_client_uuid=uuid)
        return model.create_group(partners.ids)

    def _count(self, model):
        if model == "bus.bus":
            return len(self._bus_values())
        return self.env[model].sudo().search_count([])

    def _bus_values(self):
        # Dépend de l'interne de bus.bus._sendone : les notifications
        # attendent le précommit, elles ne sont pas encore des lignes
        # bus.bus pendant le test.
        return list(self.env.cr.precommit.data.get("bus.bus.values", []))

    def test_create_group_same_uuid_twice_gives_one_group(self):
        partners = self.user_b.partner_id
        first = self._group(self.user_a, "g-1", partners)
        second = self._group(self.user_a, "g-1", partners)
        self.assertEqual(first, second)
        self.assertEqual(len(self._channels("g-1")), 1)

    def test_channel_create_same_uuid_twice_gives_one_channel(self):
        model = self.env["discuss.channel"].with_user(self.user_a)
        model = model.with_context(erplibre_client_uuid="c-1")
        first = model.channel_create("room", False)
        second = model.channel_create("room", False)
        self.assertEqual(first, second)
        self.assertEqual(len(self._channels("c-1")), 1)

    def test_retry_posts_no_second_created_message(self):
        model = self.env["discuss.channel"].with_user(self.user_a)
        model = model.with_context(erplibre_client_uuid="c-2")
        channel = model.channel_create("room", False)
        messages = self._count("mail.message")
        bus = self._count("bus.bus")
        model.channel_create("room", False)
        self.assertEqual(self._count("mail.message"), messages)
        self.assertEqual(self._count("bus.bus"), bus)
        self.assertEqual(
            len(
                channel.sudo().message_ids.filtered(
                    lambda m: "created this channel" in (m.body or "")
                )
            ),
            1,
        )

    def test_group_retry_broadcasts_nothing(self):
        partners = self.user_b.partner_id
        self._group(self.user_a, "g-2", partners)
        bus = self._count("bus.bus")
        messages = self._count("mail.message")
        self._group(self.user_a, "g-2", partners)
        self.assertEqual(self._count("bus.bus"), bus)
        self.assertEqual(self._count("mail.message"), messages)

    def test_uuid_of_other_user_not_adopted(self):
        partners = self.user_c.partner_id
        first = self._group(self.user_a, "g-3", partners)
        second = self._group(self.user_b, "g-3", partners)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self._channels("g-3")), 2)

    def test_create_without_uuid_unchanged(self):
        partners = self.user_b.partner_id
        first = self._group(self.user_a, None, partners)
        second = self._group(self.user_a, None, partners)
        self.assertNotEqual(first, second)
        self.assertFalse(first.sudo().erplibre_client_uuid)

    def test_uuid_with_several_records_refused(self):
        model = self.env["discuss.channel"].with_context(
            erplibre_client_uuid="m-1"
        )
        with self.assertRaises(UserError):
            model.create(
                [
                    {"name": "a", "channel_type": "channel"},
                    {"name": "b", "channel_type": "channel"},
                ]
            )

    def _group_of_two(self):
        return self._group(
            self.admin, None, self.user_a.partner_id | self.user_b.partner_id
        )

    def test_remove_member_by_admin_leaves_with_notice(self):
        channel = self._group_of_two().sudo()
        partner = self.user_b.partner_id
        bus_before = len(self._bus_values())
        channel.with_user(self.admin).erplibre_remove_member(partner.id)
        self.assertNotIn(partner, channel.channel_member_ids.partner_id)
        self.assertTrue(
            channel.message_ids.filtered(
                lambda m: "left the channel" in (m.body or "")
                and m.author_id == partner
            )
        )
        leave = [
            v
            for v in self._bus_values()[bus_before:]
            if '"type":"discuss.channel/leave"' in v["message"]
        ]
        target = json_dump(channel_with_db(self.env.cr.dbname, partner))
        self.assertTrue(any(v["channel"] == target for v in leave))

    def test_remove_member_refused_for_non_admin(self):
        channel = self._group_of_two().sudo()
        with self.assertRaises(AccessError):
            channel.with_user(self.user_a).erplibre_remove_member(
                self.user_b.partner_id.id
            )
        self.assertIn(
            self.user_b.partner_id, channel.channel_member_ids.partner_id
        )

    def test_remove_member_refused_in_chat(self):
        chat = (
            self.env["discuss.channel"]
            .with_user(self.user_a)
            .channel_get([self.user_b.partner_id.id])
        )
        chat = self.env["discuss.channel"].browse(chat.id)
        with self.assertRaises(UserError):
            chat.with_user(self.admin).erplibre_remove_member(
                self.user_b.partner_id.id
            )

    def test_retry_store_equals_first_store(self):
        model = self.env["discuss.channel"].with_user(self.user_a)
        model = model.with_context(erplibre_client_uuid="c-3")
        first = model.channel_create("room", False)
        second = model.channel_create("room", False)
        self.assertEqual(Store(first).get_result(), Store(second).get_result())

    def test_create_takes_advisory_lock(self):
        # Un test à deux curseurs ne tient pas dans la transaction unique
        # du test ; on vérifie que le verrou est pris avant la recherche.
        model = self.env["discuss.channel"].with_user(self.user_a)
        model = model.with_context(erplibre_client_uuid="c-4")
        with patch.object(
            dc, "erplibre_lock_uuid", wraps=dc.erplibre_lock_uuid
        ) as lock:
            model.channel_create("room", False)
        lock.assert_called_with(model.env, dc.LOCK_NAMESPACE_CHANNEL, "c-4")

    def test_lock_statement_executes(self):
        with patch.object(
            self.env.cr, "execute", wraps=self.env.cr.execute
        ) as execute:
            dc.erplibre_lock_uuid(self.env, dc.LOCK_NAMESPACE_MESSAGE, "x")
        self.assertIn("pg_advisory_xact_lock", execute.call_args[0][0])

    def test_remove_member_missing_partner_refused(self):
        channel = self._group_of_two().sudo()
        with self.assertRaises(UserError):
            channel.with_user(self.admin).erplibre_remove_member(999999999)

    def test_remove_member_non_member_refused(self):
        channel = self._group_of_two().sudo()
        with self.assertRaises(UserError):
            channel.with_user(self.admin).erplibre_remove_member(
                self.user_c.partner_id.id
            )
        self.assertFalse(
            channel.message_ids.filtered(
                lambda m: "left the channel" in (m.body or "")
            )
        )
        self.assertEqual(len(channel.channel_member_ids), 3)

    def test_unique_index_refuses_duplicate_channel(self):
        first = self._group(self.user_a, "g-9", self.user_b.partner_id).sudo()
        other = self._group(self.user_a, None, self.user_b.partner_id).sudo()
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                other.erplibre_client_uuid = first.erplibre_client_uuid
                other.flush_recordset()

    def test_unique_index_refuses_duplicate_message(self):
        channel = self._group(self.user_a, None, self.user_b.partner_id).sudo()
        vals = {
            "model": "discuss.channel",
            "res_id": channel.id,
            "author_id": self.user_a.partner_id.id,
            "body": "hi",
            "message_type": "comment",
            "erplibre_client_uuid": "m-9",
        }
        # Création directe : elle contourne le dédoublonnage de message_post.
        self.env["mail.message"].create(vals)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self.env["mail.message"].create(vals)

    def test_message_post_locks_only_with_uuid(self):
        channel = self._group(
            self.user_a, None, self.user_b.partner_id
        ).with_user(self.user_a)
        with patch.object(
            dc, "erplibre_lock_uuid", wraps=dc.erplibre_lock_uuid
        ) as lock:
            channel.message_post(body="hi", message_type="comment")
            lock.assert_not_called()
            channel.message_post(
                body="hi", message_type="comment", erplibre_client_uuid="m-8"
            )
        lock.assert_called_once_with(
            channel.env, dc.LOCK_NAMESPACE_MESSAGE, "m-8"
        )

    def _check_init_dedupes(self, model, table, index, make):
        cr = self.env.cr
        cr.execute(f"DROP INDEX {index}")
        ids = [make(i) for i in range(2)]
        self.env[model].sudo().init()
        cr.execute(
            f"SELECT id FROM {table} WHERE id IN %s"
            " AND erplibre_client_uuid = 'dup'",
            (tuple(ids),),
        )
        self.assertEqual([r[0] for r in cr.fetchall()], [min(ids)])
        cr.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,))
        self.assertTrue(cr.fetchone())

    def test_init_clears_duplicate_channel_uuid(self):
        def make(i):
            self.env.cr.execute(
                "INSERT INTO discuss_channel (name, channel_type, create_uid,"
                " erplibre_client_uuid) VALUES ('d', 'group', %s, 'dup')"
                " RETURNING id",
                (self.user_a.id,),
            )
            return self.env.cr.fetchone()[0]

        self._check_init_dedupes(
            "discuss.channel",
            "discuss_channel",
            "discuss_channel_erplibre_client_uuid_uniq",
            make,
        )

    def test_init_clears_duplicate_message_uuid(self):
        def make(i):
            self.env.cr.execute(
                "INSERT INTO mail_message (model, res_id, author_id,"
                " message_type, erplibre_client_uuid) VALUES"
                " ('discuss.channel', 1, %s, 'comment', 'dup')"
                " RETURNING id",
                (self.user_a.partner_id.id,),
            )
            return self.env.cr.fetchone()[0]

        self._check_init_dedupes(
            "mail.message",
            "mail_message",
            "mail_message_erplibre_client_uuid_uniq",
            make,
        )
