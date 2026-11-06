# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import base64
import binascii
import hashlib
import ipaddress
import logging
import secrets
from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.addons.auth_signup.models.res_partner import SignupError
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.addons.mail_linkup_reflet.models.linkup_invitation import (
    mask_email,
)
from odoo.addons.mail_linkup_reflet.models.res_users import (
    ADMIN_GROUP,
    MEMBER_GROUP,
)
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import SQL, email_normalize, email_split
from odoo.tools.image import base64_to_image

from .. import tools
from . import privacy
from .linkup_consent import MIRROR_FIELDS

_logger = logging.getLogger(__name__)

# Preferences a member reads and writes on their own account (LU-F-082 RM4).
COMMUNITY_PREFERENCES = ("linkup_first_reflet_scope",)
VERIFY_TEMPLATE_XMLID = (
    "mail_linkup_community.mail_template_linkup_verify_email"
)
EXISTING_TEMPLATE_XMLID = (
    "mail_linkup_community.mail_template_linkup_signup_existing"
)
# Hours a verification link lasts (LU-F-110 RM3).
VERIFY_HOURS = 24
# Parameters of the community, with their defaults.
VERIFICATION_PARAM = "linkup.email_verification"
RESEND_MINUTES_PARAM = "linkup.verification_resend_minutes"
DEFAULT_RESEND_MINUTES = 10
SIGNUP_RATE_PARAM = "linkup.signup_rate_per_ip_hour"
DEFAULT_SIGNUP_RATE = 3
DISPOSABLE_PARAM = "linkup.disposable_email_domains"
CONSENT_ALL_PARAM = "linkup.consent_all_members"
TERMS_URL_PARAM = "linkup.terms_url"
HELP_RESOURCES_PARAM = "linkup.help_resources"
MODERATION_HOURS_PARAM = "linkup.moderation_hours"
MODERATOR_GROUP = "mail_linkup_reflet.group_linkup_moderator"
# Groups an account of the public signup never holds, whatever the template
# it copies (LU-F-110 CA1): the administration of LinkUp and of Odoo, the
# moderation, the contacts and the technical features.
SIGNUP_FORBIDDEN_GROUPS = (
    ADMIN_GROUP,
    MODERATOR_GROUP,
    "base.group_system",
    "base.group_erp_manager",
    "base.group_partner_manager",
    "base.group_no_one",
)
# Bits of an IPv6 address the limits count as one address: a /64 network
# is what a single subscriber usually holds.
IPV6_PREFIX = 64
PSEUDONYM_MAX_LENGTH = 64
PHONE_MAX_LENGTH = 30
PHOTO_MAX_BYTES = 5 * 1024 * 1024
# Languages a member chooses in their profile (LU-NF-025).
PROFILE_LANGS = ("fr_CA", "en_US")
# Optional consents of the signup form, by purpose.
SIGNUP_OPTIONAL_CONSENTS = {
    "link_visibility": "linkup_link_visibility",
    "energy_visibility": "linkup_energy_visibility",
    "notifications": "linkup_notifications",
}
SIGNUP_REQUIRED_CONSENTS = {
    "terms": "linkup_terms",
    "privacy": "linkup_privacy",
    "sensitive_data": "linkup_sensitive_data",
}


