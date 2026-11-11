# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
PARAM = "erplibre_streamdeck.first_pilot_policy"


@tagged("post_install", "-at_install")
class TestStreamdeckConfigSettings(TransactionCase):
    """La politique du premier pilotage.

    Au premier pilotage d'un poste, l'employé choisit entre ses valeurs
    locales et celles d'Odoo (`ask`), à moins que l'organisation ne force
    `keep_local` ou `take_odoo`. Le paramètre vit en
    `ir.config_parameter` ; le gestionnaire du Stream Deck l'écrit par le
    formulaire `streamdeck.config.policy` (Stream Deck › Configuration ›
    Premier pilotage), l'administrateur des Paramètres aussi par la page
    Paramètres › Stream Deck. Une valeur inconnue s'y lit `ask`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Settings = cls.env["res.config.settings"]
        cls.Param = cls.env["ir.config_parameter"].sudo()
        cls.Schema = cls.env["streamdeck.config.schema"]
        cls.employee = new_test_user(
            cls.env,
            login="zz_sd_cfgset_e",
            name="Employee E",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_cfgset_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        cls.admin = new_test_user(
            cls.env,
            login="zz_sd_cfgset_s",
            name="Administrator S",
            groups="base.group_user,base.group_system,%s" % MANAGER_GROUP,
        )

    def test_the_first_pilot_policy_defaults_to_ask(self):
        self.Param.search([("key", "=", PARAM)]).unlink()
        self.assertEqual(self.Schema._first_pilot_policy(), "ask")
        settings = self.Settings.create({})
        self.assertEqual(settings.streamdeck_first_pilot_policy, "ask")
        settings.execute()
        self.assertEqual(self.Schema._first_pilot_policy(), "ask")
        self.assertEqual(
            self.Settings.create({}).streamdeck_first_pilot_policy, "ask"
        )

    def test_an_unknown_first_pilot_policy_reads_as_ask(self):
        for stored, read in (
            ("keep_local", "keep_local"),
            ("take_odoo", "take_odoo"),
            ("ask", "ask"),
            ("Take_Odoo", "ask"),
            ("always", "ask"),
            (" ask", "ask"),
        ):
            with self.subTest(stored=stored):
                self.Param.set_param(PARAM, stored)
                self.assertEqual(self.Schema._first_pilot_policy(), read)
                self.assertEqual(
                    self.Settings.create({}).streamdeck_first_pilot_policy,
                    read,
                )

    def test_only_the_manager_sets_the_first_pilot_policy(self):
        Policy = self.env["streamdeck.config.policy"]
        self.Param.set_param(PARAM, "ask")
        # L'employé n'ouvre pas le formulaire, n'enregistre pas celui d'un
        # autre et n'écrit pas le paramètre.
        with self.assertRaises(AccessError):
            Policy.with_user(self.employee).create(
                {"first_pilot_policy": "take_odoo"}
            )
        form = Policy.with_user(self.manager).create(
            {"first_pilot_policy": "take_odoo"}
        )
        with self.assertRaises(AccessError):
            form.with_user(self.employee).action_save()
        with self.assertRaises(AccessError):
            self.env["ir.config_parameter"].with_user(self.employee).set_param(
                PARAM, "take_odoo"
            )
        self.assertEqual(self.Schema._first_pilot_policy(), "ask")

        # Le gestionnaire, sans les droits de la page Paramètres, force
        # chaque politique, et le formulaire s'ouvre sur celle en place.
        self.assertFalse(self.manager.has_group("base.group_system"))
        for policy in ("keep_local", "take_odoo", "ask"):
            with self.subTest(policy=policy):
                form = Policy.with_user(self.manager).create(
                    {"first_pilot_policy": policy}
                )
                action = form.action_save()
                self.assertEqual(action["type"], "ir.actions.act_window_close")
                self.assertEqual(self.Param.get_param(PARAM), policy)
                self.assertEqual(self.Schema._first_pilot_policy(), policy)
                self.assertEqual(
                    Policy.with_user(self.manager)
                    .create({})
                    .first_pilot_policy,
                    policy,
                )

    def test_the_settings_page_writes_it_for_its_administrator_only(self):
        self.Param.set_param(PARAM, "ask")
        # La page Paramètres reste à `base.group_system` : le gestionnaire
        # du Stream Deck passe par son propre formulaire.
        for user in (self.employee, self.manager):
            with self.subTest(user=user.login):
                with self.assertRaises(AccessError):
                    self.Settings.with_user(user).create(
                        {"streamdeck_first_pilot_policy": "take_odoo"}
                    ).execute()
                self.assertEqual(self.Schema._first_pilot_policy(), "ask")

        for policy in ("keep_local", "take_odoo", "ask"):
            with self.subTest(policy=policy):
                self.Settings.with_user(self.admin).create(
                    {"streamdeck_first_pilot_policy": policy}
                ).execute()
                self.assertEqual(self.Param.get_param(PARAM), policy)
                self.assertEqual(self.Schema._first_pilot_policy(), policy)
