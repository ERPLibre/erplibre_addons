# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib
from datetime import datetime
from uuid import uuid4

from lxml import etree

from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
T0 = datetime(2026, 4, 1, 9, 0, 0)

# The history filter of each configuration kind, by its name in the
# search view, with the label it selects.
CONFIG_KIND_FILTERS = {
    "config_applied": "Configuration applied",
    "config_refused": "Configuration refused",
    "config_adopted": "Local setting adopted",
    "config_drift": "Setting changed locally",
}


@tagged("post_install", "-at_install")
class TestStreamdeckConfigViews(TransactionCase):
    """Ce que les vues montrent de la configuration pilotée : l'onglet
    « Configuration » du poste, les profils et les modèles de deck du
    gestionnaire, le réglage du premier pilotage, les filtres du Parc et
    de l'historique.

    Les vues se lisent par `get_views`, comme le client web les reçoit
    pour l'utilisateur qui les ouvre ; un domaine ou une expression de
    vue s'évalue contre des enregistrements.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Workstation = cls.env["streamdeck.workstation"]
        cls.Profile = cls.env["streamdeck.config.profile"]
        cls.Model = cls.env["streamdeck.config.model"]
        cls.Line = cls.env["streamdeck.config.line"]
        cls.employee = new_test_user(
            cls.env,
            login="zz_sd_cfg_views_a",
            name="Employee A",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_cfg_views_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        cls.workstation = cls.Workstation.create(
            {
                "user_id": cls.employee.id,
                "name": "host-a",
                "fingerprint": hashlib.sha256(b"host-a").hexdigest(),
            }
        )
        cls.selectable = cls.Profile.create(
            {"name": "Selectable", "selectable": True}
        )
        cls.fixed = cls.Profile.create({"name": "Fixed"})

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _arch(model, view_type, view_ref=False):
        views = model.get_views([(view_ref, view_type)])["views"]
        return etree.fromstring(views[view_type]["arch"])

    def _form(self, user):
        return self._arch(self.Workstation.with_user(user), "form")

    @staticmethod
    def _page(form):
        (page,) = form.xpath("//page[@name='configuration']")
        return page

    @staticmethod
    def _filters(search):
        return {
            node.get("name"): node
            for node in search.xpath("//filter[@domain]")
        }

    @staticmethod
    def _readonly(node, values):
        expression = node.get("readonly") or "False"
        return bool(safe_eval(expression, values))

    def _visible_menus(self, user):
        Menu = self.env["ir.ui.menu"].with_user(user)
        return Menu.browse(Menu._visible_menu_ids())

    # -- the Configuration tab -------------------------------------------

    def test_the_configuration_tab_shows_the_pilot_of_the_workstation(self):
        for user in (self.employee, self.manager):
            with self.subTest(user=user.login):
                names = set(self._page(self._form(user)).xpath(".//@name"))
                for field in (
                    "config_profile_id",
                    "config_first_choice",
                    "config_effective_html",
                    "config_line_ids",
                    "config_state",
                    "config_revision",
                    "config_applied_revision",
                    "config_reason",
                    "config_pending_since",
                    "config_ask",
                    "deck_plugins",
                ):
                    self.assertIn(field, names)

    def test_an_employee_is_offered_only_selectable_profiles(self):
        # Le profil imposé au poste est lisible par l'employé ; le menu
        # déroulant ne lui offre pourtant que les profils « au choix ».
        self.workstation.config_profile_id = self.fixed
        (node,) = self._page(self._form(self.employee)).xpath(
            ".//field[@name='config_profile_id']"
        )
        domain = safe_eval(node.get("domain") or "[]")
        Profile = self.Profile.with_user(self.employee)
        self.assertIn(self.fixed, Profile.search([]))
        offered = Profile.search(
            domain + [("id", "in", (self.selectable | self.fixed).ids)]
        )
        self.assertEqual(offered, self.selectable)

    def test_the_profile_is_read_only_to_the_employee_when_not_selectable(
        self,
    ):
        (node,) = self._page(self._form(self.employee)).xpath(
            ".//field[@name='config_profile_id']"
        )
        for profile, readonly in (
            (self.Profile, False),
            (self.selectable, False),
            (self.fixed, True),
        ):
            with self.subTest(profile=profile.name):
                self.workstation.config_profile_id = profile
                values = {
                    "config_profile_id": self.workstation.config_profile_id.id,
                    "config_profile_selectable": (
                        self.workstation.config_profile_selectable
                    ),
                }
                self.assertEqual(self._readonly(node, values), readonly)

    def test_the_manager_assigns_any_profile_from_the_form(self):
        (node,) = self._page(self._form(self.manager)).xpath(
            ".//field[@name='config_profile_id']"
        )
        domain = safe_eval(node.get("domain") or "[]")
        both = self.selectable | self.fixed
        self.assertEqual(
            self.Profile.with_user(self.manager).search(
                domain + [("id", "in", both.ids)]
            ),
            both,
        )
        self.workstation.config_profile_id = self.fixed
        self.assertFalse(
            self._readonly(
                node,
                {
                    "config_profile_id": self.fixed.id,
                    "config_profile_selectable": False,
                },
            )
        )

    def test_the_employee_edits_overrides_but_never_locks_or_sources(self):
        (lines,) = self._page(self._form(self.employee)).xpath(
            ".//field[@name='config_line_ids']/list"
        )
        self.assertIn(lines.get("editable"), ("top", "bottom"))
        nodes = {
            node.get("name"): node for node in lines.xpath("./field[@name]")
        }
        for name in ("key", "value", "locked", "source"):
            self.assertIn(name, nodes)
        for name in ("locked", "source"):
            with self.subTest(field=name):
                self.assertTrue(self._readonly(nodes[name], {}))
        # A line the manager locked on the workstation stays as it is.
        for name in ("key", "value"):
            with self.subTest(field=name):
                self.assertFalse(
                    self._readonly(nodes[name], {"locked": False})
                )
                self.assertTrue(self._readonly(nodes[name], {"locked": True}))

    def test_the_manager_locks_overrides_of_a_workstation(self):
        (lines,) = self._page(self._form(self.manager)).xpath(
            ".//field[@name='config_line_ids']/list"
        )
        nodes = {
            node.get("name"): node for node in lines.xpath("./field[@name]")
        }
        for name in ("key", "value", "locked"):
            with self.subTest(field=name):
                self.assertFalse(self._readonly(nodes[name], {"locked": True}))
        self.assertTrue(self._readonly(nodes["source"], {}))

    def test_the_form_warns_about_several_deck_models(self):
        page = self._page(self._form(self.employee))
        (warning,) = page.xpath(".//*[@invisible='not config_several_models']")
        self.assertIn("highest", "".join(warning.itertext()))
        for product in ("0084", "006c"):
            self.Model.create({"usb_product_id": product})
            self.env["streamdeck.device"].create(
                {
                    "key": "sn:SN-%s" % product,
                    "serial": "SN-%s" % product,
                    "usb_product_id": product,
                    "workstation_id": self.workstation.id,
                    "connected": True,
                }
            )
            self.workstation.invalidate_recordset()
            self.assertEqual(
                self.workstation.config_several_models, product == "006c"
            )

    def test_the_form_says_an_old_extension_cannot_be_piloted(self):
        page = self._page(self._form(self.employee))
        (warning,) = page.xpath(".//*[@invisible='not config_too_old']")
        self.assertIn("too old", "".join(warning.itertext()))
        for version, too_old in (
            (False, False),
            ("1.0", True),
            ("1.2", True),
            ("1.3", False),
            ("1.10", False),
            ("2.0", False),
            ("garbage", False),
        ):
            with self.subTest(contract_version=version):
                self.workstation.contract_version = version
                self.assertEqual(self.workstation.config_too_old, too_old)

    def test_the_form_tells_while_the_employee_is_asked(self):
        page = self._page(self._form(self.employee))
        (notice,) = page.xpath(".//*[@invisible='not config_ask']")
        self.assertIn("employee's choice", "".join(notice.itertext()))

    # -- manager menus and settings --------------------------------------

    def test_the_configuration_menus_are_the_manager_s_only(self):
        menus = (
            self.env.ref("erplibre_streamdeck.menu_streamdeck_configuration")
            | self.env.ref(
                "erplibre_streamdeck.menu_streamdeck_config_profiles"
            )
            | self.env.ref("erplibre_streamdeck.menu_streamdeck_config_models")
        )
        self.assertEqual(
            {menu.name for menu in menus},
            {"Configuration", "Profiles", "Deck models"},
        )
        self.assertEqual(menus & self._visible_menus(self.manager), menus)
        self.assertFalse(menus & self._visible_menus(self.employee))
        for xmlid, model in (
            ("action_streamdeck_config_profiles", "streamdeck.config.profile"),
            ("action_streamdeck_config_models", "streamdeck.config.model"),
        ):
            with self.subTest(action=xmlid):
                action = self.env.ref("erplibre_streamdeck." + xmlid)
                self.assertEqual(action.res_model, model)

    def test_the_profile_and_model_forms_hold_their_lines(self):
        profile = self._arch(self.Profile.with_user(self.manager), "form")
        names = set(profile.xpath("//field/@name"))
        for name in ("name", "selectable", "line_ids", "workstation_ids"):
            self.assertIn(name, names)
        model = self._arch(self.Model.with_user(self.manager), "form")
        names = set(model.xpath("//field/@name"))
        for name in ("usb_product_id", "name", "line_ids"):
            self.assertIn(name, names)
        for form in (profile, model):
            (lines,) = form.xpath("//field[@name='line_ids']/list")
            self.assertIn(lines.get("editable"), ("top", "bottom"))
            self.assertEqual(
                lines.xpath("./field/@name"),
                ["key", "value", "locked", "source"],
            )
        listed = self._arch(self.Profile.with_user(self.manager), "list")
        self.assertIn("selectable", listed.xpath("//field/@name"))

    def test_the_first_pilot_setting_is_the_administrator_s_only(self):
        settings = self._arch(self.env["res.config.settings"], "form")
        (app,) = settings.xpath("//app[@name='erplibre_streamdeck']")
        (setting,) = app.xpath(
            ".//setting[.//field[@name='streamdeck_first_pilot_policy']]"
        )
        (field,) = setting.xpath(
            ".//field[@name='streamdeck_first_pilot_policy']"
        )
        self.assertEqual(field.get("widget"), "radio")
        self.assertIn(
            "Locked settings are always offered",
            "".join(setting.itertext()) + (setting.get("help") or ""),
        )
        view = self.env.ref(
            "erplibre_streamdeck.res_config_settings_view_form"
        )
        (source_app,) = etree.fromstring(view.arch).xpath(
            "//app[@name='erplibre_streamdeck']"
        )
        self.assertEqual(source_app.get("groups"), "base.group_system")
        self.assertFalse(
            self.env["res.config.settings"]
            .with_user(self.manager)
            .has_access("read")
        )

    # -- Fleet and history filters ---------------------------------------

    def test_the_fleet_filters_pending_and_refused_configurations(self):
        others = self.Workstation.browse()
        for state in ("unmanaged", "pending", "applied", "refused", "drift"):
            others |= self.Workstation.create(
                {
                    "user_id": self.employee.id,
                    "name": "host-%s" % state,
                    "fingerprint": hashlib.sha256(state.encode()).hexdigest(),
                    "config_state": state,
                }
            )
        filters = self._filters(self._arch(self.Workstation, "search"))
        for name, string, state in (
            ("config_pending", "Configuration pending", "pending"),
            ("config_refused", "Configuration refused", "refused"),
        ):
            with self.subTest(filter=name):
                self.assertEqual(filters[name].get("string"), string)
                found = self.Workstation.search(
                    safe_eval(filters[name].get("domain"))
                    + [("id", "in", others.ids)]
                )
                self.assertEqual(found.mapped("config_state"), [state])
        listed = self._arch(self.Workstation, "list")
        self.assertIn("config_state", listed.xpath("//field/@name"))

    def test_each_config_kind_has_its_history_filter_and_fields(self):
        Event = self.env["streamdeck.event"]
        events = Event.browse()
        for kind in CONFIG_KIND_FILTERS:
            events |= Event.create(
                {
                    "uuid": str(uuid4()),
                    "kind": kind,
                    "at": T0,
                    "received_at": T0,
                    "workstation_id": self.workstation.id,
                }
            )
        filters = self._filters(self._arch(Event, "search"))
        for name, label in CONFIG_KIND_FILTERS.items():
            with self.subTest(filter=name):
                self.assertEqual(filters[name].get("string"), label)
                found = Event.search(
                    safe_eval(filters[name].get("domain"))
                    + [("id", "in", events.ids)]
                )
                self.assertEqual(found.label, label)
        form = self._arch(Event, "form")
        for name, kinds in (
            ("config_revision", {"config_applied", "config_refused"}),
            ("config_reason", {"config_refused"}),
            ("config_keys", {"config_adopted", "config_drift"}),
        ):
            (node,) = form.xpath("//field[@name='%s']" % name)
            for kind in CONFIG_KIND_FILTERS:
                with self.subTest(field=name, kind=kind):
                    shown = not safe_eval(
                        node.get("invisible") or "False", {"kind": kind}
                    )
                    self.assertEqual(shown, kind in kinds)
