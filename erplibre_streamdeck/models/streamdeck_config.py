# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import hashlib
import json
import logging
import math
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .res_config_settings import FIRST_PILOT_POLICIES, PARAM_PREFIX
from .streamdeck_device import usb_model_name
from .streamdeck_workstation import MANAGER_GROUP

_logger = logging.getLogger(__name__)

# The closed list of settings Odoo may manage on a workstation, in the
# order of the wire and of the effective table. Each is one line of the
# workstation's streamdeck.conf (CONTRACT.md of the GNOME extension).
KEYS = ("deck_program", "plugins_off", "session_refresh_sec", "games")
KEY_SELECTION = [
    ("deck_program", "Deck program"),
    ("plugins_off", "Plugins turned off"),
    ("session_refresh_sec", "Session refresh (seconds)"),
    ("games", "Games"),
]

PROGRAMS = ("tiler", "controller", "none")
GAMES_VALUES = ("on", "off")
SESSION_REFRESH_RANGE = (0.5, 60.0)
PLUGIN_ID_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
PLUGINS_OFF_MAX = 64

SOURCES = [
    ("manager", "Manager"),
    ("employee", "Employee"),
    ("local", "Workstation file"),
]
PRODUCT_ID_RE = re.compile(r"[0-9a-f]{4}")


class StreamdeckConfigSchema(models.AbstractModel):
    """The schema of the managed settings and the effective configuration
    of a workstation.

    `_validate` holds one rule per key and is the only judge of a value:
    the lines call it on every write, the report route on every value it
    receives. `_effective` folds the layers profile < deck model(s) <
    workstation, a lock stopping the fold of its key. `_hash` is the
    fingerprint of a settings dict, independent of its key order.
    """

    _name = "streamdeck.config.schema"
    _description = "Stream Deck configuration schema"

    KEYS = KEYS

    def _invalid(self, key):
        return ValidationError(
            _("Invalid value for the Stream Deck setting %(key)s.", key=key)
        )

    def _validate(self, key, value):
        """Return `value` normalised for `key`, or raise ValidationError.

        `deck_program` and `games` are one of their strings; `plugins_off`
        is a list of at most PLUGINS_OFF_MAX plugin ids, its order kept
        and its duplicates dropped; `session_refresh_sec` is a number,
        returned as a float, within SESSION_REFRESH_RANGE. A boolean is
        not a number, and an unknown key is invalid.
        """
        if key == "deck_program":
            if isinstance(value, str) and value in PROGRAMS:
                return value
        elif key == "games":
            if isinstance(value, str) and value in GAMES_VALUES:
                return value
        elif key == "plugins_off":
            if (
                isinstance(value, list)
                and len(value) <= PLUGINS_OFF_MAX
                and all(
                    isinstance(item, str) and PLUGIN_ID_RE.fullmatch(item)
                    for item in value
                )
            ):
                return list(dict.fromkeys(value))
        elif key == "session_refresh_sec":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                low, high = SESSION_REFRESH_RANGE
                if math.isfinite(value) and low <= value <= high:
                    return float(value)
        raise self._invalid(key)

    def _canonical(self, key, text):
        """The canonical JSON of the value that `text` gives `key`.

        `text` is JSON, or, for a person typing in a form, the bare value:
        a word for `deck_program` and `games`, ids separated by commas for
        `plugins_off`, a decimal number for `session_refresh_sec`.
        """
        text = text if isinstance(text, str) else ""
        try:
            value = json.loads(text)
        except ValueError:
            if key == "plugins_off":
                value = [item.strip() for item in text.split(",")]
                value = [item for item in value if item]
            elif key == "session_refresh_sec":
                try:
                    value = float(text)
                except ValueError as error:
                    raise self._invalid(key) from error
            else:
                value = text.strip()
        return json.dumps(self._validate(key, value), separators=(",", ":"))

    def _load(self, key, text):
        """The value a stored line holds, or None when the stored text no
        longer passes the schema (logged, the key then unmanaged by this
        line)."""
        try:
            return self._validate(key, json.loads(text))
        except (ValueError, ValidationError):
            _logger.warning(
                "Stream Deck setting %s holds an invalid value", key
            )
            return None

    def _layers(self, workstation):
        """[(layer, lines)] of `workstation` in folding order: its profile
        when active, the deck-model layers of its connected decks by
        ascending USB product id, then its own lines."""
        workstation = workstation.sudo()
        layers = []
        profile = workstation.config_profile_id
        if profile.active:
            layers.append(("profile", profile.line_ids))
        products = {
            device.usb_product_id.lower()
            for device in workstation.device_ids
            if device.connected and device.usb_product_id
        }
        if products:
            deck_models = (
                self.env["streamdeck.config.model"]
                .sudo()
                .search(
                    [("usb_product_id", "in", sorted(products))],
                    order="usb_product_id",
                )
            )
            layers.extend(("model", model.line_ids) for model in deck_models)
        layers.append(("workstation", workstation.config_line_ids))
        return layers

    def _effective(self, workstation):
        """The configuration Odoo wants on `workstation`.

        Returns `{"settings": {key: value}, "locked": [key], "sources":
        {key: layer}}`, keys in KEYS order. A key takes the value of the
        last layer that sets it, up to the first layer that locks it: a
        profile lock ignores the models and the workstation, a model lock
        ignores the next models and the workstation. A key no layer sets
        is absent: it stays the employee's, on the workstation.
        """
        settings, sources, locked = {}, {}, set()
        for layer, lines in self._layers(workstation):
            for line in lines:
                if line.key in locked:
                    continue
                value = self._load(line.key, line.value)
                if value is None:
                    continue
                settings[line.key] = value
                sources[line.key] = layer
                if line.locked:
                    locked.add(line.key)
        return {
            "settings": {
                key: settings[key] for key in KEYS if key in settings
            },
            "locked": [key for key in KEYS if key in locked],
            "sources": {key: sources[key] for key in KEYS if key in sources},
        }

    def _hash(self, settings):
        """SHA-256 hex of the canonical JSON of `settings`: keys sorted,
        no spaces."""
        canonical = json.dumps(settings, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _first_pilot_policy(self):
        """The organisation's first-pilot policy: "ask", "keep_local" or
        "take_odoo"; a missing or unknown parameter reads "ask"."""
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(PARAM_PREFIX + "first_pilot_policy")
        )
        return value if value in dict(FIRST_PILOT_POLICIES) else "ask"

    def _format(self, key, value):
        """`value` of `key` as a person reads it."""
        if key == "plugins_off":
            return ", ".join(value) or _("(none)")
        if key == "session_refresh_sec":
            return "%g" % value
        return value


