# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.tools import SQL

from .streamdeck_workstation import SERVICE_STATES

# The kinds that Odoo writes itself; no workstation sends them.
SERVER_KINDS = frozenset({"moved", "silent", "heard_again"})


class StreamdeckEvent(models.Model):
    """An event observed by a workstation, deduplicated by `uuid`.

    The workstation creates the uuid and the time `at`; Odoo adds the
    reception time. `workstation_name` and `employee_name` are copied at
    creation: they keep what the event was when it happened, and they let
    an employee who reads the deck's history read where it went without
    any access to that workstation.

    A `moved` event is Odoo's own, never a workstation's: the report that
    declares a deck held by another workstation creates it, with a uuid
    drawn by Odoo and the reception time as `at`. `workstation_id` is the
    new holder and `previous_workstation_id` the one it left, its name
    copied in `previous_workstation_name` as the other names are.

    `silent` and `heard_again` are Odoo's own too, about a workstation and
    no deck: `silent` is dated the end of the silent delay after the last
    report, `heard_again` the reception of the report that ends the
    silence. `label` names the event in the user's language: the state of
    the service for a `service_changed`, the kind for any other.

    `visible_to_me` is true for the current user on the events of a deck
    they hold or held, dated from their first holding on
    (`streamdeck.device.holding`); the record rule of the employees
    opens these, besides the events of their own workstations.
    """

    _name = "streamdeck.event"
    _description = "Stream Deck event"
    _order = "at desc, id desc"
    _rec_name = "uuid"

    uuid = fields.Char(string="UUID", required=True, readonly=True)
    kind = fields.Selection(
        [
            ("plugged", "Plugged"),
            ("unplugged", "Unplugged"),
            ("service_changed", "Service changed"),
            ("moved", "Changed workstation"),
            ("silent", "Workstation silent"),
            ("heard_again", "Workstation heard again"),
        ],
        required=True,
    )
    label = fields.Char(string="Event", compute="_compute_label")
    at = fields.Datetime(string="Time")
    received_at = fields.Datetime(string="Received")
    device_id = fields.Many2one(
        "streamdeck.device",
        string="Deck",
        index=True,
        ondelete="restrict",
    )
    workstation_id = fields.Many2one(
        "streamdeck.workstation",
        string="Workstation",
        required=True,
        index=True,
        ondelete="restrict",
    )
    workstation_name = fields.Char(string="Workstation name")
    previous_workstation_id = fields.Many2one(
        "streamdeck.workstation",
        string="Previous workstation",
        readonly=True,
        index=True,
        ondelete="restrict",
    )
    previous_workstation_name = fields.Char(string="Previous workstation name")
    employee_name = fields.Char(string="Employee")
    service_state = fields.Selection(SERVICE_STATES, string="Deck service")
    visible_to_me = fields.Boolean(
        string="From my holding",
        compute="_compute_visible_to_me",
        search="_search_visible_to_me",
        help="An event of a deck you hold or held, dated from the first"
        " moment one of your workstations held it.",
    )

    _sql_constraints = [
        ("uuid_unique", "UNIQUE(uuid)", "An event uuid is unique."),
    ]

    @api.depends("kind", "service_state")
    @api.depends_context("lang")
    def _compute_label(self):
        services = {
            "active": _("Service started"),
            "failed": _("Service failed"),
            "inactive": _("Service stopped"),
            "absent": _("Service absent"),
        }
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for event in self:
            label = False
            if event.kind == "service_changed":
                label = services.get(event.service_state)
            event.label = label or kinds.get(event.kind, False)

    def _held_by_me_sql(self):
        """The ids of the events that `visible_to_me` selects, for the
        user of the environment, sudo or not: an event of a deck with a
        holding of this user whose `since` is not after the event."""
        self.env["streamdeck.device.holding"].flush_model()
        self.flush_model(["device_id", "at"])
        return SQL(
            "SELECT e.id FROM streamdeck_event e"
            " JOIN streamdeck_device_holding h"
            " ON h.device_id = e.device_id AND h.since <= e.at"
            " WHERE h.user_id = %s",
            self.env.uid,
        )

    def _compute_visible_to_me(self):
        ids = [event.id for event in self if isinstance(event.id, int)]
        self.env.cr.execute(
            SQL("%s AND e.id = ANY(%s)", self._held_by_me_sql(), ids)
        )
        visible = {row[0] for row in self.env.cr.fetchall()}
        for event in self:
            event.visible_to_me = event.id in visible

    def _search_visible_to_me(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise NotImplementedError(
                "visible_to_me is searched with = or != and a boolean"
            )
        selected = (operator == "=") == value
        return [
            (
                "id",
                "in" if selected else "not in",
                SQL("(%s)", self._held_by_me_sql()),
            )
        ]
