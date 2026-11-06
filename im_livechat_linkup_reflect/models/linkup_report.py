# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.addons.mail_linkup_community.models.res_users import (
    HELP_RESOURCES_PARAM,
    MODERATION_HOURS_PARAM,
)
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.addons.mail_linkup_reflet.models.linkup_report import (
    DEFAULT_DESCRIPTION_MAX_LENGTH,
    DEFAULT_MAX_REPORTS_PER_DAY,
    MEMBER_REASONS,
    OPEN_STATES,
    URGENT_REASONS,
)


class LinkupReport(models.Model):
    """The reports of the live chat (LU-F-126, LU-F-127 RM6).

    A report of distress opens, on the server, a conversation of the
    distress channel between its reporter and an available moderator in no
    conflict of interest with it (``im_livechat.channel``); without one,
    the report stays urgent in the queue and the reporter reads the help
    resources (RM3). A visitor, who has no account, reports a distress
    from the welcome chatbot (``reporter_guest_id``); the member who
    operates a live chat conversation reports its visitor
    (``reported_guest_id``), the report carrying the conversation.
    """

    _inherit = "linkup.report"

    reporter_guest_id = fields.Many2one(
        "mail.guest",
        string="Reporting visitor",
        index="btree_not_null",
        ondelete="set null",
        readonly=True,
    )
    reported_guest_id = fields.Many2one(
        "mail.guest",
        string="Reported visitor",
        index="btree_not_null",
        ondelete="set null",
        readonly=True,
    )
    livechat_conversation_id = fields.Many2one(
        "discuss.channel",
        string="Live chat conversation",
        index="btree_not_null",
        ondelete="set null",
        readonly=True,
        help="The live chat conversation the report comes from.",
    )
    distress_channel_id = fields.Many2one(
        "discuss.channel",
        string="Distress conversation",
        index="btree_not_null",
        ondelete="set null",
        readonly=True,
        help="The conversation with a moderator that the report opened.",
    )

    # ------------------------------------------------------------------
    # Distress (LU-F-126)
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def action_create_report(
        self,
        reflet_id=None,
        message_id=None,
        user_id=None,
        reason="other",
        description=None,
        partner_id=None,
        previous_operator_id=None,
        **ignored,
    ):
        """Report as in ``mail_linkup_community``; a report of distress
        then opens a conversation with a moderator (RM1).
        ``previous_operator_id``, the partner of the moderator of a former
        conversation, is preferred only while that moderator is in no
        conflict of interest with the report (RM2)."""
        report_id = super().action_create_report(
            reflet_id=reflet_id,
            message_id=message_id,
            user_id=user_id,
            reason=reason,
            description=description,
            partner_id=partner_id,
            **ignored,
        )
        report = self.sudo().browse(report_id)
        if report.reason == "distress":
            report._linkup_open_distress(previous_operator_id)
        return report_id

    def _linkup_open_distress(self, previous_operator_id=None):
        """Open the conversation of distress of a report of a member,
        unless one of it is still open. Each opening is written to the
        audit log (RM4, LU-NF-040). Return the conversation, or an empty
        recordset."""
        self.ensure_one()
        report = self.sudo()
        current = report.distress_channel_id
        if current.livechat_active:
            return current
        if not report.reporter_id:
            return current.browse()
        conversation = self.env["im_livechat.channel"]._linkup_open_distress(
            report, report.reporter_id, previous_operator_id
        )
        if conversation:
            report.distress_channel_id = conversation
            self.env["linkup.audit.log"]._linkup_log(
                report,
                "distress_open",
                _("Conversation of distress opened by the server"),
                record=conversation,
            )
        return conversation

    @api.model
    def _linkup_help_resources(self):
        """The help resources of LU-F-118 RM2, one per line, in the
        language of the context: those of ``linkup.help_resources``, or the
        crisis line and the emergency number of Canada, the texts the web
        client of ``mail_linkup_community`` shows."""
        params = self.env["ir.config_parameter"].sudo()
        lines = [
            line.strip()
            for line in (
                params.get_param(HELP_RESOURCES_PARAM, "") or ""
            ).splitlines()
            if line.strip()
        ]
        return lines or [
            _(
                "9-8-8: suicide crisis helpline, by phone or text message,"
                " at any time (Canada)."
            ),
            _("9-1-1: emergency services, when a life is in danger."),
        ]

    @api.model
    def _linkup_distress_notice(self):
        """The reminder that LinkUp is not an emergency service
        (LU-F-118 RM3)."""
        return _(
            "LinkUp is not an emergency service: in an immediate danger,"
            " call 9-1-1. A person of the moderation reads this"
            " conversation."
        )

    @api.model
    def _linkup_help_info(self):
        """The help resources, the hours of the moderation and the delay
        within which an urgent report is processed, as "Need help now"
        shows them."""
        params = self.env["ir.config_parameter"].sudo()
        return {
            "resources": self._linkup_help_resources(),
            "moderation_hours": (
                params.get_param(MODERATION_HOURS_PARAM, "") or ""
            ).strip(),
            "urgent_hours": self._linkup_hours(True),
        }

    def _linkup_distress_info(self):
        """What the reporter of a distress reads once the report is made:
        the conversation opened with a moderator, or, without one, the help
        resources, the hours of the moderation and the delay within which
        the urgent report is processed (RM3, LU-NF-042)."""
        self.ensure_one()
        report = self.sudo()
        conversation = report.distress_channel_id
        opened = bool(conversation.livechat_active)
        return {
            "report_id": report.id,
            "channel_id": conversation.id if opened else False,
            "queued": not opened,
            **self._linkup_help_info(),
        }

    @api.model
    @server_context
    def linkup_distress_info(self, report_id):
        """The state of the distress report ``report_id`` for its reporter,
        as ``_linkup_distress_info`` gives it; any other report, or
        another reporter, reads ``linkup.unavailable``."""
        self.env["linkup.reflet"]._linkup_check_member()
        try:
            report_id = int(report_id)
        except (TypeError, ValueError):
            report_id = 0
        report = self.sudo().search(
            [
                ("id", "=", report_id),
                ("reporter_id", "=", self.env.uid),
                ("reason", "=", "distress"),
            ]
        )
        if not report:
            raise LinkupError(
                "linkup.unavailable", _("This report is unavailable.")
            )
        return report._linkup_distress_info()

    @api.model
    def _linkup_livechat_distress(self, conversation, user, guest):
        """The urgent report of distress of the party of a live chat
        conversation, a visitor (``reporter_guest_id``) or a member: the
        one still open for this conversation, or a new one."""
        Report = self.sudo()
        domain = [
            ("reason", "=", "distress"),
            ("livechat_conversation_id", "=", conversation.id),
            ("state", "in", OPEN_STATES),
        ]
        if guest:
            domain.append(("reporter_guest_id", "=", guest.id))
        else:
            domain.append(("reporter_id", "=", user.id))
        report = Report.search(domain, limit=1)
        if report:
            return report
        return Report.create(
            {
                "reporter_id": user.id,
                "reporter_guest_id": guest.id,
                "reason": "distress",
                "urgent": True,
                "livechat_conversation_id": conversation.id,
            }
        )

    # ------------------------------------------------------------------
    # Report of a visitor (LU-F-127 RM6)
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def action_report_livechat_visitor(
        self, channel_id, reason="other", description=None
    ):
        """Report the visitor of a live chat conversation, as the member
        who operates it.

        The report carries the conversation, the visitor and their last
        message, whose context the console of the moderation serves. The
        reasons, the comment, the urgency and the daily limit are those of
        ``action_create_report``. Return the id of the report.
        """
        Reflet = self.env["linkup.reflet"]
        Reflet._linkup_check_member()
        me = self.env.user
        if reason not in MEMBER_REASONS:
            raise LinkupError(
                "linkup.validation", _("Choose a reason."), field="reason"
            )
        description = (
            description.strip() if isinstance(description, str) else ""
        )
        if len(description) > DEFAULT_DESCRIPTION_MAX_LENGTH:
            raise LinkupError(
                "linkup.validation",
                _(
                    "A comment holds at most %(count)s characters.",
                    count=DEFAULT_DESCRIPTION_MAX_LENGTH,
                ),
                field="description",
                limit=DEFAULT_DESCRIPTION_MAX_LENGTH,
            )
        conversation, user, guest = Reflet._linkup_livechat_party(channel_id)
        _user, visitor = Reflet._linkup_livechat_counterpart(
            conversation, user, guest
        )
        message = (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", conversation.id),
                    ("author_guest_id", "=", visitor.id),
                ],
                order="id desc",
                limit=1,
            )
        )
        self.flush_model(["reporter_id", "create_date"])
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id = %s FOR NO KEY UPDATE NOWAIT",
            [me.id],
        )
        Report = self.sudo()
        current = Report.search(
            [
                ("reporter_id", "=", me.id),
                ("reported_guest_id", "=", visitor.id),
                ("reason", "=", reason),
                ("state", "in", OPEN_STATES),
            ],
            limit=1,
        )
        if current:
            return current.id
        self._linkup_check_daily_reports(me)
        return Report.create(
            {
                "reporter_id": me.id,
                "reported_guest_id": visitor.id,
                "livechat_conversation_id": conversation.id,
                "message_id": message.id,
                "reason": reason,
                "description": description or False,
                "urgent": reason in URGENT_REASONS,
            }
        ).id

    @api.model
    def _linkup_check_daily_reports(self, user):
        """The daily limit of the reports of a member,
        ``linkup.max_reports_per_day``, as ``action_create_report`` counts
        it."""
        maximum = self._linkup_param(
            "linkup.max_reports_per_day", DEFAULT_MAX_REPORTS_PER_DAY
        )
        since = fields.Datetime.subtract(fields.Datetime.now(), days=1)
        if (
            self.sudo().search_count(
                [("reporter_id", "=", user.id), ("create_date", ">=", since)]
            )
            >= maximum
        ):
            raise LinkupError(
                "linkup.rate_limited",
                _("Too many reports for now, try again later."),
            )

    # ------------------------------------------------------------------
    # Console of the moderation
    # ------------------------------------------------------------------

    def _linkup_row(self):
        """A report about a visitor names the visitor."""
        values = super()._linkup_row()
        report = self.sudo()
        if not report.reported_user_id and report.reported_guest_id:
            values["member"] = report.reported_guest_id.name or ""
        return values

    @api.model
    @server_context
    def linkup_moderation_detail(self, report_id):
        """A report made by a visitor names the visitor."""
        values = super().linkup_moderation_detail(report_id)
        report = self.sudo().browse(values["id"])
        if not report.reporter_id and report.reporter_guest_id:
            values["reporter"] = report.reporter_guest_id.name or ""
        return values

    @api.model
    def _linkup_check_collusion(self, reflet):
        """A reflection of a live chat has no pair: no loop of a pair nor
        of new accounts is counted on it."""
        if not reflet.link_id:
            return None
        return super()._linkup_check_collusion(reflet)
