# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""What the Network view never tells, whatever the caller sends, and its
cost with many links (LU-NF-012, LU-NF-029, LU-F-115)."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import LinkupNetworkCase

MEMBER_GROUP = "mail_linkup_reflet.group_linkup_member"


@tagged("post_install", "-at_install")
class TestLinkupNetworkAdversarial(LinkupNetworkCase):
    def _contact_ids(self, rows):
        return {row["user_id"] for row in rows}

    def test_context_does_not_widen_the_network(self):
        """A caller who turns ``active_test`` off by RPC still gets no
        archived account, and no halo of a highlight put out."""
        self._show(*self.contacts.values(), energy=True)
        self.nicolas.active = False
        Highlight = self.env["linkup.highlight"].with_user(self.jacques)
        Highlight.browse(Highlight.action_send(self.sam.id)).action_withdraw()
        Link = self.Link.with_user(self.sam).with_context(active_test=False)
        graph = Link.get_network_graph(level="x2")
        self.assertNotIn(self.nicolas.id, self._contact_ids(graph["nodes"]))
        self.assertFalse(
            [node for node in graph["nodes"] if node["highlight"]]
        )
        for kind in ("partners", "active"):
            rows = Link.get_ranking(kind=kind)["rows"]
            self.assertNotIn(self.nicolas.id, self._contact_ids(rows))
            self.assertEqual(len(rows), 5)
        self.assertEqual(
            Link.get_link_card(self.nicolas.id), {"available": False}
        )
        self.assertFalse(
            Link.get_link_card(self.jacques.id)["highlight_received"]
        )

    def test_rank_holders_stay_closed(self):
        """A member does not find the rank of another member by searching
        the ranks by their holders; an administrator does."""
        Rank = self.env["gamification.karma.rank"].with_user(self.sam)
        for domain in (
            [("user_ids", "in", [self.france.id])],
            [("user_ids.id", "=", self.france.id)],
            [("user_ids.name", "=", "France")],
        ):
            with self.assertRaises(AccessError):
                Rank.search_count(domain)
        self.assertTrue(Rank.search_count([]))
        self.assertEqual(
            self.env["gamification.karma.rank"].search(
                [("user_ids", "in", [self.france.id])]
            ),
            self.france.rank_id,
        )

    def test_preferences_of_others_stay_closed(self):
        """The two preferences of a member are read, searched and written
        by that member only."""
        self._show(self.france, links=True, energy=True)
        Users = self.env["res.users"].with_user(self.sam)
        with self.assertRaises(AccessError):
            Users.browse(self.france.id).read(["linkup_energy_visible"])
        with self.assertRaises(AccessError):
            Users.search_count([("linkup_links_visible", "=", True)])
        with self.assertRaises(AccessError):
            Users.browse(self.france.id).write({"linkup_links_visible": False})

    def test_phantom_reflection_leaves_no_trace(self):
        """A reflection and a highlight that Sam sends to Joanna while she
        blocks him reach nobody: once she lifts the block, neither card of
        the pair holds the reflection, and her graph wears no halo."""
        Block = self.env["linkup.block"]
        Block.with_user(self.joanna).action_block(user_id=self.sam.id)
        phantom = self._sent_to(self.sam, self.joanna)
        self.assertTrue(phantom.sudo().phantom)
        self.env["linkup.highlight"].with_user(self.sam).action_send(
            self.joanna.id
        )
        Block.with_user(self.joanna).action_unblock(user_id=self.sam.id)
        for reader, other in (
            (self.sam, self.joanna),
            (self.joanna, self.sam),
        ):
            card = self._card(other, reader)
            self.assertTrue(card["available"])
            self.assertNotIn(
                phantom.id, [entry["reflet_id"] for entry in card["entries"]]
            )
            self.assertNotIn(
                phantom.id,
                [
                    values["id"]
                    for values in card["store"].get("linkup.reflet", [])
                ],
            )
        joanna_graph = self._graph(self.joanna, level="x2")
        sam_node = [
            node
            for node in joanna_graph["nodes"]
            if node["user_id"] == self.sam.id
        ]
        self.assertEqual(len(sam_node), 1)
        self.assertFalse(sam_node[0]["highlight"])

    def test_ignored_reflection_reads_as_delivered(self):
        """A reflection France ignores looks the same to Sam, its author,
        in the card of the link: same entries, no ignore flag."""
        reflet = self._sent_to(self.sam, self.france)
        before = self._card(self.france)["entries"]
        reflet.with_user(self.france).action_ignore()
        card = self._card(self.france)
        self.assertEqual(card["entries"], before)
        for values in card["store"].get("linkup.reflet", []):
            self.assertNotIn("recipient_ignored", values)
        self.assertTrue(
            any(
                values.get("recipient_ignored")
                for values in self._card(self.sam, self.france)["store"][
                    "linkup.reflet"
                ]
            )
        )

    def test_suspension_is_not_told(self):
        """A suspended contact keeps their node, their row and their card:
        the view of a linked member does not tell a sanction."""
        self.jean.sudo().linkup_suspended_until = (
            fields.Datetime.now() + timedelta(days=7)
        )
        self.assertTrue(self.jean._linkup_is_suspended())
        self.assertIn(self.jean.id, self._contact_ids(self._graph()["nodes"]))
        self.assertIn(
            self.jean.id,
            self._contact_ids(self._ranking("partners")["rows"]),
        )
        self.assertTrue(self._card(self.jean)["available"])
        # The suspended member reads their own network as before.
        self.assertIn(
            self.sam.id,
            self._contact_ids(self._graph(self.jean)["nodes"]),
        )

    def test_two_hundred_links(self):
        """LU-NF-029: with about 200 links, the graph draws the 50
        strongest, and the graph, the rankings and the card read in a
        number of queries that does not grow with the links."""
        member = self.env.ref(MEMBER_GROUP)

        def add_contacts(start, count):
            users = (
                self.env["res.users"]
                .with_context(no_reset_password=True, mail_create_nolog=True)
                .create(
                    [
                        {
                            "login": f"linkup_nw_many{index}",
                            "name": f"Membre {index:03d}",
                            "email": f"linkup_nw_many{index}@example.com",
                            "groups_id": [(6, 0, member.ids)],
                        }
                        for index in range(start, start + count)
                    ]
                )
            )
            self._age_accounts(users)
            for index, user in enumerate(users):
                link = self._activate(self.sam, user)
                self._pay(self.sam, link, 10 + index)
                self._pay(user, link, 10 + index)
            self._show(*users, links=True, energy=True)
            previous = None
            for user in users:
                if previous:
                    self._activate(previous, user)
                previous = user
            return users

        def queries(call):
            self.env.invalidate_all()
            before = self.env.cr.sql_log_count
            call()
            return self.env.cr.sql_log_count - before

        calls = {
            "graph": lambda: self._graph(),
            "partners": lambda: self._ranking("partners"),
            "active": lambda: self._ranking("active"),
            "card": lambda: self._card(self.france),
        }
        self._show(*self.contacts.values(), links=True, energy=True)
        add_contacts(0, 20)
        for call in calls.values():
            queries(call)
        small = {name: queries(call) for name, call in calls.items()}
        add_contacts(20, 180)
        for call in calls.values():
            queries(call)
        large = {name: queries(call) for name, call in calls.items()}
        self.assertEqual(large, small)
        graph = self._graph()
        self.assertEqual(len(graph["nodes"]), 50)
        self.assertTrue(graph["more"])
        self.assertEqual(graph["nodes"][0]["name"], "France")
        shown = self._contact_ids(graph["nodes"])
        for edge in graph["edges"]:
            self.assertIn(edge["target"], shown | {self.sam.id})
            self.assertIn(edge["source"], shown | {self.sam.id})
        self.assertEqual(len(self._ranking("partners")["rows"]), 206)
