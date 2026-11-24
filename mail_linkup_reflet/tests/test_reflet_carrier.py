# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Carrier messages, Store and bus of the reflections (LU-F-016 CA1,
LU-F-019 CA1, LU-F-021 RM3, LU-F-024 CA1, LU-F-025 RM1, LU-F-031 RM5 and
CA2, LU-F-033 RM3, §9.5, RS-1, RS-3; T-03, T-06).
"""

import json
from datetime import timedelta

from odoo import fields
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import html2plaintext

from ..authorization import current_post, linkup_post
from .common import LinkupRefletCase

NEW_MESSAGE = "discuss.channel/new_message"
INSERT = "mail.record/insert"


def store_of(kind, payload):
    """The Store data of a bus payload."""
    return payload["data"] if kind == NEW_MESSAGE else payload


def same_target(target, record):
    """Tell whether a bus target is ``record`` itself, not a subchannel."""
    return not isinstance(target, tuple) and target == record


class LinkupCarrierMixin:
    def _cards(self, sent, record=None):
        """The cards of reflections in the notifications, merged by id;
        only those sent to ``record`` when it is given."""
        cards = {}
        for target, kind, payload in sent:
            if record is not None and not same_target(target, record):
                continue
            for values in store_of(kind, payload).get("linkup.reflet", []):
                cards.setdefault(values["id"], {}).update(values)
        return cards

    def _precision(self, reflet, codes=("goals", "emotions")):
        themes = self.env["linkup.category"].search([("code", "in", codes)])
        return self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Je voudrais trouver quelqu'un pour le potager.",
                themes.sorted(lambda c: codes.index(c.code)).ids,
            )
        )

    def assertNoHiddenTheme(self, data, themes):
        """Neither the hidden themes nor their codes are in ``data``."""
        text = json.dumps(data)
        self.assertNotIn("revealed_category_ids", text)
        self.assertNotIn("primary_category_id", text)
        for theme in themes:
            self.assertNotIn(f'"{theme.code}"', text)
            self.assertNotIn(theme.name, text)
        for category in data.get("linkup.category", []):
            self.assertNotIn(category["id"], themes.ids)


@tagged("post_install", "-at_install")
class TestLinkupRefletCarrier(LinkupCarrierMixin, LinkupRefletCase):
    # Sending (T-03)

    def test_send_posts_carrier_message(self):
        """Sending posts a comment in the direct conversation, linked to
        the reflection, and broadcasts its card."""
        self._bus_reset()
        reflet = self._sent()
        message = reflet.message_id
        channel = reflet.channel_id
        self.assertTrue(message)
        self.assertEqual(channel.channel_type, "chat")
        self.assertEqual(
            channel.channel_member_ids.partner_id,
            (self.sam | self.france).partner_id,
        )
        self.assertEqual(reflet.link_id.channel_id, channel)
        self.assertEqual(
            (message.model, message.res_id, message.message_type),
            ("discuss.channel", channel.id, "comment"),
        )
        self.assertEqual(message.subtype_id, self.env.ref("mail.mt_comment"))
        self.assertEqual(message.author_id, self.sam.partner_id)
        self.assertEqual(message.linkup_reflet_id, reflet)
        self.assertFalse(message._is_empty())
        # The body is a neutral sentence: no text of the reflection.
        body = html2plaintext(message.body)
        self.assertEqual(body, "Sam sent you a reflection.")
        sent = self._bus_sent()
        broadcasts = [
            (target, payload)
            for target, kind, payload in sent
            if kind == NEW_MESSAGE
        ]
        self.assertEqual(len(broadcasts), 1)
        self.assertTrue(same_target(broadcasts[0][0], channel))
        data = broadcasts[0][1]["data"]
        self.assertEqual(
            [m["linkup_reflet_id"] for m in data["mail.message"]], reflet.ids
        )
        card = self._cards(sent, channel)[reflet.id]
        self.assertEqual(
            {key: card[key] for key in ("kind", "state", "category_id")},
            {"kind": "initial", "state": "sent", "category_id": self.needs.id},
        )
        self.assertEqual(
            card["author"], {"id": self.sam.partner_id.id, "type": "partner"}
        )
        self.assertEqual(
            card["recipient"],
            {"id": self.france.partner_id.id, "type": "partner"},
        )
        self.assertEqual(card["you_said"], reflet.you_said)
        self.assertEqual(card["message_id"], message.id)
        self.assertFalse(card["holds_turn"])
        self.assertNotIn("recipient_ignored", card)
        self.assertEqual(
            data["linkup.category"], [{"id": self.needs.id, "code": "needs"}]
        )
        # A second reflection of the pair goes to the same conversation.
        again = self._sent(category_id=self.goals.id)
        self.assertEqual(again.channel_id, channel)
        self.assertNotEqual(again.message_id, message)

    def test_carrier_in_recipient_language(self):
        """The neutral sentence is written in the recipient's language."""
        self.env["res.lang"]._activate_lang("fr_CA")
        self.france.lang = "fr_CA"
        reflet = self._sent()
        self.assertEqual(
            html2plaintext(reflet.message_id.body),
            "Sam t'a envoyé un reflet.",
        )

    def test_server_contact_is_narrow(self):
        """The contact opened by the server covers the author of the
        reflection being posted, and the partners of its two parties."""
        reflet = self._sent()
        Sam = self.env["discuss.channel"].with_user(self.sam)
        Jacques = self.env["discuss.channel"].with_user(self.jacques)
        with linkup_post(reflet):
            self.assertTrue(current_post(Sam.env))
            self.assertIsNone(current_post(Jacques.env))
            with self.assertRaises(AccessError):
                Sam.channel_get([self.luce.partner_id.id])
            with self.assertRaises(AccessError):
                Jacques.channel_get([self.luce.partner_id.id])
        self.assertIsNone(current_post(Sam.env))

    def test_each_turn_posts_its_carrier(self):
        """Each child reflection has its own carrier, by its author, in
        the conversation of the pair."""
        reflet = self._confirmed()
        exact = self._child(
            reflet.with_user(self.france).action_answer_exact("Merci !")
        )
        close = self._child(exact.with_user(self.sam).action_close())
        channel = reflet.channel_id
        for child, author, text in (
            (exact, self.france, "France answered: that's exactly it!"),
            (close, self.sam, "Sam closed the exchange."),
        ):
            self.assertEqual(child.channel_id, channel)
            self.assertEqual(child.message_id.res_id, channel.id)
            self.assertEqual(child.message_id.author_id, author.partner_id)
            self.assertEqual(child.message_id.linkup_reflet_id, child)
            self.assertEqual(html2plaintext(child.message_id.body), text)
        self.assertNotIn("Merci", exact.message_id.body)

    # Transitions on the bus

    def test_transitions_reach_the_conversation(self):
        """Each transition sends the updated card to the conversation."""
        reflet = self._sent()
        channel = reflet.channel_id
        self._bus_reset()
        reflet.with_user(self.france).action_mark_read()
        card = self._cards(self._bus_sent(), channel)[reflet.id]
        self.assertTrue(card["read_date"])
        self._bus_reset()
        reflet.with_user(self.france).action_confirm()
        card = self._cards(self._bus_sent(), channel)[reflet.id]
        self.assertEqual(
            (card["state"], card["holds_turn"]), ("confirmed", True)
        )
        self._bus_reset()
        exact = self._child(
            reflet.with_user(self.france).action_answer_exact()
        )
        cards = self._cards(self._bus_sent(), channel)
        self.assertEqual(cards[reflet.id]["response_state"], "exact")
        self.assertFalse(cards[reflet.id]["holds_turn"])
        self.assertEqual(cards[exact.id]["kind"], "answer_exact")
        self.assertTrue(cards[exact.id]["holds_turn"])
        self.assertEqual(cards[exact.id]["parent_id"], reflet.id)

    def test_reject_and_inaccurate_reach_the_conversation(self):
        """Rejection and correction reach both parties."""
        rejected = self._sent()
        self._bus_reset()
        rejected.with_user(self.france).action_reject()
        card = self._cards(self._bus_sent(), rejected.channel_id)[rejected.id]
        self.assertEqual(card["state"], "rejected")
        inaccurate = self._sent()
        self._bus_reset()
        inaccurate.with_user(self.france).action_mark_inaccurate(
            "Je parlais du potager du quartier."
        )
        card = self._cards(self._bus_sent(), inaccurate.channel_id)[
            inaccurate.id
        ]
        self.assertEqual(card["state"], "inaccurate")
        self.assertEqual(
            card["body_text"], "Je parlais du potager du quartier."
        )

    def test_withdraw_replaces_the_carrier(self):
        """A withdrawn reflection leaves its texts nowhere (LU-F-019)."""
        reflet = self._sent()
        channel = reflet.channel_id
        message = reflet.message_id
        self._bus_reset()
        reflet.with_user(self.sam).action_withdraw()
        self.assertEqual(html2plaintext(message.body), "Reflection withdrawn.")
        sent = self._bus_sent()
        bodies = [
            values["body"]
            for target, kind, payload in sent
            if same_target(target, channel)
            for values in store_of(kind, payload).get("mail.message", [])
            if values["id"] == message.id
        ]
        self.assertEqual(len(bodies), 1)
        self.assertIn("Reflection withdrawn.", bodies[0])
        card = self._cards(sent, channel)[reflet.id]
        self.assertEqual(card["state"], "withdrawn")
        for key in ("you_said", "understood", "category_id"):
            self.assertFalse(card[key])
        data = Store(
            message.with_user(self.france), for_current_user=True
        ).get_result()
        self.assertNotIn("jardin", json.dumps(data))

    def test_ignore_reaches_the_recipient_only(self):
        """Ignoring notifies the recipient alone: the author notices
        nothing (LU-F-025 RM1)."""
        reflet = self._sent()
        self._bus_reset()
        reflet.with_user(self.france).action_ignore()
        sent = self._bus_sent()
        self.assertEqual(len(sent), 1)
        target, kind, payload = sent[0]
        self.assertTrue(same_target(target, self.france.partner_id))
        self.assertEqual(
            payload["linkup.reflet"],
            [{"id": reflet.id, "recipient_ignored": True}],
        )
        message = reflet.message_id
        as_sam = Store(message.with_user(self.sam), for_current_user=True)
        self.assertNotIn("recipient_ignored", json.dumps(as_sam.get_result()))
        as_france = Store(
            message.with_user(self.france), for_current_user=True
        ).get_result()
        self.assertTrue(
            any(
                card.get("recipient_ignored")
                for card in as_france["linkup.reflet"]
            )
        )

    def test_expiry_reaches_the_conversation(self):
        """An expired reflection shows as expired to both (LU-F-024)."""
        reflet = self._sent()
        reflet.sudo().sent_date = fields.Datetime.now() - timedelta(days=31)
        self._bus_reset()
        self.Reflet._cron_expire_reflets()
        card = self._cards(self._bus_sent(), reflet.channel_id)[reflet.id]
        self.assertEqual(card["state"], "expired")

    # Hidden themes (T-06, RS-1, RS-3)

    def test_hidden_themes_never_broadcast(self):
        """When France posts her precision, its themes go to her partner
        alone: not to the conversation, not to Sam, not in the body."""
        reflet = self._confirmed()
        themes = self.goals | self.emotions
        self._bus_reset()
        precision = self._precision(reflet)
        message = precision.message_id
        self.assertEqual(message.author_id, self.france.partner_id)
        self.assertEqual(
            html2plaintext(message.body), "France clarified their thought."
        )
        sent = self._bus_sent()
        self.assertTrue(any(kind == NEW_MESSAGE for _t, kind, _p in sent))
        private = []
        for target, kind, payload in sent:
            if same_target(target, self.france.partner_id):
                if "linkup.reflet" in payload:
                    private.append(payload)
                continue
            self.assertNoHiddenTheme(store_of(kind, payload), themes)
        card = self._cards(sent, reflet.channel_id)[precision.id]
        self.assertEqual(card["guess_state"], "pending")
        self.assertFalse(card["category_id"])
        self.assertEqual(len(private), 1)
        own = self._cards([(self.france.partner_id, INSERT, private[0])])
        self.assertEqual(
            set(own[precision.id]["revealed_category_ids"]), set(themes.ids)
        )
        self.assertEqual(
            own[precision.id]["primary_category_id"], self.goals.id
        )
        self.assertEqual(
            {c["code"] for c in private[0]["linkup.category"]},
            {"goals", "emotions"},
        )
        # Reading the conversation again: the Store of the messages, built
        # for each reader as /discuss/channel/messages does.
        messages = reflet.channel_id.message_ids
        as_sam = Store(
            messages.with_user(self.sam), for_current_user=True
        ).get_result()
        self.assertNoHiddenTheme(as_sam, themes)
        as_france = Store(
            messages.with_user(self.france), for_current_user=True
        ).get_result()
        self.assertEqual(
            set(
                self._cards([(None, INSERT, as_france)])[precision.id][
                    "revealed_category_ids"
                ]
            ),
            set(themes.ids),
        )
        # The Store built once for everybody holds no theme, whoever the
        # poster is.
        shared = Store(messages.with_user(self.france)).get_result()
        self.assertNoHiddenTheme(shared, themes)

    def test_guess_reveals_to_both_parties(self):
        """After the guess, each party gets the themes on their partner;
        the conversation gets the outcome only (LU-F-033 RM3)."""
        reflet = self._confirmed()
        precision = self._precision(reflet, codes=("goals",))
        self._bus_reset()
        precision.with_user(self.sam).action_guess(self.needs.id)
        sent = self._bus_sent()
        channel = reflet.channel_id
        card = self._cards(sent, channel)[precision.id]
        self.assertEqual(card["guess_state"], "missed")
        self.assertEqual(card["guessed_category_id"], self.needs.id)
        for target, kind, payload in sent:
            if not same_target(target, channel):
                continue
            self.assertNoHiddenTheme(store_of(kind, payload), self.goals)
        for user in (self.sam, self.france):
            own = self._cards(sent, user.partner_id)
            self.assertEqual(
                set(own[precision.id]["revealed_category_ids"]),
                set(self.goals.ids),
            )

    def test_message_store_without_reflection_field(self):
        """A Store asking for other fields leaves the card out."""
        reflet = self._sent()
        store = Store()
        reflet.message_id._to_store(store, fields=["body"])
        self.assertNotIn("linkup.reflet", store.get_result())


@tagged("post_install", "-at_install")
class TestLinkupRefletCarrierHttp(
    LinkupCarrierMixin, LinkupRefletCase, HttpCase
):
    def test_channel_messages_route_hides_themes(self):
        """``/discuss/channel/messages`` serves the hidden themes to the
        author of the precision only (T-06)."""
        reflet = self._confirmed()
        precision = self._precision(reflet)
        themes = self.goals | self.emotions
        params = {"channel_id": reflet.channel_id.id}
        self.authenticate(self.sam.login, self.sam.login)
        as_sam = self.make_jsonrpc_request("/discuss/channel/messages", params)
        self.assertIn(
            precision.id, self._cards([(None, INSERT, as_sam["data"])])
        )
        self.assertNoHiddenTheme(as_sam["data"], themes)
        self.authenticate(self.france.login, self.france.login)
        as_france = self.make_jsonrpc_request(
            "/discuss/channel/messages", params
        )
        cards = self._cards([(None, INSERT, as_france["data"])])
        self.assertEqual(
            set(cards[precision.id]["revealed_category_ids"]), set(themes.ids)
        )
