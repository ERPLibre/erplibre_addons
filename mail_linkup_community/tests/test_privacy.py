# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""What a member reads of the others (T-14, T-39, LU-F-082 RM2, RM3, CA1,
LU-F-112 RM3, CA3, LU-NF-009, Q-27): no address, phone nor login of
another member, no search on them, the photo for the linked members only.
"""

import io

from odoo.addons.mail.tools.discuss import Store
from odoo.tests import HttpCase, tagged
from PIL import Image

from .common import LinkupCommunityCase

# A PNG of one pixel.
PIXEL = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
    "DwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestLinkupPrivacy(LinkupCommunityCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.france.partner_id.write({"phone": "+1 514 555 0199"})
        (cls.sam | cls.france).partner_id.write({"image_1920": PIXEL})

    def test_contact_details_of_others_not_read(self):
        """CA1: Sam reads the partner and the user of France, a member of
        his scope, without her address, phone or login; his own stay."""
        partner = self.france.partner_id.with_user(self.sam).read(
            ["name", "email", "phone", "email_normalized"]
        )[0]
        self.assertEqual(partner["name"], "France")
        self.assertFalse(partner["email"])
        self.assertFalse(partner["phone"])
        self.assertFalse(partner["email_normalized"])
        user = self.france.with_user(self.sam).read(
            ["login", "email", "phone"]
        )[0]
        self.assertFalse(user["login"])
        self.assertFalse(user["email"])
        own = self.sam.with_user(self.sam).read(["login", "email"])[0]
        self.assertEqual(own["login"], self.sam.login)
        self.assertEqual(own["email"], self.sam.email)
        rows = self.Users.with_user(self.sam).search_read(
            [], ["login", "email"]
        )
        self.assertEqual(
            {row["email"] for row in rows if row["id"] != self.sam.id},
            {False},
        )

    def test_no_search_on_contact_details(self):
        """RM3, CA3: the searches of a member never match an address, a
        phone or a login, the searches of Discuss included."""
        Partner = self.env["res.partner"].with_user(self.sam)
        Users = self.Users.with_user(self.sam)
        for domain in (
            [("email", "=", self.france.email)],
            [("email", "ilike", "linkup_rf_france")],
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
        result = Partner.search_for_channel_invite(self.france.email)
        self.assertEqual(result["count"], 0)
        self.assertIn(
            self.france.partner_id, Partner.search([("name", "=", "France")])
        )
        # The server keeps searching addresses.
        self.assertTrue(
            self.env["res.partner"]
            .sudo()
            .search([("email", "=", self.france.email)])
        )

    def test_photo_for_linked_members_only(self):
        """RM2, RM3, Q-27: a member of the scope without an active link
        reads the pseudonym only; the active link opens the photo."""
        partner = self.france.partner_id.with_user(self.sam)
        self.assertFalse(partner.read(["image_128"])[0]["image_128"])
        self.assertTrue(
            self.sam.partner_id.with_user(self.sam).read(["image_128"])[0][
                "image_128"
            ]
        )
        self._confirmed()
        self.assertTrue(partner.read(["image_128"])[0]["image_128"])

    def test_store_leaves_the_address_out(self):
        """The Discuss Store gives no address of a member, whoever reads."""
        store = Store(self.france.partner_id.with_user(self.sam).sudo())
        data = store.get_result()["res.partner"][0]
        self.assertNotIn("email", data)
        admin = self.env.ref("base.user_admin")
        store = Store(self.france.partner_id.with_user(admin))
        self.assertNotIn("email", store.get_result()["res.partner"][0])

    def test_administrator_reads_everything(self):
        """A LinkUp administrator keeps the contact details."""
        admin = self.env.ref("base.user_admin")
        partner = self.france.partner_id.with_user(admin).read(["email"])[0]
        self.assertEqual(partner["email"], self.france.email)


@tagged("post_install", "-at_install")
class TestLinkupPrivacyRoute(LinkupCommunityCase, HttpCase):
    """``/web/image`` serves the placeholder in place of the photo of a
    member not linked to the reader (Q-27)."""

    def test_avatar_route(self):
        """The photo of France is one pixel; the placeholder is a large
        image. Sam reads the placeholder until their link is active."""
        self.france.partner_id.write({"image_1920": PIXEL})
        url = f"/web/image/res.partner/{self.france.partner_id.id}/avatar_128"

        def size():
            return Image.open(io.BytesIO(self.url_open(url).content)).size

        self.authenticate(self.sam.login, self.sam.login)
        self.assertGreater(size()[0], 1)
        self._confirmed()
        self.assertEqual(size(), (1, 1))
        self.authenticate(self.france.login, self.france.login)
        self.assertEqual(size(), (1, 1))