class StreamdeckConfigProfile(models.Model):
    """A reusable set of settings, assigned to workstations.

    The manager assigns any profile; an employee picks one marked
    `selectable` for their own workstations
    (`streamdeck.workstation._check_profile_pick`).
    """

    _name = "streamdeck.config.profile"
    _description = "Stream Deck configuration profile"
    _order = "name, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    selectable = fields.Boolean(
        string="Selectable",
        help="An employee may pick this profile for their own"
        " workstations.",
    )
    line_ids = fields.One2many(
        "streamdeck.config.line", "profile_id", string="Settings"
    )
    workstation_ids = fields.One2many(
        "streamdeck.workstation",
        "config_profile_id",
        string="Workstations",
    )


class StreamdeckConfigModel(models.Model):
    """The settings layer of a deck model, applied to the workstations to
    which a deck of that USB product id is connected."""

    _name = "streamdeck.config.model"
    _description = "Stream Deck configuration of a deck model"
    _order = "usb_product_id"

    usb_product_id = fields.Char(
        string="USB product id",
        size=4,
        required=True,
        help="Four hexadecimal digits, as the deck reports them.",
    )
    name = fields.Char(compute="_compute_name", store=True)
    line_ids = fields.One2many(
        "streamdeck.config.line", "model_id", string="Settings"
    )

    _sql_constraints = [
        (
            "usb_product_id_unique",
            "UNIQUE(usb_product_id)",
            "A deck model has one settings layer.",
        ),
    ]

    @api.depends("usb_product_id")
    def _compute_name(self):
        for model in self:
            model.name = usb_model_name(model.usb_product_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if isinstance(vals.get("usb_product_id"), str):
                vals["usb_product_id"] = vals["usb_product_id"].lower()
        return super().create(vals_list)

    def write(self, vals):
        if isinstance(vals.get("usb_product_id"), str):
            vals = dict(vals, usb_product_id=vals["usb_product_id"].lower())
        return super().write(vals)

    @api.constrains("usb_product_id")
    def _check_usb_product_id(self):
        for model in self:
            if not PRODUCT_ID_RE.fullmatch(model.usb_product_id or ""):
                raise ValidationError(
                    _("A USB product id is four hexadecimal digits.")
                )


class StreamdeckConfigLine(models.Model):
    """One managed setting of one layer: a profile, a deck model or a
    workstation, exactly one of them.

    `value` holds the canonical JSON of the value, normalised by the
    schema at every create and write. Only a manager sets `locked` and
    `source`. An employee creates, changes and deletes lines of their own
    workstations only, for keys no layer of that workstation locks; a
    line they change becomes theirs (`source` "employee"). The service
    writes the lines it adopts from a workstation in sudo, `source`
    "local".
    """

    _name = "streamdeck.config.line"
    _description = "Stream Deck configuration setting"
    _order = "key, id"

    key = fields.Selection(KEY_SELECTION, string="Setting", required=True)
    value = fields.Char(
        required=True,
        help="A word for the deck program and the games, plugin ids"
        " separated by commas, a number of seconds; stored as JSON.",
    )
    locked = fields.Boolean(
        help="Locked by the manager: no later layer and no employee"
        " changes it.",
    )
    source = fields.Selection(
        SOURCES,
        required=True,
        default=lambda self: (
            "employee" if self._is_employee() else "manager"
        ),
        help="Who set the value: the manager, the employee, or the"
        " workstation's own file, adopted by Odoo.",
    )
    profile_id = fields.Many2one(
        "streamdeck.config.profile",
        string="Profile",
        index="btree_not_null",
        ondelete="cascade",
    )
    model_id = fields.Many2one(
        "streamdeck.config.model",
        string="Deck model",
        index="btree_not_null",
        ondelete="cascade",
    )
    workstation_id = fields.Many2one(
        "streamdeck.workstation",
        string="Workstation",
        index="btree_not_null",
        ondelete="cascade",
    )

    _sql_constraints = [
        (
            "profile_key_unique",
            "UNIQUE(profile_id, key)",
            "A profile sets each setting once.",
        ),
        (
            "model_key_unique",
            "UNIQUE(model_id, key)",
            "A deck model sets each setting once.",
        ),
        (
            "workstation_key_unique",
            "UNIQUE(workstation_id, key)",
            "A workstation overrides each setting once.",
        ),
    ]

    # `key` is in every create: listing it checks a line created with no
    # parent at all, which names none of the three parent fields.
    @api.constrains("key", "profile_id", "model_id", "workstation_id")
    def _check_one_parent(self):
        for line in self:
            parents = (line.profile_id, line.model_id, line.workstation_id)
            if sum(1 for parent in parents if parent) != 1:
                raise ValidationError(
                    _(
                        "A setting belongs to exactly one profile, deck"
                        " model or workstation."
                    )
                )

    @api.constrains("key", "value")
    def _check_value(self):
        schema = self.env["streamdeck.config.schema"]
        for line in self:
            try:
                value = json.loads(line.value)
            except ValueError as error:
                raise schema._invalid(line.key) from error
            schema._validate(line.key, value)

    def _is_employee(self):
        return not self.env.su and not self.env.user.has_group(MANAGER_GROUP)

    def _check_employee_vals(self, vals):
        """Raise AccessError when an employee's `vals` sets a lock, a
        source other than theirs, or a parent other than one of their
        own workstations."""
        if (
            vals.get("locked")
            or vals.get("source", "employee") != "employee"
            or vals.get("profile_id")
            or vals.get("model_id")
        ):
            raise AccessError(
                _(
                    "Only a Stream Deck manager sets locks, profiles and"
                    " deck models."
                )
            )
        if "workstation_id" in vals:
            workstation = self.env["streamdeck.workstation"].browse(
                vals["workstation_id"]
            )
            if not workstation:
                raise AccessError(
                    _("An employee sets the settings of a workstation.")
                )
            workstation.check_access("write")

    def _check_free(self, workstation, key):
        """Raise AccessError when a layer of `workstation` locks `key`."""
        schema = self.env["streamdeck.config.schema"]
        if key in schema._effective(workstation)["locked"]:
            labels = dict(self._fields["key"]._description_selection(self.env))
            raise AccessError(
                _(
                    "The Stream Deck manager locked the setting %(key)s of"
                    " this workstation.",
                    key=labels.get(key, key),
                )
            )

    def _canonical_vals(self, vals, key):
        if "value" in vals and key:
            schema = self.env["streamdeck.config.schema"]
            vals["value"] = schema._canonical(key, vals["value"])
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        employee = self._is_employee()
        Workstation = self.env["streamdeck.workstation"]
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            self._canonical_vals(vals, vals.get("key"))
            if employee:
                if not vals.get("workstation_id"):
                    vals["workstation_id"] = False
                self._check_employee_vals(vals)
                self._check_free(
                    Workstation.browse(vals["workstation_id"]), vals.get("key")
                )
        return super().create(vals_list)

    def write(self, vals):
        if (
            "value" in vals
            and "key" not in vals
            and len(set(self.mapped("key"))) > 1
        ):
            for line in self:
                line.write(vals)
            return True
        vals = self._canonical_vals(
            dict(vals), vals.get("key") or self[:1].key
        )
        if not self.env.su:
            employee = self._is_employee()
            if employee:
                self.check_access("write")
                self._check_employee_vals(vals)
                Workstation = self.env["streamdeck.workstation"]
                for line in self:
                    self._check_free(line.workstation_id, line.key)
                    workstation = (
                        Workstation.browse(vals["workstation_id"])
                        if "workstation_id" in vals
                        else line.workstation_id
                    )
                    self._check_free(workstation, vals.get("key", line.key))
            if ("key" in vals or "value" in vals) and "source" not in vals:
                vals["source"] = "employee" if employee else "manager"
        return super().write(vals)

    def unlink(self):
        if self._is_employee():
            self.check_access("unlink")
            for line in self:
                self._check_free(line.workstation_id, line.key)
        return super().unlink()
