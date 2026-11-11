# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import datetime

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"

# Les trois moments du prêt : A déclare le deck, B le prend, A le reprend.
DAY_A = datetime(2026, 3, 1, 10, 0, 0)
DAY_B = datetime(2026, 3, 2, 10, 0, 0)
DAY_BACK = datetime(2026, 3, 3, 10, 0, 0)


@tagged("post_install", "-at_install")
class TestStreamdeckHolding(TransactionCase):
    """Chaque employé lit l'historique d'un deck à partir du moment où un
    de ses postes l'a détenu pour la première fois.

    A, B et C sont trois employés, M le gestionnaire. Les remontées passent
    par le service, comme les routes : le deck naît chez A, puis passe chez
    B par une remontée qui le déclare, ce qui crée l'événement « changé de
    poste ». L'heure du serveur est figée à chaque remontée.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["streamdeck.service"]
        cls.Device = cls.env["streamdeck.device"]
        cls.Event = cls.env["streamdeck.event"]
        cls.Holding = cls.env["streamdeck.device.holding"]
        cls.user_a, cls.user_b, cls.user_c = (
            new_test_user(
                cls.env,
                login="zz_sd_hold_%s" % seed,
                name="Employee %s" % seed.upper(),
                groups="base.group_user",
            )
            for seed in "abc"
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_hold_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        cls.token_a = cls._enroll(cls.user_a, "a")
        cls.token_b = cls._enroll(cls.user_b, "b")
        cls.token_c = cls._enroll(cls.user_c, "c")
        cls._uuid = 0

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
        return body["token"]

    # -- helpers ---------------------------------------------------------

    DECK = {
        "serial": "SN-HOLD",
        "usb_product_id": "0084",
        "usb_path": "1-2",
        "firmware": None,
    }

    def _event(self, kind, at):
        type(self)._uuid += 1
        return {
            "uuid": "00000000-0000-4000-8000-%012d" % self._uuid,
            "kind": kind,
            "at": at.isoformat() + "Z",
            "serial": self.DECK["serial"],
            "usb_product_id": self.DECK["usb_product_id"],
            "usb_path": self.DECK["usb_path"],
        }

    def _report(self, token, moment, kinds=(), decks=True, at=None):
        """Une remontée à `moment` (heure du serveur) : le deck dans
        l'état si `decks`, et un événement du deck par sorte de `kinds`,
        daté de `at`, ou de `moment` à défaut."""
        with freeze_time(moment):
            status, body = self.Service.report(
                token,
                {
                    "protocol": "1.0",
                    "state": {
                        "hostname": "host",
                        "os": {"name": "Debian GNU/Linux", "version": "13"},
                        "service_state": "active",
                        "decks": [self.DECK] if decks else [],
                    },
                    "events": [
                        self._event(kind, at or moment) for kind in kinds
                    ],
                    "lost_events": 0,
                },
            )
        self.assertEqual(status, 200, body)

    def _device(self):
        return self.Device.search([("key", "=", "sn:SN-HOLD")])

    def _seen(self, user):
        """Les événements du deck que lit `user`, sous ses droits et ses
        règles."""
        return self.Event.with_user(user).search(
            [("device_id", "=", self._device().id)]
        )

    def _lend_to_b(self):
        """Le deck naît chez A avec deux événements, puis passe chez B, qui
        en remonte un. Rend (événements de A, événements depuis B)."""
        self._report(self.token_a, DAY_A, kinds=["plugged"])
        self._report(self.token_a, DAY_A.replace(hour=11), kinds=["unplugged"])
        at_a = self._device().event_ids
        self._report(self.token_b, DAY_B, kinds=["plugged"])
        since_b = self._device().event_ids - at_a
        return at_a, since_b

    # -- tests -----------------------------------------------------------

    def test_a_new_holder_reads_nothing_before_their_arrival(self):
        at_a, since_b = self._lend_to_b()
        self.assertEqual(len(at_a), 2)
        self.assertEqual(sorted(since_b.mapped("kind")), ["moved", "plugged"])
        self._report(self.token_b, DAY_B.replace(hour=12), kinds=["unplugged"])
        since_b = self._device().event_ids - at_a
        self.assertEqual(self._seen(self.user_b), since_b)
        self.assertEqual(len(since_b), 3)
        for event in at_a:
            with self.subTest(kind=event.kind):
                with self.assertRaises(AccessError):
                    event.with_user(self.user_b).read(["kind"])
        # La fiche du deck reste lisible : B la tient.
        self.assertEqual(
            self.Device.with_user(self.user_b).search(
                [("id", "=", self._device().id)]
            ),
            self._device(),
        )

    def test_the_lender_keeps_the_whole_history(self):
        at_a, since_b = self._lend_to_b()
        self._report(self.token_b, DAY_B.replace(hour=12), kinds=["unplugged"])
        self.assertEqual(self._seen(self.user_a), self._device().event_ids)
        self.assertEqual(len(self._seen(self.user_a)), 5)
        self.assertEqual(
            self.Device.with_user(self.user_a).search(
                [("id", "=", self._device().id)]
            ),
            self._device(),
        )

    def test_a_holder_coming_back_keeps_their_first_since(self):
        at_a, since_b = self._lend_to_b()
        self._report(self.token_a, DAY_BACK, kinds=["plugged"])
        device = self._device()
        self.assertEqual(
            device.workstation_id.user_id, self.user_a, "back at A"
        )
        self.assertEqual(
            len(device.event_ids.filtered(lambda e: e.kind == "moved")), 2
        )
        holdings = self.Holding.search([("device_id", "=", device.id)])
        self.assertEqual(
            {(h.user_id, h.since) for h in holdings},
            {(self.user_a, DAY_A), (self.user_b, DAY_B)},
        )
        self.assertEqual(self._seen(self.user_a), device.event_ids)
        # B, prêteur à son tour, lit tout depuis son arrivée, le retour
        # chez A compris, et rien d'avant.
        self.assertEqual(self._seen(self.user_b), device.event_ids - at_a)
        self.assertTrue(
            all(event.at >= DAY_B for event in self._seen(self.user_b))
        )

    def test_the_manager_reads_everything(self):
        self._lend_to_b()
        self._report(self.token_a, DAY_BACK, kinds=["plugged"])
        self.assertEqual(self._seen(self.manager), self._device().event_ids)
        self.assertEqual(len(self._seen(self.manager)), 6)

    def test_a_third_employee_reads_nothing(self):
        self._lend_to_b()
        device = self._device()
        as_c = self.user_c
        self.assertFalse(self._seen(as_c))
        self.assertFalse(
            self.Device.with_user(as_c).search([("id", "=", device.id)])
        )
        for event in device.event_ids:
            with self.subTest(kind=event.kind):
                with self.assertRaises(AccessError):
                    event.with_user(as_c).read(["kind"])

    def test_an_event_about_a_deck_held_elsewhere_opens_nothing(self):
        # C envoie un événement portant le numéro de série du deck de A,
        # sans le déclarer dans son état : le deck reste chez A et C ne
        # le détient pas. C lit son propre événement, aucun de A, ni
        # d'avant ni d'après.
        self._report(self.token_a, DAY_A, kinds=["plugged"])
        self._report(self.token_c, DAY_B, kinds=["plugged"], decks=False)
        self._report(self.token_a, DAY_BACK, kinds=["unplugged"])
        device = self._device()
        self.assertEqual(device.workstation_id.user_id, self.user_a)
        self.assertFalse(
            self.Holding.search(
                [
                    ("device_id", "=", device.id),
                    ("user_id", "=", self.user_c.id),
                ]
            )
        )
        at_c = device.event_ids.filtered(
            lambda e: e.workstation_id.user_id == self.user_c
        )
        self.assertEqual(len(at_c), 1)
        self.assertEqual(self._seen(self.user_c), at_c)
        for event in device.event_ids - at_c:
            with self.subTest(kind=event.kind, at=event.at):
                with self.assertRaises(AccessError):
                    event.with_user(self.user_c).read(["kind"])

    def test_a_late_lender_event_dated_before_the_move_stays_hidden(self):
        # A remonte après le déplacement un événement qu'il a gardé hors
        # ligne, daté d'avant l'arrivée du deck chez B : la visibilité
        # compare la détention de B à l'heure de l'événement, non à sa
        # réception.
        at_a, _since_b = self._lend_to_b()
        self._report(
            self.token_a,
            DAY_B.replace(hour=13),
            kinds=["unplugged"],
            decks=False,
            at=DAY_A.replace(hour=12),
        )
        late = self._device().event_ids.filtered(
            lambda e: e.received_at == DAY_B.replace(hour=13)
        )
        self.assertEqual(len(late), 1)
        self.assertEqual(late.at, DAY_A.replace(hour=12))
        self.assertNotIn(late, self._seen(self.user_b))
        with self.assertRaises(AccessError):
            late.with_user(self.user_b).read(["kind"])
        self.assertIn(late, self._seen(self.user_a))

    def test_a_reported_time_never_opens_the_history_before_arrival(self):
        # L'heure d'un événement vient du poste : B la recule avant
        # l'arrivée du deck chez lui. Il lit cet événement, le sien, mais
        # sa détention reste datée par Odoo et rien de A ne s'ouvre.
        at_a, _since_b = self._lend_to_b()
        backdated = self._event("unplugged", datetime(2000, 1, 1))
        with freeze_time(DAY_B.replace(hour=12)):
            self.Service.report(
                self.token_b,
                {
                    "protocol": "1.0",
                    "state": {
                        "os": {"name": "Debian GNU/Linux"},
                        "service_state": "active",
                        "decks": [self.DECK],
                    },
                    "events": [backdated],
                    "lost_events": 0,
                },
            )
        holding = self.Holding.search(
            [
                ("device_id", "=", self._device().id),
                ("user_id", "=", self.user_b.id),
            ]
        )
        self.assertEqual(holding.since, DAY_B)
        seen = self._seen(self.user_b)
        self.assertIn(backdated["uuid"], seen.mapped("uuid"))
        self.assertFalse(seen & at_a)

    def test_holdings_cannot_be_written_by_an_employee(self):
        self._lend_to_b()
        holding = self.Holding.search(
            [("user_id", "=", self.user_b.id)], limit=1
        )
        self.assertTrue(holding)
        for user in (self.user_b, self.user_c, self.manager):
            Holding = self.Holding.with_user(user)
            with self.subTest(user=user.login, op="create"):
                with self.assertRaises(AccessError):
                    Holding.create(
                        {
                            "device_id": self._device().id,
                            "user_id": user.id,
                            "since": "2000-01-01 00:00:00",
                        }
                    )
            with self.subTest(user=user.login, op="write"):
                with self.assertRaises(AccessError):
                    holding.with_user(user).write(
                        {"since": "2000-01-01 00:00:00"}
                    )
            with self.subTest(user=user.login, op="read"):
                with self.assertRaises(AccessError):
                    Holding.search([])
            with self.subTest(user=user.login, op="unlink"):
                with self.assertRaises(AccessError):
                    holding.with_user(user).unlink()
        self.assertEqual(holding.since, DAY_B)

    def _backfill_from_scratch(self, device):
        """Efface toute détention et la refait depuis l'historique, le
        deck daté de sa création chez A, comme une base écrite avant les
        détentions."""
        self.env.cr.execute(
            "UPDATE streamdeck_device SET create_date = %s WHERE id = %s",
            (DAY_A, device.id),
        )
        self.Holding.search([]).unlink()
        self.Holding._backfill()
        self.Holding.invalidate_model()
        return self.Holding.search([("device_id", "=", device.id)])

    def test_the_backfill_dates_each_holder_from_the_history(self):
        # Un historique écrit avant les détentions : le deck né chez A,
        # passé chez B par un déplacement, et un événement au poste de C,
        # qui ne l'a jamais déclaré dans un état. Seuls la création et le
        # déplacement datent une détention : C n'en reçoit aucune.
        self._lend_to_b()
        with freeze_time(DAY_BACK):
            self.Service.report(
                self.token_c,
                {
                    "protocol": "1.0",
                    "state": {
                        "os": {"name": "Debian GNU/Linux"},
                        "service_state": "active",
                        "decks": [],
                    },
                    "events": [self._event("unplugged", datetime(2000, 1, 1))],
                    "lost_events": 0,
                },
            )
        self._report(
            self.token_b, DAY_BACK.replace(hour=12), kinds=["plugged"]
        )
        device = self._device()
        holdings = self._backfill_from_scratch(device)
        self.assertEqual(
            {(h.user_id, h.since) for h in holdings},
            {(self.user_a, DAY_A), (self.user_b, DAY_B)},
        )
        at_c = device.event_ids.filtered(
            lambda e: e.workstation_id.user_id == self.user_c
        )
        self.assertEqual(self._seen(self.user_c), at_c)
        # L'événement de C est daté d'avant la détention de A.
        self.assertEqual(self._seen(self.user_a), device.event_ids - at_c)
        self.Holding._backfill()
        self.assertEqual(
            self.Holding.search_count([("device_id", "=", device.id)]), 2
        )

    def test_the_backfill_dates_a_creator_without_events(self):
        # A n'a déclaré le deck que dans son état, sans aucun événement,
        # puis le deck est passé chez B : la création du deck date la
        # détention de A, et A garde tout l'historique.
        self._report(self.token_a, DAY_A)
        self._report(self.token_b, DAY_B, kinds=["plugged"])
        device = self._device()
        self.assertFalse(
            device.event_ids.filtered(
                lambda e: e.workstation_id.user_id == self.user_a
            )
        )
        holdings = self._backfill_from_scratch(device)
        self.assertEqual(
            {(h.user_id, h.since) for h in holdings},
            {(self.user_a, DAY_A), (self.user_b, DAY_B)},
        )
        self.assertEqual(len(device.event_ids), 2)
        self.assertEqual(self._seen(self.user_a), device.event_ids)
