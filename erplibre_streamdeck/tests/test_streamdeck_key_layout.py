# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib
import json
import secrets
from datetime import timedelta

import polib
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck"
MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
KEYS = ("deck_program", "plugins_off", "session_refresh_sec", "games")
AT = "2026-01-01T10:00:00Z"
CATALOG = {
    "format": 1,
    "actions": ["plugin:timers", "plugin:sound", "tiles", "empty"],
    "icons": ["timer", "sound", "tile"],
    "models": {
        "0084": {"cols": 4, "rows": 2, "keys": 8},
        "0063": {"cols": 3, "rows": 2, "keys": 6},
    },
}
DECK_PLUS = {
    "serial": "SN-PLUS",
    "usb_product_id": "0084",
    "usb_path": "1-1",
    "firmware": None,
}
DECK_MINI = {
    "serial": "SN-MINI",
    "usb_product_id": "0063",
    "usb_path": "1-2",
    "firmware": None,
}
# The terms of the key layouts and their fr_CA text.
LAYOUT_TERMS = {
    "Key layouts": "Dispositions des touches",
    "Key layout": "Disposition des touches",
    "Catalog": "Catalogue",
    "Create the keys": "Créer les touches",
    "Plugins without a key": "Plugins sans touche",
    "Kept in the workstation's file": "Gardée dans le fichier du poste",
    "Key layouts of the connected decks": (
        "Dispositions des touches des decks branchés"
    ),
}


