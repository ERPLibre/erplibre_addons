# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The quick replies to a request for action: LU-F-046."""

from odoo.addons.mail_linkup_gamification.tests.common import LinkupPointsCase
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import html2plaintext


@tagged("post_install", "-at_install")
class TestLinkupActionRequest(LinkupPointsCase):
    def _request(self):
        """A confirmed reflection of Sam to France whose category is
        Action."""
        reflet = self._sent_to(
            self.sam, self.france, category_id=self.action_cat.id
        )
        reflet.with_user(self.france).action_confirm()
        return reflet

    def _snapshot(self):
        users = self.sam | self.france
        users.invalidate_recordset(["karma"])
        return (
            self.Ledger.sudo().search_count([("user_id", "in", users.ids)]),
            self.sam.karma,
            self.france.karma,
        )

    def test_not_for_now(self):
        """LU-F-046 CA1: France answers "Not for now": the answer is posted
        in the conversation, and nobody gains or loses points."""
        reflet = self._request()
        before = self._snapshot()
        self._bus_reset()
        result = reflet.with_user(self.france).action_answer_action_request(
            "not_now"
        )
        message = self.env["mail.message"].browse(result["message_id"])
        self.assertEqual(message.model, "discuss.channel")
        self.assertEqual(message.res_id, reflet.channel_id.id)
        self.assertEqual(message.author_id, self.france.partner_id)
        self.assertEqual(message.message_type, "comment")
        self.assertEqual(html2plaintext(message.body).strip(), "Not for now.")
        self.assertEqual(reflet.linkup_action_reply, "not_now")
        self.assertEqual(self._snapshot(), before)
        cards = []
        for target, _kind, payload in self._bus_sent():
            if target == reflet.channel_id and isinstance(
                payload.get("linkup.reflet"), list
            ):
                cards += payload["linkup.reflet"]
        self.assertIn("not_now", [card.get("action_reply") for card in cards])

    def test_agree_once(self):
        """ "Agreed" is posted once; a second reply is refused."""
        reflet = self._request()
        reflet.with_user(self.france).action_answer_action_request("agree")
        self.assertEqual(reflet.linkup_action_reply, "agree")
        with self.assertLinkupCode("linkup.already_answered"):
            reflet.with_user(self.france).action_answer_action_request(
                "not_now"
            )

    def test_refusals(self):
        """Only the recipient answers, once the reflection is confirmed,
        and only a request for action; an unknown reply is refused."""
        sent = self._sent_to(
            self.sam, self.france, category_id=self.action_cat.id
        )
        with self.assertLinkupCode("linkup.validation", "state"):
            sent.with_user(self.france).action_answer_action_request("agree")
        sent.with_user(self.france).action_confirm()
        with self.assertRaises(AccessError):
            sent.with_user(self.sam).action_answer_action_request("agree")
        with self.assertRaises(AccessError):
            sent.with_user(self.jacques).action_answer_action_request("agree")
        with self.assertLinkupCode("linkup.validation", "reply"):
            sent.with_user(self.france).action_answer_action_request("other")
        needs = self._confirmed_by(self.sam, self.france)
        with self.assertLinkupCode("linkup.validation", "category_id"):
            needs.with_user(self.france).action_answer_action_request("agree")

    def test_no_round_of_free_text(self):
        """RM2: the quick reply closes no round of free text: Sam's text
        then France's reply pay no ``virtual_round``."""
        reflet = self._request()
        self._post(reflet.channel_id, self.sam, "Tu pourrais m'aider samedi ?")
        reflet.with_user(self.france).action_answer_action_request("agree")
        self.assertFalse(self._lines(self.sam, "virtual_round"))
        self.assertFalse(self._lines(self.france, "virtual_round"))
        self.assertBalanced(self.sam, self.france)

    def test_revealed_theme(self):
        """A precision hiding the Action theme is a request for action
        once its guess is made, for its recipient."""
        reflet = self._confirmed_by(self.sam, self.france)
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "J'aimerais qu'on se voie plus souvent.",
                [self.action_cat.id],
            )
        )
        with self.assertLinkupCode("linkup.validation", "category_id"):
            precision.with_user(self.sam).action_answer_action_request("agree")
        precision.with_user(self.sam).action_guess(self.needs.id)
        precision.with_user(self.sam).action_answer_action_request("agree")
        self.assertEqual(precision.linkup_action_reply, "agree")

    def test_blocked_pair(self):
        """A block of the pair refuses the reply as an unavailable
        conversation."""
        reflet = self._request()
        self.env["linkup.block"].with_user(self.sam).action_block(
            user_id=self.france.id
        )
        with self.assertLinkupCode("linkup.unavailable"):
            reflet.with_user(self.france).action_answer_action_request("agree")
