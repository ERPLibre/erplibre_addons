# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Contacts of the Reflet view: ``linkup.reflet.linkup_reflet_view_info``
(T-24, LU-F-010).
"""

from datetime import datetime

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import MEMBER, LinkupRefletCase


@tagged("post_install", "-at_install")
class TestLinkupRefletView(LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = mail_new_test_user(
            cls.env,
            login="linkup_rv_employee",
            name="Employee",
            groups="base.group_user",
        )
        cls.mathieu = mail_new_test_user(
            cls.env,
            login="linkup_rv_mathieu",
            name="Mathieu",
            email="linkup_rv_mathieu@example.com",
            groups=MEMBER,
        )
        # An internal user outside LinkUp shares the conversation of the
        # workshop; Mathieu shares another group with Sam alone.
        cls.workshop.write(
            {"channel_partner_ids": [Command.link(cls.employee.partner_id.id)]}
        )
        cls.duo = cls.env["discuss.channel"].create(
            {
                "name": "Duo",
                "channel_type": "group",
                "channel_partner_ids": [
                    Command.link(user.partner_id.id)
                    for user in (cls.sam, cls.mathieu)
                ],
            }
        )

    def _info(self, user=None):
        return self.Reflet.with_user(
            user or self.sam
        ).linkup_reflet_view_info()

    def _names(self, user=None):
        return [contact["name"] for contact in self._info(user)["contacts"]]

    def _leave(self, channel, user):
        channel.channel_member_ids.filtered(
            lambda member: member.partner_id == user.partner_id
        ).unlink()

    def test_contacts_are_the_members_of_the_scope(self):
        """The LinkUp members of the member's conversations, by name; never
        the member, an internal user outside LinkUp, or a member outside
        the scope."""
        info = self._info()
        self.assertEqual(self._names(), ["France", "Jacques", "Mathieu"])
        self.assertFalse(info["draft"])
        france = info["contacts"][0]
        self.assertEqual(
            france,
            {
                "user_id": self.france.id,
                "partner_id": self.france.partner_id.id,
                "name": "France",
                "unread_count": 0,
                "link_state": "none",
                "last_interaction_date": False,
                "needs_real_world": True,
                "channel_id": False,
            },
        )
        self.assertEqual(self._names(self.luce), [])

    def test_contacts_order(self):
        """Unread received reflections first, then the most recent
        interaction, then the others by name (LU-F-010 CA3)."""
        to_france = self._sent(recipient=self.france)
        to_france.with_user(self.france).action_confirm()
        to_jacques = self._sent(recipient=self.jacques)
        to_jacques.with_user(self.jacques).action_confirm()
        from_mathieu = self._sent(author=self.mathieu, recipient=self.sam)
        self._link(self.sam, self.jacques).write(
            {"last_interaction_date": datetime(2026, 1, 1, 9, 0)}
        )
        self._link(self.sam, self.france).write(
            {"last_interaction_date": datetime(2026, 1, 2, 9, 0)}
        )
        self._link(self.sam, self.mathieu).write(
            {"last_interaction_date": datetime(2025, 12, 1, 9, 0)}
        )
        info = self._info()
        self.assertEqual(self._names(), ["Mathieu", "France", "Jacques"])
        mathieu, france = info["contacts"][:2]
        self.assertEqual(mathieu["unread_count"], 1)
        self.assertEqual(mathieu["link_state"], "pending")
        self.assertTrue(mathieu["needs_real_world"])
        self.assertEqual(france["link_state"], "active")
        self.assertFalse(france["needs_real_world"])
        self.assertEqual(france["channel_id"], to_france.channel_id.id)
        from_mathieu.with_user(self.sam).action_mark_read()
        self.assertEqual(self._names(), ["France", "Jacques", "Mathieu"])

    def test_pending_link_and_blocked_link(self):
        """A reflection sent alone adds nobody to its author's list; its
        recipient lists the author. A blocked link removes the other member,
        even from a shared conversation."""
        reflet = self._sent(recipient=self.france)
        self._leave(self.workshop, self.france)
        self.assertEqual(self._names(), ["Jacques", "Mathieu"])
        [sam] = self._info(self.france)["contacts"]
        self.assertEqual(sam["user_id"], self.sam.id)
        self.assertEqual(sam["unread_count"], 1)
        self.assertEqual(sam["channel_id"], reflet.channel_id.id)
        # An ignored reflection is no longer waiting to be read.
        reflet.with_user(self.france).action_ignore()
        self.assertEqual(
            self._info(self.france)["contacts"][0]["unread_count"], 0
        )
        reflet.link_id.sudo().state = "blocked"
        self.assertEqual(self._names(self.france), [])
        self.workshop.write(
            {"channel_partner_ids": [Command.link(self.france.partner_id.id)]}
        )
        self.assertEqual(self._names(), ["Jacques", "Mathieu"])
        self.assertEqual(self._names(self.france), ["Jacques"])

    def test_draft_and_access(self):
        """The view gets the draft of the member; a user outside LinkUp is
        refused."""
        draft = self._draft(understood="")
        self.assertEqual(self._info()["draft"]["id"], draft.id)
        self.assertFalse(self._info(self.france)["draft"])
        with self.assertRaises(AccessError):
            self._info(self.employee)

    def test_sent_reflections_wait_in_the_view(self):
        """The initial reflections of the member still waiting stay in the
        view, with the name of their recipient, a phantom one as delivered;
        an answered or withdrawn one leaves it (LU-F-010 RM2, LU-F-019)."""
        waiting = self._sent()
        answered = self._sent(recipient=self.jacques)
        answered.with_user(self.jacques).action_reject()
        self.env["linkup.block"].with_user(self.mathieu).action_block(
            self.sam.id
        )
        phantom = self._sent(recipient=self.mathieu)
        self.assertTrue(phantom.sudo().phantom)
        info = self._info()
        self.assertEqual(info["sent_ids"], [phantom.id, waiting.id])
        partners = {
            partner["id"]: partner["name"]
            for partner in info["store"]["res.partner"]
        }
        self.assertEqual(partners[self.france.partner_id.id], "France")
        self.assertEqual(partners[self.mathieu.partner_id.id], "Mathieu")
        self.assertFalse(self._info(self.france)["sent_ids"])
        waiting.with_user(self.sam).action_withdraw()
        self.assertEqual(self._info()["sent_ids"], [phantom.id])
