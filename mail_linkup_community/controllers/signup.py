# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import http
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.addons.mail_linkup_reflet.controllers.invitation import (
    HOME_URL,
    LinkupInvitationController,
)
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.addons.web.controllers.home import SIGN_UP_REQUEST_PARAMS
from odoo.exceptions import UserError
from odoo.http import request

from ..models.res_users import VERIFY_HOURS
from ..tools import SIGNUP_FIELDS

_logger = logging.getLogger(__name__)

# The fields of the community reach the signup context of auth_signup.
SIGN_UP_REQUEST_PARAMS.update(SIGNUP_FIELDS)


class LinkupCommunityController(LinkupInvitationController):
    """The public signup of LinkUp and its pages (LU-F-110, LU-F-111), and
    the routes of the profile and of the safety of the mobile client.

    ``/web/signup`` and the page of an invitation link hold, under the
    fields of ``auth_signup``, the consents, each one apart and none
    checked in advance, the attestation of age with its range, and the
    declaration of residence. The server checks them all again
    (``res.users._linkup_check_signup``). Beyond
    ``linkup.signup_rate_per_ip_hour`` signups of the hour from one address,
    the signup page answers HTTP 429.

    While addresses are verified, a signup does not log in: the page
    answers "check your mailbox" whether the address was free, already
    used or banned (``res.users._linkup_public_signup``), and the person
    logs in once the address is confirmed. The page tells nobody which
    addresses have an account; ``signup_email``, which would send a known
    address to the login page with its login, is ignored.

    ``/linkup/verify/<token>`` verifies the address of an account.
    ``/linkup/v1/me/settings`` and ``/linkup/v1/me/verification`` serve the
    profile to the clients, delegating to ``res.users``;
    ``/linkup/v1/report`` and ``/linkup/v1/block`` delegate to
    ``linkup.report`` and ``linkup.block``.
    """

    def _linkup_signup_context(self, posted):
        """The values of the block of the community: the links of the
        texts, the age ranges, and the choices already posted, so that a
        refused form keeps them."""
        params = request.env["ir.config_parameter"].sudo()
        field = request.env["res.users"]._fields["linkup_age_bracket"]
        return {
            "linkup_signup_form": True,
            "linkup_terms_url": params.get_param("linkup.terms_url", ""),
            "linkup_privacy_url": params.get_param(
                "linkup.privacy_policy_url", ""
            ),
            "linkup_age_brackets": field._description_selection(request.env),
            "linkup_posted": {
                key: posted.get(key)
                for key in SIGNUP_FIELDS
                if key != "linkup_website"
            },
        }

    def get_auth_signup_qcontext(self):
        qcontext = super().get_auth_signup_qcontext()
        qcontext.pop("signup_email", None)
        if not qcontext.get("token"):
            qcontext.update(self._linkup_signup_context(qcontext))
        return qcontext

    def _prepare_signup_values(self, qcontext):
        """Add the fields of the community to a signup without a partner
        token; ``res.users`` takes them out again before the creation."""
        values = super()._prepare_signup_values(qcontext)
        if not qcontext.get("token"):
            for key in SIGNUP_FIELDS:
                if key in request.params:
                    values[key] = request.params[key]
        return values

    @http.route()
    def web_auth_signup(self, *args, **kw):
        if request.httprequest.method == "POST":
            qcontext = self.get_auth_signup_qcontext()
            if (
                not qcontext.get("token")
                and qcontext.get("signup_enabled")
                and "error" not in qcontext
            ):
                Users = request.env["res.users"].sudo()
                if Users._linkup_signup_rate_exceeded():
                    qcontext["error"] = request.env._(
                        "Too many signups from this connection, try again"
                        " later."
                    )
                    return self._linkup_signup_page(qcontext, status=429)
                if Users._linkup_verification_enabled():
                    return self._linkup_public_signup(qcontext)
        return super().web_auth_signup(*args, **kw)

    def _linkup_signup_page(self, qcontext, status=200):
        response = request.render("auth_signup.signup", qcontext)
        response.status_code = status
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response

    def _linkup_public_signup(self, qcontext):
        """Sign up without logging in, then answer "check your mailbox",
        the same for a free address and for one that has an account. A
        refused form comes back with its error, and nothing of it stays."""
        try:
            if not request.env["ir.http"]._verify_request_recaptcha_token(
                "signup"
            ):
                raise UserError(
                    request.env._(
                        "Suspicious activity detected by Google reCaptcha."
                    )
                )
            values = self._prepare_signup_values(qcontext)
            with request.env.cr.savepoint():
                request.env["res.users"].sudo()._linkup_public_signup(values)
        except UserError as error:
            qcontext["error"] = error.args[0]
            return self._linkup_signup_page(qcontext)
        except (SignupError, AssertionError) as error:
            _logger.warning("%s", error)
            qcontext["error"] = request.env._(
                "Could not create a new account."
            )
            return self._linkup_signup_page(qcontext)
        return self._linkup_render(
            "mail_linkup_community.linkup_signup_sent_page",
            {"verify_hours": VERIFY_HOURS},
        )

    # ------------------------------------------------------------------
    # Invitation pages
    # ------------------------------------------------------------------

    def _linkup_values(self, invite_token, invitation, lang):
        values = super()._linkup_values(invite_token, invitation, lang)
        values.update(self._linkup_signup_context(request.params))
        values["linkup_phone_required"] = bool(
            invitation and invitation._linkup_channel() == "phone"
        )
        return values

    @http.route()
    def linkup_invite(self, invite_token, lang=None, **kw):
        """A logged-in member who opens a share link types the number of
        the invitation first; the other cases are those of an invitation
        by email."""
        invitation = (
            request.env["linkup.invitation"].sudo()._linkup_find(invite_token)
        )
        if (
            invitation
            and not request.env.user._is_public()
            and invitation._linkup_channel() == "phone"
            and not invitation._linkup_token_code()
        ):
            return self._linkup_invite_phone_member(
                invite_token, invitation, lang, kw
            )
        return super().linkup_invite(invite_token, lang=lang, **kw)

    def _linkup_invite_phone_member(self, invite_token, invitation, lang, kw):
        lang = self._linkup_set_lang(invitation, lang)
        invitation = invitation.with_context(lang=lang)
        values = self._linkup_values(invite_token, invitation, lang)
        if request.httprequest.method == "POST":
            try:
                invitation.with_context(
                    linkup_typed_phone=kw.get("linkup_phone") or ""
                )._linkup_open_for(request.env.user)
                return request.redirect(HOME_URL)
            except LinkupError as error:
                if error.code == "linkup.unavailable":
                    invitation._linkup_wrong_phone()
                    values["error"] = request.env._(
                        "This number is not the one of the invitation."
                    )
                else:
                    values.update(code=error.code, message=error.args[0])
        return self._linkup_render(
            "mail_linkup_community.linkup_invite_phone_page", values
        )

    # ------------------------------------------------------------------
    # Verification of the address
    # ------------------------------------------------------------------

    @http.route(
        "/linkup/verify/<string:verify_token>",
        type="http",
        auth="public",
        methods=["GET"],
        sitemap=False,
        website=True,
    )
    def linkup_verify(self, verify_token, **kw):
        user = (
            request.env["res.users"].sudo()._linkup_verify_token(verify_token)
        )
        return self._linkup_render(
            "mail_linkup_community.linkup_verify_page",
            {
                "verified": bool(user),
                "home_url": HOME_URL,
                "logged_in": not request.env.user._is_public(),
            },
        )

    # ------------------------------------------------------------------
    # Routes of the profile (§9.8)
    # ------------------------------------------------------------------

    @http.route(
        "/linkup/v1/me/settings", type="json", auth="user", methods=["POST"]
    )
    def linkup_me_settings(self, values=None, consents=None):
        """Write the profile (``values``, as ``linkup_profile_write`` takes
        them) and the consents (``consents``, ``{purpose: granted}``);
        return the profile."""
        Users = request.env["res.users"]
        if values:
            Users.linkup_profile_write(values)
        if consents:
            if not isinstance(consents, dict):
                raise LinkupError(
                    "linkup.validation",
                    request.env._("Choose a consent."),
                    field="purpose",
                )
            Consent = request.env["linkup.consent"]
            granted = [key for key, value in consents.items() if value]
            revoked = [key for key, value in consents.items() if not value]
            if granted:
                Consent.action_grant(granted)
            if revoked:
                Consent.action_revoke(revoked)
        return Users.linkup_profile_info()

    @http.route(
        "/linkup/v1/me/verification",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def linkup_me_verification(self):
        """Send a new verification link to the current member."""
        return request.env["res.users"].linkup_resend_verification()

    # ------------------------------------------------------------------
    # Routes of the safety (§9.8)
    # ------------------------------------------------------------------

    @http.route(
        "/linkup/v1/report", type="json", auth="user", methods=["POST"]
    )
    def linkup_report(
        self,
        reason=None,
        description=None,
        message_id=None,
        reflet_id=None,
        user_id=None,
        partner_id=None,
    ):
        """Report a message, a reflection or a member
        (``linkup.report.action_create_report``); return the acknowledgement
        the member reads: the report, whether it is urgent, and the delay
        of an urgent one."""
        Report = request.env["linkup.report"]
        report_id = Report.action_create_report(
            reflet_id=reflet_id,
            message_id=message_id,
            user_id=user_id,
            partner_id=partner_id,
            reason=reason,
            description=description,
        )
        report = Report.browse(report_id)
        return {
            "id": report.id,
            "urgent": report.urgent,
            "urgent_hours": Report._linkup_hours(True),
        }

    @http.route("/linkup/v1/block", type="json", auth="user", methods=["POST"])
    def linkup_block(self, user_id=None, partner_id=None, blocked=True):
        """Block or unblock a member (``linkup.block.action_block`` and
        ``action_unblock``); return whether the member is now blocked."""
        Block = request.env["linkup.block"]
        if blocked:
            Block.action_block(user_id=user_id, partner_id=partner_id)
        else:
            Block.action_unblock(user_id=user_id, partner_id=partner_id)
        return {"blocked": bool(blocked)}
