# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from freezegun import freeze_time
from odoo import fields
from odoo.tests import TransactionCase, tagged

from ..models.linkup_points_ledger import HALF_LIFE_PARAM

DEMO = "mail_linkup_reflet.demo_"


@tagged("post_install", "-at_install")
class TestLinkupNetworkDemo(TransactionCase):
    """The demonstration gives the Network view of Sam something to show,
    without changing the points of the earlier demonstrations."""

    def setUp(self):
        super().setUp()
        self.sam = self.env.ref(f"{DEMO}user_sam", raise_if_not_found=False)
        if not self.sam:
            self.skipTest("The demonstration data is not loaded.")
        # The lines of the demonstration are dated at its installation: the
        # decay off, the energies below hold whatever the age of the
        # database; tests/test_network_decay.py checks the decay.
        self.env["ir.config_parameter"].sudo().set_param(HALF_LIFE_PARAM, "0")

    def _user(self, name):
        return self.env.ref(f"{DEMO}user_{name}")

    def test_demo_network(self):
        """Sam sees his six links; X1 draws the grey lines of the pairs
        that show their links, never France-Jacques; his six contacts
        rank by their energy."""
        Link = self.env["linkup.link"].with_user(self.sam)
        graph = Link.get_network_graph("x1")
        self.assertEqual(
            {node["name"] for node in graph["nodes"]},
            {"France", "Jacques", "Jean", "Joanna", "Nicolas", "Mathieu"},
        )
        grey = {
            frozenset((edge["source"], edge["target"]))
            for edge in graph["edges"]
            if edge["kind"] == "contacts"
        }
        pair = frozenset
        self.assertEqual(
            grey,
            {
                pair((self._user("france").id, self._user("joanna").id)),
                pair((self._user("jean").id, self._user("nicolas").id)),
                pair((self._user("joanna").id, self._user("mathieu").id)),
            },
        )
        self.assertEqual(graph["me"]["energy"], 2700)
        self.assertEqual(len(Link.get_ranking("active")["rows"]), 6)
        partners = Link.get_ranking("partners")["rows"]
        self.assertEqual(partners[0]["name"], "France")
        self.assertEqual(partners[0]["value"], 1950)
        self.assertFalse(self.sam.sudo().linkup_energy_visible)

    def test_demo_energy_without_decay(self):
        """The energy of the demonstration does not depend on the age of
        its lines once the decay is off."""
        Link = self.env["linkup.link"].with_user(self.sam)
        with freeze_time(fields.Datetime.now() + timedelta(days=30)):
            self.assertEqual(
                Link.get_network_graph("x1")["me"]["energy"], 2700
            )
