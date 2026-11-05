# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
""""You add to my happiness" (T-10, T-34; LU-F-050, LU-F-052): the sender
is the current user, a pair holds one active highlight per direction, the
next exchange puts it out, and no point is involved.
"""

from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError
from odoo.tools import mute_logger

from .common import LinkupRefletCase
from .test_reflet_carrier import INSERT, same_target

RECEIVED = "linkup.highlight/received"


class TestLinkupHighlight(LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Highlight = cls.env["linkup.highlight"]
        # Free text opens without a reflection, so that the messages of the
        # pair are not refused by the start rule.
        cls.env["ir.config_parameter"].sudo().set_param(
            "linkup.start_rule_mode", "off"
        )

    def _chat(self, user, other):
        """The direct conversation of two members, opened as the server
        does: a member alone opens it only once their link is active."""
        return (
            self.env["discuss.channel"]
            .with_user(user)
            .sudo()
            .channel_get([other.partner_id.id])
            .sudo(False)
        )

    def _send(self, sender, recipient, channel=None):
        highlight_id = self.Highlight.with_user(sender).action_send(
            recipient.id, channel.id if channel else None
        )
        return self.Highlight.browse(highlight_id)

    def _active(self, sender, recipient):
        return self.Highlight.sudo().search(
            [
                ("sender_id", "=", sender.id),
                ("recipient_id", "=", recipient.id),
            ]
        )

    def test_send_forces_the_sender(self):
        """The sender is the current user, the conversation that of the
        pair; the recipient receives it over the bus, and no scoring event
        is reported (LU-F-050 RM2, RM4)."""
        chat = self._chat(self.france, self.sam)
        self._bus_reset()
        highlight = self._send(self.france, self.sam, chat)
        self.assertEqual(highlight.sender_id, self.france)
        self.assertEqual(highlight.recipient_id, self.sam)
        self.assertEqual(highlight.channel_id, chat)
        self.assertEqual(highlight.context, "thread")
        self.assertTrue(highlight.active)
        sent = self._bus_sent()
        received = [
            payload
            for target, kind, payload in sent
            if kind == RECEIVED and same_target(target, self.sam.partner_id)
        ]
        self.assertEqual(len(received), 1)
        [card] = received[0]["linkup.highlight"]
        self.assertEqual(card["id"], highlight.id)
        self.assertTrue(
            any(
                kind == INSERT and same_target(target, self.france.partner_id)
                for target, kind, _payload in sent
            )
        )
        self.assertEqual(self.events, [])
        dragged = self._send(self.france, self.jacques)
        self.assertEqual(dragged.context, "drag")

    def test_one_active_per_direction(self):
        """A second press while the highlight shines has no effect; the
        other direction is a highlight of its own (LU-F-050 RM3)."""
        first = self._send(self.france, self.sam)
        again = self._send(self.france, self.sam)
        self.assertEqual(again, first)
        self.assertEqual(len(self._active(self.france, self.sam)), 1)
        back = self._send(self.sam, self.france)
        self.assertNotEqual(back, first)
        first.with_user(self.france).action_withdraw()
        renewed = self._send(self.france, self.sam)
        self.assertNotEqual(renewed, first)
        self.assertTrue(renewed.active)

    def test_scope_and_channel(self):
        """A member outside the scope, oneself, or a conversation that is
        not the chat of the pair are refused."""
        with self.assertLinkupCode("linkup.unavailable"):
            self._send(self.sam, self.luce)
        with self.assertLinkupCode("linkup.unavailable"):
            self._send(self.sam, self.sam)
        with self.assertLinkupCode("linkup.unavailable"):
            self._send(self.sam, self.france, self.workshop)
        self.assertFalse(self.Highlight.sudo().search([]))

    def test_blocked_link_delivers_nothing(self):
        """A blocked link answers like a delivery: the highlight shines for
        its sender only (``test_safety_bypass``)."""
        link = self.Link._get_or_create(self.sam, self.france)
        link.write({"state": "blocked"})
        highlight = self._send(self.sam, self.france)
        self.assertTrue(highlight.sudo().phantom)
        self.assertEqual(self._active(self.sam, self.france), highlight)
        self.assertFalse(self.Highlight.with_user(self.france).search([]))

    def test_withdraw_and_dismiss(self):
        """The sender withdraws, the recipient hides; each one only their
        own side (LU-F-052 RM2, LU-F-026)."""
        highlight = self._send(self.france, self.sam)
        with self.assertRaises(AccessError):
            highlight.with_user(self.sam).action_withdraw()
        with self.assertRaises(AccessError):
            highlight.with_user(self.france).action_dismiss()
        with self.assertRaises(AccessError):
            highlight.with_user(self.jacques).action_dismiss()
        highlight.with_user(self.sam).action_dismiss()
        self.assertFalse(highlight.active)
        self.assertEqual(highlight.extinguished_reason, "manual")
        self.assertTrue(highlight.extinguished_date)
        other = self._send(self.sam, self.france)
        other.with_user(self.sam).action_withdraw()
        self.assertEqual(other.extinguished_reason, "withdrawn")

    def test_reflection_puts_it_out(self):
        """A reflection sent in the pair puts out both directions."""
        mine = self._send(self.sam, self.france)
        theirs = self._send(self.france, self.sam)
        self._sent()
        self.assertFalse(mine.active)
        self.assertFalse(theirs.active)
        self.assertEqual(mine.extinguished_reason, "reflet")

    def test_message_of_the_highlighted_member_puts_it_out(self):
        """A message of the highlighted member puts out the highlight they
        received; a message of the sender leaves it (T-10, LU-F-052)."""
        chat = self._chat(self.france, self.sam)
        highlight = self._send(self.france, self.sam, chat)
        chat.with_user(self.france).message_post(
            body="Merci", message_type="comment"
        )
        self.assertTrue(highlight.active)
        chat.with_user(self.sam).message_post(
            body="Avec plaisir", message_type="comment"
        )
        self.assertFalse(highlight.active)
        self.assertEqual(highlight.extinguished_reason, "message")

    def test_call_puts_it_out(self):
        """A call started in the conversation puts out the highlights of
        the pair, answered or not (T-10, LU-F-052 CA1)."""
        chat = self._chat(self.sam, self.france)
        highlight = self._send(self.france, self.sam, chat)
        member = chat.sudo().channel_member_ids.filtered(
            lambda m: m.partner_id == self.sam.partner_id
        )
        member.with_user(self.sam).sudo()._rtc_join_call()
        self.assertFalse(highlight.active)
        self.assertEqual(highlight.extinguished_reason, "call")

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_access(self):
        """A member reads the highlights they sent or received and writes
        none; a third member reads none (§9.4)."""
        highlight = self._send(self.france, self.sam)
        Highlight = self.Highlight
        self.assertEqual(Highlight.with_user(self.sam).search([]), highlight)
        self.assertEqual(
            Highlight.with_user(self.france).search([]), highlight
        )
        self.assertFalse(Highlight.with_user(self.jacques).search([]))
        with self.assertRaises(AccessError):
            highlight.with_user(self.jacques).read(["sender_id"])
        with self.assertRaises(AccessError):
            highlight.with_user(self.france).write({"active": False})
        with self.assertRaises(AccessError):
            Highlight.with_user(self.sam).create(
                {"sender_id": self.france.id, "recipient_id": self.sam.id}
            )
        with self.assertRaises(AccessError):
            highlight.with_user(self.france).unlink()

    def test_store_of_the_member(self):
        """The Store of a member holds the active highlights they sent or
        received, and nothing for another member."""
        highlight = self._send(self.france, self.sam)
        data = self._init_store(self.sam)
        self.assertEqual(
            [card["id"] for card in data.get("linkup.highlight", [])],
            [highlight.id],
        )
        self.assertFalse(
            self._init_store(self.jacques).get("linkup.highlight")
        )

    def _init_store(self, user):
        store = Store()
        self.env["res.users"].with_user(user)._init_store_data(store)
        return store.get_result()
