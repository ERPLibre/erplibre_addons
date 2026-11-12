# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The contact details of the other people (T-14, LU-F-112 RM3, CA2, CA3,
LU-F-082 CA1, LU-NF-009): a member reads no address, phone nor login of a
member of their scope, matches none in their searches, and receives none in
the Discuss Store; administrators keep them.

Sam, France and Jacques share a group conversation: each one is in the
scope of the others.
"""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tools.discuss import Store
from odoo.tests import HttpCase, tagged

from .common import MEMBER, LinkupRefletCase

ADMIN = "mail_linkup_reflet.group_linkup_admin"
FRANCE_PHONE = "+1 514 555 0199"


def _partner_ids(store_data):
    """Ids of the partners held by the result of a ``Store``."""
    return {vals["id"] for vals in store_data.get("res.partner", [])}


class LinkupContactCase(LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.france.partner_id.write({"phone": FRANCE_PHONE})
        cls.admin = cls.env.ref("base.user_admin")
        cls.Partner = cls.env["res.partner"]
        cls.Users = cls.env["res.users"]

    def _post(self, user, body):
        return self.workshop.with_user(user).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )


@tagged("post_install", "-at_install")
class TestLinkupContactPrivacy(LinkupContactCase):
    def test_contact_details_of_others_blanked(self):
        """CA1, CA3: Sam reads France, a member of his scope, without her
        address, phone or login; his own stay."""
        partner = self.france.partner_id.with_user(self.sam).read(
            ["name", "email", "phone", "email_normalized", "email_formatted"]
        )[0]
        self.assertEqual(partner["name"], "France")
        for fname in ("email", "phone", "email_normalized", "email_formatted"):
            self.assertFalse(partner[fname], fname)
        user = self.france.with_user(self.sam).read(
            ["login", "email", "phone"]
        )[0]
        self.assertEqual(
            {user["login"], user["email"], user["phone"]}, {False}
        )
        own = self.sam.with_user(self.sam).read(["login", "email"])[0]
        self.assertEqual(own["login"], self.sam.login)
        self.assertEqual(own["email"], self.sam.email)
        rows = self.Users.with_user(self.sam).search_read(
            [], ["login", "email", "phone"]
        )
        self.assertIn(self.france.id, {row["id"] for row in rows})
        others = [row for row in rows if row["id"] != self.sam.id]
        self.assertEqual(
            {row[fname] for row in others for fname in ("login", "email")},
            {False},
        )

    def test_no_search_on_contact_details(self):
        """RM3: no search of Sam matches an address, a phone or a login,
        the people searches of Discuss included; the server still does."""
        Partner = self.Partner.with_user(self.sam)
        Users = self.Users.with_user(self.sam)
        for domain in (
            [("email", "=", self.france.email)],
            [("email", "ilike", "linkup_rf_france")],
            [("email_normalized", "=", self.france.email)],
            [("phone", "ilike", "555")],
        ):
            with self.subTest(domain=domain):
                self.assertFalse(Partner.search(domain))
                self.assertFalse(Users.search(domain))
        self.assertFalse(Users.search([("login", "=", self.france.login)]))
        self.assertFalse(
            Users.search([("partner_id.email", "=", self.france.email)])
        )
        self.assertFalse(Partner.name_search(self.france.email))
        self.assertEqual(
            Partner.search_for_channel_invite(self.france.email)["count"], 0
        )
        self.assertNotIn(
            self.france.partner_id.id,
            _partner_ids(Partner.im_search(self.france.email)),
        )
        self.assertNotIn(
            self.france.partner_id.id,
            _partner_ids(Partner.get_mention_suggestions(self.france.email)),
        )
        self.assertIn(
            self.france.partner_id.id,
            _partner_ids(Partner.get_mention_suggestions("France")),
        )
        self.assertTrue(
            self.Partner.sudo().search([("email", "=", self.france.email)])
        )

    def test_display_name_holds_no_address(self):
        """``show_email`` writes no address in a name Sam reads."""
        partner = self.france.partner_id.with_user(self.sam).with_context(
            show_email=True
        )
        self.assertNotIn(self.france.email, partner.display_name)
        own = self.sam.partner_id.with_user(self.sam).with_context(
            show_email=True
        )
        self.assertIn(self.sam.email, own.display_name)

    def test_store_leaves_the_address_out(self):
        """The Discuss Store gives no address of a member, whoever reads,
        and no address at all to a member."""
        data = Store(self.france.partner_id.with_user(self.sam).sudo())
        self.assertNotIn("email", data.get_result()["res.partner"][0])
        data = Store(self.france.partner_id.with_user(self.admin))
        self.assertNotIn("email", data.get_result()["res.partner"][0])
        data = Store(self.admin.partner_id.with_user(self.admin))
        self.assertEqual(
            data.get_result()["res.partner"][0]["email"], self.admin.email
        )

    def test_message_author_address(self):
        """The address of the author of a message reaches neither the
        reading nor the Store of Sam, nor his searches; France reads her
        own."""
        message = self._post(self.france, "Bonjour")
        self.assertTrue(message.sudo().email_from)
        row = message.with_user(self.sam).read(["email_from", "reply_to"])[0]
        self.assertFalse(row["email_from"])
        self.assertFalse(row["reply_to"])
        data = Store(
            message.with_user(self.sam), for_current_user=True
        ).get_result()
        self.assertFalse(data["mail.message"][0]["email_from"])
        self.assertFalse(
            self.env["mail.message"]
            .with_user(self.sam)
            .search([("email_from", "ilike", "linkup_rf_france")])
        )
        own = message.with_user(self.france).read(["email_from"])[0]
        self.assertEqual(own["email_from"], message.sudo().email_from)

    def test_administrators_read_everything(self):
        """A system administrator and a LinkUp administrator keep the
        contact details and their searches."""
        luce_admin = mail_new_test_user(
            self.env,
            login="linkup_cp_admin",
            name="Luce administratrice",
            email="linkup_cp_admin@example.com",
            groups=f"{MEMBER},{ADMIN}",
        )
        for reader in (self.admin, luce_admin):
            with self.subTest(reader=reader.login):
                partner = self.france.partner_id.with_user(reader)
                self.assertEqual(
                    partner.read(["email", "phone"])[0],
                    {
                        "id": self.france.partner_id.id,
                        "email": self.france.email,
                        "phone": FRANCE_PHONE,
                    },
                )
                user = self.france.with_user(reader).read(["login"])[0]
                self.assertEqual(user["login"], self.france.login)
                self.assertEqual(
                    self.Partner.with_user(reader).search(
                        [("email", "=", self.france.email)]
                    ),
                    self.france.partner_id,
                )


@tagged("post_install", "-at_install")
class TestLinkupContactPrivacyRoutes(LinkupContactCase, HttpCase):
    """The JSON that Discuss sends to the web client of Sam holds no
    address of France: the member list, the messages and the messaging
    data of a conversation they share."""

    def test_discuss_payloads(self):
        self._post(self.france, "Bonjour")
        self.authenticate(self.sam.login, self.sam.login)
        payloads = {
            "/discuss/channel/members": {
                "channel_id": self.workshop.id,
                "known_member_ids": [],
            },
            "/discuss/channel/messages": {"channel_id": self.workshop.id},
            "/mail/data": {
                "init_messaging": {"channel_types": ["group"]},
                "channels_as_member": True,
            },
        }
        for route, params in payloads.items():
            with self.subTest(route=route):
                result = self.make_jsonrpc_request(route, params)
                text = str(result)
                self.assertIn("France", text)
                self.assertNotIn(self.france.email, text)
                self.assertNotIn(FRANCE_PHONE, text)
