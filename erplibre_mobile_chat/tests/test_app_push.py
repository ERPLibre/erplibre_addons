# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Appareils de l'application : marque par la route, charge portant
l'identifiant du message et le type du canal, envoi après validation par
l'expéditeur du module ; tout autre appareil suit le code d'Odoo."""

import base64
import hashlib
import json
import os
from unittest.mock import Mock, patch

import requests
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from odoo.addons.mail.models import mail_push as mail_push_module
from odoo.addons.mail.models import mail_thread as mail_thread_module
from odoo.addons.mail.tools.web_push import push_to_end_point
from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase

APP_PUSH = "odoo.addons.erplibre_mobile_chat.tools.app_push"
WEB_PUSH_LOGGER = "odoo.addons.mail.tools.web_push"
ENDPOINT = "https://ntfy.exemple.test/upab12cd34"


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

    def _app_device(self, user, endpoint=ENDPOINT):
        return self._device(user, endpoint, erplibre_app=True)

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

    def test_level_selection_ends_with_1_5(self):
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
        self.assertEqual(selection[-1], ["1.5", "1.5"])

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
        self.assertFalse(device.erplibre_quiet_while_online)
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
        self.assertTrue(device.erplibre_quiet_while_online)
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
        self.assertFalse(device.erplibre_quiet_while_online)

    def test_register_to_other_partner_clears_marks(self):
        device = self._device(
            self.user_a,
            erplibre_app=True,
            erplibre_quiet_while_online=True,
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
        self.assertFalse(device.erplibre_quiet_while_online)
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
            self.user_b, erplibre_app=True, erplibre_quiet_while_online=True
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
