# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Detection of the problems of workstations and decks.

`streamdeck.monitor` writes the `silent` history event whatever the
Settings say, and opens or closes one Odoo activity per problem when the
Settings › Stream Deck enable them. The cron `_cron_watch()` handles what
time reveals: a silent workstation, a deck service failed for its delay,
a deck unplugged for its delay. The report service calls `_on_report()`
for what a report reveals or solves: a deck that changed workstation, a
service that left `failed`, a workstation heard again, a deck plugged in
again. Archiving a workstation or clearing its token calls
`_resolve_all()`.

An activity is unique per (record, activity type, assigned user) while it
is open. It closes with `action_feedback`, which keeps it done because
its type has `keep_done`, and a « Resolved at <time>: <what> » feedback,
the time in the assigned user's time zone, UTC without one. A `moved`
activity is closed by a person only.

The mail notices these activities cause, as Odoo's notice to the user of
a new activity, go to Odoo's mail queue: neither a report nor the cron
waits on the mail server.
"""

import logging
from datetime import timedelta

import psycopg2.errors
import pytz
from markupsafe import Markup

from odoo import _lt, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import SQL, str2bool

from .res_config_settings import (
    ALERT_KINDS,
    DELAY_DEFAULTS,
    DELAY_FLOORS,
    PARAM_PREFIX,
    RECIPIENTS,
)

_logger = logging.getLogger(__name__)

# The activity type of each kind of problem, an xmlid of this module.
ACTIVITY_TYPES = {
    kind: "erplibre_streamdeck.activity_type_streamdeck_%s" % kind
    for kind in ALERT_KINDS
}

# What solved a problem, for the feedback of its activity. A report always
# carries one of SERVICE_STATES, so a service that leaves `failed` is in
# one of the three others.
HEARD_AGAIN = _lt("the workstation reported again")
PLUGGED_AGAIN = _lt("the deck is plugged in again")
SERVICE_LEFT_FAILED = {
    "active": _lt("the deck service is active"),
    "inactive": _lt("the deck service is stopped"),
    "absent": _lt("the deck service is absent"),
}
ENDINGS = {
    "archived": _lt("the workstation is archived"),
    "unenrolled": _lt("the workstation is unenrolled"),
}


class StreamdeckMonitor(models.AbstractModel):
    """Settings, recipients, opening and closing of the activities, and
    the cron. Every method works in sudo: the cron and the report
    service call it, and so does the archive of a workstation, which the
    record rules have already allowed."""

    _name = "streamdeck.monitor"
    _description = "Stream Deck monitoring"

    # -- settings and recipients -----------------------------------------

    @api.model
    def _settings(self):
        """The Settings › Stream Deck as a dict: `enabled`, `recipient`
        (one of RECIPIENTS), `manager` (a res.users, empty when the
        activities are disabled, when the recipient leaves the manager
        out, when none is named, or when the one named is archived or
        deleted, with a warning; so no warning while nothing can open),
        `alerts` (kind -> bool, a missing box meaning checked) and the
        three delays, an unreadable delay taking its default and none
        going below its floor."""
        params = self.env["ir.config_parameter"].sudo()

        def get(name):
            return params.get_param(PARAM_PREFIX + name) or ""

        enabled = str2bool(get("activities_enabled") or "False", False)
        recipient = get("activity_recipient")
        if recipient not in dict(RECIPIENTS):
            recipient = "manager"
        manager = self.env["res.users"]
        if enabled and recipient != "employee":
            manager = self._named_manager(get("activity_manager_id"))
        settings = {
            "enabled": enabled,
            "recipient": recipient,
            "manager": manager,
            "alerts": {
                kind: str2bool(get("alert_" + kind) or "True", True)
                for kind in ALERT_KINDS
            },
        }
        for name, default in DELAY_DEFAULTS.items():
            try:
                value = int(get(name) or default)
            except ValueError:
                value = default
            settings[name] = max(value, DELAY_FLOORS[name])
        return settings

    def _named_manager(self, stored):
        """The active user whose id is `stored`, or an empty recordset;
        a stored id of a user archived or deleted is logged, without any
        name, as a manager who gets nothing."""
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        if not stored:
            return self.env["res.users"]
        try:
            manager = Users.browse(int(stored)).exists()
        except ValueError:
            manager = Users
        if not manager.active:
            _logger.warning(
                "The Stream Deck activity manager named in the Settings is"
                " archived or deleted: only the employee part of the"
                " activities is created."
            )
            return self.env["res.users"]
        return self.env["res.users"].browse(manager.id)

    def _employee_of(self, record):
        """The employee of a workstation, or of the workstation that holds
        a deck."""
        if record._name == "streamdeck.device":
            record = record.sudo().workstation_id
        return record.sudo().user_id

    def _recipients(self, record, settings):
        """The active users an activity about `record` goes to; an
        archived employee is dropped with a warning."""
        users = self.env["res.users"]
        if settings["recipient"] in ("employee", "both"):
            employee = self._employee_of(record)
            if employee and not employee.active:
                _logger.warning(
                    "The employee of %s %s is archived: their part of the"
                    " Stream Deck activity is not created.",
                    record._name,
                    record.id,
                )
            else:
                users |= employee
        if settings["recipient"] in ("manager", "both"):
            users |= settings["manager"]
        return users

    def _activity_type(self, kind):
        """The activity type of `kind`, empty when someone deleted it: the
        problem then opens nothing and a report never fails over it."""
        return (
            self.env.ref(ACTIVITY_TYPES[kind], raise_if_not_found=False)
            or self.env["mail.activity.type"]
        )

    def _open_activities(self, record, kind):
        """The open activities of `kind` on `record`, whoever they are
        assigned to."""
        activity_type = self._activity_type(kind)
        if not activity_type:
            return self.env["mail.activity"].sudo()
        return (
            self.env["mail.activity"]
            .sudo()
            .search(
                [
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("activity_type_id", "=", activity_type.id),
                ]
            )
        )

    def _queued(self):
        """This model with the mail notices of its activities and thread
        messages queued: Odoo otherwise sends them by SMTP when the
        transaction commits, before the report that caused them gets its
        answer."""
        return self.with_context(mail_notify_force_send=False)

    @staticmethod
    def _in_language(env, user):
        return env(context=dict(env.context, lang=user.lang or "en_US"))

    # -- opening and closing ---------------------------------------------

    def _open(self, record, kind, note, settings=None, still=None):
        """Open an activity of `kind` on `record` for each recipient that
        has no open one of that kind there, its note `note` (a lazy
        translation) in the recipient's language; return the activities
        created. Nothing opens while the activities are disabled or the
        box of `kind` is cleared. For `moved`, an activity still open on
        `record`, whoever it is assigned to, keeps it unique: nothing
        opens, and `note` is posted once to the record's thread instead,
        so a deck moved twice keeps its activity and its thread tells the
        second move.

        With `still`, the domain that made the cron pick `record`, the row
        is first taken by `_lock()`, and nothing opens unless it is
        free and `record` still matches `still`."""
        settings = settings or self._settings()
        self = self._queued()
        Activity = self.env["mail.activity"].sudo()
        activity_type = self._activity_type(kind)
        if not settings["enabled"] or not settings["alerts"][kind]:
            return Activity
        if not activity_type:
            return Activity
        record = record.with_env(self.env).sudo()
        already = self._open_activities(record, kind)
        if kind == "moved" and already:
            env = self._in_language(self.env, already[0].user_id)
            record.message_post(
                body=Markup("<p>%s</p>") % env._(note),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            return Activity
        values = []
        for user in self._recipients(record, settings):
            if user in already.user_id:
                continue
            env = self._in_language(self.env, user)
            values.append(
                {
                    "activity_type_id": activity_type.id,
                    "res_model_id": self.env["ir.model"]._get_id(record._name),
                    "res_id": record.id,
                    "user_id": user.id,
                    "note": Markup("<p>%s</p>") % env._(note),
                    "date_deadline": fields.Date.context_today(record),
                    "automated": True,
                }
            )
        if values and still is not None and not self._lock(record, still):
            return Activity
        return Activity.create(values)

    def _resolve(self, record, kind, what):
        """Close the open activities of `kind` on `record` with the
        feedback « Resolved at <time>: <what> », `what` a lazy
        translation, both in the language of each activity's user and the
        time in their time zone. A `moved` activity is left to a person."""
        if kind == "moved":
            return
        self = self._queued()
        now = fields.Datetime.now()
        for activity in self._open_activities(record, kind):
            user = activity.user_id
            env = self._in_language(self.env, user)
            try:
                zone = pytz.timezone(user.tz or "UTC")
            except pytz.UnknownTimeZoneError:
                zone = pytz.utc
            moment = pytz.utc.localize(now).astimezone(zone)
            activity.action_feedback(
                feedback=env._(
                    "Resolved at %s: %s",
                    moment.strftime("%Y-%m-%d %H:%M %Z"),
                    env._(what),
                )
            )

    def _resolve_all(self, workstation, reason):
        """Close the activities that `workstation` will never solve, now
        that it is archived or has no token (`reason`: a key of ENDINGS):
        its own, and the `unplugged` ones of the decks it holds. `moved`
        activities stay, for a person to close."""
        workstation = workstation.sudo()
        what = ENDINGS[reason]
        for kind in ("silent", "service_failed"):
            self._resolve(workstation, kind, what)
        for device in workstation.device_ids:
            self._resolve(device, "unplugged", what)

    # -- report ----------------------------------------------------------

    def _on_report(
        self,
        workstation,
        moved,
        replugged_devices,
        previous_service_state,
        heard_again=False,
    ):
        """What a report of `workstation` solves or reveals: `moved`, the
        `(device, previous workstation)` pairs of decks it took from
        another workstation; `replugged_devices`, the decks it reports
        connected that were not; `previous_service_state`, the stored state
        before the report; `heard_again`, true when the report ended a
        silence. Closing does not depend on the Settings; they are read
        only for a moved deck, which may open an activity."""
        workstation = workstation.sudo()
        if heard_again:
            self._resolve(workstation, "silent", HEARD_AGAIN)
        if (
            previous_service_state == "failed"
            and workstation.service_state != "failed"
        ):
            self._resolve(
                workstation,
                "service_failed",
                SERVICE_LEFT_FAILED[workstation.service_state],
            )
        for device in replugged_devices:
            self._resolve(device, "unplugged", PLUGGED_AGAIN)
        if moved:
            settings = self._settings()
            for device, previous in moved:
                note = _lt(
                    "The deck moved from workstation %(previous)s to"
                    " %(current)s.",
                    previous=previous.name,
                    current=workstation.name,
                )
                self._open(device, "moved", note, settings)

    # -- cron ------------------------------------------------------------

    @api.model
    def _cron_watch(self):
        """Mark the workstations that went silent, whatever the Settings
        say, then open the activities of the problems that lasted their
        delay; every step is idempotent, so the cron may run again at any
        time."""
        now = fields.Datetime.now()
        settings = self._settings()
        self._watch_silent(now, settings)
        if not settings["enabled"]:
            return
        if settings["alerts"]["service_failed"]:
            self._watch_service_failed(now, settings)
        if settings["alerts"]["unplugged"]:
            self._watch_unplugged(now, settings)

    def _watched_domain(self):
        """The workstations that may still report: active, with a token.
        Any other one would alert without end."""
        return [("active", "=", True), ("token_hash", "!=", False)]

    def _candidates(self, model, domain):
        """The records of `model` that match `domain`, read before any
        lock: each one is locked and checked again before it is
        written."""
        return self.env[model].sudo().search(domain)

    def _watch_silent(self, now, settings):
        """Mark silent each watched workstation that has not reported for
        the silent delay: `silent_since` dated the end of the delay after
        `last_report`, a `silent` event at that time, and its activity.
        The row is locked and read again first, a report that holds or
        has just changed it skipping the workstation until the next run:
        a report never leaves its workstation silent behind it."""
        delay = timedelta(minutes=settings["silent_after_min"])
        domain = self._watched_domain() + [
            ("silent_since", "=", False),
            ("last_report", "<", now - delay),
        ]
        for workstation in self._candidates("streamdeck.workstation", domain):
            if not self._lock(workstation, domain):
                continue
            silent_since = workstation.last_report + delay
            workstation.write({"silent_since": silent_since})
            self.env["streamdeck.service"]._server_event(
                workstation, "silent", silent_since
            )
            note = _lt(
                "The workstation has sent no report for %(minutes)s"
                " minutes.",
                minutes=settings["silent_after_min"],
            )
            self._open(workstation, "silent", note, settings)

    def _lock(self, record, domain):
        """Lock and write the row of `record` (a workstation or a device)
        until the end of the transaction, drop its cached values and tell
        whether it still matches `domain`. False when it no longer does,
        and when a report holds the row or changed it since this
        transaction began, the row then left untouched: the cron skips the
        record until its next run.

        The write keeps a value as it is, so that the row has a new
        version: a report that waits on the lock then fails on a
        serialization error once the cron commits, and Odoo runs it again
        with a snapshot that sees what the cron opened, which a lock alone
        would leave it blind to. The two skips are expected and logged
        nowhere."""
        self.env.flush_all()
        table = SQL.identifier(record._table)
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(
                    SQL(
                        "SELECT id FROM %s WHERE id = %s FOR UPDATE NOWAIT",
                        table,
                        record.id,
                    ),
                    log_exceptions=False,
                )
        except (
            psycopg2.errors.LockNotAvailable,
            psycopg2.errors.SerializationFailure,
        ):
            return False
        self.env.cr.execute(
            SQL(
                "UPDATE %s SET write_date = write_date WHERE id = %s",
                table,
                record.id,
            )
        )
        record.invalidate_recordset()
        return bool(record.search_count(domain + [("id", "=", record.id)]))

    def _watch_service_failed(self, now, settings):
        """Open the activity of each watched workstation whose deck
        service has been `failed` for the delay."""
        minutes = settings["service_failed_after_min"]
        domain = self._watched_domain() + [
            ("service_state", "=", "failed"),
            ("service_state_since", "<=", now - timedelta(minutes=minutes)),
        ]
        note = _lt(
            "The deck service has been in the failed state for at least"
            " %(minutes)s minutes.",
            minutes=minutes,
        )
        for workstation in self._candidates("streamdeck.workstation", domain):
            self._open(
                workstation, "service_failed", note, settings, still=domain
            )

    def _watch_unplugged(self, now, settings):
        """Open the activity of each disconnected deck of a watched
        workstation that has been out of sight for the unplugged delay:
        since its last `unplugged` event or its last report as connected,
        whichever is later, so neither an old event nor a deck removed
        while the workstation was off is counted too early."""
        hours = settings["unplugged_after_h"]
        self.env.flush_all()
        out_of_sight = SQL(
            "SELECT d.id FROM streamdeck_device d"
            " WHERE GREATEST(d.last_seen, (SELECT MAX(e.at)"
            " FROM streamdeck_event e WHERE e.device_id = d.id"
            " AND e.kind = 'unplugged')) <= %s",
            now - timedelta(hours=hours),
        )
        domain = [
            ("connected", "=", False),
            ("workstation_id", "any", self._watched_domain()),
            ("id", "in", SQL("(%s)", out_of_sight)),
        ]
        note = _lt(
            "The deck has been unplugged for at least %(hours)s hours.",
            hours=hours,
        )
        for device in self._candidates("streamdeck.device", domain):
            self._open(device, "unplugged", note, settings, still=domain)


class MailActivity(models.Model):
    """The activity types of the monitoring belong to it: an activity of
    one of them, created or retyped by hand, would make the monitoring
    believe the problem already has its activity, so only sudo writes
    them.

    The check reads the type of the activities created, not the values
    given: the type may come from the values, from the context key
    `default_activity_type_id` or from the default of the model. The
    AccessError it raises rolls the creation back with the transaction."""

    _inherit = "mail.activity"

    @api.model_create_multi
    def create(self, vals_list):
        activities = super().create(vals_list)
        if not self.env.su:
            self._check_not_monitoring(activities.activity_type_id.ids)
        return activities

    def write(self, vals):
        if not self.env.su and "activity_type_id" in vals:
            self._check_not_monitoring([vals["activity_type_id"]])
        return super().write(vals)

    def _check_not_monitoring(self, type_ids):
        monitoring = set()
        for xmlid in ACTIVITY_TYPES.values():
            activity_type = self.env.ref(xmlid, raise_if_not_found=False)
            if activity_type:
                monitoring.add(activity_type.id)
        if monitoring & set(type_ids):
            raise AccessError(
                self.env._(
                    "Only the Stream Deck monitoring opens activities of"
                    " this type."
                )
            )
