# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib
import json

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestStreamdeckConfig(TransactionCase):
    """La configuration voulue d'un poste : le schéma des quatre clés,
    les couches profil < modèle de deck < poste, les verrous et
    l'empreinte.

    Les couches sont écrites en superutilisateur ; les droits de chacun
    sont dans `test_streamdeck_config_access.py`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Schema = cls.env["streamdeck.config.schema"]
        cls.Profile = cls.env["streamdeck.config.profile"]
        cls.Model = cls.env["streamdeck.config.model"]
        cls.Line = cls.env["streamdeck.config.line"]
        cls.user = new_test_user(
            cls.env,
            login="zz_sd_cfg_e",
            name="Employee E",
            groups="base.group_user",
        )
        cls.ws = cls.env["streamdeck.workstation"].create(
            {
                "user_id": cls.user.id,
                "name": "host-e",
                "fingerprint": hashlib.sha256(b"cfg-e").hexdigest(),
            }
        )

    # -- helpers ---------------------------------------------------------

    def _deck(self, serial, product, connected=True):
        return self.env["streamdeck.device"].create(
            {
                "key": "sn:%s" % serial,
                "serial": serial,
                "usb_product_id": product,
                "workstation_id": self.ws.id,
                "connected": connected,
            }
        )

    def _line(self, parent, key, value, locked=False):
        field = {
            "streamdeck.config.profile": "profile_id",
            "streamdeck.config.model": "model_id",
            "streamdeck.workstation": "workstation_id",
        }[parent._name]
        return self.Line.create(
            {
                field: parent.id,
                "key": key,
                "value": json.dumps(value),
                "locked": locked,
            }
        )

    def _profile(self, name="Profile"):
        profile = self.Profile.create({"name": name})
        self.ws.config_profile_id = profile
        return profile

    # -- tests -----------------------------------------------------------

    def test_each_key_accepts_its_values_and_refuses_others(self):
        self.assertEqual(
            self.Schema.KEYS,
            ("deck_program", "plugins_off", "session_refresh_sec", "games"),
        )
        longest = "a" + "b" * 63
        sixty_four = ["p%d" % number for number in range(64)]
        for key, value, expected in (
            ("deck_program", "tiler", "tiler"),
            ("deck_program", "controller", "controller"),
            ("deck_program", "none", "none"),
            ("plugins_off", [], []),
            ("plugins_off", ["sound"], ["sound"]),
            (
                "plugins_off",
                ["timers", "a_2", longest],
                ["timers", "a_2", longest],
            ),
            ("plugins_off", ["b", "a", "b"], ["b", "a"]),
            ("plugins_off", sixty_four, sixty_four),
            # La borne compte les identifiants, répétitions retirées.
            ("plugins_off", sixty_four + ["p0"], sixty_four),
            ("session_refresh_sec", 0.5, 0.5),
            ("session_refresh_sec", 60, 60.0),
            ("session_refresh_sec", 2, 2.0),
            ("games", "on", "on"),
            ("games", "off", "off"),
        ):
            with self.subTest(key=key, value=value):
                normalised = self.Schema._validate(key, value)
                self.assertEqual(normalised, expected)
                self.assertIs(type(normalised), type(expected))

        for key, value in (
            ("deck_program", "Tiler"),
            ("deck_program", "/bin/sh"),
            ("deck_program", ""),
            ("deck_program", None),
            ("deck_program", 1),
            ("plugins_off", "sound"),
            ("plugins_off", ["a-b"]),
            ("plugins_off", ["Sound"]),
            ("plugins_off", ["1a"]),
            ("plugins_off", [""]),
            ("plugins_off", ["a" + "b" * 64]),
            ("plugins_off", [1]),
            ("plugins_off", sixty_four + ["p64"]),
            ("plugins_off", None),
            ("session_refresh_sec", 0.4),
            ("session_refresh_sec", 60.1),
            ("session_refresh_sec", "2"),
            ("session_refresh_sec", True),
            ("session_refresh_sec", None),
            ("session_refresh_sec", float("nan")),
            ("session_refresh_sec", float("inf")),
            ("session_refresh_sec", 10**400),
            ("session_refresh_sec", -(10**400)),
            ("games", "On"),
            ("games", "yes"),
            ("games", True),
            ("key_layouts", {}),
            ("DECK_PROGRAM", "tiler"),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValidationError):
                    self.Schema._validate(key, value)

    def test_a_value_is_stored_as_canonical_json(self):
        profile = self._profile()
        for key, typed, stored in (
            ("deck_program", '"tiler"', '"tiler"'),
            ("deck_program", " controller ", '"controller"'),
            ("plugins_off", '[ "sound" , "timers" ]', '["sound","timers"]'),
            ("plugins_off", "sound, timers,sound", '["sound","timers"]'),
            ("plugins_off", "", "[]"),
            ("session_refresh_sec", "2", "2.0"),
            ("session_refresh_sec", " 0.5", "0.5"),
            ("games", "off", '"off"'),
        ):
            with self.subTest(key=key, typed=typed):
                line = self.Line.create(
                    {"profile_id": profile.id, "key": key, "value": typed}
                )
                self.assertEqual(line.value, stored)
                line.unlink()

        line = self._line(profile, "games", "on")
        line.write({"value": "off"})
        self.assertEqual(line.value, '"off"')
        for key, typed in (
            ("deck_program", "/bin/sh"),
            ("session_refresh_sec", "fast"),
            ("session_refresh_sec", "1" * 400),
            ("plugins_off", "a-b"),
        ):
            with self.subTest(key=key, typed=typed):
                with self.assertRaises(ValidationError):
                    self.Line.create(
                        {"profile_id": profile.id, "key": key, "value": typed}
                    )
        with self.assertRaises(ValidationError):
            line.write({"value": "maybe"})

    def test_a_line_that_changes_only_its_key_keeps_to_the_schema(self):
        # Sans `value` dans l'écriture, la valeur en place est jugée sous
        # la nouvelle clé : « on » n'est pas un programme du deck.
        profile = self._profile()
        for label, line, user in (
            ("profile", self._line(profile, "games", "on"), self.env.user),
            (
                "workstation",
                self.Line.with_user(self.user).create(
                    {
                        "workstation_id": self.ws.id,
                        "key": "games",
                        "value": "on",
                    }
                ),
                self.user,
            ),
        ):
            with self.subTest(layer=label):
                with self.assertRaises(ValidationError):
                    with self.cr.savepoint():
                        line.with_user(user).write({"key": "deck_program"})
                self.assertEqual(line.key, "games")
                self.assertEqual(line.value, '"on"')

    def test_profile_then_model_then_workstation(self):
        profile = self._profile()
        self._line(profile, "deck_program", "tiler")
        self._line(profile, "games", "on")
        self._line(profile, "session_refresh_sec", 5)
        model = self.Model.create({"usb_product_id": "0084"})
        self._line(model, "games", "off")
        self._line(model, "session_refresh_sec", 3)
        self._line(self.ws, "session_refresh_sec", 2)

        # Sans deck connecté de ce modèle, sa couche ne compte pas.
        self._deck("SN-OFF", "0084", connected=False)
        self.assertEqual(
            self.Schema._effective(self.ws),
            {
                "settings": {
                    "deck_program": "tiler",
                    "session_refresh_sec": 2.0,
                    "games": "on",
                },
                "locked": [],
                "sources": {
                    "deck_program": "profile",
                    "session_refresh_sec": "workstation",
                    "games": "profile",
                },
            },
        )

        self._deck("SN-ON", "0084")
        effective = self.Schema._effective(self.ws)
        self.assertEqual(
            effective["settings"],
            {
                "deck_program": "tiler",
                "session_refresh_sec": 2.0,
                "games": "off",
            },
        )
        self.assertEqual(
            effective["sources"],
            {
                "deck_program": "profile",
                "session_refresh_sec": "workstation",
                "games": "model",
            },
        )
        # Une clé qu'aucune couche ne fixe n'est pas gérée.
        self.assertNotIn("plugins_off", effective["settings"])
        self.assertEqual(
            list(effective["settings"]),
            ["deck_program", "session_refresh_sec", "games"],
        )

        # Un profil archivé ne compte plus.
        profile.active = False
        self.assertEqual(
            self.Schema._effective(self.ws)["settings"],
            {"session_refresh_sec": 2.0, "games": "off"},
        )
        # Un poste sans couche n'a rien de géré.
        self.assertEqual(
            self.Schema._effective(self.env["streamdeck.workstation"]),
            {"settings": {}, "locked": [], "sources": {}},
        )

    def test_a_profile_lock_ignores_model_and_workstation(self):
        profile = self._profile()
        self._line(profile, "games", "on", locked=True)
        model = self.Model.create({"usb_product_id": "0084"})
        self._line(model, "games", "off", locked=True)
        self._line(self.ws, "games", "off")
        self._deck("SN-1", "0084")
        effective = self.Schema._effective(self.ws)
        self.assertEqual(effective["settings"], {"games": "on"})
        self.assertEqual(effective["locked"], ["games"])
        self.assertEqual(effective["sources"], {"games": "profile"})

    def test_a_model_lock_ignores_the_workstation(self):
        profile = self._profile()
        self._line(profile, "session_refresh_sec", 5)
        model = self.Model.create({"usb_product_id": "0084"})
        self._line(model, "session_refresh_sec", 3, locked=True)
        self._line(self.ws, "session_refresh_sec", 2)
        self._line(self.ws, "plugins_off", ["sound"], locked=True)
        self._deck("SN-1", "0084")
        effective = self.Schema._effective(self.ws)
        self.assertEqual(
            effective["settings"],
            {"plugins_off": ["sound"], "session_refresh_sec": 3.0},
        )
        self.assertEqual(
            effective["locked"], ["plugins_off", "session_refresh_sec"]
        )
        self.assertEqual(
            effective["sources"],
            {"plugins_off": "workstation", "session_refresh_sec": "model"},
        )

    def test_two_connected_models_apply_by_product_id(self):
        plus = self.Model.create({"usb_product_id": "0084"})
        xl = self.Model.create({"usb_product_id": "006C"})
        self.assertEqual(xl.usb_product_id, "006c")
        self.assertEqual(xl.name, "Stream Deck XL")
        self._line(plus, "games", "off")
        self._line(xl, "games", "on")
        self._line(plus, "deck_program", "controller")
        self._line(xl, "session_refresh_sec", 4, locked=True)
        self._line(plus, "session_refresh_sec", 9)
        self._deck("SN-PLUS", "0084")
        self._deck("SN-XL", "006c")
        effective = self.Schema._effective(self.ws)
        # 006c passe avant 0084 : la plus grande l'emporte, sauf derrière
        # un verrou posé plus tôt.
        self.assertEqual(
            effective["settings"],
            {
                "deck_program": "controller",
                "session_refresh_sec": 4.0,
                "games": "off",
            },
        )
        self.assertEqual(effective["locked"], ["session_refresh_sec"])

        # Un modèle sans couche ne change rien.
        self._deck("SN-MINI", "0063")
        self.assertEqual(self.Schema._effective(self.ws), effective)

        with self.assertRaises(ValidationError):
            self.Model.create({"usb_product_id": "84"})
        with self.assertRaises(ValidationError):
            self.Model.create({"usb_product_id": "zz84"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.Model.create({"usb_product_id": "0084"})

    def test_a_line_has_exactly_one_parent(self):
        profile = self._profile()
        model = self.Model.create({"usb_product_id": "0084"})
        for parents in (
            {},
            {"profile_id": profile.id, "model_id": model.id},
            {"profile_id": profile.id, "workstation_id": self.ws.id},
            {"model_id": model.id, "workstation_id": self.ws.id},
        ):
            with self.subTest(parents=sorted(parents)):
                with self.assertRaises(ValidationError):
                    self.Line.create(dict(parents, key="games", value='"on"'))
        line = self._line(profile, "games", "on")
        with self.assertRaises(ValidationError):
            line.write({"model_id": model.id})

        # Une clé par parent.
        for parent in (profile, model, self.ws):
            with self.subTest(parent=parent._name):
                if parent._name != profile._name:
                    self._line(parent, "games", "on")
                with mute_logger("odoo.sql_db"), self.assertRaises(
                    IntegrityError
                ):
                    with self.cr.savepoint():
                        self._line(parent, "games", "off")

    def test_hash_is_stable_and_order_free(self):
        settings = {
            "games": "on",
            "deck_program": "tiler",
            "plugins_off": ["sound"],
            "session_refresh_sec": 2.0,
        }
        canonical = (
            '{"deck_program":"tiler","games":"on",'
            '"plugins_off":["sound"],"session_refresh_sec":2.0}'
        )
        expected = hashlib.sha256(canonical.encode()).hexdigest()
        self.assertEqual(self.Schema._hash(settings), expected)
        reordered = dict(reversed(list(settings.items())))
        self.assertEqual(self.Schema._hash(reordered), expected)
        self.assertNotEqual(
            self.Schema._hash(dict(settings, games="off")), expected
        )
        self.assertRegex(self.Schema._hash({}), "^[0-9a-f]{64}$")
