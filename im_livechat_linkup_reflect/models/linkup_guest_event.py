# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import api, fields, models

EXPIRY_PARAM = "linkup.guest_event_expiry_days"
DEFAULT_EXPIRY_DAYS = 30


class LinkupGuestEvent(models.Model):
    """A scoring event of a reflection with a visitor, waiting for the
    signup of that visitor (Q-43, LU-F-127 RM5).

    A visitor has no account, so neither a ledger line nor karma: the event
    is held here, without points, for the visitor (``guest_id``) and the
    member on the other side (``counterpart_user_id``), who earns theirs at
    the same moment. ``event_key`` is the key the ledger receives, the one
    of the reflection, or the one of the pair for an event a pair earns
    once, so that an event held twice is held once (``UNIQUE``), and paid
    twice is paid once (the ledger is unique per rule, member and key).

    Once the visitor signs up from the same browser and verifies the
    address, ``_linkup_release`` reports each event to the core with its
    key, the rules of the scale and their caps applying as to any event;
    the rows are then deleted. Those still waiting after
    ``linkup.guest_event_expiry_days`` days (30) are deleted by a daily
    cron, without points. No group has access: the server reads and writes
    them under ``sudo``.
    """

    _name = "linkup.guest.event"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp scoring event of a visitor, pending"
    _order = "id"

    guest_id = fields.Many2one(
        "mail.guest",
        string="Visitor",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    code = fields.Char(required=True, readonly=True)
    counterpart_user_id = fields.Many2one(
        "res.users",
        string="Member of the pair",
        ondelete="cascade",
        readonly=True,
    )
    reflet_id = fields.Many2one(
        "linkup.reflet",
        string="Reflection",
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    event_key = fields.Char(string="Event key", required=True, readonly=True)
    date = fields.Datetime(
        required=True, readonly=True, default=fields.Datetime.now, index=True
    )

    _sql_constraints = [
        (
            "event_unique",
            "UNIQUE(guest_id, code, event_key)",
            "An event of a visitor is held once.",
        ),
    ]

    @api.model
    def _linkup_hold(self, guest, code, reflet, counterpart, key=None):
        """Hold the event ``code`` of ``reflet`` for the visitor ``guest``
        and the member ``counterpart``, keyed by ``key``, or as the ledger
        keys an event of a reflection; an event already held under that
        key stays as it is. The caller holds the lock of the
        reflection."""
        guest.ensure_one()
        event_key = key or f"reflet:{reflet.id}"
        Event = self.sudo()
        current = Event.search(
            [
                ("guest_id", "=", guest.id),
                ("code", "=", code),
                ("event_key", "=", event_key),
            ],
            limit=1,
        )
        if current:
            return current
        return Event.create(
            {
                "guest_id": guest.id,
                "code": code,
                "counterpart_user_id": counterpart.id,
                "reflet_id": reflet.id,
                "event_key": event_key,
            }
        )

    @api.model
    def _linkup_release(self, guest):
        """Report the events held for ``guest``, oldest first, then delete
        them.

        The reflections of the visitor are already given to their new
        account (``res.users._linkup_livechat_attach``): the parties of the
        event are those of its reflection, and the rules pay each of them
        as for any event, idempotently by ``event_key``.
        """
        events = self.sudo().search([("guest_id", "=", guest.id)])
        for event in events:
            reflet = event.reflet_id
            if not reflet:
                continue
            reflet._linkup_event(
                event.code,
                reflet._linkup_parties(),
                link=reflet.link_id,
                channel=reflet.channel_id,
                key=event.event_key,
            )
        events.unlink()
        return True

    @api.model
    def _linkup_expiry_days(self):
        return self.env["linkup.reflet"]._linkup_param(
            EXPIRY_PARAM, DEFAULT_EXPIRY_DAYS
        )

    @api.model
    def _cron_linkup_expire(self):
        """Delete the events held longer than
        ``linkup.guest_event_expiry_days`` days, and expire the reflections
        of the live chat left unanswered."""
        limit = fields.Datetime.now() - timedelta(
            days=max(self._linkup_expiry_days(), 1)
        )
        self.sudo().search([("date", "<", limit)]).unlink()
        self.env["linkup.reflet"]._cron_expire_livechat_reflets()
        return True
