# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.addons.mail_linkup_reflet.models.linkup_report import (
    MODERATION_FIELDS,
)
from odoo.addons.mail_linkup_reflet.models.res_users import ADMIN_GROUP
from odoo.exceptions import AccessError
from odoo.tools import html2plaintext

MODERATOR_GROUP = "mail_linkup_reflet.group_linkup_moderator"
URGENT_TEMPLATE_XMLID = (
    "mail_linkup_community.mail_template_linkup_urgent_report"
)
BAN_TEMPLATE_XMLID = "mail_linkup_community.mail_template_linkup_banned"
# A report waits in the queue in one of these states.
QUEUE_STATES = ("new", "in_review", "appealed")
CLOSED_STATES = ("actioned", "dismissed")
# Delays of the moderation (LU-NF-042), in hours, and other settings.
URGENT_HOURS_PARAM = "linkup.report_urgent_hours"
DEFAULT_URGENT_HOURS = 24
DUE_HOURS_PARAM = "linkup.report_due_hours"
DEFAULT_DUE_HOURS = 72
CONTEXT_PARAM = "linkup.moderation_context_messages"
DEFAULT_CONTEXT_MESSAGES = 3
SUSPENSION_DAYS_PARAM = "linkup.suspension_days"
DEFAULT_SUSPENSION_DAYS = 7
MAX_SUSPENSION_DAYS = 365
REASON_MAX_LENGTH = 2000
# Characters of a message of the context the console shows.
CONTEXT_TEXT_LENGTH = 1000
# The decisions of a moderator, with the action taken they record.
DECISIONS = {
    "dismiss": "none",
    "hide": "hidden",
    "warn": "warning",
    "suspend": "suspended",
    "ban": "banned",
}
NOTICE_OF_ACTION = {
    "hidden": "hidden",
    "warning": "warning",
    "suspended": "suspended",
    "banned": "banned",
}


