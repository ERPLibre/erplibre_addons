# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Appareils de l'application : marque par la route, charge portant
l'identifiant du message et le type du canal, et pour un appareil en charge
v 2 la mention et l'activité d'un navigateur du destinataire, envoi après
validation par l'expéditeur du module ; tout autre appareil suit le code
d'Odoo."""

import base64
import hashlib
import importlib.util
import json
import os
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from odoo import fields
from odoo.addons.bus.websocket import _wsrequest_stack
from odoo.addons.mail.models import mail_push as mail_push_module
from odoo.addons.mail.models import mail_thread as mail_thread_module
from odoo.addons.mail.tools.web_push import push_to_end_point
from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase
from odoo.tools.misc import file_path
from odoo.tools.sql import column_exists

APP_PUSH = "odoo.addons.erplibre_mobile_chat.tools.app_push"
WEB_PUSH_LOGGER = "odoo.addons.mail.tools.web_push"
ENDPOINT = "https://ntfy.exemple.test/upab12cd34"
APP_SID = "sid-de-l-application-exemple"
BROWSER_SID = "sid-du-navigateur-exemple"
MIGRATION_16 = "erplibre_mobile_chat/migrations/18.0.1.6.0/post-migration.py"


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def device_keys():
    """Rend des clés de navigateur valides : un point P-256 non compressé
    (p256dh) et 16 octets aléatoires (auth), en base64url sans
    remplissage, comme `PushSubscription.toJSON()`."""
    key = ec.generate_private_key(ec.SECP256R1())
    point = key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    return {"p256dh": _b64(point), "auth": _b64(os.urandom(16))}


def answer(status):
    return Mock(status_code=status, text="")


def write_browser_presence(env, user, poll_age, presence_age):
    """Écrit (sudo) la présence d'un navigateur de `user` : dernier sondage
    et dernière activité il y a `poll_age` et `presence_age` secondes."""
    now = fields.Datetime.now()
    values = {
        "erplibre_browser_user_id": user.id,
        "erplibre_browser_poll": now - timedelta(seconds=poll_age),
        "erplibre_browser_presence": now - timedelta(seconds=presence_age),
    }
    Presence = env["bus.presence"].sudo()
    presence = Presence.search([("user_id", "=", user.id)])
    if presence:
        presence.write(values)
    else:
        Presence.create({"user_id": user.id, **values})


@contextmanager
def bus_request(env, user, sid):
    """Rejoue une requête du bus de `user` par websocket : `wsrequest`
    porte une session d'id `sid`, et la validation de update_presence
    reste dans la transaction du test. Rend l'environnement de `user`."""
    user_env = env(user=user)
    fake = SimpleNamespace(
        session=SimpleNamespace(sid=sid, uid=user.id),
        cookies={},
        env=user_env,
        update_context=lambda **kw: None,
    )
    _wsrequest_stack.push(fake)
    try:
        with patch.object(env.cr, "commit"):
            yield user_env
    finally:
        _wsrequest_stack.pop()


