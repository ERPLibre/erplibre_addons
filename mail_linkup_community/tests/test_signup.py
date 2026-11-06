# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The public signup (T-19, LU-F-110, LU-F-111, LU-F-113, Q-22, Q-32):
an internal member of the template, a technical login, its consents and
declarations recorded, every refusal decided by the server, the limit by
address, and pages that tell nobody which addresses have an account
(LU-NF-009)."""

import re
from types import SimpleNamespace
from unittest.mock import patch

from odoo import Command
from odoo.addons.mail_linkup_community.models import res_users
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import SIGNUP_FORM, VERIFY_RE

PASSWORD = "linkup-Signup-2026"
# The marker of the page that answers a signup while addresses are
# verified.
SENT_PAGE = "o-linkup-SignupSentPage"


@tagged("post_install", "-at_install")
class TestLinkupSignup(HttpCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        self.template = self.env.ref(
            "mail_linkup_reflet.user_linkup_member_template"
        )

    def _post(self, email, name="Camille", headers=None, **overrides):
        """Post the signup form as a browser does; ``None`` leaves a field
        out."""
        page = self.url_open("/web/signup")
        self.assertEqual(page.status_code, 200)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        data = dict(
            SIGNUP_FORM,
            login=email,
            name=name,
            password=PASSWORD,
            confirm_password=PASSWORD,
            csrf_token=csrf.group(1),
        )
        data.update(overrides)
        data = {key: value for key, value in data.items() if value is not None}
        response = self.url_open(
            "/web/signup", data=data, allow_redirects=False, headers=headers
        )
        self.opener.cookies.clear()
        return response

    def _user(self, email):
        return (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search([("email", "=", email)])
        )

    def test_page_shows_the_consents(self):
        """RM1: the form holds each consent apart, none checked, the age
        range and the residence, and a pseudonym."""
        page = self.url_open("/web/signup").text
        for name in (
            "linkup_terms",
            "linkup_privacy",
            "linkup_sensitive_data",
            "linkup_adult",
            "linkup_age_bracket",
            "linkup_resides_canada",
        ):
            self.assertIn(f'name="{name}"', page)
        self.assertNotRegex(page, r'name="linkup_terms"[^>]*checked')
        self.assertIn("Pseudonym", page)

    def test_signup_creates_a_restricted_member(self):
        """CA1, CA2, LU-F-113 CA2: an internal member with the groups of the
        template only, the Reflet view as home, Discuss as only app, a
        login without the address, not verified, its consents and
        declarations recorded, its verification email sent."""
        email = "camille.signup@example.com"
        response = self._post(email, linkup_notifications="on")
        self.assertEqual(response.status_code, 200)
        self.assertIn(SENT_PAGE, response.text)
        user = self._user(email)
        self.assertEqual(len(user), 1)
        self.assertTrue(user.active)
        self.assertFalse(user.share)
        self.assertEqual(user.groups_id, self.template.groups_id)
        self.assertEqual(
            user.action_id.id,
            self.env.ref("mail_linkup_reflet.action_linkup_home").id,
        )
        self.assertTrue(user.login.startswith("lu-"))
        self.assertNotIn("camille", user.login)
        self.assertEqual(user.name, "Camille")
        self.assertFalse(user.linkup_email_verified)
        self.assertTrue(user.linkup_consent_required)
        self.assertTrue(user.linkup_age_attested)
        self.assertEqual(user.linkup_age_bracket, "25_34")
        self.assertEqual(user.linkup_jurisdiction, "CA")
        consents = (
            self.env["linkup.consent"]
            .sudo()
            .search([("user_id", "=", user.id)])
        )
        granted = {row.purpose for row in consents if row.granted}
        self.assertTrue(
            {"terms", "privacy", "sensitive_data", "notifications"} <= granted
        )
        self.assertTrue(all(row.version and row.ip_hash for row in consents))
        roots = (
            self.env["ir.ui.menu"]
            .with_user(user)
            .load_menus_root()["children"]
        )
        self.assertEqual(
            [root["id"] for root in roots],
            [self.env.ref("mail.menu_root_discuss").id],
        )
        mail = (
            self.env["mail.mail"]
            .sudo()
            .search(
                [
                    ("email_to", "=", email),
                    ("body_html", "like", "/linkup/verify/"),
                ]
            )
        )
        self.assertEqual(len(mail), 1)
        token = VERIFY_RE.search(mail.body_html).group(1)
        page = self.url_open(f"/linkup/verify/{token}")
        self.assertIn('data-verified="1"', page.text)
        self.assertTrue(user.linkup_email_verified)
        self.assertIn(
            'data-verified="0"', self.url_open(f"/linkup/verify/{token}").text
        )

    def test_login_with_the_address(self):
        """LU-F-113 RM2: the member logs in with their address; the
        technical login stays unknown to them."""
        email = "camille.login@example.com"
        self._post(email)
        self.authenticate(email, PASSWORD)
        self.assertEqual(self.session.uid, self._user(email).id)

    def test_refusals(self):
        """LU-F-111 CA1, Q-22, Q-32, CA5: the server refuses a form without
        a required consent, without the attestation or the range of age,
        without the residence, with a disposable domain or one of its
        subdomains, or with the trap field filled."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.disposable_email_domains", "jetable.example, other.example"
        )
        cases = {
            "terms": {"linkup_terms": None},
            "privacy": {"linkup_privacy": None},
            "sensitive": {"linkup_sensitive_data": None},
            "adult": {"linkup_adult": None},
            "bracket": {"linkup_age_bracket": "12_17"},
            "canada": {"linkup_resides_canada": None},
            "trap": {"linkup_website": "https://spam.example"},
            "pseudonym": {"name": " "},
        }
        for index, (case, overrides) in enumerate(cases.items()):
            with self.subTest(case=case):
                email = f"refused{index}@example.com"
                response = self._post(email, **overrides)
                self.assertEqual(response.status_code, 200)
                self.assertIn("alert-danger", response.text)
                self.assertFalse(self._user(email))
        for email in ("dee@jetable.example", "dee@mx.other.example"):
            with self.subTest(email=email):
                response = self._post(email)
                self.assertIn("alert-danger", response.text)
                self.assertFalse(self._user(email))

    def test_taken_address_answers_as_a_free_one(self):
        """LU-NF-009: an address already used, or banned, gets the page of a
        free one and no account; the account of a used address receives an
        email that tells how to log in, at most once in ten minutes. Each
        try counts against the limit by address."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.signup_rate_per_ip_hour", "4"
        )
        free = self._post("taken@example.com")
        self.assertEqual(len(self._user("taken@example.com")), 1)
        for email in ("TAKEN@example.com", "taken@example.com"):
            with self.subTest(email=email):
                again = self._post(email, name="Another")
                self.assertEqual(again.status_code, free.status_code)
                self.assertIn(SENT_PAGE, again.text)
                self.assertNotIn("alert-danger", again.text)
        self.assertEqual(len(self._user("taken@example.com")), 1)
        notices = (
            self.env["mail.mail"]
            .sudo()
            .search(
                [
                    ("email_to", "=", "taken@example.com"),
                    ("body_html", "like", "/web/reset_password"),
                ]
            )
        )
        self.assertEqual(len(notices), 1)
        self.assertNotIn("/linkup/verify/", notices.body_html)
        self.env["linkup.email.blocklist"]._linkup_add(
            "banned@example.com", "banned"
        )
        banned = self._post("banned@example.com")
        self.assertIn(SENT_PAGE, banned.text)
        self.assertFalse(self._user("banned@example.com"))
        self.assertFalse(
            self.env["mail.mail"]
            .sudo()
            .search([("email_to", "=", "banned@example.com")])
        )
        self.assertEqual(self._post("taken@example.com").status_code, 429)

    def test_known_address_not_sent_to_the_login(self):
        """``signup_email`` sends a known address nowhere: the page of the
        signup neither redirects nor shows its technical login."""
        email = "camille.known@example.com"
        self._post(email)
        self.authenticate(email, PASSWORD)
        self.authenticate(None, None)
        response = self.url_open(
            f"/web/signup?signup_email={email}", allow_redirects=False
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self._user(email).login, response.text)

    def test_reset_password_tells_nothing(self):
        """The page of a forgotten password answers an unknown address as a
        known one, and only the known one receives an email."""
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.reset_password", "True"
        )
        email = "camille.reset@example.com"
        self._post(email)
        answers = []
        for login in (email, "nobody.here@example.com"):
            page = self.url_open("/web/reset_password")
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
            response = self.url_open(
                "/web/reset_password",
                data={"login": login, "csrf_token": csrf.group(1)},
            )
            self.opener.cookies.clear()
            self.assertNotIn("alert-danger", response.text)
            answers.append(response.status_code)
        self.assertEqual(answers[0], answers[1])
        self.assertFalse(
            self.env["mail.mail"]
            .sudo()
            .search([("email_to", "ilike", "nobody.here@example.com")])
        )

    def test_same_pseudonym(self):
        """LU-F-113 CA1: a pseudonym already taken is accepted."""
        self._post("sam.one@example.com", name="Sam")
        self._post("sam.two@example.com", name="Sam")
        self.assertEqual(self._user("sam.two@example.com").name, "Sam")

    def test_signups_per_address(self):
        """CA4, LU-NF-006: three signups from an address in the hour, then
        HTTP 429 with ``linkup.rate_limited``. Without ``proxy_mode``, a
        ``X-Forwarded-For`` header the client sends changes nothing."""
        for index in range(3):
            self._post(
                f"rate{index}@example.com",
                headers={"X-Forwarded-For": f"198.51.100.{index + 1}"},
            )
            self.assertTrue(self._user(f"rate{index}@example.com"))
        response = self._post(
            "rate3@example.com",
            headers={"X-Forwarded-For": "198.51.100.9"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertFalse(self._user("rate3@example.com"))

    def test_address_of_the_limits(self):
        """An IPv6 address counts as its /64 network; an IPv4 address,
        mapped or not, as itself."""
        Users = self.env["res.users"]
        cases = {
            "2001:db8:1:2::5": "2001:db8:1:2::/64",
            "2001:db8:1:2:ffff::9": "2001:db8:1:2::/64",
            "192.0.2.7": "192.0.2.7",
            "::ffff:192.0.2.7": "192.0.2.7",
        }
        for address, key in cases.items():
            fake = SimpleNamespace(
                httprequest=SimpleNamespace(remote_addr=address)
            )
            with self.subTest(address=address), patch.object(
                res_users, "request", fake
            ):
                self.assertEqual(Users._linkup_request_address(), key)

    @mute_logger(
        "odoo.addons.mail_linkup_community.models.res_users",
        "odoo.addons.mail_linkup_community.controllers.signup",
    )
    def test_template_with_more_rights_refused(self):
        """CA1: a template that gives more than the member group creates no
        account."""
        template = self.template.with_context(no_reset_password=True).copy(
            {
                "login": "linkup_template_admin",
                "groups_id": [
                    Command.link(
                        self.env.ref(
                            "mail_linkup_reflet.group_linkup_admin"
                        ).id
                    )
                ],
            }
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "base.template_portal_user_id", str(template.id)
        )
        response = self._post("camille.template@example.com")
        self.assertIn("alert-danger", response.text)
        self.assertFalse(self._user("camille.template@example.com"))
