# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"


@tagged("post_install", "-at_install")
class TestStreamdeckConfigAccess(TransactionCase):
    """Qui lit et qui écrit les couches de configuration.

    A et B sont deux employés, M le gestionnaire. Le gestionnaire écrit
    tout ; l'employé lit les profils « au choix » et celui de ses postes,
    toutes les couches modèle, et surcharge sur ses postes les clés
    qu'aucune couche ne verrouille, sans jamais poser `locked` ni
    `source`. Il choisit pour ses postes un profil « au choix », jamais
    à la place d'un profil que le gestionnaire a imposé.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Profile = cls.env["streamdeck.config.profile"]
        cls.Model = cls.env["streamdeck.config.model"]
        cls.Line = cls.env["streamdeck.config.line"]
        cls.Workstation = cls.env["streamdeck.workstation"]
        cls.user_a = new_test_user(
            cls.env,
            login="zz_sd_cfg_a",
            name="Employee A",
            groups="base.group_user",
        )
        cls.user_b = new_test_user(
            cls.env,
            login="zz_sd_cfg_b",
            name="Employee B",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_cfg_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        cls.ws_a = cls._workstation(cls.user_a, "host-a")
        cls.ws_b = cls._workstation(cls.user_b, "host-b")
        cls.selectable = cls.Profile.create(
            {"name": "Selectable", "selectable": True}
        )
        cls.selectable_2 = cls.Profile.create(
            {"name": "Selectable 2", "selectable": True}
        )
        cls.fixed = cls.Profile.create({"name": "Fixed"})
        cls.other = cls.Profile.create({"name": "Other"})
        cls.ws_b.config_profile_id = cls.other
        cls.model = cls.Model.create({"usb_product_id": "0084"})

    @classmethod
    def _workstation(cls, user, name):
        return cls.Workstation.create(
            {
                "user_id": user.id,
                "name": name,
                "fingerprint": hashlib.sha256(name.encode()).hexdigest(),
            }
        )

    def _line(self, values, user=None):
        Line = self.Line.with_user(user) if user else self.Line
        return Line.create(values)

    def _connect(self, workstation, product="0084"):
        self.env["streamdeck.device"].create(
            {
                "key": "sn:SN-%s" % workstation.name,
                "serial": "SN-%s" % workstation.name,
                "usb_product_id": product,
                "workstation_id": workstation.id,
                "connected": True,
            }
        )

    # -- the manager -----------------------------------------------------

    def test_the_manager_writes_every_layer(self):
        Profile = self.Profile.with_user(self.manager)
        profile = Profile.create({"name": "M's", "selectable": True})
        profile.write({"name": "M's profile", "selectable": False})
        model = self.Model.with_user(self.manager).create(
            {"usb_product_id": "006c"}
        )
        lines = self.Line.browse()
        for parent in (
            {"profile_id": profile.id},
            {"model_id": model.id},
            {"workstation_id": self.ws_b.id},
        ):
            line = self._line(
                dict(parent, key="games", value='"on"', locked=True),
                user=self.manager,
            )
            self.assertEqual(line.source, "manager")
            line.write({"value": '"off"', "locked": False})
            lines |= line
        self.assertEqual(set(lines.mapped("value")), {'"off"'})
        lines.unlink()
        profile.unlink()
        model.unlink()

    def test_the_manager_assigns_any_profile(self):
        ws = self.ws_a.with_user(self.manager)
        for profile in (self.fixed, self.selectable, self.fixed):
            ws.write({"config_profile_id": profile.id})
            self.assertEqual(self.ws_a.config_profile_id, profile)
        ws.write({"config_profile_id": False})
        self.assertFalse(self.ws_a.config_profile_id)

    # -- the employee's overrides ----------------------------------------

    def test_an_employee_overrides_a_free_key_of_their_workstation(self):
        line = self._line(
            {"workstation_id": self.ws_a.id, "key": "games", "value": "off"},
            user=self.user_a,
        )
        self.assertEqual(line.source, "employee")
        self.assertEqual(line.value, '"off"')
        line.write({"value": "on"})
        self.assertEqual(line.value, '"on"')
        line.unlink()

        # Une ligne adoptée du poste devient celle de l'employé qui la
        # change.
        adopted = self._line(
            {
                "workstation_id": self.ws_a.id,
                "key": "session_refresh_sec",
                "value": "5",
                "source": "local",
            }
        )
        adopted.with_user(self.user_a).write({"value": "2"})
        self.assertEqual(adopted.source, "employee")

        # Par le formulaire du poste aussi.
        self.ws_a.with_user(self.user_a).write(
            {
                "config_line_ids": [
                    Command.create({"key": "deck_program", "value": "tiler"})
                ]
            }
        )
        line = self.ws_a.config_line_ids.filtered(
            lambda line: line.key == "deck_program"
        )
        self.assertEqual(line.value, '"tiler"')
        self.assertEqual(line.source, "employee")

    def test_an_employee_cannot_override_a_locked_key(self):
        self.ws_a.config_profile_id = self.selectable
        self._line(
            {
                "profile_id": self.selectable.id,
                "key": "games",
                "value": "on",
                "locked": True,
            }
        )
        self._line(
            {
                "model_id": self.model.id,
                "key": "session_refresh_sec",
                "value": "3",
                "locked": True,
            }
        )
        self._connect(self.ws_a)
        locked_here = self._line(
            {
                "workstation_id": self.ws_a.id,
                "key": "deck_program",
                "value": "tiler",
                "locked": True,
            }
        )
        free = self._line(
            {
                "workstation_id": self.ws_a.id,
                "key": "plugins_off",
                "value": "",
            },
            user=self.user_a,
        )
        for layer, key, value in (
            ("profile", "games", "off"),
            ("model", "session_refresh_sec", "2"),
            ("workstation", "deck_program", "controller"),
        ):
            with self.subTest(layer=layer):
                with self.assertRaises(AccessError):
                    with self.cr.savepoint():
                        self._line(
                            {
                                "workstation_id": self.ws_a.id,
                                "key": key,
                                "value": value,
                            },
                            user=self.user_a,
                        )
                with self.assertRaises(AccessError):
                    with self.cr.savepoint():
                        free.with_user(self.user_a).write({"key": key})
                with self.assertRaises(AccessError):
                    with self.cr.savepoint():
                        self.ws_a.with_user(self.user_a).write(
                            {
                                "config_line_ids": [
                                    Command.create(
                                        {"key": key, "value": value}
                                    )
                                ]
                            }
                        )
        with self.assertRaises(AccessError):
            locked_here.with_user(self.user_a).write({"value": "controller"})
        with self.assertRaises(AccessError):
            locked_here.with_user(self.user_a).unlink()
        self.assertEqual(locked_here.value, '"tiler"')
        self.assertTrue(locked_here.exists())
        self.assertEqual(free.key, "plugins_off")

    def test_an_employee_cannot_set_locked_or_source(self):
        values = {
            "workstation_id": self.ws_a.id,
            "key": "games",
            "value": "on",
        }
        for extra in (
            {"locked": True},
            {"source": "manager"},
            {"source": "local"},
        ):
            with self.subTest(extra=extra):
                with self.assertRaises(AccessError):
                    self._line(dict(values, **extra), user=self.user_a)
        line = self._line(values, user=self.user_a)
        for extra in (
            {"locked": True},
            {"source": "manager"},
            {"source": "local"},
        ):
            with self.subTest(write=extra):
                with self.assertRaises(AccessError):
                    line.with_user(self.user_a).write(extra)
        self.assertFalse(line.locked)
        self.assertEqual(line.source, "employee")

    def test_an_employee_cannot_touch_another_workstation(self):
        theirs = self._line(
            {"workstation_id": self.ws_b.id, "key": "games", "value": "on"}
        )
        mine = self._line(
            {"workstation_id": self.ws_a.id, "key": "games", "value": "on"},
            user=self.user_a,
        )
        as_a = theirs.with_user(self.user_a)
        with self.assertRaises(AccessError):
            as_a.read(["value"])
        with self.assertRaises(AccessError):
            as_a.write({"value": "off"})
        with self.assertRaises(AccessError):
            as_a.unlink()
        for parent in (
            {"workstation_id": self.ws_b.id},
            {"profile_id": self.selectable.id},
            {"model_id": self.model.id},
        ):
            with self.subTest(create=sorted(parent)):
                with self.assertRaises(AccessError):
                    self._line(
                        dict(parent, key="deck_program", value="none"),
                        user=self.user_a,
                    )
        for move in (
            {"workstation_id": self.ws_b.id},
            {"workstation_id": False, "profile_id": self.selectable.id},
            {"workstation_id": False, "model_id": self.model.id},
        ):
            with self.subTest(move=sorted(move)):
                with self.assertRaises(AccessError):
                    mine.with_user(self.user_a).write(move)
        with self.assertRaises(AccessError):
            self.ws_b.with_user(self.user_a).write(
                {
                    "config_line_ids": [
                        Command.create(
                            {"key": "deck_program", "value": "none"}
                        )
                    ]
                }
            )
        self.assertEqual(theirs.value, '"on"')
        self.assertEqual(mine.workstation_id, self.ws_a)
        self.assertEqual(self.ws_b.config_line_ids, theirs)

    # -- the employee's profile ------------------------------------------

    def test_an_employee_picks_a_selectable_profile_for_their_workstation(
        self,
    ):
        ws = self.ws_a.with_user(self.user_a)
        ws.write({"config_profile_id": self.selectable.id})
        self.assertEqual(self.ws_a.config_profile_id, self.selectable)
        ws.write({"config_profile_id": self.selectable_2.id})
        self.assertEqual(self.ws_a.config_profile_id, self.selectable_2)

    def test_an_employee_cannot_pick_a_non_selectable_profile(self):
        with self.assertRaises(AccessError):
            self.ws_a.with_user(self.user_a).write(
                {"config_profile_id": self.fixed.id}
            )
        self.assertFalse(self.ws_a.config_profile_id)

    def test_an_employee_cannot_replace_a_manager_assigned_profile(self):
        self.ws_a.with_user(self.manager).write(
            {"config_profile_id": self.fixed.id}
        )
        with self.assertRaises(AccessError):
            self.ws_a.with_user(self.user_a).write(
                {"config_profile_id": self.selectable.id}
            )
        self.assertEqual(self.ws_a.config_profile_id, self.fixed)

        # Un profil « au choix » posé par le gestionnaire, lui, se change.
        self.ws_a.with_user(self.manager).write(
            {"config_profile_id": self.selectable.id}
        )
        self.ws_a.with_user(self.user_a).write(
            {"config_profile_id": self.selectable_2.id}
        )
        self.assertEqual(self.ws_a.config_profile_id, self.selectable_2)

    def test_an_employee_cannot_clear_the_profile(self):
        ws = self.ws_a.with_user(self.user_a)
        ws.write({"config_profile_id": self.selectable.id})
        with self.assertRaises(AccessError):
            ws.write({"config_profile_id": False})
        self.assertEqual(self.ws_a.config_profile_id, self.selectable)

    def test_an_employee_cannot_pick_for_another_workstation(self):
        self.ws_b.config_profile_id = self.selectable
        with self.assertRaises(AccessError):
            self.ws_b.with_user(self.user_a).write(
                {"config_profile_id": self.selectable_2.id}
            )
        self.assertEqual(self.ws_b.config_profile_id, self.selectable)

    def test_an_employee_cannot_mark_a_profile_selectable(self):
        with self.assertRaises(AccessError):
            self.fixed.with_user(self.user_a).write({"selectable": True})
        with self.assertRaises(AccessError):
            self.Profile.with_user(self.user_a).create(
                {"name": "Mine", "selectable": True}
            )
        with self.assertRaises(AccessError):
            self.model.with_user(self.user_a).write({"usb_product_id": "006c"})
        self.assertFalse(self.fixed.selectable)

    def test_an_employee_cannot_write_config_first_choice(self):
        for user in (self.user_a, self.manager):
            for values in (
                {"config_first_choice": "keep_local"},
                {"config_state": "applied"},
                {"config_revision": 7},
                {"config_hash": "0" * 64},
                {"config_applied": "{}"},
            ):
                with self.subTest(user=user.login, values=sorted(values)):
                    with self.assertRaises(AccessError):
                        self.ws_a.with_user(user).write(values)
        self.assertFalse(self.ws_a.config_first_choice)
        self.assertEqual(self.ws_a.config_state, "unmanaged")

    def test_an_employee_reads_selectable_and_own_profiles_and_the_model_layers_only(  # noqa: E501
        self,
    ):
        self.ws_a.config_profile_id = self.fixed
        lines = {}
        for name, parent in (
            ("selectable", {"profile_id": self.selectable.id}),
            ("fixed", {"profile_id": self.fixed.id}),
            ("other", {"profile_id": self.other.id}),
            ("model", {"model_id": self.model.id}),
            ("ws_a", {"workstation_id": self.ws_a.id}),
            ("ws_b", {"workstation_id": self.ws_b.id}),
        ):
            lines[name] = self._line(dict(parent, key="games", value="on"))

        profiles = self.Profile.with_user(self.user_a).search([])
        self.assertEqual(
            profiles, self.selectable | self.selectable_2 | self.fixed
        )
        with self.assertRaises(AccessError):
            self.other.with_user(self.user_a).read(["name"])
        self.assertIn(self.model, self.Model.with_user(self.user_a).search([]))
        seen = self.Line.with_user(self.user_a).search([])
        self.assertEqual(
            seen,
            lines["selectable"]
            | lines["fixed"]
            | lines["model"]
            | lines["ws_a"],
        )
        for name in ("other", "ws_b"):
            with self.subTest(line=name):
                with self.assertRaises(AccessError):
                    lines[name].with_user(self.user_a).read(["value"])
