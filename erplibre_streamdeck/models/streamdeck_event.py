# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models

from .streamdeck_workstation import SERVICE_STATES


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
        ],
        required=True,
    )
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

    _sql_constraints = [
        ("uuid_unique", "UNIQUE(uuid)", "An event uuid is unique."),
    ]
