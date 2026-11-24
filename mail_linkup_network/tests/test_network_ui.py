# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Web client of the Network view: the tour of the graph, its densities and
the card of a link (LU-F-070 to LU-F-076), and the Hoot unit tests of the
module (§12.1)."""

from odoo import fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import (
    MEMBER,
    DarkThemeTourMixin,
)
from odoo.addons.web.tests import test_js
from odoo.tests import HttpCase, tagged

# Suite of the Hoot tests of the module, as the Hoot runner names it.
HOOT_SUITE = "@mail_linkup_network"


@tagged("post_install", "-at_install")
class TestLinkupNetworkUi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def member(name):
            login = f"linkup_nw_ui_{name.lower()}"
            return mail_new_test_user(
                cls.env,
                login=login,
                password=login,
                name=name,
                email=f"{login}@example.com",
                groups=MEMBER,
                tz="America/Toronto",
            )

        cls.sam = member("Sam")
        cls.france = member("France")
        cls.jacques = member("Jacques")
        cls.jean = member("Jean")
        members = cls.sam | cls.france | cls.jacques | cls.jean
        # The first-use tour would cover the screens the tour uses.
        members.write({"linkup_tour_done": True})
        Link = cls.env["linkup.link"]
        # The points Sam received with each contact, as in "My partners"
        # (#113): the card of the link reads the same value.
        rule = cls.env["linkup.points.rule"].search(
            [("code", "=", "reflect_confirmed")]
        )
        Ledger = cls.env["linkup.points.ledger"].sudo()
        for contact, points in (
            (cls.france, 32450),
            (cls.jacques, 12459),
            (cls.jean, 6909),
        ):
            link = Link._get_or_create(cls.sam, contact)
            link._linkup_activate()
            line = Ledger._linkup_insert(
                {
                    "user_id": cls.sam.id,
                    "partner_user_id": contact.id,
                    "rule_id": rule.id,
                    "points": points,
                    "capped": False,
                    "cap_reason": None,
                    "date": fields.Datetime.now(),
                    "channel_id": None,
                    "message_id": None,
                    "reflet_id": None,
                    "link_id": link.id,
                    "event_key": f"test:network_ui:{contact.id}",
                    "resets_decay": False,
                    "decay_day": None,
                }
            )
            line._linkup_credit_karma(link)
            line._linkup_add_energy()
        # Jacques and Jean are linked and both show their links: X1 draws
        # their grey line.
        Link._get_or_create(cls.jacques, cls.jean)._linkup_activate()
        (cls.jacques | cls.jean).sudo().write({"linkup_links_visible": True})

    def test_network_tour(self):
        """T-36: Sam opens the Network view from Discuss, changes its
        density, opens the card of a link by its line, by its node and by
        the ranking, closes it each way, and goes back to Discuss."""
        graph = self.env["linkup.link"].with_user(self.sam).get_network_graph()
        self.assertEqual(len(graph["nodes"]), 3)
        self.assertEqual(graph["nodes"][0]["energy"], 32450)
        self.start_tour(
            "/odoo/discuss", "linkup_network_tour", login=self.sam.login
        )


@tagged("post_install", "-at_install")
class TestLinkupNetworkUiDark(DarkThemeTourMixin, TestLinkupNetworkUi):
    """The tours of TestLinkupNetworkUi in the dark theme (LU-NF-054, T-56)."""


@tagged("post_install", "-at_install")
class TestLinkupNetworkHoot(HttpCase):
    def test_hoot_suite(self):
        """The Hoot tests of the module, in a desktop browser."""
        suite_id = test_js.HOOTCommon._generate_hash(self, HOOT_SUITE)
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000"
            f"&id={suite_id}",
            "",
            "",
            login="admin",
            timeout=1800,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=test_js.unit_test_error_checker,
        )
