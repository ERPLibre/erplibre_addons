# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Blocking, suspension, reports and the contact initiated by the server
(LU-F-016 CA3, LU-F-023 CA2 and CA3, LU-F-063, LU-F-114 RM5 and RM6,
LU-F-115; T-05, T-15, T-35).

France blocks Sam in most tests. Sam must never learn it: what he sends to
France looks delivered, and every refusal he meets reads as for a person
out of his scope or a conversation that no longer exists.
"""

import json
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from .common import MEMBER, LinkupRefletCase

ADMIN = "mail_linkup_reflet.group_linkup_admin"
MODERATOR = "mail_linkup_reflet.group_linkup_moderator"


class LinkupSafetyMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Block = cls.env["linkup.block"]
        cls.Report = cls.env["linkup.report"]
        # Free text opens without a reflection: what refuses a post below
        # is the block or the suspension, not the start rule.
        cls.env["ir.config_parameter"].sudo().set_param(
            "linkup.start_rule_mode", "off"
        )

    def _block(self, blocker, blocked):
        return self.Block.with_user(blocker).action_block(blocked.id)

    def _post(self, channel, user, **kwargs):
        values = {
            "body": "Bonjour",
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_comment",
        }
        values.update(kwargs)
        return channel.with_user(user).message_post(**values)

    def _messages(self, channel):
        return (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", channel.id),
                    ("message_type", "=", "comment"),
                ]
            )
        )

    def _member(self, channel, user):
        return channel.sudo().channel_member_ids.filtered(
            lambda member: member.partner_id == user.partner_id
        )


@tagged("post_install", "-at_install")
class TestLinkupBlock(LinkupSafetyMixin, LinkupRefletCase):
    # The block and its record

    def test_block_closes_the_pair(self):
        """A block makes the link ``blocked`` and is read by its holder
        only; the other member reads neither the block nor the state of the
        link, the two disappear from each other's contacts, and the blocked
        member reads the conversation as that of a deleted account."""
        reflet = self._confirmed()
        self._block(self.france, self.sam)
        link = reflet.link_id
        self.assertEqual(link.state, "blocked")
        self.assertEqual(
            self.Block.with_user(self.france).search([]).blocked_id, self.sam
        )
        self.assertFalse(self.Block.with_user(self.sam).search([]))
        with self.assertRaises(AccessError):
            link.with_user(self.sam).read(["state"])
        for user, other in ((self.sam, self.france), (self.france, self.sam)):
            contacts = self.Reflet.with_user(user).linkup_reflet_view_info()[
                "contacts"
            ]
            self.assertNotIn(other.id, [c["user_id"] for c in contacts])
        sam_info = self.Reflet.with_user(self.sam).linkup_channel_info(
            reflet.channel_id.id
        )
        france_info = self.Reflet.with_user(self.france).linkup_channel_info(
            reflet.channel_id.id
        )
        # An active link never closes but by a block: Sam reads the
        # conversation as that of a deleted account.
        self.assertEqual(sam_info, {"available": False})
        self.assertEqual(
            self.Reflet.with_user(self.sam).linkup_history(
                reflet.channel_id.id
            ),
            {"available": False},
        )
        self.assertEqual(france_info["link_state"], "closed")
        self.assertTrue(france_info["blocked_by_me"])
        self._block(self.sam, self.france)
        sam_info = self.Reflet.with_user(self.sam).linkup_channel_info(
            reflet.channel_id.id
        )
        self.assertTrue(sam_info["blocked_by_me"])

    def test_block_hides_conversation_of_blocker(self):
        """The direct conversation is unpinned for the blocker only, and
        kept; the highlights of the pair go out."""
        reflet = self._confirmed()
        chat = reflet.channel_id
        Highlight = self.env["linkup.highlight"]
        sent = Highlight.browse(
            Highlight.with_user(self.france).action_send(self.sam.id)
        )
        received = Highlight.browse(
            Highlight.with_user(self.sam).action_send(self.france.id)
        )
        self._bus_reset()
        self._block(self.france, self.sam)
        unpinned = [
            (target, payload["id"])
            for target, kind, payload in self._bus_sent()
            if kind == "discuss.channel/unpin"
        ]
        self.assertEqual(unpinned, [(self.france.partner_id, chat.id)])
        self.assertTrue(self._member(chat, self.france).unpin_dt)
        self.assertFalse(self._member(chat, self.sam).unpin_dt)
        self.assertTrue(chat.exists())
        self.assertFalse(sent.active)
        self.assertEqual(sent.extinguished_reason, "withdrawn")
        self.assertFalse(received.active)
        self.assertEqual(received.extinguished_reason, "manual")

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_block_targets(self):
        """A member blocks a member of their scope or of a link, never
        themself, an outsider or an unknown id; writing a block directly is
        refused."""
        for target in (self.sam.id, self.luce.id, 999999, "x"):
            with self.subTest(target=target):
                with self.assertLinkupCode("linkup.unavailable"):
                    self.Block.with_user(self.sam).action_block(target)
        self.Link._get_or_create(self.luce, self.sam).state = "closed"
        self.Block.with_user(self.luce).action_block(self.sam.id)
        self.Block.with_user(self.sam).action_block(
            partner_id=self.france.partner_id.id
        )
        self.assertEqual(
            self.Block.sudo().search([]).mapped("blocked_id"),
            self.france | self.sam,
        )
        with self.assertRaises(AccessError):
            self.Block.with_user(self.sam).create(
                {"blocker_id": self.sam.id, "blocked_id": self.jacques.id}
            )

    def test_unblock_restores_the_link(self):
        """Lifting the last block gives the link back the state of its
        reflections; a block held by the other member keeps it blocked."""
        reflet = self._confirmed()
        link = reflet.link_id
        self._block(self.france, self.sam)
        self._block(self.sam, self.france)
        self.Block.with_user(self.france).action_unblock(self.sam.id)
        self.assertEqual(link.state, "blocked")
        self.Block.with_user(self.sam).action_unblock(self.france.id)
        self.assertEqual(link.state, "active")
        jacques = self._sent(recipient=self.jacques)
        self._block(self.jacques, self.sam)
        self.Block.with_user(self.jacques).action_unblock(
            partner_id=self.sam.partner_id.id
        )
        self.assertEqual(jacques.link_id.state, "pending")
        jacques.with_user(self.jacques).action_reject()
        self._block(self.jacques, self.sam)
        self.Block.with_user(self.jacques).action_unblock(self.sam.id)
        self.assertEqual(jacques.link_id.state, "closed")
        self.assertEqual(
            self.Block.with_user(self.jacques).linkup_blocked_members(), []
        )

    def test_blocked_members_list(self):
        """The settings list the members the member blocks, by name."""
        self._block(self.france, self.sam)
        self.assertEqual(
            [
                (row["user_id"], row["partner_id"], row["name"])
                for row in self.Block.with_user(
                    self.france
                ).linkup_blocked_members()
            ],
            [(self.sam.id, self.sam.partner_id.id, "Sam")],
        )
        self.assertEqual(
            self.Block.with_user(self.sam).linkup_blocked_members(), []
        )

    # What the blocked member sends (LU-F-115 CA1 and CA2, LU-F-016 CA3)

    def test_post_in_blocked_chat_refused(self):
        """A message of either member in their direct conversation is
        refused as for a conversation that no longer exists."""
        chat = self._confirmed().channel_id
        self._post(chat, self.sam)
        self._block(self.france, self.sam)
        for user in (self.sam, self.france):
            with self.subTest(user=user.name):
                with self.assertLinkupCode("linkup.unavailable"):
                    self._post(chat, user)

    def test_phantom_reflection(self):
        """A reflection to a member who blocked its author looks sent and
        reaches nobody: no carrier, no event, nothing on the bus for the
        recipient, who neither reads nor answers it. It expires as usual
        and stays out of reach after the block is lifted."""
        self._block(self.france, self.sam)
        self._bus_reset()
        self.events.clear()
        reflet = self._sent()
        self.assertEqual(reflet.state, "sent")
        self.assertTrue(reflet.sudo().phantom)
        self.assertFalse(reflet.message_id)
        self.assertFalse(reflet.channel_id)
        self.assertEqual(self.events, [])
        france = self.france.partner_id
        self.assertFalse(
            [sent for sent in self._bus_sent() if sent[0] == france]
        )
        self.assertEqual(
            reflet.with_user(self.sam).read(["state"])[0]["state"], "sent"
        )
        Reflet = self.Reflet.with_user(self.france)
        self.assertFalse(Reflet.search([("id", "=", reflet.id)]))
        for action in ("action_confirm", "action_reject", "action_mark_read"):
            with self.subTest(action=action):
                with self.assertRaises(AccessError):
                    getattr(reflet.with_user(self.france), action)()
        reflet.sudo().sent_date = fields.Datetime.now() - timedelta(days=31)
        self.Reflet._cron_expire_reflets()
        self.assertEqual(reflet.state, "expired")
        self.Block.with_user(self.france).action_unblock(self.sam.id)
        self.assertFalse(Reflet.search([("id", "=", reflet.id)]))
        self.assertEqual(reflet.link_id.state, "closed")

    def test_phantom_out_of_scope(self):
        """A member who blocked the author is no longer in their scope, and
        still gets a phantom delivery rather than a refusal."""
        self.Link._get_or_create(self.luce, self.sam).state = "active"
        self._block(self.luce, self.sam)
        self.assertNotIn(
            self.luce, self.env["res.users"].with_user(self.sam).search([])
        )
        reflet = self._sent(recipient=self.luce)
        self.assertEqual(reflet.state, "sent")
        self.assertTrue(reflet.sudo().phantom)
        Highlight = self.env["linkup.highlight"]
        highlight = Highlight.browse(
            Highlight.with_user(self.sam).action_send(self.luce.id)
        )
        self.assertTrue(highlight.sudo().phantom)
        self.assertFalse(Highlight.with_user(self.luce).search([]))

    def test_blocker_sends_nothing(self):
        """The member who blocks sends neither a reflection nor a
        highlight to the member they block."""
        self._block(self.france, self.sam)
        with self.assertLinkupCode("linkup.unavailable"):
            self._sent(author=self.france, recipient=self.sam)
        with self.assertLinkupCode("linkup.unavailable"):
            self.env["linkup.highlight"].with_user(self.france).action_send(
                self.sam.id
            )

    def test_no_action_in_blocked_pair(self):
        """A blocked pair takes no exchange; reading, withdrawing and
        ignoring stay possible."""
        reflet = self._confirmed()
        pending = self._sent(author=self.france, recipient=self.sam)
        self._block(self.sam, self.france)
        with self.assertLinkupCode("linkup.unavailable"):
            reflet.with_user(self.france).action_answer_exact()
        with self.assertLinkupCode("linkup.unavailable"):
            pending.with_user(self.sam).action_confirm()
        pending.with_user(self.sam).action_mark_read()
        pending.with_user(self.sam).action_ignore()
        later = self._sent(author=self.sam, recipient=self.jacques)
        later.with_user(self.sam).action_withdraw()
        self.assertEqual(later.state, "withdrawn")

    # Shared conversations (LU-F-063 RM4)

    def test_mention_skips_blocked_member(self):
        """In a shared group, a mention and ``@everyone`` skip the people a
        block separates from the author."""
        self._block(self.france, self.sam)
        partners = (self.france | self.jacques).partner_id
        message = self._post(self.workshop, self.sam, partner_ids=partners.ids)
        self.assertEqual(message.partner_ids, self.jacques.partner_id)
        message = self._post(
            self.workshop,
            self.sam,
            partner_ids=[],
            special_mentions=["everyone"],
        )
        self.assertIn(self.jacques.partner_id, message.partner_ids)
        self.assertNotIn(self.france.partner_id, message.partner_ids)
        message = self._post(
            self.workshop, self.jacques, partner_ids=partners.ids
        )
        self.assertEqual(message.partner_ids, partners)

    def test_reaction_to_blocked_member_refused(self):
        """A member does not react to a message of a member a block
        separates them from, in a shared group either."""
        message = self._post(self.workshop, self.france)
        self._block(self.france, self.sam)
        with self.assertLinkupCode("linkup.unavailable"):
            message.with_user(self.sam).sudo()._message_reaction(
                "👍", "add", self.sam.partner_id, self.env["mail.guest"]
            )
        message.with_user(self.jacques).sudo()._message_reaction(
            "👍", "add", self.jacques.partner_id, self.env["mail.guest"]
        )
        self.assertEqual(len(message.sudo().reaction_ids), 1)

    def test_call_skips_blocked_member(self):
        """A call in a shared group rings for nobody a block separates from
        the caller; the call of a blocked direct conversation is refused."""
        self._block(self.france, self.sam)
        self._member(self.workshop, self.sam).with_user(
            self.sam
        ).sudo()._rtc_join_call()
        self.assertTrue(
            self._member(self.workshop, self.jacques).rtc_inviting_session_id
        )
        self.assertFalse(
            self._member(self.workshop, self.france).rtc_inviting_session_id
        )
        chat = (
            self.env["discuss.channel"]
            .with_user(self.sam)
            .sudo()
            .channel_get([self.france.partner_id.id])
        )
        with self.assertLinkupCode("linkup.unavailable"):
            self._member(chat, self.sam).with_user(
                self.sam
            ).sudo()._rtc_join_call()


@tagged("post_install", "-at_install")
class TestLinkupSuspension(LinkupSafetyMixin, LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.linkup_admin = mail_new_test_user(
            cls.env,
            login="linkup_sf_admin",
            name="Joanna",
            email="joanna@example.com",
            groups=ADMIN,
        )

    def _suspend(self, user, days=3):
        user.with_user(self.linkup_admin).action_linkup_suspend(
            fields.Datetime.now() + timedelta(days=days)
        )

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_suspension_reserved_to_administrators(self):
        """A member neither reads, writes nor lifts a suspension; a LinkUp
        administrator sets it in the future only (LU-F-082 CA2)."""
        with self.assertRaises(AccessError):
            self.sam.with_user(self.sam).write(
                {"linkup_suspended_until": fields.Datetime.now()}
            )
        with self.assertRaises(AccessError):
            self.sam.with_user(self.sam).read(["linkup_suspended_until"])
        with self.assertRaises(AccessError):
            self.sam.with_user(self.sam).action_linkup_lift_suspension()
        with self.assertRaises(AccessError):
            self.france.with_user(self.sam).action_linkup_suspend(
                fields.Datetime.now() + timedelta(days=1)
            )
        with self.assertLinkupCode("linkup.validation"):
            self._suspend(self.sam, days=-1)
        self._suspend(self.sam)
        self.assertTrue(self.sam._linkup_is_suspended())
        self.sam.with_user(self.linkup_admin).action_linkup_lift_suspension()
        self.assertFalse(self.sam._linkup_is_suspended())

    def test_suspended_member_sends_nothing(self):
        """A suspended member sends no reflection, message, reaction or
        highlight, adds nobody to a group and calls nobody; they still read
        and withdraw. Once the suspension ends, everything opens again."""
        message = self._post(self.workshop, self.france)
        sent = self._sent()
        self._suspend(self.sam)
        attempts = {
            "reflection": lambda: self._sent(recipient=self.jacques),
            "message": lambda: self._post(self.workshop, self.sam),
            "reaction": lambda: message.with_user(self.sam)
            .sudo()
            ._message_reaction(
                "👍", "add", self.sam.partner_id, self.env["mail.guest"]
            ),
            "highlight": lambda: self.env["linkup.highlight"]
            .with_user(self.sam)
            .action_send(self.jacques.id),
            "call": lambda: self._member(self.workshop, self.sam)
            .with_user(self.sam)
            .sudo()
            ._rtc_join_call(),
        }
        for name, attempt in attempts.items():
            with self.subTest(attempt=name):
                with self.assertLinkupCode("linkup.unavailable"):
                    attempt()
        with self.assertLinkupCode("linkup.unavailable"):
            self.workshop.with_user(self.sam).add_members(
                partner_ids=self.luce.partner_id.ids
            )
        sent.with_user(self.sam).action_withdraw()
        self.assertEqual(sent.state, "withdrawn")
        self.sam.sudo().linkup_suspended_until = (
            fields.Datetime.now() - timedelta(minutes=1)
        )
        self._post(self.workshop, self.sam)
        self._sent(recipient=self.jacques)

    def test_suspended_member_receives_and_answers_nothing(self):
        """A suspended member receives no reflection and answers none."""
        reflet = self._sent()
        self._suspend(self.france)
        with self.assertLinkupCode("linkup.unavailable"):
            reflet.with_user(self.france).action_confirm()
        with self.assertLinkupCode("linkup.unavailable"):
            self._sent(author=self.jacques, recipient=self.france)
        reflet.with_user(self.france).action_mark_read()


@tagged("post_install", "-at_install")
class TestLinkupReport(LinkupSafetyMixin, LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.moderator = mail_new_test_user(
            cls.env,
            login="linkup_sf_moderator",
            name="Nicolas",
            email="nicolas@example.com",
            groups=MODERATOR,
        )

    def _report(self, user, **kwargs):
        values = {"reason": "harassment"}
        values.update(kwargs)
        return self.Report.browse(
            self.Report.with_user(user).action_create_report(**values)
        )

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_report_a_reflection(self):
        """The reporter is the current user, the reported member the
        author; the system fields a client sends are ignored, the urgency
        follows the reason, and the reported member reads nothing of it
        (LU-F-114 CA1 and CA3)."""
        reflet = self._sent()
        report = self._report(
            self.france,
            reflet_id=reflet.id,
            description="  Encore.  ",
            urgent=True,
            auto_generated=True,
            state="dismissed",
            reporter_id=self.jacques.id,
        )
        self.assertEqual(report.reporter_id, self.france)
        self.assertEqual(report.reported_user_id, self.sam)
        self.assertEqual(report.reflet_id, reflet)
        self.assertEqual(report.description, "Encore.")
        self.assertFalse(report.urgent)
        self.assertFalse(report.auto_generated)
        self.assertEqual(report.state, "new")
        self.assertEqual(self.Report.with_user(self.france).search([]), report)
        self.assertFalse(self.Report.with_user(self.sam).search([]))
        self.assertEqual(
            self.Report.with_user(self.moderator).search([]), report
        )
        threat = self._report(
            self.france, reflet_id=reflet.id, reason="threat"
        )
        self.assertTrue(threat.urgent)
        self.assertEqual(
            self._report(self.france, reflet_id=reflet.id), report
        )
        with self.assertRaises(AccessError):
            self.Report.with_user(self.france).create(
                {"reason": "spam", "reported_user_id": self.sam.id}
            )

    def test_report_needs_reading_rights(self):
        """A member reports only what they read with their own rights
        (LU-F-114 RM5, CA2), never themself, with a reason of a member."""
        reflet = self._sent()
        chat_message = reflet.message_id
        for kwargs in (
            {"reflet_id": reflet.id},
            {"message_id": chat_message.id},
            {"user_id": self.luce.id},
            {"reflet_id": 999999},
        ):
            with self.subTest(**kwargs):
                with self.assertLinkupCode("linkup.unavailable"):
                    self._report(self.jacques, **kwargs)
        with self.assertLinkupCode("linkup.validation"):
            self._report(self.sam, reflet_id=reflet.id)
        with self.assertLinkupCode("linkup.validation"):
            self._report(
                self.france, reflet_id=reflet.id, reason="repeated_rejections"
            )
        with self.assertLinkupCode("linkup.validation"):
            self._report(self.france)
        message = self._post(self.workshop, self.sam)
        report = self._report(
            self.jacques, message_id=message.id, reason="spam"
        )
        self.assertEqual(report.reported_user_id, self.sam)
        report = self._report(self.france, user_id=self.jacques.id)
        self.assertEqual(report.reported_user_id, self.jacques)

    def test_report_daily_limit(self):
        """Beyond the daily limit, a report is refused (LU-NF-006)."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.max_reports_per_day", "2"
        )
        self._report(self.france, user_id=self.sam.id)
        self._report(self.france, user_id=self.jacques.id)
        with self.assertLinkupCode("linkup.rate_limited"):
            self._report(self.france, user_id=self.jacques.id, reason="spam")

    def test_moderator_does_not_see_reports_about_themself(self):
        """A moderator reads the reports of others, not those about
        themself (LU-F-116 RM5)."""
        self.workshop.add_members(partner_ids=self.moderator.partner_id.ids)
        report = self._report(self.france, user_id=self.moderator.id)
        self.assertNotIn(
            report, self.Report.with_user(self.moderator).search([])
        )

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_moderator_writes_the_processing_only(self):
        """A moderator processes a report and never changes what was
        reported nor by whom; a member writes none."""
        report = self._report(self.france, reflet_id=self._sent().id)
        as_moderator = report.with_user(self.moderator)
        as_moderator.write({"state": "in_review"})
        self.assertEqual(report.state, "in_review")
        for vals in (
            {"reported_user_id": self.jacques.id},
            {"reporter_id": self.jacques.id},
            {"urgent": True},
            {"state": "dismissed", "reason": "spam"},
        ):
            with self.subTest(vals=vals):
                with self.assertRaises(AccessError):
                    as_moderator.write(vals)
        with self.assertRaises(AccessError):
            report.with_user(self.france).write({"state": "dismissed"})
        self.assertEqual(report.reported_user_id, self.sam)
        self.assertEqual(report.reporter_id, self.france)


