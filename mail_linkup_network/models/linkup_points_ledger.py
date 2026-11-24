# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import math

from odoo import api, fields, models
from odoo.tools import SQL

# Half-life of the energy, in days (Q-41). An unset or invalid parameter
# takes the default; 0 or below turns the decay off.
HALF_LIFE_PARAM = "linkup.energy_half_life_days"
DEFAULT_HALF_LIFE_DAYS = 90
# Halvings at most in the weight of a line: 2 ** -1000 is still a float of
# PostgreSQL, whose ``POWER`` raises an underflow below about 2 ** -1074.
MAX_HALVINGS = 1000
DAY_SECONDS = 86400


def round_half_up(value):
    """Round a decayed sum of points to the nearest integer, halves up."""
    return math.floor(value + 0.5)


class LinkupPointsLedger(models.Model):
    """The energy of the Network view decays with time (Q-41).

    A line of the ledger weighs ``2 ** (-d / H)`` in an energy: ``d`` is
    the number of whole days since its date, ``H`` the half-life
    ``linkup.energy_half_life_days`` (90 days). A line keeps its full
    weight its first day, half of it after ``H`` days, a quarter after
    ``2 H``. The decay is computed when an energy is read, from the dated
    lines: the ledger, append-only and keyed by ``event_key``, and the karma
    never change, so the karma still equals the sum of the lines
    (LU-NF-043). Each reading is one query grouped by the column asked for,
    on the indexes ``(user_id, date)`` and ``link_id``, however many
    contacts the member holds.

    An unset or invalid parameter takes 90 days, the decision of the owner;
    0 or below turns the decay off, every line keeping its full weight.
    """

    _inherit = "linkup.points.ledger"

    @api.model
    def _linkup_half_life_days(self):
        """The half-life of the energy in days, 0 when it does not
        decay."""
        days = self.env["linkup.reflet"]._linkup_param(
            HALF_LIFE_PARAM, DEFAULT_HALF_LIFE_DAYS
        )
        return max(days, 0)

    @api.model
    def _linkup_energy_sums(self, domain, groupby):
        """The points of the lines of ``domain``, grouped by the column
        ``groupby``: ``{value: (points, energy)}``, ``points`` their plain
        sum, ``energy`` their sum weighted by the decay, rounded to the
        nearest integer. A group without a line is absent."""
        Ledger = self.sudo()
        Ledger.flush_model(["user_id", "link_id", "points", "date"])
        query = Ledger._search(domain)
        if query.is_empty():
            return {}
        table = Ledger._table
        column = SQL.identifier(table, groupby)
        points = SQL.identifier(table, "points")
        half_life = self._linkup_half_life_days()
        if half_life:
            weight = SQL(
                "POWER(0.5::float8, LEAST(FLOOR(GREATEST(EXTRACT(EPOCH FROM"
                " (%s - %s))::float8, 0) / %s) / %s, %s))",
                fields.Datetime.now(),
                SQL.identifier(table, "date"),
                DAY_SECONDS,
                float(half_life),
                MAX_HALVINGS,
            )
        else:
            weight = SQL("1")
        query.groupby = column
        self.env.cr.execute(
            query.select(
                column,
                SQL("SUM(%s)", points),
                SQL("SUM(%s * %s)", points, weight),
            )
        )
        return {
            value: (int(total or 0), round_half_up(energy or 0))
            for value, total, energy in self.env.cr.fetchall()
        }
