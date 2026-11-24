# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Sounds and notifications of a member (T-30, LU-F-090, LU-F-092): their
settings, and the web push of a reflection that follows them.
"""

import json
from unittest.mock import patch

from odoo.addons.mail.models import mail_thread

from .common import LinkupRefletCase


class TestLinkupNotifications(LinkupRefletCase):
    def _settings(self, user):
        return self.env["res.users.settings"]._find_or_create_for_user(user)

    def _push_data(self, *users):
        return [
            {"id": user.partner_id.id, "notif": "web_push"} for user in users
        ]

    def test_defaults_and_member_write(self):
        """The sounds of sending and receiving and every notification are
        on, the reward sounds off (LU-F-090 RM3, LU-F-092 RM2); a member
        writes their own settings, which reach their client."""
        settings = self._settings(self.france)
        self.assertTrue(settings.linkup_sound_enabled)
        self.assertFalse(settings.linkup_reward_sounds_enabled)
        self.assertTrue(settings.linkup_notify_reflet_received)
        self.assertTrue(settings.linkup_notify_confirmed)
        self.assertTrue(settings.linkup_notify_highlight)
        self.assertFalse(settings.linkup_notify_discreet)
        result = settings.with_user(self.france).set_res_users_settings(
            {"linkup_sound_enabled": False}
        )
        self.assertIs(result["linkup_sound_enabled"], False)
        self.assertIn(
            "linkup_notify_highlight", settings._res_users_settings_format()
        )

    def test_web_push_of_a_reflection(self):
        """The web push of a carrier leaves out the members who turned the
        notification of a received reflection off; another message keeps
        all its recipients (LU-F-092 CA2)."""
        reflet = self._sent()
        carrier = reflet.message_id
        chat = reflet.channel_id
        data = self._push_data(self.france, self.jacques)
        self.assertEqual(chat._linkup_push_recipients(carrier, data), data)
        self._settings(self.france).linkup_notify_reflet_received = False
        self.assertEqual(
            chat._linkup_push_recipients(carrier, data),
            self._push_data(self.jacques),
        )
        other = self.workshop.with_user(self.sam).message_post(
            body="Bonjour", message_type="comment"
        )
        self.assertEqual(
            self.workshop._linkup_push_recipients(other, data), data
        )

    def _push_payloads(self, author, recipient):
        """Send a reflection of ``author`` to ``recipient``, who has a
        device for the web push; return the payloads pushed."""
        self.env["mail.push.device"].get_web_push_vapid_public_key()
        self.env["mail.push.device"].sudo().create(
            {
                "endpoint": f"https://push.example.com/linkup/{recipient.id}",
                "expiration_time": None,
                "keys": json.dumps(
                    {
                        "p256dh": "BGbhnoP_91U7oR59BaaSx0JnDv2oEooYnJRV2AbY5T"
                        "BeKGCRCf0HcIJ9bOKchUCDH4cHYWo9SYDz3U-8vSxPL_A",
                        "auth": "DJFdtAgZwrT6yYkUMgUqow",
                    }
                ),
                "partner_id": recipient.partner_id.id,
            }
        )
        with patch.object(mail_thread, "push_to_end_point") as push:
            self._sent(author=author, recipient=recipient)
        return [json.loads(call.kwargs["payload"]) for call in push.mock_calls]

    def test_web_push_discreet(self):
        """With discreet notifications, the web push of a reflection names
        nobody and reads "New LinkUp event" in the language of the
        recipient (LU-F-092 RM4); otherwise it names the author."""
        payloads = self._push_payloads(self.sam, self.france)
        self.assertEqual(len(payloads), 1)
        self.assertIn("Sam", payloads[0]["title"])
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"].search(
            [("name", "=", "mail_linkup_reflet")]
        )._update_translations(["fr_CA"])
        self.jacques.lang = "fr_CA"
        self._settings(self.jacques).linkup_notify_discreet = True
        payloads = self._push_payloads(self.sam, self.jacques)
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload["title"], "LinkUp")
        self.assertEqual(payload["options"]["body"], "Nouvel événement LinkUp")
        self.assertNotIn("Sam", json.dumps(payload))
