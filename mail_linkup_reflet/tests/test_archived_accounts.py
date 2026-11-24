# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""An archived account, banned or deleted, opens nothing to a member
(LU-F-016 RM5, LU-F-063 RM1, error catalogue ``linkup.unavailable``).

The methods that read the users of a conversation with the active test off
keep the link of an archived account: Sam opens no new conversation with
it, adds it to no group, posts no more in its direct conversation, and its
link no longer opens a strict group to him.
"""

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import LinkupRefletCase


@tagged("post_install", "-at_install")
class TestLinkupArchivedAccounts(LinkupRefletCase):
    def _activate(self, user1, user2):
        self.Link._get_or_create(user1, user2).state = "active"

    def _post(self, channel, user=None, body="Bonjour"):
        return channel.with_user(user or self.sam).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def test_no_new_direct_conversation(self):
        """Sam opens a direct conversation with Jacques while his account
        is active, and none once it is archived."""
        self._activate(self.sam, self.jacques)
        self.jacques.action_archive()
        Channel = self.env["discuss.channel"].with_user(self.sam)
        with self.assertRaises(AccessError):
            Channel.channel_get([self.jacques.partner_id.id])
        self.jacques.action_unarchive()
        chat = Channel.channel_get([self.jacques.partner_id.id])
        self.assertEqual(chat.channel_type, "chat")

    def test_existing_direct_conversation_closed(self):
        """The direct conversation of Sam and France stays readable once
        her account is archived, and takes no more post, reaction or call
        from Sam."""
        reflet = self._confirmed()
        chat = reflet.channel_id
        message = self._post(chat)
        self.france.action_archive()
        reopened = (
            self.env["discuss.channel"]
            .with_user(self.sam)
            .channel_get([self.france.partner_id.id])
        )
        self.assertEqual(reopened, chat)
        with self.assertLinkupCode("linkup.unavailable"):
            self._post(chat)
        with self.assertLinkupCode("linkup.unavailable"):
            message.with_user(self.sam).sudo()._message_reaction(
                "👍", "add", self.sam.partner_id, self.env["mail.guest"]
            )
        self.france.action_unarchive()
        self._post(chat)

    def test_not_added_to_a_group(self):
        """Sam adds Jacques to a group while his account is active, and not
        once it is archived."""
        self._activate(self.sam, self.france)
        self._activate(self.sam, self.jacques)
        Channel = self.env["discuss.channel"].with_user(self.sam)
        group = Channel.create_group([self.france.partner_id.id])
        self.jacques.action_archive()
        with self.assertRaises(AccessError):
            group.add_members(partner_ids=self.jacques.partner_id.ids)
        with self.assertRaises(AccessError):
            Channel.create_group([self.jacques.partner_id.id])
        with self.assertRaises(AccessError):
            Channel.create(
                {
                    "name": "Verger",
                    "channel_type": "group",
                    "channel_member_ids": [
                        Command.create({"partner_id": self.sam.partner_id.id}),
                        Command.create(
                            {"partner_id": self.jacques.partner_id.id}
                        ),
                    ],
                }
            )
        self.jacques.action_unarchive()
        group.add_members(partner_ids=self.jacques.partner_id.ids)
        self.assertIn(
            self.jacques.partner_id, group.sudo().channel_member_ids.partner_id
        )

    def test_strict_group_ignores_archived_link(self):
        """In a strict group, the active link of Sam with France opens it
        to him while her account is active, and no longer once archived."""
        self.workshop.sudo().linkup_start_rule = "strict"
        self._activate(self.sam, self.france)
        self._post(self.workshop)
        self.france.action_archive()
        with self.assertLinkupCode("linkup.start_rule"):
            self._post(self.workshop)
        self.assertFalse(
            self.workshop.with_user(self.sam)._linkup_start_rule_info()[
                "linkup_start_rule_satisfied"
            ]
        )