@tagged("post_install", "-at_install")
class TestErplibreAppPush(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vapid_public_key = cls.env[
            "mail.push.device"
        ].get_web_push_vapid_public_key()
        cls.user_a = new_test_user(
            cls.env,
            login="push_user_a",
            groups="base.group_user,base.group_partner_manager",
        )
        cls.user_b = new_test_user(
            cls.env, login="push_user_b", groups="base.group_user"
        )
        cls.user_c = new_test_user(
            cls.env, login="push_user_c", groups="base.group_user"
        )
        cls.chat = (
            cls.env["discuss.channel"]
            .with_user(cls.user_a)
            .channel_get([cls.user_b.partner_id.id])
        )
        partners = (cls.user_a | cls.user_b | cls.user_c).partner_id
        members = [(0, 0, {"partner_id": p.id}) for p in partners]
        cls.group = cls.env["discuss.channel"].create(
            {
                "name": "Groupe démo",
                "channel_type": "group",
                "channel_member_ids": members,
            }
        )
        cls.channel = cls.env["discuss.channel"].create(
            {
                "name": "général-démo",
                "channel_type": "channel",
                "channel_member_ids": members,
            }
        )
        cls.record = cls.env["res.partner"].create({"name": "Alice Martin"})
        cls.record.message_subscribe(partner_ids=cls.user_b.partner_id.ids)

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

    def _v2_device(self, user, endpoint=ENDPOINT, mode="ring"):
        return self._app_device(
            user,
            endpoint,
            erplibre_browser_mode=mode,
            erplibre_payload_v=2,
        )

    def _member(self, channel, user):
        return channel.channel_member_ids.filtered(
            lambda member: member.partner_id == user.partner_id
        )

    def _v2(self, message, channel_type, mentioned=False, online=False):
        return {
            "v": 2,
            "message_id": message.id,
            "channel_type": channel_type,
            "mentioned": mentioned,
            "browser_online": online,
        }

    @contextmanager
    def _sent_by_device(self):
        """Simule ntfy (200) et rend le dict, rempli au fil des envois, id
        d'appareil → charge JSON en clair (str) passée au chiffrement."""
        sent = {}
        with (
            patch.object(requests.Session, "post", return_value=answer(200)),
            patch(
                f"{APP_PUSH}._encrypt_payload",
                side_effect=lambda content, device: sent.__setitem__(
                    device["id"], content.decode()
                )
                or b"x",
            ),
        ):
            yield sent

    def _flags_of(self, sent, device):
        return json.loads(sent[device.id])["options"]["data"]["erplibre"]

    def _mark(self, login, params):
        self.authenticate(login, login)
        return self.make_jsonrpc_request(
            "/erplibre_mobile_chat/push/device",
            {"endpoint": ENDPOINT, **params},
        )

    def _post(self, thread=None, body="Bonjour", **kwargs):
        thread = thread if thread is not None else self.chat
        return thread.with_user(self.user_a).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            **kwargs,
        )

    def _sent_plaintexts(self, encrypt):
        """Rend, pour chaque envoi de l'expéditeur du module, la charge
        JSON en clair passée au chiffrement (`encrypt`, le simulacre de
        `_encrypt_payload`)."""
        return [json.loads(c.args[0]) for c in encrypt.call_args_list]

    def test_level_selection_ends_with_1_6(self):
        self.authenticate("push_user_b", "push_user_b")
        fields = self.make_jsonrpc_request(
            "/web/dataset/call_kw/mail.message/fields_get",
            {
                "model": "mail.message",
                "method": "fields_get",
                "args": [["erplibre_chat_level"]],
                "kwargs": {"attributes": ["selection"]},
            },
        )
        selection = fields["erplibre_chat_level"]["selection"]
        self.assertEqual(selection[-1], ["1.6", "1.6"])

    def test_route_marks_own_device_only(self):
        device = self._device(self.user_b)
        self.authenticate("push_user_a", "push_user_a")
        result = self.make_jsonrpc_request(
            "/erplibre_mobile_chat/push/device",
            {"endpoint": ENDPOINT, "quiet_while_online": True},
        )
        self.assertEqual(result, {"ok": False})
        device.invalidate_recordset()
        self.assertFalse(device.erplibre_app)
        self.assertEqual(device.erplibre_browser_mode, "ring")
        self.assertFalse(device.erplibre_session_hash)
        self.assertEqual(device.partner_id, self.user_b.partner_id)

    def test_route_stores_session_hash_and_quiet(self):
        device = self._device(self.user_a)
        session = self.authenticate("push_user_a", "push_user_a")
        result = self.make_jsonrpc_request(
            "/erplibre_mobile_chat/push/device",
            {"endpoint": ENDPOINT, "quiet_while_online": True},
        )
        self.assertEqual(result, {"ok": True})
        device.invalidate_recordset()
        self.assertTrue(device.erplibre_app)
        self.assertEqual(device.erplibre_browser_mode, "quiet")
        self.assertEqual(
            device.erplibre_session_hash,
            hashlib.sha256(session.sid.encode()).hexdigest(),
        )
        result = self.make_jsonrpc_request(
            "/erplibre_mobile_chat/push/device", {"endpoint": ENDPOINT}
        )
        self.assertEqual(result, {"ok": True})
        device.invalidate_recordset()
        self.assertTrue(device.erplibre_app)
        self.assertEqual(device.erplibre_browser_mode, "ring")

    def test_register_to_other_partner_clears_marks(self):
        device = self._device(
            self.user_a,
            erplibre_app=True,
            erplibre_browser_mode="wait",
            erplibre_payload_v=2,
            erplibre_session_hash="0" * 64,
        )
        self.env["mail.push.device"].with_user(self.user_a).register_devices(
            endpoint=ENDPOINT,
            keys=device_keys(),
            vapid_public_key=self.vapid_public_key,
        )
        device.invalidate_recordset()
        self.assertTrue(device.erplibre_app)
        self.env["mail.push.device"].with_user(self.user_b).register_devices(
            endpoint=ENDPOINT,
            keys=device_keys(),
            vapid_public_key=self.vapid_public_key,
        )
        device.invalidate_recordset()
        self.assertEqual(device.partner_id, self.user_b.partner_id)
        self.assertFalse(device.erplibre_app)
        self.assertEqual(device.erplibre_browser_mode, "ring")
        self.assertEqual(device.erplibre_payload_v, 1)
        self.assertFalse(device.erplibre_session_hash)

    def test_unmarked_device_takes_odoo_path_unchanged(self):
        device = self._device(self.user_b)
        with (
            patch.object(
                requests.Session, "post", return_value=answer(200)
            ) as post,
            patch.object(
                mail_thread_module,
                "push_to_end_point",
                wraps=push_to_end_point,
            ) as odoo_push,
            self.assertLogs(WEB_PUSH_LOGGER, "WARNING") as logs,
        ):
            message = self._post()
            self.env.cr.postcommit.run()
        odoo_push.assert_called_once()
        kwargs = odoo_push.call_args.kwargs
        stock = self.chat._truncate_payload(
            self.chat._notify_by_web_push_prepare_payload(message)
        )
        self.assertEqual(kwargs["payload"], json.dumps(stock))
        self.assertNotIn("erplibre", kwargs["payload"])
        self.assertEqual(
            kwargs["device"],
            {"id": device.id, "endpoint": ENDPOINT, "keys": device.keys},
        )
        self.assertEqual(post.call_count, 1)
        self.assertIn(
            f"Failed push notification {ENDPOINT} 200", logs.output[0]
        )

    def test_marked_device_skips_odoo_path(self):
        self._app_device(self.user_b)
        with (
            patch.object(
                requests.Session, "post", return_value=answer(201)
            ) as post,
            patch.object(mail_thread_module, "push_to_end_point") as odoo_push,
        ):
            self._post()
            self.env.cr.postcommit.run()
        odoo_push.assert_not_called()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], ENDPOINT)

    def test_marked_payload_has_message_id_and_channel_type(self):
        self._app_device(self.user_b)
        cases = [
            (self.chat, {}, "chat"),
            (self.group, {}, "group"),
            (
                self.channel,
                {"partner_ids": self.user_b.partner_id.ids},
                "channel",
            ),
            (self.record, {}, None),
        ]
        for thread, kwargs, channel_type in cases:
            with (
                self.subTest(channel_type=channel_type),
                patch.object(
                    requests.Session, "post", return_value=answer(200)
                ),
                patch(
                    f"{APP_PUSH}._encrypt_payload", return_value=b"x"
                ) as encrypt,
            ):
                message = self._post(thread, **kwargs)
                self.env.cr.postcommit.run()
                payloads = self._sent_plaintexts(encrypt)
                self.assertEqual(len(payloads), 1)
                data = payloads[0]["options"]["data"]
                self.assertEqual(
                    data["erplibre"],
                    {
                        "v": 1,
                        "message_id": message.id,
                        "channel_type": channel_type,
                    },
                )
                self.assertEqual(data["model"], thread._name)
                self.assertEqual(data["res_id"], thread.id)
                self.assertEqual(payloads[0]["options"]["body"], "Bonjour")

    def test_marked_push_waits_for_commit(self):
        self._app_device(self.user_b)
        with patch.object(
            requests.Session, "post", return_value=answer(200)
        ) as post:
            self._post()
            post.assert_not_called()
            self.env.cr.postcommit.run()
            self.assertEqual(post.call_count, 1)

    def test_marked_200_logs_nothing_with_the_endpoint(self):
        device = self._app_device(self.user_b)
        with (
            patch.object(requests.Session, "post", return_value=answer(200)),
            self.assertNoLogs(WEB_PUSH_LOGGER, "WARNING"),
            self.assertLogs(APP_PUSH, "DEBUG") as logs,
        ):
            self._post()
            self.env.cr.postcommit.run()
        self.assertTrue(logs.records)
        for record in logs.records:
            self.assertNotIn("ntfy.exemple.test", record.getMessage())
            self.assertNotIn("upab12cd34", record.getMessage())
        self.assertIn(str(device.id), logs.records[-1].getMessage())

    def test_marked_410_unlinks_device(self):
        device = self._app_device(self.user_b)
        with patch.object(requests.Session, "post", return_value=answer(410)):
            self._post()
            self.assertTrue(device.exists())
            self.env.cr.postcommit.run()
        self.assertFalse(
            self.env["mail.push.device"]
            .sudo()
            .search([("id", "=", device.id)])
        )

    def test_long_body_still_fits(self):
        self._app_device(self.user_b)
        limit = self.env[
            "mail.thread"
        ]._truncate_payload_get_max_payload_length()
        with (
            patch.object(requests.Session, "post", return_value=answer(200)),
            patch(
                f"{APP_PUSH}._encrypt_payload", return_value=b"x"
            ) as encrypt,
        ):
            message = self._post(body="é" * 4000)
            self.env.cr.postcommit.run()
        content = encrypt.call_args.args[0]
        self.assertLessEqual(len(content), limit)
        payload = json.loads(content)
        self.assertEqual(
            payload["options"]["data"]["erplibre"]["message_id"], message.id
        )
        self.assertTrue(payload["options"]["body"].startswith("é"))

    def test_five_marked_devices_go_through_mail_push(self):
        app_devices = self.env["mail.push.device"]
        for index in range(5):
            app_devices |= self._app_device(self.user_b, f"{ENDPOINT}{index}")
        browser = self._device(self.user_c, "https://push.exemple.test/b1")
        Push = self.env["mail.push"].sudo()
        with (
            patch.object(
                requests.Session, "post", return_value=answer(201)
            ) as post,
            patch.object(mail_thread_module, "push_to_end_point") as odoo_push,
        ):
            message = self._post()
            odoo_push.assert_not_called()
            post.assert_not_called()
        rows = Push.search([])
        self.assertEqual(rows.mail_push_device_id, app_devices)
        self.assertIn(f'"message_id": {message.id}', rows[0].payload)
        Push.create({"mail_push_device_id": browser.id, "payload": "{}"})
        with (
            patch.object(
                requests.Session, "post", return_value=answer(201)
            ) as post,
            patch.object(mail_push_module, "push_to_end_point") as odoo_push,
        ):
            Push._push_notification_to_endpoint()
            odoo_push.assert_called_once()
            self.assertEqual(
                odoo_push.call_args.kwargs["device"]["id"], browser.id
            )
            self.assertFalse(Push.search([]))
            post.assert_not_called()
            self.env.cr.postcommit.run()
        self.assertEqual(
            sorted(c.args[0] for c in post.call_args_list),
            sorted(app_devices.mapped("endpoint")),
        )

    def test_marked_send_waits_two_seconds_at_most(self):
        self._app_device(self.user_b)
        with patch.object(
            requests.Session, "post", return_value=answer(200)
        ) as post:
            self._post()
            self.env.cr.postcommit.run()
        self.assertEqual(post.call_args.kwargs["timeout"], 2)

    def test_cron_batch_full_of_app_rows_leaves_odoo_rows(self):
        app_devices = self.env["mail.push.device"]
        for index in range(2):
            app_devices |= self._app_device(self.user_b, f"{ENDPOINT}{index}")
        browser = self._device(self.user_c, "https://push.exemple.test/b1")
        Push = self.env["mail.push"].sudo()
        Push.create(
            [
                {"mail_push_device_id": device.id, "payload": "{}"}
                for device in app_devices | browser
            ]
        )
        cron = self.env.ref("mail.ir_cron_web_push_notification")
        with (
            patch.object(requests.Session, "post", return_value=answer(201)),
            patch.object(mail_push_module, "push_to_end_point") as odoo_push,
            patch.object(type(cron), "_trigger") as trigger,
        ):
            Push._push_notification_to_endpoint(batch_size=2)
        odoo_push.assert_not_called()
        self.assertEqual(Push.search([]).mail_push_device_id, browser)
        trigger.assert_called()

    def test_cron_odoo_rows_take_what_the_app_rows_leave(self):
        device = self._app_device(self.user_b)
        browsers = self.env["mail.push.device"]
        for index in range(3):
            browsers |= self._device(
                self.user_c, f"https://push.exemple.test/b{index}"
            )
        Push = self.env["mail.push"].sudo()
        Push.create(
            [
                {"mail_push_device_id": d.id, "payload": "{}"}
                for d in device | browsers
            ]
        )
        with (
            patch.object(requests.Session, "post", return_value=answer(201)),
            patch.object(mail_push_module, "push_to_end_point") as odoo_push,
        ):
            Push._push_notification_to_endpoint(batch_size=2)
        self.assertEqual(odoo_push.call_count, 1)
        self.assertEqual(len(Push.search([])), 2)

    def test_marked_500_warns_with_the_device_id_only(self):
        device = self._app_device(self.user_b)
        with (
            patch.object(requests.Session, "post", return_value=answer(500)),
            self.assertLogs(APP_PUSH, "WARNING") as logs,
        ):
            self._post()
            self.env.cr.postcommit.run()
        self.assertEqual(len(logs.records), 1)
        text = logs.records[0].getMessage()
        self.assertIn(str(device.id), text)
        self.assertIn("500", text)
        self.assertNotIn("ntfy.exemple.test", text)
        self.assertNotIn("upab12cd34", text)
        self.assertTrue(device.exists())

    def test_cron_keeps_app_rows_without_vapid_keys(self):
        device = self._app_device(self.user_b)
        Push = self.env["mail.push"].sudo()
        row = Push.create({"mail_push_device_id": device.id, "payload": "{}"})
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.web_push_vapid_private_key", False
        )
        with patch.object(
            requests.Session, "post", return_value=answer(201)
        ) as post:
            Push._push_notification_to_endpoint()
            self.env.cr.postcommit.run()
        post.assert_not_called()
        self.assertTrue(row.exists())

    def test_quiet_device_receives_while_only_the_app_polls(self):
        device = self._device(
            self.user_b, erplibre_app=True, erplibre_browser_mode="quiet"
        )
        # Le bus de l'application tient la présence d'Odoo à jour sans
        # toucher celle des navigateurs.
        self.env["bus.presence"].sudo().create(
            {"user_id": self.user_b.id, "status": "online"}
        )
        self.assertFalse(self.user_b._erplibre_browser_online())
        with patch.object(
            requests.Session, "post", return_value=answer(201)
        ) as post:
            self._post()
            self.env.cr.postcommit.run()
        self.assertEqual(
            [c.args[0] for c in post.call_args_list], [device.endpoint]
        )

    # Module 1.6 : mode de l'appareil et charge v 2

    def test_route_with_browser_mode_sets_mode_and_v2(self):
        device = self._device(self.user_a)
        for mode in ("ring", "wait", "quiet"):
            with self.subTest(mode=mode):
                # `quiet_while_online` contredit le mode : le mode l'emporte.
                result = self._mark(
                    "push_user_a",
                    {
                        "browser_mode": mode,
                        "quiet_while_online": mode != "quiet",
                    },
                )
                self.assertEqual(result, {"ok": True})
                device.invalidate_recordset()
                self.assertTrue(device.erplibre_app)
                self.assertEqual(device.erplibre_browser_mode, mode)
                self.assertEqual(device.erplibre_payload_v, 2)
                self.assertTrue(device.erplibre_session_hash)

    def test_route_without_browser_mode_maps_quiet_and_v1(self):
        device = self._device(
            self.user_a,
            erplibre_app=True,
            erplibre_browser_mode="wait",
            erplibre_payload_v=2,
        )
        for quiet, mode in ((True, "quiet"), (False, "ring")):
            with self.subTest(quiet_while_online=quiet):
                result = self._mark(
                    "push_user_a", {"quiet_while_online": quiet}
                )
                self.assertEqual(result, {"ok": True})
                device.invalidate_recordset()
                self.assertEqual(device.erplibre_browser_mode, mode)
                self.assertEqual(device.erplibre_payload_v, 1)

    def test_route_refuses_an_unknown_mode(self):
        device = self._device(
            self.user_a,
            erplibre_app=True,
            erplibre_browser_mode="wait",
            erplibre_payload_v=2,
            erplibre_session_hash="0" * 64,
        )
        for mode in ("sonner", "", ["ring"]):
            with self.subTest(mode=mode):
                result = self._mark("push_user_a", {"browser_mode": mode})
                self.assertEqual(result, {"ok": False})
                device.invalidate_recordset()
                self.assertEqual(device.erplibre_browser_mode, "wait")
                self.assertEqual(device.erplibre_payload_v, 2)
                self.assertEqual(device.erplibre_session_hash, "0" * 64)

    def test_device_marked_without_browser_mode_gets_v1_payload(self):
        v1 = self._device(self.user_b)
        self.assertEqual(self._mark("push_user_b", {}), {"ok": True})
        v2 = self._v2_device(self.user_b, f"{ENDPOINT}v2")
        limit = self.env[
            "mail.thread"
        ]._truncate_payload_get_max_payload_length()
        with self._sent_by_device() as sent:
            message = self._post(body="é" * 4000)
            self.env.cr.postcommit.run()
        lot2 = self.chat._notify_by_web_push_prepare_payload(message)
        lot2["options"]["data"]["erplibre"] = {
            "v": 1,
            "message_id": message.id,
            "channel_type": "chat",
        }
        self.assertEqual(
            sent[v1.id], json.dumps(self.chat._truncate_payload(lot2))
        )
        self.assertLessEqual(len(sent[v1.id]), limit)
        self.assertLessEqual(len(sent[v2.id]), limit)
        body_v1 = json.loads(sent[v1.id])["options"]["body"]
        body_v2 = json.loads(sent[v2.id])["options"]["body"]
        self.assertLess(len(body_v2), len(body_v1))
        self.assertTrue(body_v1.startswith(body_v2))

    def test_v2_payload_flags_mentioned_per_recipient(self):
        self._member(self.channel, self.user_c).custom_notifications = "all"
        bruno = self._v2_device(self.user_b)
        alice = self._v2_device(self.user_c, f"{ENDPOINT}c")
        with self._sent_by_device() as sent:
            message = self._post(
                self.channel, partner_ids=self.user_b.partner_id.ids
            )
            self.env.cr.postcommit.run()
        self.assertEqual(
            self._flags_of(sent, bruno),
            self._v2(message, "channel", mentioned=True),
        )
        self.assertEqual(
            self._flags_of(sent, alice), self._v2(message, "channel")
        )

    def test_everyone_counts_as_mentioned(self):
        devices = self._v2_device(self.user_b) | self._v2_device(
            self.user_c, f"{ENDPOINT}c"
        )
        with self._sent_by_device() as sent:
            message = self._post(
                self.channel, partner_ids=[], special_mentions=["everyone"]
            )
            self.env.cr.postcommit.run()
        for device in devices:
            self.assertEqual(
                self._flags_of(sent, device),
                self._v2(message, "channel", mentioned=True),
            )

    def test_chat_and_group_payload_not_mentioned_without_mention(self):
        device = self._v2_device(self.user_b)
        for thread, channel_type in (
            (self.chat, "chat"),
            (self.group, "group"),
        ):
            with self.subTest(channel_type=channel_type):
                with self._sent_by_device() as sent:
                    message = self._post(thread)
                    self.env.cr.postcommit.run()
                self.assertEqual(
                    self._flags_of(sent, device),
                    self._v2(message, channel_type),
                )

    def test_record_comment_payload_has_flags(self):
        device = self._v2_device(self.user_b)
        for kwargs, mentioned in (
            ({}, False),
            ({"partner_ids": self.user_b.partner_id.ids}, True),
        ):
            with self.subTest(mentioned=mentioned):
                with self._sent_by_device() as sent:
                    message = self._post(self.record, **kwargs)
                    self.env.cr.postcommit.run()
                self.assertEqual(
                    self._flags_of(sent, device),
                    self._v2(message, None, mentioned=mentioned),
                )

    def test_browser_online_true_for_a_wait_device_with_an_active_browser(
        self,
    ):
        device = self._v2_device(self.user_b, mode="wait")
        write_browser_presence(self.env, self.user_b, 10, 60)
        with self._sent_by_device() as sent:
            message = self._post()
            self.env.cr.postcommit.run()
        self.assertEqual(
            self._flags_of(sent, device),
            self._v2(message, "chat", online=True),
        )

    def test_browser_online_false_after_five_minutes_inactive(self):
        device = self._v2_device(self.user_b, mode="wait")
        write_browser_presence(self.env, self.user_b, 10, 301)
        with self._sent_by_device() as sent:
            message = self._post()
            self.env.cr.postcommit.run()
        self.assertEqual(
            self._flags_of(sent, device), self._v2(message, "chat")
        )

    def test_ring_device_has_browser_online_false_and_no_presence_written(
        self,
    ):
        device = self._v2_device(self.user_b, mode="ring")
        Presence = type(self.env["bus.presence"])
        with (
            patch.object(
                Presence, "_erplibre_update_browser_presence"
            ) as write,
            bus_request(self.env, self.user_b, BROWSER_SID) as env,
        ):
            env["ir.websocket"]._update_bus_presence(0, {})
        write.assert_not_called()
        # Une présence active écrite à la main n'est pas lue non plus.
        write_browser_presence(self.env, self.user_b, 10, 60)
        with self._sent_by_device() as sent:
            message = self._post()
            self.env.cr.postcommit.run()
        self.assertEqual(
            self._flags_of(sent, device), self._v2(message, "chat")
        )

    def test_v2_payload_with_long_body_fits(self):
        self._member(self.channel, self.user_c).custom_notifications = "all"
        both_true = self._v2_device(self.user_b, mode="wait")
        both_false = self._v2_device(self.user_c, f"{ENDPOINT}c")
        write_browser_presence(self.env, self.user_b, 10, 60)
        limit = self.env[
            "mail.thread"
        ]._truncate_payload_get_max_payload_length()
        with self._sent_by_device() as sent:
            message = self._post(
                self.channel,
                body="é" * 4000,
                partner_ids=self.user_b.partner_id.ids,
            )
            self.env.cr.postcommit.run()
        self.assertEqual(
            self._flags_of(sent, both_true),
            self._v2(message, "channel", mentioned=True, online=True),
        )
        self.assertEqual(
            self._flags_of(sent, both_false), self._v2(message, "channel")
        )
        for device in (both_true, both_false):
            content = sent[device.id]
            self.assertLessEqual(len(content.encode()), limit)
            self.assertTrue(
                json.loads(content)["options"]["body"].startswith("é")
            )

    def test_migration_maps_quiet_to_mode(self):
        quiet = self._app_device(self.user_b)
        loud = self._app_device(self.user_c, f"{ENDPOINT}c")
        self.env.flush_all()
        cr = self.env.cr
        # La colonne de 1.5, que le chargement de 1.6 ne crée plus.
        cr.execute(
            "ALTER TABLE mail_push_device"
            " ADD COLUMN erplibre_quiet_while_online boolean"
        )
        cr.execute(
            "UPDATE mail_push_device SET erplibre_browser_mode = 'wait',"
            " erplibre_quiet_while_online = (id = %s)",
            [quiet.id],
        )
        spec = importlib.util.spec_from_file_location(
            "erplibre_mobile_chat_migration_16", file_path(MIGRATION_16)
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(cr, "18.0.1.5.0")
        self.env.invalidate_all()
        self.assertEqual(quiet.erplibre_browser_mode, "quiet")
        self.assertEqual(loud.erplibre_browser_mode, "ring")
        self.assertEqual((quiet | loud).mapped("erplibre_payload_v"), [1, 1])
        self.assertFalse(
            column_exists(
                cr, "mail_push_device", "erplibre_quiet_while_online"
            )
        )
