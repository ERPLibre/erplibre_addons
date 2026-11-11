# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import datetime
from uuid import uuid4

from lxml import etree

from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

T0 = datetime(2026, 4, 1, 9, 0, 0)

# The filter of the history that selects each label, by its name in the
# search view: one per kind, and one per state of a `service_changed`.
LABEL_FILTERS = {
    "plugged": "Plugged",
    "unplugged": "Unplugged",
    "moved": "Changed workstation",
    "silent": "Workstation silent",
    "heard_again": "Workstation heard again",
    "service_started": "Service started",
    "service_failed": "Service failed",
    "service_stopped": "Service stopped",
    "service_absent": "Service absent",
}


@tagged("post_install", "-at_install")
class TestStreamdeckMonitorViews(TransactionCase):
    """Ce que les vues montrent de la surveillance : le fil et les
    activités sur les fiches poste et deck, « Muet depuis » et le filtre
    des postes muets au Parc, le libellé de chaque événement et un filtre
    par libellé dans l'historique.

    Les vues se lisent par `get_views`, comme le client web les reçoit ;
    un filtre se vérifie en appliquant son domaine à des enregistrements.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Workstation = cls.env["streamdeck.workstation"]
        cls.Device = cls.env["streamdeck.device"]
        cls.Event = cls.env["streamdeck.event"]
        cls.user_a, cls.user_b = (
            new_test_user(
                cls.env,
                login="zz_sd_views_%s" % seed,
                name="Employee %s" % seed.upper(),
                groups="base.group_user",
            )
            for seed in "ab"
        )
        cls.workstation_a = cls._enroll(cls.user_a, "a")
        cls.workstation_b = cls._enroll(cls.user_b, "b")

    @classmethod
    def _enroll(cls, user, seed):
        Service = cls.env["streamdeck.service"]
        code = Service.new_pairing_code(user)
        status, body = Service.enroll(
            {
                "protocol": "1.0",
                "method": "pairing_code",
                "code": code.code,
                "fingerprint": seed * 64,
                "hostname": "host-%s" % seed,
            }
        )
        assert status == 200, body
        return cls.Workstation.browse(body["workstation_id"])

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _arch(model, view_type):
        arch = model.get_views([(False, view_type)])["views"][view_type][
            "arch"
        ]
        return etree.fromstring(arch)

    @staticmethod
    def _filters(search):
        """The filters of a search arch with a domain, by name."""
        return {
            node.get("name"): node
            for node in search.xpath("//filter[@domain]")
        }

    def _event(self, kind, service_state=False):
        return self.Event.create(
            {
                "uuid": str(uuid4()),
                "kind": kind,
                "at": T0,
                "received_at": T0,
                "workstation_id": self.workstation_a.id,
                "service_state": service_state,
            }
        )

    # -- tests -----------------------------------------------------------

    def test_the_workstation_and_deck_forms_show_their_thread(self):
        # La surveillance pose ses activités et ses notes au fil du poste
        # (service en échec, muet) et du deck (débranché, changé de
        # poste) : chaque fiche porte le fil, pour l'employé comme pour
        # le gestionnaire.
        for model in (self.Workstation, self.Device):
            for user in (self.env.user, self.user_a):
                with self.subTest(model=model._name, user=user.login):
                    form = self._arch(model.with_user(user), "form")
                    self.assertEqual(len(form.xpath("//chatter")), 1)
                    # Le fil suit la feuille, à droite ou dessous.
                    self.assertEqual(
                        form.xpath("//chatter/preceding-sibling::*[1]")[0].tag,
                        "sheet",
                    )

    def test_the_fleet_shows_and_filters_silent_workstations(self):
        self.workstation_a.silent_since = T0
        listed = self._arch(self.Workstation, "list")
        self.assertIn("silent_since", listed.xpath("//field/@name"))
        form = self._arch(self.Workstation, "form")
        self.assertIn("silent_since", form.xpath("//field/@name"))
        self.assertIn("service_state_since", form.xpath("//field/@name"))

        silent = self._filters(self._arch(self.Workstation, "search"))[
            "silent"
        ]
        self.assertEqual(silent.get("string"), "Silent")
        domain = safe_eval(silent.get("domain"))
        mine = self.workstation_a | self.workstation_b
        self.assertEqual(
            self.Workstation.search(domain + [("id", "in", mine.ids)]),
            self.workstation_a,
        )

    def test_every_event_list_names_the_event_by_its_label(self):
        # Le libellé dit l'état du service d'un `service_changed`, que la
        # sorte seule tait : chaque liste d'événements le montre.
        lists = {
            "history": self._arch(self.Event, "list"),
            "workstation": self._arch(self.Workstation, "form").xpath(
                "//field[@name='event_ids']/list"
            ),
            "deck": self._arch(self.Device, "form").xpath(
                "//field[@name='event_ids']/list"
            ),
        }
        for where, node in lists.items():
            with self.subTest(where=where):
                if isinstance(node, list):
                    self.assertEqual(len(node), 1)
                    node = node[0]
                self.assertIn("label", node.xpath(".//field/@name"))
        form = self._arch(self.Event, "form")
        self.assertIn("label", form.xpath("//field/@name"))

    def test_each_history_filter_selects_the_events_of_its_label(self):
        events = (
            self._event("plugged")
            | self._event("unplugged")
            | self._event("moved")
            | self._event("silent")
            | self._event("heard_again")
        )
        for state in ("active", "failed", "inactive", "absent"):
            events |= self._event("service_changed", state)
        filters = self._filters(self._arch(self.Event, "search"))
        for name, label in LABEL_FILTERS.items():
            with self.subTest(filter=name):
                self.assertIn(name, filters)
                self.assertEqual(filters[name].get("string"), label)
                found = self.Event.search(
                    safe_eval(filters[name].get("domain"))
                    + [("id", "in", events.ids)]
                )
                self.assertEqual(len(found), 1)
                self.assertEqual(found.label, label)
        # « Service changed » garde les quatre états à la fois.
        found = self.Event.search(
            safe_eval(filters["service_changed"].get("domain"))
            + [("id", "in", events.ids)]
        )
        self.assertEqual(len(found), 4)
