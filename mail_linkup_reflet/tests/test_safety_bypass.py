# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The side doors of Discuss around the start rule, a block and a
suspension (LU-F-063 RM1 and RM4, LU-F-114 RM5, LU-F-115 RM1 and RM2).

An internal user of ``mail`` writes to anybody without a conversation: a
private message, an inbox notification, the star of another user, the
mention of an edited message. A restricted member reaches nobody that
way. A highlight to a member who blocked its sender behaves for the
sender as a delivered one, and either party of a block still reports the
other.
"""

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import LinkupRefletCase
from .test_safety import LinkupSafetyMixin


@tagged("post_install", "-at_install")
class TestLinkupSafetyBypass(LinkupSafetyMixin, LinkupRefletCase):
    def setUp(self):
        super().setUp()
        self.Message = self.env["mail.message"]
        self.Highlight = self.env["linkup.highlight"]

    def _inbox(self, user):
        """The messages waiting in the inbox of ``user``."""
        return (
            self.env["mail.notification"]
            .sudo()
            .search([("res_partner_id", "=", user.partner_id.id)])
            .mail_message_id
        )

    # Messages outside a conversation

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_no_private_message(self):
        """Sam shares nothing with Luce: neither a message without a
        document nor ``message_notify`` reaches her inbox."""
        with self.assertRaises(AccessError):
            self.Message.with_user(self.sam).create(
                {
                    "body": "Écris-moi",
                    "message_type": "comment",
                    "partner_ids": self.luce.partner_id.ids,
                }
            )
        with self.assertRaises(AccessError):
            self.env["mail.thread"].with_user(self.sam).message_notify(
                body="Écris-moi", partner_ids=self.luce.partner_id.ids
            )
        self.assertFalse(self._inbox(self.luce))

    def test_no_notification_nor_star_for_another(self):
        """A message Sam reads does not go to the inbox nor to the starred
        messages of somebody else by the ORM; his own star still works."""
        message = self._post(self.workshop, self.sam)
        with self.assertRaises(AccessError):
            self.env["mail.notification"].with_user(self.sam).create(
                {
                    "mail_message_id": message.id,
                    "res_partner_id": self.luce.partner_id.id,
                    "notification_type": "inbox",
                }
            )
        for field in ("starred_partner_ids", "partner_ids"):
            with self.subTest(field=field):
                with self.assertRaises(AccessError):
                    message.with_user(self.sam).write(
                        {field: [fields.Command.link(self.luce.partner_id.id)]}
                    )
        self.assertFalse(self._inbox(self.luce))
        message.with_user(self.sam).toggle_message_starred()
        self.assertEqual(
            message.sudo().starred_partner_ids, self.sam.partner_id
        )

    def test_edited_mention_skips_the_blocker(self):
        """An edition adds no mention of a member who blocked the author;
        ``/mail/message/update_content`` gives the message under ``sudo``."""
        message = self._post(self.workshop, self.sam)
        self._block(self.france, self.sam)
        self.workshop.with_user(self.sam)._message_update_content(
            message.sudo(),
            "Bonjour @France @Jacques",
            partner_ids=(self.france | self.jacques).partner_id.ids,
        )
        self.assertEqual(message.sudo().partner_ids, self.jacques.partner_id)

    def test_typing_in_a_blocked_conversation(self):
        """Neither party of a blocked pair tells the other one it types."""
        chat = self._confirmed().channel_id
        self._block(self.france, self.sam)
        self._bus_reset()
        self._member(chat, self.sam).with_user(self.sam)._notify_typing(True)
        self.assertFalse(
            [sent for sent in self._bus_sent() if "isTyping" in str(sent[2])]
        )
        self._member(self.workshop, self.sam).with_user(
            self.sam
        )._notify_typing(True)
        self.assertTrue(
            [sent for sent in self._bus_sent() if "isTyping" in str(sent[2])]
        )

    # A highlight to a member who blocked its sender (LU-F-115 RM2)

    def test_phantom_highlight(self):
        """Sam's highlight to France, who blocked him, answers and reads as
        a delivered one; France never reads it nor hides it. Once the block
        is lifted, a new press reaches her."""
        self._block(self.france, self.sam)
        self._bus_reset()
        highlight_id = self.Highlight.with_user(self.sam).action_send(
            self.france.id
        )
        self.assertTrue(highlight_id)
        highlight = self.Highlight.sudo().browse(highlight_id)
        self.assertTrue(highlight.active)
        self.assertEqual(
            self.Highlight.with_user(self.sam).action_send(self.france.id),
            highlight_id,
        )
        self.assertEqual(
            self.Highlight.with_user(self.sam).search([]).ids, [highlight_id]
        )
        self.assertIn(highlight, self.Highlight._linkup_store_for(self.sam))
        self.assertNotIn(
            highlight, self.Highlight._linkup_store_for(self.france)
        )
        self.assertFalse(self.Highlight.with_user(self.france).search([]))
        targets = {sent[0] for sent in self._bus_sent()}
        self.assertIn(self.sam.partner_id, targets)
        self.assertNotIn(self.france.partner_id, targets)
        with self.assertRaises(AccessError):
            highlight.with_user(self.france).action_dismiss()
        self.Block.with_user(self.france).action_unblock(self.sam.id)
        self.assertFalse(self.Highlight.with_user(self.france).search([]))
        delivered_id = self.Highlight.with_user(self.sam).action_send(
            self.france.id
        )
        self.assertNotEqual(delivered_id, highlight_id)
        self.assertFalse(highlight.active)
        self.assertEqual(
            self.Highlight.with_user(self.france).search([]).ids,
            [delivered_id],
        )

    # Reports across a block (LU-F-114, LU-F-115)

    def test_report_across_a_block(self):
        """Luce, linked to Sam, blocks him: each one leaves the scope of the
        other, and still reports the other, as before the block. A member
        who never shared anything with Luce reports her not."""
        self.Link._get_or_create(self.luce, self.sam).state = "active"
        self._block(self.luce, self.sam)
        for reporter, reported in (
            (self.luce, self.sam),
            (self.sam, self.luce),
        ):
            with self.subTest(reporter=reporter.name):
                self.assertNotIn(
                    reported,
                    self.env["res.users"].with_user(reporter).search([]),
                )
                report_id = self.Report.with_user(
                    reporter
                ).action_create_report(user_id=reported.id, reason="spam")
                self.assertEqual(
                    self.Report.sudo().browse(report_id).reported_user_id,
                    reported,
                )
        with self.assertLinkupCode("linkup.unavailable"):
            self.Report.with_user(self.jacques).action_create_report(
                user_id=self.luce.id, reason="spam"
            )
