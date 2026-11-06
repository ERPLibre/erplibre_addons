# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The rankings of the Network view: LU-F-071 CA2, LU-F-073, LU-F-074
(T-13)."""

from odoo.tests import tagged

from .common import ACTIVE, PARTNERS, LinkupNetworkCase


@tagged("post_install", "-at_install")
class TestLinkupNetworkRanking(LinkupNetworkCase):
    def test_my_partners(self):
        """LU-F-074 CA1: "My partners" gives the values of #113, in order,
        and the card of the link Sam-France shows the same 32450."""
        rows = self._ranking("partners")["rows"]
        self.assertEqual(
            [(row["name"], row["value"]) for row in rows],
            [
                ("France", 32450),
                ("Jacques", 12459),
                ("Jean", 6909),
                ("Joanna", 4100),
                ("Nicolas", 3145),
                ("Mathieu", 2500),
            ],
        )
        self.assertEqual([row["position"] for row in rows], [1, 2, 3, 4, 5, 6])
        self.assertEqual(self._card(self.france)["energy"], 32450)

    def test_card_and_ranking_agree(self):
        """LU-F-071 CA2: after real events of the pair, the card of the
        link and "My partners" still give the same value for France, and
        France reads her own side."""
        reflet = self._confirmed_by(self.sam, self.france)
        self._exact(reflet, self.france)
        rows = self._ranking("partners")["rows"]
        value = {row["user_id"]: row["value"] for row in rows}[self.france.id]
        self.assertGreater(value, PARTNERS["france"])
        self.assertEqual(self._card(self.france)["energy"], value)
        france_rows = self._ranking("partners", self.france)["rows"]
        france_value = {row["user_id"]: row["value"] for row in france_rows}
        self.assertEqual(
            self._card(self.sam, self.france)["energy"],
            france_value[self.sam.id],
        )

    def test_most_active(self):
        """LU-F-073 CA1: the six contacts show their energy; the order is
        France, Joanna, Jean, Jacques, Nicolas, Mathieu, each value rounded
        to the hundred, without the penalty."""
        self._show(*self.contacts.values(), energy=True)
        rows = self._ranking("active")["rows"]
        self.assertEqual(
            self._names(rows),
            ["France", "Joanna", "Jean", "Jacques", "Nicolas", "Mathieu"],
        )
        self.assertEqual(
            [row["value"] for row in rows],
            [87300, 65500, 31900, 21800, 21800, 12600],
        )
        for row in rows:
            self.assertEqual(row["value"] % 100, 0)
        # The karma of France holds the penalty; the ranking does not.
        self.assertEqual(self.france.karma, ACTIVE["france"] - 150)

    def test_most_active_needs_consent(self):
        """LU-F-073 CA2, LU-NF-012: nobody shows their energy by default;
        Jean, who does not, is absent while the others are there."""
        self.assertEqual(self._ranking("active")["rows"], [])
        others = [c for key, c in self.contacts.items() if key != "jean"]
        self._show(*others, energy=True)
        names = self._names(self._ranking("active")["rows"])
        self.assertNotIn("Jean", names)
        self.assertEqual(len(names), 5)

    def test_never_the_community(self):
        """LU-NF-032: Luce shows her energy but is not linked to Sam: she
        never appears in his rankings; a blocked contact neither."""
        self._show(self.luce, *self.contacts.values(), energy=True)
        self.env["linkup.block"].with_user(self.joanna).action_block(
            user_id=self.sam.id
        )
        for kind in ("active", "partners"):
            ids = {row["user_id"] for row in self._ranking(kind)["rows"]}
            self.assertNotIn(self.luce.id, ids)
            self.assertNotIn(self.joanna.id, ids)
            self.assertEqual(len(ids), 5)
        # Luce ranks the six contacts, her own links, and never Sam.
        luce_ids = {
            row["user_id"]
            for row in self._ranking("active", self.luce)["rows"]
        }
        self.assertNotIn(self.sam.id, luce_ids)

    def test_period(self):
        """The period of 30 days counts the lines of the last 30 days."""
        link = self.Link._get_between(self.sam, self.jean)
        self._pay(self.sam, link, 50000, days=45)
        self._pay(self.jean, link, 50000, days=45)
        self._show(self.jean, energy=True)
        partners = {
            row["name"]: row["value"]
            for row in self._ranking("partners", period="30d")["rows"]
        }
        self.assertEqual(partners["Jean"], PARTNERS["jean"])
        all_time = {
            row["name"]: row["value"]
            for row in self._ranking("partners")["rows"]
        }
        self.assertEqual(all_time["Jean"], PARTNERS["jean"] + 50000)
        self.assertEqual(
            self._names(self._ranking("partners")["rows"])[0], "Jean"
        )
        active = self._ranking("active", period="30d")["rows"]
        self.assertEqual(active[0]["value"], 31900)

    def test_validation(self):
        with self.assertLinkupCode("linkup.validation", "kind"):
            self._ranking("community")
        with self.assertLinkupCode("linkup.validation", "period"):
            self._ranking("active", period="7d")
