# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Notifications « lu » et « traité » vers les appareils de l'application,
présence des navigateurs et appareils silencieux pendant ce temps."""

import hashlib
import json
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import requests
from odoo import fields
from odoo.addons.bus.websocket import _wsrequest_stack
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from .test_app_push import APP_PUSH, ENDPOINT, answer, device_keys

APP_SID = "sid-de-l-application-exemple"
BROWSER_SID = "sid-du-navigateur-exemple"


@tagged("post_install", "-at_install")
class TestErplibreReadPush(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Crée les clés VAPID d'Odoo, sans lesquelles rien ne part.
        cls.env["mail.push.device"].get_web_push_vapid_public_key()
        cls.user_a = new_test_user(
            cls.env,
            login="read_user_a",
            groups="base.group_user,base.group_partner_manager",
        )
        cls.user_b = new_test_user(
            cls.env,
            login="read_user_b",
            groups="base.group_user",
            notification_type="inbox",
        )
        cls.chat = (
            cls.env["discuss.channel"]
            .with_user(cls.user_a)
            .channel_get([cls.user_b.partner_id.id])
        )
        partners = (cls.user_a | cls.user_b).partner_id
        cls.group = cls.env["discuss.channel"].create(
            {
                "name": "Groupe lecture",
                "channel_type": "group",
                "channel_member_ids": [
                    (0, 0, {"partner_id": p.id}) for p in partners
                ],
            }
        )
        cls.records = cls.env["res.partner"].create(
            [{"name": "Alice Martin"}, {"name": "Bruno Tremblay"}]
        )

    def setUp(self):
        super().setUp()
        self.env.cr.postcommit.clear()

    def _device(self, user, endpoint=ENDPOINT, **marks):
        return (
            self.env["mail.push.device"]
            .sudo()
            .create(
                {
                    "partner_id": user.partner_id.id,
                    "endpoint": endpoint,
                    "keys": json.dumps(device_keys()),
                    **marks,
                }
            )
        )

    def _app_device(self, user, endpoint=ENDPOINT, **marks):
        return self._device(user, endpoint, erplibre_app=True, **marks)

    def _post(self, thread, user=None, body="Bonjour", **kwargs):
        return thread.with_user(user or self.user_a).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            **kwargs,
        )

    def _member(self, channel, user):
        return (
            self.env["discuss.channel.member"]
            .with_user(user)
            .search(
                [
                    ("channel_id", "=", channel.id),
                    ("partner_id", "=", user.partner_id.id),
                ]
            )
        )

    @contextmanager
    def _capture(self, status=200):
        """Simule ntfy (`status`) et rend la liste, remplie au fil des
        envois, des charges en clair passées au chiffrement."""
        sent = []
        with (
            patch.object(
                requests.Session, "post", return_value=answer(status)
            ),
            patch(
                f"{APP_PUSH}._encrypt_payload",
                side_effect=lambda content, device: sent.append(
                    json.loads(content)
                )
                or b"x",
            ),
        ):
            yield sent

    def _needaction(self, message, user):
        """Garantit à `user` une notification de boîte non lue de
        `message`."""
        Notification = self.env["mail.notification"].sudo()
        if not Notification.search(
            [
                ("mail_message_id", "=", message.id),
                ("res_partner_id", "=", user.partner_id.id),
            ]
        ):
            Notification.create(
                {
                    "mail_message_id": message.id,
                    "res_partner_id": user.partner_id.id,
                    "notification_type": "inbox",
                    "is_read": False,
                }
            )

    def _presence(self, user, poll_age, presence_age):
        """Écrit la présence d'un navigateur de `user` : dernier sondage et
        dernière activité il y a `poll_age` et `presence_age` secondes."""
        now = fields.Datetime.now()
        values = {
            "erplibre_browser_poll": now - timedelta(seconds=poll_age),
            "erplibre_browser_presence": now - timedelta(seconds=presence_age),
        }
        Presence = self.env["bus.presence"].sudo()
        presence = Presence.search([("user_id", "=", user.id)])
        if presence:
            presence.write(values)
        else:
            Presence.create({"user_id": user.id, **values})

    @contextmanager
    def _websocket(self, user, sid):
        """Rejoue une requête du bus de `user` par websocket : `wsrequest`
        porte une session d'id `sid`, et la validation de update_presence
        reste dans la transaction du test."""
        env = self.env(user=user)
        fake = SimpleNamespace(
            session=SimpleNamespace(sid=sid, uid=user.id),
            cookies={},
            env=env,
            update_context=lambda **kw: None,
        )
        _wsrequest_stack.push(fake)
        try:
            with patch.object(self.env.cr, "commit"):
                yield env
        finally:
            _wsrequest_stack.pop()

    def _read_payload(self, channel, message):
        return {
            "erplibre": {
                "v": 1,
                "type": "read",
                "channel_id": channel.id,
                "last_message_id": message.id,
            }
        }

    # Notifications « lu »

    def test_mark_as_read_sends_read_push_after_commit(self):
        message = self._post(self.chat)
        self._app_device(self.user_b)
        self.env.cr.postcommit.clear()
        with self._capture() as sent:
            self._member(self.chat, self.user_b)._mark_as_read(message.id)
            self.assertEqual(sent, [])
            self.env.cr.postcommit.run()
        self.assertEqual(sent, [self._read_payload(self.chat, message)])

    def test_own_post_sends_read_push(self):
        self._app_device(self.user_a)
        with self._capture() as sent:
            message = self._post(self.chat)
            self.env.cr.postcommit.run()
        self.assertEqual(sent, [self._read_payload(self.chat, message)])

    def test_no_read_push_when_seen_does_not_advance(self):
        message = self._post(self.chat)
        self._app_device(self.user_b)
        member = self._member(self.chat, self.user_b)
        member._mark_as_read(message.id)
        self.env.cr.postcommit.clear()
        with self._capture() as sent:
            member._mark_as_read(message.id)
            self.env.cr.postcommit.run()
        self.assertEqual(sent, [])

    def test_two_marks_in_one_request_send_one_read_push_with_the_highest_id(
        self,
    ):
        first = self._post(self.chat)
        second = self._post(self.chat, body="Encore")
        in_group = self._post(self.group)
        self._app_device(self.user_b)
        self.env.cr.postcommit.clear()
        with self._capture() as sent:
            member = self._member(self.chat, self.user_b)
            member._mark_as_read(first.id)
            member._mark_as_read(second.id)
            self._member(self.group, self.user_b)._mark_as_read(in_group.id)
            self.env.cr.postcommit.run()
        self.assertEqual(
            sorted(sent, key=lambda p: p["erplibre"]["channel_id"]),
            sorted(
                [
                    self._read_payload(self.chat, second),
                    self._read_payload(self.group, in_group),
                ],
                key=lambda p: p["erplibre"]["channel_id"],
            ),
        )

    def test_read_push_never_reaches_a_browser_device(self):
        message = self._post(self.chat)
        self._device(self.user_b)
        self.env.cr.postcommit.clear()
        with patch.object(
            requests.Session, "post", return_value=answer(201)
        ) as post:
            self._member(self.chat, self.user_b)._mark_as_read(message.id)
            self.env.cr.postcommit.run()
        post.assert_not_called()

    # Notifications « traité »

    def test_set_message_done_sends_inbox_done_with_threads(self):
        first, second = self.records
        messages = (
            self._post(first, partner_ids=self.user_b.partner_id.ids)
            | self._post(second, partner_ids=self.user_b.partner_id.ids)
            | self._post(self.group, partner_ids=self.user_b.partner_id.ids)
        )
        for message in messages:
            self._needaction(message, self.user_b)
        self._app_device(self.user_b)
        self._app_device(self.user_a, f"{ENDPOINT}a")
        self.env.cr.postcommit.clear()
        with self._capture() as sent:
            result = messages.with_user(self.user_b).set_message_done()
            self.assertEqual(sent, [])
            self.env.cr.postcommit.run()
        self.assertIsNone(result)
        self.assertEqual(
            sent,
            [
                {
                    "erplibre": {
                        "v": 1,
                        "type": "inbox_done",
                        "threads": [
                            ["res.partner", first.id],
                            ["res.partner", second.id],
                        ],
                    }
                }
            ],
        )

    def test_mark_all_as_read_with_domain_sends_one_inbox_done(self):
        message = self._post(
            self.records[0], partner_ids=self.user_b.partner_id.ids
        )
        self._needaction(message, self.user_b)
        self._app_device(self.user_b)
        self.env.cr.postcommit.clear()
        with self._capture() as sent:
            result = (
                self.env["mail.message"]
                .with_user(self.user_b)
                .mark_all_as_read([("id", "=", message.id)])
            )
            self.env.cr.postcommit.run()
        self.assertEqual(result, [message.id])
        self.assertEqual(
            sent,
            [
                {
                    "erplibre": {
                        "v": 1,
                        "type": "inbox_done",
                        "threads": [["res.partner", self.records[0].id]],
                    }
                }
            ],
        )

    def test_mark_all_as_read_over_40_threads_sends_null(self):
        records = self.env["res.partner"].create(
            [{"name": f"Fiche {index}"} for index in range(41)]
        )
        messages = self.env["mail.message"].create(
            [
                {
                    "model": "res.partner",
                    "res_id": record.id,
                    "body": "Bonjour",
                    "message_type": "comment",
                    "author_id": self.user_a.partner_id.id,
                }
                for record in records
            ]
        )
        for message in messages:
            self._needaction(message, self.user_b)
        self._app_device(self.user_b)
        self.env.cr.postcommit.clear()
        with self._capture() as sent:
            result = (
                self.env["mail.message"]
                .with_user(self.user_b)
                .mark_all_as_read()
            )
            self.env.cr.postcommit.run()
        self.assertIsNone(result)
        self.assertEqual(
            sent,
            [{"erplibre": {"v": 1, "type": "inbox_done", "threads": None}}],
        )
        self.assertFalse(
            self.env["mail.notification"].search_count(
                [
                    ("res_partner_id", "=", self.user_b.partner_id.id),
                    ("is_read", "=", False),
                ]
            )
        )

    def test_inbox_done_without_record_threads_sends_nothing(self):
        message = self._post(
            self.group, partner_ids=self.user_b.partner_id.ids
        )
        self._needaction(message, self.user_b)
        self._app_device(self.user_b)
        self.env.cr.postcommit.clear()
        with self._capture() as sent:
            message.with_user(self.user_b).set_message_done()
            self.env["mail.message"].with_user(self.user_b).mark_all_as_read()
            self.env.cr.postcommit.run()
        self.assertEqual(sent, [])

    # Présence des navigateurs

    def test_browser_presence_written_for_a_browser_session(self):
        self._app_device(
            self.user_b,
            erplibre_session_hash=hashlib.sha256(APP_SID.encode()).hexdigest(),
        )
        with self._websocket(self.user_b, BROWSER_SID) as env:
            env["ir.websocket"]._update_bus_presence(120000, {})
        presence = self.env["bus.presence"].search(
            [("user_id", "=", self.user_b.id)]
        )
        now = fields.Datetime.now()
        self.assertTrue(presence.erplibre_browser_poll)
        self.assertLessEqual(
            now - presence.erplibre_browser_poll, timedelta(seconds=5)
        )
        self.assertLessEqual(
            abs(
                now
                - timedelta(seconds=120)
                - presence.erplibre_browser_presence
            ),
            timedelta(seconds=5),
        )
        self.assertTrue(self.user_b._erplibre_browser_online())

    def test_the_apps_own_session_never_counts_as_a_browser(self):
        self._app_device(
            self.user_b,
            erplibre_session_hash=hashlib.sha256(APP_SID.encode()).hexdigest(),
        )
        with self._websocket(self.user_b, APP_SID) as env:
            env["ir.websocket"]._update_bus_presence(0, {})
        presence = self.env["bus.presence"].search(
            [("user_id", "=", self.user_b.id)]
        )
        self.assertTrue(presence.last_poll)
        self.assertFalse(presence.erplibre_browser_poll)
        self.assertFalse(presence.erplibre_browser_presence)
        self.assertFalse(self.user_b._erplibre_browser_online())

    def test_quiet_device_skipped_while_browser_online(self):
        quiet = self._app_device(self.user_b, erplibre_quiet_while_online=True)
        loud = self._app_device(self.user_b, f"{ENDPOINT}loud")
        self._presence(self.user_b, poll_age=10, presence_age=60)
        with patch.object(
            requests.Session, "post", return_value=answer(201)
        ) as post:
            self._post(self.chat)
            self.env.cr.postcommit.run()
        endpoints = [c.args[0] for c in post.call_args_list]
        self.assertEqual(endpoints, [loud.endpoint])
        self.assertNotIn(quiet.endpoint, endpoints)

    def test_an_away_browser_lets_the_push_through(self):
        device = self._app_device(
            self.user_b, erplibre_quiet_while_online=True
        )
        self._presence(self.user_b, poll_age=10, presence_age=31 * 60)
        self.assertFalse(self.user_b._erplibre_browser_online())
        with patch.object(
            requests.Session, "post", return_value=answer(201)
        ) as post:
            self._post(self.chat)
            self.env.cr.postcommit.run()
        self.assertEqual(
            [c.args[0] for c in post.call_args_list], [device.endpoint]
        )

    def test_a_stale_browser_lets_the_push_through(self):
        device = self._app_device(
            self.user_b, erplibre_quiet_while_online=True
        )
        self._presence(self.user_b, poll_age=66, presence_age=66)
        self.assertFalse(self.user_b._erplibre_browser_online())
        with patch.object(
            requests.Session, "post", return_value=answer(201)
        ) as post:
            self._post(self.chat)
            self.env.cr.postcommit.run()
        self.assertEqual(
            [c.args[0] for c in post.call_args_list], [device.endpoint]
        )

    def test_read_push_sent_even_while_browser_online(self):
        message = self._post(self.chat)
        self._app_device(self.user_b, erplibre_quiet_while_online=True)
        self._presence(self.user_b, poll_age=10, presence_age=60)
        self.assertTrue(self.user_b._erplibre_browser_online())
        self.env.cr.postcommit.clear()
        with self._capture() as sent:
            self._member(self.chat, self.user_b)._mark_as_read(message.id)
            self.env.cr.postcommit.run()
        self.assertEqual(sent, [self._read_payload(self.chat, message)])
