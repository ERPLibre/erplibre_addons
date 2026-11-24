# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import re

from altcha.v2 import Challenge, Payload, solve_challenge
from odoo.addons.mail_linkup_reflet.tests.common import LinkupRefletCase

# A signup form filled as a person who accepts the required consents,
# declares an age range and lives in Canada.
SIGNUP_FORM = {
    "linkup_terms": "on",
    "linkup_privacy": "on",
    "linkup_sensitive_data": "on",
    "linkup_adult": "on",
    "linkup_age_bracket": "25_34",
    "linkup_resides_canada": "on",
}
VERIFY_RE = re.compile(r"/linkup/verify/([A-Za-z0-9_-]{20,})")
INVITE_RE = re.compile(r"/linkup/invite/([A-Za-z0-9_-]{20,})")


class LinkupAltchaMixin:
    """Helpers of the proof of work of the signup entries, for an
    ``HttpCase``.

    ``_linkup_altcha_enable`` gives the current website an ALTCHA key, with
    the smallest cost, so that a test solves a challenge at once.
    ``_linkup_altcha_solution`` fetches a challenge from ``/altcha``, as the
    widget of the page does, and returns its solution, the value of the
    ``altcha`` field of a form; it serves once.
    """

    def _linkup_altcha_enable(self):
        website = self.env["website"].get_current_website()
        website.write(
            {
                "altcha_key": "linkup-test-key",
                "altcha_private_key": "linkup-test-private-key",
                "altcha_cost": 2,
            }
        )
        return website

    def _linkup_altcha_solution(self):
        response = self.url_open("/altcha")
        response.raise_for_status()
        challenge = Challenge.from_dict(response.json())
        return Payload(challenge, solve_challenge(challenge)).to_base64()


class LinkupCommunityCase(LinkupRefletCase):
    """The members of the reflections module (Sam, France and Jacques share
    a group, Luce shares nothing), with helpers of the community."""

    def setUp(self):
        super().setUp()
        self.Consent = self.env["linkup.consent"]
        self.Invitation = self.env["linkup.invitation"]
        self.Users = self.env["res.users"]

    def _as_public_account(self, user, verified=False, consents=()):
        """Make ``user`` an account of the public signup: unverified unless
        said, its consents required, those of ``consents`` given."""
        user.sudo().write(
            {
                "linkup_email_verified": verified,
                "linkup_consent_required": True,
            }
        )
        for purpose in consents:
            self.Consent._linkup_record(user, purpose, True)

    def _mails_to(self, email):
        return (
            self.env["mail.mail"]
            .sudo()
            .search([("email_to", "=", email)], order="id")
        )

    def _verify_token(self, email):
        mail = self._mails_to(email)[-1:]
        self.assertTrue(mail, f"No email to {email}.")
        match = VERIFY_RE.search(mail.body_html)
        self.assertTrue(match, "The email holds no verification link.")
        return match.group(1)
