# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Enrollment and report of workstations, protocol 1.2.

Every public method takes the decoded JSON body and returns
`(http_status, body)`, the body always carrying `protocol`; an error body
adds `error`, one of the codes of `ERRORS`. A body is validated whole
before anything is written, so a 4xx leaves the database as it was.

Only a Stream Deck user, which every internal user is, enrolls or
reports: valid credentials of any other account, a portal one included,
and the token of an employee who is no longer such a user, are answered
403 `user_inactive`, as for an archived employee.

A report of protocol 1.1 or later may carry `config`, the managed
configuration as the workstation holds it (`_parse_config`); the reply to
the pilot of a workstation that a layer configures carries the revision
Odoo offers (`_apply_config`). A report of protocol 1.0 gets no `config`.
From protocol 1.2, the state may carry the catalog of the deck program
(`_parse_catalog`), and the configuration holds the key layouts of the
connected deck models (`streamdeck.key.layout`).

Secrets: the workstation token is returned once by `enroll` and only its
SHA-256 is stored; an API key or a password is checked and dropped. No
log line carries any of them.
"""

import contextlib
import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from psycopg2 import errors

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, ValidationError
from odoo.tools import mute_logger

from .streamdeck_config import KEYS, LAYOUTS_KEY, PLUGIN_ID_RE
from .streamdeck_event import SERVER_KINDS
from .streamdeck_key_layout import ACTION_RE, ICON_RE
from .streamdeck_workstation import FIRST_CHOICES, SERVICE_STATES

_logger = logging.getLogger(__name__)

PROTOCOL = "1.2"
HEARTBEAT_S = 900
PAIRING_TTL_MIN = 10
FUTURE_TOLERANCE_MIN = 5
# The unique index of the event uuid, as PostgreSQL names it in an error.
UUID_CONSTRAINT = "streamdeck_event_uuid_unique"

USER_GROUP = "erplibre_streamdeck.group_streamdeck_user"

PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_LENGTH = 8
TOKEN_BYTES = 32

# Bounds on what a body may carry. The extension queues at most 1000
# events per destination; ten times that is no conforming client.
MAX_TEXT = 256
MAX_SECRET = 4096
MAX_DECKS = 128
MAX_EVENTS = 10000
MAX_DECK_PLUGINS = 128
# The catalog of the deck program: the extension drops one larger than
# MAX_CATALOG_BYTES as compact JSON, and Odoo does the same; its size
# bounds the number of items. Each number of a geometry is at most
# MAX_GEOMETRY.
MAX_CATALOG_BYTES = 32 * 1024
MAX_GEOMETRY = 256
# The largest value of an Integer field, a PostgreSQL `integer` column.
MAX_COUNT = 2**31 - 1

ENROLL_METHODS = ("pairing_code", "api_key", "password")
# The kinds a workstation reports. Those of SERVER_KINDS are written by
# Odoo only, so a report that carries one is refused as any unknown kind.
EVENT_KINDS = ("plugged", "unplugged", "service_changed")
SERVICE_STATE_KEYS = tuple(key for key, _label in SERVICE_STATES)

CONFIG_STATUSES = ("applied", "refused")
CONFIG_CHOICES = tuple(key for key, _label in FIRST_CHOICES)
# Why a workstation refused a revision (CONTRACT.md of the extension).
REFUSAL_REASONS = frozenset(
    ["write_failed", "restart_failed", "unit_missing"]
    + ["invalid:%s" % key for key in KEYS]
)
# A workstation refuses the key layouts from protocol 1.2 on, the first
# that sends them.
LAYOUTS_REFUSAL = "invalid:%s" % LAYOUTS_KEY
# The refusals that come after the revision is written to the file: the
# file holds its values though the deck unit does not run them.
WRITTEN_REASONS = ("restart_failed", "unit_missing")

ERRORS = (
    "bad_request",
    "protocol_unsupported",
    "credentials_refused",
    "user_inactive",
    "token_invalid",
)

# Matched with `fullmatch`: a trailing newline is refused too.
_PROTOCOL_RE = re.compile(r"([0-9]+)\.([0-9]+)")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
_HASH_RE = _FINGERPRINT_RE
_PRODUCT_RE = re.compile(r"[0-9a-f]{4}")
# A serial has no `:`, so `sn:<serial>` never equals a `nosn:` key.
_SERIAL_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestError(Exception):
    """A refused request: `status` and `code` become the error reply."""

    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


def _bad():
    return RequestError(400, "bad_request")


def _text(obj, key, required=False, bound=MAX_TEXT):
    """The string at `obj[key]`, or None when absent or null; an empty
    string counts as absent. Raises a 400 when the value is not a string,
    is longer than `bound`, is required and absent, or cannot reach
    PostgreSQL: a NUL character or a lone surrogate, which JSON carries
    as `\\u0000` or `\\ud800`, would fail in the database driver."""
    value = obj.get(key)
    if value is None or value == "":
        if required:
            raise _bad()
        return None
    if not isinstance(value, str) or len(value) > bound:
        raise _bad()
    if "\x00" in value:
        raise _bad()
    try:
        value.encode()
    except UnicodeEncodeError as error:
        raise _bad() from error
    return value


def _dict(obj, key, nullable=False):
    value = obj.get(key)
    if value is None and nullable:
        return None
    if not isinstance(value, dict):
        raise _bad()
    return value


def _list(obj, key, bound):
    value = obj.get(key)
    if not isinstance(value, list) or len(value) > bound:
        raise _bad()
    return value


def _check_protocol(payload):
    """Return the minor of `payload`'s `protocol`; raise unless `payload`
    is a dict whose `protocol` has major 1. A newer minor is accepted and
    its unknown keys are ignored."""
    if not isinstance(payload, dict):
        raise _bad()
    protocol = payload.get("protocol")
    if not isinstance(protocol, str):
        raise _bad()
    match = _PROTOCOL_RE.fullmatch(protocol)
    if not match:
        raise _bad()
    if int(match.group(1)) != int(PROTOCOL.split(".")[0]):
        raise RequestError(400, "protocol_unsupported")
    return int(match.group(2))


def _parse_at(value):
    """A naive UTC datetime, to the second, from an ISO-8601 string; a
    string without offset is read as UTC, and a final `Z` is read as
    `+00:00` on every Python that Odoo 18 runs on. Raises a 400 for
    anything else, a moment outside the years 1-9999 in UTC included."""
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise _bad()
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is not None:
            moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError) as error:
        raise _bad() from error
    return moment.replace(microsecond=0)


def _deck_identity(obj):
    """`(serial, usb_product_id, usb_path)` of a deck or of an event, the
    serial within `_SERIAL_RE`, the product id as four lowercase hex
    digits, each or None; at least a serial or a USB path is required to
    name the deck."""
    serial = _text(obj, "serial")
    if serial is not None and not _SERIAL_RE.fullmatch(serial):
        raise _bad()
    product = _text(obj, "usb_product_id")
    path = _text(obj, "usb_path")
    if serial is None and path is None:
        raise _bad()
    if product is not None:
        product = product.lower()
        if not _PRODUCT_RE.fullmatch(product):
            raise _bad()
    return serial, product, path


def _parse_state(state):
    os_info = _dict(state, "os")
    erplibre = _dict(state, "erplibre", nullable=True) or {}
    service_state = state.get("service_state")
    if service_state not in SERVICE_STATE_KEYS:
        raise _bad()
    decks = []
    for deck in _list(state, "decks", MAX_DECKS):
        if not isinstance(deck, dict):
            raise _bad()
        serial, product, path = _deck_identity(deck)
        decks.append(
            {
                "serial": serial,
                "usb_product_id": product,
                "usb_path": path,
                "firmware": _text(deck, "firmware"),
            }
        )
    values = {
        "os_name": _text(os_info, "name"),
        "os_version": _text(os_info, "version"),
        "gnome_shell": _text(state, "gnome_shell"),
        "extension_version": _text(state, "extension_version"),
        "contract_version": _text(state, "contract_version"),
        "erplibre_branch": _text(erplibre, "branch"),
        "erplibre_commit": _text(erplibre, "commit"),
        "deck_program": _text(state, "deck_program"),
        "service_state": service_state,
    }
    plugins = state.get("deck_plugins")
    if plugins is not None:
        if not isinstance(plugins, list) or len(plugins) > MAX_DECK_PLUGINS:
            raise _bad()
        if not all(
            isinstance(plugin, str) and PLUGIN_ID_RE.fullmatch(plugin)
            for plugin in plugins
        ):
            raise _bad()
        values["deck_plugins"] = ",".join(dict.fromkeys(plugins))
    # The host name is validated but never written: it names the
    # workstation at enrollment only, and the employee may rename it.
    _text(state, "hostname")
    return {key: value or False for key, value in values.items()}, decks


def _parse_event(event):
    if not isinstance(event, dict):
        raise _bad()
    uuid = _text(event, "uuid", required=True)
    kind = event.get("kind")
    if kind not in EVENT_KINDS:
        raise _bad()
    parsed = {"uuid": uuid, "kind": kind, "at": _parse_at(event.get("at"))}
    service_state = event.get("service_state")
    if service_state is not None and service_state not in SERVICE_STATE_KEYS:
        raise _bad()
    if kind == "service_changed":
        if service_state is None:
            raise _bad()
        parsed["service_state"] = service_state
        parsed["deck"] = None
    else:
        serial, product, path = _deck_identity(event)
        parsed["deck"] = {
            "serial": serial,
            "usb_product_id": product,
            "usb_path": path,
        }
    return parsed


def _count(value, nullable=False):
    """`value`, an integer from 0 to MAX_COUNT (None too when `nullable`);
    raises a 400 for anything else, a boolean included."""
    if value is None and nullable:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise _bad()
    if not 0 <= value <= MAX_COUNT:
        raise _bad()
    return value


def _parse_report(payload):
    state, decks = _parse_state(_dict(payload, "state"))
    events = [_parse_event(e) for e in _list(payload, "events", MAX_EVENTS)]
    lost = _count(payload.get("lost_events"))
    return state, decks, events, lost


def _parse_result(result, minor=1):
    """The `result` of a pilot's `config`: None, or `{revision, status,
    reason, at}` with a reason of REFUSAL_REASONS, LAYOUTS_REFUSAL from
    protocol 1.2 on, or None."""
    if result is None:
        return None
    if not isinstance(result, dict):
        raise _bad()
    status = result.get("status")
    if status not in CONFIG_STATUSES:
        raise _bad()
    reason = result.get("reason")
    reasons = REFUSAL_REASONS
    if minor >= 2:
        reasons = reasons | {LAYOUTS_REFUSAL}
    if reason is not None and (
        not isinstance(reason, str) or reason not in reasons
    ):
        raise _bad()
    return {
        "revision": _count(result.get("revision")),
        "status": status,
        "reason": reason,
        "at": _parse_at(result.get("at")),
    }


def _int(value, low, high):
    """`value`, an integer from `low` to `high`; raises a 400 for anything
    else, a boolean included."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise _bad()
    if not low <= value <= high:
        raise _bad()
    return value


def _parse_catalog(state):
    """The `deck_catalog` of a state of protocol 1.2, as
    `streamdeck.catalog.item._take` takes it.

    None when absent or null, when larger than MAX_CATALOG_BYTES as compact
    JSON, or of a format other than 1. An action or an icon of another
    form, a model whose key is not a USB product id, or one no key fits
    (no key, or more keys than cells), is skipped: a newer deck program
    may offer more. Raises a 400 for any other shape: a format that is
    not an integer, an entry that is not a string, a geometry whose
    numbers are not integers from 0 to MAX_GEOMETRY."""
    catalog = state.get("deck_catalog")
    if catalog is None:
        return None
    if not isinstance(catalog, dict):
        raise _bad()
    if not isinstance(catalog.get("format"), int) or isinstance(
        catalog.get("format"), bool
    ):
        raise _bad()
    text = json.dumps(catalog, separators=(",", ":"), ensure_ascii=False)
    if len(text.encode("utf-8", "surrogatepass")) > MAX_CATALOG_BYTES:
        return None
    if catalog["format"] != 1:
        return None
    actions = _list(catalog, "actions", MAX_CATALOG_BYTES)
    icons = _list(catalog, "icons", MAX_CATALOG_BYTES)
    shapes = _dict(catalog, "models")
    for entry in actions + icons:
        if not isinstance(entry, str) or len(entry) > MAX_TEXT:
            raise _bad()
    models = {}
    for product, shape in shapes.items():
        if not isinstance(shape, dict):
            raise _bad()
        cols = _int(shape.get("cols"), 0, MAX_GEOMETRY)
        rows = _int(shape.get("rows"), 0, MAX_GEOMETRY)
        keys = _int(shape.get("keys"), 0, MAX_GEOMETRY)
        if _PRODUCT_RE.fullmatch(product) and 0 < keys <= cols * rows:
            models[product] = {"cols": cols, "rows": rows, "keys": keys}
    return {
        "actions": [
            a for a in dict.fromkeys(actions) if ACTION_RE.fullmatch(a)
        ],
        "icons": [i for i in dict.fromkeys(icons) if ICON_RE.fullmatch(i)],
        "models": models,
    }


def _parse_layout_hashes(value):
    """`current.key_layouts` of a pilot, protocol 1.2: `{product id:
    sha256 hex | None}`, the hash of each layout the workstation's
    keymap.json holds; `{}` when absent or null. Raises a 400 for any
    other shape, or more than MAX_DECKS models."""
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > MAX_DECKS:
        raise _bad()
    for product, digest in value.items():
        if not _PRODUCT_RE.fullmatch(product):
            raise _bad()
        if digest is not None and not (
            isinstance(digest, str) and _HASH_RE.fullmatch(digest)
        ):
            raise _bad()
    return dict(value)


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _reply(status=200, **body):
    return status, dict(body, protocol=PROTOCOL)


class StreamdeckService(models.AbstractModel):
    """Entry points of the workstation routes, called in sudo; each
    method works in sudo itself and writes only the workstation that the
    credentials or the token designate, its decks and its events."""

    _name = "streamdeck.service"
    _description = "Stream Deck workstation service"

    # -- pairing codes ---------------------------------------------------

    @api.model
    def new_pairing_code(self, user):
        """A new unused code for `user`, valid PAIRING_TTL_MIN minutes;
        it is drawn again on the rare collision with a stored code."""
        Code = self.env["streamdeck.pairing.code"].sudo()
        while True:
            code = "".join(
                secrets.choice(PAIRING_ALPHABET)
                for _i in range(PAIRING_LENGTH)
            )
            if not Code.search_count([("code", "=", code)]):
                break
        return Code.create(
            {
                "code": code,
                "user_id": user.id,
                "expires_at": fields.Datetime.now()
                + timedelta(minutes=PAIRING_TTL_MIN),
            }
        )

    # -- public entry points ---------------------------------------------

    @api.model
    def enroll(self, payload):
        try:
            return self.sudo()._enroll(payload)
        except RequestError as error:
            return _reply(error.status, error=error.code)

    @api.model
    def report(self, token, payload):
        try:
            return self.sudo()._report(token, payload)
        except RequestError as error:
            return _reply(error.status, error=error.code)

    @api.model
    def unenroll(self, token, payload):
        try:
            _check_protocol(payload)
            workstation = self.sudo()._workstation_of(token)
            workstation.write({"token_hash": False})
            _logger.info(
                "Stream Deck workstation %s unenrolled", workstation.id
            )
            return _reply()
        except RequestError as error:
            return _reply(error.status, error=error.code)

    # -- enrollment ------------------------------------------------------

    def _enroll(self, payload):
        _check_protocol(payload)
        method = payload.get("method")
        if method not in ENROLL_METHODS:
            raise _bad()
        fingerprint = payload.get("fingerprint")
        if not isinstance(fingerprint, str) or not _FINGERPRINT_RE.fullmatch(
            fingerprint
        ):
            raise _bad()
        hostname = _text(payload, "hostname", required=True)
        if method == "pairing_code":
            secret = _text(payload, "code", required=True)
            user, code = self._user_of_code(secret)
        elif method == "api_key":
            secret = _text(payload, "key", required=True, bound=MAX_SECRET)
            user, code = self._user_of_api_key(secret), None
        else:
            login = _text(payload, "login", required=True)
            secret = _text(
                payload, "password", required=True, bound=MAX_SECRET
            )
            user, code = self._user_of_password(login, secret), None
        if not user.active:
            raise RequestError(403, "user_inactive")
        if not user.has_group(USER_GROUP):
            raise RequestError(403, "user_inactive")
        if code:
            code.write({"used": True})

        token = secrets.token_urlsafe(TOKEN_BYTES)
        now = fields.Datetime.now()
        token_values = {
            "token_hash": _hash_token(token),
            "token_created": now,
            "token_last_used": False,
        }
        Workstation = self.env["streamdeck.workstation"].with_context(
            active_test=False
        )
        workstation = Workstation.search(
            [("user_id", "=", user.id), ("fingerprint", "=", fingerprint)],
            limit=1,
        )
        if workstation:
            workstation.write(dict(token_values, active=True))
        else:
            workstation = Workstation.create(
                dict(
                    token_values,
                    user_id=user.id,
                    fingerprint=fingerprint,
                    name=hostname,
                )
            )
        _logger.info(
            "Stream Deck workstation %s enrolled for user %s by %s",
            workstation.id,
            user.id,
            method,
        )
        return _reply(workstation_id=workstation.id, token=token)

    def _user_of_code(self, typed):
        """The user and the code record of an unused, unexpired pairing
        code; case, spaces and hyphens of the typed code are ignored."""
        code = re.sub(r"[\s-]", "", typed).upper()
        with self._throttled("pairing code"):
            record = (
                self.env["streamdeck.pairing.code"]
                .sudo()
                .search(
                    [
                        ("code", "=", code),
                        ("used", "=", False),
                        ("expires_at", ">", fields.Datetime.now()),
                    ],
                    limit=1,
                )
            )
            if not record:
                raise AccessDenied()
        return record.user_id, record

    def _user_of_api_key(self, key):
        """The user of a global or `rpc` API key; Odoo matches keys of
        active users only."""
        with self._throttled("API key"):
            uid = self.env["res.users.apikeys"]._check_credentials(
                scope="rpc", key=key
            )
            if not uid:
                raise AccessDenied()
        return self.env["res.users"].browse(uid)

    def _user_of_password(self, login, password):
        """The active user whose login and password match, checked as an
        RPC login (`interactive: False`): a user whose RPC access is
        limited to API keys, as with two-factor authentication, is
        refused. No session is opened and no login is recorded."""
        Users = self.env["res.users"]
        with self._throttled(login):
            user = Users.search(
                Users._get_login_domain(login),
                order=Users._get_login_order(),
                limit=1,
            )
            if not user:
                raise AccessDenied()
            user.with_user(user)._check_credentials(
                {"type": "password", "login": login, "password": password},
                {"interactive": False},
            )
        return user

    @contextlib.contextmanager
    def _throttled(self, label):
        """Odoo's login cooldown around a credential check, which counts
        failures by remote address (inert outside an HTTP request); a
        refused check, or an attempt during the cooldown, becomes 401
        `credentials_refused`."""
        try:
            with self.env["res.users"]._assert_can_auth(user=label):
                yield
        except AccessDenied as error:
            raise RequestError(401, "credentials_refused") from error

    # -- report ----------------------------------------------------------

    def _workstation_of(self, token):
        """The workstation holding `token`; 401 `token_invalid` for an
        unknown or revoked token, 403 `user_inactive` when its employee
        is archived or no longer a Stream Deck user."""
        if not isinstance(token, str) or not token:
            raise RequestError(401, "token_invalid")
        workstation = (
            self.env["streamdeck.workstation"]
            .with_context(active_test=False)
            .search([("token_hash", "=", _hash_token(token))], limit=1)
        )
        if not workstation or not workstation.active:
            raise RequestError(401, "token_invalid")
        if not workstation.user_id.active:
            raise RequestError(403, "user_inactive")
        if not workstation.user_id.has_group(USER_GROUP):
            raise RequestError(403, "user_inactive")
        return workstation

    def _report(self, token, payload):
        """Apply a valid report to the workstation of `token`. A
        `service_state` that differs from the stored one, or that has no
        date yet, is dated `now`; a silent workstation is no longer, and
        gets a `heard_again` event dated `now`. The monitoring then hears
        what the report solved or revealed. Last, the `config` of a report
        of protocol 1.1 or later is taken in: a pilot's reply carries the
        configuration Odoo offers, a non-pilot's releases the workstation
        (`_apply_config`)."""
        minor = _check_protocol(payload)
        workstation = self._workstation_of(token)
        state, decks, events, lost = _parse_report(payload)
        catalog = _parse_catalog(payload["state"]) if minor >= 2 else None
        config = self._parse_config(payload, minor) if minor >= 1 else None
        now = fields.Datetime.now()
        values = dict(
            state,
            last_report=now,
            token_last_used=now,
            lost_events_total=max(workstation.lost_events_total, lost),
        )
        if (
            state["service_state"] != workstation.service_state
            or not workstation.service_state_since
        ):
            values["service_state_since"] = now
        previous_service_state = workstation.service_state
        was_silent = bool(workstation.silent_since)
        if was_silent:
            values["silent_since"] = False
        workstation.write(values)
        if was_silent:
            self._server_event(
                workstation, "heard_again", now, received_at=now
            )
        if catalog:
            self.env["streamdeck.catalog.item"]._take(catalog, now)
        moved, replugged = self._apply_decks(workstation, decks, now)
        accepted = self._store_events(workstation, events, now)
        self.env["streamdeck.monitor"]._on_report(
            workstation,
            moved,
            replugged,
            previous_service_state,
            heard_again=was_silent,
        )
        reply = {"accepted": accepted, "heartbeat_s": HEARTBEAT_S}
        offered = self._apply_config(workstation, config, now)
        if offered:
            reply["config"] = offered
        return _reply(**reply)

    def _deck_key(self, workstation, deck):
        """`sn:<serial>`, shared by every workstation that reports the
        serial, or `nosn:<workstation>:<product>:<path>` for a deck
        without one, which no other workstation can name."""
        if deck["serial"]:
            return "sn:%s" % deck["serial"]
        return "nosn:%d:%s:%s" % (
            workstation.id,
            deck["usb_product_id"] or "",
            deck["usb_path"] or "",
        )

    def _device(self, workstation, deck, now):
        """The device of `deck`, created on `workstation`, disconnected,
        when unknown; the employee of `workstation` then holds it from
        `now`."""
        Device = self.env["streamdeck.device"]
        key = self._deck_key(workstation, deck)
        device = Device.search([("key", "=", key)], limit=1)
        if not device:
            device = Device.create(
                {
                    "key": key,
                    "serial": deck["serial"] or False,
                    "usb_product_id": deck["usb_product_id"] or False,
                    "workstation_id": workstation.id,
                    "connected": False,
                }
            )
            self.env["streamdeck.device.holding"]._hold(
                device, workstation.user_id, now
            )
        return device

    def _apply_decks(self, workstation, decks, now):
        """The decks of the state become the connected decks of
        `workstation`, moved from another workstation if need be; its
        other decks are disconnected. A null firmware keeps the stored
        one: the deck service may hold the device and hide it.

        A deck taken from another workstation gets a `moved` event dated
        `now`, which keeps both workstations, and the employee of
        `workstation` holds it from `now` unless they held it before; a
        deck created by this report, or already held by `workstation`,
        gets none.

        Returns `(moved, replugged)`: the `(device, previous workstation)`
        pairs of the decks taken from another workstation, and the decks
        connected by this report that were not."""
        seen = replugged = self.env["streamdeck.device"]
        moved = []
        for deck in decks:
            device = self._device(workstation, deck, now)
            previous = device.workstation_id
            if previous and previous != workstation:
                self._server_event(
                    workstation,
                    "moved",
                    now,
                    device=device,
                    previous=previous,
                    received_at=now,
                )
                self.env["streamdeck.device.holding"]._hold(
                    device, workstation.user_id, now
                )
                moved.append((device, previous))
            if not device.connected:
                replugged |= device
            values = {"last_seen": now, "connected": True}
            if not device.connected or previous != workstation:
                values["connected_since"] = now
            values["workstation_id"] = workstation.id
            if deck["usb_product_id"]:
                values["usb_product_id"] = deck["usb_product_id"]
            if deck["firmware"]:
                values["firmware"] = deck["firmware"]
            device.write(values)
            seen |= device
        (workstation.device_ids - seen).filtered("connected").write(
            {"connected": False, "connected_since": False}
        )
        return moved, replugged

    def _server_event(
        self,
        workstation,
        kind,
        at,
        device=None,
        previous=None,
        received_at=None,
        **values,
    ):
        """Create and return an event of `kind`, one of SERVER_KINDS, at
        `workstation`, dated `at` and received at `received_at`, the
        current time by default; `values` sets further fields, as the
        `config_*` ones. The names of `workstation` and of `previous`, the
        workstation a moved deck left, are copied as those of a reported
        event are. The uuid is drawn here: no workstation sends these
        events. Raises ValueError for a kind that a workstation
        reports."""
        if kind not in SERVER_KINDS:
            raise ValueError("%r is not an event kind of the server" % kind)
        return self.env["streamdeck.event"].create(
            {
                "uuid": str(uuid4()),
                "kind": kind,
                "at": at,
                "received_at": received_at or fields.Datetime.now(),
                "device_id": device.id if device else False,
                "workstation_id": workstation.id,
                "workstation_name": workstation.name,
                "employee_name": workstation.user_id.name,
                "previous_workstation_id": previous.id if previous else False,
                "previous_workstation_name": (
                    previous.name if previous else False
                ),
                **values,
            }
        )

    def _store_events(self, workstation, events, now):
        """Create the events whose uuid is new and return every uuid of
        the report once, in order: a uuid already stored is acknowledged
        again without change, also when a concurrent report stores it
        between the search and the insert (`_create_events`). An event
        dated more than FUTURE_TOLERANCE_MIN minutes after `now` takes
        `now`."""
        Event = self.env["streamdeck.event"]
        uuids = list(dict.fromkeys(event["uuid"] for event in events))
        known = set(Event.search([("uuid", "in", uuids)]).mapped("uuid"))
        limit = now + timedelta(minutes=FUTURE_TOLERANCE_MIN)
        values = []
        for event in events:
            if event["uuid"] in known:
                continue
            known.add(event["uuid"])
            deck = event["deck"]
            device = self._device(workstation, deck, now) if deck else None
            values.append(
                {
                    "uuid": event["uuid"],
                    "kind": event["kind"],
                    "at": event["at"] if event["at"] <= limit else now,
                    "received_at": now,
                    "device_id": device.id if device else False,
                    "workstation_id": workstation.id,
                    "workstation_name": workstation.name,
                    "employee_name": workstation.user_id.name,
                    "service_state": event.get("service_state") or False,
                }
            )
        self._create_events(values)
        return uuids

    def _create_events(self, values):
        """Create the events of `values`. The search of known uuids reads
        the transaction's snapshot, which misses an event that another
        report, from another workstation of the same extension, commits
        meanwhile: its insert then breaks the uuid's unique constraint.
        The batch is inserted first; refused, each event is inserted
        alone, and one refused again is a known uuid, skipped."""
        if values and not self._insert_events(values):
            for vals in values:
                self._insert_events([vals])

    def _insert_events(self, values):
        """Create `values` in a savepoint and return True; return False,
        nothing created, when one of their uuids is stored already. Any
        other error is raised. The failed insert is not logged."""
        try:
            with mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                self.env["streamdeck.event"].create(values)
        except errors.UniqueViolation as error:
            if error.diag.constraint_name != UUID_CONSTRAINT:
                raise
            return False
        return True

    # -- managed configuration -------------------------------------------

    def _parse_config(self, payload, minor=1):
        """The `config` of a report: None when absent or null, which says
        nothing of the pilot; `{"pilot": False}` from a destination that
        is not the pilot, whatever else it holds; for the pilot,
        `{pilot: True, revision_applied, current, result, choice, layouts,
        current_layouts}`. `current` holds every key of KEYS, validated by
        the schema and normalised, None for a key absent or null; a key
        outside KEYS is ignored. `layouts` is True from protocol 1.2 on,
        which takes in the key layouts; `current_layouts` then holds the
        hashes of `current.key_layouts` (`_parse_layout_hashes`), `{}`
        before. Raises a 400 for any other shape or value."""
        config = payload.get("config")
        if config is None:
            return None
        if not isinstance(config, dict):
            raise _bad()
        pilot = config.get("pilot")
        if not isinstance(pilot, bool):
            raise _bad()
        if not pilot:
            return {"pilot": False}
        schema = self.env["streamdeck.config.schema"]
        local = _dict(config, "current")
        current = {}
        for key in KEYS:
            value = local.get(key)
            if value is not None:
                try:
                    value = schema._validate(key, value)
                except ValidationError as error:
                    raise _bad() from error
            current[key] = value
        choice = config.get("choice")
        if choice is not None and choice not in CONFIG_CHOICES:
            raise _bad()
        layouts = minor >= 2
        return {
            "pilot": True,
            "revision_applied": _count(
                config.get("revision_applied"), nullable=True
            ),
            "current": current,
            "result": _parse_result(config.get("result"), minor),
            "choice": choice,
            "layouts": layouts,
            "current_layouts": (
                _parse_layout_hashes(local.get(LAYOUTS_KEY)) if layouts else {}
            ),
        }

    def _apply_config(self, workstation, config, now):
        """Take in the pilot's `config` and return the reply's `config`.

        Returns None, and changes nothing, for `config` None. A
        destination that is not the pilot gets None and releases the
        workstation (`_config_release`): this Odoo no longer offers it a
        revision. Otherwise, in this order: the `result` of the offered
        revision is recorded (`_config_result`); a first pilot settles the
        free keys whose local value differs from Odoo's by the
        organisation's policy, or under `ask` by the employee's `choice`,
        until then listed in `ask`; after a first pilot, a managed key
        changed in the file since the last revision written to it is
        adopted when free and offered again when locked
        (`_config_drift`). The effective configuration then gets a new
        revision when its hash differs from the offered one, or when a
        drift asks for it with the same values.

        From protocol 1.2, the settings carry `key_layouts`, the layouts
        of the connected deck models (`_config_settings`), and a layout
        changed in the workstation's file is adopted or offered again as
        a key is (`_config_layout_drift`); the first pilot asks nothing
        of the layouts, which the extension alone writes.

        A workstation that no layer configures is `unmanaged` and gets no
        `config`; its hash is cleared, so a later configuration gets a
        new revision whatever its values.
        """
        if config is None:
            return None
        if not config["pilot"]:
            self._config_release(workstation)
            return None
        schema = self.env["streamdeck.config.schema"]
        self._config_result(workstation, config["result"], now)
        effective = schema._effective(workstation)
        layouts = (
            schema._effective_layouts(workstation) if config["layouts"] else {}
        )
        current = config["current"]
        if not self._config_settings(effective, layouts, current)[0]:
            self._config_release(workstation)
            return None
        ask, drift, adopt, adopt_layouts = [], [], {}, {}
        if (
            not workstation.config_first_choice
            and not workstation.config_applied_revision
        ):
            differing = self._config_differing(effective, current)
            policy = schema._first_pilot_policy()
            choice = config["choice"] if policy == "ask" else policy
            if choice == "keep_local":
                adopt = {key: current[key] for key in differing}
            if choice:
                workstation.config_first_choice = choice
            else:
                ask = differing
        elif workstation.config_applied_revision and (
            config["revision_applied"] == workstation.config_applied_revision
        ):
            adopt, drift = self._config_drift(workstation, effective, current)
            adopt_layouts, drift_layouts = self._config_layout_drift(
                workstation,
                self._config_settings(effective, layouts, current)[0],
                layouts,
                config["current_layouts"],
            )
            drift += ["%s:%s" % (LAYOUTS_KEY, pid) for pid in drift_layouts]
        if adopt or adopt_layouts:
            self._config_adopt(workstation, adopt, now, adopt_layouts)
            effective = schema._effective(workstation)
            if config["layouts"]:
                layouts = schema._effective_layouts(workstation)
        settings, locked = self._config_settings(effective, layouts, current)
        if not settings:
            self._config_release(workstation)
            return None
        digest = schema._hash(settings)
        values = {"config_ask": ",".join(ask) or False}
        renewed = digest != workstation.config_hash or bool(drift)
        if renewed:
            values.update(
                config_revision=workstation.config_revision + 1,
                config_hash=digest,
                config_offered=json.dumps(settings),
                config_pending_since=now,
                config_reason=False,
            )
        revision = values.get("config_revision", workstation.config_revision)
        if revision == workstation.config_applied_revision:
            values.update(config_state="applied", config_pending_since=False)
        elif drift:
            values["config_state"] = "drift"
        elif renewed or workstation.config_state != "refused":
            values["config_state"] = "pending"
        workstation.write(values)
        if drift:
            self._server_event(
                workstation, "config_drift", now, config_keys=", ".join(drift)
            )
        offered = {
            "revision": workstation.config_revision,
            "hash": digest,
            "settings": settings,
            "locked": locked,
        }
        if ask:
            offered["ask"] = ask
        return offered

    def _config_settings(self, effective, layouts, current):
        """`(settings, locked)` that Odoo offers: those of `effective`,
        plus `key_layouts` when `layouts` (`_effective_layouts`) gives a
        layout to send, locked when one of the sent layouts is. The
        plugins turned off are those `effective` sets, else those of the
        workstation's file (`current`), as the workstation checks the
        layouts against them."""
        schema = self.env["streamdeck.config.schema"]
        settings = dict(effective["settings"])
        locked = list(effective["locked"])
        plugins_off = settings.get(
            "plugins_off", current.get("plugins_off") or []
        )
        sent = schema._layout_settings(layouts, plugins_off)
        if sent:
            settings[LAYOUTS_KEY] = sent
            if any(layouts[product]["locked"] for product in sent):
                locked.append(LAYOUTS_KEY)
        return settings, locked

    def _config_release(self, workstation):
        """Make `workstation` `unmanaged`: no revision offered, pending
        or asked. Its hash is cleared, so the next pilot report gets a
        new revision whatever its values; what it applied and wrote, and
        its first-pilot choice, stay."""
        values = {
            "config_state": "unmanaged",
            "config_hash": False,
            "config_offered": False,
            "config_ask": False,
            "config_pending_since": False,
        }
        if any(workstation[name] != value for name, value in values.items()):
            workstation.write(values)

    def _config_differing(self, effective, current):
        """The free keys of `effective` whose local value in `current` is
        not None and differs from Odoo's, in KEYS order."""
        return [
            key
            for key, value in effective["settings"].items()
            if key not in effective["locked"]
            and current[key] is not None
            and current[key] != value
        ]

    def _config_drift(self, workstation, effective, current):
        """`(adopt, drift)` for a workstation whose file `current` follows
        its applied revision. The baseline is `config_written`: the
        values of that revision, or of a later one refused after its
        write, which the file holds as well; `config_applied` when
        `config_written` is empty. `adopt` maps each free key whose local
        value differs from the baseline, and from Odoo's, to the local
        value; `drift` lists the managed keys changed to another value,
        when locked, or to None, which holds nothing to adopt. A drift is
        listed only while the applied revision is the offered one: a
        revision already pending restores the key once applied, and
        listing it at each report would renew the revision each time.

        A key the baseline does not set fails closed. Set by the offered
        revision, it counts as changed when its local value differs from
        Odoo's: a drift when locked or None, so an empty baseline never
        hides a locked key; never adopted when free, so an empty baseline
        never turns a local value into an override. A key the offered
        revision does not set either is skipped: its hash differs from
        the offered one, and the new revision offers it."""
        schema = self.env["streamdeck.config.schema"]
        baseline = json.loads(
            workstation.config_written or workstation.config_applied or "{}"
        )
        offered = json.loads(workstation.config_offered or "{}")
        settled = workstation.config_revision == (
            workstation.config_applied_revision
        )
        adopt, drift = {}, []
        for key, value in effective["settings"].items():
            local = current[key]
            if key not in baseline:
                if key not in offered or local == value:
                    continue
                if key in effective["locked"] or local is None:
                    if settled:
                        drift.append(key)
                continue
            if local == schema._load(key, json.dumps(baseline[key])):
                continue
            if key in effective["locked"] or local is None:
                if settled and local != value:
                    drift.append(key)
            elif local != value:
                adopt[key] = local
        return adopt, drift

    def _config_layout_drift(self, workstation, settings, layouts, current):
        """`(adopt, drift)` of the key layouts, as `_config_drift` for the
        settings, on hashes: `current` maps a product id to the hash of the
        layout the workstation's keymap.json holds, None when it holds
        none; the baseline is the `key_layouts` of `config_written`, else
        of `config_applied`.

        `adopt` maps each product id whose free layout differs from the
        baseline, and from Odoo's, to its hash in the file; `drift` lists
        those whose locked layout, or missing one, differs, while the
        applied revision is the offered one. A layout the baseline lacks
        fails closed as a key does: offered again when locked or missing
        from the file, never adopted. Only the layouts of `settings`, the
        settings Odoo offers now, count: a layout Odoo does not send (kept
        in the file, model of unknown keys) is skipped."""
        schema = self.env["streamdeck.config.schema"]
        sent = settings.get(LAYOUTS_KEY) or {}
        if not sent:
            return {}, []
        written = json.loads(
            workstation.config_written or workstation.config_applied or "{}"
        )
        baseline = written.get(LAYOUTS_KEY) or {}
        offered = (
            json.loads(workstation.config_offered or "{}").get(LAYOUTS_KEY)
            or {}
        )
        settled = workstation.config_revision == (
            workstation.config_applied_revision
        )
        adopt, drift = {}, []
        for product, layout in sent.items():
            local = current.get(product)
            wanted = schema._layout_hash(layout)
            locked = layouts[product]["locked"]
            if product not in baseline:
                if product not in offered or local == wanted:
                    continue
                if (locked or local is None) and settled:
                    drift.append(product)
                continue
            if local == schema._layout_hash(baseline[product]):
                continue
            if locked or local is None:
                if settled and local != wanted:
                    drift.append(product)
            elif local != wanted:
                adopt[product] = local
        return adopt, drift

    def _config_adopt(self, workstation, values, now, layouts=None):
        """Write each `{key: value}` as the workstation's own line, not
        locked, `source` "local"; mark the workstation's layout of each
        `{product id: hash}` of `layouts` as kept in its file, `source`
        "local"; record one `config_adopted` event naming them all. The
        keys and the layouts are free: no layer locks them, so the line
        is the value of the effective configuration, and Odoo stops
        sending the layout."""
        Line = self.env["streamdeck.config.line"]
        lines = {line.key: line for line in workstation.config_line_ids}
        for key, value in values.items():
            line_values = {"value": json.dumps(value), "source": "local"}
            if key in lines:
                lines[key].write(line_values)
            else:
                Line.create(
                    dict(line_values, key=key, workstation_id=workstation.id)
                )
        layouts = layouts or {}
        Layout = self.env["streamdeck.key.layout"]
        own = {item.usb_product_id: item for item in workstation.layout_ids}
        for product, digest in layouts.items():
            layout_values = {
                "in_file": True,
                "file_hash": digest,
                "source": "local",
            }
            if product in own:
                own[product].write(layout_values)
            else:
                Layout.create(
                    dict(
                        layout_values,
                        usb_product_id=product,
                        workstation_id=workstation.id,
                    )
                )
        keys = list(values) + [
            "%s:%s" % (LAYOUTS_KEY, product) for product in layouts
        ]
        self._server_event(
            workstation, "config_adopted", now, config_keys=", ".join(keys)
        )

    def _config_result(self, workstation, result, now):
        """Record `result` when it is about the offered revision; a result
        about another revision, or already recorded, changes nothing.

        `applied` stores the offered values as the applied and written
        ones, ends the pending state and, at a first pilot not settled
        yet, records the choice `take_odoo`: the employee took Odoo's
        values. `refused` keeps the reason, and for a reason of
        WRITTEN_REASONS stores the offered values as the written ones,
        the applied revision staying as it was. Each recorded result
        writes its event, dated as
        the workstation reports it, a moment more than
        FUTURE_TOLERANCE_MIN minutes ahead of `now` taking `now`."""
        if not result or not workstation.config_hash:
            return
        revision = result["revision"]
        if revision != workstation.config_revision:
            return
        at = result["at"]
        if at > now + timedelta(minutes=FUTURE_TOLERANCE_MIN):
            at = now
        if result["status"] == "applied":
            if workstation.config_applied_revision == revision:
                return
            values = {
                "config_applied_revision": revision,
                "config_applied": workstation.config_offered,
                "config_written": workstation.config_offered,
                "config_state": "applied",
                "config_reason": False,
                "config_pending_since": False,
            }
            if not workstation.config_first_choice:
                values["config_first_choice"] = "take_odoo"
            workstation.write(values)
            self._server_event(
                workstation,
                "config_applied",
                at,
                received_at=now,
                config_revision=revision,
            )
            return
        if workstation.config_state == "refused" and (
            workstation.config_reason == (result["reason"] or False)
        ):
            return
        values = {"config_state": "refused", "config_reason": result["reason"]}
        if result["reason"] in WRITTEN_REASONS:
            values["config_written"] = workstation.config_offered
        workstation.write(values)
        self._server_event(
            workstation,
            "config_refused",
            at,
            received_at=now,
            config_revision=revision,
            config_reason=result["reason"],
        )
