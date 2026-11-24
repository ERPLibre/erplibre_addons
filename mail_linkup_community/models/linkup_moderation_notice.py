# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError

NOTICE_DECISIONS = [
    ("hidden", "Content hidden"),
    ("warning", "Warning"),
    ("suspended", "Suspension"),
    ("banned", "Account closed"),
]
APPEAL_STATES = [
    ("none", "No appeal"),
    ("requested", "Appeal under review"),
    ("upheld", "Decision upheld"),
    ("reversed", "Decision reversed"),
]
APPEAL_DAYS_PARAM = "linkup.appeal_days"
DEFAULT_APPEAL_DAYS = 14
APPEAL_MAX_LENGTH = 2000


class LinkupModerationNotice(models.Model):
    """A decision of the moderation, as the member it concerns reads it
    (LU-F-116 RM3).

    The member reads the decision, its reason and the end of a suspension,
    never the report behind it: neither who reported, nor what they wrote.
    A member contests a decision once, within ``linkup.appeal_days`` days,
    through ``action_appeal``: the report goes back to the queue, where the
    moderator who decided does not process it. A ban is contested outside
    LinkUp, the account being closed.

    Members read their own notices and write none; the server writes them
    under ``sudo``.
    """

    _name = "linkup.moderation.notice"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp moderation decision notified to a member"
    _order = "create_date desc, id desc"

    user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        ondelete="cascade",
        index=True,
    )
    report_id = fields.Many2one(
        "linkup.report",
        required=True,
        readonly=True,
        ondelete="cascade",
        groups="base.group_system",
    )
    decision = fields.Selection(NOTICE_DECISIONS, required=True, readonly=True)
    reason = fields.Selection(
        selection=lambda self: self.env["linkup.report"]
        ._fields["reason"]
        ._description_selection(self.env),
        readonly=True,
    )
    suspended_until = fields.Datetime(readonly=True)
    appeal_state = fields.Selection(
        APPEAL_STATES, default="none", required=True, readonly=True
    )
    appeal_text = fields.Text(readonly=True)
    appeal_date = fields.Datetime(readonly=True)
    seen = fields.Boolean(readonly=True)

    @api.model
    def _linkup_appeal_days(self):
        return self.env["linkup.reflet"]._linkup_param(
            APPEAL_DAYS_PARAM, DEFAULT_APPEAL_DAYS
        )

    def _linkup_can_appeal(self):
        self.ensure_one()
        notice = self.sudo()
        return (
            notice.decision != "banned"
            and notice.appeal_state == "none"
            and notice.create_date
            >= fields.Datetime.now()
            - timedelta(days=self._linkup_appeal_days())
        )

    def _linkup_info(self):
        """A notice as the profile of the member shows it."""
        self.ensure_one()
        notice = self.sudo()
        return {
            "id": notice.id,
            "date": notice.create_date,
            "decision": notice.decision,
            "reason": notice.reason or False,
            "suspended_until": notice.suspended_until or False,
            "appeal_state": notice.appeal_state,
            "can_appeal": notice._linkup_can_appeal(),
            "seen": notice.seen,
        }

    @api.model
    @server_context
    def linkup_my_notices(self):
        """The decisions about the current member, the most recent first."""
        self.env["linkup.reflet"]._linkup_check_member()
        return [
            notice._linkup_info()
            for notice in self.search([("user_id", "=", self.env.uid)])
        ]

    @api.model
    def _linkup_unseen_count(self, user):
        return self.sudo().search_count(
            [("user_id", "=", user.id), ("seen", "=", False)]
        )

    @api.model
    @server_context
    def action_mark_seen(self):
        """The member read their decisions."""
        self.env["linkup.reflet"]._linkup_check_member()
        self.sudo().search(
            [("user_id", "=", self.env.uid), ("seen", "=", False)]
        ).write({"seen": True})
        return True

    @server_context
    def action_appeal(self, text):
        """Contest a decision about the current member with ``text``.

        Refused with ``linkup.unavailable`` for a notice of another member,
        and with ``linkup.validation`` once contested, after the delay, for
        a ban or without a text. The report of the decision goes back to the
        queue of the moderation, its audit log telling who contested.
        """
        self.env["linkup.reflet"]._linkup_check_member()
        notice = self.search(
            [("id", "in", self.ids), ("user_id", "=", self.env.uid)]
        )
        if len(notice) != 1 or len(self) != 1:
            raise LinkupError(
                "linkup.unavailable", _("This decision cannot be contested.")
            )
        text = text.strip() if isinstance(text, str) else ""
        if not text or len(text) > APPEAL_MAX_LENGTH:
            raise LinkupError(
                "linkup.validation",
                _(
                    "Explain why in at most %(count)s characters.",
                    count=APPEAL_MAX_LENGTH,
                ),
                field="appeal_text",
                limit=APPEAL_MAX_LENGTH,
            )
        notice = notice.sudo()
        if not notice._linkup_can_appeal():
            raise LinkupError(
                "linkup.validation",
                _("This decision can no longer be contested."),
                field="appeal_text",
            )
        notice.write(
            {
                "appeal_state": "requested",
                "appeal_text": text,
                "appeal_date": fields.Datetime.now(),
            }
        )
        notice.report_id._linkup_reopen_for_appeal(notice)
        return notice._linkup_info()

    def _linkup_notify(self):
        """Tell the member, if connected, that a decision concerns them."""
        for notice in self.sudo():
            notice.user_id.partner_id._bus_send(
                "linkup.moderation/notice", {"id": notice.id}
            )
