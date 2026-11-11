# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib
import json
import secrets

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, get_db_name, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
POLICY_PARAM = "erplibre_streamdeck.first_pilot_policy"
KEYS = ("deck_program", "plugins_off", "session_refresh_sec", "games")
CONFIG_KINDS = ("config_applied", "config_refused", "config_adopted")
CONFIG_KINDS += ("config_drift",)
AT = "2026-01-01T10:00:00Z"


@tagged("post_install", "-at_install")
class TestStreamdeckConfigWire(HttpCase):
    """La configuration voulue sur le fil, protocole 1.1, par la vraie
    route `/streamdeck/v1/report`.

    Le profil P fixe `deck_program` (verrouillé), `plugins_off` et
    `games` ; le poste de A le porte. Le corps `config` du pilote dit ce
    que le fichier du poste contient (`current`), ce que l'extension a
    appliqué (`revision_applied`, `result`) et la réponse de l'employé à
    une question du premier pilotage (`choice`) ; la réponse porte la
    révision offerte.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Workstation = cls.env["streamdeck.workstation"]
        cls.Line = cls.env["streamdeck.config.line"]
        cls.Event = cls.env["streamdeck.event"]
        cls.schema = cls.env["streamdeck.config.schema"]
        cls.user_a = new_test_user(
            cls.env,
            login="zz_sd_wire_a",
            name="Employee A",
            groups="base.group_user",
        )
        cls.user_b = new_test_user(
            cls.env,
            login="zz_sd_wire_b",
            name="Employee B",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_wire_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        Profile = cls.env["streamdeck.config.profile"]
        cls.profile = Profile.create({"name": "P"})
        for key, value, locked in (
            ("deck_program", '"tiler"', True),
            ("plugins_off", '["sound"]', False),
            ("games", '"on"', False),
        ):
            cls.Line.create(
                {
                    "profile_id": cls.profile.id,
                    "key": key,
                    "value": value,
                    "locked": locked,
                }
            )
        cls.selectable = Profile.create({"name": "S", "selectable": True})
        cls.Line.create(
            {
                "profile_id": cls.selectable.id,
                "key": "games",
                "value": '"off"',
            }
        )

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(POLICY_PARAM, "ask")
        response = self.url_open("/web/login?db=%s" % get_db_name())
        self.assertEqual(response.status_code, 200)

    # -- helpers ---------------------------------------------------------

    def _workstation(self, user=None, profile=None):
        """Un poste inscrit de `user` (A par défaut) et son jeton."""
        token = secrets.token_urlsafe(32)
        user = user or self.user_a
        workstation = self.Workstation.create(
            {
                "user_id": user.id,
                "name": "host-%s" % token[:6],
                "fingerprint": hashlib.sha256(token.encode()).hexdigest(),
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "config_profile_id": (profile or self.profile).id,
            }
        )
        return workstation, token

    @staticmethod
    def _pilot(current=None, applied=None, result=None, choice=None):
        values = dict.fromkeys(KEYS)
        values.update(current or {})
        return {
            "pilot": True,
            "revision_applied": applied,
            "current": values,
            "result": result,
            "choice": choice,
        }

    @staticmethod
    def _result(revision, status="applied", reason=None):
        return {
            "revision": revision,
            "status": status,
            "reason": reason,
            "at": AT,
        }

    @staticmethod
    def _payload(config=None, protocol="1.1", events=(), **state):
        payload = {
            "protocol": protocol,
            "state": dict(
                {
                    "hostname": "host",
                    "os": {"name": "Debian GNU/Linux", "version": "13"},
                    "gnome_shell": "48.4",
                    "extension_version": "1.5.0",
                    "contract_version": "1.3",
                    "erplibre": None,
                    "deck_program": "tiler",
                    "service_state": "active",
                    "deck_plugins": [],
                    "decks": [],
                },
                **state,
            ),
            "events": list(events),
            "lost_events": 0,
        }
        if config is not None:
            payload["config"] = config
        return payload

    def _post(self, token, payload, status=200):
        response = self.url_open(
            "/streamdeck/v1/report",
            data=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer %s" % token,
            },
        )
        self.assertEqual(response.status_code, status, response.text)
        body = response.json()
        self.assertEqual(body["protocol"], "1.1")
        return body

    def _report(self, token, config=None, **kwargs):
        """La réponse 200 d'une remontée 1.1 portant `config`."""
        return self._post(token, self._payload(config, **kwargs))

    def _profile_line(self, key):
        return self.profile.line_ids.filtered(lambda line: line.key == key)

    def _events(self, workstation, kind):
        return self.Event.search(
            [("workstation_id", "=", workstation.id), ("kind", "=", kind)]
        )

    def _settings(self, **values):
        settings = {
            "deck_program": "tiler",
            "plugins_off": ["sound"],
            "games": "on",
        }
        settings.update(values)
        return {key: settings[key] for key in KEYS if key in settings}

    def _applied(self, token, workstation, current=None):
        """Remonter puis appliquer la révision offerte ; renvoie la
        révision appliquée."""
        current = current or self._settings()
        revision = self._report(token, self._pilot(current))["config"][
            "revision"
        ]
        self._report(
            token, self._pilot(current, revision, self._result(revision))
        )
        self.assertEqual(workstation.config_state, "applied")
        return revision

    # -- protocol and pilot ----------------------------------------------

    def test_a_1_0_report_gets_no_config_and_stays_unmanaged(self):
        workstation, token = self._workstation()
        for config in (None, self._pilot(self._settings())):
            with self.subTest(config=config):
                body = self._post(token, self._payload(config, protocol="1.0"))
                self.assertNotIn("config", body)
                self.assertEqual(workstation.config_state, "unmanaged")
                self.assertFalse(workstation.config_revision)

    def test_a_pilot_report_gets_revision_hash_settings_locked(self):
        workstation, token = self._workstation()
        # Le verrou du profil arrête la clé : la surcharge du poste ne
        # compte pas.
        self.Line.create(
            {
                "workstation_id": workstation.id,
                "key": "deck_program",
                "value": '"controller"',
            }
        )
        body = self._report(token, self._pilot({"games": "on"}))
        settings = self._settings()
        self.assertEqual(
            body["config"],
            {
                "revision": 1,
                "hash": self.schema._hash(settings),
                "settings": settings,
                "locked": ["deck_program"],
            },
        )
        self.assertEqual(workstation.config_state, "pending")
        self.assertTrue(workstation.config_pending_since)
        self.assertEqual(json.loads(workstation.config_offered), settings)
        self.assertEqual(workstation.config_hash, body["config"]["hash"])

    def test_a_non_pilot_destination_gets_nothing(self):
        workstation, token = self._workstation()
        for config in (
            None,
            {"pilot": False},
            {"pilot": False, "current": {"games": "maybe"}},
        ):
            with self.subTest(config=config):
                body = self._report(token, config)
                self.assertNotIn("config", body)
                self.assertEqual(workstation.config_state, "unmanaged")
                self.assertFalse(workstation.config_revision)

    def test_a_workstation_no_layer_configures_gets_no_config(self):
        workstation, token = self._workstation()
        workstation.config_profile_id = False
        body = self._report(token, self._pilot())
        self.assertNotIn("config", body)
        self.assertEqual(workstation.config_state, "unmanaged")

    def test_the_revision_moves_only_when_the_hash_changes(self):
        workstation, token = self._workstation()
        first = self._report(token, self._pilot())["config"]
        again = self._report(token, self._pilot())["config"]
        self.assertEqual(again, first)
        self.assertEqual(workstation.config_revision, 1)
        # Un verrou seul change `locked`, ni les valeurs ni la révision.
        games = self._profile_line("games")
        games.locked = True
        locked = self._report(token, self._pilot())["config"]
        self.assertEqual(locked["revision"], 1)
        self.assertEqual(locked["locked"], ["deck_program", "games"])
        games.write({"value": '"off"', "locked": False})
        moved = self._report(token, self._pilot())["config"]
        self.assertEqual(moved["revision"], 2)
        self.assertEqual(moved["settings"]["games"], "off")
        self.assertNotEqual(moved["hash"], first["hash"])
        games.value = '"on"'
        back = self._report(token, self._pilot())["config"]
        self.assertEqual(back["revision"], 3)
        self.assertEqual(back["hash"], first["hash"])

    def test_an_unknown_current_key_is_ignored(self):
        workstation, token = self._workstation()
        config = self._pilot({"key_layouts": {"0084": "anything"}})
        self.assertEqual(self._report(token, config)["config"]["revision"], 1)

    def test_picking_a_selectable_profile_offers_a_new_revision(self):
        workstation, token = self._workstation(profile=self.selectable)
        first = self._report(token, self._pilot())["config"]
        self.assertEqual(first["settings"], {"games": "off"})
        other = self.env["streamdeck.config.profile"].create(
            {"name": "S2", "selectable": True}
        )
        self.Line.create(
            {"profile_id": other.id, "key": "games", "value": '"on"'}
        )
        workstation.with_user(self.user_a).write(
            {"config_profile_id": other.id}
        )
        picked = self._report(token, self._pilot())["config"]
        self.assertEqual(picked["revision"], 2)
        self.assertEqual(picked["settings"], {"games": "on"})
        self.assertEqual(workstation.config_state, "pending")

    # -- results ---------------------------------------------------------

    def test_applied_result_records_values_and_event(self):
        workstation, token = self._workstation()
        revision = self._report(token, self._pilot())["config"]["revision"]
        result = self._result(revision)
        body = self._report(
            token, self._pilot(self._settings(), revision, result)
        )
        self.assertEqual(body["config"]["revision"], revision)
        self.assertEqual(workstation.config_state, "applied")
        self.assertEqual(workstation.config_applied_revision, revision)
        self.assertEqual(
            json.loads(workstation.config_applied), self._settings()
        )
        self.assertFalse(workstation.config_pending_since)
        event = self._events(workstation, "config_applied")
        self.assertEqual(len(event), 1)
        self.assertEqual(event.config_revision, revision)
        self.assertFalse(event.device_id)
        # Le même résultat renvoyé, comme après une réponse perdue, n'ajoute
        # rien.
        self._report(token, self._pilot(self._settings(), revision, result))
        self.assertEqual(self._events(workstation, "config_applied"), event)

    def test_refused_result_keeps_the_reason(self):
        workstation, token = self._workstation()
        revision = self._report(token, self._pilot())["config"]["revision"]
        refused = self._result(revision, "refused", "invalid:games")
        self._report(token, self._pilot(result=refused))
        self.assertEqual(workstation.config_state, "refused")
        self.assertEqual(workstation.config_reason, "invalid:games")
        event = self._events(workstation, "config_refused")
        self.assertEqual(len(event), 1)
        self.assertEqual(event.config_revision, revision)
        self.assertEqual(event.config_reason, "invalid:games")
        self._report(token, self._pilot())
        self.assertEqual(workstation.config_state, "refused")
        self.assertEqual(workstation.config_reason, "invalid:games")
        # Une nouvelle révision attend de nouveau, sans la raison de la
        # précédente.
        self._profile_line("games").value = '"off"'
        self._report(token, self._pilot())
        self.assertEqual(workstation.config_state, "pending")
        self.assertFalse(workstation.config_reason)

    def test_a_result_for_another_revision_is_ignored(self):
        workstation, token = self._workstation()
        revision = self._report(token, self._pilot())["config"]["revision"]
        for status in ("applied", "refused"):
            with self.subTest(status=status):
                result = self._result(revision + 1, status, None)
                self._report(token, self._pilot(result=result))
                self.assertEqual(workstation.config_state, "pending")
                self.assertFalse(workstation.config_applied_revision)
        self.assertFalse(
            self.Event.search(
                [
                    ("workstation_id", "=", workstation.id),
                    ("kind", "in", CONFIG_KINDS),
                ]
            )
        )

    def test_a_refused_result_sent_again_is_recorded_once(self):
        # L'extension renvoie son résultat tant qu'une remontée n'a pas eu
        # sa réponse : la même raison ne fait qu'un événement.
        workstation, token = self._workstation()
        revision = self._report(token, self._pilot())["config"]["revision"]
        refused = self._result(revision, "refused", "restart_failed")
        for _attempt in range(2):
            self._report(token, self._pilot(self._settings(), result=refused))
        self.assertEqual(workstation.config_state, "refused")
        self.assertEqual(len(self._events(workstation, "config_refused")), 1)

    def test_a_result_without_an_offered_revision_is_ignored(self):
        # Jamais offerte, ou retirée depuis : aucune révision n'attend de
        # résultat.
        never, token = self._workstation()
        never.config_profile_id = False
        refused = self._result(0, "refused", "write_failed")
        self._report(token, self._pilot(result=refused))
        withdrawn, token = self._workstation()
        revision = self._report(token, self._pilot())["config"]["revision"]
        withdrawn.config_profile_id = False
        self._report(token, self._pilot())
        result = self._result(revision)
        self._report(token, self._pilot(self._settings(), revision, result))
        for workstation in (never, withdrawn):
            self.assertEqual(workstation.config_state, "unmanaged")
            self.assertFalse(workstation.config_reason)
            self.assertFalse(workstation.config_applied_revision)
        self.assertFalse(
            self.Event.search(
                [
                    ("workstation_id", "in", (never | withdrawn).ids),
                    ("kind", "in", CONFIG_KINDS),
                ]
            )
        )

    def test_a_result_dated_ahead_is_dated_when_received(self):
        workstation, token = self._workstation()
        revision = self._report(token, self._pilot())["config"]["revision"]
        result = dict(self._result(revision), at="2999-01-01T00:00:00Z")
        self._report(token, self._pilot(self._settings(), revision, result))
        event = self._events(workstation, "config_applied")
        self.assertEqual(len(event), 1)
        self.assertEqual(event.at, event.received_at)

    def test_a_configuration_withdrawn_then_restored_gets_a_new_revision(
        self,
    ):
        workstation, token = self._workstation()
        revision = self._applied(token, workstation)
        workstation.config_profile_id = False
        body = self._report(token, self._pilot(self._settings(), revision))
        self.assertNotIn("config", body)
        self.assertEqual(workstation.config_state, "unmanaged")
        # Les mêmes valeurs revenues : une révision neuve, à confirmer.
        workstation.config_profile_id = self.profile
        body = self._report(token, self._pilot(self._settings(), revision))
        self.assertEqual(body["config"]["revision"], revision + 1)
        self.assertEqual(body["config"]["settings"], self._settings())
        self.assertEqual(workstation.config_state, "pending")

    # -- local changes ---------------------------------------------------

    def test_a_key_added_after_the_applied_revision_is_offered(self):
        # La révision appliquée ne fixait pas la clé : sa valeur locale n'a
        # pas de référence, ni adoptée ni écart.
        workstation, token = self._workstation()
        revision = self._applied(token, workstation)
        self.Line.create(
            {
                "workstation_id": workstation.id,
                "key": "session_refresh_sec",
                "value": "2",
            }
        )
        local = self._settings(session_refresh_sec=5)
        body = self._report(token, self._pilot(local, revision))
        self.assertEqual(body["config"]["revision"], revision + 1)
        self.assertEqual(
            body["config"]["settings"], self._settings(session_refresh_sec=2)
        )
        self.assertEqual(workstation.config_state, "pending")
        self.assertEqual(len(workstation.config_line_ids), 1)
        self.assertFalse(
            self.Event.search(
                [
                    ("workstation_id", "=", workstation.id),
                    ("kind", "in", ("config_adopted", "config_drift")),
                ]
            )
        )

    def test_a_locked_local_change_is_reoffered_as_drift(self):
        workstation, token = self._workstation()
        revision = self._applied(token, workstation)
        changed = self._settings(deck_program="controller")
        body = self._report(token, self._pilot(changed, revision))
        self.assertEqual(body["config"]["revision"], revision + 1)
        self.assertEqual(body["config"]["settings"], self._settings())
        self.assertEqual(workstation.config_state, "drift")
        drift = self._events(workstation, "config_drift")
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift.config_keys, "deck_program")
        # Toujours changé à la remontée suivante : ni révision ni événement
        # de plus.
        body = self._report(token, self._pilot(changed, revision))
        self.assertEqual(body["config"]["revision"], revision + 1)
        self.assertEqual(workstation.config_state, "pending")
        self.assertEqual(self._events(workstation, "config_drift"), drift)
        self.assertFalse(workstation.config_line_ids)
        result = self._result(revision + 1)
        self._report(
            token, self._pilot(self._settings(), revision + 1, result)
        )
        self.assertEqual(workstation.config_state, "applied")

    def test_a_file_that_follows_another_revision_is_left_alone(self):
        # Sans la révision appliquée qu'Odoo connaît, l'écart n'a pas de
        # référence : ni adoption, ni nouvelle révision.
        workstation, token = self._workstation()
        revision = self._applied(token, workstation)
        local = self._settings(games="off", deck_program="none")
        for applied in (None, revision + 5):
            with self.subTest(applied=applied):
                body = self._report(token, self._pilot(local, applied))
                self.assertEqual(body["config"]["revision"], revision)
                self.assertEqual(workstation.config_state, "applied")
                self.assertFalse(workstation.config_line_ids)
        self.assertFalse(
            self.Event.search(
                [
                    ("workstation_id", "=", workstation.id),
                    ("kind", "in", ("config_adopted", "config_drift")),
                ]
            )
        )

    def test_a_free_key_cleared_locally_is_reoffered(self):
        workstation, token = self._workstation()
        revision = self._applied(token, workstation)
        cleared = self._settings(games=None)
        body = self._report(token, self._pilot(cleared, revision))
        self.assertEqual(body["config"]["revision"], revision + 1)
        self.assertEqual(body["config"]["settings"]["games"], "on")
        self.assertEqual(workstation.config_state, "drift")
        self.assertEqual(
            self._events(workstation, "config_drift").config_keys, "games"
        )
        self.assertFalse(workstation.config_line_ids)

    def test_a_free_local_change_is_adopted_once(self):
        workstation, token = self._workstation()
        revision = self._applied(token, workstation)
        local = self._settings(games="off", plugins_off=[])
        body = self._report(token, self._pilot(local, revision))
        offered = body["config"]
        self.assertEqual(offered["revision"], revision + 1)
        self.assertEqual(offered["settings"], local)
        lines = workstation.config_line_ids
        self.assertEqual(
            {(line.key, line.value, line.source) for line in lines},
            {("games", '"off"', "local"), ("plugins_off", "[]", "local")},
        )
        adopted = self._events(workstation, "config_adopted")
        self.assertEqual(len(adopted), 1)
        self.assertEqual(adopted.config_keys, "plugins_off, games")
        # Avant que le `applied` silencieux de l'extension n'arrive : rien de
        # neuf.
        again = self._report(token, self._pilot(local, revision))["config"]
        self.assertEqual(again, offered)
        result = self._result(revision + 1)
        body = self._report(token, self._pilot(local, revision + 1, result))
        self.assertEqual(body["config"], offered)
        self.assertEqual(workstation.config_state, "applied")
        self._report(token, self._pilot(local, revision + 1))
        self.assertEqual(workstation.config_state, "applied")
        self.assertEqual(workstation.config_revision, revision + 1)
        self.assertEqual(self._events(workstation, "config_adopted"), adopted)
        self.assertFalse(self._events(workstation, "config_drift"))

    # -- first pilot -----------------------------------------------------

    def test_first_pilot_under_ask_offers_odoo_values_and_lists_differing_free_keys(  # noqa: E501
        self,
    ):
        workstation, token = self._workstation()
        local = {
            "deck_program": "controller",
            "plugins_off": [],
            "games": "on",
            "session_refresh_sec": 5,
        }
        config = self._report(token, self._pilot(local))["config"]
        self.assertEqual(config["settings"], self._settings())
        self.assertEqual(config["ask"], ["plugins_off"])
        self.assertEqual(workstation.config_ask, "plugins_off")
        self.assertFalse(workstation.config_line_ids)
        self.assertFalse(workstation.config_first_choice)
        self.assertEqual(workstation.config_state, "pending")
        self.assertFalse(self._events(workstation, "config_adopted"))

    def test_no_ask_when_free_local_values_already_match_or_are_null(self):
        workstation, token = self._workstation()
        for local in (
            self._settings(),
            {"deck_program": "none"},
            {"games": "on", "plugins_off": None},
        ):
            with self.subTest(local=local):
                config = self._report(token, self._pilot(local))["config"]
                self.assertNotIn("ask", config)
                self.assertFalse(workstation.config_ask)

    def test_choice_keep_local_adopts_free_values_and_offers_locked_ones(self):
        workstation, token = self._workstation()
        local = self._settings(deck_program="none", games="off")
        first = self._report(token, self._pilot(local))["config"]
        self.assertEqual(first["ask"], ["games"])
        body = self._report(token, self._pilot(local, choice="keep_local"))
        config = body["config"]
        self.assertNotIn("ask", config)
        self.assertEqual(config["revision"], first["revision"] + 1)
        self.assertEqual(config["settings"], self._settings(games="off"))
        self.assertEqual(config["locked"], ["deck_program"])
        self.assertEqual(workstation.config_first_choice, "keep_local")
        line = workstation.config_line_ids
        self.assertEqual(
            (line.key, line.value, line.source, line.locked),
            ("games", '"off"', "local", False),
        )
        adopted = self._events(workstation, "config_adopted")
        self.assertEqual(adopted.config_keys, "games")
        self.assertEqual(workstation.config_state, "pending")

    def test_choice_take_odoo_adopts_nothing(self):
        workstation, token = self._workstation()
        local = self._settings(games="off")
        first = self._report(token, self._pilot(local))["config"]
        config = self._report(token, self._pilot(local, choice="take_odoo"))[
            "config"
        ]
        self.assertNotIn("ask", config)
        self.assertEqual(config["revision"], first["revision"])
        self.assertEqual(config["settings"], self._settings())
        self.assertEqual(workstation.config_first_choice, "take_odoo")
        self.assertFalse(workstation.config_line_ids)
        self.assertFalse(self._events(workstation, "config_adopted"))

    def test_policy_keep_local_adopts_without_asking(self):
        self.env["ir.config_parameter"].sudo().set_param(
            POLICY_PARAM, "keep_local"
        )
        workstation, token = self._workstation()
        local = self._settings(games="off", deck_program="none")
        config = self._report(token, self._pilot(local))["config"]
        self.assertNotIn("ask", config)
        self.assertEqual(config["revision"], 1)
        self.assertEqual(config["settings"], self._settings(games="off"))
        self.assertEqual(workstation.config_first_choice, "keep_local")
        self.assertEqual(workstation.config_line_ids.source, "local")
        self.assertEqual(len(self._events(workstation, "config_adopted")), 1)

    def test_policy_take_odoo_offers_without_asking(self):
        self.env["ir.config_parameter"].sudo().set_param(
            POLICY_PARAM, "take_odoo"
        )
        workstation, token = self._workstation()
        local = self._settings(games="off")
        config = self._report(token, self._pilot(local))["config"]
        self.assertNotIn("ask", config)
        self.assertEqual(config["settings"], self._settings())
        self.assertEqual(workstation.config_first_choice, "take_odoo")
        self.assertFalse(workstation.config_line_ids)

    def test_locked_keys_are_offered_under_every_policy(self):
        local = self._settings(deck_program="controller", games="off")
        for policy in ("ask", "keep_local", "take_odoo"):
            with self.subTest(policy=policy):
                self.env["ir.config_parameter"].sudo().set_param(
                    POLICY_PARAM, policy
                )
                workstation, token = self._workstation()
                config = self._report(token, self._pilot(local))["config"]
                self.assertEqual(config["settings"]["deck_program"], "tiler")
                self.assertIn("deck_program", config["locked"])
                self.assertNotIn("deck_program", config.get("ask", []))
                if policy == "ask":
                    self.assertEqual(config["ask"], ["games"])
                    config = self._report(
                        token, self._pilot(local, choice="keep_local")
                    )["config"]
                self.assertEqual(config["settings"]["deck_program"], "tiler")
                self.assertNotIn(
                    "deck_program", workstation.config_line_ids.mapped("key")
                )

    def test_a_forced_policy_ignores_the_client_choice(self):
        local = self._settings(games="off")
        for policy, choice in (
            ("take_odoo", "keep_local"),
            ("keep_local", "take_odoo"),
        ):
            with self.subTest(policy=policy):
                self.env["ir.config_parameter"].sudo().set_param(
                    POLICY_PARAM, policy
                )
                workstation, token = self._workstation()
                config = self._report(
                    token, self._pilot(local, choice=choice)
                )["config"]
                self.assertEqual(workstation.config_first_choice, policy)
                adopted = policy == "keep_local"
                self.assertEqual(bool(workstation.config_line_ids), adopted)
                self.assertEqual(
                    config["settings"]["games"], "off" if adopted else "on"
                )
                # Retour à `ask` : le choix, posé une fois, reste.
                self.env["ir.config_parameter"].sudo().set_param(
                    POLICY_PARAM, "ask"
                )
                config = self._report(
                    token, self._pilot(local, choice=choice)
                )["config"]
                self.assertNotIn("ask", config)
                self.assertEqual(workstation.config_first_choice, policy)
                self.assertEqual(bool(workstation.config_line_ids), adopted)

    def test_ask_ends_after_a_choice_or_an_applied_result(self):
        local = self._settings(games="off")
        by_choice, token = self._workstation()
        self.assertIn("ask", self._report(token, self._pilot(local))["config"])
        self._report(token, self._pilot(local, choice="take_odoo"))
        self.assertNotIn(
            "ask", self._report(token, self._pilot(local))["config"]
        )
        self.assertFalse(by_choice.config_ask)

        by_result, token = self._workstation()
        revision = self._report(token, self._pilot(local))["config"][
            "revision"
        ]
        result = self._result(revision)
        config = self._report(
            token, self._pilot(self._settings(), revision, result)
        )["config"]
        self.assertNotIn("ask", config)
        self.assertEqual(by_result.config_first_choice, "take_odoo")
        # Un choix `keep_local` tardif ne compte plus.
        self._report(
            token, self._pilot(self._settings(), revision, choice="keep_local")
        )
        self.assertEqual(by_result.config_first_choice, "take_odoo")
        self.assertFalse(self._events(by_result, "config_adopted"))

    # -- refusals --------------------------------------------------------

    def _assert_refused(self, workstation, token, payload):
        before = (
            workstation.config_state,
            workstation.config_revision,
            workstation.last_report,
            workstation.deck_plugins,
        )
        body = self._post(token, payload, status=400)
        self.assertEqual(body["error"], "bad_request")
        workstation.invalidate_recordset()
        self.assertEqual(
            (
                workstation.config_state,
                workstation.config_revision,
                workstation.last_report,
                workstation.deck_plugins,
            ),
            before,
        )

    def test_an_unknown_choice_is_400(self):
        workstation, token = self._workstation()
        for choice in ("both", "", 1, ["keep_local"]):
            with self.subTest(choice=choice):
                config = self._pilot(self._settings(games="off"))
                config["choice"] = choice
                self._assert_refused(workstation, token, self._payload(config))
        self.assertFalse(workstation.config_first_choice)

    def test_out_of_schema_current_or_result_is_400(self):
        workstation, token = self._workstation()
        revision = self._report(token, self._pilot())["config"]["revision"]
        bad_current = (
            {"deck_program": "/bin/sh"},
            {"deck_program": "Tiler"},
            {"games": "maybe"},
            {"games": True},
            {"plugins_off": ["Sound"]},
            {"plugins_off": "sound"},
            {"plugins_off": ["p%d" % index for index in range(65)]},
            {"session_refresh_sec": 0.4},
            {"session_refresh_sec": 60.1},
            {"session_refresh_sec": "5"},
            {"session_refresh_sec": True},
        )
        for current in bad_current:
            with self.subTest(current=current):
                self._assert_refused(
                    workstation, token, self._payload(self._pilot(current))
                )
        good = self._result(revision)
        bad_results = (
            "applied",
            dict(good, revision=-1),
            dict(good, revision="1"),
            dict(good, revision=True),
            dict(good, status="done"),
            dict(good, status="refused", reason="because"),
            dict(good, status="refused", reason="invalid:key_layouts"),
            dict(good, status="refused", reason="x" * 257),
            dict(good, status="refused", reason=["write_failed"]),
            dict(good, at="yesterday"),
            dict(good, at=None),
        )
        for result in bad_results:
            with self.subTest(result=result):
                self._assert_refused(
                    workstation,
                    token,
                    self._payload(self._pilot(result=result)),
                )
        bad_frames = (
            [],
            "pilot",
            {"pilot": "yes"},
            {"pilot": None},
            dict(self._pilot(), current=["tiler"]),
            dict(self._pilot(), current=None),
            dict(self._pilot(), revision_applied=-1),
            dict(self._pilot(), revision_applied="1"),
            dict(self._pilot(), revision_applied=2**31),
        )
        for config in bad_frames:
            with self.subTest(config=config):
                self._assert_refused(workstation, token, self._payload(config))
        self.assertEqual(workstation.config_state, "pending")
        self.assertFalse(
            self.Event.search(
                [
                    ("workstation_id", "=", workstation.id),
                    ("kind", "in", CONFIG_KINDS),
                ]
            )
        )

    def test_a_client_cannot_send_config_kinds(self):
        workstation, token = self._workstation()
        for kind in CONFIG_KINDS:
            with self.subTest(kind=kind):
                event = {
                    "uuid": "00000000-0000-4000-8000-%012d"
                    % CONFIG_KINDS.index(kind),
                    "kind": kind,
                    "at": AT,
                    "serial": "SN-CFG",
                    "usb_product_id": "0084",
                    "usb_path": "1-2",
                    "service_state": "active",
                }
                self._assert_refused(
                    workstation,
                    token,
                    self._payload(self._pilot(), events=[event]),
                )
        self.assertFalse(workstation.event_ids)

    def test_deck_plugins_are_stored_and_bounded(self):
        workstation, token = self._workstation()
        self._report(token, deck_plugins=["sound", "timers", "sound"])
        self.assertEqual(workstation.deck_plugins, "sound,timers")
        # Une remontée 1.0 ne porte pas la clé : la liste reste.
        payload = self._payload(protocol="1.0")
        del payload["state"]["deck_plugins"]
        self._post(token, payload)
        self.assertEqual(workstation.deck_plugins, "sound,timers")
        bounded = ["p%d" % index for index in range(128)]
        self._report(token, deck_plugins=bounded)
        self.assertEqual(workstation.deck_plugins, ",".join(bounded))
        for plugins in (
            bounded + ["p128"],
            ["Sound"],
            ["sound/../x"],
            ["a" * 65],
            "sound",
            [1],
        ):
            with self.subTest(plugins=plugins):
                self._assert_refused(
                    workstation, token, self._payload(deck_plugins=plugins)
                )
        self._report(token, deck_plugins=[])
        self.assertFalse(workstation.deck_plugins)

    # -- access ----------------------------------------------------------

    def test_only_the_owner_reads_the_config_of_a_workstation(self):
        workstation, token = self._workstation()
        revision = self._report(token, self._pilot())["config"]["revision"]
        self._report(
            token, self._pilot(self._settings(), revision, self._result(1))
        )
        fields = [
            "config_state",
            "config_revision",
            "config_offered",
            "config_applied",
            "config_ask",
            "deck_plugins",
        ]
        own = workstation.with_user(self.user_a).read(fields)
        self.assertEqual(own[0]["config_state"], "applied")
        self.assertTrue(
            self.Event.with_user(self.user_a).search(
                [
                    ("workstation_id", "=", workstation.id),
                    ("kind", "=", "config_applied"),
                ]
            )
        )
        managed = workstation.with_user(self.manager).read(fields)
        self.assertEqual(managed[0]["config_revision"], revision)
        with self.assertRaises(AccessError):
            workstation.with_user(self.user_b).read(fields)
        self.assertFalse(
            self.Event.with_user(self.user_b).search(
                [("workstation_id", "=", workstation.id)]
            )
        )
        for values in (
            {"config_state": "applied"},
            {"config_revision": 9},
            {"config_first_choice": "keep_local"},
            {"config_ask": "games"},
            {"deck_plugins": "x"},
        ):
            with self.subTest(values=values):
                with self.assertRaises(AccessError):
                    workstation.with_user(self.user_a).write(values)
