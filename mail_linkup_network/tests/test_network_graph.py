# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The graph of the Network view: LU-F-070, LU-F-072 (T-36)."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import PARTNERS, LinkupNetworkCase


@tagged("post_install", "-at_install")
class TestLinkupNetworkGraph(LinkupNetworkCase):
    def test_six_nodes(self):
        """LU-F-070 CA1: Sam and his six links give six nodes, each tied
        to him by a direct edge carrying the energy he received."""
        graph = self._graph()
        self.assertEqual(graph["level"], "x1")
        self.assertEqual(len(graph["nodes"]), 6)
        self.assertEqual(
            {node["user_id"] for node in graph["nodes"]},
            {user.id for user in self.contacts.values()},
        )
        direct = [edge for edge in graph["edges"] if edge["kind"] == "direct"]
        self.assertEqual(len(direct), 6)
        self.assertTrue(all(edge["source"] == self.sam.id for edge in direct))
        by_user = {node["user_id"]: node for node in graph["nodes"]}
        for key, contact in self.contacts.items():
            self.assertEqual(by_user[contact.id]["energy"], PARTNERS[key])
        self.assertEqual(graph["nodes"][0]["name"], "France")
        self.assertFalse(graph["more"])

    def test_me_energy_is_karma(self):
        """Q-08: the energy of the member is their karma."""
        graph = self._graph()
        self.assertEqual(graph["me"]["user_id"], self.sam.id)
        self.assertEqual(graph["me"]["energy"], sum(PARTNERS.values()))
        self.assertEqual(graph["me"]["energy"], self.sam.karma)

    def test_grey_line_needs_both_consents(self):
        """LU-F-070 CA2: France and Jacques are linked, but Jacques does
        not show his links: X1 draws no line France-Jacques. Once he shows
        them, the line appears; X2 and X3 never draw it."""
        self._activate(self.france, self.jacques)
        self._show(self.france, links=True)
        pair = frozenset((self.france.id, self.jacques.id))
        self.assertNotIn(pair, self._contact_edges(self._graph()))
        self._show(self.jacques, links=True)
        self.assertEqual(self._contact_edges(self._graph()), {pair})
        self.assertFalse(self._contact_edges(self._graph(level="x2")))
        self.assertFalse(self._contact_edges(self._graph(level="x3")))
        self.assertEqual(self._contact_edges(self._graph(level=2)), {pair})

    def test_grey_lines_stay_among_contacts(self):
        """Luce is linked to every contact of Sam and shows her links, as
        they do: she never appears in his graph, not even as a line."""
        self._show(self.luce, *self.contacts.values(), links=True)
        graph = self._graph()
        ids = {node["user_id"] for node in graph["nodes"]}
        self.assertNotIn(self.luce.id, ids)
        for edge in graph["edges"]:
            self.assertNotIn(self.luce.id, (edge["source"], edge["target"]))
        self.assertFalse(self._contact_edges(graph))

    def test_grey_line_of_blocked_pair(self):
        """A pair of contacts that a block separates draws no line."""
        self._activate(self.jean, self.nicolas)
        self._show(self.jean, self.nicolas, links=True)
        pair = frozenset((self.jean.id, self.nicolas.id))
        self.assertEqual(self._contact_edges(self._graph()), {pair})
        self.env["linkup.block"].with_user(self.jean).action_block(
            user_id=self.nicolas.id
        )
        self.assertFalse(self._contact_edges(self._graph()))

    def test_x3_keeps_the_strongest(self):
        """LU-F-072 CA1, Q-40: X3 keeps France and Jacques, the two
        strongest links; the number follows the setting."""
        graph = self._graph(level="x3")
        self.assertEqual(self._names(graph["nodes"]), ["France", "Jacques"])
        self.assertEqual(len(graph["edges"]), 2)
        self.assertEqual(self._graph(level="top")["level"], "x3")
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.network_top_count", "3"
        )
        graph = self._graph(level="x3")
        self.assertEqual(
            self._names(graph["nodes"]), ["France", "Jacques", "Jean"]
        )

    def test_limit_keeps_the_strongest(self):
        """LU-F-070 RM3: beyond the limit, the strongest nodes stay."""
        graph = self._graph(limit=4)
        self.assertEqual(
            self._names(graph["nodes"]),
            ["France", "Jacques", "Jean", "Joanna"],
        )
        self.assertTrue(graph["more"])

    def test_unknown_level(self):
        with self.assertLinkupCode("linkup.validation", "level"):
            self._graph(level="x9")

    def test_only_active_links(self):
        """A pending link, a closed one and a blocked one add no node,
        whoever holds the block; an archived account neither."""
        thomas = mail_new_test_user(
            self.env,
            login="linkup_nw_thomas",
            name="Thomas",
            email="linkup_nw_thomas@example.com",
            groups=MEMBER,
        )
        self.Link._get_or_create(self.sam, thomas)
        closed = self.Link._get_or_create(self.sam, self.luce)
        closed.write({"state": "closed"})
        self.env["linkup.block"].with_user(self.france).action_block(
            user_id=self.sam.id
        )
        self.env["linkup.block"].with_user(self.sam).action_block(
            user_id=self.jacques.id
        )
        self.nicolas.active = False
        names = self._names(self._graph()["nodes"])
        self.assertEqual(names, ["Jean", "Joanna", "Mathieu"])
        # The member France blocks reads her absence as the one of an
        # archived account: no node, no line, no energy.
        france_graph = self._graph(self.france)
        self.assertNotIn(
            self.sam.id, {node["user_id"] for node in france_graph["nodes"]}
        )

    def test_highlight_halo(self):
        """A contact whose highlight to the member is active wears the
        halo; a highlight the member sent does not."""
        self.env["linkup.highlight"].with_user(self.jacques).action_send(
            self.sam.id
        )
        self.env["linkup.highlight"].with_user(self.sam).action_send(
            self.france.id
        )
        halo = {
            node["name"]
            for node in self._graph()["nodes"]
            if node["highlight"]
        }
        self.assertEqual(halo, {"Jacques"})

    def test_member_only(self):
        """Only a LinkUp member reads a graph."""
        outsider = mail_new_test_user(
            self.env,
            login="linkup_nw_outsider",
            name="Visiteur",
            email="linkup_nw_outsider@example.com",
            groups="base.group_user",
        )
        with self.assertRaises(AccessError):
            self._graph(outsider)

    def test_queries_do_not_grow_with_contacts(self):
        """LU-NF-029: the graph reads its contacts in a fixed number of
        queries, whatever their number."""
        self._show(*self.contacts.values(), links=True)
        self._activate(self.france, self.joanna)

        def count():
            self.env.invalidate_all()
            before = self.env.cr.sql_log_count
            self._graph()
            return self.env.cr.sql_log_count - before

        count()
        small = count()
        for index in range(12):
            extra = mail_new_test_user(
                self.env,
                login=f"linkup_nw_extra{index}",
                name=f"Membre {index}",
                email=f"linkup_nw_extra{index}@example.com",
                groups=MEMBER,
            )
            self._activate(self.sam, extra)
            self._show(extra, links=True)
            self._activate(extra, self.france)
        count()
        self.assertEqual(count(), small)
        self.assertEqual(len(self._graph()["nodes"]), 18)
