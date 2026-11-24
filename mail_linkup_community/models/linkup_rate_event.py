# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.tools import SQL
from odoo.tools.misc import hmac

# Scope of the keyed hash of a key of a limit.
KEY_HASH_SCOPE = "linkup.rate.event"
# Days an event is kept: the longest window of a limit is one day.
RETENTION_DAYS = 2
# Table of one row per locked key, outside the ORM: no record of it is ever
# read, only written to serialize the transactions on one key.
LOCK_TABLE = "linkup_rate_event_lock"


class LinkupRateEvent(models.Model):
    """The attempts that the limits of LinkUp count (LU-NF-006): a kind and
    a keyed hash of what is counted, an IP address or a user, never the
    value itself. A limit counts the events of its kind and key within its
    window; a daily cron deletes those older than two days.

    No group has access: the server reads and writes them under ``sudo``.
    """

    _name = "linkup.rate.event"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp rate limit event"
    _order = "id desc"

    kind = fields.Selection(
        [
            ("signup", "Public signup"),
            ("verification", "Verification email"),
        ],
        required=True,
        index=True,
        readonly=True,
    )
    key_hash = fields.Char(required=True, index=True, readonly=True)

    def init(self):
        super().init()
        self.env.cr.execute(
            SQL(
                "CREATE TABLE IF NOT EXISTS %s (key_hash varchar PRIMARY KEY,"
                " locked_at timestamp NOT NULL)",
                SQL.identifier(LOCK_TABLE),
            )
        )

    @api.model
    def _linkup_key(self, value):
        return hmac(self.env(su=True), KEY_HASH_SCOPE, str(value))

    @api.model
    def _linkup_count(self, kind, value, window):
        """The events of ``kind`` for ``value`` within ``window``, a
        ``timedelta`` ending now."""
        return self.sudo().search_count(
            [
                ("kind", "=", kind),
                ("key_hash", "=", self._linkup_key(value)),
                ("create_date", ">", fields.Datetime.now() - window),
            ]
        )

    @api.model
    def _linkup_exceeded(self, kind, value, limit, window):
        """Whether ``limit`` events of ``kind`` for ``value`` already
        happened within ``window``."""
        return self._linkup_count(kind, value, window) >= limit

    @api.model
    def _linkup_check(self, kind, value, limit, window, message=None):
        """Refuse with ``linkup.rate_limited`` once the limit is reached."""
        if self._linkup_exceeded(kind, value, limit, window):
            raise LinkupError(
                "linkup.rate_limited",
                message or _("Too many attempts for now, try again later."),
            )

    @api.model
    def _linkup_lock(self, kind, values):
        """Serialize, until the end of the transaction, the transactions
        that count and add events of ``kind`` for any of ``values``.

        A limit counts, then adds its event: two transactions at once
        would each count without the event of the other, and both pass.
        Each key writes its row of ``LOCK_TABLE``, in a fixed order: a
        second transaction waits for the first, then, under the
        ``REPEATABLE READ`` of Odoo, fails with a serialization error once
        the first commits, since the row changed after its snapshot. The
        RPC layer retries it (``odoo.service.model.retrying``), and the
        retry counts the event of the first.
        """
        keys = sorted(
            {f"{kind}:{self._linkup_key(value)}" for value in values}
        )
        for key in keys:
            self.env.cr.execute(
                SQL(
                    "INSERT INTO %s (key_hash, locked_at) VALUES (%s, %s)"
                    " ON CONFLICT (key_hash) DO UPDATE"
                    " SET locked_at = EXCLUDED.locked_at",
                    SQL.identifier(LOCK_TABLE),
                    key,
                    fields.Datetime.now(),
                )
            )

    @api.model
    def _linkup_hit(self, kind, value):
        """Count one event of ``kind`` for ``value``."""
        return self.sudo().create(
            {"kind": kind, "key_hash": self._linkup_key(value)}
        )

    @api.model
    def _cron_linkup_purge(self):
        """Delete the events older than ``RETENTION_DAYS`` days."""
        self.sudo().search(
            [
                (
                    "create_date",
                    "<",
                    fields.Datetime.now() - timedelta(days=RETENTION_DAYS),
                )
            ]
        ).unlink()
        self.env.cr.execute(
            SQL(
                "DELETE FROM %s WHERE locked_at < %s",
                SQL.identifier(LOCK_TABLE),
                fields.Datetime.now() - timedelta(days=RETENTION_DAYS),
            )
        )
        return True
