# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.tools.misc import hmac

# Scope of the keyed hash of a key of a limit.
KEY_HASH_SCOPE = "linkup.rate.event"
# Days an event is kept: the longest window of a limit is one day.
RETENTION_DAYS = 2


class LinkupRateEvent(models.Model):
    """The attempts that the limits of LinkUp count (LU-NF-006): a kind and
    a keyed hash of what is counted, an address IP or a user, never the
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
        return True
