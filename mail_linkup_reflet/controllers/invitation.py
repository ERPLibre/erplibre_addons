# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.exceptions import UserError
from odoo.http import request
from werkzeug.urls import url_encode

from ..exceptions import LinkupError

_logger = logging.getLogger(__name__)

# Fields of the signup form taken from a request.
SIGNUP_FIELDS = ("login", "name", "password", "confirm_password")
# Where a member lands once the invitation is used: the Reflet view.
HOME_URL = "/odoo/linkup"
# The action of the anti-robot check of a signup, the one of /web/signup.
SIGNUP_ACTION = "signup"


class LinkupInvitationController(AuthSignupHome):
    """The pages of a NewLink invitation link (LU-F-020).

    ``/linkup/invite/<token>`` tells who invites, then signs the person up
    with the form of ``auth_signup``; the account copies the member
    template, and the reflection reaches it when its address is the
    invited one. A logged-in member opening the link uses it for their own
    account, when it holds the invited address. A used, cancelled, expired
    or unknown link gets a page that says so, with the native signup and
    login. A signup through the link first passes the anti-robot check of
    ``/web/signup`` (``ir.http._verify_request_recaptcha_token``), which
    lets every request through unless a captcha module checks it.
    ``/linkup/invite/<token>/optout`` refuses every invitation to
    the address, after a confirmation.

    The path variable is not named ``token``: ``auth_signup`` reads that
    request parameter as the signup token of a partner. The routes are
    ``website`` ones, as ``/web/signup`` is: with the ``website`` module
    installed, the login layout they render reads the current website.
    """

    def _linkup_set_lang(self, invitation, lang):
        """Render in ``lang`` when installed, else in the language of the
        invitation, which is the one of its email."""
        installed = {
            code for code, _name in request.env["res.lang"].get_installed()
        }
        for code in (lang, invitation and invitation.sudo().lang):
            if code and code in installed:
                request.update_context(lang=code)
                return code
        return request.env.lang

    def _linkup_values(self, invite_token, invitation, lang):
        """The values shared by the pages of an invitation."""
        Invitation = request.env["linkup.invitation"]
        code = (
            invitation._linkup_token_code()
            if invitation
            else "linkup.unavailable"
        )
        other = "en_US" if (lang or "").startswith("fr") else "fr_CA"
        values = dict(
            self.get_auth_signup_config(),
            code=code,
            message=code and Invitation._linkup_code_message(code),
            other_lang_url=f"/linkup/invite/{invite_token}?lang={other}",
            privacy_url=request.env["ir.config_parameter"]
            .sudo()
            .get_param("linkup.privacy_policy_url", ""),
            optout_url=f"/linkup/invite/{invite_token}/optout",
            login_url="/web/login?"
            + url_encode({"redirect": f"/linkup/invite/{invite_token}"}),
        )
        if invitation:
            values["intro"] = request.env._(
                "A person you met, %(name)s, would like to make you a"
                " reflection on LinkUp.",
                name=invitation.sudo().inviter_id.partner_id.name,
            )
        return values

    def _linkup_render(self, template, values):
        """Render a page of the link. Its URL holds the token: no other
        site receives it as a referrer, and no cache keeps the page."""
        response = request.render(template, values)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @http.route(
        "/linkup/invite/<string:invite_token>",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        sitemap=False,
        website=True,
    )
    def linkup_invite(self, invite_token, lang=None, **kw):
        invitation = (
            request.env["linkup.invitation"].sudo()._linkup_find(invite_token)
        )
        lang = self._linkup_set_lang(invitation, lang)
        invitation = invitation.with_context(lang=lang)
        values = self._linkup_values(invite_token, invitation, lang)
        if values["code"]:
            return self._linkup_render(
                "mail_linkup_reflet.linkup_invite_page", values
            )
        user = request.env.user
        if not user._is_public():
            try:
                invitation._linkup_open_for(user)
            except LinkupError as error:
                values.update(code=error.code, message=error.args[0])
                return self._linkup_render(
                    "mail_linkup_reflet.linkup_invite_page", values
                )
            return request.redirect(HOME_URL)
        qcontext = {key: kw[key] for key in SIGNUP_FIELDS if key in kw}
        values.update(qcontext)
        if request.httprequest.method == "POST":
            try:
                # The anti-robot check comes first: its refusal reads no
                # address, so it is the same whatever the form holds.
                request.env["ir.http"]._verify_request_recaptcha_token(
                    SIGNUP_ACTION
                )
                signup = self._prepare_signup_values(qcontext)
                login, password = (
                    request.env["res.users"]
                    .sudo()
                    ._linkup_signup_invited(signup, invitation)
                )
                request.env.cr.commit()
                request.session.authenticate(
                    request.db,
                    {"login": login, "password": password, "type": "password"},
                )
                return request.redirect(HOME_URL)
            except LinkupError as error:
                values.update(code=error.code, message=error.args[0])
            except UserError as error:
                values["error"] = error.args[0]
            except (SignupError, AssertionError) as error:
                Users = request.env["res.users"].sudo()
                if Users.search_count(
                    Users._get_login_domain(qcontext.get("login") or ""),
                    limit=1,
                ):
                    values["error"] = request.env._(
                        "Another user is already registered using this email"
                        " address."
                    )
                else:
                    _logger.warning("%s", error)
                    values["error"] = request.env._(
                        "Could not create a new account."
                    )
        return self._linkup_render(
            "mail_linkup_reflet.linkup_invite_page", values
        )

    @http.route(
        "/linkup/invite/<string:invite_token>/optout",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        sitemap=False,
        website=True,
    )
    def linkup_invite_optout(self, invite_token, lang=None, **kw):
        invitation = (
            request.env["linkup.invitation"].sudo()._linkup_find(invite_token)
        )
        lang = self._linkup_set_lang(invitation, lang)
        values = self._linkup_values(invite_token, invitation, lang)
        # The refusal serves whatever the state of the invitation, as long
        # as it exists.
        values["code"] = not invitation and values["code"]
        if invitation and request.httprequest.method == "POST":
            invitation._linkup_optout()
            values["done"] = True
        return self._linkup_render(
            "mail_linkup_reflet.linkup_invite_optout_page", values
        )
