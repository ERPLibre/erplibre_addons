# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The indexes of LU-NF-029, and the SQL queries of each screen of a
member: their number does not grow with the contacts of the member, and
stays under a ceiling. The response times themselves are measured on the
load-test database (``mail_linkup_reflet/tools/linkup_bench_measure.py``).
"""

import re

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.tests import tagged

from .common import LinkupNetworkCase

# The columns of the indexes LU-NF-029 requires, by table.
INDEXES = {
    "linkup_link": [("user_a_id", "user_b_id")],
    "linkup_points_ledger": [
        ("user_id", "date"),
        ("user_id", "partner_user_id"),
    ],
}
# Queries of each screen at most, with the six LinkUp modules installed.
# The sending opens the direct conversation of the pair; a check of the
# groups of a user that queries the database, once per member read, takes
# it far above its ceiling.
CEILINGS = {
    "reflet_view": 25,
    "graph_x1": 15,
    "graph_x2": 13,
    "graph_x3": 12,
    "ranking_partners": 12,
    "ranking_active": 12,
    "link_card": 12,
    "my_points": 17,
    "send": 130,
}


@tagged("post_install", "-at_install")
class TestLinkupNetworkPerformance(LinkupNetworkCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._show_all(cls.sam, *cls.contacts.values())
        cls.added = 0

    @classmethod
    def _show_all(cls, *users):
        for user in users:
            user.with_user(user).write(
                {"linkup_links_visible": True, "linkup_energy_visible": True}
            )

    def _grow(self, count):
        """Give Sam ``count`` more contacts, each like the others: an
        active link paid both ways, its links and its energy shown, a
        link with France, which draws a grey line, and a highlight to
        Sam."""
        users = self.env["res.users"]
        for _index in range(count):
            self.added += 1
            login = f"linkup_nw_perf{self.added}"
            users |= mail_new_test_user(
                self.env,
                login=login,
                name=f"Contact {self.added:02d}",
                email=f"{login}@example.com",
                groups=MEMBER,
                tz="America/Toronto",
            )
        self._age_accounts(users)
        for user in users:
            link = self._activate(self.sam, user)
            self._pay(self.sam, link, 100)
            self._pay(user, link, 100)
            self._activate(user, self.france)
            self._show_all(user)
        self.env["linkup.highlight"].sudo().create(
            [
                {"sender_id": user.id, "recipient_id": self.sam.id}
                for user in users
            ]
        )
        return users

    def _screens(self):
        """The number of queries of each screen of Sam, each read with an
        empty ORM cache after a first reading."""
        env = self.env(user=self.sam)
        Link = env["linkup.link"]
        screens = {
            "reflet_view": env["linkup.reflet"].linkup_reflet_view_info,
            "graph_x1": lambda: Link.get_network_graph(level="x1"),
            "graph_x2": lambda: Link.get_network_graph(level="x2"),
            "graph_x3": lambda: Link.get_network_graph(level="x3"),
            "ranking_partners": lambda: Link.get_ranking(kind="partners"),
            "ranking_active": lambda: Link.get_ranking(
                kind="active", period="30d"
            ),
            "link_card": lambda: Link.get_link_card(self.france.id),
            "my_points": env["linkup.points.ledger"].linkup_my_points,
        }
        counts = {}
        for name, call in screens.items():
            call()
            self.env.flush_all()
            self.env.invalidate_all()
            start = self.env.cr.sql_log_count
            call()
            counts[name] = self.env.cr.sql_log_count - start
        return counts

    def test_required_indexes(self):
        """LU-NF-029: an index covers each pair of columns, in order."""
        self.env.cr.execute(
            "SELECT tablename, indexdef FROM pg_indexes"
            " WHERE tablename IN %s",
            [tuple(INDEXES)],
        )
        found = {
            (
                table,
                tuple(re.search(r"\((.*)\)", indexdef).group(1).split(", ")),
            )
            for table, indexdef in self.env.cr.fetchall()
        }
        for table, column_lists in INDEXES.items():
            for columns in column_lists:
                self.assertIn((table, columns), found, table)

    def test_queries_do_not_grow_with_contacts(self):
        """Each screen of Sam runs as many queries with 9 contacts as with
        21: none of them reads its contacts one by one."""
        self._grow(3)
        before = self._screens()
        self._grow(12)
        after = self._screens()
        self.assertEqual(after, before)
        graph = self._graph()
        self.assertEqual(len(graph["nodes"]), 21)
        self.assertTrue(self._contact_edges(graph))

    def test_query_ceilings(self):
        """Each screen, and the sending of a reflection, stays under its
        ceiling of queries."""
        self._grow(3)
        counts = self._screens()
        contact = self._grow(1)
        draft = self._draft(contact)
        self.env.flush_all()
        self.env.invalidate_all()
        start = self.env.cr.sql_log_count
        draft.with_user(contact).action_send(self.sam.id)
        self.env.flush_all()
        self.env.cr.precommit.run()
        counts["send"] = self.env.cr.sql_log_count - start
        for name, ceiling in CEILINGS.items():
            self.assertLessEqual(counts[name], ceiling, name)
