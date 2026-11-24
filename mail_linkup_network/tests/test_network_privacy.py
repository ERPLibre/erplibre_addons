# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The gamification of a member stays theirs, and the preferences of the
network are off by default (LU-NF-012, LU-F-073 RM2, LU-F-082 RM4)."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import LinkupNetworkCase

ADMIN = "mail_linkup_reflet.group_linkup_admin"


@tagged("post_install", "-at_install")
class TestLinkupNetworkPrivacy(LinkupNetworkCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        badge = cls.env.ref("mail_linkup_gamification.badge_first_link")
        cls.badge = badge
        cls.env["gamification.badge.user"].sudo().create(
            [
                {"user_id": cls.france.id, "badge_id": badge.id},
                {"user_id": cls.sam.id, "badge_id": badge.id},
            ]
        )

    def test_read_of_a_linked_member(self):
        """Sam is linked to France and shares a conversation with her: a
        reading of her account by RPC gives neither her karma, nor her
        rank, nor her badges, even once she shows her energy."""
        self.assertTrue(self.france.karma)
        self.assertTrue(self.france.rank_id)
        self._show(self.france, energy=True)
        Users = self.env["res.users"].with_user(self.sam)
        fields = [
            "name",
            "karma",
            "rank_id",
            "next_rank_id",
            "badge_ids",
            "gold_badge",
            "silver_badge",
            "bronze_badge",
        ]
        france = Users.browse(self.france.id)
        values = france.read(fields)[0]
        self.assertEqual(values["name"], "France")
        for fname in fields[1:]:
            self.assertFalse(values[fname], fname)
        values = france.web_read(
            {"karma": {}, "rank_id": {"fields": {"display_name": {}}}}
        )[0]
        self.assertFalse(values["karma"])
        self.assertFalse(values["rank_id"])
        rows = Users.search_read(
            [("id", "in", (self.sam | self.france).ids)], ["karma"]
        )
        karma = {row["id"]: row["karma"] for row in rows}
        self.assertFalse(karma[self.france.id])
        self.assertEqual(karma[self.sam.id], self.sam.karma)

    def test_own_reading(self):
        """A member reads their own karma, rank and badges."""
        values = (
            self.env["res.users"]
            .with_user(self.sam)
            .browse(self.sam.id)
            .read(["karma", "rank_id", "badge_ids"])[0]
        )
        self.assertEqual(values["karma"], self.sam.karma)
        self.assertEqual(values["rank_id"][0], self.sam.rank_id.id)
        self.assertTrue(values["badge_ids"])

    def test_no_search_order_or_group(self):
        """Neither a search, an order nor a grouping by these fields sorts
        the users for a member: each one would tell their activity."""
        Users = self.env["res.users"].with_user(self.sam)
        for domain in (
            [("id", "=", self.france.id), ("karma", ">", 1000)],
            [("rank_id.name", "=", "Flame")],
            [("badge_ids.badge_id", "=", self.badge.id)],
        ):
            with self.assertRaises(AccessError):
                Users.search_count(domain)
        with self.assertRaises(AccessError):
            Users.search([], order="karma desc")
        with self.assertRaises(AccessError):
            Users.read_group([], ["karma:sum"], ["rank_id"])
        with self.assertRaises(AccessError):
            Users._read_group([], ["rank_id"], ["__count"])
        Partners = self.env["res.partner"].with_user(self.sam)
        with self.assertRaises(AccessError):
            Partners.search([("user_ids.karma", ">", 0)])

    def test_badges_and_ranks(self):
        """A badge lists its holders among the member only, and a rank
        lists nobody."""
        values = (
            self.env["gamification.badge"]
            .with_user(self.sam)
            .browse(self.badge.id)
            .read(
                ["unique_owner_ids", "granted_count", "granted_users_count"]
            )[0]
        )
        self.assertEqual(values["unique_owner_ids"], [self.sam.id])
        self.assertFalse(values["granted_count"])
        self.assertFalse(values["granted_users_count"])
        BadgeUser = self.env["gamification.badge.user"].with_user(self.sam)
        self.assertEqual(
            BadgeUser.search([("badge_id", "=", self.badge.id)]).user_id,
            self.sam,
        )
        rank = self.env["gamification.karma.rank"].with_user(self.sam)
        rank = rank.browse(self.france.rank_id.id)
        self.assertTrue(rank.read(["name", "karma_min"]))
        with self.assertRaises(AccessError):
            rank.read(["user_ids"])
        with self.assertRaises(AccessError):
            rank.read(["rank_users_count"])

    def test_administrators_keep_reading(self):
        """A LinkUp administrator and the server read the karma of
        anybody."""
        admin = mail_new_test_user(
            self.env,
            login="linkup_nw_admin",
            name="Admin",
            email="linkup_nw_admin@example.com",
            groups=ADMIN,
        )
        values = (
            self.env["res.users"]
            .with_user(admin)
            .browse(self.france.id)
            .read(["karma"])[0]
        )
        self.assertEqual(values["karma"], self.france.karma)
        self.assertEqual(
            self.env["res.users"]
            .with_user(self.sam)
            .sudo()
            .browse(self.france.id)
            .read(["karma"])[0]["karma"],
            self.france.karma,
        )

    def test_preferences(self):
        """LU-NF-012: both preferences are off by default. A member reads
        and writes their own, never those of another member, and the web
        client receives them."""
        Users = self.env["res.users"].with_user(self.sam)
        own = Users.browse(self.sam.id)
        self.assertEqual(
            own.read(["linkup_links_visible", "linkup_energy_visible"])[0],
            {
                "id": self.sam.id,
                "linkup_links_visible": False,
                "linkup_energy_visible": False,
            },
        )
        self._bus_reset()
        own.write({"linkup_links_visible": True})
        self.assertTrue(self.sam.linkup_links_visible)
        sent = [
            payload
            for target, kind, payload in self._bus_sent()
            if target == self.sam.partner_id
        ]
        self.assertTrue(
            any(
                payload.get("Store", {}).get("linkup_links_visible")
                for payload in sent
            )
        )
        france = Users.browse(self.france.id)
        with self.assertRaises(AccessError):
            france.read(["linkup_links_visible"])
        with self.assertRaises(AccessError):
            france.write({"linkup_energy_visible": True})
        with self.assertRaises(AccessError):
            Users.search([("linkup_energy_visible", "=", True)])

    def test_store_data(self):
        """The web client of a member starts with their preferences and
        the number of partners of the density X3."""
        store = Store()
        self.env["res.users"].with_user(self.sam)._init_store_data(store)
        result = store.get_result()["Store"]
        self.assertFalse(result["linkup_links_visible"])
        self.assertFalse(result["linkup_energy_visible"])
        self.assertEqual(result["linkup_network_top_count"], 2)
