# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import uuid
from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"

T0 = datetime(2026, 4, 1, 9, 0, 0)


@tagged("post_install", "-at_install")
class TestStreamdeckMonitorEvents(TransactionCase):
    """Les événements qu'Odoo écrit seul pour la surveillance, et ce que
    la remontée tient à jour pour elle.

    `silent` et `heard_again` sont des sortes du serveur, comme `moved` :
    aucun poste ne les envoie. La remontée qui suit un silence efface
    `silent_since` et écrit `heard_again` ; `service_state_since` date
    l'état du service tel que le poste l'a remonté la première fois. Le
    cron qui pose `silent_since` vient au-delà : les tests le posent ici
    comme lui, par `_server_event` et une écriture en superutilisateur.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["streamdeck.service"]
        cls.Workstation = cls.env["streamdeck.workstation"]
        cls.Event = cls.env["streamdeck.event"]
        cls.user_a = new_test_user(
            cls.env,
            login="zz_sd_mon_a",
            name="Employee A",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_mon_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        code = cls.Service.new_pairing_code(cls.user_a)
        status, body = cls.Service.enroll(
            {
                "protocol": "1.0",
                "method": "pairing_code",
                "code": code.code,
                "fingerprint": "a" * 64,
                "hostname": "host-a",
            }
        )
        assert status == 200, body
        cls.token = body["token"]
        cls.workstation = cls.Workstation.browse(body["workstation_id"])
        cls._uuid = 0

    # -- helpers ---------------------------------------------------------

    def _event(self, kind, service_state=None):
        type(self)._uuid += 1
        return {
            "uuid": "00000000-0000-4000-8000-%012d" % self._uuid,
            "kind": kind,
            "at": "2026-04-01T08:00:00Z",
            "serial": "SN-MON",
            "usb_product_id": "0084",
            "usb_path": "1-2",
            "service_state": service_state,
        }

    def _report(self, moment, service_state="active", events=()):
        """Une remontée du poste de A à `moment`, heure du serveur ; rend
        `(statut, corps)`."""
        with freeze_time(moment):
            return self.Service.report(
                self.token,
                {
                    "protocol": "1.0",
                    "state": {
                        "hostname": "host-a",
                        "os": {"name": "Debian GNU/Linux", "version": "13"},
                        "service_state": service_state,
                        "decks": [],
                    },
                    "events": list(events),
                    "lost_events": 0,
                },
            )

    def _report_ok(self, moment, service_state="active", events=()):
        status, body = self._report(moment, service_state, events)
        self.assertEqual(status, 200, body)
        return body

    def _make_silent(self, at):
        """Ce que fait le cron d'un poste muet : la sorte `silent` datée de
        la fin du délai, et `silent_since` posé à cette heure."""
        self.Service._server_event(self.workstation, "silent", at)
        self.workstation.write({"silent_since": at})

    def _of_kind(self, kind):
        return self.Event.search(
            [("workstation_id", "=", self.workstation.id), ("kind", "=", kind)]
        )

    # -- tests -----------------------------------------------------------

    def test_a_client_cannot_send_silent_or_heard_again(self):
        # Les deux sortes existent, et seul Odoo les écrit : un poste qui
        # en envoie une est refusé comme pour `moved`, sans rien écrire.
        kinds = dict(self.Event._fields["kind"].selection)
        for kind in ("silent", "heard_again"):
            with self.subTest(kind=kind):
                self.assertIn(kind, kinds)
                before = self.Event.search_count([])
                status, body = self._report(T0, events=[self._event(kind)])
                self.assertEqual(status, 400, body)
                self.assertEqual(body["error"], "bad_request")
                self.assertEqual(self.Event.search_count([]), before)
                self.assertFalse(self._of_kind(kind))
                self.assertFalse(self.workstation.last_report)

    def test_a_server_event_copies_the_names_and_draws_its_uuid(self):
        at = T0 + timedelta(hours=1)
        with freeze_time(T0 + timedelta(hours=2)):
            event = self.Service._server_event(self.workstation, "silent", at)
        self.assertRecordValues(
            event,
            [
                {
                    "kind": "silent",
                    "at": at,
                    "received_at": T0 + timedelta(hours=2),
                    "workstation_id": self.workstation.id,
                    "workstation_name": "host-a",
                    "employee_name": "Employee A",
                    "device_id": False,
                    "previous_workstation_id": False,
                    "service_state": False,
                }
            ],
        )
        self.assertEqual(uuid.UUID(event.uuid).version, 4)
        # Une sorte qu'un poste envoie n'est jamais écrite par le serveur.
        for kind in ("plugged", "unplugged", "service_changed", "unknown"):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    self.Service._server_event(self.workstation, kind, at)

    def test_a_report_after_silence_writes_heard_again_and_clears_it(self):
        self._report_ok(T0)
        self._make_silent(T0 + timedelta(minutes=60))
        back = T0 + timedelta(hours=10)
        self._report_ok(back)
        self.assertFalse(self.workstation.silent_since)
        heard = self._of_kind("heard_again")
        self.assertRecordValues(
            heard,
            [
                {
                    "at": back,
                    "received_at": back,
                    "workstation_name": "host-a",
                    "employee_name": "Employee A",
                    "device_id": False,
                }
            ],
        )
        self.assertEqual(uuid.UUID(heard.uuid).version, 4)
        self.assertEqual(len(self._of_kind("silent")), 1)
        # La remontée suivante parle d'un poste qui parlait déjà.
        self._report_ok(back + timedelta(minutes=15))
        self.assertEqual(self._of_kind("heard_again"), heard)

    def test_a_report_without_silence_writes_no_heard_again(self):
        self._report_ok(T0)
        self._report_ok(T0 + timedelta(hours=3))
        self.assertFalse(self.workstation.silent_since)
        self.assertFalse(self._of_kind("heard_again"))
        self.assertFalse(self._of_kind("silent"))

    def test_a_refused_report_after_silence_leaves_it_silent(self):
        # Une remontée refusée n'écrit rien : le poste reste muet.
        self._report_ok(T0)
        silent_at = T0 + timedelta(minutes=60)
        self._make_silent(silent_at)
        status, _body = self._report(
            T0 + timedelta(hours=2), events=[self._event("silent")]
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.workstation.silent_since, silent_at)
        self.assertFalse(self._of_kind("heard_again"))

    def test_service_state_since_moves_only_when_the_state_changes(self):
        steps = [
            (T0, "active", T0),
            (T0 + timedelta(minutes=15), "active", T0),
            (T0 + timedelta(minutes=30), "failed", T0 + timedelta(minutes=30)),
            (T0 + timedelta(minutes=45), "failed", T0 + timedelta(minutes=30)),
            (T0 + timedelta(minutes=60), "active", T0 + timedelta(minutes=60)),
        ]
        for moment, state, since in steps:
            with self.subTest(moment=moment, state=state):
                self._report_ok(moment, service_state=state)
                self.assertEqual(self.workstation.service_state, state)
                self.assertEqual(self.workstation.service_state_since, since)

    def test_a_state_without_its_date_is_dated_by_the_next_report(self):
        # Un poste remonté avant que la date existe a un état sans date :
        # la remontée suivante la pose, même si l'état ne change pas.
        self._report_ok(T0, service_state="failed")
        self.workstation.write({"service_state_since": False})
        later = T0 + timedelta(minutes=15)
        self._report_ok(later, service_state="failed")
        self.assertEqual(self.workstation.service_state_since, later)

    def test_silent_and_service_dates_are_never_written_by_hand(self):
        self._report_ok(T0)
        for user in (self.user_a, self.manager):
            for field in ("silent_since", "service_state_since"):
                with self.subTest(user=user.name, field=field):
                    with self.assertRaises(AccessError):
                        self.workstation.with_user(user).write({field: T0})

    def test_the_event_label_names_the_service_state(self):
        expected = {
            "active": "Service started",
            "failed": "Service failed",
            "inactive": "Service stopped",
            "absent": "Service absent",
        }
        events = {
            state: self._event("service_changed", service_state=state)
            for state in expected
        }
        self._report_ok(T0, events=events.values())
        for state, label in expected.items():
            with self.subTest(state=state):
                event = self.Event.search(
                    [("uuid", "=", events[state]["uuid"])]
                )
                self.assertEqual(event.label, label)
        # Les autres sortes portent leur propre libellé.
        plugged = self._event("plugged")
        self._report_ok(T0, events=[plugged])
        self.assertEqual(
            self.Event.search([("uuid", "=", plugged["uuid"])]).label,
            "Plugged",
        )
        for kind, label in (
            ("silent", "Workstation silent"),
            ("heard_again", "Workstation heard again"),
        ):
            with self.subTest(kind=kind):
                event = self.Service._server_event(self.workstation, kind, T0)
                self.assertEqual(event.label, label)
