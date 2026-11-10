# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib
from datetime import datetime, timedelta, timezone

from odoo import Command, fields
from odoo.tests.common import TransactionCase, new_test_user, tagged

FINGERPRINT_A = "a" * 64
FINGERPRINT_B = "b" * 64


@tagged("post_install", "-at_install")
class TestStreamdeckService(TransactionCase):
    """Le service qui inscrit les postes et reçoit leurs remontées.

    Chaque méthode rend `(statut HTTP, corps)` : les tests lisent les deux,
    comme le ferait l'extension. A et B sont deux employés.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["streamdeck.service"]
        cls.Workstation = cls.env["streamdeck.workstation"].with_context(
            active_test=False
        )
        cls.Device = cls.env["streamdeck.device"]
        cls.Event = cls.env["streamdeck.event"]
        cls.user_a = new_test_user(
            cls.env,
            login="zz_sd_svc_a",
            password="zz-sd-svc-a-pw-1",
            name="Employee A",
            groups="base.group_user",
        )
        cls.user_b = new_test_user(
            cls.env,
            login="zz_sd_svc_b",
            name="Employee B",
            groups="base.group_user",
        )
        cls.portal = new_test_user(
            cls.env,
            login="zz_sd_svc_p",
            password="zz-sd-svc-p-pw-1",
            name="Portal P",
            groups="base.group_portal",
        )
        cls._uuid = 0

    # -- helpers ---------------------------------------------------------

    def _enroll(self, user, fingerprint=FINGERPRINT_A, hostname="host-a"):
        code = self.Service.new_pairing_code(user)
        status, body = self.Service.enroll(
            {
                "protocol": "1.0",
                "method": "pairing_code",
                "code": code.code,
                "fingerprint": fingerprint,
                "hostname": hostname,
            }
        )
        self.assertEqual(status, 200, body)
        return body

    @staticmethod
    def _deck(serial, product="0084", path="1-2.3", firmware=None):
        return {
            "serial": serial,
            "usb_product_id": product,
            "usb_path": path,
            "firmware": firmware,
        }

    @staticmethod
    def _state(decks=(), service_state="active", hostname="host-a"):
        return {
            "hostname": hostname,
            "os": {"name": "Debian GNU/Linux", "version": "13"},
            "gnome_shell": "48.4",
            "extension_version": "1.4.0",
            "contract_version": "1.2",
            "erplibre": {"branch": "develop", "commit": "0" * 40},
            "deck_program": "streamdeck_ui",
            "service_state": service_state,
            "decks": list(decks),
        }

    def _event(self, kind, deck=None, at=None, service_state=None):
        type(self)._uuid += 1
        deck = deck or {}
        return {
            "uuid": "00000000-0000-4000-8000-%012d" % self._uuid,
            "kind": kind,
            "at": at or "2026-01-01T10:00:00.000Z",
            "serial": deck.get("serial"),
            "usb_product_id": deck.get("usb_product_id"),
            "usb_path": deck.get("usb_path"),
            "service_state": service_state,
        }

    def _report(self, token, decks=(), events=(), lost=0, **extra):
        payload = {
            "protocol": "1.0",
            "state": self._state(decks),
            "events": list(events),
            "lost_events": lost,
        }
        payload.update(extra)
        return self.Service.report(token, payload)

    def _assert_error(self, result, status, code):
        self.assertEqual(result[0], status, result[1])
        self.assertEqual(result[1].get("error"), code, result[1])
        self.assertEqual(result[1].get("protocol"), "1.0")

    def _counts(self):
        return (
            self.Workstation.search_count([]),
            self.Device.search_count([]),
            self.Event.search_count([]),
        )

    # -- enrollment ------------------------------------------------------

    def test_enroll_by_pairing_code_returns_a_token_and_stores_only_its_hash(
        self,
    ):
        code = self.Service.new_pairing_code(self.user_a)
        self.assertEqual(len(code.code), 8)
        self.assertTrue(
            set(code.code) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
        )
        self.assertEqual(code.user_id, self.user_a)
        self.assertAlmostEqual(
            code.expires_at,
            fields.Datetime.now() + timedelta(minutes=10),
            delta=timedelta(seconds=5),
        )
        status, body = self.Service.enroll(
            {
                "protocol": "1.0",
                "method": "pairing_code",
                "code": code.code,
                "fingerprint": FINGERPRINT_A,
                "hostname": "host-a",
            }
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(set(body), {"protocol", "workstation_id", "token"})
        self.assertEqual(body["protocol"], "1.0")
        token = body["token"]
        self.assertEqual(len(token), 43)
        self.assertRegex(token, r"^[A-Za-z0-9_-]{43}$")
        workstation = self.Workstation.browse(body["workstation_id"])
        self.assertEqual(workstation.user_id, self.user_a)
        self.assertEqual(workstation.name, "host-a")
        self.assertEqual(workstation.fingerprint, FINGERPRINT_A)
        self.assertEqual(
            workstation.token_hash, hashlib.sha256(token.encode()).hexdigest()
        )
        self.assertTrue(workstation.token_created)
        self.assertTrue(code.used)
        for name, field in workstation._fields.items():
            if field.type in ("char", "text"):
                self.assertNotEqual(workstation[name], token, name)

    def test_a_pairing_code_is_typed_without_regard_to_case_or_spaces(self):
        code = self.Service.new_pairing_code(self.user_a).code
        typed = " %s-%s " % (code[:4].lower(), code[4:])
        status, body = self.Service.enroll(
            {
                "protocol": "1.0",
                "method": "pairing_code",
                "code": typed,
                "fingerprint": FINGERPRINT_A,
                "hostname": "host-a",
            }
        )
        self.assertEqual(status, 200, body)

    def test_a_pairing_code_is_single_use_and_expires(self):
        def enroll(code, fingerprint):
            return self.Service.enroll(
                {
                    "protocol": "1.0",
                    "method": "pairing_code",
                    "code": code,
                    "fingerprint": fingerprint,
                    "hostname": "host-a",
                }
            )

        code = self.Service.new_pairing_code(self.user_a)
        self.assertEqual(enroll(code.code, FINGERPRINT_A)[0], 200)
        before = self._counts()
        self._assert_error(
            enroll(code.code, FINGERPRINT_B), 401, "credentials_refused"
        )
        late = self.Service.new_pairing_code(self.user_a)
        late.write(
            {"expires_at": fields.Datetime.now() - timedelta(seconds=1)}
        )
        self._assert_error(
            enroll(late.code, FINGERPRINT_B), 401, "credentials_refused"
        )
        self.assertFalse(late.used)
        self._assert_error(
            enroll("ZZZZZZZZ", FINGERPRINT_B), 401, "credentials_refused"
        )
        self.assertEqual(self._counts(), before)

    def test_enroll_by_api_key(self):
        key = (
            self.env["res.users.apikeys"]
            .with_user(self.user_a)
            .sudo()
            ._generate(None, "inventory", None)
        )
        status, body = self.Service.enroll(
            {
                "protocol": "1.0",
                "method": "api_key",
                "key": key,
                "fingerprint": FINGERPRINT_A,
                "hostname": "host-a",
            }
        )
        self.assertEqual(status, 200, body)
        workstation = self.Workstation.browse(body["workstation_id"])
        self.assertEqual(workstation.user_id, self.user_a)
        self._assert_error(
            self.Service.enroll(
                {
                    "protocol": "1.0",
                    "method": "api_key",
                    "key": "0" * 40,
                    "fingerprint": FINGERPRINT_B,
                    "hostname": "host-a",
                }
            ),
            401,
            "credentials_refused",
        )

    def test_enroll_by_password(self):
        password = "zz-sd-svc-a-pw-1"
        status, body = self.Service.enroll(
            {
                "protocol": "1.0",
                "method": "password",
                "login": "zz_sd_svc_a",
                "password": password,
                "fingerprint": FINGERPRINT_A,
                "hostname": "host-a",
            }
        )
        self.assertEqual(status, 200, body)
        workstation = self.Workstation.browse(body["workstation_id"])
        self.assertEqual(workstation.user_id, self.user_a)
        # Le mot de passe ne sert qu'à l'inscription : aucun champ texte du
        # poste ne le garde, ni ne le contient.
        for name, field in workstation._fields.items():
            if field.type in ("char", "text"):
                value = workstation[name] or ""
                self.assertNotIn(password, value, name)
        for login, pw in (
            ("zz_sd_svc_a", "wrong-password"),
            ("zz_sd_nobody", password),
        ):
            with self.subTest(login=login):
                self._assert_error(
                    self.Service.enroll(
                        {
                            "protocol": "1.0",
                            "method": "password",
                            "login": login,
                            "password": pw,
                            "fingerprint": FINGERPRINT_B,
                            "hostname": "host-a",
                        }
                    ),
                    401,
                    "credentials_refused",
                )

    def test_a_long_password_is_checked_not_refused(self):
        password = "p" * 300
        self.user_b.write({"password": password})
        status, body = self.Service.enroll(
            {
                "protocol": "1.0",
                "method": "password",
                "login": "zz_sd_svc_b",
                "password": password,
                "fingerprint": FINGERPRINT_B,
                "hostname": "host-b",
            }
        )
        self.assertEqual(status, 200, body)

    def test_a_product_id_is_stored_in_lowercase(self):
        token = self._enroll(self.user_a)["token"]
        deck = self._deck("SN-UPPER", "006C")
        self.assertEqual(self._report(token, decks=[deck])[0], 200)
        device = self.Device.search([("key", "=", "SN-UPPER")])
        self.assertEqual(device.usb_product_id, "006c")
        self.assertEqual(device.model_name, "Stream Deck XL")

    def test_an_archived_employee_cannot_enroll_with_a_pairing_code(self):
        code = self.Service.new_pairing_code(self.user_a)
        self.user_a.write({"active": False})
        self._assert_error(
            self.Service.enroll(
                {
                    "protocol": "1.0",
                    "method": "pairing_code",
                    "code": code.code,
                    "fingerprint": FINGERPRINT_A,
                    "hostname": "host-a",
                }
            ),
            403,
            "user_inactive",
        )
        self.assertFalse(
            self.Workstation.search([("user_id", "=", self.user_a.id)])
        )

    def test_a_portal_user_cannot_enroll(self):
        # Un compte portail (un client) n'est pas un utilisateur Stream
        # Deck : ses identifiants valides ne lui ouvrent pas l'inventaire,
        # quelle que soit la méthode.
        code = self.Service.new_pairing_code(self.portal)
        key = (
            self.env["res.users.apikeys"]
            .with_user(self.portal)
            .sudo()
            ._generate(None, "inventory", None)
        )
        payloads = {
            "pairing_code": {"code": code.code},
            "api_key": {"key": key},
            "password": {
                "login": "zz_sd_svc_p",
                "password": "zz-sd-svc-p-pw-1",
            },
        }
        before = self._counts()
        for method, secret in payloads.items():
            with self.subTest(method=method):
                payload = dict(
                    secret,
                    protocol="1.0",
                    method=method,
                    fingerprint=FINGERPRINT_A,
                    hostname="host-p",
                )
                self._assert_error(
                    self.Service.enroll(payload), 403, "user_inactive"
                )
        self.assertFalse(code.used)
        self.assertEqual(self._counts(), before)

    def test_an_employee_turned_portal_user_is_refused(self):
        enrolled = self._enroll(self.user_a)
        token = enrolled["token"]
        workstation = self.Workstation.browse(enrolled["workstation_id"])
        self.user_a.write(
            {
                "groups_id": [
                    Command.set([self.env.ref("base.group_portal").id])
                ]
            }
        )
        before = self._counts()
        self._assert_error(
            self._report(token, decks=[self._deck("SN-PORTAL")]),
            403,
            "user_inactive",
        )
        self._assert_error(
            self.Service.unenroll(token, {"protocol": "1.0"}),
            403,
            "user_inactive",
        )
        self.assertEqual(self._counts(), before)
        self.assertFalse(workstation.last_report)
        self.assertTrue(workstation.token_hash)

    def test_reenrolling_the_same_fingerprint_keeps_the_workstation(self):
        first = self._enroll(self.user_a)
        workstation = self.Workstation.browse(first["workstation_id"])
        workstation.write({"active": False})
        second = self._enroll(self.user_a, hostname="host-a-renamed")
        self.assertEqual(second["workstation_id"], first["workstation_id"])
        self.assertNotEqual(second["token"], first["token"])
        self.assertTrue(workstation.active)
        self.assertEqual(
            workstation.token_hash,
            hashlib.sha256(second["token"].encode()).hexdigest(),
        )
        self._assert_error(self._report(first["token"]), 401, "token_invalid")
        self.assertEqual(self._report(second["token"])[0], 200)
        # Le même poste chez un autre employé est un autre poste.
        other = self._enroll(self.user_b)
        self.assertNotEqual(other["workstation_id"], first["workstation_id"])

    # -- protocol --------------------------------------------------------

    def test_an_unknown_major_is_refused(self):
        token = self._enroll(self.user_a)["token"]
        code = self.Service.new_pairing_code(self.user_a)
        enroll = {
            "protocol": "2.0",
            "method": "pairing_code",
            "code": code.code,
            "fingerprint": FINGERPRINT_B,
            "hostname": "host-a",
        }
        self._assert_error(
            self.Service.enroll(enroll), 400, "protocol_unsupported"
        )
        self.assertFalse(code.used)
        self._assert_error(
            self._report(token, protocol="2.0"), 400, "protocol_unsupported"
        )
        self._assert_error(
            self.Service.unenroll(token, {"protocol": "0.9"}),
            400,
            "protocol_unsupported",
        )
        workstation = self.Workstation.search(
            [("user_id", "=", self.user_a.id)]
        )
        self.assertTrue(workstation.token_hash)
        self.assertFalse(workstation.last_report)

    def test_a_newer_minor_is_accepted(self):
        code = self.Service.new_pairing_code(self.user_a)
        status, body = self.Service.enroll(
            {
                "protocol": "1.7",
                "method": "pairing_code",
                "code": code.code,
                "fingerprint": FINGERPRINT_A,
                "hostname": "host-a",
                "future_key": {"anything": [1, 2]},
            }
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["protocol"], "1.0")
        deck = dict(self._deck("SN-MINOR"), future_deck_key=True)
        event = dict(self._event("plugged", deck), future_event_key="x")
        payload = {
            "protocol": "1.7",
            "state": dict(self._state([deck]), future_state_key=3),
            "events": [event],
            "lost_events": 0,
            "future_key": None,
        }
        status, reply = self.Service.report(body["token"], payload)
        self.assertEqual(status, 200, reply)
        self.assertEqual(reply["accepted"], [event["uuid"]])

    # -- report ----------------------------------------------------------

    def test_a_report_sets_the_inventory(self):
        enrolled = self._enroll(self.user_a)
        token = enrolled["token"]
        workstation = self.Workstation.browse(enrolled["workstation_id"])
        one = self._deck("SN-ONE", "0084", "1-2.3", firmware="1.0.5")
        two = self._deck("SN-TWO", "006c", "1-2.4")
        status, body = self._report(token, decks=[one, two])
        self.assertEqual(status, 200, body)
        self.assertEqual(
            body, {"protocol": "1.0", "accepted": [], "heartbeat_s": 900}
        )
        decks = self.Device.search([("workstation_id", "=", workstation.id)])
        self.assertEqual(sorted(decks.mapped("serial")), ["SN-ONE", "SN-TWO"])
        self.assertTrue(all(decks.mapped("connected")))
        self.assertTrue(all(decks.mapped("connected_since")))
        self.assertTrue(all(decks.mapped("last_seen")))
        deck_one = decks.filtered(lambda d: d.serial == "SN-ONE")
        self.assertEqual(deck_one.key, "SN-ONE")
        self.assertEqual(deck_one.firmware, "1.0.5")
        self.assertEqual(deck_one.model_name, "Stream Deck +")
        self.assertRecordValues(
            workstation,
            [
                {
                    "name": "host-a",
                    "os_name": "Debian GNU/Linux",
                    "os_version": "13",
                    "gnome_shell": "48.4",
                    "extension_version": "1.4.0",
                    "contract_version": "1.2",
                    "erplibre_branch": "develop",
                    "erplibre_commit": "0" * 40,
                    "deck_program": "streamdeck_ui",
                    "service_state": "active",
                }
            ],
        )
        self.assertTrue(workstation.last_report)
        self.assertTrue(workstation.token_last_used)
        # Un deck resté branché garde l'heure de son branchement.
        since = datetime(2026, 1, 1, 8, 0, 0)
        deck_one.write({"connected_since": since})
        # Remontée suivante : un seul deck, sans firmware lisible, et le
        # checkout ERPLibre disparu.
        payload = {
            "protocol": "1.0",
            "state": dict(
                self._state([dict(one, firmware=None)], "failed"),
                erplibre=None,
            ),
            "events": [],
            "lost_events": 0,
        }
        self.assertEqual(self.Service.report(token, payload)[0], 200)
        deck_two = decks - deck_one
        self.assertFalse(deck_two.connected)
        self.assertFalse(deck_two.connected_since)
        self.assertEqual(deck_two.workstation_id, workstation)
        self.assertTrue(deck_one.connected)
        self.assertEqual(deck_one.connected_since, since)
        self.assertEqual(deck_one.firmware, "1.0.5")
        self.assertEqual(workstation.service_state, "failed")
        self.assertFalse(workstation.erplibre_branch)
        self.assertFalse(workstation.erplibre_commit)

    def test_a_report_never_renames_the_workstation(self):
        enrolled = self._enroll(self.user_a)
        workstation = self.Workstation.browse(enrolled["workstation_id"])
        workstation.with_user(self.user_a).write({"name": "my desk"})
        payload = {
            "protocol": "1.0",
            "state": self._state(hostname="host-a"),
            "events": [],
            "lost_events": 0,
        }
        self.assertEqual(
            self.Service.report(enrolled["token"], payload)[0], 200
        )
        self.assertEqual(workstation.name, "my desk")

    def test_a_replayed_report_creates_no_duplicate(self):
        token = self._enroll(self.user_a)["token"]
        deck = self._deck("SN-REPLAY")
        events = [
            self._event("plugged", deck),
            self._event("service_changed", service_state="failed"),
        ]
        uuids = [e["uuid"] for e in events]
        first = self._report(token, decks=[deck], events=events)
        self.assertEqual(first[0], 200, first[1])
        counts = self._counts()
        second = self._report(token, decks=[deck], events=events)
        self.assertEqual(second[0], 200, second[1])
        self.assertEqual(first[1]["accepted"], uuids)
        self.assertEqual(second[1]["accepted"], uuids)
        self.assertEqual(self._counts(), counts)
        self.assertEqual(self.Event.search_count([("uuid", "in", uuids)]), 2)
        # Un événement répété dans la même remontée compte une fois.
        again = self._event("unplugged", deck)
        third = self._report(token, events=[again, again])
        self.assertEqual(third[1]["accepted"], [again["uuid"]])
        self.assertEqual(
            self.Event.search_count([("uuid", "=", again["uuid"])]), 1
        )

    def test_events_keep_their_time_deck_and_snapshot(self):
        enrolled = self._enroll(self.user_a)
        workstation = self.Workstation.browse(enrolled["workstation_id"])
        deck = self._deck("SN-EVT")
        plugged = self._event("plugged", deck, at="2026-01-01T10:00:00.250Z")
        service = self._event(
            "service_changed",
            at="2026-01-01T12:30:00+02:00",
            service_state="failed",
        )
        status, _body = self._report(
            enrolled["token"], decks=[deck], events=[plugged, service]
        )
        self.assertEqual(status, 200)
        stored = self.Event.search([("workstation_id", "=", workstation.id)])
        by_kind = {e.kind: e for e in stored}
        self.assertEqual(by_kind["plugged"].at, datetime(2026, 1, 1, 10, 0, 0))
        self.assertEqual(by_kind["plugged"].device_id.serial, "SN-EVT")
        self.assertEqual(by_kind["plugged"].workstation_name, "host-a")
        self.assertEqual(by_kind["plugged"].employee_name, "Employee A")
        self.assertTrue(by_kind["plugged"].received_at)
        self.assertEqual(
            by_kind["service_changed"].at, datetime(2026, 1, 1, 10, 30, 0)
        )
        self.assertFalse(by_kind["service_changed"].device_id)
        self.assertEqual(by_kind["service_changed"].service_state, "failed")

    def test_an_event_of_a_deck_gone_before_the_report_creates_the_deck(self):
        # Branché puis débranché hors ligne : l'état ne porte plus le deck,
        # ses deux événements le créent, débranché, sur ce poste.
        enrolled = self._enroll(self.user_a)
        deck = self._deck("SN-GONE")
        events = [self._event("plugged", deck), self._event("unplugged", deck)]
        self.assertEqual(
            self._report(enrolled["token"], events=events)[0], 200
        )
        device = self.Device.search([("key", "=", "SN-GONE")])
        self.assertEqual(len(device), 1)
        self.assertFalse(device.connected)
        self.assertEqual(device.workstation_id.id, enrolled["workstation_id"])
        self.assertEqual(len(device.event_ids), 2)

    def test_a_deck_moves_to_the_reporting_workstation(self):
        enrolled_a = self._enroll(self.user_a, FINGERPRINT_A, "host-a")
        enrolled_b = self._enroll(self.user_b, FINGERPRINT_B, "host-b")
        deck = self._deck("SN-MOVE")
        at_a = self._event("plugged", deck)
        self._report(enrolled_a["token"], decks=[deck], events=[at_a])
        since_a = datetime(2026, 1, 1, 8, 0, 0)
        self.Device.search([("key", "=", "SN-MOVE")]).write(
            {"connected_since": since_a}
        )
        at_b = self._event("plugged", dict(deck, usb_path="3-1"))
        self._report(
            enrolled_b["token"],
            decks=[dict(deck, usb_path="3-1")],
            events=[at_b],
        )
        device = self.Device.search([("serial", "=", "SN-MOVE")])
        self.assertEqual(len(device), 1)
        self.assertEqual(
            device.workstation_id.id, enrolled_b["workstation_id"]
        )
        self.assertTrue(device.connected)
        self.assertGreater(device.connected_since, since_a)
        by_uuid = {e.uuid: e for e in device.event_ids}
        self.assertEqual(
            by_uuid[at_a["uuid"]].workstation_id.id,
            enrolled_a["workstation_id"],
        )
        self.assertEqual(by_uuid[at_a["uuid"]].employee_name, "Employee A")
        self.assertEqual(
            by_uuid[at_b["uuid"]].workstation_id.id,
            enrolled_b["workstation_id"],
        )
        self.assertEqual(by_uuid[at_b["uuid"]].employee_name, "Employee B")
        # A ne voit plus le deck dans son état : il reste chez B, branché.
        self._report(enrolled_a["token"], decks=[])
        self.assertEqual(
            device.workstation_id.id, enrolled_b["workstation_id"]
        )
        self.assertTrue(device.connected)

    def test_a_deck_without_serial_stays_with_its_workstation(self):
        enrolled_a = self._enroll(self.user_a, FINGERPRINT_A, "host-a")
        enrolled_b = self._enroll(self.user_b, FINGERPRINT_B, "host-b")
        deck = self._deck(None, "0063", "1-4")
        for enrolled in (enrolled_a, enrolled_b):
            status, body = self._report(
                enrolled["token"],
                decks=[deck],
                events=[self._event("plugged", deck)],
            )
            self.assertEqual(status, 200, body)
        devices = self.Device.search([("usb_product_id", "=", "0063")])
        self.assertEqual(len(devices), 2)
        self.assertEqual(
            sorted(devices.mapped("key")),
            sorted(
                "nosn:%d:0063:1-4" % e["workstation_id"]
                for e in (enrolled_a, enrolled_b)
            ),
        )
        for device in devices:
            self.assertFalse(device.serial)
            self.assertEqual(
                device.event_ids.workstation_id, device.workstation_id
            )

    def test_an_event_from_the_future_takes_the_reception_time(self):
        token = self._enroll(self.user_a)["token"]
        now = datetime.now(timezone.utc)
        late = self._event(
            "plugged",
            self._deck("SN-FUTURE"),
            at=(now + timedelta(days=1)).isoformat(),
        )
        close = self._event(
            "unplugged",
            self._deck("SN-FUTURE"),
            at=(now + timedelta(minutes=4)).isoformat(),
        )
        self.assertEqual(self._report(token, events=[late, close])[0], 200)
        stored = self.Event.search([("uuid", "=", late["uuid"])])
        self.assertEqual(stored.at, stored.received_at)
        within = self.Event.search([("uuid", "=", close["uuid"])])
        self.assertGreater(within.at, within.received_at)

    def test_a_revoked_token_or_archived_user_is_refused(self):
        enrolled = self._enroll(self.user_a)
        token = enrolled["token"]
        workstation = self.Workstation.browse(enrolled["workstation_id"])
        self.assertEqual(self._report(token)[0], 200)
        self._assert_error(self._report("not-a-token"), 401, "token_invalid")
        self._assert_error(self._report(""), 401, "token_invalid")
        self._assert_error(self._report(None), 401, "token_invalid")
        # Un employé désactivé sans passer par l'ORM garde le jeton de son
        # poste : le service vérifie l'employé lui-même.
        self.env.cr.execute(
            "UPDATE res_users SET active = false WHERE id = %s",
            (self.user_a.id,),
        )
        self.env.invalidate_all()
        self._assert_error(self._report(token), 403, "user_inactive")
        self._assert_error(
            self.Service.unenroll(token, {"protocol": "1.0"}),
            403,
            "user_inactive",
        )
        self.env.cr.execute(
            "UPDATE res_users SET active = true WHERE id = %s",
            (self.user_a.id,),
        )
        self.env.invalidate_all()
        # Un poste archivé sans passer par l'ORM garde aussi son empreinte
        # de jeton : le service le refuse quand même.
        self.env.cr.execute(
            "UPDATE streamdeck_workstation SET active = false WHERE id = %s",
            (workstation.id,),
        )
        self.env.invalidate_all()
        self.assertTrue(workstation.token_hash)
        self._assert_error(self._report(token), 401, "token_invalid")
        self.env.cr.execute(
            "UPDATE streamdeck_workstation SET active = true WHERE id = %s",
            (workstation.id,),
        )
        self.env.invalidate_all()
        self.assertEqual(self._report(token)[0], 200)
        workstation.action_revoke_token()
        self._assert_error(self._report(token), 401, "token_invalid")
        # Archivé par l'ORM, l'employé perd aussi ses jetons.
        token = self._enroll(self.user_a)["token"]
        self.user_a.write({"active": False})
        self._assert_error(self._report(token), 401, "token_invalid")

    def test_unenroll_revokes_the_token(self):
        enrolled = self._enroll(self.user_a)
        token = enrolled["token"]
        status, body = self.Service.unenroll(token, {"protocol": "1.0"})
        self.assertEqual((status, body), (200, {"protocol": "1.0"}))
        workstation = self.Workstation.browse(enrolled["workstation_id"])
        self.assertFalse(workstation.token_hash)
        self.assertTrue(workstation.active)
        self._assert_error(self._report(token), 401, "token_invalid")
        self._assert_error(
            self.Service.unenroll(token, {"protocol": "1.0"}),
            401,
            "token_invalid",
        )

    def test_lost_events_are_logged_on_the_workstation(self):
        enrolled = self._enroll(self.user_a)
        token = enrolled["token"]
        workstation = self.Workstation.browse(enrolled["workstation_id"])
        self.assertEqual(workstation.lost_events_total, 0)
        largest = 2**31 - 1  # le plus grand entier de la colonne
        for lost, expected in (
            (3, 3),
            (3, 3),
            (2, 3),
            (5, 5),
            (0, 5),
            (largest, largest),
        ):
            with self.subTest(lost=lost):
                self.assertEqual(self._report(token, lost=lost)[0], 200)
                self.assertEqual(workstation.lost_events_total, expected)

    def test_bad_requests_are_400(self):
        enrolled = self._enroll(self.user_a)
        token = enrolled["token"]
        workstation = self.Workstation.browse(enrolled["workstation_id"])
        code = self.Service.new_pairing_code(self.user_b)
        good_enroll = {
            "protocol": "1.0",
            "method": "pairing_code",
            "code": code.code,
            "fingerprint": FINGERPRINT_B,
            "hostname": "host-b",
        }
        enroll_cases = {
            "not a dict": ["protocol", "1.0"],
            "no protocol": {
                k: v for k, v in good_enroll.items() if k != "protocol"
            },
            "protocol not text": dict(good_enroll, protocol=1.0),
            "protocol malformed": dict(good_enroll, protocol="1"),
            "no fingerprint": {
                k: v for k, v in good_enroll.items() if k != "fingerprint"
            },
            "fingerprint upper": dict(good_enroll, fingerprint="B" * 64),
            "fingerprint short": dict(good_enroll, fingerprint="b" * 63),
            "fingerprint newline": dict(
                good_enroll, fingerprint="b" * 64 + "\n"
            ),
            "protocol newline": dict(good_enroll, protocol="1.0\n"),
            "hostname empty": dict(good_enroll, hostname=""),
            "hostname not text": dict(good_enroll, hostname=7),
            "method unknown": dict(good_enroll, method="token"),
            "code missing": {
                k: v for k, v in good_enroll.items() if k != "code"
            },
            "code not text": dict(good_enroll, code=12345678),
            "key missing": dict(good_enroll, method="api_key"),
            "password missing": dict(
                good_enroll, method="password", login="zz_sd_svc_b"
            ),
            # PostgreSQL ne stocke ni le caractère NUL ni une moitié de
            # paire de substitution : le texte est refusé avant la base.
            "hostname with NUL": dict(good_enroll, hostname="a\x00b"),
            "hostname not UTF-8": dict(good_enroll, hostname="a\ud800b"),
            "code with NUL": dict(good_enroll, code="ABCD\x00EFG"),
            "key with NUL": dict(
                good_enroll, method="api_key", key="\x00" * 40
            ),
            "login with NUL": dict(
                good_enroll,
                method="password",
                login="zz_sd\x00svc_b",
                password="x",
            ),
        }
        for name, payload in enroll_cases.items():
            with self.subTest(route="enroll", case=name):
                self._assert_error(
                    self.Service.enroll(payload), 400, "bad_request"
                )
        self.assertFalse(code.used)

        good = {
            "protocol": "1.0",
            "state": self._state([self._deck("SN-BAD")]),
            "events": [self._event("plugged", self._deck("SN-BAD"))],
            "lost_events": 1,
        }
        state = good["state"]
        event = good["events"][0]
        report_cases = {
            "not a dict": [],
            "no state": {k: v for k, v in good.items() if k != "state"},
            "state not a dict": dict(good, state=[]),
            "events not a list": dict(good, events={"0": event}),
            "events missing": {k: v for k, v in good.items() if k != "events"},
            "event not a dict": dict(good, events=["x"]),
            "event kind unknown": dict(good, events=[dict(event, kind="x")]),
            "event uuid missing": dict(good, events=[dict(event, uuid=None)]),
            "event uuid empty": dict(good, events=[dict(event, uuid="")]),
            "event at not a date": dict(
                good, events=[dict(event, at="yesterday")]
            ),
            "event at not text": dict(good, events=[dict(event, at=12)]),
            "event without deck": dict(
                good,
                events=[
                    dict(
                        event, serial=None, usb_product_id=None, usb_path=None
                    )
                ],
            ),
            "service event state unknown": dict(
                good,
                events=[
                    self._event("service_changed", service_state="sleeping")
                ],
            ),
            "lost not an int": dict(good, lost_events="3"),
            "lost a bool": dict(good, lost_events=True),
            "lost negative": dict(good, lost_events=-1),
            "lost beyond the column": dict(good, lost_events=2**31),
            "lost missing": {
                k: v for k, v in good.items() if k != "lost_events"
            },
            "decks not a list": dict(good, state=dict(state, decks={"a": 1})),
            "deck not a dict": dict(good, state=dict(state, decks=["SN"])),
            "deck serial not text": dict(
                good, state=dict(state, decks=[self._deck(42)])
            ),
            "deck without identity": dict(
                good, state=dict(state, decks=[self._deck(None, None, None)])
            ),
            "service state unknown": dict(
                good, state=dict(state, service_state="running")
            ),
            "os not a dict": dict(good, state=dict(state, os="Debian")),
            "erplibre not a dict": dict(
                good, state=dict(state, erplibre="develop")
            ),
            "gnome_shell not text": dict(
                good, state=dict(state, gnome_shell=48)
            ),
            "text too long": dict(
                good, state=dict(state, deck_program="x" * 1000)
            ),
            "text with NUL": dict(
                good, state=dict(state, gnome_shell="4\x008")
            ),
            "text not UTF-8": dict(
                good, state=dict(state, deck_program="\udcff")
            ),
            "deck serial with NUL": dict(
                good, state=dict(state, decks=[self._deck("SN\x00")])
            ),
            "event uuid with NUL": dict(
                good, events=[dict(event, uuid="u\x00u")]
            ),
            "deck product not hex": dict(
                good, state=dict(state, decks=[self._deck("SN", "84zz")])
            ),
            "deck product too long": dict(
                good, state=dict(state, decks=[self._deck("SN", "00840")])
            ),
            "event product too long": dict(
                good, events=[dict(event, usb_product_id="00840")]
            ),
            "event at out of range": dict(
                good, events=[dict(event, at="0001-01-01T00:00:00+01:00")]
            ),
        }
        before = self._counts()
        for name, payload in report_cases.items():
            with self.subTest(route="report", case=name):
                self._assert_error(
                    self.Service.report(token, payload), 400, "bad_request"
                )
        self.assertEqual(self._counts(), before)
        self.assertFalse(workstation.last_report)
        self.assertFalse(workstation.token_last_used)
        self.assertEqual(workstation.lost_events_total, 0)
        self._assert_error(
            self.Service.unenroll(token, {}), 400, "bad_request"
        )
        self._assert_error(
            self.Service.unenroll(token, "1.0"), 400, "bad_request"
        )
        self.assertTrue(workstation.token_hash)
        self.assertEqual(self.Service.report(token, good)[0], 200)
