# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ..client_context import server_context
from ..exceptions import LinkupError
from .res_users import ADMIN_GROUP

# Reasons a member gives (LU-F-114 RM2), and the one of the reports the
# server creates by itself (LU-F-023 RM5).
REPORT_REASONS = [
    ("harassment", "Harassment"),
    ("hate", "Hate speech"),
    ("sexual", "Sexual content"),
    ("threat", "Threat"),
    ("minor", "Minor in danger"),
    ("distress", "Person in distress or at risk for themselves"),
    ("spam", "Spam"),
    ("impersonation", "Impersonation"),
    ("other", "Other"),
    ("repeated_rejections", "Repeated rejections"),
]
MEMBER_REASONS = frozenset(code for code, _label in REPORT_REASONS) - {
    "repeated_rejections"
}
# A report for one of these reasons is urgent (LU-F-114 RM4).
URGENT_REASONS = frozenset({"threat", "minor", "distress"})
OPEN_STATES = ("new", "in_review")
# What a moderator writes on a report: its processing, never what was
# reported nor by whom.
MODERATION_FIELDS = frozenset(
    {"state", "moderator_id", "action_taken", "moderator_note"}
)

DEFAULT_MAX_REPORTS_PER_DAY = 20
DEFAULT_DESCRIPTION_MAX_LENGTH = 2000
DEFAULT_REJECTION_ALERT_COUNT = 5
DEFAULT_REJECTION_ALERT_DAYS = 30
# A recipient whose account is younger counts for no rejection alert.
REJECTION_ALERT_ACCOUNT_DAYS = 7