@tagged("post_install", "-at_install")
class TestLinkupRejectionAlert(LinkupSafetyMixin, LinkupRefletCase):
    """Repeated rejections of one author (LU-F-023 RM5, CA2 and CA3)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        names = ("Jean", "Joanna", "Nicolas", "Pierre", "Marie", "Louise")
        cls.recipients = cls.env["res.users"]
        for index, name in enumerate(names):
            cls.recipients |= mail_new_test_user(
                cls.env,
                login=f"linkup_sf_recipient_{index}",
                name=name,
                email=f"recipient{index}@example.com",
                groups=MEMBER,
            )
        cls.env["discuss.channel"].create(
            {
                "name": "Jardin",
                "channel_type": "group",
                "channel_partner_ids": [
                    Command.link(user.partner_id.id)
                    for user in cls.recipients | cls.sam
                ],
            }
        )

    def _age(self, users, days):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE res_users SET create_date = %s WHERE id IN %s",
            [fields.Datetime.now() - timedelta(days=days), tuple(users.ids)],
        )
        users.invalidate_recordset(["create_date"])

    def _rejected_by(self, users):
        for user in users:
            self._sent(recipient=user).with_user(user).action_reject()

    def _alerts(self):
        return self.Report.sudo().search(
            [("reported_user_id", "=", self.sam.id)]
        )

    def test_six_rejections_alert(self):
        """The sixth distinct recipient creates one report of the server,
        and no more while it is open; it suspends nobody."""
        self._age(self.recipients, 8)
        self._rejected_by(self.recipients[:5])
        self.assertFalse(self._alerts())
        self._rejected_by(self.recipients[5:])
        alert = self._alerts()
        self.assertEqual(len(alert), 1)
        self.assertEqual(alert.reason, "repeated_rejections")
        self.assertTrue(alert.auto_generated)
        self.assertFalse(alert.reporter_id)
        self.assertFalse(self.sam._linkup_is_suspended())
        self._rejected_by(self.jacques)
        self.assertEqual(len(self._alerts()), 1)

    def test_recent_or_linked_recipients_weigh_less(self):
        """Recipients younger than seven days count for nothing, and linked
        recipients count once (CA3)."""
        self._rejected_by(self.recipients)
        self.assertFalse(self._alerts())
        self._age(self.recipients, 8)
        self.Link._get_or_create(
            self.recipients[0], self.recipients[1]
        ).state = "active"
        self._rejected_by(self.recipients[:1])
        self.assertFalse(self._alerts())


@tagged("post_install", "-at_install")
class TestLinkupServerContact(LinkupSafetyMixin, LinkupRefletCase):
    """The contact initiated by the server (LU-F-063 RM1, RM2, CA1, CA2)."""

    def test_member_opens_chat_of_active_link_only(self):
        """A member opens no direct conversation with a person of their
        scope until their link is active; the one the server opened for a
        reflection opens again; a blocked pair opens none."""
        Channel = self.env["discuss.channel"].with_user(self.sam)
        france = self.france.partner_id.ids
        with self.assertRaises(AccessError):
            Channel.channel_get(france)
        reflet = self._sent()
        self.assertEqual(Channel.channel_get(france), reflet.channel_id)
        self.Link._get_or_create(self.sam, self.jacques).state = "active"
        chat = Channel.channel_get(self.jacques.partner_id.ids)
        self.assertEqual(chat.channel_type, "chat")
        self.Link._get_or_create(self.luce, self.sam).state = "active"
        self._block(self.luce, self.sam)
        with self.assertRaises(AccessError):
            Channel.channel_get(self.luce.partner_id.ids)

    def test_member_names_no_direct_conversation(self):
        """The name and the description of a direct conversation carry no
        free text of a member; those of a group follow the start rule."""
        chat = self._sent().channel_id.with_user(self.sam)
        with self.assertRaises(AccessError):
            chat.channel_rename("Appelle-moi")
        with self.assertRaises(AccessError):
            chat.channel_change_description("Appelle-moi")
        self.workshop.with_user(self.sam).channel_rename("Atelier du jeudi")
        self.workshop.sudo().linkup_start_rule = "strict"
        with self.assertLinkupCode("linkup.start_rule"):
            self.workshop.with_user(self.sam).channel_change_description(
                "Appelle-moi"
            )

    def test_new_channel_kept_to_administrators(self):
        """A channel created without a group is kept to the LinkUp
        administrators; an explicit group stays (RM2)."""
        place = self.env["discuss.channel"].create(
            {"name": "Place", "channel_type": "channel"}
        )
        self.assertEqual(place.group_public_id, self.env.ref(ADMIN))
        members = self.env["discuss.channel"].create(
            {
                "name": "Animation",
                "channel_type": "channel",
                "group_public_id": self.env.ref(MEMBER).id,
            }
        )
        self.assertEqual(members.group_public_id, self.env.ref(MEMBER))
        Channel = self.env["discuss.channel"].with_user(self.sam)
        self.assertFalse(Channel.search([("id", "=", place.id)]))
        self.assertTrue(Channel.search([("id", "=", members.id)]))


@tagged("post_install", "-at_install")
class TestLinkupBlockRpc(LinkupSafetyMixin, LinkupRefletCase, HttpCase):
    """What the blocked member obtains by forcing the routes (CA1)."""

    @mute_logger("odoo.http")
    def test_post_route_refused_as_unavailable(self):
        chat = self._confirmed().channel_id
        self._block(self.france, self.sam)
        self.authenticate(self.sam.login, self.sam.login)
        response = self.url_open(
            "/mail/message/post",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "call",
                    "id": 1,
                    "params": {
                        "thread_model": "discuss.channel",
                        "thread_id": chat.id,
                        "post_data": {
                            "body": "Bonjour",
                            "message_type": "comment",
                        },
                    },
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        error = response.json()["error"]
        self.assertEqual(
            error["data"]["context"]["linkup_code"], "linkup.unavailable"
        )
        self.assertEqual(len(self._messages(chat)), 1)