class LinkupReport(models.Model):
    """The reports of the community and their moderation (LU-F-114,
    LU-F-116, LU-F-118).

    A member reports a reflection, a message or a member, given by user or
    by partner id. A report gets a due date, ``linkup.report_urgent_hours``
    (24) after its creation when it is urgent, ``linkup.report_due_hours``
    (72) otherwise; an urgent report reaches at once, by the bus and by an
    email that tells neither the content nor who reported it, every
    moderator who may process it.

    The console of the moderation (``linkup.moderation``) calls the
    ``linkup_moderation_*`` and ``action_moderation_*`` methods, which
    serve a moderator the reports outside their conflicts of interest only
    (``linkup_moderator_conflict``), administrators included. The content
    and its immediate context are served apart, on demand, each reading
    written to ``linkup.audit.log``, as is every decision and every change
    of the processing made through the ORM. A decision that concerns the
    reported member reaches them as a ``linkup.moderation.notice``, which
    they may contest once; the moderator who decided does not process the
    appeal.
    """

    _inherit = "linkup.report"

    state = fields.Selection(
        selection_add=[("appealed", "Appealed")],
        ondelete={"appealed": "set default"},
    )
    due_date = fields.Datetime(readonly=True, index=True)
    decided_by_id = fields.Many2one(
        "res.users",
        string="Decided by",
        readonly=True,
        ondelete="set null",
        groups=MODERATOR_GROUP,
    )
    decision_date = fields.Datetime(readonly=True, groups=MODERATOR_GROUP)

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    @api.model
    def _linkup_hours(self, urgent):
        Reflet = self.env["linkup.reflet"]
        if urgent:
            return Reflet._linkup_param(
                URGENT_HOURS_PARAM, DEFAULT_URGENT_HOURS
            )
        return Reflet._linkup_param(DUE_HOURS_PARAM, DEFAULT_DUE_HOURS)

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            vals.setdefault(
                "due_date",
                now + timedelta(hours=self._linkup_hours(vals.get("urgent"))),
            )
        reports = super().create(vals_list)
        reports.filtered("urgent")._linkup_notify_moderators()
        return reports

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
        **ignored,
    ):
        """Report as in ``mail_linkup_reflet``; a member is also given by
        ``partner_id``, as the clients of Discuss know them. Return the id
        of the report."""
        if partner_id and not (reflet_id or message_id or user_id):
            user_id = self._linkup_user_of_partner(partner_id)
        return super().action_create_report(
            reflet_id=reflet_id,
            message_id=message_id,
            user_id=user_id,
            reason=reason,
            description=description,
            **ignored,
        )

    @api.model
    def _linkup_user_of_partner(self, partner_id):
        """The internal user of a partner id, or ``-1``, which names
        nobody, so that the check of the reflections module refuses an
        unknown partner as it refuses an unknown user."""
        try:
            partner = (
                self.env["res.partner"]
                .sudo()
                .with_context(active_test=False)
                .browse(int(partner_id))
                .exists()
            )
        except (TypeError, ValueError):
            return -1
        user = partner.user_ids.filtered(lambda user: not user.share)[:1]
        return user.id or -1

    @api.model
    def _linkup_moderators_for(self, reports):
        """The moderators who may process all of ``reports``: active
        internal users of the moderator group, none in a conflict of
        interest with one of them."""
        group = self.env.ref(MODERATOR_GROUP)
        moderators = group.sudo().users.filtered(
            lambda user: user.active
            and not user.share
            and user.id != SUPERUSER_ID
            and user.partner_id
        )
        return moderators.filtered(
            lambda moderator: not reports.sudo()
            .with_user(moderator)
            .filtered("linkup_moderator_conflict")
        )

    def _linkup_notify_moderators(self):
        """Tell the moderators who may process an urgent report that it
        waits (LU-F-114 RM4): a bus notification for those connected and an
        email for all, in their language. Neither one holds the content,
        the reason, nor who reported."""
        template = self.env.ref(
            URGENT_TEMPLATE_XMLID, raise_if_not_found=False
        )
        for report in self.sudo():
            moderators = self._linkup_moderators_for(report)
            for moderator in moderators:
                moderator.partner_id._bus_send(
                    "linkup.moderation/urgent", {"id": report.id}
                )
                if template and moderator.email:
                    template.with_user(SUPERUSER_ID).with_context(
                        linkup_console_url=(
                            f"{moderator.get_base_url()}/odoo/linkup-moderation"
                        ),
                        linkup_urgent_hours=self._linkup_hours(True),
                    ).send_mail(
                        moderator.id,
                        email_values={
                            "model": False,
                            "res_id": False,
                            "author_id": False,
                        },
                    )

    # ------------------------------------------------------------------
    # Conflicts of interest and audit of the ORM
    # ------------------------------------------------------------------

    @api.model
    def _linkup_conflict_domain(self, user):
        """Also in conflict: an appealed report, for the moderator who made
        the contested decision."""
        return [
            "|",
            *super()._linkup_conflict_domain(user),
            "&",
            ("state", "=", "appealed"),
            ("decided_by_id", "=", user.id),
        ]

    def write(self, vals):
        """Write a change of the processing that a moderator makes through
        the ORM to the audit log too."""
        res = super().write(vals)
        if not self.env.su and MODERATION_FIELDS.intersection(vals):
            reason = ", ".join(sorted(MODERATION_FIELDS.intersection(vals)))
            for report in self:
                self.env["linkup.audit.log"]._linkup_log(
                    report, "update", reason
                )
        return res

    # ------------------------------------------------------------------
    # Console of the moderation: reading
    # ------------------------------------------------------------------

    @api.model
    def _linkup_check_moderator(self):
        if not self.env.user._linkup_has_group_id(MODERATOR_GROUP):
            raise AccessError(_("Only a LinkUp moderator can do this."))

    @api.model
    def _linkup_moderation_get(self, report_id):
        """The report ``report_id`` for the current moderator, under
        ``sudo``: one they may process, otherwise ``linkup.unavailable``,
        whether it exists or not."""
        self._linkup_check_moderator()
        try:
            report_id = int(report_id)
        except (TypeError, ValueError):
            report_id = 0
        report = self.sudo().search(
            [("id", "=", report_id), ("linkup_moderator_conflict", "=", False)]
        )
        if not report:
            raise LinkupError(
                "linkup.unavailable", _("This report is not in your queue.")
            )
        return report

    def _linkup_source(self):
        self.ensure_one()
        if self.auto_generated:
            return "auto"
        if self.reflet_id:
            return "reflet"
        if self.message_id:
            return "message"
        return "member"

    @api.model
    def _linkup_display_name(self, user):
        """The pseudonym of a member, as members see it."""
        user = user.sudo()
        return user.partner_id.name or user.name or ""

    def _linkup_row(self):
        """A report as a line of the queue."""
        self.ensure_one()
        report = self.sudo()
        now = fields.Datetime.now()
        return {
            "id": report.id,
            "date": report.create_date,
            "reason": report.reason,
            "urgent": report.urgent,
            "member": self._linkup_display_name(report.reported_user_id),
            "source": report._linkup_source(),
            "state": report.state,
            "due_date": report.due_date or False,
            "overdue": bool(
                report.state in QUEUE_STATES
                and report.due_date
                and report.due_date < now
            ),
            "moderator": (
                self._linkup_display_name(report.moderator_id)
                if report.moderator_id
                else ""
            ),
        }

    @api.model
    def _linkup_queue_domain(self, scope):
        states = CLOSED_STATES if scope == "closed" else QUEUE_STATES
        return [
            ("state", "in", states),
            ("linkup_moderator_conflict", "=", False),
        ]

    @api.model
    @server_context
    def linkup_moderation_summary(self):
        """The counters of the queue of the current moderator (LU-NF-042):
        reports to process, urgent ones, and those past their due date."""
        self._linkup_check_moderator()
        Report = self.sudo()
        domain = self._linkup_queue_domain("open")
        return {
            "open": Report.search_count(domain),
            "urgent": Report.search_count(domain + [("urgent", "=", True)]),
            "overdue": Report.search_count(
                domain + [("due_date", "<", fields.Datetime.now())]
            ),
            "urgent_hours": self._linkup_hours(True),
        }

    @api.model
    @server_context
    def linkup_moderation_queue(self, scope="open", limit=80):
        """The queue of the current moderator, urgent reports first, then
        by date: those to process, or with ``scope="closed"`` the latest
        closed ones. The reports in a conflict of interest with the
        moderator are never in it."""
        self._linkup_check_moderator()
        limit = min(int(limit or 80), 200)
        order = "urgent desc, create_date asc, id asc"
        if scope == "closed":
            order = "decision_date desc, id desc"
        reports = self.sudo().search(
            self._linkup_queue_domain(scope), order=order, limit=limit
        )
        return {
            "rows": [report._linkup_row() for report in reports],
            "summary": self.linkup_moderation_summary(),
        }

    def _linkup_history(self):
        """What the moderation already decided about the reported member,
        as counters."""
        self.ensure_one()
        report = self.sudo()
        member = report.reported_user_id
        if not member:
            return {}
        others = self.sudo().search(
            [("reported_user_id", "=", member.id), ("id", "!=", report.id)]
        )
        return {
            "reports": len(others),
            "open": len(others.filtered(lambda r: r.state in QUEUE_STATES)),
            "warnings": len(
                others.filtered(lambda r: r.action_taken == "warning")
            ),
            "hidden": len(
                others.filtered(lambda r: r.action_taken == "hidden")
            ),
            "suspensions": len(
                others.filtered(lambda r: r.action_taken == "suspended")
            ),
        }

    def _linkup_audit_rows(self):
        self.ensure_one()
        rows = (
            self.env["linkup.audit.log"]
            .sudo()
            .search([("report_id", "=", self.id)], order="date asc, id asc")
        )
        return [
            {
                "id": row.id,
                "date": row.date,
                "actor": self._linkup_display_name(row.actor_id),
                "action": row.action,
                "reason": row.reason or "",
            }
            for row in rows
        ]

    @api.model
    @server_context
    def linkup_moderation_detail(self, report_id):
        """A report of the queue, without the reported content: its reason,
        the comment of the reporter, who reported (a pseudonym), its state,
        due date and decision, the appeal of the member, the counters of
        the history of the member, and its audit log."""
        report = self._linkup_moderation_get(report_id)
        notice = (
            self.env["linkup.moderation.notice"]
            .sudo()
            .search([("report_id", "=", report.id)], limit=1)
        )
        values = report._linkup_row()
        values.update(
            {
                "reporter": (
                    self._linkup_display_name(report.reporter_id)
                    if report.reporter_id
                    else ""
                ),
                "description": report.description or "",
                "action_taken": report.action_taken or "none",
                "decision_date": report.decision_date or False,
                "moderator_note": report.moderator_note or "",
                "is_mine": report.moderator_id == self.env.user,
                "can_hide": bool(
                    report.message_id
                    or report.reflet_id.message_id
                    or report.reflet_id
                ),
                "can_ban": bool(report.reported_user_id)
                and report._linkup_can_sanction(),
                "appeal_text": (
                    notice.appeal_text or ""
                    if notice.appeal_state == "requested"
                    else ""
                ),
                "history": report._linkup_history(),
                "audit": report._linkup_audit_rows(),
                "suspension_days": self.env["linkup.reflet"]._linkup_param(
                    SUSPENSION_DAYS_PARAM, DEFAULT_SUSPENSION_DAYS
                ),
            }
        )
        return values

    @api.model
    def _linkup_context_messages(self, message):
        """The messages around ``message`` in its conversation:
        ``linkup.moderation_context_messages`` (3) before and as many
        after."""
        message = message.sudo()
        if message.model != "discuss.channel" or not message.res_id:
            return message
        count = self.env["linkup.reflet"]._linkup_param(
            CONTEXT_PARAM, DEFAULT_CONTEXT_MESSAGES
        )
        Message = self.env["mail.message"].sudo()
        base = [
            ("model", "=", "discuss.channel"),
            ("res_id", "=", message.res_id),
            ("message_type", "in", ("comment", "email")),
        ]
        before = Message.search(
            base + [("id", "<", message.id)], order="id desc", limit=count
        )
        after = Message.search(
            base + [("id", ">", message.id)], order="id asc", limit=count
        )
        return (before | message | after).sorted("id")

    def _linkup_hidden_original(self, message=None, reflet=None):
        hidden = self.env["linkup.hidden.content"].sudo()
        domain = []
        if message:
            domain = [("message_id", "=", message.id)]
        elif reflet:
            domain = [("reflet_id", "=", reflet.id)]
        return hidden.search(domain, limit=1) if domain else hidden

    def _linkup_message_item(self, message, reported):
        """A message of the context as the console shows it: its author, its
        date and its text; the original of a hidden one for the reported
        message only."""
        message = message.sudo()
        body = message.body
        if message.linkup_hidden and reported:
            body = self._linkup_hidden_original(message=message).body
        text = html2plaintext(body or "").strip()
        reflet = message.linkup_reflet_id
        return {
            "kind": "message",
            "id": message.id,
            "author": message.author_id.name or "",
            "date": message.date,
            "reported": reported,
            "hidden": message.linkup_hidden,
            "text": text[:CONTEXT_TEXT_LENGTH],
            "reflet_category": reflet.category_id.name if reflet else "",
        }

    def _linkup_reflet_item(self, reflet):
        reflet = reflet.sudo()
        texts = reflet
        if reflet.linkup_moderation_hidden:
            texts = self._linkup_hidden_original(reflet=reflet)
        return {
            "kind": "reflet",
            "id": reflet.id,
            "author": reflet.author_id.partner_id.name or "",
            "recipient": reflet.recipient_id.partner_id.name or "",
            "date": reflet.sent_date or reflet.create_date,
            "reported": True,
            "hidden": reflet.linkup_moderation_hidden,
            "state": reflet.state,
            "category": reflet.category_id.name or "",
            "you_said": texts.you_said or "",
            "understood": texts.understood or "",
            "body_text": texts.body_text or "",
        }

    def _linkup_rejections_item(self):
        """For a report of repeated rejections: the rejected reflections of
        the member, by date and category, without their texts."""
        reflets = (
            self.env["linkup.reflet"]
            .sudo()
            .search(
                [
                    ("author_id", "=", self.reported_user_id.id),
                    ("kind", "=", "initial"),
                    ("state", "=", "rejected"),
                ],
                order="answered_date desc",
                limit=20,
            )
        )
        return [
            {
                "kind": "rejection",
                "id": reflet.id,
                "date": reflet.answered_date,
                "category": reflet.category_id.name or "",
            }
            for reflet in reflets
        ]

    @api.model
    @server_context
    def linkup_moderation_content(self, report_id):
        """The reported content and its immediate context, for the current
        moderator (LU-F-116 RM1, RM4).

        Each call writes one row to the audit log, visible to the other
        moderators. A reflection comes with its texts and the messages
        around its carrier; a message with the messages around it; a report
        of repeated rejections with the rejected reflections, without their
        texts; a reported member with no content. Nothing else of the
        conversation is served.
        """
        report = self._linkup_moderation_get(report_id)
        source = report._linkup_source()
        items = []
        record = report.reported_user_id
        if source == "reflet":
            record = report.reflet_id
            items.append(report._linkup_reflet_item(report.reflet_id))
            carrier = report.reflet_id.message_id
            if carrier:
                items += [
                    report._linkup_message_item(message, False)
                    for message in report._linkup_context_messages(carrier)
                    if message != carrier
                ]
        elif source == "message":
            record = report.message_id
            reflet = report.message_id.linkup_reflet_id
            if reflet:
                items.append(report._linkup_reflet_item(reflet))
            items += [
                report._linkup_message_item(
                    message, message == report.message_id
                )
                for message in report._linkup_context_messages(
                    report.message_id
                )
            ]
        elif source == "auto":
            items = report._linkup_rejections_item()
        self.env["linkup.audit.log"]._linkup_log(
            report,
            "content_read",
            _("Processing of the report"),
            record=record or None,
        )
        return {"source": source, "items": items}

    # ------------------------------------------------------------------
    # Console of the moderation: decisions
    # ------------------------------------------------------------------

    @api.model
    def _linkup_clean_reason(self, reason, required=True):
        reason = reason.strip() if isinstance(reason, str) else ""
        if (required and not reason) or len(reason) > REASON_MAX_LENGTH:
            raise LinkupError(
                "linkup.validation",
                _(
                    "Give the reason of the decision, in at most %(count)s"
                    " characters.",
                    count=REASON_MAX_LENGTH,
                ),
                field="reason",
                limit=REASON_MAX_LENGTH,
            )
        return reason

    def _linkup_can_sanction(self):
        """Whether the moderation may sanction the reported member: a
        restricted member who is not a LinkUp administrator."""
        self.ensure_one()
        member = self.sudo().reported_user_id.with_context(active_test=False)
        return bool(member) and (
            member._linkup_is_restricted_member()
            and not member._linkup_has_group_id(ADMIN_GROUP)
        )

    @api.model
    @server_context
    def action_moderation_take(self, report_id):
        """Take a report: it is ``in_review`` and assigned to the current
        moderator, who may then decide. A report another moderator took is
        taken over, which the audit log tells."""
        report = self._linkup_moderation_get(report_id)
        report._linkup_lock()
        if report.state not in ("new", "in_review"):
            raise LinkupError(
                "linkup.already_answered", _("This report is already closed.")
            )
        if (
            report.state == "in_review"
            and report.moderator_id == self.env.user
        ):
            return self.linkup_moderation_detail(report.id)
        report.write({"state": "in_review", "moderator_id": self.env.uid})
        self.env["linkup.audit.log"]._linkup_log(report, "take")
        return self.linkup_moderation_detail(report.id)

    def _linkup_lock(self):
        """Lock the row of the report, so that two decisions do not cross."""
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM linkup_report WHERE id = %s FOR NO KEY UPDATE",
            [self.id],
        )
        self.invalidate_recordset()

    @api.model
    @server_context
    def action_moderation_decide(self, report_id, decision, reason, days=None):
        """Decide on a report the current moderator took (LU-F-116 RM2).

        ``decision`` is ``dismiss`` (no follow-up), ``hide`` (the reported
        message or reflection, ``linkup.hidden.content``), ``warn``,
        ``suspend`` for ``days`` days (``linkup.suspension_days``, 7, by
        default, at most 365), or ``ban`` (the account is closed and a hash
        of its address keeps it from signing up again, LU-F-116 RM6).
        ``reason`` is required and goes to the audit log. Every decision but
        ``dismiss`` reaches the reported member as a notice, with the
        appeal it allows; the reporter only sees their report closed.
        """
        report = self._linkup_moderation_get(report_id)
        report._linkup_lock()
        if decision not in DECISIONS:
            raise LinkupError(
                "linkup.validation", _("Choose a decision."), field="decision"
            )
        reason = self._linkup_clean_reason(reason)
        if report.state != "in_review" or report.moderator_id != self.env.user:
            raise LinkupError(
                "linkup.already_answered",
                _("Take the report before deciding."),
            )
        member = report.reported_user_id.with_context(active_test=False)
        if decision in ("suspend", "ban", "warn") and not (
            report._linkup_can_sanction()
        ):
            raise LinkupError(
                "linkup.validation",
                _("The moderation cannot sanction this account."),
                field="decision",
            )
        audit_record = None
        notice_values = {}
        if decision == "hide":
            message = report.message_id or report.reflet_id.message_id
            reflet = report.reflet_id or message.linkup_reflet_id
            if not message and not reflet:
                raise LinkupError(
                    "linkup.validation",
                    _("This report holds no content to hide."),
                    field="decision",
                )
            self.env["linkup.hidden.content"]._linkup_hide(
                report, message, reflet
            )
            audit_record = message or reflet
        elif decision == "suspend":
            try:
                days = int(
                    days
                    or self.env["linkup.reflet"]._linkup_param(
                        SUSPENSION_DAYS_PARAM, DEFAULT_SUSPENSION_DAYS
                    )
                )
            except (TypeError, ValueError):
                days = 0
            if not 1 <= days <= MAX_SUSPENSION_DAYS:
                raise LinkupError(
                    "linkup.validation",
                    _(
                        "A suspension lasts from 1 to %(count)s days.",
                        count=MAX_SUSPENSION_DAYS,
                    ),
                    field="days",
                )
            until = fields.Datetime.now() + timedelta(days=days)
            member.sudo().write({"linkup_suspended_until": until})
            notice_values["suspended_until"] = until
            reason = f"{reason} ({days} d)"
        elif decision == "ban":
            report._linkup_ban(member)
        action = DECISIONS[decision]
        report.write(
            {
                "state": "dismissed" if decision == "dismiss" else "actioned",
                "action_taken": action,
                "decided_by_id": self.env.uid,
                "decision_date": fields.Datetime.now(),
                "moderator_note": reason,
            }
        )
        self.env["linkup.audit.log"]._linkup_log(
            report, decision, reason, record=audit_record
        )
        if action in NOTICE_OF_ACTION and member:
            notice = (
                self.env["linkup.moderation.notice"]
                .sudo()
                .create(
                    {
                        "user_id": member.id,
                        "report_id": report.id,
                        "decision": NOTICE_OF_ACTION[action],
                        "reason": report.reason,
                        **notice_values,
                    }
                )
            )
            notice._linkup_notify()
        return self.linkup_moderation_detail(report.id)

    def _linkup_ban(self, member):
        """Close the account of ``member``: a hash of its address goes to
        ``linkup.email.blocklist`` for 24 months, the account is archived,
        which ends its sessions, and an email tells the person, with the
        address to write to for a recourse."""
        self.ensure_one()
        member = member.sudo()
        if member.email:
            self.env["linkup.email.blocklist"]._linkup_add(
                member.email, "banned"
            )
        template = self.env.ref(BAN_TEMPLATE_XMLID, raise_if_not_found=False)
        if template and member.email:
            template.with_user(SUPERUSER_ID).with_context(
                linkup_appeal_days=self.env[
                    "linkup.moderation.notice"
                ]._linkup_appeal_days()
            ).send_mail(
                member.id,
                email_values={
                    "model": False,
                    "res_id": False,
                    "author_id": False,
                },
            )
        member.write({"active": False})

    def _linkup_reopen_for_appeal(self, notice):
        """Put the report back in the queue for the appeal of the member,
        the audit log telling it."""
        self.ensure_one()
        report = self.sudo()
        report._linkup_lock()
        report.write({"state": "appealed"})
        self.env["linkup.audit.log"]._linkup_log(report, "appeal")

    @api.model
    @server_context
    def action_moderation_resolve_appeal(self, report_id, uphold, reason):
        """Close the appeal of a report. Upheld, the decision stays; reversed,
        the hidden content comes back, the suspension ends, and the report is
        dismissed. The member is told either way."""
        report = self._linkup_moderation_get(report_id)
        report._linkup_lock()
        if report.state != "appealed":
            raise LinkupError(
                "linkup.already_answered",
                _("This report has no appeal to close."),
            )
        reason = self._linkup_clean_reason(reason)
        notice = (
            self.env["linkup.moderation.notice"]
            .sudo()
            .search([("report_id", "=", report.id)], limit=1)
        )
        values = {
            "moderator_id": self.env.uid,
            "decision_date": fields.Datetime.now(),
            "moderator_note": reason,
        }
        if uphold:
            values["state"] = "actioned"
        else:
            self.env["linkup.hidden.content"].sudo().search(
                [("report_id", "=", report.id)]
            )._linkup_restore()
            if report.action_taken == "suspended":
                report.reported_user_id.sudo().write(
                    {"linkup_suspended_until": False}
                )
            values.update(state="dismissed", action_taken="none")
        report.write(values)
        self.env["linkup.audit.log"]._linkup_log(
            report, "uphold" if uphold else "reverse", reason
        )
        if notice:
            notice.write(
                {
                    "appeal_state": "upheld" if uphold else "reversed",
                    "seen": False,
                }
            )
            notice._linkup_notify()
        return self.linkup_moderation_detail(report.id)

    # ------------------------------------------------------------------
    # The member
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def linkup_my_reports(self, limit=50):
        """The reports the current member made, the most recent first:
        their date, reason, what they reported and where they stand,
        ``received``, ``in_review`` or ``closed``. The decision itself
        belongs to the reported member."""
        self.env["linkup.reflet"]._linkup_check_member()
        reports = self.sudo().search(
            [("reporter_id", "=", self.env.uid)],
            order="create_date desc, id desc",
            limit=min(int(limit or 50), 200),
        )
        progress = {
            "new": "received",
            "in_review": "in_review",
            "appealed": "in_review",
            "actioned": "closed",
            "dismissed": "closed",
        }
        return [
            {
                "id": report.id,
                "date": report.create_date,
                "reason": report.reason,
                "urgent": report.urgent,
                "source": report._linkup_source(),
                "member": self._linkup_display_name(report.reported_user_id),
                "progress": progress.get(report.state, "received"),
            }
            for report in reports
        ]
