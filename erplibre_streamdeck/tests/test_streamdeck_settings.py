# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
PREFIX = "erplibre_streamdeck."

ALERTS = ("service_failed", "silent", "moved", "unplugged")


@tagged("post_install", "-at_install")
class TestStreamdeckSettings(TransactionCase):
    """Paramètres › Stream Deck : les réglages de la surveillance, stockés
    en `ir.config_parameter` sous le préfixe `erplibre_streamdeck.`.

    Par défaut, la surveillance n'écrit que l'historique. Activer les
    activités pour un gestionnaire exige de le nommer, les délais ont un
    plancher, et seule la page Paramètres d'Odoo (administrateurs) les
    écrit.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Settings = cls.env["res.config.settings"]
        cls.Param = cls.env["ir.config_parameter"].sudo()
        cls.employee = new_test_user(
            cls.env,
            login="zz_sd_set_e",
            name="Employee E",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_set_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        cls.admin = new_test_user(
            cls.env,
            login="zz_sd_set_s",
            name="Administrator S",
            groups="base.group_user,base.group_system",
        )

    # -- helpers ---------------------------------------------------------

    def _save(self, **values):
        """Enregistre la page Paramètres comme le bouton « Enregistrer » :
        une fiche créée avec les valeurs courantes, puis `execute()`."""
        settings = self.Settings.create(
            {"streamdeck_%s" % name: value for name, value in values.items()}
        )
        settings.execute()
        return settings

    def _param(self, name):
        return self.Param.get_param(PREFIX + name)

    # -- tests -----------------------------------------------------------

    def test_defaults_are_history_only(self):
        for key in self.Param.search([("key", "=like", PREFIX + "%")]):
            key.unlink()
        settings = self.Settings.create({})
        self.assertFalse(settings.streamdeck_activities_enabled)
        self.assertEqual(settings.streamdeck_activity_recipient, "manager")
        self.assertFalse(settings.streamdeck_activity_manager_id)
        for kind in ALERTS:
            with self.subTest(alert=kind):
                self.assertTrue(settings["streamdeck_alert_%s" % kind])
        self.assertEqual(settings.streamdeck_silent_after_min, 60)
        self.assertEqual(settings.streamdeck_unplugged_after_h, 72)
        self.assertEqual(settings.streamdeck_service_failed_after_min, 10)

        # Enregistrer la page sans rien changer ne les active pas, et les
        # relit telles quelles.
        settings.execute()
        self.assertFalse(self._param("activities_enabled"))
        again = self.Settings.create({})
        self.assertFalse(again.streamdeck_activities_enabled)
        self.assertEqual(again.streamdeck_activity_recipient, "manager")
        for kind in ALERTS:
            self.assertTrue(again["streamdeck_alert_%s" % kind])
        self.assertEqual(
            (
                again.streamdeck_silent_after_min,
                again.streamdeck_unplugged_after_h,
                again.streamdeck_service_failed_after_min,
            ),
            (60, 72, 10),
        )

    def test_enabling_for_the_manager_needs_a_named_manager(self):
        for recipient in ("manager", "both"):
            with self.subTest(recipient=recipient):
                with self.assertRaises(ValidationError):
                    self._save(
                        activities_enabled=True,
                        activity_recipient=recipient,
                        activity_manager_id=False,
                    )
                self.assertFalse(self._param("activities_enabled"))

                self._save(
                    activities_enabled=True,
                    activity_recipient=recipient,
                    activity_manager_id=self.manager.id,
                )
                self.assertEqual(self._param("activities_enabled"), "True")
                self.assertEqual(self._param("activity_recipient"), recipient)
                self.assertEqual(
                    self._param("activity_manager_id"), str(self.manager.id)
                )
                settings = self.Settings.create({})
                self.assertTrue(settings.streamdeck_activities_enabled)
                self.assertEqual(
                    settings.streamdeck_activity_manager_id, self.manager
                )
                self._save(activities_enabled=False)

        # Désactivées, les activités n'ont besoin de personne.
        self._save(
            activities_enabled=False,
            activity_recipient="manager",
            activity_manager_id=False,
        )
        self.assertFalse(self._param("activities_enabled"))
        self.assertFalse(self._param("activity_manager_id"))

    def test_employee_only_needs_no_manager(self):
        self._save(activities_enabled=True, activity_recipient="employee")
        self.assertEqual(self._param("activities_enabled"), "True")
        self.assertEqual(self._param("activity_recipient"), "employee")
        self.assertFalse(self._param("activity_manager_id"))

    def test_silent_delay_below_thirty_minutes_is_refused(self):
        with self.assertRaises(ValidationError):
            self._save(silent_after_min=29)
        self.assertFalse(self._param("silent_after_min"))
        self._save(silent_after_min=30)
        self.assertEqual(self._param("silent_after_min"), "30")
        self.assertEqual(
            self.Settings.create({}).streamdeck_silent_after_min, 30
        )

    def test_delays_below_their_floor_are_refused(self):
        for name, refused, accepted in (
            ("unplugged_after_h", 0, 1),
            ("service_failed_after_min", -1, 0),
        ):
            with self.subTest(delay=name):
                with self.assertRaises(ValidationError):
                    self._save(**{name: refused})
                self._save(**{name: accepted})
                self.assertEqual(self._param(name), str(accepted))
                self.assertEqual(
                    self.Settings.create({})["streamdeck_%s" % name],
                    accepted,
                )

    def test_an_alert_turned_off_stays_off(self):
        # Une case cochée par défaut doit pouvoir se décocher : le
        # paramètre garde « False » au lieu de disparaître, ce qui
        # ramènerait la valeur par défaut.
        for kind in ALERTS:
            with self.subTest(alert=kind):
                self._save(**{"alert_%s" % kind: False})
                self.assertEqual(self._param("alert_%s" % kind), "False")
                settings = self.Settings.create({})
                self.assertFalse(settings["streamdeck_alert_%s" % kind])
                for other in ALERTS:
                    if other != kind:
                        self.assertTrue(
                            settings["streamdeck_alert_%s" % other]
                        )

                self._save(**{"alert_%s" % kind: True})
                self.assertEqual(self._param("alert_%s" % kind), "True")
                self.assertTrue(
                    self.Settings.create({})["streamdeck_alert_%s" % kind]
                )

    def test_the_manager_is_chosen_among_streamdeck_managers(self):
        field = self.Settings._fields["streamdeck_activity_manager_id"]
        candidates = self.env["res.users"].search(
            field.get_domain_list(self.Settings)
        )
        self.assertIn(self.manager, candidates)
        self.assertNotIn(self.employee, candidates)

    def test_only_settings_admins_write_them(self):
        manager_settings = self.Settings.with_user(self.manager)
        with self.assertRaises(AccessError):
            manager_settings.create(
                {"streamdeck_activities_enabled": True}
            ).execute()
        with self.assertRaises(AccessError):
            self.env["ir.config_parameter"].with_user(self.manager).set_param(
                PREFIX + "activities_enabled", "True"
            )
        self.assertFalse(self._param("activities_enabled"))

        # Un administrateur, lui, les écrit par la page Paramètres.
        self.Settings.with_user(self.admin).create(
            {
                "streamdeck_activities_enabled": True,
                "streamdeck_activity_recipient": "employee",
            }
        ).execute()
        self.assertEqual(self._param("activities_enabled"), "True")

    def test_the_settings_page_has_a_stream_deck_section(self):
        arch = self.Settings.get_views([(False, "form")])["views"]["form"][
            "arch"
        ]
        app = etree.fromstring(arch).xpath(
            "//app[@name='erplibre_streamdeck']"
        )
        self.assertEqual(len(app), 1)
        names = set(app[0].xpath(".//field/@name"))
        for name in (
            "activities_enabled",
            "activity_recipient",
            "activity_manager_id",
            "alert_service_failed",
            "alert_silent",
            "alert_moved",
            "alert_unplugged",
            "silent_after_min",
            "unplugged_after_h",
            "service_failed_after_min",
        ):
            self.assertIn("streamdeck_" + name, names)

        action = self.env.ref("erplibre_streamdeck.action_streamdeck_settings")
        self.assertEqual(action.res_model, "res.config.settings")
        self.assertIn("erplibre_streamdeck", action.context)
        menu = self.env.ref("erplibre_streamdeck.menu_streamdeck_settings")
        self.assertEqual(menu.action, action)
        self.assertEqual(menu.groups_id, self.env.ref("base.group_system"))
