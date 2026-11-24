# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The personal data of a member: export, erasure of an account and the
retention periods (LU-F-117, LU-NF-014, LU-NF-015, Q-23, Q-31).

``linkup.personal.data`` holds no row. ``_linkup_export`` gathers what an
account wrote and received, ``_linkup_erase_accounts`` anonymizes accounts
and erases their content, and ``_cron_linkup_retention`` applies every
retention period, each run picking up whatever the previous ones left: the
purges replayed after the restoration of a backup catch up the same way.
"""

import logging
import secrets
from datetime import datetime

from dateutil.relativedelta import relativedelta
from odoo import Command, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.tools import SQL, html2plaintext, is_html_empty

from .. import tools
from .linkup_report import CLOSED_STATES, QUEUE_STATES

_logger = logging.getLogger(__name__)

EXPORT_FORMAT = "linkup.personal_data"
EXPORT_VERSION = 1

# Retention periods (LU-NF-015, Q-31): parameter, unit and default value.
# A value below 1 falls back to the default, so that a wrong setting never
# purges everything at once.
RETENTION = {
    "deletion_grace": ("linkup.deletion_grace_days", "days", 30),
    "draft": ("linkup.retention_draft_days", "days", 30),
    "closed_reflet": ("linkup.retention_closed_reflet_months", "months", 12),
    "inactive_pair": ("linkup.retention_inactive_pair_months", "months", 24),
    "closed_report": ("linkup.retention_closed_report_months", "months", 24),
    "unverified": ("linkup.retention_unverified_days", "days", 30),
}
# Fields of the partner of an erased account set to ``False``, when the
# installed modules define them.
PARTNER_ERASED_FIELDS = (
    "email",
    "phone",
    "mobile",
    "image_1920",
    "street",
    "street2",
    "zip",
    "city",
    "state_id",
    "country_id",
    "website",
    "comment",
    "function",
    "vat",
    "ref",
)
# States of a reflection whose texts the retention erases after
# ``closed_reflet``.
CLOSED_REFLET_STATES = ("rejected", "expired")


def to_text(value):
    """A date or datetime as the export writes it, ``None`` for none."""
    if not value:
        return None
    if isinstance(value, datetime):
        return fields.Datetime.to_string(value)
    return fields.Date.to_string(value)


class LinkupPersonalData(models.AbstractModel):
    _name = "linkup.personal.data"
    _description = "LinkUp personal data"

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    @api.model
    def _linkup_period(self, kind):
        """The retention period ``kind`` of ``RETENTION``, as a
        ``relativedelta``."""
        key, unit, default = RETENTION[kind]
        value = self.env["linkup.reflet"]._linkup_param(key, default)
        return relativedelta(**{unit: value if value >= 1 else default})

    @api.model
    def _linkup_cutoff(self, kind):
        """The moment before which the period ``kind`` is over."""
        return fields.Datetime.now() - self._linkup_period(kind)

    @api.model
    def _linkup_deleted_name(self):
        """The name of an erased account, in the language of the company."""
        lang = self.env.company.partner_id.lang or self.env.lang
        return self.with_context(lang=lang).env._("Deleted member")

    # ------------------------------------------------------------------
    # Export (LU-F-117 RM1, LU-NF-014)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_export(self, user):
        """Everything LinkUp keeps about ``user``, as JSON-ready values:
        profile, consents, reflections written and received, messages
        written, points ledger, links, highlights, invitations, reports
        made, blocks and decisions of the moderation.

        A reflection between two other members never appears, nor the
        address, the phone or the photo of another person: the other party
        of an exchange is named by their pseudonym. A received reflection
        follows what its recipient reads (no draft, no withdrawn or phantom
        one); the hidden themes of a reflection go to its author only.
        """
        user = user.sudo()
        member = user.with_context(lang=user.lang or self.env.lang).env
        return {
            "format": EXPORT_FORMAT,
            "version": EXPORT_VERSION,
            "generated": to_text(fields.Datetime.now()),
            "profile": self._linkup_export_profile(user),
            "consents": self._linkup_export_consents(user),
            "reflections": self.with_env(member)._linkup_export_reflets(user),
            "messages": self._linkup_export_messages(user),
            "points": self.with_env(member)._linkup_export_points(user),
            "links": self._linkup_export_links(user),
            "highlights": self._linkup_export_highlights(user),
            "invitations": self._linkup_export_invitations(user),
            "reports": self._linkup_export_reports(user),
            "blocked_members": [
                self._linkup_name(block.blocked_id)
                for block in self.env["linkup.block"]
                .sudo()
                .search([("blocker_id", "=", user.id)])
            ],
            "moderation_decisions": self._linkup_export_notices(user),
        }

    @api.model
    def _linkup_name(self, user):
        """The pseudonym of another member, the only thing of them an
        export holds."""
        return (user.partner_id.name or user.name) if user else None

    @api.model
    def _linkup_export_profile(self, user):
        partner = user.partner_id
        return {
            "pseudonym": partner.name,
            "email": partner.email or None,
            "email_verified": bool(user.linkup_email_verified),
            "phone": partner.phone or None,
            "language": user.lang or None,
            "age_range": user.linkup_age_bracket or None,
            "declared_residence": user.linkup_jurisdiction or None,
            "first_reflection_from": user.linkup_first_reflet_scope or None,
            "personal_code": tools.format_code(user.linkup_personal_code)
            or None,
            "created": to_text(user.create_date),
            "deletion_requested": to_text(user.linkup_deletion_requested_date),
        }

    @api.model
    def _linkup_export_consents(self, user):
        consents = (
            self.env["linkup.consent"]
            .sudo()
            .search([("user_id", "=", user.id)], order="date, id")
        )
        return [
            {
                "purpose": consent.purpose,
                "granted": consent.granted,
                "version": consent.version,
                "date": to_text(consent.date),
            }
            for consent in consents
        ]

    @api.model
    def _linkup_export_reflets(self, user):
        reflets = (
            self.env["linkup.reflet"]
            .sudo()
            .search(
                [
                    "|",
                    ("author_id", "=", user.id),
                    ("recipient_id", "=", user.id),
                ],
                order="id",
            )
        )
        reflets = reflets.filtered(
            lambda reflet: reflet.author_id == user
            or (
                reflet.state not in ("draft", "withdrawn")
                and not reflet.phantom
            )
        )
        secrets_by_reflet = {
            secret.reflet_id.id: secret
            for secret in self.env["linkup.reflet.secret"]
            .sudo()
            .search(
                [
                    (
                        "reflet_id",
                        "in",
                        reflets.filtered(
                            lambda reflet: reflet.author_id == user
                        ).ids,
                    )
                ]
            )
        }
        rows = []
        for reflet in reflets:
            authored = reflet.author_id == user
            other = reflet.recipient_id if authored else reflet.author_id
            row = {
                "id": reflet.id,
                "role": "author" if authored else "recipient",
                "other_member": self._linkup_name(other),
                "kind": reflet.kind,
                "state": reflet.state,
                "category": reflet.category_id.name or None,
                "you_said": reflet.you_said or None,
                "understood": reflet.understood or None,
                "text": reflet.body_text or None,
                "content_removed": reflet.linkup_content_removed,
                "exchange_in_person": reflet.real_world_declared,
                "exchange_date": to_text(reflet.real_world_date),
                "previous_reflection": reflet.parent_id.id or None,
                "sent": to_text(reflet.sent_date),
                "read": to_text(reflet.read_date),
                "answered": to_text(reflet.answered_date),
            }
            secret = secrets_by_reflet.get(reflet.id)
            if secret:
                row["hidden_themes"] = secret.category_ids.mapped("name")
            rows.append(row)
        return rows

    @api.model
    def _linkup_export_messages(self, user):
        """The messages the member wrote in their conversations, as plain
        text; the carrier messages of the reflections, which LinkUp writes,
        are left out."""
        Message = self.env["mail.message"].sudo()
        messages = Message.search(
            [
                ("author_id", "=", user.partner_id.id),
                ("model", "=", "discuss.channel"),
                ("message_type", "=", "comment"),
            ],
            order="id",
        )
        messages -= messages.filtered("linkup_reflet_ids")
        channels = {
            channel.id: channel
            for channel in self.env["discuss.channel"]
            .sudo()
            .browse(set(messages.mapped("res_id")))
            .exists()
        }
        rows = []
        for message in messages:
            channel = channels.get(message.res_id)
            rows.append(
                {
                    "id": message.id,
                    "date": to_text(message.date),
                    "conversation": message.res_id,
                    "conversation_kind": (
                        channel.channel_type if channel else None
                    ),
                    "text": html2plaintext(message.body or "") or None,
                    "attachments": message.attachment_ids.mapped("name"),
                    "hidden_by_moderation": message.linkup_hidden,
                }
            )
        return rows

    @api.model
    def _linkup_export_points(self, user):
        lines = (
            self.env["linkup.points.ledger"]
            .sudo()
            .search([("user_id", "=", user.id)], order="date, id")
        )
        return {
            "balance": user.karma,
            "lines": [
                {
                    "date": to_text(line.date),
                    "rule": line.rule_id.code,
                    "label": line.rule_id.name,
                    "points": line.points,
                    "capped": line.capped,
                    "cap_reason": line.cap_reason or None,
                    "other_member": self._linkup_name(line.partner_user_id),
                }
                for line in lines
            ],
        }

    @api.model
    def _linkup_export_links(self, user):
        links = (
            self.env["linkup.link"]
            .sudo()
            .search(
                [
                    "|",
                    ("user_a_id", "=", user.id),
                    ("user_b_id", "=", user.id),
                ],
                order="id",
            )
        )
        return [
            {
                "other_member": self._linkup_name(
                    link.user_b_id
                    if link.user_a_id == user
                    else link.user_a_id
                ),
                "state": link.state,
                "first_link": to_text(link.first_link_date),
                "last_interaction": to_text(link.last_interaction_date),
                "energy": link._linkup_energy_for(user),
            }
            for link in links
        ]

    @api.model
    def _linkup_export_highlights(self, user):
        highlights = (
            self.env["linkup.highlight"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    "|",
                    ("sender_id", "=", user.id),
                    "&",
                    ("recipient_id", "=", user.id),
                    ("phantom", "=", False),
                ],
                order="id",
            )
        )
        return [
            {
                "direction": "sent" if light.sender_id == user else "received",
                "other_member": self._linkup_name(
                    light.recipient_id
                    if light.sender_id == user
                    else light.sender_id
                ),
                "date": to_text(light.create_date),
                "active": light.active,
                "ended": to_text(light.extinguished_date),
                "end_reason": light.extinguished_reason or None,
            }
            for light in highlights
        ]

    @api.model
    def _linkup_export_invitations(self, user):
        invitations = (
            self.env["linkup.invitation"]
            .sudo()
            .search([("inviter_id", "=", user.id)], order="id")
        )
        return [
            {
                "date": to_text(invitation.create_date),
                "to": invitation.display_name,
                "name_to_remember": invitation.name or None,
                "state": invitation.state,
                "expires": to_text(invitation.expiry_date),
            }
            for invitation in invitations
        ]

    @api.model
    def _linkup_export_reports(self, user):
        reports = (
            self.env["linkup.report"]
            .sudo()
            .search([("reporter_id", "=", user.id)], order="id")
        )
        progress = {state: "closed" for state in CLOSED_STATES}
        progress.update(new="received", in_review="in_review")
        progress["appealed"] = "in_review"
        return [
            {
                "date": to_text(report.create_date),
                "reason": report.reason,
                "comment": report.description or None,
                "reported_member": self._linkup_name(report.reported_user_id),
                "progress": progress.get(report.state, "received"),
            }
            for report in reports
        ]

    @api.model
    def _linkup_export_notices(self, user):
        notices = (
            self.env["linkup.moderation.notice"]
            .sudo()
            .search([("user_id", "=", user.id)], order="id")
        )
        return [
            {
                "date": to_text(notice.create_date),
                "decision": notice.decision,
                "reason": notice.reason or None,
                "suspended_until": to_text(notice.suspended_until),
                "appeal": notice.appeal_text or None,
                "appeal_state": notice.appeal_state or None,
            }
            for notice in notices
        ]

    # ------------------------------------------------------------------
    # Erasure of an account (LU-F-117 RM2, Q-23)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_held_messages(self, messages):
        """The messages of ``messages`` a report still open points to."""
        return (
            self.env["linkup.report"]
            .sudo()
            .search(
                [
                    ("message_id", "in", messages.ids),
                    ("state", "in", QUEUE_STATES),
                ]
            )
            .message_id
        )

    @api.model
    def _linkup_erase_messages(self, messages):
        """Erase the content of ``messages`` for good: body, subject,
        attachments (voice messages included), link previews, tracking
        values and the emails not sent yet. The address of the author
        leaves every message, the carrier messages of the reflections
        included, whose neutral sentence stays. The conversations receive
        the emptied messages, which their clients then draw as removed.
        """
        messages = messages.sudo()
        if not messages:
            return
        messages.write({"email_from": False, "reply_to": False})
        plain = messages - messages.filtered("linkup_reflet_ids")
        plain = plain.filtered(
            lambda message: not is_html_empty(message.body)
            or message.subject
            or message.attachment_ids
            or message.link_preview_ids
        )
        if not plain:
            return
        attachments = plain.attachment_ids
        plain.write(
            {
                "body": "",
                "subject": False,
                "attachment_ids": [Command.clear()],
            }
        )
        attachments.unlink()
        plain.link_preview_ids.unlink()
        plain.tracking_value_ids.unlink()
        self.env["mail.mail"].sudo().search(
            [("mail_message_id", "in", plain.ids)]
        ).unlink()
        for channel_id in set(
            plain.filtered(lambda m: m.model == "discuss.channel").mapped(
                "res_id"
            )
        ):
            channel = self.env["discuss.channel"].sudo().browse(channel_id)
            in_channel = plain.filtered(
                lambda m, channel_id=channel_id: m.model == "discuss.channel"
                and m.res_id == channel_id
            )
            store = Store(in_channel, fields=["body"])
            for message in in_channel:
                store.add(
                    message,
                    {"attachment_ids": Store.many(message.attachment_ids)},
                )
            channel._bus_send_store(store)

    @api.model
    def _linkup_erase_content(self, user):
        """Erase the content ``user`` wrote or received: the texts of their
        reflections, written and received, the content of their messages,
        their reactions, and the originals of their content the moderation
        hid. What a report still open points to stays until it is closed.
        Return whether something stayed, for a later run."""
        user = user.sudo()
        partner = user.partner_id
        Reflet = self.env["linkup.reflet"].sudo()
        reflets = Reflet.search(
            [
                "|",
                ("author_id", "=", user.id),
                ("recipient_id", "=", user.id),
                ("state", "not in", ("draft", "pending_invite")),
            ]
        )
        held_reflets = reflets._linkup_held_by_report()
        (reflets - held_reflets)._linkup_remove_content()
        Message = self.env["mail.message"].sudo()
        messages = Message.search([("author_id", "=", partner.id)])
        held_messages = self._linkup_held_messages(messages)
        self._linkup_erase_messages(messages - held_messages)
        self.env["mail.message.reaction"].sudo().search(
            [("partner_id", "=", partner.id)]
        ).unlink()
        Message.search([("starred_partner_ids", "in", partner.id)]).write(
            {"starred_partner_ids": [Command.unlink(partner.id)]}
        )
        originals = (
            self.env["linkup.hidden.content"]
            .sudo()
            .search(
                [
                    "|",
                    ("message_id", "in", messages.ids),
                    ("reflet_id", "in", reflets.ids),
                ]
            )
        )
        held_originals = originals.filtered(
            lambda hidden: hidden.report_id.state in QUEUE_STATES
        )
        done = originals - held_originals
        done.attachment_ids.unlink()
        done.unlink()
        return bool(held_reflets or held_messages or held_originals)

    @api.model
    def _linkup_erase_accounts(self, users):
        """Anonymize ``users`` and erase what they wrote (Q-23): the
        pseudonym becomes "Deleted member"; the address, the phone, the
        photo and the login leave; the account is archived and its
        sessions end. The points ledger stays, so that the energy of the
        links of the other members and the karma of everyone keep their
        sum (LU-NF-043); the consents stay as proof, without the hash of
        their address. An account already erased is left as it is."""
        users = (
            users.sudo()
            .with_context(active_test=False)
            .filtered(lambda user: not user.linkup_deleted_date)
        )
        for user in users:
            self._linkup_erase_account(user)

    @api.model
    def _linkup_erase_account(self, user):
        partner = user.partner_id
        email = partner.email_normalized
        held = self._linkup_erase_content(user)
        Reflet = self.env["linkup.reflet"].sudo()
        Invitation = self.env["linkup.invitation"].sudo()
        invitations = Invitation.search(
            [("inviter_id", "=", user.id)]
        ) | Invitation.search(
            [
                "|",
                "|",
                ("accepted_user_id", "=", user.id),
                ("invitee_id", "=", user.id),
                ("email", "=", email or "-"),
            ]
        )
        unsent = invitations.reflet_id.filtered(
            lambda reflet: reflet.author_id == user
            and reflet.state in ("pending_invite", "expired")
            and not reflet.recipient_id
        )
        invitations.unlink()
        (
            unsent
            | Reflet.search(
                [("author_id", "=", user.id), ("state", "=", "draft")]
            )
        ).unlink()
        Highlight = self.env["linkup.highlight"].sudo()
        Highlight.search([("sender_id", "=", user.id)])._linkup_put_out(
            "withdrawn"
        )
        Highlight.search([("recipient_id", "=", user.id)])._linkup_put_out(
            "manual"
        )
        self.env["linkup.consent"].sudo().search(
            [("user_id", "=", user.id)]
        ).write({"ip_hash": False})
        if email:
            # The emails written to the address rather than to the partner:
            # an invitation, a verification, a notice of the moderation.
            self.env["mail.mail"].sudo().search(
                [
                    "|",
                    ("email_to", "=ilike", email),
                    ("email_to", "ilike", f"<{email}>"),
                ]
            ).unlink()
        self._linkup_erase_traces(user)
        deleted_name = self._linkup_deleted_name()
        partner.with_context(tracking_disable=True, mail_notrack=True).write(
            {
                "name": deleted_name,
                **{
                    name: False
                    for name in PARTNER_ERASED_FIELDS
                    if name in partner._fields
                },
            }
        )
        user.with_context(tracking_disable=True, mail_notrack=True).write(
            {
                "login": f"{tools.LOGIN_PREFIX}deleted-{secrets.token_hex(8)}",
                "password": secrets.token_urlsafe(32),
                "signature": False,
                "active": False,
                "linkup_personal_code": False,
                "linkup_verify_token_hash": False,
                "linkup_verify_expiry": False,
                "linkup_age_bracket": False,
                "linkup_jurisdiction": False,
                "linkup_deleted_date": fields.Datetime.now(),
                "linkup_erase_pending": held,
            }
        )
        # The traces of the writes above, on the partner and the user.
        self._linkup_erase_traces(user)
        for reflet in Reflet.search(
            [("author_id", "=", user.id), ("message_id", "!=", False)]
        ):
            reflet._linkup_replace_carrier()
        self._linkup_rename_chats(partner)
        _logger.info("LinkUp: account %s erased", user.id)

    @api.model
    def _linkup_erase_traces(self, user):
        """Delete what Odoo keeps about an account besides its content: the
        history of its partner and user records (their tracking values hold
        the former address and name), its followers, the notifications and
        emails addressed to it, its logins, devices and API keys."""
        partner = user.partner_id
        Message = self.env["mail.message"].sudo()
        Message.search(
            [
                "|",
                "&",
                ("model", "=", "res.partner"),
                ("res_id", "=", partner.id),
                "&",
                ("model", "=", "res.users"),
                ("res_id", "=", user.id),
            ]
        ).unlink()
        self.env["mail.followers"].sudo().search(
            [("partner_id", "=", partner.id)]
        ).unlink()
        self.env["mail.notification"].sudo().search(
            [("res_partner_id", "=", partner.id)]
        ).unlink()
        self.env["mail.mail"].sudo().search(
            [("recipient_ids", "in", partner.id)]
        ).unlink()
        self.env["res.device.log"].sudo().search(
            [("user_id", "=", user.id)]
        ).unlink()
        self.env["res.users.log"].sudo().search(
            [("create_uid", "=", user.id)]
        ).unlink()
        self.env["res.users.apikeys"].sudo().search(
            [("user_id", "=", user.id)]
        ).unlink()
        if "auth_totp.device" in self.env:
            self.env["auth_totp.device"].sudo().search(
                [("user_id", "=", user.id)]
            ).unlink()

    @api.model
    def _linkup_rename_chats(self, partner):
        """Name again the direct conversations of ``partner``, whose stored
        name, and the record name of their messages, hold the former
        pseudonym."""
        channels = (
            self.env["discuss.channel"]
            .sudo()
            .search(
                [
                    ("channel_type", "=", "chat"),
                    ("channel_member_ids.partner_id", "=", partner.id),
                ]
            )
        )
        for channel in channels:
            name = ", ".join(
                channel.channel_member_ids.partner_id.mapped("name")
            )
            channel.name = name
            self.env["mail.message"].flush_model(["record_name"])
            self.env.cr.execute(
                SQL(
                    "UPDATE mail_message SET record_name = %s"
                    " WHERE model = 'discuss.channel' AND res_id = %s",
                    name,
                    channel.id,
                )
            )
        self.env["mail.message"].invalidate_model(["record_name"])

    # ------------------------------------------------------------------
    # Retention (LU-NF-015, Q-31)
    # ------------------------------------------------------------------

    @api.model
    def _cron_linkup_retention(self):
        """Apply every retention period: the deletions past their delay of
        grace, the accounts never verified, the drafts, the rejected and
        expired reflections, the pairs without activity, the closed
        reports with their audit log, and the content an open report held
        back at the erasure of an account."""
        self._linkup_purge_deletions()
        self._linkup_purge_unverified()
        self._linkup_purge_drafts()
        self._linkup_purge_closed_reflets()
        self._linkup_purge_inactive_pairs()
        self._linkup_purge_closed_reports()
        self._linkup_purge_held_content()
        return True

    @api.model
    def _linkup_purge_deletions(self):
        """Erase the accounts whose deletion was asked longer ago than the
        delay of grace."""
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        users = Users.search(
            [
                ("linkup_deletion_requested_date", "!=", False),
                (
                    "linkup_deletion_requested_date",
                    "<=",
                    self._linkup_cutoff("deletion_grace"),
                ),
                ("linkup_deleted_date", "=", False),
            ]
        )
        self._linkup_erase_accounts(users)
        return users

    @api.model
    def _linkup_purge_unverified(self):
        """Erase the accounts of the public signup never verified within
        the period: an account verified once, whose new address waits for
        its link, stays."""
        users = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("linkup_consent_required", "=", True),
                    ("linkup_email_verified", "=", False),
                    ("linkup_verified_date", "=", False),
                    ("linkup_deleted_date", "=", False),
                    ("create_date", "<", self._linkup_cutoff("unverified")),
                ]
            )
        )
        self._linkup_erase_accounts(users)
        return users

    @api.model
    def _linkup_purge_drafts(self):
        """Delete the drafts left unchanged for the period."""
        drafts = (
            self.env["linkup.reflet"]
            .sudo()
            .search(
                [
                    ("state", "=", "draft"),
                    ("write_date", "<", self._linkup_cutoff("draft")),
                ]
            )
        )
        drafts.unlink()
        return drafts

    @api.model
    def _linkup_purge_closed_reflets(self):
        """Erase the texts of the rejected and expired reflections closed
        for the period; their metadata stays."""
        cutoff = self._linkup_cutoff("closed_reflet")
        reflets = (
            self.env["linkup.reflet"]
            .sudo()
            .search(
                [
                    ("state", "in", CLOSED_REFLET_STATES),
                    ("linkup_content_removed", "=", False),
                    "|",
                    ("answered_date", "<", cutoff),
                    "&",
                    ("answered_date", "=", False),
                    ("sent_date", "<", cutoff),
                ]
            )
        )
        reflets -= reflets._linkup_held_by_report()
        reflets._linkup_remove_content()
        return reflets

    @api.model
    def _linkup_purge_inactive_pairs(self):
        """Erase the reflections and the messages of the pairs without any
        activity for the period: neither a reflection, a call nor a
        message in their direct conversation."""
        cutoff = self._linkup_cutoff("inactive_pair")
        links = (
            self.env["linkup.link"]
            .sudo()
            .search(
                [
                    "|",
                    ("last_interaction_date", "<", cutoff),
                    "&",
                    ("last_interaction_date", "=", False),
                    ("create_date", "<", cutoff),
                ]
            )
        )
        Message = self.env["mail.message"].sudo()
        inactive = self.env["linkup.link"]
        for link in links:
            channel = link.channel_id
            if channel and Message.search_count(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", channel.id),
                    ("date", ">=", cutoff),
                ],
                limit=1,
            ):
                continue
            inactive |= link
        reflets = (
            self.env["linkup.reflet"]
            .sudo()
            .search(
                [
                    ("link_id", "in", inactive.ids),
                    ("state", "not in", ("draft", "pending_invite")),
                    ("linkup_content_removed", "=", False),
                ]
            )
        )
        (reflets - reflets._linkup_held_by_report())._linkup_remove_content()
        chats = inactive.channel_id.filtered(
            lambda channel: channel.channel_type == "chat"
        )
        messages = Message.search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "in", chats.ids),
                ("date", "<", cutoff),
            ]
        )
        self._linkup_erase_messages(
            messages - self._linkup_held_messages(messages)
        )
        return inactive

    @api.model
    def _linkup_purge_closed_reports(self):
        """Delete the reports closed for the period, with the originals of
        the content they hid, their audit log and their notices."""
        cutoff = self._linkup_cutoff("closed_report")
        Report = self.env["linkup.report"].sudo()
        reports = Report.search(
            [
                ("state", "in", CLOSED_STATES),
                "|",
                ("decision_date", "<", cutoff),
                "&",
                ("decision_date", "=", False),
                ("write_date", "<", cutoff),
            ]
        )
        if not reports:
            return reports
        originals = (
            self.env["linkup.hidden.content"]
            .sudo()
            .search([("report_id", "in", reports.ids)])
        )
        originals.attachment_ids.unlink()
        originals.unlink()
        self.env["linkup.audit.log"].sudo().with_context(
            linkup_audit_purge=True
        ).search([("report_id", "in", reports.ids)]).unlink()
        reports.unlink()
        return reports

    @api.model
    def _linkup_purge_held_content(self):
        """Erase what the reports open at the erasure of an account held
        back, once they are closed."""
        users = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search([("linkup_erase_pending", "=", True)])
        )
        for user in users:
            user.linkup_erase_pending = self._linkup_erase_content(user)
        return users