class LinkupReport(models.Model):
    """A report of a reflection, a message or a member, for the moderators.

    A member creates one through ``action_create_report`` only, which forces
    the reporter to the current user, derives the reported member from the
    content, sets ``urgent`` from the reason and ignores every other field:
    ``state``, ``moderator_id``, ``action_taken``, ``auto_generated``. The
    reporter must read the reported content with their own rights. The
    reported member is never told who reported them, nor that a report
    exists.

    ``_linkup_check_rejections`` creates the report of the server itself:
    too many rejections of the reflections of one author, from distinct
    recipients (LU-F-023 RM5). It never sanctions anyone by itself.

    Members read the reports they made; moderators read and process the
    others, except those in a conflict of interest with them
    (``linkup_moderator_conflict``, LU-F-116 RM5), and write only the
    fields of their processing (``MODERATION_FIELDS``); LinkUp
    administrators manage them all, under the same exception.
    """

    _name = "linkup.report"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp report"
    _order = "urgent desc, create_date desc, id desc"

    reporter_id = fields.Many2one(
        "res.users", index=True, ondelete="set null", readonly=True
    )
    reported_user_id = fields.Many2one(
        "res.users",
        string="Reported member",
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    message_id = fields.Many2one(
        "mail.message", ondelete="set null", readonly=True
    )
    reflet_id = fields.Many2one(
        "linkup.reflet", ondelete="set null", readonly=True
    )
    reason = fields.Selection(REPORT_REASONS, required=True, readonly=True)
    description = fields.Text(string="Comment", readonly=True)
    urgent = fields.Boolean(readonly=True, index=True)
    auto_generated = fields.Boolean(readonly=True)
    state = fields.Selection(
        [
            ("new", "New"),
            ("in_review", "In review"),
            ("actioned", "Actioned"),
            ("dismissed", "Dismissed"),
        ],
        required=True,
        default="new",
        index=True,
    )
    moderator_id = fields.Many2one(
        "res.users",
        ondelete="set null",
        groups="mail_linkup_reflet.group_linkup_moderator",
    )
    action_taken = fields.Selection(
        [
            ("none", "None"),
            ("hidden", "Hidden"),
            ("warning", "Warning"),
            ("suspended", "Suspended"),
            ("banned", "Banned"),
        ],
        default="none",
        groups="mail_linkup_reflet.group_linkup_moderator",
    )
    moderator_note = fields.Text(
        groups="mail_linkup_reflet.group_linkup_moderator"
    )
    # Evaluated for the current user at each search, so that the record
    # rule of the moderators follows the links as they change.
    linkup_moderator_conflict = fields.Boolean(
        string="Conflict of interest",
        compute="_compute_linkup_moderator_conflict",
        search="_search_linkup_moderator_conflict",
    )

    @api.model
    def _linkup_conflict_user_ids(self, user):
        """The users whose reports ``user`` does not process: themself, and
        every member they share a link with, in any state."""
        links = (
            self.env["linkup.link"]
            .sudo()
            .search(
                ["|", ("user_a_id", "=", user.id), ("user_b_id", "=", user.id)]
            )
        )
        return {user.id} | set(links.user_a_id.ids) | set(links.user_b_id.ids)

    @api.model
    def _linkup_conflict_domain(self, user):
        """The reports in a conflict of interest with ``user``: those they
        made, those about them, and those whose reporter or reported member
        shares a link with them."""
        user_ids = list(self._linkup_conflict_user_ids(user))
        return [
            "|",
            ("reporter_id", "in", user_ids),
            ("reported_user_id", "in", user_ids),
        ]

    @api.depends_context("uid")
    def _compute_linkup_moderator_conflict(self):
        conflicted = set(
            self.sudo()
            .search(
                [("id", "in", self.ids)]
                + self._linkup_conflict_domain(self.env.user)
            )
            .ids
        )
        for report in self:
            report.linkup_moderator_conflict = report.id in conflicted

    def _search_linkup_moderator_conflict(self, operator, value):
        if operator not in ("=", "!="):
            raise NotImplementedError(
                f"Operator {operator} is not supported on a conflict."
            )
        query = self.sudo()._search(
            self._linkup_conflict_domain(self.env.user)
        )
        inside = (operator == "=") == bool(value)
        return [("id", "in" if inside else "not in", query)]

    @api.model
    def _linkup_param(self, key, default):
        return self.env["linkup.reflet"]._linkup_param(key, default)

    def write(self, vals):
        """Keep what was reported, and by whom, out of a moderator's reach:
        the access rights let a moderator write a report, and the
        ``readonly`` of a field binds the forms only. Nobody but the server
        processes a report in a conflict of interest with them, their own
        reports included, which the rule of the members lets them read: a
        LinkUp administrator neither, though they read every report."""
        if not self.env.su:
            if set(vals) - MODERATION_FIELDS and not (
                self.env.user._linkup_has_group_id(ADMIN_GROUP)
            ):
                raise AccessError(
                    _("A moderator changes only the processing of a report.")
                )
            self._linkup_check_no_conflict()
        return super().write(vals)

    def unlink(self):
        """A LinkUp administrator deletes a report, but not one in a
        conflict of interest with them; the retention of the closed reports
        deletes them under ``sudo``."""
        if not self.env.su:
            self._linkup_check_no_conflict()
        return super().unlink()

    def _linkup_check_no_conflict(self):
        if self.filtered("linkup_moderator_conflict"):
            raise AccessError(
                _(
                    "A moderator does not process a report that concerns"
                    " them or one of their links."
                )
            )

    @api.model
    def _linkup_reported_content(self, reflet_id, message_id, user_id):
        """The content a member reports and its author, read with the
        rights of the member.

        Exactly one of the three ids is given. A member is reported by a
        reporter who reads them, or shares a link with them in any state:
        a block closes the scope of the pair, and its two parties still
        report each other, as before the block. A reflection, a message or
        a member the reporter cannot reach that way, or that does not
        exist, gets the same refusal. Return ``(reflection, message,
        reported user)``, the records under ``sudo``.
        """
        unavailable = LinkupError(
            "linkup.unavailable", _("This content cannot be reported.")
        )
        given = [value for value in (reflet_id, message_id, user_id) if value]
        if len(given) != 1:
            raise LinkupError(
                "linkup.validation",
                _("Report one reflection, one message or one member."),
                field="target",
            )
        try:
            target_id = int(given[0])
        except (TypeError, ValueError):
            raise unavailable from None
        reflet = self.env["linkup.reflet"]
        message = self.env["mail.message"]
        if reflet_id:
            reflet = reflet.search([("id", "=", target_id)])
            if not reflet:
                raise unavailable
            reported = reflet.sudo().author_id
        elif message_id:
            message = message.browse(target_id).exists()
            try:
                message.check_access("read")
            except AccessError:
                raise unavailable from None
            if not message:
                raise unavailable
            reported = (
                message.sudo()
                .author_id.with_context(active_test=False)
                .user_ids.filtered(lambda user: not user.share)[:1]
            )
        else:
            reported = self.env["res.users"].search([("id", "=", target_id)])
            if not reported:
                linked = (
                    self.env["res.users"].sudo().browse(target_id).exists()
                )
                if not (
                    linked
                    and self.env["linkup.link"]._get_between(
                        self.env.user, linked
                    )
                ):
                    raise unavailable
                reported = linked
        if reported == self.env.user:
            raise LinkupError(
                "linkup.validation",
                _("You cannot report yourself."),
                field="target",
            )
        return reflet.sudo(), message.sudo(), reported.sudo()

    @api.model
    @server_context
    def action_create_report(
        self,
        reflet_id=None,
        message_id=None,
        user_id=None,
        reason="other",
        description=None,
        **ignored,
    ):
        """Report a reflection, a message or a member, as the current user.

        ``reason`` is one of the reasons of a member; the server sets
        ``urgent`` from it. ``description`` is an optional comment. Any
        other value a client sends, such as ``urgent``, ``auto_generated``,
        ``state`` or ``moderator_id``, is ignored. A
        member makes at most ``linkup.max_reports_per_day`` reports a day,
        then gets ``linkup.rate_limited``. Reporting again what the member
        already reported for the same reason, while that report is open,
        returns it. Return
        the id of the report.
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
        reflet, message, reported = self._linkup_reported_content(
            reflet_id, message_id, user_id
        )
        # The row of the reporter serializes two reports at once, so that
        # the daily limit and the repeated report hold.
        self.flush_model(["reporter_id", "create_date"])
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id = %s FOR NO KEY UPDATE NOWAIT",
            [me.id],
        )
        Report = self.sudo()
        current = Report.search(
            [
                ("reporter_id", "=", me.id),
                ("reflet_id", "=", reflet.id),
                ("message_id", "=", message.id),
                ("reported_user_id", "=", reported.id),
                ("reason", "=", reason),
                ("state", "in", OPEN_STATES),
            ],
            limit=1,
        )
        if current:
            return current.id
        maximum = self._linkup_param(
            "linkup.max_reports_per_day", DEFAULT_MAX_REPORTS_PER_DAY
        )
        since = fields.Datetime.now() - timedelta(days=1)
        if (
            Report.search_count(
                [("reporter_id", "=", me.id), ("create_date", ">=", since)]
            )
            >= maximum
        ):
            raise LinkupError(
                "linkup.rate_limited",
                _("Too many reports for now, try again later."),
            )
        report = Report.create(
            {
                "reporter_id": me.id,
                "reported_user_id": reported.id,
                "reflet_id": reflet.id,
                "message_id": message.id,
                "reason": reason,
                "description": description or False,
                "urgent": reason in URGENT_REASONS,
            }
        )
        return report.id

    @api.model
    def _linkup_check_rejections(self, author):
        """Report an author whose reflections too many members rejected.

        The rejections of the last ``linkup.rejection_alert_days`` days
        count once per recipient, for the recipients whose account is at
        least seven days old and who share no active link with another
        counted recipient: a group of linked members counts as one, so
        that a coordinated rejection weighs little. Beyond
        ``linkup.rejection_alert_count`` recipients, the server creates a
        report for the moderators, once while it is open. It suspends
        nobody.
        """
        author = author.sudo()
        maximum = self._linkup_param(
            "linkup.rejection_alert_count", DEFAULT_REJECTION_ALERT_COUNT
        )
        days = self._linkup_param(
            "linkup.rejection_alert_days", DEFAULT_REJECTION_ALERT_DAYS
        )
        now = fields.Datetime.now()
        rejected = (
            self.env["linkup.reflet"]
            .sudo()
            .search(
                [
                    ("author_id", "=", author.id),
                    ("kind", "=", "initial"),
                    ("state", "=", "rejected"),
                    ("answered_date", ">=", now - timedelta(days=days)),
                ]
            )
        )
        account_limit = now - timedelta(days=REJECTION_ALERT_ACCOUNT_DAYS)
        recipients = rejected.recipient_id.filtered(
            lambda user: user.create_date and user.create_date <= account_limit
        )
        if len(recipients) <= maximum:
            return
        links = (
            self.env["linkup.link"]
            .sudo()
            .search(
                [
                    ("state", "=", "active"),
                    ("user_a_id", "in", recipients.ids),
                    ("user_b_id", "in", recipients.ids),
                ]
            )
        )
        linked = {}
        for link in links:
            linked.setdefault(link.user_a_id.id, set()).add(link.user_b_id.id)
            linked.setdefault(link.user_b_id.id, set()).add(link.user_a_id.id)
        counted = set()
        for user_id in sorted(recipients.ids):
            if not linked.get(user_id, set()) & counted:
                counted.add(user_id)
        if len(counted) <= maximum:
            return
        Report = self.sudo()
        if Report.search_count(
            [
                ("reported_user_id", "=", author.id),
                ("reason", "=", "repeated_rejections"),
                ("state", "in", OPEN_STATES),
            ]
        ):
            return
        Report.create(
            {
                "reported_user_id": author.id,
                "reason": "repeated_rejections",
                "auto_generated": True,
            }
        )
