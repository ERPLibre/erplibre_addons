# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"


@tagged("post_install", "-at_install")
class TestStreamdeckAccess(TransactionCase):
    """Qui lit et qui écrit l'inventaire des postes, des decks et des
    événements.

    A et B sont deux employés, M le gestionnaire. Les enregistrements sont
    créés en superutilisateur, comme le font les routes ; chaque test lit
    ensuite par `with_user` pour passer par les droits et les règles.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Workstation = cls.env["streamdeck.workstation"]
        cls.Device = cls.env["streamdeck.device"]
        cls.Event = cls.env["streamdeck.event"]
        cls.user_a = new_test_user(
            cls.env,
            login="zz_sd_a",
            name="Employee A",
            groups="base.group_user",
        )
        cls.user_b = new_test_user(
            cls.env,
            login="zz_sd_b",
            name="Employee B",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        cls.ws_a = cls._workstation(cls.user_a, "host-a", "a")
        cls.ws_b = cls._workstation(cls.user_b, "host-b", "b")
        cls._uuid = 0

    @classmethod
    def _workstation(cls, user, name, seed, token="secret-token"):
        return cls.Workstation.create(
            {
                "user_id": user.id,
                "name": name,
                "fingerprint": hashlib.sha256(seed.encode()).hexdigest(),
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            }
        )

    def _device(self, serial, workstation, product="0084"):
        return self.Device.create(
            {
                "key": serial,
                "serial": serial,
                "usb_product_id": product,
                "workstation_id": workstation.id,
                "connected": True,
            }
        )

    def _event(self, kind, workstation, device=None):
        type(self)._uuid += 1
        return self.Event.create(
            {
                "uuid": "00000000-0000-4000-8000-%012d" % self._uuid,
                "kind": kind,
                "at": "2026-01-01 10:00:00",
                "received_at": "2026-01-01 10:00:01",
                "device_id": device.id if device else False,
                "workstation_id": workstation.id,
                "workstation_name": workstation.name,
                "employee_name": workstation.user_id.name,
            }
        )

    def test_an_employee_reads_only_their_workstations(self):
        ws_a2 = self._workstation(self.user_a, "host-a2", "a2")
        seen = self.Workstation.with_user(self.user_a).search([])
        self.assertEqual(seen, self.ws_a | ws_a2)
        with self.assertRaises(AccessError):
            self.ws_b.with_user(self.user_a).read(["name"])

    def test_a_deck_lent_keeps_its_whole_history_for_the_lender(self):
        deck = self._device("SN-LENT", self.ws_b)
        events = (
            self._event("plugged", self.ws_a, deck)
            | self._event("unplugged", self.ws_a, deck)
            | self._event("plugged", self.ws_b, deck)
        )
        for user in (self.user_a, self.user_b):
            seen_deck = self.Device.with_user(user).search(
                [("id", "=", deck.id)]
            )
            self.assertEqual(seen_deck, deck)
            seen = self.Event.with_user(user).search(
                [("device_id", "=", deck.id)]
            )
            self.assertEqual(seen, events)
        at_b = events[2].with_user(self.user_a)
        values = at_b.read(
            ["workstation_name", "employee_name", "workstation_id"]
        )[0]
        self.assertEqual(values["workstation_name"], "host-b")
        self.assertEqual(values["employee_name"], "Employee B")
        # La fiche du deck se lit, mais le poste qui le tient reste fermé.
        with self.assertRaises(AccessError):
            self.ws_b.with_user(self.user_a).read(["name"])

    def test_the_current_holder_reads_the_deck_history(self):
        # Le deck tenu par le poste de B n'a d'événement qu'au poste de A :
        # B le lit par son poste actuel, pas par l'historique.
        deck = self._device("SN-HELD", self.ws_b)
        events = self._event("plugged", self.ws_a, deck) | self._event(
            "unplugged", self.ws_a, deck
        )
        self.assertEqual(
            self.Device.with_user(self.user_b).search([("id", "=", deck.id)]),
            deck,
        )
        seen = self.Event.with_user(self.user_b).search(
            [("device_id", "=", deck.id)]
        )
        self.assertEqual(seen, events)

    def test_an_employee_reads_the_service_history_of_their_workstation(
        self,
    ):
        # Un changement d'état du service ne porte aucun deck : seule la
        # branche des postes de l'employé, dans la règle des événements,
        # le montre.
        service = self._event("service_changed", self.ws_a)
        seen = self.Event.with_user(self.user_a).search(
            [("workstation_id", "=", self.ws_a.id)]
        )
        self.assertEqual(seen, service)
        self.assertEqual(
            service.with_user(self.user_a).read(["kind"])[0]["kind"],
            "service_changed",
        )

    def test_an_employee_never_reads_a_deck_their_workstations_never_had(
        self,
    ):
        deck = self._device("SN-B-ONLY", self.ws_b)
        plugged = self._event("plugged", self.ws_b, deck)
        service = self._event("service_changed", self.ws_b)
        as_a = self.user_a
        self.assertFalse(
            self.Device.with_user(as_a).search([("id", "=", deck.id)])
        )
        self.assertFalse(
            self.Event.with_user(as_a).search(
                [("id", "in", (plugged | service).ids)]
            )
        )
        with self.assertRaises(AccessError):
            deck.with_user(as_a).read(["serial"])
        with self.assertRaises(AccessError):
            service.with_user(as_a).read(["kind"])

    def test_the_manager_reads_the_whole_fleet(self):
        deck_a = self._device("SN-FLEET-A", self.ws_a)
        deck_b = self._device("SN-FLEET-B", self.ws_b)
        events = self._event("plugged", self.ws_a, deck_a) | self._event(
            "service_changed", self.ws_b
        )
        as_m = self.manager
        self.assertEqual(
            self.Workstation.with_user(as_m).search(
                [("id", "in", (self.ws_a | self.ws_b).ids)]
            ),
            self.ws_a | self.ws_b,
        )
        self.assertEqual(
            self.Device.with_user(as_m).search(
                [("id", "in", (deck_a | deck_b).ids)]
            ),
            deck_a | deck_b,
        )
        self.assertEqual(
            self.Event.with_user(as_m).search([("id", "in", events.ids)]),
            events,
        )
        # Le gestionnaire archive le poste d'un autre, qu'il voit encore.
        self.ws_b.with_user(as_m).write({"active": False})
        self.assertIn(
            self.ws_b,
            self.Workstation.with_user(as_m)
            .with_context(active_test=False)
            .search([]),
        )

    def test_nobody_creates_inventory_by_hand(self):
        deck = self._device("SN-HAND", self.ws_a)
        event = self._event("plugged", self.ws_a, deck)
        values = {
            "streamdeck.workstation": {
                "user_id": self.user_a.id,
                "name": "by-hand",
                "fingerprint": "f" * 64,
            },
            "streamdeck.device": {"key": "SN-BY-HAND"},
            "streamdeck.event": {
                "uuid": "by-hand",
                "kind": "plugged",
                "workstation_id": self.ws_a.id,
            },
            "streamdeck.pairing.code": {
                "code": "ABCDEFGH",
                "user_id": self.user_a.id,
            },
        }
        existing = {
            "streamdeck.workstation": self.ws_a,
            "streamdeck.device": deck,
            "streamdeck.event": event,
        }
        for user in (self.user_a, self.manager):
            for model, vals in values.items():
                with self.subTest(user=user.login, model=model):
                    with self.assertRaises(AccessError):
                        self.env[model].with_user(user).create(vals)
            for model, record in existing.items():
                with self.subTest(user=user.login, model=model, op="unlink"):
                    with self.assertRaises(AccessError):
                        record.with_user(user).unlink()
            with self.subTest(user=user.login, model="pairing", op="read"):
                with self.assertRaises(AccessError):
                    self.env["streamdeck.pairing.code"].with_user(user).search(
                        []
                    )
            for record, vals in (
                (deck, {"serial": "x"}),
                (event, {"kind": "unplugged"}),
            ):
                with self.subTest(user=user.login, model=record._name):
                    with self.assertRaises(AccessError):
                        record.with_user(user).write(vals)

    def test_an_employee_only_renames_their_workstation(self):
        ws = self.ws_a.with_user(self.user_a)
        ws.write({"name": "renamed"})
        self.assertEqual(self.ws_a.name, "renamed")
        # Le changement d'employé vient en dernier : accepté, il fermerait
        # le poste à A et masquerait les cas suivants.
        for vals in (
            {"fingerprint": "0" * 64},
            {"os_name": "invented"},
            {"active": False},
            {"user_id": self.user_b.id},
        ):
            with self.subTest(vals=vals):
                with self.assertRaises(AccessError):
                    ws.write(vals)
        with self.assertRaises(AccessError):
            self.ws_b.with_user(self.user_a).write({"name": "taken"})

    def test_the_manager_only_renames_and_archives_a_workstation(self):
        ws = self.ws_b.with_user(self.manager)
        ws.write({"name": "renamed-by-m"})
        self.assertEqual(self.ws_b.name, "renamed-by-m")
        for vals in (
            {"fingerprint": "0" * 64},
            {"os_name": "invented"},
            {"token_active": False},
            {"user_id": self.user_a.id},
        ):
            with self.subTest(vals=vals):
                with self.assertRaises(AccessError):
                    ws.write(vals)
        self.assertEqual(self.ws_b.user_id, self.user_b)

    def test_an_employee_revokes_their_own_token_only(self):
        self.ws_a.with_user(self.user_a).action_revoke_token()
        self.assertFalse(self.ws_a.token_hash)
        self.assertFalse(self.ws_a.token_active)
        self.assertTrue(self.ws_b.token_hash)
        with self.assertRaises(AccessError):
            self.ws_b.with_user(self.user_a).action_revoke_token()
        self.assertTrue(self.ws_b.token_hash)
        self.ws_b.with_user(self.manager).action_revoke_token()
        self.assertFalse(self.ws_b.token_hash)

    def test_archiving_a_workstation_revokes_its_token(self):
        self.ws_a.with_user(self.manager).write({"active": False})
        self.assertFalse(self.ws_a.active)
        self.assertFalse(self.ws_a.token_hash)

    def test_archiving_an_employee_archives_workstations_and_revokes_tokens(
        self,
    ):
        ws_a2 = self._workstation(self.user_a, "host-a2", "a2")
        deck = self._device("SN-LEAVER", self.ws_a)
        event = self._event("plugged", self.ws_a, deck)
        self.user_a.action_archive()
        for ws in self.ws_a | ws_a2:
            self.assertFalse(ws.active)
            self.assertFalse(ws.token_hash)
        self.assertTrue(self.ws_b.active)
        self.assertTrue(self.ws_b.token_hash)
        # Le gestionnaire garde le poste, son deck et son historique.
        as_m = self.manager
        self.assertIn(
            self.ws_a,
            self.Workstation.with_user(as_m)
            .with_context(active_test=False)
            .search([]),
        )
        self.assertEqual(
            self.Device.with_user(as_m).search([("id", "=", deck.id)]), deck
        )
        self.assertEqual(
            self.Event.with_user(as_m).search([("id", "=", event.id)]), event
        )

    def test_reactivating_employees_leaves_their_workstations_alone(self):
        # Une réactivation en lot touche aussi des employés restés actifs :
        # leurs postes gardent leur jeton. Le poste d'un employé de retour
        # reste archivé jusqu'à sa réinscription.
        self.user_a.action_archive()
        (self.user_a | self.user_b).write({"active": True})
        self.assertTrue(self.user_a.active)
        self.assertTrue(self.ws_b.active)
        self.assertTrue(self.ws_b.token_hash)
        self.assertFalse(self.ws_a.active)
        self.assertFalse(self.ws_a.token_hash)

    def test_the_token_hash_is_not_readable_by_an_employee(self):
        for user in (self.user_a, self.manager):
            with self.subTest(user=user.login):
                ws = self.ws_a.with_user(user)
                with self.assertRaises(AccessError):
                    ws.read(["token_hash"])
                with self.assertRaises(AccessError):
                    self.Workstation.with_user(user).search(
                        [("token_hash", "=like", "a%")]
                    )
                self.assertTrue(ws.read(["token_active"])[0]["token_active"])
        admin = self.env.ref("base.user_admin")
        self.assertTrue(self.ws_a.with_user(admin).token_hash)

    def test_the_model_name_comes_from_the_usb_product_id(self):
        known = self._device("SN-PLUS", self.ws_a, product="0084")
        unknown = self._device("SN-NEW", self.ws_a, product="ffff")
        self.assertEqual(known.model_name, "Stream Deck +")
        self.assertEqual(unknown.model_name, "Stream Deck (ffff)")

    def test_inventory_keys_are_unique(self):
        self._device("SN-UNIQUE", self.ws_a)
        self._event("plugged", self.ws_a)
        cases = (
            (
                "streamdeck.workstation",
                {
                    "user_id": self.user_a.id,
                    "name": "twin",
                    "fingerprint": self.ws_a.fingerprint,
                },
            ),
            ("streamdeck.device", {"key": "SN-UNIQUE"}),
            (
                "streamdeck.event",
                {
                    "uuid": "00000000-0000-4000-8000-%012d" % self._uuid,
                    "kind": "plugged",
                    "workstation_id": self.ws_a.id,
                },
            ),
        )
        for model, vals in cases:
            with self.subTest(model=model), mute_logger("odoo.sql_db"):
                with self.assertRaises(IntegrityError), self.cr.savepoint():
                    self.env[model].create(vals)
                    self.env.flush_all()
        # La même empreinte chez un autre employé est un autre poste.
        self.Workstation.create(
            {
                "user_id": self.user_b.id,
                "name": "same-machine-other-user",
                "fingerprint": self.ws_a.fingerprint,
            }
        )