def layout_hash(layout):
    """SHA-256 of the canonical JSON of one model's layout, as the
    workstation hashes its keymap.json (CONTRACT.md of the extension):
    Python's json.dumps with sorted keys and no spaces, every character
    outside ASCII escaped."""
    text = json.dumps(layout, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


class KeyLayoutCase(TransactionCase):
    """Données communes : un catalogue remonté, deux employés A et B, un
    gestionnaire M, le profil P qui fixe `games` et une disposition du
    Stream Deck + (0084)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["streamdeck.service"]
        cls.Workstation = cls.env["streamdeck.workstation"]
        cls.Item = cls.env["streamdeck.catalog.item"]
        cls.Layout = cls.env["streamdeck.key.layout"]
        cls.Key = cls.env["streamdeck.key.layout.key"]
        cls.Line = cls.env["streamdeck.config.line"]
        cls.Event = cls.env["streamdeck.event"]
        cls.schema = cls.env["streamdeck.config.schema"]
        cls.user_a = new_test_user(
            cls.env,
            login="zz_sd_kl_a",
            name="Employee A",
            groups="base.group_user",
        )
        cls.user_b = new_test_user(
            cls.env,
            login="zz_sd_kl_b",
            name="Employee B",
            groups="base.group_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_kl_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        cls.Item._take(CATALOG, "2026-01-01 10:00:00")
        cls.profile = cls.env["streamdeck.config.profile"].create(
            {"name": "P"}
        )
        cls.Line.create(
            {"profile_id": cls.profile.id, "key": "games", "value": '"on"'}
        )
        cls.layout = cls._layout(
            {"profile_id": cls.profile.id},
            (0, "plugin:timers", "timer", "Minuteries"),
            (1, "tiles", None, None),
            (2, None, None, None),
        )

    @classmethod
    def _item(cls, kind, value):
        return cls.Item.search([("kind", "=", kind), ("value", "=", value)])

    @classmethod
    def _layout(cls, parent, *keys, product="0084", env=None):
        """A layout of `product` under `parent`, with `keys` as
        `(index, action, icon, label)`; None leaves a field empty."""
        Layout = env["streamdeck.key.layout"] if env else cls.Layout
        return Layout.create(
            dict(
                parent,
                usb_product_id=product,
                key_ids=[
                    Command.create(cls._key_values(*key)) for key in keys
                ],
            )
        )

    @classmethod
    def _key_values(cls, index, action=None, icon=None, label=None):
        values = {"key_index": index}
        if action:
            values["action_id"] = cls._item("action", action).id
        if icon:
            values["icon_id"] = cls._item("icon", icon).id
        if label:
            values["label"] = label
        return values

    def _workstation(self, user=None, profile=None, decks=(DECK_PLUS,)):
        """An enrolled workstation of `user` (A by default) with `decks`
        connected, and its token."""
        token = secrets.token_urlsafe(32)
        user = user or self.user_a
        digest = hashlib.sha256(token.encode()).hexdigest()
        workstation = self.Workstation.create(
            {
                "user_id": user.id,
                "name": "host-%s" % token[:6],
                "fingerprint": digest,
                "token_hash": digest,
                "config_profile_id": (profile or self.profile).id,
            }
        )
        for deck in decks:
            self.env["streamdeck.device"].create(
                {
                    "key": "sn:%s-%s" % (deck["serial"], token[:6]),
                    "serial": "%s-%s" % (deck["serial"], token[:6]),
                    "usb_product_id": deck["usb_product_id"],
                    "workstation_id": workstation.id,
                    "connected": True,
                }
            )
        return workstation, token

    @staticmethod
    def _decks(workstation):
        return [
            {
                "serial": device.serial,
                "usb_product_id": device.usb_product_id,
                "usb_path": "1-%d" % device.id,
                "firmware": None,
            }
            for device in workstation.device_ids
            if device.connected
        ]

    @staticmethod
    def _pilot(layouts=None, applied=None, result=None, **current):
        values = dict.fromkeys(KEYS)
        values.update(current)
        values["key_layouts"] = layouts
        return {
            "pilot": True,
            "revision_applied": applied,
            "current": values,
            "result": result,
            "choice": None,
        }

    @staticmethod
    def _result(revision, status="applied", reason=None):
        return {
            "revision": revision,
            "status": status,
            "reason": reason,
            "at": AT,
        }

    def _report(
        self, token, workstation, config=None, protocol="1.2", catalog=None
    ):
        """`(status, body)` of a report of `workstation` carrying `config`
        and the catalog."""
        state = {
            "hostname": "host",
            "os": {"name": "Debian GNU/Linux", "version": "13"},
            "gnome_shell": "48.4",
            "extension_version": "1.6.0",
            "contract_version": "1.4",
            "erplibre": None,
            "deck_program": "tiler",
            "service_state": "active",
            "deck_plugins": ["timers", "sound"],
            "deck_catalog": CATALOG if catalog is None else catalog,
            "decks": self._decks(workstation),
        }
        payload = {
            "protocol": protocol,
            "state": state,
            "events": [],
            "lost_events": 0,
        }
        if config is not None:
            payload["config"] = config
        return self.Service.report(token, payload)

    def _ok(self, token, workstation, config=None, **kwargs):
        status, body = self._report(token, workstation, config, **kwargs)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["protocol"], "1.2")
        return body

    def _events(self, workstation, kind):
        return self.Event.search(
            [("workstation_id", "=", workstation.id), ("kind", "=", kind)]
        )


@tagged("post_install", "-at_install")
class TestStreamdeckKeyLayout(KeyLayoutCase):
    """La disposition des touches d'accueil, par modèle de deck : le
    catalogue que les postes remontent, l'éditeur, les couches et leur
    verrou, la livraison au battement et l'écart local."""

    # -- catalog ---------------------------------------------------------

    def test_the_catalog_grows_from_reports_and_keeps_old_items(self):
        workstation, token = self._workstation()
        timers = self._item("action", "plugin:timers")
        self.assertEqual(str(timers.last_seen), "2026-01-01 10:00:00")
        newer = {
            "format": 1,
            "actions": ["plugin:clock", "tiles", "empty"],
            "icons": ["clock"],
            "models": {"0084": {"cols": 4, "rows": 2, "keys": 8}},
        }
        self._ok(token, workstation, catalog=newer)
        clock = self._item("action", "plugin:clock")
        self.assertTrue(clock)
        self.assertTrue(self._item("icon", "clock"))
        self.assertGreater(clock.last_seen, timers.last_seen)
        # An item no report names any more stays, dated when last seen.
        self.assertTrue(timers.exists())
        self.assertEqual(str(timers.last_seen), "2026-01-01 10:00:00")
        self.assertEqual(
            self._item("model", "0084").read(["cols", "rows", "key_count"])[0],
            {
                "id": self._item("model", "0084").id,
                "cols": 4,
                "rows": 2,
                "key_count": 8,
            },
        )
        self.assertEqual(
            self.Item.search_count(
                [("kind", "=", "action"), ("value", "=", "tiles")]
            ),
            1,
        )
        # A date moves once an hour at most: every workstation reports
        # the same items.
        recent = fields.Datetime.now() - timedelta(minutes=30)
        old = fields.Datetime.now() - timedelta(hours=2)
        clock.last_seen = recent
        self._item("icon", "clock").last_seen = old
        self._ok(token, workstation, catalog=newer)
        self.assertEqual(clock.last_seen, recent)
        self.assertGreater(self._item("icon", "clock").last_seen, old)
        # A catalog of another format, or in a report of protocol 1.1, is
        # not read; an unknown action or icon is skipped.
        for protocol, catalog in (
            ("1.2", dict(newer, format=2, actions=["plugin:later"])),
            ("1.1", dict(newer, actions=["plugin:older"])),
            ("1.2", dict(newer, actions=["page:other", "plugin:Bad"])),
        ):
            with self.subTest(protocol=protocol, catalog=catalog):
                self._ok(
                    token, workstation, protocol=protocol, catalog=catalog
                )
                for value in ("plugin:later", "plugin:older", "page:other"):
                    self.assertFalse(self._item("action", value))

    def test_a_malformed_catalog_is_a_bad_request(self):
        workstation, token = self._workstation()
        for catalog in (
            "catalog",
            {"format": "1", "actions": [], "icons": [], "models": {}},
            dict(CATALOG, actions="tiles"),
            dict(CATALOG, actions=[7]),
            dict(CATALOG, models=[]),
            dict(CATALOG, models={"0084": {"cols": 4, "rows": 2}}),
            dict(
                CATALOG, models={"0084": {"cols": True, "rows": 2, "keys": 1}}
            ),
            dict(
                CATALOG, models={"0084": {"cols": 257, "rows": 1, "keys": 1}}
            ),
        ):
            with self.subTest(catalog=catalog):
                status, body = self._report(
                    token, workstation, catalog=catalog
                )
                self.assertEqual(
                    (status, body.get("error")), (400, "bad_request")
                )
        # The extension sends any geometry from 0 to 256 and any number
        # of items within 32 KiB: a geometry no key fits is skipped.
        many = ["i%d" % index for index in range(1000)]
        self._ok(
            token,
            workstation,
            catalog=dict(
                CATALOG,
                icons=many,
                models={
                    "0063": {"cols": 0, "rows": 2, "keys": 0},
                    "006c": {"cols": 4, "rows": 2, "keys": 9},
                    "00aa": {"cols": 16, "rows": 2, "keys": 32},
                },
            ),
        )
        self.assertTrue(self._item("icon", "i999"))
        self.assertEqual(self._item("model", "0063").key_count, 6)
        self.assertFalse(self._item("model", "006c"))
        self.assertEqual(self._item("model", "00aa").key_count, 32)
        # Beyond 32 KiB, the catalog is dropped as the extension drops it.
        huge = dict(CATALOG, actions=["plugin:%s" % ("x" * 60)] * 600)
        self._ok(token, workstation, catalog=huge)
        self.assertFalse(self._item("action", "plugin:%s" % ("x" * 60)))

    # -- editor ----------------------------------------------------------

    def test_create_keys_makes_one_line_per_key_of_the_model(self):
        layout = self._layout({"profile_id": self.profile.id}, product="0063")
        layout.action_create_keys()
        self.assertEqual(layout.key_ids.mapped("key_index"), list(range(6)))
        self.assertFalse(layout.key_ids.mapped("action_id"))
        # Again: the missing keys only.
        layout.key_ids.filtered(lambda key: key.key_index == 3).unlink()
        layout.action_create_keys()
        self.assertEqual(
            sorted(layout.key_ids.mapped("key_index")), list(range(6))
        )
        # A model no catalog describes takes the module's table.
        self.assertFalse(self._item("model", "006c"))
        xl = self._layout({"profile_id": self.profile.id}, product="006c")
        xl.action_create_keys()
        self.assertEqual(len(xl.key_ids), 32)
        self.assertEqual((xl.cols, xl.rows, xl.key_count), (8, 4, 32))
        # A model neither knows has no keys to create.
        unknown = self._layout({"profile_id": self.profile.id}, product="ffff")
        with self.assertRaises(ValidationError):
            unknown.action_create_keys()

    def test_a_key_index_outside_the_model_is_refused(self):
        for values in (
            {"key_index": 8},
            {"key_index": -1},
            self._key_values(4, "plugin:sound", label="x" * 17),
            self._key_values(4, "plugin:sound", label="a\nb"),
            {"key_index": 4, "action_id": self._item("icon", "timer").id},
            {"key_index": 4, "icon_id": self._item("action", "tiles").id},
            # A plugin has one home key.
            self._key_values(4, "plugin:timers"),
        ):
            with self.subTest(values=values), self.assertRaises(
                ValidationError
            ):
                self.Key.create(dict(values, layout_id=self.layout.id))
        key = self.Key.create(
            dict(
                self._key_values(7, "empty", label="é" * 16),
                layout_id=self.layout.id,
            )
        )
        self.assertEqual(key.label, "é" * 16)
        with self.assertRaises(ValidationError):
            key.key_index = 8
        with self.assertRaises(ValidationError):
            self.layout.usb_product_id = "zz84"
        # A model whose keys no longer fit is refused too.
        with self.assertRaises(ValidationError):
            self.layout.usb_product_id = "0086"

    # -- layers ----------------------------------------------------------

    def test_a_layout_lock_stops_lower_layouts(self):
        workstation, _token = self._workstation()
        model = self.env["streamdeck.config.model"].create(
            {"usb_product_id": "0084"}
        )
        model_layout = self._layout(
            {"model_id": model.id}, (0, "plugin:sound", None, None)
        )
        own = self._layout(
            {"workstation_id": workstation.id}, (0, "empty", None, None)
        )

        def effective():
            entry = self.schema._effective_layouts(workstation)["0084"]
            return entry["layout"], entry["source"], entry["locked"]

        self.assertEqual(effective(), (own, "workstation", False))
        model_layout.locked = True
        self.assertEqual(effective(), (model_layout, "model", True))
        self.layout.locked = True
        self.assertEqual(effective(), (self.layout, "profile", True))
        # A layout of another model never stands for this one.
        self.layout.locked = False
        model_layout.locked = False
        own.unlink()
        self.assertEqual(effective(), (model_layout, "model", False))

    # -- wire ------------------------------------------------------------

    def test_key_layouts_go_only_for_connected_models_and_change_the_hash(
        self,
    ):
        self._layout(
            {"profile_id": self.profile.id},
            (0, "empty", None, None),
            product="0063",
        )
        workstation, token = self._workstation()
        body = self._ok(token, workstation, self._pilot())
        plus = {
            "keys": [
                {
                    "key": 0,
                    "action": "plugin:timers",
                    "icon": "timer",
                    "label": "Minuteries",
                },
                {"key": 1, "action": "tiles"},
            ]
        }
        settings = {"games": "on", "key_layouts": {"0084": plus}}
        self.assertEqual(
            body["config"],
            {
                "revision": 1,
                "hash": self.schema._hash(settings),
                "settings": settings,
                "locked": [],
            },
        )
        # A protocol 1.1 extension does not know the layouts: it gets the
        # settings alone, under another hash.
        old, old_token = self._workstation()
        old_body = self._ok(old_token, old, self._pilot(), protocol="1.1")
        self.assertEqual(old_body["config"]["settings"], {"games": "on"})

        # A key changed in the layout is a new revision.
        self.layout.key_ids.filtered(lambda k: k.key_index == 0).label = "T"
        moved = self._ok(token, workstation, self._pilot())["config"]
        self.assertEqual(moved["revision"], 2)
        self.assertNotEqual(moved["hash"], body["config"]["hash"])
        self.assertEqual(
            moved["settings"]["key_layouts"]["0084"]["keys"][0]["label"], "T"
        )
        # A second deck model connected brings its layout.
        self.env["streamdeck.device"].create(
            {
                "key": "sn:SN-MINI-1",
                "serial": "SN-MINI-1",
                "usb_product_id": "0063",
                "workstation_id": workstation.id,
                "connected": True,
            }
        )
        both = self._ok(token, workstation, self._pilot())["config"]
        self.assertEqual(
            sorted(both["settings"]["key_layouts"]), ["0063", "0084"]
        )
        self.assertEqual(both["revision"], 3)
        # A locked layout locks the key_layouts setting.
        self.layout.locked = True
        locked = self._ok(token, workstation, self._pilot())["config"]
        self.assertEqual(locked["locked"], ["key_layouts"])
        self.assertEqual(locked["revision"], 3)

    def test_a_refusal_of_the_layouts_is_recorded(self):
        workstation, token = self._workstation()
        revision = self._ok(token, workstation, self._pilot())["config"][
            "revision"
        ]
        result = self._result(revision, "refused", "invalid:key_layouts")
        self._ok(token, workstation, self._pilot(result=result))
        self.assertEqual(workstation.config_state, "refused")
        self.assertEqual(workstation.config_reason, "invalid:key_layouts")

    def test_a_malformed_current_key_layouts_is_a_bad_request(self):
        workstation, token = self._workstation()
        for layouts in (
            "0084",
            {"84": None},
            {"0084": "abc"},
            {"0084": 7},
            {"%04x" % n: None for n in range(200)},
        ):
            with self.subTest(layouts=layouts):
                status, body = self._report(
                    token, workstation, self._pilot(layouts)
                )
                self.assertEqual(
                    (status, body.get("error")), (400, "bad_request")
                )

    def test_the_layout_hash_is_the_workstation_s(self):
        # Python's json.dumps, sorted keys, no spaces, non-ASCII escaped:
        # the form CONTRACT.md of the extension gives.
        layout = {"keys": [{"key": 0, "action": "tiles", "label": "Été"}]}
        text = (
            '{"keys":[{"action":"tiles","key":0,'
            '"label":"\\u00c9t\\u00e9"}]}'
        )
        self.assertEqual(
            self.schema._layout_hash(layout),
            hashlib.sha256(text.encode()).hexdigest(),
        )

    def test_a_plugin_turned_off_is_sent_as_a_black_key(self):
        # The extension refuses a layout that names a plugin turned off:
        # Odoo sends its key black, as the deck program leaves it.
        workstation, token = self._workstation()
        self.Line.create(
            {
                "profile_id": self.profile.id,
                "key": "plugins_off",
                "value": '["timers"]',
            }
        )
        keys = self._ok(token, workstation, self._pilot())["config"][
            "settings"
        ]["key_layouts"]["0084"]["keys"]
        self.assertEqual(
            keys,
            [{"key": 0, "action": "empty"}, {"key": 1, "action": "tiles"}],
        )
        # Not set by Odoo, the file's own list counts.
        self.profile.line_ids.filtered(
            lambda line: line.key == "plugins_off"
        ).unlink()
        other, other_token = self._workstation()
        keys = self._ok(
            other_token, other, self._pilot(plugins_off=["timers"])
        )["config"]["settings"]["key_layouts"]["0084"]["keys"]
        self.assertEqual(keys[0], {"key": 0, "action": "empty"})
        keys = self._ok(token, workstation, self._pilot())["config"][
            "settings"
        ]["key_layouts"]["0084"]["keys"]
        self.assertEqual(keys[0]["action"], "plugin:timers")

    def _applied(self, token, workstation):
        """Report then apply the offered revision; return it with the
        layout of 0084 it offered."""
        config = self._ok(token, workstation, self._pilot())["config"]
        revision = config["revision"]
        layouts = {
            pid: layout_hash(layout)
            for pid, layout in config["settings"]
            .get("key_layouts", {})
            .items()
        }
        self._ok(
            token,
            workstation,
            self._pilot(layouts, None, self._result(revision), games="on"),
        )
        self.assertEqual(workstation.config_state, "applied")
        return revision, layouts

    def test_a_free_local_layout_is_adopted_a_locked_one_reoffered(self):
        workstation, token = self._workstation()
        revision, layouts = self._applied(token, workstation)
        self.assertEqual(len(layouts), 1)
        # Nothing changed in the file: nothing happens.
        self._ok(
            token, workstation, self._pilot(layouts, revision, games="on")
        )
        self.assertEqual(workstation.config_revision, revision)

        # A free layout edited by hand on the workstation: adopted as the
        # workstation's own layout, kept in its file and no longer sent.
        edited = {"0084": "e" * 64}
        body = self._ok(
            token, workstation, self._pilot(edited, revision, games="on")
        )
        own = workstation.layout_ids
        self.assertEqual(len(own), 1)
        self.assertEqual(
            (own.usb_product_id, own.in_file, own.file_hash, own.source),
            ("0084", True, "e" * 64, "local"),
        )
        adopted = self._events(workstation, "config_adopted")
        self.assertEqual(adopted.mapped("config_keys"), ["key_layouts:0084"])
        self.assertEqual(body["config"]["settings"], {"games": "on"})
        adopted_revision = body["config"]["revision"]
        self.assertEqual(adopted_revision, revision + 1)
        # The extension finds the revision in place and says so silently.
        self._ok(
            token,
            workstation,
            self._pilot(
                edited, revision, self._result(adopted_revision), games="on"
            ),
        )
        self.assertEqual(workstation.config_state, "applied")
        # Further hand edits are the workstation's: nothing adopted again.
        self._ok(
            token,
            workstation,
            self._pilot({"0084": "f" * 64}, adopted_revision, games="on"),
        )
        self.assertEqual(workstation.config_revision, adopted_revision)
        self.assertEqual(len(self._events(workstation, "config_adopted")), 1)

        # The manager locks the profile's layout: it is offered again,
        # over the kept file.
        self.layout.locked = True
        offered = self._ok(
            token,
            workstation,
            self._pilot({"0084": "f" * 64}, adopted_revision, games="on"),
        )["config"]
        self.assertIn("0084", offered["settings"]["key_layouts"])
        self.assertEqual(offered["locked"], ["key_layouts"])
        locked_revision = offered["revision"]
        wanted = {
            "0084": layout_hash(offered["settings"]["key_layouts"]["0084"])
        }
        self._ok(
            token,
            workstation,
            self._pilot(
                wanted,
                adopted_revision,
                self._result(locked_revision),
                games="on",
            ),
        )
        self.assertEqual(workstation.config_state, "applied")
        # A hand edit of a locked layout is offered again, same values.
        drift = self._ok(
            token,
            workstation,
            self._pilot({"0084": "d" * 64}, locked_revision, games="on"),
        )["config"]
        self.assertEqual(drift["revision"], locked_revision + 1)
        self.assertEqual(drift["settings"], offered["settings"])
        self.assertEqual(workstation.config_state, "drift")
        self.assertEqual(
            self._events(workstation, "config_drift").mapped("config_keys"),
            ["key_layouts:0084"],
        )
        self.assertEqual(len(self._events(workstation, "config_adopted")), 1)

    # -- preview ---------------------------------------------------------

    def test_the_preview_warns_of_plugins_without_a_key(self):
        self.assertEqual(self.layout.missing_plugins, "sound")
        html = str(self.layout.preview_html)
        tree = etree.fromstring("<div>%s</div>" % html, etree.HTMLParser())
        self.assertEqual(len(tree.xpath("//table//tr")), 2)
        self.assertEqual(len(tree.xpath("//table//td")), 8)
        self.assertIn("Minuteries", html)
        self.assertIn("timer", html)
        self.assertIn("sound", html)
        # Every plugin with its key: no warning.
        self.Key.create(
            dict(self._key_values(5, "plugin:sound"), layout_id=self.layout.id)
        )
        self.assertFalse(self.layout.missing_plugins)
        self.assertNotIn("alert", str(self.layout.preview_html))

    # -- access ----------------------------------------------------------

    def test_an_employee_edits_a_free_layout_of_their_workstation_only(self):
        ws_a, _token = self._workstation()
        ws_b, _token_b = self._workstation(self.user_b)
        env_a = self.env(user=self.user_a)
        own = self._layout(
            {"workstation_id": ws_a.id},
            (0, "plugin:sound", None, None),
            env=env_a,
        )
        self.assertEqual(own.source, "employee")
        key = own.with_user(self.user_a).key_ids
        key.label = "Son"
        key.write(self._key_values(0, "tiles"))
        own.with_user(self.user_a).action_create_keys()
        self.assertEqual(len(own.key_ids), 8)
        # The profile's layout and the model layers are read, not written.
        profile_layout = self.layout.with_user(self.user_a)
        self.assertEqual(profile_layout.key_ids[0].label, "Minuteries")
        for action in (
            lambda: profile_layout.write({"locked": False}),
            lambda: profile_layout.key_ids[0].write({"label": "x"}),
            lambda: own.with_user(self.user_a).write({"locked": True}),
            lambda: own.with_user(self.user_a).write({"source": "manager"}),
            lambda: own.with_user(self.user_a).write({"in_file": True}),
            lambda: self._layout(
                {"workstation_id": ws_b.id}, product="0063", env=env_a
            ),
            lambda: self._layout(
                {"profile_id": self.profile.id}, product="0063", env=env_a
            ),
        ):
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()
        # The layout of another employee's workstation stays closed.
        other = self._layout(
            {"workstation_id": ws_b.id}, (0, "tiles", None, None)
        )
        with self.assertRaises(AccessError):
            other.with_user(self.user_a).key_ids.read(["label"])
        with self.assertRaises(AccessError):
            other.with_user(self.user_a).unlink()
        own.with_user(self.user_a).unlink()
        self.assertFalse(own.exists())

    def test_an_employee_cannot_edit_a_locked_layout(self):
        ws_a, _token = self._workstation()
        env_a = self.env(user=self.user_a)
        locked = self._layout(
            {"workstation_id": ws_a.id, "locked": True},
            (0, "tiles", None, None),
        )
        as_a = locked.with_user(self.user_a)
        self.assertTrue(as_a.key_ids.read(["label"]))
        for action in (
            lambda: as_a.write({"usb_product_id": "0063"}),
            lambda: as_a.key_ids.write({"label": "x"}),
            lambda: as_a.key_ids.unlink(),
            lambda: self.env["streamdeck.key.layout.key"]
            .with_user(self.user_a)
            .create({"layout_id": locked.id, "key_index": 3}),
            lambda: as_a.action_create_keys(),
            lambda: as_a.unlink(),
        ):
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()
        locked.unlink()
        # A layout the profile locks for this model cannot be replaced by
        # one of the workstation, with keys or without.
        self.layout.locked = True
        for keys in ([(0, "tiles", None, None)], []):
            with self.subTest(keys=keys), self.assertRaises(AccessError):
                self._layout({"workstation_id": ws_a.id}, *keys, env=env_a)
        self.layout.locked = False
        free = self._layout({"workstation_id": ws_a.id}, env=env_a)
        self.layout.locked = True
        with self.assertRaises(AccessError):
            free.with_user(self.user_a).action_create_keys()


@tagged("post_install", "-at_install")
class TestStreamdeckKeyLayoutViews(KeyLayoutCase):
    """L'éditeur et ce que le poste en montre, en anglais et en fr_CA."""

    def _arch(self, model, view_type, user=None):
        Model = self.env[model].with_user(user) if user else self.env[model]
        arch = Model.get_views([(False, view_type)])["views"][view_type][
            "arch"
        ]
        return etree.fromstring(arch)

    def test_the_editor_lists_keys_with_catalog_choices_and_a_preview(self):
        for user in (self.manager, self.user_a):
            with self.subTest(user=user.login):
                form = self._arch("streamdeck.key.layout", "form", user)
                self.assertTrue(
                    form.xpath("//button[@name='action_create_keys']")
                )
                self.assertTrue(form.xpath("//field[@name='preview_html']"))
                (keys,) = form.xpath("//field[@name='key_ids']")
                for name in ("key_index", "action_id", "icon_id", "label"):
                    self.assertTrue(keys.xpath(".//field[@name='%s']" % name))
                (action,) = keys.xpath(".//field[@name='action_id']")
                self.assertIn("action", action.get("domain"))

    def test_the_configuration_tab_shows_the_layouts_of_connected_decks(self):
        workstation, _token = self._workstation()
        form = self._arch("streamdeck.workstation", "form", self.user_a)
        (page,) = form.xpath("//page[@name='configuration']")
        self.assertTrue(page.xpath(".//field[@name='config_layouts_html']"))
        self.assertTrue(page.xpath(".//field[@name='layout_ids']"))
        html = str(workstation.with_user(self.user_a).config_layouts_html)
        self.assertIn("Minuteries", html)
        self.assertIn("0084", html)
        for xmlid in (
            "menu_streamdeck_config_layouts",
            "menu_streamdeck_config_catalog",
        ):
            menu = self.env.ref("%s.%s" % (MODULE, xmlid))
            with self.subTest(menu=xmlid):
                visible = self.env["ir.ui.menu"].with_user(self.user_a)
                self.assertNotIn(menu.id, visible._visible_menu_ids())
                visible = self.env["ir.ui.menu"].with_user(self.manager)
                self.assertIn(menu.id, visible._visible_menu_ids())
        for model in ("streamdeck.config.profile", "streamdeck.config.model"):
            with self.subTest(model=model):
                form = self._arch(model, "form", self.manager)
                self.assertTrue(form.xpath("//field[@name='layout_ids']"))

    def test_every_key_layout_term_has_its_fr_CA_text(self):
        french = {
            entry.msgid: entry.msgstr
            for entry in polib.pofile(file_path("%s/i18n/fr_CA.po" % MODULE))
        }
        for english, translated in LAYOUT_TERMS.items():
            with self.subTest(term=english):
                self.assertEqual(french.get(english), translated)
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            [MODULE], ["fr_CA"], overwrite=True
        )
        fr = self.env(context={"lang": "fr_CA"})
        self.assertEqual(
            fr.ref("%s.menu_streamdeck_config_layouts" % MODULE).name,
            "Dispositions des touches",
        )
        self.assertEqual(
            fr["streamdeck.key.layout"].fields_get(["missing_plugins"])[
                "missing_plugins"
            ]["string"],
            "Plugins sans touche",
        )
