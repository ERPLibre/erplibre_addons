# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_gamification.tests.common import LinkupPointsCase
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER

# "My partners" of Sam: the points he received with each contact (#113).
PARTNERS = {
    "france": 32450,
    "jacques": 12459,
    "jean": 6909,
    "joanna": 4100,
    "nicolas": 3145,
    "mathieu": 2500,
}
# "The most active": the points each contact received from anybody (#112).
ACTIVE = {
    "france": 87250,
    "joanna": 65539,
    "jean": 31874,
    "jacques": 21765,
    "nicolas": 21764,
    "mathieu": 12647,
}
# A penalty of each contact, left out of the ranking of the most active.
PENALTY = -150


class LinkupNetworkCase(LinkupPointsCase):
    """Sam and his six contacts of the deck, each linked to him: France,
    Jacques, Jean, Joanna, Nicolas and Mathieu. Luce is linked to each of
    the six, never to Sam. The ledger gives Sam the values of "My
    partners", and each contact the values of "The most active" (points
    with Sam and with Luce) and a penalty with Luce. Nobody shows their
    links or their energy yet."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def member(name):
            login = f"linkup_nw_{name.lower()}"
            return mail_new_test_user(
                cls.env,
                login=login,
                name=name,
                email=f"{login}@example.com",
                groups=MEMBER,
                tz="America/Toronto",
            )

        cls.jean = member("Jean")
        cls.joanna = member("Joanna")
        cls.nicolas = member("Nicolas")
        cls.mathieu = member("Mathieu")
        cls._age_accounts(cls.jean | cls.joanna | cls.nicolas | cls.mathieu)
        cls.contacts = {
            "france": cls.france,
            "jacques": cls.jacques,
            "jean": cls.jean,
            "joanna": cls.joanna,
            "nicolas": cls.nicolas,
            "mathieu": cls.mathieu,
        }
        cls.rule_paid = cls.env["linkup.points.rule"].search(
            [("code", "=", "reflect_confirmed")]
        )
        cls.rule_penalty = cls.env["linkup.points.rule"].search(
            [("code", "=", "reflect_rejected")]
        )
        cls._event = 0
        for key, contact in cls.contacts.items():
            with_sam = cls._activate(cls.sam, contact)
            with_luce = cls._activate(contact, cls.luce)
            cls._pay(cls.sam, with_sam, PARTNERS[key])
            cls._pay(contact, with_sam, PARTNERS[key])
            cls._pay(contact, with_luce, ACTIVE[key] - PARTNERS[key])
            cls._pay(contact, with_luce, PENALTY, cls.rule_penalty)
        cls.Link = cls.env["linkup.link"]

    @classmethod
    def _activate(cls, user1, user2):
        """The ``active`` link of two members, created if needed."""
        link = cls.env["linkup.link"]._get_or_create(user1, user2)
        link._linkup_activate()
        return link

    @classmethod
    def _pay(cls, user, link, points, rule=None, days=0):
        """Write one ledger line of ``points`` for ``user`` in the pair of
        ``link``, ``days`` days ago, then credit its karma and the energy
        of the link, as an event does."""
        cls._event += 1
        Ledger = cls.env["linkup.points.ledger"].sudo()
        line = Ledger._linkup_insert(
            {
                "user_id": user.id,
                "partner_user_id": link._linkup_other_user(user).id,
                "rule_id": (rule or cls.rule_paid).id,
                "points": points,
                "capped": False,
                "cap_reason": None,
                "date": fields.Datetime.now() - timedelta(days=days),
                "channel_id": None,
                "message_id": None,
                "reflet_id": None,
                "link_id": link.id,
                "event_key": f"test:network:{cls._event}",
                "resets_decay": False,
                "decay_day": None,
            }
        )
        line._linkup_credit_karma(link)
        line._linkup_add_energy()
        return line

    def _show(self, *users, links=None, energy=None):
        """Each user writes their own network preferences."""
        vals = {}
        if links is not None:
            vals["linkup_links_visible"] = links
        if energy is not None:
            vals["linkup_energy_visible"] = energy
        for user in users:
            user.with_user(user).write(vals)

    def _graph(self, user=None, level="x1", limit=50):
        return self.Link.with_user(user or self.sam).get_network_graph(
            level=level, limit=limit
        )

    def _ranking(self, kind, user=None, period="all"):
        return self.Link.with_user(user or self.sam).get_ranking(
            kind=kind, period=period
        )

    def _card(self, other, user=None, **kwargs):
        return self.Link.with_user(user or self.sam).get_link_card(
            other.id, **kwargs
        )

    @staticmethod
    def _names(rows):
        return [row["name"] for row in rows]

    @staticmethod
    def _contact_edges(graph):
        return {
            frozenset((edge["source"], edge["target"]))
            for edge in graph["edges"]
            if edge["kind"] == "contacts"
        }
