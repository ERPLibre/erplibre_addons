# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The profile of the member (T-39, LU-F-082, LU-F-113): what the member
writes, what stays reserved, the personal code, the route of the
settings."""

import json

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from .. import tools
from .common import LinkupCommunityCase


@tagged("post_install", "-at_install")
class TestLinkupProfile(LinkupCommunityCase):
    def test_profile_reads_and_writes(self):
        """RM1: pseudonym, phone, language and the first-reflection scope;
        each value is checked on the server."""
        Users = self.Users.with_user(self.sam)
        info = Users.linkup_profile_info()
        self.assertEqual(info["name"], "Sam")
        self.assertEqual(info["first_reflet_scope"], "code")
        self.assertTrue(info["email_verified"])
        self.assertRegex(info["code"], r"^[A-Z2-9]{5}-[A-Z2-9]{5}$")
        info = Users.linkup_profile_write(
            {
                "name": "  Sam S.  ",
                "phone": "514 555-0123",
                "first_reflet_scope": "nobody",
                "login": "not-written",
            }
        )
        self.assertEqual(info["name"], "Sam S.")
        self.assertEqual(info["phone"], "514 555-0123")
        self.assertEqual(self.sam.sudo().linkup_first_reflet_scope, "nobody")
        self.assertNotEqual(self.sam.login, "not-written")
        for vals, field in (
            ({"name": ""}, "name"),
            ({"name": "x" * 65}, "name"),
            ({"phone": "call me"}, "phone"),
            ({"lang": "de_DE"}, "lang"),
            ({"first_reflet_scope": "everybody"}, "first_reflet_scope"),
            ({"image": "bm90IGFuIGltYWdl"}, "image"),
            ({"email": "not-an-address"}, "email"),
            ({"email": self.france.email}, "email"),
        ):
            with self.subTest(field=field):
                with self.assertLinkupCode("linkup.validation", field):
                    Users.linkup_profile_write(vals)

    def test_same_pseudonym_allowed(self):
        """LU-F-113 CA1: a pseudonym need not be unique."""
        info = self.Users.with_user(self.sam).linkup_profile_write(
            {"name": "France"}
        )
        self.assertEqual(info["name"], "France")

    def test_reserved_fields(self):
        """CA2: the member writes their preference; the suspension, the
        verification and the declarations stay out of their reach."""
        me = self.sam.with_user(self.sam)
        me.write({"linkup_first_reflet_scope": "email_or_code"})
        self.assertEqual(
            me.read(["linkup_first_reflet_scope"])[0][
                "linkup_first_reflet_scope"
            ],
            "email_or_code",
        )
        for field, value in (
            ("linkup_suspended_until", "2030-01-01 00:00:00"),
            ("linkup_email_verified", False),
            ("linkup_consent_required", False),
            ("linkup_age_bracket", "65_plus"),
            ("linkup_personal_code", "ABCDEFGHJK"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(AccessError):
                    me.write({field: value})
        with self.assertRaises(AccessError):
            self.france.with_user(self.sam).read(["linkup_first_reflet_scope"])

    def test_personal_code(self):
        """LU-F-112 RM2: a code per member, found again typed in any case
        and with blanks; a new code voids the former one."""
        code = self.sam.sudo()._linkup_code()
        self.assertEqual(len(code), tools.CODE_LENGTH)
        typed = f" {code[:5].lower()} - {code[5:]} "
        self.assertEqual(self.Users._linkup_find_by_code(typed), self.sam)
        new = self.Users.with_user(self.sam).linkup_regenerate_code()
        self.assertNotEqual(new.replace("-", ""), code)
        self.assertFalse(self.Users._linkup_find_by_code(code))
        self.assertFalse(self.Users._linkup_find_by_code("short"))


@tagged("post_install", "-at_install")
class TestLinkupProfileRoute(HttpCase):
    def test_me_settings(self):
        """§9.8: ``/linkup/v1/me/settings`` writes the profile and the
        consents, and answers the profile; a refusal carries its code."""
        mail_new_test_user(
            self.env,
            login="linkup_cm_route",
            password="linkup_cm_route",
            name="Jean",
            email="linkup_cm_route@example.com",
            groups="mail_linkup_reflet.group_linkup_member",
        )
        self.authenticate("linkup_cm_route", "linkup_cm_route")

        def call(params):
            response = self.url_open(
                "/linkup/v1/me/settings",
                data=json.dumps({"jsonrpc": "2.0", "params": params}),
                headers={"Content-Type": "application/json"},
            )
            return response.json()

        result = call(
            {
                "values": {"name": "Jeannot"},
                "consents": {"sensitive_data": True},
            }
        )["result"]
        self.assertEqual(result["name"], "Jeannot")
        consents = {row["purpose"]: row for row in result["consents"]}
        self.assertTrue(consents["sensitive_data"]["granted"])
        error = call({"values": {"lang": "xx"}})["error"]
        self.assertEqual(
            error["data"]["context"]["linkup_code"], "linkup.validation"
        )
