# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.sql_db import Cursor
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
PREFIX = "erplibre_streamdeck."
LOGGER = "odoo.addons.erplibre_streamdeck.models.streamdeck_monitor"
TYPES = {
    kind: "erplibre_streamdeck.activity_type_streamdeck_%s" % kind
    for kind in ("service_failed", "silent", "unplugged", "moved")
}
MODELS = ("streamdeck.workstation", "streamdeck.device")

# Un lundi, 9 h UTC.
T0 = datetime(2026, 4, 6, 9, 0, 0)
MIN = timedelta(minutes=1)
HOUR = timedelta(hours=1)

DECK = {
    "serial": "SN-MON-1",
    "usb_product_id": "0084",
    "usb_path": "1-2",
    "firmware": None,
}
OTHER_DECK = dict(DECK, serial="SN-MON-2", usb_path="1-3")
THIRD_DECK = dict(DECK, serial="SN-MON-3", usb_path="1-4")


@tagged("post_install", "-at_install")
class TestStreamdeckMonitor(TransactionCase):
    """La surveillance : le cron qui marque les postes muets et ouvre les
    activités que le temps révèle, la remontée qui ferme ce qu'elle règle.

    A, B et C sont trois employés, M le gestionnaire nommé aux Paramètres.
    Les remontées passent par le service, comme les routes, l'heure du
    serveur figée à chacune ; le cron est appelé par `_cron_watch()` à une
    heure figée. Les activités sont désactivées tant qu'un test ne les
    active pas, comme sur une base neuve.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["streamdeck.service"]
        cls.Event = cls.env["streamdeck.event"]
        cls.Activity = cls.env["mail.activity"]
        cls.user_a, cls.user_b, cls.user_c = (
            new_test_user(
                cls.env,
                login="zz_sd_watch_%s" % seed,
                name="Employee %s" % seed.upper(),
                groups="base.group_user",
                tz=False,
            )
            for seed in "abc"
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_watch_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
            tz="America/Toronto",
        )
        cls.token_a, cls.workstation_a = cls._enroll(cls.user_a, "a")
        cls.token_b, cls.workstation_b = cls._enroll(cls.user_b, "b")
        cls.token_c, cls.workstation_c = cls._enroll(cls.user_c, "c")

    @classmethod
    def _enroll(cls, user, seed):
        code = cls.Service.new_pairing_code(user)
        status, body = cls.Service.enroll(
            {
                "protocol": "1.0",
                "method": "pairing_code",
                "code": code.code,
                "fingerprint": seed * 64,
                "hostname": "host-%s" % seed,
            }
        )
        assert status == 200, body
        workstation = cls.env["streamdeck.workstation"].browse(
            body["workstation_id"]
        )
        return body["token"], workstation

    # -- helpers ---------------------------------------------------------

    @property
    def Monitor(self):
        return self.env["streamdeck.monitor"]

    def _set(self, **values):
        params = self.env["ir.config_parameter"].sudo()
        for name, value in values.items():
            params.set_param(PREFIX + name, value)

    def _enable(self, recipient="manager", **values):
        self._set(
            activities_enabled="True",
            activity_recipient=recipient,
            activity_manager_id=str(self.manager.id),
            **values,
        )

    _uuid = 0

    def _event(self, kind, at, deck=DECK):
        type(self)._uuid += 1
        return {
            "uuid": "00000000-0000-4000-8000-%012d" % self._uuid,
            "kind": kind,
            "at": at.isoformat() + "Z",
            "serial": deck["serial"],
            "usb_product_id": deck["usb_product_id"],
            "usb_path": deck["usb_path"],
        }

    def _report(
        self, token, moment, decks=(), service_state="active", events=()
    ):
        """Une remontée à `moment`, heure du serveur."""
        with freeze_time(moment):
            status, body = self.Service.report(
                token,
                {
                    "protocol": "1.0",
                    "state": {
                        "hostname": "host",
                        "os": {"name": "Debian GNU/Linux", "version": "13"},
                        "service_state": service_state,
                        "decks": list(decks),
                    },
                    "events": list(events),
                    "lost_events": 0,
                },
            )
        self.assertEqual(status, 200, body)

    def _cron(self, moment):
        with freeze_time(moment):
            self.Monitor._cron_watch()

    def _device(self, deck=DECK):
        return self.env["streamdeck.device"].search(
            [("key", "=", "sn:%s" % deck["serial"])]
        )

    def _activities(self, record=None, kind=None, active=True):
        domain = [("res_model", "in", MODELS)]
        if record is not None:
            domain = [
                ("res_model", "=", record._name),
                ("res_id", "=", record.id),
            ]
        if kind:
            domain.append(
                ("activity_type_id", "=", self.env.ref(TYPES[kind]).id)
            )
        if active is not None:
            domain.append(("active", "=", active))
        return self.Activity.with_context(active_test=False).search(domain)

    def _events(self, workstation, kind):
        return self.Event.search(
            [("workstation_id", "=", workstation.id), ("kind", "=", kind)]
        )

    def _done_messages(self, record, kind):
        """Les messages « activité faite » du fil de `record` pour la
        sorte `kind`."""
        return self.env["mail.message"].search(
            [
                ("model", "=", record._name),
                ("res_id", "=", record.id),
                ("mail_activity_type_id", "=", self.env.ref(TYPES[kind]).id),
            ]
        )

    def _notes(self, device):
        """Les notes du fil de `device` qui ne sont pas des messages
        d'activité."""
        return self.env["mail.message"].search(
            [
                ("model", "=", "streamdeck.device"),
                ("res_id", "=", device.id),
                ("message_type", "=", "comment"),
                ("subtype_id", "=", self.env.ref("mail.mt_note").id),
                ("mail_activity_type_id", "=", False),
            ]
        )

    def _solved_after_the_read(self, record, query, params):
        """Un contexte où le cron lit ses candidats comme d'habitude, puis,
        si `record` en est, `query` écrit sa ligne : une remontée écrite
        par une autre transaction entre la lecture du cron et son
        écriture, qui ne repasse pas par le cache de celle-ci."""
        monitor = type(self.Monitor)
        read = monitor._candidates
        env = self.env

        def candidates(self, model, domain):
            found = read(self, model, domain)
            if model == record._name and record.id in found.ids:
                env.flush_all()
                env.cr.execute(query, params)
            return found

        return patch.object(monitor, "_candidates", candidates)

    def _ctid(self, record):
        """L'emplacement de la ligne de `record`, qui change à chaque
        écriture de la ligne."""
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT ctid::text FROM %s WHERE id = %%s" % record._table,
            (record.id,),
        )
        return self.env.cr.fetchone()[0]

    def _unplug(self, token, moment, deck=DECK, service_state="active"):
        """Le poste remonte le deck, puis, un quart d'heure plus tard, son
        débranchement daté de cinq minutes avant : rend l'heure du
        débranchement."""
        self._report(token, moment, decks=[deck], service_state=service_state)
        unplugged_at = moment + 10 * MIN
        self._report(
            token,
            moment + 15 * MIN,
            service_state=service_state,
            events=[self._event("unplugged", unplugged_at, deck)],
        )
        return unplugged_at

    # -- settings and data -----------------------------------------------

    def test_the_settings_are_read_with_their_defaults_and_floors(self):
        self.assertEqual(
            self.Monitor._settings(),
            {
                "enabled": False,
                "recipient": "manager",
                "manager": self.env["res.users"],
                "alerts": {
                    "service_failed": True,
                    "silent": True,
                    "moved": True,
                    "unplugged": True,
                },
                "silent_after_min": 60,
                "unplugged_after_h": 72,
                "service_failed_after_min": 10,
            },
        )
        # Une valeur écrite à la main, illisible ou sous son plancher, ne
        # descend jamais sous le plancher des Paramètres.
        self._enable(
            recipient="nobody",
            alert_silent="False",
            silent_after_min="5",
            unplugged_after_h="not a number",
            service_failed_after_min="-3",
        )
        settings = self.Monitor._settings()
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["recipient"], "manager")
        self.assertEqual(settings["manager"], self.manager)
        self.assertFalse(settings["alerts"]["silent"])
        self.assertTrue(settings["alerts"]["moved"])
        self.assertEqual(settings["silent_after_min"], 30)
        self.assertEqual(settings["unplugged_after_h"], 72)
        self.assertEqual(settings["service_failed_after_min"], 0)

    def test_the_cron_job_and_the_activity_types_exist(self):
        cron = self.env.ref("erplibre_streamdeck.ir_cron_streamdeck_watch")
        self.assertRecordValues(
            cron,
            [
                {
                    "active": True,
                    "interval_number": 5,
                    "interval_type": "minutes",
                    "code": "model._cron_watch()",
                }
            ],
        )
        self.assertEqual(cron.model_id.model, "streamdeck.monitor")
        for kind, model in (
            ("service_failed", "streamdeck.workstation"),
            ("silent", "streamdeck.workstation"),
            ("unplugged", "streamdeck.device"),
            ("moved", "streamdeck.device"),
        ):
            with self.subTest(kind=kind):
                activity_type = self.env.ref(TYPES[kind])
                self.assertEqual(activity_type.res_model, model)
                # Fermée, l'activité reste lisible, faite.
                self.assertTrue(activity_type.keep_done)
                self.assertFalse(activity_type.triggered_next_type_id)
                self.assertEqual(activity_type.chaining_type, "suggest")

    # -- the plan's tests ------------------------------------------------

    def test_no_activity_while_disabled(self):
        # Tout arrive : service en échec, poste muet, deck changé de poste,
        # deck débranché longtemps. L'historique s'écrit, aucune activité,
        # même avec un destinataire nommé, les quatre cases cochées.
        self._enable(recipient="both")
        self._set(activities_enabled=False)
        self._report(self.token_a, T0, decks=[DECK], service_state="failed")
        self._unplug(self.token_c, T0, deck=OTHER_DECK)
        self._report(self.token_b, T0 + 30 * MIN, decks=[DECK])
        self._cron(T0 + 73 * HOUR)
        self.assertEqual(len(self._events(self.workstation_a, "silent")), 1)
        self.assertEqual(len(self._events(self.workstation_b, "moved")), 1)
        self.assertTrue(self.workstation_a.silent_since)
        self.assertFalse(self._activities(active=None))
        # Les mêmes problèmes, activités activées : le cron les ouvre. Le
        # silence est déjà marqué, il n'en ouvre pas.
        self._enable(recipient="manager")
        self._cron(T0 + 74 * HOUR)
        self.assertEqual(
            len(self._activities(self.workstation_a, "service_failed")), 1
        )
        self.assertFalse(self._activities(self._device(DECK)))
        self.assertEqual(
            len(self._activities(self._device(OTHER_DECK), "unplugged")), 1
        )
        self.assertFalse(self._activities(kind="silent"))

    def test_a_silent_workstation_gets_one_event_and_one_activity(self):
        self._enable()
        self._report(self.token_a, T0)
        self._cron(T0 + 59 * MIN)
        self.assertFalse(self.workstation_a.silent_since)
        self.assertFalse(self._events(self.workstation_a, "silent"))
        self._cron(T0 + 61 * MIN)
        self.assertEqual(self.workstation_a.silent_since, T0 + 60 * MIN)
        silent = self._events(self.workstation_a, "silent")
        self.assertRecordValues(
            silent,
            [
                {
                    "at": T0 + 60 * MIN,
                    "received_at": T0 + 61 * MIN,
                    "workstation_name": "host-a",
                    "device_id": False,
                }
            ],
        )
        activity = self._activities(self.workstation_a, "silent")
        self.assertRecordValues(
            activity, [{"user_id": self.manager.id, "active": True}]
        )
        self.assertIn("60", activity.note)
        self.assertFalse(self._activities(self.workstation_b))

    def test_the_cron_twice_creates_nothing_more(self):
        # Une nuit où tous les postes se taisent, le cron passe et repasse :
        # un événement muet et une activité par poste et destinataire ;
        # les remontées du matin les ferment toutes.
        self._enable(recipient="both")
        for token in (self.token_a, self.token_b):
            self._report(token, T0)
        for moment in (T0 + 61 * MIN, T0 + 2 * HOUR, T0 + 8 * HOUR):
            self._cron(moment)
        for workstation, employee in (
            (self.workstation_a, self.user_a),
            (self.workstation_b, self.user_b),
        ):
            with self.subTest(workstation=workstation.name):
                self.assertEqual(len(self._events(workstation, "silent")), 1)
                activities = self._activities(workstation, "silent")
                self.assertEqual(
                    sorted(activities.mapped("user_id").ids),
                    sorted((employee | self.manager).ids),
                )
        morning = T0 + 9 * HOUR
        for token in (self.token_a, self.token_b):
            self._report(token, morning)
        self.assertFalse(self._activities(kind="silent"))
        self.assertEqual(len(self._activities(kind="silent", active=False)), 4)
        self._cron(morning + 5 * MIN)
        self.assertEqual(len(self._activities(kind="silent", active=None)), 4)
        self.assertEqual(len(self._events(self.workstation_a, "silent")), 1)

    def test_a_workstation_that_reported_since_is_not_marked(self):
        # La remontée arrive entre la lecture du cron et son écriture : le
        # cron relit `last_report` sous le verrou de la ligne et laisse le
        # poste qui vient de parler.
        self._enable()
        self._report(self.token_a, T0)
        workstation = self.workstation_a
        self.assertEqual(workstation.last_report, T0)
        with self._solved_after_the_read(
            workstation,
            "UPDATE streamdeck_workstation SET last_report = %s"
            " WHERE id = %s",
            (T0 + 60 * MIN, workstation.id),
        ):
            self._cron(T0 + 61 * MIN)
        workstation.invalidate_recordset()
        self.assertFalse(workstation.silent_since)
        self.assertFalse(self._events(workstation, "silent"))
        self.assertFalse(self._activities(workstation))

    def test_heard_again_closes_the_silent_activity_with_the_time(self):
        self._enable(recipient="both")
        self._report(self.token_a, T0)
        self._cron(T0 + 61 * MIN)
        activities = self._activities(self.workstation_a, "silent")
        self.assertEqual(len(activities), 2)
        back = T0 + 3 * HOUR
        self._report(self.token_a, back)
        self.assertEqual(
            len(self._events(self.workstation_a, "heard_again")), 1
        )
        self.assertFalse(activities.filtered("active"))
        self.assertTrue(all(activities.mapped("date_done")))
        bodies = self._done_messages(self.workstation_a, "silent").mapped(
            "body"
        )
        self.assertEqual(len(bodies), 2)
        # 12 h UTC : 8 h à Toronto (heure d'été) pour M, UTC pour A qui n'a
        # pas de fuseau.
        self.assertTrue(
            any("Resolved at 2026-04-06 08:00 EDT" in b for b in bodies),
            bodies,
        )
        self.assertTrue(
            any("Resolved at 2026-04-06 12:00 UTC" in b for b in bodies),
            bodies,
        )

    def test_a_failed_service_waits_its_delay_then_closes_as_it_leaves_failed(
        self,
    ):
        self._enable()
        self._report(self.token_a, T0)
        failed_at = T0 + 15 * MIN
        self._report(self.token_a, failed_at, service_state="failed")
        self._cron(failed_at + 9 * MIN)
        self.assertFalse(self._activities(self.workstation_a))
        self._cron(failed_at + 10 * MIN)
        activity = self._activities(self.workstation_a, "service_failed")
        self.assertEqual(len(activity), 1)
        self.assertIn("10", activity.note)
        # Toujours en échec : le cron repasse sans en ouvrir une autre.
        self._report(
            self.token_a, failed_at + 15 * MIN, service_state="failed"
        )
        self._cron(failed_at + 20 * MIN)
        self.assertEqual(
            self._activities(self.workstation_a, "service_failed"), activity
        )
        self._report(
            self.token_a, failed_at + 30 * MIN, service_state="inactive"
        )
        self.assertFalse(activity.active)
        body = self._done_messages(self.workstation_a, "service_failed").body
        self.assertIn("Resolved at", body)
        self.assertIn("stopped", body)

    def test_an_unplugged_deck_alerts_after_72_hours_and_closes_when_plugged(
        self,
    ):
        self._enable()
        unplugged_at = self._unplug(self.token_a, T0)
        device = self._device()
        self.assertFalse(device.connected)
        self._cron(unplugged_at + 72 * HOUR - 5 * MIN)
        self.assertFalse(self._activities(device))
        self._cron(unplugged_at + 72 * HOUR)
        activity = self._activities(device, "unplugged")
        self.assertRecordValues(activity, [{"user_id": self.manager.id}])
        self.assertIn("72", activity.note)
        self._cron(unplugged_at + 73 * HOUR)
        self.assertEqual(self._activities(device, "unplugged"), activity)
        self._report(self.token_a, unplugged_at + 74 * HOUR, decks=[DECK])
        self.assertFalse(activity.active)
        body = self._done_messages(device, "unplugged").body
        self.assertIn("Resolved at", body)
        self.assertIn("plugged in", body)

    def test_a_deck_gone_without_its_event_counts_from_last_seen(self):
        # Un deck absent de l'état sans événement « débranché » (le poste
        # éteint quand on l'a retiré) se compte de sa dernière vue ; un
        # événement « débranché » ancien ne compte plus après une vue plus
        # récente.
        self._enable()
        self._report(
            self.token_a,
            T0,
            decks=[DECK],
            events=[self._event("unplugged", T0 - 200 * HOUR)],
        )
        self._report(self.token_a, T0 + 15 * MIN)
        device = self._device()
        self._cron(T0 + 72 * HOUR - 5 * MIN)
        self.assertFalse(self._activities(device))
        self._cron(T0 + 72 * HOUR)
        self.assertEqual(len(self._activities(device, "unplugged")), 1)

    def test_a_moved_deck_opens_one_activity_and_a_second_move_adds_a_note(
        self,
    ):
        self._enable()
        self._report(self.token_a, T0, decks=[DECK])
        device = self._device()
        self.assertFalse(self._activities(device))
        self._report(self.token_b, T0 + HOUR, decks=[DECK])
        activity = self._activities(device, "moved")
        self.assertRecordValues(activity, [{"user_id": self.manager.id}])
        self.assertIn("host-a", activity.note)
        self.assertIn("host-b", activity.note)
        notes = self._notes(device)
        self._report(self.token_c, T0 + 2 * HOUR, decks=[DECK])
        self.assertEqual(self._activities(device, "moved"), activity)
        added = self._notes(device) - notes
        self.assertEqual(len(added), 1)
        self.assertIn("host-b", added.body)
        self.assertIn("host-c", added.body)
        # Le deck changé de poste ne se ferme pas seul : le rebrancher ou
        # le revoir n'y touche pas.
        self._report(self.token_c, T0 + 3 * HOUR)
        self._report(self.token_c, T0 + 4 * HOUR, decks=[DECK])
        self.assertTrue(activity.active)

    def test_recipient_both_gives_two_activities_employee_gives_the_owner_only(
        self,
    ):
        self._enable(recipient="both")
        self._report(self.token_a, T0, decks=[DECK])
        self._cron(T0 + 61 * MIN)
        self.assertEqual(
            self._activities(self.workstation_a, "silent").user_id,
            self.user_a | self.manager,
        )
        self._enable(recipient="employee")
        self._report(self.token_b, T0, decks=[OTHER_DECK])
        self._cron(T0 + 2 * HOUR)
        self.assertEqual(
            self._activities(self.workstation_b, "silent").user_id,
            self.user_b,
        )
        # Pour un deck, l'employé est celui du poste qui le tient : le
        # nouveau détenteur, pour un deck changé de poste.
        self._report(self.token_c, T0 + 3 * HOUR, decks=[DECK])
        self.assertEqual(
            self._activities(self._device(), "moved").user_id, self.user_c
        )

    def test_an_archived_manager_gets_nothing_and_breaks_nothing(self):
        self._enable(recipient="both")
        self.manager.active = False
        self._report(self.token_a, T0)
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self._cron(T0 + 61 * MIN)
        self.assertIn("archived", "\n".join(logs.output))
        self.assertNotIn("Manager M", "\n".join(logs.output))
        self.assertEqual(
            self._activities(self.workstation_a, "silent").user_id,
            self.user_a,
        )
        # Destinataire « gestionnaire » seul : l'historique s'écrit, aucune
        # activité, aucune erreur.
        self._enable(recipient="manager")
        self.manager.active = False
        self._report(self.token_b, T0)
        with self.assertLogs(LOGGER, "WARNING"):
            self._cron(T0 + 2 * HOUR)
        self.assertEqual(len(self._events(self.workstation_b, "silent")), 1)
        self.assertFalse(self._activities(self.workstation_b))

    def test_unenrolled_revoked_or_archived_workstations_never_go_silent(
        self,
    ):
        self._enable()
        for token in (self.token_a, self.token_b, self.token_c):
            self._report(token, T0)
        self.Service.unenroll(self.token_a, {"protocol": "1.0"})
        self.workstation_b.with_user(self.manager).action_revoke_token()
        self.workstation_c.with_user(self.manager).action_archive()
        # Un quatrième poste, inscrit, se tait : le cron tourne bien.
        token_d, workstation_d = self._enroll(self.user_a, "d")
        self._report(token_d, T0)
        self._cron(T0 + 2 * HOUR)
        self.assertTrue(workstation_d.silent_since)
        for workstation in (
            self.workstation_a,
            self.workstation_b,
            self.workstation_c,
        ):
            with self.subTest(workstation=workstation.name):
                self.assertFalse(workstation.silent_since)
                self.assertFalse(self._events(workstation, "silent"))
                self.assertFalse(self._activities(workstation, active=None))

    def test_a_silent_workstation_unenrolled_or_archived_is_no_longer_silent(
        self,
    ):
        # Le cron ne revoit plus un poste sans jeton : la marque laissée
        # le garderait au filtre « Muets » et en couleur au Parc sans fin.
        self._enable()
        for token in (self.token_a, self.token_b, self.token_c):
            self._report(token, T0)
        self._cron(T0 + 2 * HOUR)
        ended = (self.workstation_a, self.workstation_b, self.workstation_c)
        for workstation in ended:
            self.assertTrue(workstation.silent_since)
        self.Service.unenroll(self.token_a, {"protocol": "1.0"})
        self.workstation_b.with_user(self.manager).action_revoke_token()
        self.workstation_c.with_user(self.manager).action_archive()
        silent = self.env["streamdeck.workstation"].with_context(
            active_test=False
        )
        for workstation in ended:
            with self.subTest(workstation=workstation.name):
                self.assertFalse(workstation.silent_since)
                self.assertFalse(
                    silent.search(
                        [
                            ("silent_since", "!=", False),
                            ("id", "=", workstation.id),
                        ]
                    )
                )
                # L'historique garde le silence.
                self.assertEqual(len(self._events(workstation, "silent")), 1)

    def test_archiving_a_workstation_closes_its_activities(self):
        self._enable()
        self._unplug(self.token_a, T0, deck=DECK, service_state="failed")
        self._unplug(self.token_b, T0, deck=OTHER_DECK, service_state="failed")
        self._cron(T0 + 73 * HOUR)
        opened = {
            "archived": (self.workstation_a, self._device(DECK)),
            "unenrolled": (self.workstation_b, self._device(OTHER_DECK)),
        }
        for workstation, device in opened.values():
            for record, kind in (
                (workstation, "silent"),
                (workstation, "service_failed"),
                (device, "unplugged"),
            ):
                self.assertEqual(len(self._activities(record, kind)), 1)
        self.workstation_a.with_user(self.manager).action_archive()
        self.workstation_b.with_user(self.manager).action_revoke_token()
        for reason, (workstation, device) in opened.items():
            for record, kind in (
                (workstation, "silent"),
                (workstation, "service_failed"),
                (device, "unplugged"),
            ):
                with self.subTest(reason=reason, kind=kind):
                    self.assertFalse(self._activities(record, kind))
                    self.assertEqual(
                        len(self._activities(record, kind, active=False)), 1
                    )
                    body = self._done_messages(record, kind).body
                    self.assertIn("Resolved at", body)
                    self.assertIn(reason, body)

    def test_an_employee_reads_activities_of_their_records_only(self):
        self._enable(recipient="both")
        self._report(self.token_a, T0, decks=[DECK])
        self._report(self.token_b, T0 + 30 * MIN, decks=[DECK])
        self._cron(T0 + 2 * HOUR)
        on_a = self._activities(self.workstation_a, "silent")
        on_b = self._activities(self.workstation_b, "silent")
        moved = self._activities(self._device(), "moved")
        self.assertEqual(len(on_a), 2)
        self.assertEqual(len(on_b), 2)
        self.assertEqual(moved.user_id, self.user_b | self.manager)
        self.env.invalidate_all()
        readable = self.Activity.with_user(self.user_a).search(
            [("res_model", "in", MODELS)]
        )
        # A lit les deux activités de son poste, celle de M comprise, et,
        # prêteur, celles du deck passé chez B ; rien du poste de B.
        self.assertEqual(readable, on_a | moved)
        with self.assertRaises(AccessError):
            on_b.with_user(self.user_a).read(["summary"])
        self.env.invalidate_all()
        readable = self.Activity.with_user(self.user_b).search(
            [("res_model", "in", MODELS)]
        )
        self.assertEqual(readable, on_b | moved)

    # -- beyond the plan -------------------------------------------------

    def test_an_alert_turned_off_opens_nothing_of_its_kind(self):
        self._enable(alert_silent="False")
        self._report(self.token_a, T0, service_state="failed")
        self._cron(T0 + 61 * MIN)
        self.assertEqual(len(self._events(self.workstation_a, "silent")), 1)
        self.assertFalse(self._activities(kind="silent"))
        self.assertEqual(
            len(self._activities(self.workstation_a, "service_failed")), 1
        )

    def test_a_deleted_activity_type_breaks_no_report(self):
        # Les types sont des données que l'administrateur peut supprimer :
        # le problème n'ouvre alors rien, l'historique s'écrit, et ni la
        # remontée ni le cron n'échouent.
        self._enable()
        for kind in ("moved", "unplugged", "silent"):
            self.env.ref(TYPES[kind]).unlink()
        self._unplug(self.token_a, T0)
        self._report(self.token_b, T0 + HOUR, decks=[DECK])
        self._report(self.token_a, T0 + HOUR, decks=[OTHER_DECK])
        self._cron(T0 + 3 * HOUR)
        self.assertEqual(len(self._events(self.workstation_b, "moved")), 1)
        self.assertEqual(len(self._events(self.workstation_a, "silent")), 1)
        self.assertFalse(self.Activity.search([("res_model", "in", MODELS)]))

    def test_only_the_monitoring_opens_its_activity_types(self):
        # Une activité de ces types posée à la main tromperait le
        # dédoublonnage : l'employé, ni même le gestionnaire, n'en crée
        # pas, ni n'y change une activité ; une activité ordinaire reste
        # permise.
        todo = self.env.ref("mail.mail_activity_data_todo")
        silent = self.env.ref(TYPES["silent"])
        model_id = self.env["ir.model"]._get_id("streamdeck.workstation")
        for user in (self.user_a, self.manager):
            with self.subTest(user=user.name):
                Activity = self.Activity.with_user(user)
                values = {
                    "res_model_id": model_id,
                    "res_id": self.workstation_a.id,
                    "user_id": self.manager.id,
                }
                with self.assertRaises(AccessError):
                    Activity.create(dict(values, activity_type_id=silent.id))
                own = Activity.create(dict(values, activity_type_id=todo.id))
                with self.assertRaises(AccessError):
                    own.write({"activity_type_id": silent.id})
        # Le cron, lui, ouvre la sienne malgré l'activité ordinaire.
        self._enable()
        self._report(self.token_a, T0)
        self._cron(T0 + 61 * MIN)
        self.assertEqual(
            len(self._activities(self.workstation_a, "silent")), 1
        )

    # -- review round ----------------------------------------------------

    def test_a_problem_solved_since_the_cron_read_opens_nothing(self):
        # Comme pour le silence : une remontée qui règle le problème entre
        # la lecture du cron et son écriture (service reparti, deck
        # rebranché) ne laisse pas derrière elle une activité que plus
        # rien ne fermerait. Le poste B, que rien ne règle, sert de témoin.
        self._enable()
        for token, deck in ((self.token_a, DECK), (self.token_b, OTHER_DECK)):
            self._unplug(token, T0, deck=deck, service_state="failed")
        workstation, device = self.workstation_a, self._device(DECK)
        with self._solved_after_the_read(
            workstation,
            "UPDATE streamdeck_workstation SET service_state = 'active',"
            " service_state_since = %s WHERE id = %s",
            (T0 + 20 * MIN, workstation.id),
        ):
            self._cron(T0 + 30 * MIN)
        self.assertFalse(self._activities(workstation, "service_failed"))
        self.assertEqual(
            len(self._activities(self.workstation_b, "service_failed")), 1
        )
        with self._solved_after_the_read(
            device,
            "UPDATE streamdeck_device SET connected = TRUE, last_seen = %s"
            " WHERE id = %s",
            (T0 + 73 * HOUR, device.id),
        ):
            self._cron(T0 + 73 * HOUR)
        self.assertFalse(self._activities(device, "unplugged"))
        self.assertEqual(
            len(self._activities(self._device(OTHER_DECK), "unplugged")), 1
        )

    def test_the_cron_writes_the_row_it_opens_an_activity_on(self):
        # Le verrou seul laisse une remontée qui l'attendait poursuivre
        # avec une image de la base antérieure à l'activité, qu'elle ne
        # fermerait pas ; la ligne réécrite la fait échouer, puis rejouer
        # avec une image qui voit l'activité. Rien n'est réécrit quand
        # rien ne s'ouvre.
        self._enable()
        self._unplug(self.token_a, T0, service_state="failed")
        # Une remontée récente : le poste n'est pas muet, le cron n'écrit
        # pas `silent_since`.
        self._report(
            self.token_a, T0 + 73 * HOUR - 5 * MIN, service_state="failed"
        )
        records = (self.workstation_a, self._device())
        before = [self._ctid(record) for record in records]
        self._cron(T0 + 73 * HOUR)
        self.assertEqual(
            len(self._activities(self.workstation_a, "service_failed")), 1
        )
        self.assertEqual(len(self._activities(self._device(), "unplugged")), 1)
        after = [self._ctid(record) for record in records]
        for record, old, new in zip(records, before, after):
            with self.subTest(model=record._name):
                self.assertNotEqual(old, new)
        self._cron(T0 + 73 * HOUR + 5 * MIN)
        self.assertEqual([self._ctid(record) for record in records], after)

    def test_a_skipped_lock_writes_no_error_to_the_log(self):
        # Une remontée qui tient la ligne, ou l'a changée depuis l'image du
        # cron : le cron passe ce poste, c'est prévu, et n'écrit aucune
        # erreur SQL au journal du serveur.
        self._report(self.token_a, T0)
        execute = Cursor.execute
        for code in ("lock_not_available", "serialization_failure"):

            def refused(cr, query, params=None, log_exceptions=True):
                if "FOR UPDATE NOWAIT" in getattr(query, "code", str(query)):
                    query = (
                        "DO $$ BEGIN RAISE EXCEPTION 'busy'"
                        " USING ERRCODE = '%s'; END $$" % code
                    )
                return execute(cr, query, params, log_exceptions)

            with self.subTest(code=code):
                with patch.object(Cursor, "execute", refused):
                    with self.assertNoLogs("odoo.sql_db", "ERROR"):
                        self._cron(T0 + 61 * MIN)
                self.assertFalse(self.workstation_a.silent_since)
        self._cron(T0 + 61 * MIN)
        self.assertTrue(self.workstation_a.silent_since)

    def test_a_second_move_adds_a_note_whoever_the_activity_went_to(self):
        # « Changé de poste » reste une seule activité ouverte par deck,
        # que le destinataire soit l'employé ou les deux : le nouveau
        # détenteur d'un deck déplacé une seconde fois n'en reçoit pas une
        # de plus, le fil du deck reçoit une note.
        for recipient, deck, first in (
            ("employee", DECK, self.user_b),
            ("both", OTHER_DECK, self.user_b | self.manager),
        ):
            with self.subTest(recipient=recipient):
                self._enable(recipient=recipient)
                self._report(self.token_a, T0, decks=[deck])
                self._report(self.token_b, T0 + HOUR, decks=[deck])
                device = self._device(deck)
                activities = self._activities(device, "moved")
                self.assertEqual(activities.user_id, first)
                notes = self._notes(device)
                self._report(self.token_c, T0 + 2 * HOUR, decks=[deck])
                self.assertEqual(self._activities(device, "moved"), activities)
                added = self._notes(device) - notes
                self.assertEqual(len(added), 1)
                self.assertIn("host-b", added.body)
                self.assertIn("host-c", added.body)

    def test_disabled_activities_never_warn_about_the_manager(self):
        # Activités désactivées, aucune part du gestionnaire ne peut
        # naître : son archivage n'a rien à signaler, ni au cron ni à une
        # remontée qui déplace un deck.
        self._enable(recipient="both")
        self._set(activities_enabled=False)
        self.manager.active = False
        with self.assertNoLogs(LOGGER, "WARNING"):
            self._report(self.token_a, T0, decks=[DECK])
            self._report(self.token_b, T0 + HOUR, decks=[DECK])
            self._cron(T0 + 3 * HOUR)
        self.assertEqual(len(self._events(self.workstation_b, "moved")), 1)
        self.assertEqual(len(self._events(self.workstation_a, "silent")), 1)
        self.assertFalse(self._activities(active=None))

    def test_archiving_the_employee_closes_their_workstation_activities(
        self,
    ):
        # Le départ de l'employé (lot 1) archive son poste par write(),
        # hors du chemin d'action_archive : ses activités se ferment là
        # aussi, « archived », au lieu de partir avec le poste archivé.
        self._enable()
        self._unplug(self.token_a, T0, service_state="failed")
        self._cron(T0 + 73 * HOUR)
        opened = (
            (self.workstation_a, "silent"),
            (self.workstation_a, "service_failed"),
            (self._device(), "unplugged"),
        )
        for record, kind in opened:
            self.assertEqual(len(self._activities(record, kind)), 1)
        self.user_a.active = False
        self.assertFalse(self.workstation_a.active)
        for record, kind in opened:
            with self.subTest(kind=kind):
                self.assertFalse(self._activities(record, kind))
                self.assertEqual(
                    len(self._activities(record, kind, active=False)), 1
                )
                body = self._done_messages(record, kind).body
                self.assertIn("Resolved at", body)
                self.assertIn("archived", body)

    def test_a_workstation_no_longer_watched_opens_no_failed_or_unplugged(
        self,
    ):
        # Révoqué ou archivé, un poste ne remontera plus : figé « en
        # échec », son deck débranché, il alerterait sans fin. B, inscrit,
        # sert de témoin.
        self._enable()
        for token, deck in (
            (self.token_a, DECK),
            (self.token_b, OTHER_DECK),
            (self.token_c, THIRD_DECK),
        ):
            self._unplug(token, T0, deck=deck, service_state="failed")
        self.workstation_a.with_user(self.manager).action_revoke_token()
        self.workstation_c.with_user(self.manager).action_archive()
        self._cron(T0 + 73 * HOUR)
        self.assertEqual(
            len(self._activities(self.workstation_b, "service_failed")), 1
        )
        self.assertEqual(
            len(self._activities(self._device(OTHER_DECK), "unplugged")), 1
        )
        for workstation, deck in (
            (self.workstation_a, DECK),
            (self.workstation_c, THIRD_DECK),
        ):
            with self.subTest(workstation=workstation.name):
                self.assertFalse(
                    self._activities(
                        workstation, "service_failed", active=None
                    )
                )
                self.assertFalse(
                    self._activities(
                        self._device(deck), "unplugged", active=None
                    )
                )

    def test_the_note_and_the_feedback_speak_the_recipient_language(self):
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            ["erplibre_streamdeck"], ["fr_CA"], overwrite=True
        )
        self.user_a.lang = "fr_CA"
        self._enable(recipient="both")
        self._report(self.token_a, T0)
        self._cron(T0 + 61 * MIN)
        activities = self._activities(self.workstation_a, "silent")
        french = activities.filtered(lambda a: a.user_id == self.user_a)
        self.assertIn("aucune remontée depuis 60 minutes", french.note)
        self.assertIn(
            "has sent no report for 60 minutes", (activities - french).note
        )
        self._report(self.token_a, T0 + 3 * HOUR)
        bodies = self._done_messages(self.workstation_a, "silent").mapped(
            "body"
        )
        self.assertTrue(
            any(
                "Résolu à 2026-04-06 12:00 UTC" in b
                and "le poste est revenu" in b
                for b in bodies
            ),
            bodies,
        )
        self.assertTrue(
            any(
                "Resolved at 2026-04-06 08:00 EDT" in b
                and "the workstation reported again" in b
                for b in bodies
            ),
            bodies,
        )

    # -- design rules of the monitoring ---------------------------------

    def test_a_deck_unplugged_long_writes_no_event_of_its_own(self):
        # L'événement « débranché » date déjà le débranchement : le délai
        # n'ouvre qu'une activité. Le cron n'écrit que le silence du poste.
        self._enable()
        self._unplug(self.token_a, T0)
        device = self._device()
        before = self.Event.search([])
        self._cron(T0 + 73 * HOUR)
        self.assertEqual(len(self._activities(device, "unplugged")), 1)
        written = self.Event.search([]) - before
        self.assertEqual(written.mapped("kind"), ["silent"])
        self.assertFalse(written.device_id)

    def test_a_report_leaves_the_time_based_work_to_the_cron(self):
        # Une remontée ne touche que son poste et ses decks : le silence,
        # le service en échec et le deck débranché d'un autre poste, tous
        # au-delà de leur délai, attendent le cron.
        self._enable()
        self._unplug(self.token_b, T0, deck=OTHER_DECK, service_state="failed")
        self._report(self.token_a, T0 + 73 * HOUR, decks=[DECK])
        self.assertFalse(self.workstation_b.silent_since)
        self.assertFalse(self._events(self.workstation_b, "silent"))
        self.assertFalse(self._activities(active=None))
        self._cron(T0 + 73 * HOUR)
        self.assertTrue(self.workstation_b.silent_since)
        for record, kind in (
            (self.workstation_b, "silent"),
            (self.workstation_b, "service_failed"),
            (self._device(OTHER_DECK), "unplugged"),
        ):
            with self.subTest(kind=kind):
                self.assertEqual(len(self._activities(record, kind)), 1)

    def test_a_report_never_sends_the_notices_of_its_activities(self):
        # Une activité ouverte pour un autre utilisateur lui vaut l'avis
        # d'Odoo, par courriel selon sa préférence. Celui d'une remontée
        # part dans la file des courriels : la remontée n'attend jamais le
        # serveur de courriel.
        self._enable(recipient="both")
        (self.user_b | self.manager).write({"notification_type": "email"})
        self._report(self.token_a, T0, decks=[DECK])
        Mail = type(self.env["mail.mail"])
        with patch.object(Mail, "send", autospec=True) as send:
            self._report(self.token_b, T0 + HOUR, decks=[DECK])
        self.assertEqual(
            self._activities(self._device(), "moved").user_id,
            self.user_b | self.manager,
        )
        send.assert_not_called()
        queued = self.env["mail.mail"].search(
            [
                ("model", "=", "streamdeck.device"),
                ("res_id", "=", self._device().id),
                ("state", "=", "outgoing"),
            ]
        )
        self.assertEqual(
            queued.recipient_ids,
            (self.user_b | self.manager).partner_id,
        )

    def test_an_employee_reads_no_message_of_another_workstation(self):
        # Le fil d'un poste se lit avec le poste : A lit la note posée sur
        # le sien, aucune de celle posée sur le poste de B.
        notes = {
            workstation: workstation.message_post(
                body="Checked", message_type="comment"
            )
            for workstation in (self.workstation_a, self.workstation_b)
        }
        self.env.invalidate_all()
        Message = self.env["mail.message"].with_user(self.user_a)
        readable = Message.search(
            [
                ("model", "=", "streamdeck.workstation"),
                ("id", "in", [note.id for note in notes.values()]),
            ]
        )
        self.assertEqual(readable, notes[self.workstation_a])
        with self.assertRaises(AccessError):
            notes[self.workstation_b].with_user(self.user_a).read(["body"])

    # -- final review round ----------------------------------------------

    def test_a_type_from_the_context_forges_no_monitoring_activity(self):
        # Le type d'une activité vient de ses valeurs, de la clé de
        # contexte default_activity_type_id ou du défaut du modèle : le
        # refus porte sur l'activité créée, quelle que soit la voie. Sans
        # lui, l'activité de A tiendrait la place de celle de M, qui ne
        # recevrait rien pour le silence.
        self._enable()
        silent = self.env.ref(TYPES["silent"])
        Activity = self.Activity.with_user(self.user_a).with_context(
            default_activity_type_id=silent.id
        )
        values = {
            "res_model_id": self.env["ir.model"]._get_id(
                "streamdeck.workstation"
            ),
            "res_id": self.workstation_a.id,
            "user_id": self.manager.id,
            "summary": "probe",
        }
        with self.assertRaises(AccessError):
            Activity.create(values)
        self.assertFalse(self._activities(self.workstation_a, active=None))
        self._report(self.token_a, T0)
        self._cron(T0 + 61 * MIN)
        self.assertRecordValues(
            self._activities(self.workstation_a, "silent"),
            [{"user_id": self.manager.id, "automated": True}],
        )
