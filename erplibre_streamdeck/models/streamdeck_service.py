# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Enrollment and report of workstations, protocol 1.0.

Every public method takes the decoded JSON body and returns
`(http_status, body)`, the body always carrying `protocol`; an error body
adds `error`, one of the codes of `ERRORS`. A body is validated whole
before anything is written, so a 4xx leaves the database as it was.

Only a Stream Deck user, which every internal user is, enrolls or
reports: valid credentials of any other account, a portal one included,
and the token of an employee who is no longer such a user, are answered
403 `user_inactive`, as for an archived employee.

Secrets: the workstation token is returned once by `enroll` and only its
SHA-256 is stored; an API key or a password is checked and dropped. No
log line carries any of them.
"""

import contextlib
import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from odoo import api, fields, models
from odoo.exceptions import AccessDenied

from .streamdeck_workstation import SERVICE_STATES

_logger = logging.getLogger(__name__)

PROTOCOL = "1.0"
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
# The largest value of an Integer field, a PostgreSQL `integer` column.
MAX_COUNT = 2**31 - 1

ENROLL_METHODS = ("pairing_code", "api_key", "password")
# The kinds a workstation reports. `moved` is written by Odoo only, so a
# report that carries it is refused as any unknown kind.
EVENT_KINDS = ("plugged", "unplugged", "service_changed")
SERVICE_STATE_KEYS = tuple(key for key, _label in SERVICE_STATES)

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
    """Raise unless `payload` is a dict whose `protocol` has major 1; a
    newer minor is accepted and its unknown keys are ignored."""
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


def _parse_report(payload):
    state, decks = _parse_state(_dict(payload, "state"))
    events = [_parse_event(e) for e in _list(payload, "events", MAX_EVENTS)]
    lost = payload.get("lost_events")
    if not isinstance(lost, int) or isinstance(lost, bool):
        raise _bad()
    if not 0 <= lost <= MAX_COUNT:
        raise _bad()
    return state, decks, events, lost


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
        _check_protocol(payload)
        workstation = self._workstation_of(token)
        state, decks, events, lost = _parse_report(payload)
        now = fields.Datetime.now()
        workstation.write(
            dict(
                state,
                last_report=now,
                token_last_used=now,
                lost_events_total=max(workstation.lost_events_total, lost),
            )
        )
        self._apply_decks(workstation, decks, now)
        accepted = self._store_events(workstation, events, now)
        return _reply(accepted=accepted, heartbeat_s=HEARTBEAT_S)

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
        gets none."""
        seen = self.env["streamdeck.device"]
        moves = []
        for deck in decks:
            device = self._device(workstation, deck, now)
            previous = device.workstation_id
            if previous and previous != workstation:
                moves.append(
                    self._moved_values(device, previous, workstation, now)
                )
                self.env["streamdeck.device.holding"]._hold(
                    device, workstation.user_id, now
                )
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
        self.env["streamdeck.event"].create(moves)

    def _moved_values(self, device, previous, workstation, now):
        """The values of the `moved` event of `device`, taken by
        `workstation` from `previous`, with the names of both copied as
        those of a reported event are. The uuid is drawn here: no
        workstation sends this event."""
        return {
            "uuid": str(uuid4()),
            "kind": "moved",
            "at": now,
            "received_at": now,
            "device_id": device.id,
            "workstation_id": workstation.id,
            "workstation_name": workstation.name,
            "employee_name": workstation.user_id.name,
            "previous_workstation_id": previous.id,
            "previous_workstation_name": previous.name,
        }

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
