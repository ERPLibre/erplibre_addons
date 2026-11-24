# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The card of a link: LU-F-075, Q-26, and what it never tells."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.tests import tagged

from .common import LinkupNetworkCase


@tagged("post_install", "-at_install")
class TestLinkupNetworkCard(LinkupNetworkCase):
    def test_card_of_france(self):
        """LU-F-075 CA1: the card of the link Sam-France gives 32450, the
        first link date and the conversation of the pair, for the call,
        the video call and the conversation."""
        reflet = self._confirmed_by(self.sam, self.france)
        card = self._card(self.france)
        self.assertTrue(card["available"])
        self.assertEqual(card["user_id"], self.france.id)
        self.assertEqual(card["partner_id"], self.france.partner_id.id)
        self.assertEqual(card["name"], "France")
        self.assertEqual(
            card["energy"],
            self.Link._get_between(self.sam, self.france)._linkup_energy_for(
                self.sam
            ),
        )
        self.assertTrue(card["first_link_date"])
        self.assertEqual(card["channel_id"], reflet.channel_id.id)
        self.assertFalse(card["highlight_sent"])
        self.env["linkup.highlight"].with_user(self.sam).action_send(
            self.france.id
        )
        self.assertTrue(self._card(self.france)["highlight_sent"])
        self.assertTrue(
            self._card(self.sam, self.france)["highlight_received"]
        )

    def test_card_reads_the_reader_side(self):
        """LU-F-071 RM2: each member reads the energy they received."""
        link = self.Link._get_between(self.sam, self.france)
        self._pay(self.france, link, 1000)
        self.assertEqual(self._card(self.france)["energy"], 32450)
        self.assertEqual(self._card(self.sam, self.france)["energy"], 33450)

    def test_thread_shown_to_both(self):
        """Q-26: the thread alternates the posts of the two members,
        oldest first, the reflections with their cards; with
        ``reflets_only``, only the reflections. A withdrawn reflection and
        a draft have no entry, and the hidden theme of a precision is not
        in the cards."""
        reflet = self._confirmed_by(self.sam, self.france)
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Je parlais plutôt de mon but.", [self.goals.id]
            )
        )
        self._post(reflet.channel_id, self.sam, "On en reparle demain ?")
        withdrawn = self._sent_to(self.sam, self.france)
        withdrawn.with_user(self.sam).action_withdraw()
        self._draft(self.sam)
        card = self._card(self.france)
        entries = card["entries"]
        self.assertEqual(
            [entry["reflet_id"] for entry in entries],
            [reflet.id, precision.id, False],
        )
        self.assertEqual(
            [entry["mine"] for entry in entries], [True, False, True]
        )
        self.assertEqual(entries[-1]["text"], "On en reparle demain ?")
        france_card = self._card(self.sam, self.france)
        self.assertEqual(
            [entry["message_id"] for entry in france_card["entries"]],
            [entry["message_id"] for entry in entries],
        )
        self.assertEqual(
            [entry["mine"] for entry in france_card["entries"]],
            [False, True, False],
        )
        cards = {
            values["id"]: values for values in card["store"]["linkup.reflet"]
        }
        self.assertEqual(set(cards), {reflet.id, precision.id})
        self.assertNotIn("revealed_category_ids", cards[precision.id])
        only = self._card(self.france, reflets_only=True)["entries"]
        self.assertEqual(
            [entry["reflet_id"] for entry in only], [reflet.id, precision.id]
        )

    def test_unavailable_reads_the_same(self):
        """A stranger, a pending link, a block either way, an archived
        account and a wrong id give the same answer, so the card tells
        neither a block nor a person outside the links."""
        unavailable = {"available": False}
        thomas = mail_new_test_user(
            self.env,
            login="linkup_nw_card_thomas",
            name="Thomas",
            email="linkup_nw_card_thomas@example.com",
            groups=MEMBER,
        )
        self.Link._get_or_create(self.sam, thomas)
        self.assertEqual(self._card(thomas), unavailable)
        self.assertEqual(self._card(self.luce), unavailable)
        self.assertEqual(self._card(self.sam), unavailable)
        self.assertEqual(
            self.Link.with_user(self.sam).get_link_card("abc"), unavailable
        )
        self.env["linkup.block"].with_user(self.joanna).action_block(
            user_id=self.sam.id
        )
        self.assertEqual(self._card(self.joanna), unavailable)
        self.assertEqual(self._card(self.sam, self.joanna), unavailable)
        self.mathieu.active = False
        self.assertEqual(self._card(self.mathieu), unavailable)
