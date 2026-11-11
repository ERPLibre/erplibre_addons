# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib
import json
import logging
from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import (
    HttpCase,
    TransactionCase,
    get_db_name,
    new_test_user,
    tagged,
)
from odoo.tools.safe_eval import safe_eval

FINGERPRINT_A = "c" * 64
FINGERPRINT_B = "d" * 64
ROUTES = ("enroll", "report", "unenroll")
PAIRING_ALPHABET = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
# L'adresse d'où le client de test parle au serveur de test : la
# temporisation des connexions y compte les échecs.
LOOPBACK = "127.0.0.1"


@tagged("post_install", "-at_install")
class TestStreamdeckRoutes(HttpCase):
    """Les trois routes JSON du protocole 1.0, appelées par HTTP comme le
    fait l'extension : la base est d'abord choisie par
    `GET /web/login?db=`, puis chaque appel est un POST JSON."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["streamdeck.service"]
        cls.Workstation = cls.env["streamdeck.workstation"].with_context(
            active_test=False
        )
        cls.password = "zz-sd-route-a-pw-1"
        cls.user_a = new_test_user(
            cls.env,
            login="zz_sd_route_a",
            password=cls.password,
            name="Employee A",
            groups="base.group_user",
        )
        cls.portal = new_test_user(
            cls.env,
            login="zz_sd_route_p",
            password="zz-sd-route-p-pw-1",
            name="Portal P",
            groups="base.group_portal",
        )

    def setUp(self):
        super().setUp()

        def forget_failures():
            failures = getattr(self.registry, "_login_failures", {})
            failures.pop(LOOPBACK, None)

        self.addCleanup(forget_failures)
        response = self.url_open("/web/login?db=%s" % get_db_name())
        self.assertEqual(response.status_code, 200)

    # -- helpers ---------------------------------------------------------

    def _post(self, route, payload=None, token=None, raw=None, headers=None):
        all_headers = {"Content-Type": "application/json"}
        if token is not None:
            all_headers["Authorization"] = "Bearer %s" % token
        all_headers.update(headers or {})
        data = raw if raw is not None else json.dumps(payload)
        return self.url_open(
            "/streamdeck/v1/%s" % route, data=data, headers=all_headers
        )

    def _json(self, response, status):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(
            response.headers["Content-Type"].split(";")[0],
            "application/json",
        )
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        body = response.json()
        self.assertEqual(body["protocol"], "1.0")
        return body

    def _error(self, response, status, code):
        body = self._json(response, status)
        self.assertEqual(body.get("error"), code, body)
        return body

    def _enroll_payload(self, method="pairing_code", **values):
        payload = {
            "protocol": "1.0",
            "method": method,
            "fingerprint": FINGERPRINT_A,
            "hostname": "host-a",
        }
        payload.update(values)
        return payload

    @staticmethod
    def _report_payload(decks=(), events=()):
        return {
            "protocol": "1.0",
            "state": {
                "hostname": "host-a",
                "os": {"name": "Debian GNU/Linux", "version": "13"},
                "gnome_shell": "48.4",
                "extension_version": "1.4.0",
                "contract_version": "1.2",
                "erplibre": None,
                "deck_program": None,
                "service_state": "active",
                "decks": list(decks),
            },
            "events": list(events),
            "lost_events": 0,
        }

    def _enroll_by_code(self, user, fingerprint=FINGERPRINT_A):
        code = self.Service.new_pairing_code(user)
        body = self._json(
            self._post(
                "enroll",
                self._enroll_payload(code=code.code, fingerprint=fingerprint),
            ),
            200,
        )
        return body

    # -- tests -----------------------------------------------------------

    def test_enroll_then_report_over_http(self):
        body = self._enroll_by_code(self.user_a)
        self.assertEqual(set(body), {"protocol", "workstation_id", "token"})
        token = body["token"]
        self.assertRegex(token, r"^[A-Za-z0-9_-]{43}$")
        workstation = self.Workstation.browse(body["workstation_id"])
        self.assertEqual(workstation.user_id, self.user_a)

        deck = {
            "serial": "SN-ROUTE-1",
            "usb_product_id": "0084",
            "usb_path": "1-2.3",
            "firmware": None,
        }
        event = {
            "uuid": "00000000-0000-4000-8000-000000000101",
            "kind": "plugged",
            "at": "2026-01-01T10:00:00Z",
            "serial": "SN-ROUTE-1",
            "usb_product_id": "0084",
            "usb_path": "1-2.3",
            "service_state": None,
        }
        body = self._json(
            self._post(
                "report", self._report_payload([deck], [event]), token=token
            ),
            200,
        )
        self.assertEqual(
            body,
            {
                "protocol": "1.0",
                "accepted": [event["uuid"]],
                "heartbeat_s": 900,
            },
        )
        self.assertEqual(workstation.device_ids.serial, "SN-ROUTE-1")
        self.assertTrue(workstation.device_ids.connected)
        self.assertEqual(workstation.os_name, "Debian GNU/Linux")
        self.assertEqual(len(workstation.event_ids), 1)

        body = self._json(
            self._post("unenroll", {"protocol": "1.0"}, token=token), 200
        )
        self.assertEqual(body, {"protocol": "1.0"})
        self.assertFalse(workstation.token_hash)
        self._error(
            self._post("report", self._report_payload(), token=token),
            401,
            "token_invalid",
        )

    def test_every_error_of_the_contract_answers_over_http(self):
        self._error(self._post("enroll", raw="{not json"), 400, "bad_request")
        self._error(self._post("enroll", raw="\xff"), 400, "bad_request")
        self._error(self._post("enroll", [1, 2]), 400, "bad_request")
        self._error(
            self._post("enroll", self._enroll_payload(protocol="2.0")),
            400,
            "protocol_unsupported",
        )
        self._error(
            self._post("enroll", self._enroll_payload(code="ZZZZZZZZ")),
            401,
            "credentials_refused",
        )
        self._error(
            self._post(
                "enroll",
                self._enroll_payload(
                    method="password",
                    login="zz_sd_route_p",
                    password="zz-sd-route-p-pw-1",
                ),
            ),
            403,
            "user_inactive",
        )
        token = self._enroll_by_code(self.user_a)["token"]
        self._error(
            self._post("report", raw="{not json", token=token),
            400,
            "bad_request",
        )
        self._error(
            self._post("report", {"protocol": "1.0"}, token=token),
            400,
            "bad_request",
        )
        self._error(
            self._post("unenroll", {"protocol": "2.0"}, token=token),
            400,
            "protocol_unsupported",
        )
        self.user_a.groups_id = [
            (6, 0, [self.env.ref("base.group_portal").id])
        ]
        self._error(
            self._post("report", self._report_payload(), token=token),
            403,
            "user_inactive",
        )

    def test_a_report_without_bearer_is_401(self):
        token = self._enroll_by_code(self.user_a)["token"]
        payload = self._report_payload()
        for route, body in (("report", payload), ("unenroll", None)):
            body = body or {"protocol": "1.0"}
            with self.subTest(route=route, header="absent"):
                self._error(self._post(route, body), 401, "token_invalid")
            for header in (
                "Basic %s" % token,
                "Bearer",
                "Bearer ",
                token,
                "Bearer %s extra" % token,
            ):
                with self.subTest(route=route, header=header):
                    self._error(
                        self._post(
                            route, body, headers={"Authorization": header}
                        ),
                        401,
                        "token_invalid",
                    )
        # Le schéma se lit sans égard à la casse, comme le veut HTTP.
        self._json(
            self._post(
                "report",
                payload,
                headers={"Authorization": "bearer %s" % token},
            ),
            200,
        )

    def test_get_is_refused(self):
        for route in ROUTES:
            with self.subTest(route=route):
                response = self.url_open("/streamdeck/v1/%s" % route)
                self.assertEqual(response.status_code, 405)

    def test_a_route_writes_without_a_retry(self):
        # Une route `auth="none"` s'ouvre par défaut sur un curseur en
        # lecture seule : la première écriture y échoue, Odoo journalise
        # la requête refusée et rejoue tout l'appel.
        with self.assertLogs(level=logging.DEBUG) as captured:
            token = self._enroll_by_code(self.user_a)["token"]
            self._json(
                self._post("report", self._report_payload(), token=token),
                200,
            )
        self.assertFalse(
            [
                record.getMessage()[:200]
                for record in captured.records
                if record.levelno >= logging.WARNING
            ]
        )

    def test_no_route_logs_the_token_or_password(self):
        key = (
            self.env["res.users.apikeys"]
            .with_user(self.user_a)
            .sudo()
            ._generate(None, "inventory", None)
        )
        secrets_seen = []
        with self.assertLogs(level=logging.DEBUG) as captured:
            body = self._json(
                self._post(
                    "enroll",
                    self._enroll_payload(
                        method="password",
                        login="zz_sd_route_a",
                        password=self.password,
                    ),
                ),
                200,
            )
            secrets_seen.append(body["token"])
            self._json(
                self._post(
                    "report", self._report_payload(), token=body["token"]
                ),
                200,
            )
            body = self._json(
                self._post(
                    "enroll",
                    self._enroll_payload(
                        method="api_key", key=key, fingerprint=FINGERPRINT_B
                    ),
                ),
                200,
            )
            secrets_seen.append(body["token"])
            self._json(
                self._post(
                    "unenroll", {"protocol": "1.0"}, token=body["token"]
                ),
                200,
            )
        self.assertTrue(
            any(
                "enrolled" in record.getMessage()
                for record in captured.records
            ),
            "the enrollment is logged, without its secrets",
        )
        for record in captured.records:
            text = record.getMessage() + (record.exc_text or "")
            for secret in [self.password, key] + secrets_seen:
                self.assertNotIn(secret, text, record.name)


@tagged("post_install", "-at_install")
class TestStreamdeckPairingWizard(TransactionCase):
    """« Ajouter un poste » : l'assistant qui affiche un code d'appairage
    neuf, au nom de l'employé qui l'ouvre et lisible de lui seul."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(
            cls.env,
            login="zz_sd_wiz_a",
            name="Employee A",
            groups="base.group_user",
        )
        cls.user_b = new_test_user(
            cls.env,
            login="zz_sd_wiz_b",
            name="Employee B",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_wiz_m",
            name="Manager M",
            groups="base.group_user,"
            "erplibre_streamdeck.group_streamdeck_manager",
        )

    def _open(self, user):
        Wizard = self.env["streamdeck.pairing.wizard"].with_user(user)
        action = Wizard.action_open()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "streamdeck.pairing.wizard")
        self.assertEqual(action["target"], "new")
        return Wizard.browse(action["res_id"])

    def _visible(self, xmlid, user):
        """Ce qu'une action de fenêtre montre à `user` : son domaine, évalué
        avec l'`uid` de l'utilisateur comme le fait le client web, puis la
        recherche sous ses droits et ses règles."""
        action = self.env.ref(xmlid)
        domain = safe_eval(action.domain or "[]", {"uid": user.id})
        return self.env[action.res_model].with_user(user).search(domain)

    def test_add_a_workstation_runs_for_an_employee(self):
        # Le chemin du client web : le bouton d'en-tête de la liste des
        # postes lance l'action serveur, qui exécute `action_open` sous
        # l'utilisateur qui clique. Un groupe trop étroit sur l'action
        # serveur refuserait le clic par une AccessError.
        server_action = self.env.ref(
            "erplibre_streamdeck.action_streamdeck_pairing_wizard"
        )
        for user in (self.user_a, self.manager):
            with self.subTest(user=user.login):
                arch = (
                    self.env["streamdeck.workstation"]
                    .with_user(user)
                    .get_views([(False, "list")])["views"]["list"]["arch"]
                )
                buttons = etree.fromstring(arch).xpath(
                    "//header/button[@type='action'][@name='%d']"
                    % server_action.id
                )
                self.assertEqual(len(buttons), 1)

                action = server_action.with_user(user).run()
                self.assertEqual(action["type"], "ir.actions.act_window")
                self.assertEqual(
                    action["res_model"], "streamdeck.pairing.wizard"
                )
                self.assertEqual(action["target"], "new")
                wizard = (
                    self.env["streamdeck.pairing.wizard"]
                    .with_user(user)
                    .browse(action["res_id"])
                )
                self.assertEqual(len(wizard.code), 8)
                code = (
                    self.env["streamdeck.pairing.code"]
                    .sudo()
                    .search([("code", "=", wizard.code)])
                )
                self.assertEqual(code.user_id, user)

    def test_my_menus_hold_only_my_own_records_even_for_the_manager(self):
        # Les règles ouvrent tout le parc au gestionnaire : seul le domaine
        # des actions « Mes postes » et « Mes decks » le borne à ses postes.
        Workstation = self.env["streamdeck.workstation"]
        Device = self.env["streamdeck.device"]
        ws_a, ws_m = (
            Workstation.create(
                {
                    "user_id": user.id,
                    "name": "host-%s" % seed,
                    "fingerprint": hashlib.sha256(seed.encode()).hexdigest(),
                }
            )
            for user, seed in ((self.user_a, "a"), (self.manager, "m"))
        )
        deck_a, deck_m, deck_moved = (
            Device.create(
                {
                    "key": serial,
                    "serial": serial,
                    "usb_product_id": "0084",
                    "workstation_id": workstation.id,
                    "connected": True,
                }
            )
            for serial, workstation in (
                ("SN-A", ws_a),
                ("SN-M", ws_m),
                ("SN-MOVED", ws_a),
            )
        )
        # Le deck déplacé a été détenu par le poste du gestionnaire avant
        # de passer sur celui de l'employé A : la détention que le service
        # pose à la création du deck chez le gestionnaire.
        self.env["streamdeck.device.holding"].create(
            {
                "device_id": deck_moved.id,
                "user_id": self.manager.id,
                "since": "2026-01-01 10:00:00",
            }
        )
        my_workstations = (
            "erplibre_streamdeck.action_streamdeck_my_workstations"
        )
        my_decks = "erplibre_streamdeck.action_streamdeck_my_decks"
        self.assertEqual(self._visible(my_workstations, self.manager), ws_m)
        self.assertEqual(
            self._visible(my_decks, self.manager), deck_m | deck_moved
        )
        self.assertEqual(self._visible(my_workstations, self.user_a), ws_a)
        self.assertEqual(
            self._visible(my_decks, self.user_a), deck_a | deck_moved
        )
        # Le parc, lui, montre au gestionnaire les postes et les decks de
        # chacun.
        self.assertLessEqual(
            ws_a | ws_m,
            self._visible(
                "erplibre_streamdeck.action_streamdeck_fleet_workstations",
                self.manager,
            ),
        )
        self.assertLessEqual(
            deck_a | deck_m | deck_moved,
            self._visible(
                "erplibre_streamdeck.action_streamdeck_fleet_decks",
                self.manager,
            ),
        )

    def test_the_wizard_shows_a_fresh_code_for_the_current_user(self):
        wizard = self._open(self.user_a)
        self.assertEqual(len(wizard.code), 8)
        self.assertLessEqual(set(wizard.code), PAIRING_ALPHABET)
        self.assertAlmostEqual(
            wizard.expires_at,
            fields.Datetime.now() + timedelta(minutes=10),
            delta=timedelta(seconds=5),
        )
        code = (
            self.env["streamdeck.pairing.code"]
            .sudo()
            .search([("code", "=", wizard.code)])
        )
        self.assertEqual(code.user_id, self.user_a)
        self.assertFalse(code.used)
        self.assertEqual(code.expires_at, wizard.expires_at)

        again = self._open(self.user_a)
        self.assertNotEqual(again.code, wizard.code)

        status, body = self.env["streamdeck.service"].enroll(
            {
                "protocol": "1.0",
                "method": "pairing_code",
                "code": wizard.code,
                "fingerprint": FINGERPRINT_A,
                "hostname": "host-a",
            }
        )
        self.assertEqual(status, 200, body)
        workstation = self.env["streamdeck.workstation"].browse(
            body["workstation_id"]
        )
        self.assertEqual(workstation.user_id, self.user_a)

    def test_nobody_reads_the_code_of_another_employee(self):
        wizard = self._open(self.user_a)
        for user in (self.user_b, self.manager):
            with self.subTest(user=user.login):
                with self.assertRaises(AccessError):
                    wizard.with_user(user).read(["code"])
                self.assertFalse(
                    self.env["streamdeck.pairing.wizard"]
                    .with_user(user)
                    .search([("id", "=", wizard.id)])
                )

    def test_the_code_cannot_be_typed_into_the_wizard(self):
        Wizard = self.env["streamdeck.pairing.wizard"].with_user(self.user_a)
        wizard = Wizard.create({})
        self.assertEqual(len(wizard.code), 8)
        code = (
            self.env["streamdeck.pairing.code"]
            .sudo()
            .search([("code", "=", wizard.code)])
        )
        self.assertEqual(code.user_id, self.user_a)
        # Un code ou un créateur fourni à la création est ignoré : le code
        # naît toujours du service, au nom de l'utilisateur courant.
        forged = Wizard.create(
            {"code": "AAAAAAAA", "create_uid": self.user_b.id}
        )
        self.assertNotEqual(forged.code, "AAAAAAAA")
        self.assertEqual(forged.create_uid, self.user_a)
        self.assertEqual(
            self.env["streamdeck.pairing.code"]
            .sudo()
            .search([("code", "=", forged.code)])
            .user_id,
            self.user_a,
        )
        self.assertFalse(
            self.env["streamdeck.pairing.code"]
            .sudo()
            .search([("code", "=", "AAAAAAAA")])
        )

    def test_the_menus_open_for_an_employee(self):
        menus = (
            self.env["ir.ui.menu"].with_user(self.user_a)._visible_menu_ids()
        )
        for xmlid, visible in (
            ("erplibre_streamdeck.menu_streamdeck_root", True),
            ("erplibre_streamdeck.menu_streamdeck_my_workstations", True),
            ("erplibre_streamdeck.menu_streamdeck_my_decks", True),
            ("erplibre_streamdeck.menu_streamdeck_fleet", False),
        ):
            with self.subTest(menu=xmlid):
                self.assertEqual(self.env.ref(xmlid).id in menus, visible)
        menus = (
            self.env["ir.ui.menu"].with_user(self.manager)._visible_menu_ids()
        )
        for xmlid in (
            "erplibre_streamdeck.menu_streamdeck_fleet_workstations",
            "erplibre_streamdeck.menu_streamdeck_fleet_decks",
            "erplibre_streamdeck.menu_streamdeck_fleet_events",
        ):
            with self.subTest(menu=xmlid):
                self.assertIn(self.env.ref(xmlid).id, menus)

    def test_the_views_render_for_an_employee(self):
        for model in (
            "streamdeck.workstation",
            "streamdeck.device",
            "streamdeck.event",
            "streamdeck.pairing.wizard",
        ):
            for view_type in ("list", "form", "search"):
                if (
                    model == "streamdeck.pairing.wizard"
                    and view_type != "form"
                ):
                    continue
                with self.subTest(model=model, view_type=view_type):
                    views = (
                        self.env[model]
                        .with_user(self.user_a)
                        .get_views([(False, view_type)])
                    )
                    self.assertTrue(views["views"][view_type]["arch"])

    def test_only_the_manager_sees_the_archive_flag(self):
        # Le formulaire n'offre « Archiver » que si `active` y figure :
        # l'employé, qui ne peut pas archiver, ne l'y trouve pas.
        Workstation = self.env["streamdeck.workstation"]
        for user, shown in ((self.user_a, False), (self.manager, True)):
            with self.subTest(user=user.login):
                arch = Workstation.with_user(user).get_views(
                    [(False, "form")]
                )["views"]["form"]["arch"]
                self.assertEqual('name="active"' in arch, shown)
