# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, models
from odoo.exceptions import ValidationError


class EventTableSeatClaim(models.AbstractModel):
    """One seat is claimed once per table and round.

    fields.Integer stores int(value or 0), so an empty seat number is 0
    and never NULL: a SQL UNIQUE index would collide on every unnumbered
    seat. The rule therefore lives in Python and covers only seat
    numbers above zero.

    An heir names the fields it compares through the two attributes
    below, since two models need not name them alike, and declares its
    own @api.constrains over them: Odoo resolves a constraint's field
    names against the model carrying the decorator, and an abstract
    model holds none of these fields.
    """

    _name = "event.table.seat.claim"
    _description = "Seat Claim Uniqueness"

    # The fields scoping a claim, then the field holding the seat number
    # itself. An heir naming them otherwise overrides these.
    _seat_claim_scope_fields = ("plan_id", "round_number", "table_id")
    _seat_claim_seat_field = "seat_number"

    def _seat_claim_error(self):
        """Message raised when two rows claim the same seat."""
        return _("A seat is claimed once per table and round.")

    def _check_seat_claim_unique(self):
        """Refuse a row claiming a seat another row of the model holds.

        Seat 0 means "no seat" and never collides, so it is skipped
        rather than compared.
        """
        seat_field = self._seat_claim_seat_field
        for record in self:
            seat = record[seat_field]
            if seat <= 0:
                continue
            domain = [("id", "!=", record.id), (seat_field, "=", seat)]
            for name in self._seat_claim_scope_fields:
                value = record[name]
                if isinstance(value, models.BaseModel):
                    value = value.id
                domain.append((name, "=", value))
            if self.search_count(domain):
                raise ValidationError(record._seat_claim_error())
