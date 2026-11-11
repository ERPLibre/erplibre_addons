# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Enrollment and report of workstations, protocol 1.1.

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

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, ValidationError

from .streamdeck_config import KEYS, PLUGIN_ID_RE
from .streamdeck_event import SERVER_KINDS
from .streamdeck_workstation import FIRST_CHOICES, SERVICE_STATES

_logger = logging.getLogger(__name__)

PROTOCOL = "1.1"
HEARTBEAT_S = 900
PAIRING_TTL_MIN = 10
FUTURE_TOLERANCE_MIN = 5

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


def _parse_result(result):
    """The `result` of a pilot's `config`: None, or `{revision, status,
    reason, at}` with a reason of REFUSAL_REASONS or None."""
    if result is None:
        return None
    if not isinstance(result, dict):
        raise _bad()
    status = result.get("status")
    if status not in CONFIG_STATUSES:
        raise _bad()
    reason = result.get("reason")
    if reason is not None and (
        not isinstance(reason, str) or reason not in REFUSAL_REASONS
    ):
        raise _bad()
    return {
        "revision": _count(result.get("revision")),
        "status": status,
        "reason": reason,
        "at": _parse_at(result.get("at")),
    }


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
        what the report solved or revealed. Last, the `config` of a pilot
        report of protocol 1.1 or later is taken in, and the reply
        carries the configuration Odoo offers (`_apply_config`)."""
        minor = _check_protocol(payload)
        workstation = self._workstation_of(token)
        state, decks, events, lost = _parse_report(payload)
        config = self._parse_config(payload) if minor >= 1 else None
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
        again without change. An event dated more than
        FUTURE_TOLERANCE_MIN minutes after `now` takes `now`."""
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
        Event.create(values)
        return uuids

    # -- managed configuration -------------------------------------------

    def _parse_config(self, payload):
        """The `config` of a report: None when absent, null or from a
        destination that is not the pilot (`{"pilot": false}`, whatever
        else it holds); for the pilot, `{revision_applied, current,
        result, choice}`. `current` holds every key of KEYS, validated by
        the schema and normalised, None for a key absent or null; a key
        outside KEYS is ignored. Raises a 400 for any other shape or
        value."""
        config = payload.get("config")
        if config is None:
            return None
        if not isinstance(config, dict):
            raise _bad()
        pilot = config.get("pilot")
        if not isinstance(pilot, bool):
            raise _bad()
        if not pilot:
            return None
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
        return {
            "revision_applied": _count(
                config.get("revision_applied"), nullable=True
            ),
            "current": current,
            "result": _parse_result(config.get("result")),
            "choice": choice,
        }

    def _apply_config(self, workstation, config, now):
        """Take in the pilot's `config` and return the reply's `config`.

        Returns None, and changes nothing, for `config` None. Otherwise,
        in this order: the `result` of the offered revision is recorded
        (`_config_result`); a first pilot settles the free keys whose
        local value differs from Odoo's by the organisation's policy, or
        under `ask` by the employee's `choice`, until then listed in
        `ask`; after a first pilot, a managed key changed in the file
        since the revision the workstation applied is adopted when free
        and offered again when locked (`_config_drift`). The effective
        configuration then gets a new revision when its hash differs from
        the offered one, or when a drift asks for it with the same
        values.

        A workstation that no layer configures is `unmanaged` and gets no
        `config`; its hash is cleared, so a later configuration gets a
        new revision whatever its values.
        """
        if config is None:
            return None
        schema = self.env["streamdeck.config.schema"]
        self._config_result(workstation, config["result"], now)
        effective = schema._effective(workstation)
        if not effective["settings"]:
            workstation.write(
                {
                    "config_state": "unmanaged",
                    "config_hash": False,
                    "config_offered": False,
                    "config_ask": False,
                    "config_pending_since": False,
                }
            )
            return None
        current = config["current"]
        ask, drift, adopt = [], [], {}
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
        if adopt:
            self._config_adopt(workstation, adopt, now)
            effective = schema._effective(workstation)
        settings = effective["settings"]
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
            "locked": effective["locked"],
        }
        if ask:
            offered["ask"] = ask
        return offered

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
        its applied revision: `adopt` maps each free key whose local value
        changed since that revision, and differs from Odoo's, to the local
        value; `drift` lists the managed keys changed to another value,
        when locked, or to None, which holds nothing to adopt. A drift is
        listed only while the applied revision is the offered one: a
        revision already pending restores the key once applied, and
        listing it at each report would renew the revision each time.
        A key the applied revision did not set has no baseline and is
        skipped."""
        schema = self.env["streamdeck.config.schema"]
        applied = json.loads(workstation.config_applied or "{}")
        settled = workstation.config_revision == (
            workstation.config_applied_revision
        )
        adopt, drift = {}, []
        for key, value in effective["settings"].items():
            if key not in applied:
                continue
            local = current[key]
            if local == schema._load(key, json.dumps(applied[key])):
                continue
            if key in effective["locked"] or local is None:
                if settled and local != value:
                    drift.append(key)
            elif local != value:
                adopt[key] = local
        return adopt, drift

    def _config_adopt(self, workstation, values, now):
        """Write each `{key: value}` as the workstation's own line, not
        locked, `source` "local", and record one `config_adopted` event.
        The keys are free: no layer locks them, so the line is the value
        of the effective configuration."""
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
        self._server_event(
            workstation, "config_adopted", now, config_keys=", ".join(values)
        )

    def _config_result(self, workstation, result, now):
        """Record `result` when it is about the offered revision; a result
        about another revision, or already recorded, changes nothing.

        `applied` stores the offered values as the applied ones, ends the
        pending state and, at a first pilot not settled yet, records the
        choice `take_odoo`: the employee took Odoo's values. `refused`
        keeps the reason. Each recorded result writes its event, dated as
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
        workstation.write(
            {"config_state": "refused", "config_reason": result["reason"]}
        )
        self._server_event(
            workstation,
            "config_refused",
            at,
            received_at=now,
            config_revision=revision,
            config_reason=result["reason"],
        )
