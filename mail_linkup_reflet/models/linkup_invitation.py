# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import hashlib
import secrets
from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import email_normalize

from ..exceptions import LinkupError
from .res_users import MEMBER_GROUP

DEFAULT_EXPIRY_DAYS = 14
DEFAULT_MAX_PER_DAY = 10
# Days an invitation is kept after its expiry, with an undelivered
# reflection (LU-NF-015).
PURGE_DELAY_DAYS = 1
# Bytes of randomness of a token; its URL-safe text is about 43 characters.
TOKEN_BYTES = 32
TEMPLATE_XMLID = "mail_linkup_reflet.mail_template_linkup_invitation"


def token_hash(token):
    """The stored form of a token: its SHA-256, in hexadecimal.

    A token is 256 random bits, so a plain hash is enough to keep the
    database from holding a usable link.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def mask_email(email):
    """The address as the inviter sees it after sending: the first letter
    of the local part, then ``***@`` and the domain."""
    local, _sep, domain = (email or "").partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


class LinkupInvitation(models.Model):
    """A NewLink invitation: a reflection sent by email to a person who is
    not a member yet (LU-F-020).

    ``linkup.reflet.action_send`` creates it from the draft of the member,
    which waits in the ``pending_invite`` state. The email holds a link
    ``/linkup/invite/<token>``; the token is random, stored as a hash only,
    and serves once: the signup through that link consumes it, and attaches
    the reflection to the new member when their address is the invited one.
    A member already signed up with that address attaches it by opening the
    link while logged in.

    The inviter sees the same answer whatever the address: unknown, of a
    member, refusing the invitations, or of a member a block separates from
    them. Only the email differs, sent in the first two cases and not in the
    last two, and nothing the inviter reads tells which.

    The inviter cancels an invitation not used yet, which gives the
    reflection back as their draft, or sends its link again with a new
    token; both count against ``linkup.max_invitations_per_day`` sendings
    a day. An invitation lasts ``linkup.invitation_expiry_days`` days. A
    daily cron expires it with its reflection, and deletes it one day after
    its expiry, with its reflection when nobody received it.

    Members read their own invitations and write none: every change goes
    through a method of this model that checks the inviter, then writes
    under ``sudo``. The token hash and the sending counter are kept to the
    system administrators, and the account that used an invitation to the
    LinkUp administrators.
    """

    _name = "linkup.invitation"
    _description = "LinkUp invitation"
    _order = "id desc"

    inviter_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        default=lambda self: self.env.user,
        ondelete="cascade",
        readonly=True,
    )
    reflet_id = fields.Many2one(
        "linkup.reflet",
        string="Reflection",
        index="btree_not_null",
        ondelete="set null",
        readonly=True,
    )
    name = fields.Char(
        string="Name to remember them",
        readonly=True,
        help="Seen by the inviter only; never sent to anybody.",
    )
    email = fields.Char(required=True, readonly=True)
    lang = fields.Char(string="Language", readonly=True)
    token_hash = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        groups="base.group_system",
    )
    state = fields.Selection(
        [
            ("sent", "Sent"),
            ("accepted", "Used"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="sent",
        index=True,
        readonly=True,
    )
    expiry_date = fields.Datetime(required=True, index=True, readonly=True)
    # The account that signed up through the link may not be the invited
    # person: the inviter never learns who it is.
    accepted_user_id = fields.Many2one(
        "res.users",
        string="Used by",
        ondelete="set null",
        readonly=True,
        groups="mail_linkup_reflet.group_linkup_admin",
    )
    accepted_date = fields.Datetime(string="Used on", readonly=True)
    # Sendings of the day ``send_day`` (creation and new sendings), for the
    # daily limit of the inviter.
    send_day = fields.Date(readonly=True, groups="base.group_system")
    send_day_count = fields.Integer(readonly=True, groups="base.group_system")

    _sql_constraints = [
        (
            "token_hash_unique",
            "UNIQUE(token_hash)",
            "An invitation token is unique.",
        ),
    ]

    @api.depends("email")
    def _compute_display_name(self):
        """Name an invitation by its masked address, as the inviter sees it
        after sending, never by the name the inviter gave."""
        for invitation in self:
            invitation.display_name = mask_email(invitation.sudo().email)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _linkup_param(self, key, default):
        return self.env["linkup.reflet"]._linkup_param(key, default)

    @api.model
    def _linkup_new_token(self):
        """A new token and its hash."""
        token = secrets.token_urlsafe(TOKEN_BYTES)
        return token, token_hash(token)

    @api.model
    def _linkup_find(self, token):
        """The invitation of a token as a ``sudo`` record, or an empty one."""
        if not isinstance(token, str) or not 20 <= len(token) <= 100:
            return self.sudo().browse()
        return self.sudo().search(
            [("token_hash", "=", token_hash(token))], limit=1
        )

    def _linkup_lock(self):
        """Lock the row of the invitation for the rest of the transaction;
        a concurrent action fails at once, and the RPC layer retries it."""
        self.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM linkup_invitation WHERE id IN %s"
            " FOR UPDATE NOWAIT",
            [tuple(self.ids)],
        )
        self.invalidate_recordset()

    def _linkup_token_code(self):
        """``False`` while the link of the invitation is usable, otherwise
        the code of the refusal: ``linkup.invite_used``,
        ``linkup.invite_cancelled`` or ``linkup.invite_expired``. An
        invitation past its date is expired before the cron writes it."""
        self.ensure_one()
        invitation = self.sudo()
        if invitation.state == "accepted":
            return "linkup.invite_used"
        if invitation.state == "cancelled":
            return "linkup.invite_cancelled"
        if (
            invitation.state == "expired"
            or invitation.expiry_date <= fields.Datetime.now()
        ):
            return "linkup.invite_expired"
        return False

    @api.model
    def _linkup_code_message(self, code):
        """The sentence of a refusal of an invitation link."""
        return {
            "linkup.invite_used": _("This invitation has already been used."),
            "linkup.invite_cancelled": _(
                "This invitation was cancelled by the person who sent it."
            ),
            "linkup.invite_expired": _("This invitation has expired."),
        }.get(code, _("This invitation link is not valid."))

    def _linkup_check_usable(self):
        code = self._linkup_token_code()
        if code:
            raise LinkupError(code, self._linkup_code_message(code))

    def _linkup_begin(self):
        """Start an action of the inviter: check the current user, lock the
        row. Return the invitation under ``sudo``."""
        self.ensure_one()
        invitation = self.sudo()
        if invitation.inviter_id != self.env.user:
            raise AccessError(
                _("This action belongs to the person who sent the invitation.")
            )
        invitation._linkup_lock()
        return invitation

    # ------------------------------------------------------------------
    # Daily limit
    # ------------------------------------------------------------------

    @api.model
    def _linkup_today(self, user):
        """The current day in the time zone of ``user``."""
        return fields.Date.context_today(self.with_user(user))

    @api.model
    def _linkup_used_today(self, user):
        """The sendings of invitations ``user`` made today."""
        groups = self.sudo()._read_group(
            [
                ("inviter_id", "=", user.id),
                ("send_day", "=", self._linkup_today(user)),
            ],
            aggregates=["send_day_count:sum"],
        )
        return groups[0][0] or 0

    @api.model
    def _linkup_max_per_day(self):
        return self._linkup_param(
            "linkup.max_invitations_per_day", DEFAULT_MAX_PER_DAY
        )

    @api.model
    def _linkup_take_quota(self, user):
        """Refuse a sending beyond the daily limit of ``user``.

        The row of the user serializes two sendings at once: the second
        fails on the lock, and its retry counts the first.
        """
        self.flush_model(["inviter_id", "send_day", "send_day_count"])
        self.env.cr.execute(
            "SELECT id FROM res_users WHERE id = %s FOR NO KEY UPDATE NOWAIT",
            [user.id],
        )
        if self._linkup_used_today(user) >= self._linkup_max_per_day():
            raise LinkupError(
                "linkup.rate_limited",
                _("Too many invitations today, try again tomorrow."),
            )

    def _linkup_count_sending(self):
        """Count one sending of the invitation, today."""
        self.ensure_one()
        invitation = self.sudo()
        today = self._linkup_today(invitation.inviter_id)
        count = (
            invitation.send_day_count + 1
            if invitation.send_day == today
            else 1
        )
        invitation.write({"send_day": today, "send_day_count": count})

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    def _linkup_deliverable(self):
        """Whether the email of the invitation goes out.

        It does not for an address of the blocklist, nor for the address
        of a user a block separates from the inviter, in either direction
        (LU-F-020 RM6, RM7). The inviter is never told.
        """
        self.ensure_one()
        invitation = self.sudo()
        if self.env["linkup.email.blocklist"]._linkup_is_listed(
            invitation.email
        ):
            return False
        users = (
            self.env["res.users"]
            .sudo()
            .search([("partner_id.email_normalized", "=", invitation.email)])
        )
        separated = self.env["linkup.block"]._linkup_blocked_users(
            invitation.inviter_id
        )
        return not (users & separated)

    def _linkup_urls(self, token):
        """The links of the email: the invitation, the refusal of every
        invitation, the page in the other language, and the privacy policy
        when ``linkup.privacy_policy_url`` is set."""
        self.ensure_one()
        url = f"{self.get_base_url()}/linkup/invite/{token}"
        other_lang = (
            "en_US" if (self.sudo().lang or "").startswith("fr") else "fr_CA"
        )
        return {
            "linkup_invite_url": url,
            "linkup_optout_url": f"{url}/optout",
            "linkup_other_lang_url": f"{url}?lang={other_lang}",
            "linkup_privacy_url": self.env["ir.config_parameter"]
            .sudo()
            .get_param("linkup.privacy_policy_url", ""),
            "linkup_expiry_days": self._linkup_param(
                "linkup.invitation_expiry_days", DEFAULT_EXPIRY_DAYS
            ),
        }

    def _linkup_send_mail(self, token, deliver=True):
        """Queue the email of the invitation, with the link of ``token``.

        The email is rendered in the language of the inviter. It is attached
        to no record and created by the superuser: ``mail.message`` lets the
        creator of a message read it, and its body holds the link, so the
        inviter would otherwise read by id whether an email went out, and
        its token. Its content is generic and never holds the texts of the
        reflection.

        Without ``deliver``, the email is rendered the same way and dropped:
        an address that receives none costs the server the same work, and
        the time of the answer does not tell the inviter which.
        """
        self.ensure_one()
        template = self.env.ref(TEMPLATE_XMLID, raise_if_not_found=False)
        if not template:
            return
        template = template.with_user(SUPERUSER_ID).with_context(
            **self._linkup_urls(token)
        )
        if not deliver:
            template._generate_template(
                self.ids, ("body_html", "email_from", "email_to", "subject")
            )
            return
        template.send_mail(
            self.id,
            email_values={
                "model": False,
                "res_id": False,
                "author_id": False,
            },
        )

    # ------------------------------------------------------------------
    # Creation, cancellation, new sending (inviter)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_create_for(self, reflet, invite):
        """Create the invitation of a draft being sent, and send its email.

        ``reflet`` is the locked draft under ``sudo``, its texts checked;
        ``invite`` is ``{"email": …, "name": …}`` as a client sends it. The
        invitation by phone belongs to a later lot. Return what
        ``_linkup_info`` gives, the same whatever the address.
        """
        invite = invite if isinstance(invite, dict) else {}
        me = self.env.user
        if invite.get("phone"):
            raise LinkupError(
                "linkup.validation",
                _("The invitation by phone is not available yet."),
                field="phone",
            )
        email = email_normalize(invite.get("email") or "")
        if not email:
            raise LinkupError(
                "linkup.validation",
                _("Enter a valid email address."),
                field="email",
            )
        if email == email_normalize(me.email or ""):
            raise LinkupError(
                "linkup.validation",
                _("This is your own address."),
                field="email",
            )
        name = invite.get("name")
        name = name.strip()[:100] if isinstance(name, str) else ""
        self._linkup_take_quota(me)
        token, hashed = self._linkup_new_token()
        days = self._linkup_param(
            "linkup.invitation_expiry_days", DEFAULT_EXPIRY_DAYS
        )
        invitation = self.sudo().create(
            {
                "inviter_id": me.id,
                "reflet_id": reflet.id,
                "name": name or False,
                "email": email,
                "lang": me.lang or self.env.lang,
                "token_hash": hashed,
                "expiry_date": fields.Datetime.now() + timedelta(days=days),
            }
        )
        invitation._linkup_count_sending()
        invitation._linkup_send_mail(
            token, deliver=invitation._linkup_deliverable()
        )
        return invitation

    def action_cancel(self):
        """Cancel an invitation not used yet (LU-F-026 RM2).

        Its link stops working and its reflection becomes the draft of the
        inviter again; the inviter who already holds a draft sends or
        deletes it first. Return the id of the draft, or ``False``.
        """
        invitation = self._linkup_begin()
        invitation._linkup_check_usable()
        reflet = invitation.reflet_id
        if reflet:
            self.env.cr.execute(
                "SELECT id FROM res_users WHERE id = %s"
                " FOR NO KEY UPDATE NOWAIT",
                [self.env.uid],
            )
            Reflet = self.env["linkup.reflet"].sudo()
            if Reflet.search_count(
                [("author_id", "=", self.env.uid), ("state", "=", "draft")]
            ):
                raise LinkupError(
                    "linkup.validation",
                    _(
                        "Send or delete your current draft before cancelling"
                        " this invitation."
                    ),
                    field="draft",
                )
            reflet._linkup_lock()
            if reflet.state == "pending_invite":
                reflet.write({"state": "draft", "invitation_id": False})
            else:
                reflet = Reflet
        invitation.write({"state": "cancelled", "reflet_id": False})
        return reflet.id or False

    def action_resend(self):
        """Send the link of an invitation not used yet again, with a new
        token: the former link stops working. It counts as a sending of
        the day; the expiry date does not move. A suspended member sends
        none. Return ``_linkup_info``."""
        invitation = self._linkup_begin()
        self.env.user._linkup_check_not_suspended()
        invitation._linkup_check_usable()
        self._linkup_take_quota(self.env.user)
        token, hashed = self._linkup_new_token()
        invitation.write({"token_hash": hashed})
        invitation._linkup_count_sending()
        invitation._linkup_send_mail(
            token, deliver=invitation._linkup_deliverable()
        )
        return invitation._linkup_info()

    # ------------------------------------------------------------------
    # Web client
    # ------------------------------------------------------------------

    def _linkup_info(self):
        """What the inviter sees of an invitation: its masked address, the
        name they gave, its state and expiry, and its reflection."""
        self.ensure_one()
        invitation = self.sudo()
        reflet = invitation.reflet_id
        state = invitation.state
        if state == "sent" and invitation._linkup_token_code():
            state = "expired"
        return {
            "id": invitation.id,
            "email": mask_email(invitation.email),
            "name": invitation.name or "",
            "state": state,
            "expiry_date": invitation.expiry_date,
            "reflet": reflet
            and {
                "id": reflet.id,
                "state": reflet.state,
                "category_code": reflet.category_id.code or False,
                "you_said": reflet.you_said or "",
                "understood": reflet.understood or "",
            },
        }

    @api.model
    def linkup_invitations_info(self):
        """The invitations of the current member still waiting, the most
        recent first, and the sendings of the day against the limit."""
        self.env["linkup.reflet"]._linkup_check_member()
        me = self.env.user
        invitations = self.search(
            [
                ("inviter_id", "=", me.id),
                ("state", "=", "sent"),
                ("expiry_date", ">", fields.Datetime.now()),
            ]
        )
        return {
            "invitations": [inv._linkup_info() for inv in invitations],
            "quota": {
                "used": self._linkup_used_today(me),
                "max": self._linkup_max_per_day(),
            },
            "expiry_days": self._linkup_param(
                "linkup.invitation_expiry_days", DEFAULT_EXPIRY_DAYS
            ),
        }

    # ------------------------------------------------------------------
    # Use of the link (invited person)
    # ------------------------------------------------------------------

    def _linkup_matches(self, user):
        """Whether ``user`` holds the invited address."""
        self.ensure_one()
        return email_normalize(user.sudo().email or "") == self.sudo().email

    def _linkup_consume(self, user):
        """Use the invitation for ``user``, who just signed up through its
        link or opened it while logged in; the caller holds its lock.

        The token serves once. The reflection reaches ``user`` when their
        address is the invited one; otherwise, as for a forwarded link, it
        reaches nobody and expires. Return whether it was delivered.
        """
        self.ensure_one()
        invitation = self.sudo()
        invitation._linkup_check_usable()
        invitation.write(
            {
                "state": "accepted",
                "accepted_user_id": user.id,
                "accepted_date": fields.Datetime.now(),
            }
        )
        reflet = invitation.reflet_id
        if not reflet:
            return False
        if invitation._linkup_matches(user):
            return reflet._linkup_deliver_invited(user)
        reflet._linkup_lock()
        if reflet.state == "pending_invite":
            reflet.write({"state": "expired"})
        return False

    def _linkup_open_for(self, user):
        """A logged-in member opens the link: the invitation is used for
        them when they hold the invited address, and refused otherwise
        without being used, so that the invited person keeps it."""
        self.ensure_one()
        invitation = self.sudo()
        invitation._linkup_lock()
        invitation._linkup_check_usable()
        if not (
            invitation._linkup_matches(user)
            and user.sudo()._linkup_has_group_id(MEMBER_GROUP)
        ):
            raise LinkupError(
                "linkup.unavailable",
                _("This invitation was sent to another address."),
            )
        return invitation._linkup_consume(user)

    def _linkup_optout(self):
        """Refuse every future invitation to the address of this one."""
        self.ensure_one()
        return self.env["linkup.email.blocklist"]._linkup_add(
            self.sudo().email, "invite_optout"
        )

    # ------------------------------------------------------------------
    # Expiry and purge (LU-NF-015)
    # ------------------------------------------------------------------

    @api.model
    def _cron_linkup_invitations(self):
        """Expire the invitations past their date, then purge.

        An expired invitation takes its ``pending_invite`` reflection with
        it. One day after its expiry, every invitation is deleted, with its
        reflection when nobody received it; a delivered reflection stays,
        without its invitation. The reflection that a link used with
        another address let expire goes one day after that use, while its
        invitation stays to tell that its link served. The rows held by an
        action in progress are skipped and handled at the next run. The
        expired entries of the blocklist are deleted too.
        """
        now = fields.Datetime.now()
        cutoff = now - timedelta(days=PURGE_DELAY_DAYS)
        self.flush_model(
            ["state", "expiry_date", "reflet_id", "accepted_date"]
        )
        self.env.cr.execute(
            """
            SELECT id FROM linkup_invitation
            WHERE state = 'sent' AND expiry_date <= %s
            FOR UPDATE SKIP LOCKED
            """,
            [now],
        )
        expired = self.sudo().browse(
            [row[0] for row in self.env.cr.fetchall()]
        )
        expired.invalidate_recordset()
        expired.reflet_id.filtered(
            lambda reflet: reflet.state == "pending_invite"
        ).write({"state": "expired"})
        expired.write({"state": "expired"})
        self.env.cr.execute(
            """
            SELECT id, expiry_date <= %s FROM linkup_invitation
            WHERE expiry_date <= %s
               OR (state = 'accepted' AND accepted_date <= %s)
            FOR UPDATE SKIP LOCKED
            """,
            [cutoff, cutoff, cutoff],
        )
        rows = self.env.cr.fetchall()
        old = self.sudo().browse([row[0] for row in rows])
        old.invalidate_recordset()
        old.reflet_id.filtered(
            lambda reflet: not reflet.recipient_id
            and reflet.state in ("pending_invite", "expired")
        ).unlink()
        old.browse([row[0] for row in rows if row[1]]).unlink()
        self.env["linkup.email.blocklist"]._linkup_purge()
        return True