def checked(value):
    """Whether a checkbox of a form was checked."""
    return value not in (None, False, "", "0", "false", "False", "off")


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class ResUsers(models.Model):
    _inherit = "res.users"

    # Written by the server only; read by the member through their profile.
    linkup_email_verified = fields.Boolean(
        string="Email verified",
        default=True,
        copy=False,
        groups=ADMIN_GROUP,
        help="An account of the public signup sends, invites and earns"
        " nothing before the click on the link of its verification email."
        " An account created by an administrator, or through an invitation"
        " sent to its address, is verified.",
    )
    linkup_consent_required = fields.Boolean(
        string="Consents required",
        default=False,
        copy=False,
        groups=ADMIN_GROUP,
        help="The account sends nothing without its consents to the terms"
        " of use, the privacy policy and the processing of sensitive"
        " information. Set by the signup; the setting 'Consents of every"
        " member' extends it to all.",
    )
    linkup_age_attested = fields.Boolean(
        string="Adult attested",
        copy=False,
        groups=ADMIN_GROUP,
        help="The person declared being 18 or older at signup.",
    )
    linkup_age_bracket = fields.Selection(
        tools.AGE_BRACKETS,
        string="Age range",
        copy=False,
        groups=ADMIN_GROUP,
    )
    linkup_jurisdiction = fields.Selection(
        tools.JURISDICTIONS,
        string="Declared residence",
        copy=False,
        groups=ADMIN_GROUP,
    )
    # A preference of the member (SELF_READABLE_FIELDS and
    # SELF_WRITEABLE_FIELDS); kept from the others.
    linkup_first_reflet_scope = fields.Selection(
        tools.FIRST_REFLET_SCOPES,
        string="Who may send me a first reflection",
        default="code",
        required=True,
        copy=False,
        groups=ADMIN_GROUP,
    )
    linkup_personal_code = fields.Char(
        string="Personal code",
        copy=False,
        index="btree_not_null",
        groups="base.group_system",
    )
    linkup_verify_token_hash = fields.Char(
        copy=False, groups="base.group_system"
    )
    linkup_verify_expiry = fields.Datetime(
        copy=False, groups="base.group_system"
    )
    # Personal data (LU-F-117): written by the server only.
    linkup_verified_date = fields.Datetime(
        string="Address first verified on",
        copy=False,
        readonly=True,
        groups=ADMIN_GROUP,
        help="An account of the public signup never verified is erased once"
        " the retention period of the unverified accounts is over.",
    )
    linkup_deletion_requested_date = fields.Datetime(
        string="Deletion requested on",
        copy=False,
        readonly=True,
        groups=ADMIN_GROUP,
        help="The account is erased once the delay of grace is over; until"
        " then, the member cancels the request from their profile.",
    )
    linkup_deleted_date = fields.Datetime(
        string="Erased on",
        copy=False,
        readonly=True,
        index="btree_not_null",
        groups=ADMIN_GROUP,
    )
    linkup_erase_pending = fields.Boolean(
        string="Content held by a report",
        copy=False,
        readonly=True,
        groups=ADMIN_GROUP,
        help="Content of this erased account that an open report points to;"
        " the retention cron erases it once the report is closed.",
    )

    _sql_constraints = [
        (
            "linkup_personal_code_unique",
            "UNIQUE(linkup_personal_code)",
            "A personal code is unique.",
        ),
    ]

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + list(COMMUNITY_PREFERENCES)

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + list(COMMUNITY_PREFERENCES)

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    @api.model
    def _linkup_param_text(self, key, default=""):
        return (
            self.env["ir.config_parameter"].sudo().get_param(key, default)
            or default
        )

    @api.model
    def _linkup_verification_enabled(self):
        """Whether a public signup verifies its address; "False" turns it
        off, any other value keeps it on."""
        return self._linkup_param_text(VERIFICATION_PARAM, "True") != "False"

    @api.model
    def _linkup_disposable_domains(self):
        """The domains of disposable addresses the signup refuses, from
        ``linkup.disposable_email_domains``: one per line or separated by
        commas."""
        text = self._linkup_param_text(DISPOSABLE_PARAM)
        return {
            domain.strip().lower().lstrip("@")
            for domain in text.replace(",", "\n").splitlines()
            if domain.strip()
        }

    @api.model
    def _linkup_is_disposable(self, email):
        """Whether ``email`` belongs to a listed domain or to one of its
        subdomains."""
        domain = (email or "").rpartition("@")[2].lower()
        if not domain:
            return False
        listed = self._linkup_disposable_domains()
        parts = domain.split(".")
        return any(
            ".".join(parts[index:]) in listed for index in range(len(parts))
        )

    # ------------------------------------------------------------------
    # Rights of a member of the community
    # ------------------------------------------------------------------

    def _linkup_consents_required(self):
        """Whether the account needs its consents to send: an account of
        the signup, or every restricted member when
        ``linkup.consent_all_members`` is "True"."""
        self.ensure_one()
        if not self._linkup_is_restricted_member():
            return False
        return (
            self.sudo().linkup_consent_required
            or self._linkup_param_text(CONSENT_ALL_PARAM) == "True"
        )

    def _linkup_is_verified(self):
        self.ensure_one()
        return bool(self.sudo().linkup_email_verified)

    def _linkup_check_can_exchange(self):
        """Refuse every exchange to a restricted member whose address is not
        verified (``linkup.not_verified``), or who lacks a required consent
        (``linkup.consent_required``, LU-F-111 CA2): no reflection, no
        answer, no highlight, no invitation."""
        self.ensure_one()
        if not self._linkup_is_restricted_member():
            return
        if not self._linkup_is_verified():
            raise LinkupError(
                "linkup.not_verified",
                _("Confirm your email address first."),
            )
        if self.env["linkup.consent"]._linkup_missing(self):
            raise LinkupError(
                "linkup.consent_required",
                _("Accept the conditions of LinkUp first."),
            )

    def _linkup_accepts_invitation(self, inviter, via):
        """Apply the preference of the member (LU-F-016 RM7): nobody, a
        code only, or an address or a code. An account not verified yet
        receives nothing."""
        if not super()._linkup_accepts_invitation(inviter, via):
            return False
        user = self.sudo()
        if not user._linkup_is_verified():
            return False
        scope = user.linkup_first_reflet_scope or "code"
        if scope == "nobody":
            return False
        if scope == "code":
            return via == "code"
        return True

    # ------------------------------------------------------------------
    # Login: a technical identifier, the address to log in (LU-F-113 RM2)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_signup_login(self, email):
        return tools.new_login()

    @api.model
    def _get_login_domain(self, login):
        """Log a member in by their address as well: their login is a
        technical identifier they never see."""
        domain = super()._get_login_domain(login)
        email = email_normalize(login or "")
        if not email:
            return domain
        return [
            "|",
            *domain,
            "&",
            ("login", "=like", tools.LOGIN_PREFIX + "%"),
            ("partner_id.email_normalized", "=", email),
        ]

    @api.model
    def _linkup_email_taken(self, email):
        """Whether an account already uses ``email``, as its login or its
        address."""
        email = email_normalize(email or "")
        return bool(email) and bool(
            self.sudo()
            .with_context(active_test=False)
            .search_count(
                [
                    "|",
                    ("login", "=ilike", email),
                    ("partner_id.email_normalized", "=", email),
                ],
                limit=1,
            )
        )

    # ------------------------------------------------------------------
    # Signup (LU-F-110, LU-F-111)
    # ------------------------------------------------------------------

    @api.model
    def _linkup_pop_signup_values(self, values):
        """Take the fields of the community out of ``values``, which then
        holds only fields of ``res.users``."""
        return {
            key: values.pop(key)
            for key in list(values)
            if key in tools.SIGNUP_FIELDS
        }

    @api.model
    def _linkup_check_signup(
        self, values, form, check_domain=True, check_address=True
    ):
        """Check a signup on the server, whatever the client sent: the
        trap left empty, a pseudonym, a valid address not disposable, the
        required consents, the attestation of age with its range, the
        residence in Canada, and, unless ``check_address`` is off, an
        address neither used nor banned (LU-F-116 RM6). Return the
        normalized address.
        """
        if form.get("linkup_website"):
            raise UserError(_("Could not create a new account."))
        name = (values.get("name") or "").strip()
        if not name or len(name) > PSEUDONYM_MAX_LENGTH:
            raise LinkupError(
                "linkup.validation",
                _(
                    "Choose a pseudonym of at most %(count)s characters.",
                    count=PSEUDONYM_MAX_LENGTH,
                ),
                field="name",
            )
        values["name"] = name
        email = email_normalize(values.get("email") or values.get("login"))
        if not email:
            raise LinkupError(
                "linkup.validation",
                _("Enter a valid email address."),
                field="email",
            )
        if check_domain and self._linkup_is_disposable(email):
            raise LinkupError(
                "linkup.validation",
                _("Addresses of this domain are not accepted; use another."),
                field="email",
            )
        missing = [
            purpose
            for purpose, key in SIGNUP_REQUIRED_CONSENTS.items()
            if not checked(form.get(key))
        ]
        if missing:
            raise LinkupError(
                "linkup.consent_required",
                _(
                    "Accept the terms of use, the privacy policy and the"
                    " processing of sensitive information to sign up."
                ),
            )
        brackets = {code for code, _label in tools.AGE_BRACKETS}
        if (
            not checked(form.get("linkup_adult"))
            or form.get("linkup_age_bracket") not in brackets
        ):
            raise LinkupError(
                "linkup.validation",
                _("LinkUp is open to people aged 18 and over."),
                field="age",
            )
        if not checked(form.get("linkup_resides_canada")):
            raise LinkupError(
                "linkup.validation",
                _("LinkUp is open to people living in Canada for now."),
                field="jurisdiction",
            )
        if check_address:
            closed = self._linkup_address_closed(email)
            if closed == "taken":
                raise UserError(
                    _(
                        "Another user is already registered using this email"
                        " address."
                    )
                )
            if closed == "banned":
                raise LinkupError(
                    "linkup.validation",
                    _("This address cannot open an account."),
                    field="email",
                )
        return email

    @api.model
    def _linkup_address_closed(self, email):
        """Why ``email`` opens no account: ``banned`` when the moderation
        closed an account of it (LU-F-116 RM6), ``taken`` when an account
        already uses it, ``False`` when it is free."""
        if self.env["linkup.email.blocklist"]._linkup_is_listed(
            email, "banned"
        ):
            return "banned"
        if self._linkup_email_taken(email):
            return "taken"
        return False

    def _linkup_after_signup(self, form, verified):
        """Write what the signup declared on the new account: its consents,
        each one recorded apart, its age range and residence, the
        notifications it chose; then send its verification email unless
        its address is already verified."""
        self.ensure_one()
        user = self.sudo()
        user.write(
            {
                "linkup_email_verified": verified,
                "linkup_verified_date": verified and fields.Datetime.now(),
                "linkup_consent_required": True,
                "linkup_age_attested": True,
                "linkup_age_bracket": form.get("linkup_age_bracket"),
                "linkup_jurisdiction": "CA",
            }
        )
        Consent = self.env["linkup.consent"]
        for purpose in SIGNUP_REQUIRED_CONSENTS:
            Consent._linkup_record(user, purpose, True)
        for purpose, key in SIGNUP_OPTIONAL_CONSENTS.items():
            if Consent._linkup_available(purpose):
                Consent._linkup_apply(user, purpose, checked(form.get(key)))
        if not verified:
            user._linkup_send_verification()

    @api.model
    def _signup_create_user(self, values):
        """A signup without a partner is the public signup of LinkUp: its
        values are checked on the server, the anti-robot limit applies, the
        login becomes a technical identifier and the account copies the
        member template (``base.template_portal_user_id``). ``values`` is
        updated in place: ``signup`` returns its login to authenticate."""
        if "partner_id" in values:
            return super()._signup_create_user(values)
        form = self._linkup_pop_signup_values(values)
        email = self._linkup_check_signup(values, form)
        self._linkup_check_signup_rate()
        values.update(
            login=self._linkup_signup_login(email), email=email, active=True
        )
        user = super()._signup_create_user(values)
        user._linkup_check_signup_groups()
        self.env["linkup.rate.event"]._linkup_hit(
            "signup", self._linkup_request_address()
        )
        user._linkup_after_signup(
            form, verified=not self._linkup_verification_enabled()
        )
        return user

    def _linkup_check_signup_groups(self):
        """Refuse an account of the public signup that the template would
        make more than a restricted member: internal, of the member group,
        without any group of ``SIGNUP_FORBIDDEN_GROUPS``. The error undoes
        the creation."""
        self.ensure_one()
        user = self.sudo()
        if (
            user.share
            or not user._linkup_is_restricted_member()
            or any(
                user._linkup_has_group_id(xmlid)
                for xmlid in SIGNUP_FORBIDDEN_GROUPS
            )
        ):
            _logger.error(
                "LinkUp: the signup template gives more than the member"
                " group; the signup is refused."
            )
            raise SignupError(_("Could not create a new account."))

    @api.model
    def _linkup_public_signup(self, values):
        """Run the public signup the way its page does when addresses are
        verified, without telling whether an address has an account.

        ``values`` holds the fields of ``auth_signup`` and those of the
        community. The form is checked as for any signup, and refused with
        the same errors. A free address then gets its account and its
        verification email; an address already used gets an email telling
        how to log in, and a banned one nothing. The page answers the
        three cases alike, and each one counts against the limit by
        address, so that no series of signups lists the addresses of the
        members (LU-NF-009).
        """
        values = dict(values)
        form = self._linkup_pop_signup_values(dict(values))
        fields_only = {
            key: value
            for key, value in values.items()
            if key not in tools.SIGNUP_FIELDS
        }
        email = self._linkup_check_signup(
            dict(fields_only), form, check_address=False
        )
        self._linkup_check_signup_rate()
        closed = self._linkup_address_closed(email)
        if not closed:
            self.signup(values)
            return
        self.env["linkup.rate.event"]._linkup_hit(
            "signup", self._linkup_request_address()
        )
        if closed == "taken":
            self._linkup_send_signup_existing(email)

    @api.model
    def _linkup_send_signup_existing(self, email):
        """Tell the active account using ``email`` that a signup tried it:
        it logs in, or resets its password. At most one such email per
        ``linkup.verification_resend_minutes`` (10) minutes reaches an
        account, so that the signup page sends no flood of them."""
        user = self.sudo().search(
            [
                "|",
                ("login", "=ilike", email),
                ("partner_id.email_normalized", "=", email),
            ],
            limit=1,
        )
        template = self.env.ref(
            EXISTING_TEMPLATE_XMLID, raise_if_not_found=False
        )
        if not user or not user.email or not template:
            return False
        minutes = self.env["linkup.reflet"]._linkup_param(
            RESEND_MINUTES_PARAM, DEFAULT_RESEND_MINUTES
        )
        Rate = self.env["linkup.rate.event"]
        if Rate._linkup_exceeded(
            "verification", user.id, 1, timedelta(minutes=minutes)
        ):
            return False
        Rate._linkup_hit("verification", user.id)
        base_url = user.get_base_url()
        template.with_user(SUPERUSER_ID).with_context(
            linkup_login_url=f"{base_url}/web/login",
            linkup_reset_url=f"{base_url}/web/reset_password",
        ).send_mail(
            user.id,
            email_values={"model": False, "res_id": False, "author_id": False},
        )
        return True

    @api.model
    def reset_password(self, login):
        """Answer a login or an address without an account as one with an
        account: the page then says the same in both cases, and only an
        existing account receives the email (LU-NF-009)."""
        users = self.search(self._get_login_domain(login))
        if not users:
            users = self.search(self._get_email_domain(login))
        if len(users) != 1:
            return False
        return super().reset_password(login)

    @api.model
    def _linkup_signup_invited(self, values, invitation):
        """Check the form of an invitation page as a public signup, without
        the limit by address: the token is the proof. The address of the
        invitation is verified by the signup itself (LU-F-020 RM4); another
        address receives a verification email. A phone invitation compares
        the number typed (``linkup_phone``) with its own."""
        form = self._linkup_pop_signup_values(values)
        invited = email_normalize(values.get("login") or "")
        same = bool(invited) and invited == invitation.sudo().email
        self._linkup_check_signup(
            dict(values, email=invited), form, check_domain=not same
        )
        values["name"] = values["name"].strip()
        invitation = invitation.with_context(
            linkup_typed_phone=form.get("linkup_phone") or ""
        )
        login, password = super()._linkup_signup_invited(values, invitation)
        user = self.sudo().search([("login", "=", login)], limit=1)
        user._linkup_after_signup(form, verified=same)
        return login, password

    @api.model
    def _linkup_request_address(self):
        """The address IP of the current request, as the limits count it:
        an IPv6 address counts as its /64 network, which one subscriber
        holds whole.

        ``remote_addr`` follows ``X-Forwarded-For`` only with ``proxy_mode``
        on, where the proxy appends the address it saw (LU-NF-007): without
        it, a header a client sends changes nothing."""
        address = (request and request.httprequest.remote_addr) or ""
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return address or "n/a"
        if parsed.version == 4:
            return str(parsed)
        if parsed.ipv4_mapped:
            return str(parsed.ipv4_mapped)
        return str(
            ipaddress.ip_network(f"{parsed}/{IPV6_PREFIX}", strict=False)
        )

    @api.model
    def _linkup_signup_rate_exceeded(self, address=None):
        """Whether the address of the request already made the number of
        signups ``linkup.signup_rate_per_ip_hour`` allows in the hour."""
        limit = self.env["linkup.reflet"]._linkup_param(
            SIGNUP_RATE_PARAM, DEFAULT_SIGNUP_RATE
        )
        return self.env["linkup.rate.event"]._linkup_exceeded(
            "signup",
            address or self._linkup_request_address(),
            limit,
            timedelta(hours=1),
        )

    @api.model
    def _linkup_check_signup_rate(self):
        if self._linkup_signup_rate_exceeded():
            raise LinkupError(
                "linkup.rate_limited",
                _("Too many signups from this connection, try again later."),
            )

    # ------------------------------------------------------------------
    # Verification of the address (LU-F-110 RM3)
    # ------------------------------------------------------------------

    def _linkup_send_verification(self):
        """Send the account a link that verifies its address, valid
        ``VERIFY_HOURS`` hours and once; a new link voids the former one.

        The email is attached to no record and created by the superuser,
        like an invitation: its body holds the token."""
        self.ensure_one()
        user = self.sudo()
        if not user.email:
            return False
        token = secrets.token_urlsafe(32)
        user.write(
            {
                "linkup_verify_token_hash": token_hash(token),
                "linkup_verify_expiry": fields.Datetime.now()
                + timedelta(hours=VERIFY_HOURS),
            }
        )
        template = self.env.ref(
            VERIFY_TEMPLATE_XMLID, raise_if_not_found=False
        )
        if not template:
            return False
        template.with_user(SUPERUSER_ID).with_context(
            linkup_verify_url=f"{user.get_base_url()}/linkup/verify/{token}",
            linkup_verify_hours=VERIFY_HOURS,
        ).send_mail(
            user.id,
            email_values={"model": False, "res_id": False, "author_id": False},
        )
        return True

    @api.model
    @server_context
    def linkup_resend_verification(self):
        """Send the current member a new verification link, at most once
        per ``linkup.verification_resend_minutes`` (10) minutes, beyond
        which the code is ``linkup.rate_limited``."""
        self.env["linkup.reflet"]._linkup_check_member()
        user = self.env.user
        if user._linkup_is_verified():
            return {"verified": True}
        minutes = self.env["linkup.reflet"]._linkup_param(
            RESEND_MINUTES_PARAM, DEFAULT_RESEND_MINUTES
        )
        Rate = self.env["linkup.rate.event"]
        Rate._linkup_check(
            "verification",
            user.id,
            1,
            timedelta(minutes=minutes),
            _(
                "A link was sent a moment ago: check your mailbox, or try"
                " again in a few minutes."
            ),
        )
        Rate._linkup_hit("verification", user.id)
        user._linkup_send_verification()
        return {"verified": False, "email": mask_email(user.sudo().email)}

    @api.model
    def _linkup_verify_token(self, token):
        """Verify the address of the account a token was sent to, once and
        before its expiry. Return the account, or an empty recordset."""
        if not isinstance(token, str) or not 20 <= len(token) <= 100:
            return self.browse()
        user = self.sudo().search(
            [
                ("linkup_verify_token_hash", "=", token_hash(token)),
                ("linkup_verify_expiry", ">", fields.Datetime.now()),
            ],
            limit=1,
        )
        if user:
            user.write(
                {
                    "linkup_email_verified": True,
                    "linkup_verified_date": user.linkup_verified_date
                    or fields.Datetime.now(),
                    "linkup_verify_token_hash": False,
                    "linkup_verify_expiry": False,
                }
            )
            user._linkup_send_consent_state()
        return user

    # ------------------------------------------------------------------
    # Personal code (LU-F-112 RM2, Q-21)
    # ------------------------------------------------------------------

    def _linkup_code(self):
        """The personal code of the member, created at its first use."""
        self.ensure_one()
        user = self.sudo()
        if not user.linkup_personal_code:
            user._linkup_new_code()
        return user.linkup_personal_code

    def _linkup_new_code(self):
        """Give the member a new code: the former one stops working."""
        self.ensure_one()
        user = self.sudo()
        Users = self.sudo().with_context(active_test=False)
        for _attempt in range(10):
            code = tools.new_code()
            if not Users.search_count(
                [("linkup_personal_code", "=", code)], limit=1
            ):
                user.linkup_personal_code = code
                return code
        raise UserError(_("No code could be created, try again."))

    @api.model
    def _linkup_find_by_code(self, code):
        """The active restricted member holding ``code``, or an empty
        recordset."""
        code = tools.normalize_code(code)
        if not code:
            return self.browse()
        user = self.sudo().search(
            [("linkup_personal_code", "=", code), ("share", "=", False)],
            limit=1,
        )
        return (
            user
            if user and user._linkup_is_restricted_member()
            else (self.browse())
        )

    @api.model
    @server_context
    def linkup_regenerate_code(self):
        """Replace the code of the current member; return the new one."""
        self.env["linkup.reflet"]._linkup_check_member()
        return tools.format_code(self.env.user._linkup_new_code())

    # ------------------------------------------------------------------
    # Profile (LU-F-082)
    # ------------------------------------------------------------------

    def _linkup_send_consent_state(self):
        """Send the member's clients what their banners read."""
        for user in self.sudo():
            user.partner_id._bus_send_store(user._linkup_consent_state())

    def _linkup_consent_state(self):
        self.ensure_one()
        user = self.sudo()
        return {
            "linkup_email_verified": user._linkup_is_verified(),
            "linkup_consent_missing": self.env[
                "linkup.consent"
            ]._linkup_missing(user),
        }

    @api.model
    @server_context
    def linkup_profile_info(self):
        """The profile of the current member: pseudonym, address and its
        verification, phone, language, who may send them a first
        reflection, their personal code, their consents, what they
        declared at signup, the decisions of the moderation about them,
        the reports they made and the members they block."""
        self.env["linkup.reflet"]._linkup_check_member()
        user = self.env.user.sudo()
        installed = dict(self.env["res.lang"].get_installed())
        params = self.env["ir.config_parameter"].sudo()
        return {
            "user_id": user.id,
            "partner_id": user.partner_id.id,
            "name": user.partner_id.name or "",
            "email": user.email or "",
            "email_verified": user._linkup_is_verified(),
            "phone": user.partner_id.phone or "",
            "lang": user.lang or "",
            "langs": [
                [code, installed[code]]
                for code in PROFILE_LANGS
                if code in installed
            ],
            "first_reflet_scope": user.linkup_first_reflet_scope or "code",
            "code": tools.format_code(user._linkup_code()),
            "consents": self.env["linkup.consent"].linkup_consents_info(),
            "age_bracket": user.linkup_age_bracket or False,
            "jurisdiction": user.linkup_jurisdiction or False,
            "terms_url": params.get_param(TERMS_URL_PARAM, ""),
            "privacy_url": params.get_param("linkup.privacy_policy_url", ""),
            **self._linkup_deletion_info(),
            "notices": self.env[
                "linkup.moderation.notice"
            ].linkup_my_notices(),
            "reports": self.env["linkup.report"].linkup_my_reports(),
            "blocked": self.env["linkup.block"].linkup_blocked_members(),
        }

    @api.model
    def _linkup_clean_profile(self, vals):
        """The values of ``vals`` the profile writes, checked; the others
        are ignored."""
        values = {}
        if "name" in vals:
            name = (
                vals["name"].strip() if isinstance(vals["name"], str) else ""
            )
            if not name or len(name) > PSEUDONYM_MAX_LENGTH:
                raise LinkupError(
                    "linkup.validation",
                    _(
                        "Choose a pseudonym of at most %(count)s characters.",
                        count=PSEUDONYM_MAX_LENGTH,
                    ),
                    field="name",
                )
            values["name"] = name
        if "phone" in vals:
            phone = vals["phone"] if isinstance(vals["phone"], str) else ""
            phone = phone.strip()
            if phone and (
                len(phone) > PHONE_MAX_LENGTH
                or not tools.normalize_phone(phone)
            ):
                raise LinkupError(
                    "linkup.validation",
                    _("Enter a valid phone number."),
                    field="phone",
                )
            values["phone"] = phone or False
        if "lang" in vals:
            installed = dict(self.env["res.lang"].get_installed())
            if (
                vals["lang"] not in PROFILE_LANGS
                or vals["lang"] not in installed
            ):
                raise LinkupError(
                    "linkup.validation",
                    _("Choose one of the languages offered."),
                    field="lang",
                )
            values["lang"] = vals["lang"]
        if "first_reflet_scope" in vals:
            scopes = {code for code, _label in tools.FIRST_REFLET_SCOPES}
            if vals["first_reflet_scope"] not in scopes:
                raise LinkupError(
                    "linkup.validation",
                    _("Choose who may send you a first reflection."),
                    field="first_reflet_scope",
                )
            values["linkup_first_reflet_scope"] = vals["first_reflet_scope"]
        if "image" in vals:
            values["image_1920"] = self._linkup_clean_photo(vals["image"])
        if "email" in vals:
            # Checked by ``write``, whichever way the member writes it.
            values["email"] = vals["email"]
        return values

    @api.model
    def _linkup_clean_photo(self, image):
        """A photo as base64 text, checked to be an image of at most
        ``PHOTO_MAX_BYTES``; ``False`` removes it."""
        if not image:
            return False
        try:
            data = base64.b64decode(image, validate=True)
            if len(data) > PHOTO_MAX_BYTES:
                raise ValueError("too large")
            base64_to_image(image)
        except (binascii.Error, ValueError, UserError, TypeError):
            raise LinkupError(
                "linkup.validation",
                _("Choose a photo in a common format, of at most 5 MB."),
                field="image",
            ) from None
        return image

    @api.model
    def _linkup_clean_email(self, email):
        """A new address of the current member: valid, not disposable, not
        used by another account, not banned."""
        user = self.env.user.sudo()
        email = email if isinstance(email, str) else ""
        normalized = email_normalize(email)
        if not normalized or len(email_split(email)) != 1:
            raise LinkupError(
                "linkup.validation",
                _("Enter a valid email address."),
                field="email",
            )
        if normalized == email_normalize(user.email or ""):
            return user.email
        if self._linkup_is_disposable(normalized):
            raise LinkupError(
                "linkup.validation",
                _("Addresses of this domain are not accepted; use another."),
                field="email",
            )
        if self._linkup_email_taken(normalized) or self.env[
            "linkup.email.blocklist"
        ]._linkup_is_listed(normalized, "banned"):
            raise LinkupError(
                "linkup.validation",
                _("This address is not available."),
                field="email",
            )
        return normalized

    @api.model
    @server_context
    def linkup_profile_write(self, vals):
        """Write the profile of the current member: ``name`` (the
        pseudonym, LU-F-113), ``phone``, ``lang``, ``first_reflet_scope``,
        ``image`` (base64, or ``False``) and ``email``, which ``write``
        checks and verifies again. Return ``linkup_profile_info``."""
        self.env["linkup.reflet"]._linkup_check_member()
        if not isinstance(vals, dict):
            vals = {}
        values = self._linkup_clean_profile(vals)
        if values:
            self.env.user.sudo().write(values)
        return self.linkup_profile_info()

    # ------------------------------------------------------------------
    # Personal data (LU-F-117, LU-F-026 RM4)
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def linkup_export_data(self):
        """Everything LinkUp keeps about the current member, as JSON-ready
        values (``linkup.personal.data._linkup_export``); nobody exports
        the data of another account."""
        self.env["linkup.reflet"]._linkup_check_member()
        return self.env["linkup.personal.data"]._linkup_export(self.env.user)

    @api.model
    def _linkup_deletion_info(self):
        """The deletion of the account of the current member as their
        profile reads it: the date it was asked, the date of the erasure,
        and the delay of grace in days."""
        user = self.env.user.sudo()
        Data = self.env["linkup.personal.data"]
        grace = Data._linkup_period("deletion_grace")
        requested = user.linkup_deletion_requested_date
        return {
            "deletion_requested": requested or False,
            "deletion_date": (requested + grace) if requested else False,
            "deletion_grace_days": grace.days,
        }

    @api.model
    @server_context
    def linkup_request_deletion(self):
        """Ask for the deletion of the account of the current member: it is
        erased once the delay of grace is over (``linkup.deletion_grace_days``,
        30), and cancelled meanwhile by ``linkup_cancel_deletion``. A second
        request keeps the first date. An administrator account is closed by
        another administrator. Return ``_linkup_deletion_info``."""
        self.env["linkup.reflet"]._linkup_check_member()
        user = self.env.user
        if not user._linkup_is_restricted_member():
            raise LinkupError(
                "linkup.unavailable",
                _(
                    "An administrator account is closed by another administrator."
                ),
            )
        if not user.sudo().linkup_deletion_requested_date:
            user.sudo().linkup_deletion_requested_date = fields.Datetime.now()
        return self._linkup_deletion_info()

    @api.model
    @server_context
    def linkup_cancel_deletion(self):
        """Cancel the deletion the current member asked for, during the
        delay of grace (LU-F-026 RM4); the account stays as it is."""
        self.env["linkup.reflet"]._linkup_check_member()
        self.env.user.sudo().linkup_deletion_requested_date = False
        return self._linkup_deletion_info()

    # ------------------------------------------------------------------
    # Consents mirrored by fields of other modules (LU-F-111)
    # ------------------------------------------------------------------

    def _linkup_writes_own_account(self):
        """Whether the current user, a restricted member who is not a
        LinkUp administrator, writes their own account, as the profile and
        the preferences of Odoo do, under ``sudo`` or not."""
        user = self.env.user
        return (
            len(self) == 1
            and self.id == self.env.uid
            and user._linkup_is_restricted_member()
            and not user._linkup_has_group_id(ADMIN_GROUP)
        )

    def _linkup_check_own_email(self, vals):
        """The values of a member writing their own address, checked as the
        profile checks it (``_linkup_clean_email``), and whether the
        address changes."""
        current = email_normalize(self.sudo().email or "")
        email = self._linkup_clean_email(vals["email"])
        return dict(vals, email=email), email_normalize(email) != current

    def write(self, vals):
        """Check the new address a member writes on their own account, which
        the preferences of Odoo allow (``SELF_WRITEABLE_FIELDS``), as the
        profile does; a changed address is verified again, and until its
        link is clicked the member sends nothing (LU-F-110 RM3).

        Record a consent each time a preference that mirrors one changes,
        whoever writes it: the Network view, the profile or the signup."""
        new_email = False
        if "email" in vals and self._linkup_writes_own_account():
            vals, new_email = self._linkup_check_own_email(vals)
        mirrored = {
            purpose: field
            for purpose, field in MIRROR_FIELDS.items()
            if field in vals and field in self._fields
        }
        before = {}
        if mirrored:
            for user in self.sudo():
                before[user.id] = {
                    field: bool(user[field]) for field in mirrored.values()
                }
        res = super().write(vals)
        if mirrored:
            Consent = self.env["linkup.consent"]
            for user in self.sudo():
                for purpose, field in mirrored.items():
                    value = bool(user[field])
                    if before[user.id][
                        field
                    ] != value or not Consent.sudo().search_count(
                        [("user_id", "=", user.id), ("purpose", "=", purpose)],
                        limit=1,
                    ):
                        Consent._linkup_record(user, purpose, value)
        if new_email and self._linkup_verification_enabled():
            user = self.sudo()
            user.linkup_email_verified = False
            user._linkup_send_verification()
            user._linkup_send_consent_state()
        return res

    # ------------------------------------------------------------------
    # Reading of the other users (LU-NF-009, Q-27)
    # ------------------------------------------------------------------

    def _read_format(self, fnames, load="_classic_read"):
        """Blank the login and the contact details of the other users, and
        the photo of those not linked, in what a restricted member reads
        (LU-F-082 CA1, LU-F-112 CA3)."""
        result = super()._read_format(fnames, load)
        if privacy.contact_closed(self.env):
            privacy.mask_rows(
                self,
                result,
                fnames,
                privacy.USER_CONTACT_FIELDS,
                self.env.uid,
                lambda: privacy.linked_user_ids(self.env),
            )
        return result

    def _condition_to_sql(self, alias, fname, operator, value, query):
        """A restricted member searches no user by their login or contact
        details (LU-F-112 CA3)."""
        if privacy.search_closed(self, fname, privacy.USER_CONTACT_FIELDS):
            return SQL("FALSE")
        return super()._condition_to_sql(alias, fname, operator, value, query)

    # ------------------------------------------------------------------
    # Web client
    # ------------------------------------------------------------------

    def _init_store_data(self, store: Store, /):
        """Give a member the state of their address and consents, which the
        banners of the Reflet view read; the help in distress and the
        delay of an urgent report (LU-F-118, LU-NF-042); the number of
        decisions of the moderation they have not read; and to a
        moderator, the number of urgent reports of their queue."""
        super()._init_store_data(store)
        user = self.env.user
        if user._is_public() or not user._linkup_has_group_id(MEMBER_GROUP):
            return
        store.add(user._linkup_consent_state())
        Report = self.env["linkup.report"]
        params = self.env["ir.config_parameter"].sudo()
        resources = params.get_param(HELP_RESOURCES_PARAM, "") or ""
        values = {
            "linkup_help_resources": [
                line.strip() for line in resources.splitlines() if line.strip()
            ],
            "linkup_moderation_hours": (
                params.get_param(MODERATION_HOURS_PARAM, "") or ""
            ).strip(),
            "linkup_urgent_hours": Report._linkup_hours(True),
            "linkup_notice_unseen": self.env[
                "linkup.moderation.notice"
            ]._linkup_unseen_count(user),
            "linkup_is_moderator": user._linkup_has_group_id(MODERATOR_GROUP),
        }
        if values["linkup_is_moderator"]:
            values["linkup_moderation_urgent"] = Report.sudo().search_count(
                Report._linkup_queue_domain("open") + [("urgent", "=", True)]
            )
        store.add(values)
