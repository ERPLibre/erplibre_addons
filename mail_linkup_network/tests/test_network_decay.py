# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The decay of the energy (Q-41): each line of the ledger weighs half as
much after ``linkup.energy_half_life_days`` days (90), in the energy of
the member, of a link, in the rankings and in X3. The ledger and the karma
never change."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.tests import tagged

from .common import PARTNERS, LinkupNetworkCase

PARAM = "linkup.energy_half_life_days"
POINTS = 1000


@tagged("post_install", "-at_install")
class TestLinkupNetworkDecay(LinkupNetworkCase):
    @classmethod
    def setUpClass(cls):
        """Sam receives 1000 points with each of three new contacts, today,
        90 days ago and 180 days ago; each contact receives the same."""
        super().setUpClass()
        cls.aged = {}
        for days in (0, 90, 180):
            login = f"linkup_nw_decay{days}"
            contact = mail_new_test_user(
                cls.env,
                login=login,
                name=f"Decay {days:03d}",
                email=f"{login}@example.com",
                groups=MEMBER,
                tz="America/Toronto",
            )
            cls._age_accounts(contact)
            link = cls._activate(cls.sam, contact)
            cls._pay(cls.sam, link, POINTS, days=days)
            cls._pay(contact, link, POINTS, days=days)
            cls.aged[days] = contact

    def _set(self, value):
        self.env["ir.config_parameter"].sudo().set_param(PARAM, value)

    def _nodes(self, level="x1"):
        return {
            node["user_id"]: node["energy"]
            for node in self._graph(level=level)["nodes"]
        }

    def _partners(self):
        return {
            row["user_id"]: row["value"]
            for row in self._ranking("partners")["rows"]
        }

    def _energies(self):
        """The energy of the link with each aged contact, as the graph,
        "My partners" and the card give it."""
        nodes = self._nodes()
        partners = self._partners()
        result = {}
        for days, contact in self.aged.items():
            card = self._card(contact)["energy"]
            self.assertEqual(nodes[contact.id], card)
            self.assertEqual(partners[contact.id], card)
            result[days] = card
        return result

    def test_link_energy_halves(self):
        """A line counts whole its first day, half after 90 days, a
        quarter after 180, in the graph, "My partners" and the card."""
        self.assertEqual(self._energies(), {0: 1000, 90: 500, 180: 250})
        # The lines of the deck, paid today, keep their full value.
        self.assertEqual(self._card(self.france)["energy"], PARTNERS["france"])

    def test_network_energy_of_the_member(self):
        """The energy of the member is their karma, less what the decay
        took from their lines; the karma and the ledger keep every
        point."""
        karma = sum(PARTNERS.values()) + 3 * POINTS
        self.assertEqual(self.sam.karma, karma)
        decayed = karma - (POINTS - 500) - (POINTS - 250)
        self.assertEqual(self._graph()["me"]["energy"], decayed)
        self.assertEqual(self.sam._linkup_network_energy(), decayed)
        lines = self.Ledger.sudo().search([("user_id", "=", self.sam.id)])
        self.assertEqual(sum(lines.mapped("points")), karma)
        self.assertEqual(self.sam.karma, karma)

    def test_x3_follows_the_decayed_energy(self):
        """X3 keeps the two strongest partners by their decayed energy: an
        old link worth more than Jacques in points stays out of it."""
        old = self.aged[180]
        link = self.Link._get_between(self.sam, old)
        self._pay(self.sam, link, 40000, days=180)
        self.assertEqual(
            set(self._nodes("x3")), {self.france.id, self.jacques.id}
        )
        self._set("0")
        self.assertEqual(set(self._nodes("x3")), {self.france.id, old.id})

    def test_most_active_decays(self):
        """ "The most active" weighs the points of each contact by their
        age, then rounds to the hundred."""
        old = self.aged[180]
        self._show(old, energy=True)
        link = self.Link._get_between(self.sam, old)
        self._pay(old, link, 4000, days=180)
        rows = self._ranking("active")["rows"]
        value = {row["user_id"]: row["value"] for row in rows}[old.id]
        self.assertEqual(value, 1300)

    def test_half_life_is_a_setting(self):
        """With a half-life of 30 days, a line of 90 days counts an
        eighth."""
        self._set("30")
        self.assertEqual(self._energies(), {0: 1000, 90: 125, 180: 16})

    def test_zero_turns_the_decay_off(self):
        """0, or a negative value, turns the decay off: the energy is the
        karma and the sums kept on the links."""
        for value in ("0", "-5"):
            self._set(value)
            self.assertEqual(self._energies(), {0: 1000, 90: 1000, 180: 1000})
            self.assertEqual(self._graph()["me"]["energy"], self.sam.karma)

    def test_settings_keep_the_default_of_an_invalid_value(self):
        """The settings show the 90 days the server applies for an invalid
        value, and a save keeps them, rather than 0, which turns the decay
        off."""
        self._set("ninety")
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.linkup_energy_half_life_days, 90)
        settings.set_values()
        self.assertEqual(
            self.env["linkup.points.ledger"]._linkup_half_life_days(), 90
        )
        self._set("0")
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.linkup_energy_half_life_days, 0)

    def test_unset_or_invalid_takes_the_default(self):
        """An unset or invalid half-life takes the 90 days of the
        decision."""
        for value in (False, "", "ninety"):
            self._set(value)
            self.assertEqual(self._energies(), {0: 1000, 90: 500, 180: 250})
