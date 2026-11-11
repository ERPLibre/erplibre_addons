# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models
from odoo.tools import SQL


class StreamdeckDeviceHolding(models.Model):
    """The first moment a user's workstation held a deck.

    An employee reads the events of a deck dated from `since` on, besides
    those of their own workstations. One row per (deck, user), written
    once and never moved: a holder who lends the deck and gets it back
    keeps their first `since`. The report service writes it in sudo,
    when it creates a deck on a workstation and when a deck moves to a
    workstation whose user has no row yet, with Odoo's reception time,
    never a time the workstation sent. No group has any right on it.
    """

    _name = "streamdeck.device.holding"
    _description = "Stream Deck device holding"
    _order = "device_id, since, id"
    _rec_name = "device_id"

    device_id = fields.Many2one(
        "streamdeck.device",
        string="Deck",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Employee",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    since = fields.Datetime(string="Held since", required=True, readonly=True)

    _sql_constraints = [
        (
            "device_user_unique",
            "UNIQUE(device_id, user_id)",
            "A user has one first holding per deck.",
        ),
    ]

    def _hold(self, device, user, since):
        """Record that `user` holds `device` from `since`, unless a row
        already dates their first holding."""
        if not self.search_count(
            [("device_id", "=", device.id), ("user_id", "=", user.id)]
        ):
            self.create(
                {"device_id": device.id, "user_id": user.id, "since": since}
            )

    def _backfill(self):
        """Date the holdings of a history written without them, keeping
        any row that exists.

        A user holds a deck from the earliest of the two moments the
        report service dates: the creation of the deck, for the user who
        first had it (the one the earliest `moved` event took it from, or
        its current holder when it never moved); the reception of a
        `moved` event to one of their workstations. Any other event at a
        workstation dates nothing: it may carry the serial of a deck held
        elsewhere. Only times written by Odoo count, never the `at` a
        workstation sent with its own events.
        """
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                """
            INSERT INTO streamdeck_device_holding
                (device_id, user_id, since,
                 create_uid, create_date, write_uid, write_date)
            SELECT held.device_id, held.user_id, MIN(held.since),
                   %(uid)s, NOW() AT TIME ZONE 'UTC',
                   %(uid)s, NOW() AT TIME ZONE 'UTC'
              FROM (
                SELECT d.id AS device_id, w.user_id,
                       d.create_date AS since
                  FROM streamdeck_device d
                  JOIN streamdeck_workstation w ON w.id = COALESCE(
                      (SELECT e.previous_workstation_id
                         FROM streamdeck_event e
                        WHERE e.device_id = d.id AND e.kind = 'moved'
                        ORDER BY e.at, e.id
                        LIMIT 1),
                      d.workstation_id)
                UNION ALL
                SELECT e.device_id, w.user_id, e.received_at
                  FROM streamdeck_event e
                  JOIN streamdeck_workstation w ON w.id = e.workstation_id
                 WHERE e.device_id IS NOT NULL AND e.kind = 'moved'
              ) held
             WHERE held.since IS NOT NULL
             GROUP BY held.device_id, held.user_id
            ON CONFLICT (device_id, user_id) DO NOTHING
            """,
                uid=self.env.uid,
            )
        )
        self.invalidate_model()
