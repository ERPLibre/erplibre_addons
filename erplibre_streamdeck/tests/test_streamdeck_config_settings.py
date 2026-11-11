# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
PARAM = "erplibre_streamdeck.first_pilot_policy"


@tagged("post_install", "-at_install")
class TestStreamdeckConfigSettings(TransactionCase):
    """Paramètres › Stream Deck : la politique du premier pilotage.

    Au premier pilotage d'un poste, l'employé choisit entre ses valeurs
    locales et celles d'Odoo (`ask`), à moins que l'organisation ne force
    `keep_local` ou `take_odoo`. Le paramètre vit en
    `ir.config_parameter`, écrit par la page Paramètres seule, donc par
    son administrateur (`base.group_system`), qui est aussi gestionnaire
    du Stream Deck ; une valeur inconnue s'y lit `ask`.
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

    def test_only_a_settings_administrator_sets_the_first_pilot_policy(
        self,
    ):
        self.Param.set_param(PARAM, "ask")
        # L'employé, et le gestionnaire du Stream Deck sans les droits de
        # la page Paramètres, ne l'écrivent ni par la page ni par le
        # paramètre : Odoo réserve la page Paramètres à `base.group_system`.
        for user in (self.employee, self.manager):
            with self.subTest(user=user.login):
                with self.assertRaises(AccessError):
                    self.Settings.with_user(user).create(
                        {"streamdeck_first_pilot_policy": "take_odoo"}
                    ).execute()
                with self.assertRaises(AccessError):
                    self.env["ir.config_parameter"].with_user(user).set_param(
                        PARAM, "take_odoo"
                    )
                self.assertEqual(self.Schema._first_pilot_policy(), "ask")

        for policy in ("keep_local", "take_odoo", "ask"):
            with self.subTest(policy=policy):
                self.Settings.with_user(self.admin).create(
                    {"streamdeck_first_pilot_policy": policy}
                ).execute()
                self.assertEqual(self.Param.get_param(PARAM), policy)
                self.assertEqual(self.Schema._first_pilot_policy(), policy)
