# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Identifiants TURN temporaires rendus par `mail.ice.server`."""

import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.mail.tools.discuss import Store

NOW = 1893456000
EXPIRY = NOW + 24 * 3600
SECRET = "s3cret"
URLS = [
    "stun:turn.exemple.test:3478",
    "turn:turn.exemple.test:3478?transport=udp",
    "turn:turn.exemple.test:3478?transport=tcp",
    "turns:turn.exemple.test:5349?transport=tcp",
]
MODULE = "odoo.addons.erplibre_turn.models.mail_ice_server"
TWILIO = "odoo.addons.mail.models.mail_ice_server.requests.post"


def expected_credential(username, secret=SECRET):
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


@tagged("post_install", "-at_install")
class TestErplibreTurn(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp = cls.env["ir.config_parameter"].sudo()
        cls.Ice = cls.env["mail.ice.server"]
        cls.Ice.sudo().search([]).unlink()
        cls.user = new_test_user(
            cls.env, login="turn_employee", groups="base.group_user"
        )

    def configure(self, secret=SECRET, urls=URLS, ttl="24"):
        self.icp.set_param("erplibre_turn.secret", secret)
        self.icp.set_param("erplibre_turn.urls", "\n".join(urls))
        self.icp.set_param("erplibre_turn.ttl_hours", ttl)

    def ice_servers(self, user=None):
        clock = MagicMock()
        clock.time.return_value = NOW + 0.75
        env = self.env(user=user or self.user)
        with patch(MODULE + ".time", clock):
            return env["mail.ice.server"]._get_ice_servers()

    def hand_rows(self, count):
        return self.Ice.sudo().create(
            [
                {
                    "server_type": "turn",
                    "uri": f"relais{i}.exemple.test:3478",
                    "username": "alice",
                    "credential": "mot-de-passe",
                }
                for i in range(count)
            ]
        )

    def test_one_entry_per_url_signed_with_the_secret(self):
        self.configure()
        servers = self.ice_servers()
        username = f"{EXPIRY}:odoo-u{self.user.id}"
        self.assertEqual([s["urls"] for s in servers], URLS)
        for server in servers[1:]:
            self.assertEqual(server["username"], username)
            self.assertEqual(server["credential"], expected_credential(username))

    def test_stun_entry_carries_no_credential(self):
        self.configure()
        stun = self.ice_servers()[0]
        self.assertEqual(stun, {"urls": URLS[0]})

    def test_username_never_carries_the_login(self):
        self.configure()
        for server in self.ice_servers()[1:]:
            self.assertNotIn(self.user.login, server["username"])

    def test_public_user_is_a_guest(self):
        self.configure()
        public = self.env.ref("base.public_user")
        servers = self.ice_servers(user=public)
        self.assertEqual(servers[1]["username"], f"{EXPIRY}:odoo-guest")

    def test_lifetime_follows_the_parameter(self):
        self.configure(ttl="2")
        username = self.ice_servers()[1]["username"]
        self.assertEqual(username, f"{NOW + 7200}:odoo-u{self.user.id}")

    def test_lifetime_below_one_hour_or_unreadable_is_bounded(self):
        self.configure(ttl="0")
        zero = self.ice_servers()[1]["username"]
        self.assertTrue(zero.startswith(f"{NOW + 3600}:"))
        self.configure(ttl="abc")
        bad = self.ice_servers()[1]["username"]
        self.assertTrue(bad.startswith(f"{EXPIRY}:"))

    def test_missing_lifetime_defaults_to_one_day(self):
        self.configure()
        self.icp.set_param("erplibre_turn.ttl_hours", False)
        username = self.ice_servers()[1]["username"]
        self.assertTrue(username.startswith(f"{EXPIRY}:"))

    def test_empty_secret_returns_what_mail_returns(self):
        self.configure(secret="")
        self.assertEqual(self.ice_servers(), [])
        rows = self.hand_rows(2)
        self.assertEqual(self.ice_servers(), rows._get_local_ice_servers())

    def test_empty_urls_return_what_mail_returns(self):
        self.configure(urls=[])
        self.assertEqual(self.ice_servers(), [])

    def test_twilio_enabled_takes_precedence(self):
        self.configure()
        self.icp.set_param("mail.use_twilio_rtc_servers", True)
        self.icp.set_param("mail.twilio_account_sid", "ACexemple")
        self.icp.set_param("mail.twilio_account_token", "jeton")
        twilio = [{"urls": "turn:global.exemple.test:3478"}]
        response = MagicMock(ok=True)
        response.json.return_value = {"ice_servers": twilio}
        with patch(TWILIO, return_value=response) as post:
            self.assertEqual(self.ice_servers(), twilio)
        post.assert_called_once()

    def test_twilio_enabled_without_answer_leaves_mail_fallback(self):
        self.configure()
        self.icp.set_param("mail.use_twilio_rtc_servers", True)
        rows = self.hand_rows(1)
        self.assertEqual(self.ice_servers(), rows._get_local_ice_servers())

    def test_hand_rows_are_appended_up_to_five(self):
        self.configure(urls=URLS[:3])
        rows = self.hand_rows(2)
        servers = self.ice_servers()
        self.assertEqual(len(servers), 5)
        self.assertEqual(servers[3:], rows._get_local_ice_servers())

    def test_hand_rows_past_five_are_dropped_with_a_warning(self):
        self.configure()
        self.hand_rows(2)
        with self.assertLogs(MODULE, level="WARNING") as logs:
            servers = self.ice_servers()
        self.assertEqual(len(servers), 5)
        self.assertEqual([s["urls"] for s in servers[:4]], URLS)
        self.assertEqual(servers[4]["urls"], "turn:relais0.exemple.test:3478")
        self.assertIn("1 mail.ice.server row(s) dropped", logs.output[0])

    def test_module_list_past_five_is_kept_with_a_warning(self):
        urls = URLS + ["turn:autre.exemple.test:3478", "stun:autre.test"]
        self.configure(urls=urls)
        with self.assertLogs(MODULE, level="WARNING"):
            servers = self.ice_servers()
        self.assertEqual([s["urls"] for s in servers], urls)

    def test_a_module_list_past_five_leaves_no_room_for_hand_rows(self):
        urls = URLS + ["turn:autre.exemple.test:3478", "stun:autre.test"]
        self.configure(urls=urls)
        self.hand_rows(2)
        with self.assertLogs(MODULE, level="WARNING") as logs:
            servers = self.ice_servers()
        self.assertEqual([s["urls"] for s in servers], urls)
        self.assertIn("2 mail.ice.server row(s) dropped", logs.output[-1])

    def test_the_dropped_count_covers_rows_past_the_mail_limit(self):
        # mail ne lit que cinq lignes ; le compte des lignes écartées porte
        # sur toutes.
        self.configure()
        self.hand_rows(7)
        with self.assertLogs(MODULE, level="WARNING") as logs:
            servers = self.ice_servers()
        self.assertEqual(len(servers), 5)
        self.assertIn("6 mail.ice.server row(s) dropped", logs.output[0])

    def test_blank_lines_in_urls_are_ignored(self):
        self.configure(urls=["", URLS[1], "   ", URLS[2], ""])
        servers = self.ice_servers()
        self.assertEqual([s["urls"] for s in servers], URLS[1:3])

    def test_join_call_hands_the_caller_its_credentials(self):
        self.configure()
        channel = self.env["discuss.channel"].create(
            {
                "name": "appel",
                "channel_type": "group",
                "channel_member_ids": [(0, 0, {"partner_id": self.user.partner_id.id})],
            }
        )
        member = channel.channel_member_ids.filtered(
            lambda m: m.partner_id == self.user.partner_id
        )
        store = Store()
        clock = MagicMock()
        clock.time.return_value = NOW
        with patch(MODULE + ".time", clock):
            member.with_user(self.user).sudo()._rtc_join_call(store)
        ice = store.get_result()["Rtc"]["iceServers"]
        self.assertEqual(ice[1]["username"], f"{EXPIRY}:odoo-u{self.user.id}")

    def test_settings_field_writes_the_parameter(self):
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.erplibre_turn_ttl_hours, 24)
        settings.erplibre_turn_ttl_hours = 12
        settings.execute()
        self.assertEqual(self.icp.get_param("erplibre_turn.ttl_hours"), "12")
