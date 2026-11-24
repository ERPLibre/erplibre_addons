# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""A channel opened to a group is read by its members only (LU-F-112 RM1,
LU-F-063 RM2).

The channel "Rencontres" is opened to the member group, and France and Luce
belong to it. Sam belongs to none: he reads neither the channel, nor its
members, nor its messages, and does not join it by himself. A LinkUp
administrator, or a member of it with whom he shares an ``active`` link,
adds him.
"""

import json

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from .common import MEMBER, LinkupRefletCase

ADMIN = "mail_linkup_reflet.group_linkup_admin"


class LinkupChannelCase(LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.channel = cls._open_channel("Rencontres", MEMBER)
        cls.channel.with_user(cls.france).message_post(
            body="Bienvenue",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    @classmethod
    def _open_channel(cls, name, group):
        return (
            cls.env["discuss.channel"]
            .with_user(cls.admin)
            .create(
                {
                    "name": name,
                    "channel_type": "channel",
                    "group_public_id": cls.env.ref(group).id,
                    "channel_partner_ids": [
                        Command.link(cls.france.partner_id.id),
                        Command.link(cls.luce.partner_id.id),
                    ],
                }
            )
        )

    def _reads(self, user, channel=None):
        """Whether ``user`` reads the channel, its members and its
        messages; each answer apart."""
        channel = channel or self.channel
        self.env.invalidate_all()
        Channel = self.env["discuss.channel"].with_user(user)
        members = (
            self.env["discuss.channel.member"]
            .with_user(user)
            .search([("channel_id", "=", channel.id)])
        )
        messages = (
            self.env["mail.message"]
            .with_user(user)
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", channel.id),
                    ("message_type", "=", "comment"),
                ]
            )
        )
        return (
            bool(Channel.search([("id", "=", channel.id)])),
            bool(members),
            bool(messages),
        )


@tagged("post_install", "-at_install")
class TestLinkupChannelIsolation(LinkupChannelCase):
    def test_outsider_reads_nothing(self):
        """Sam reads neither the channel, nor its member list, nor its
        messages, whether it is opened to the members or to every internal
        user; Luce stays out of his scope."""
        open_to_all = self._open_channel("Grand public", "base.group_user")
        for channel in (self.channel, open_to_all):
            with self.subTest(channel=channel.name):
                self.assertEqual(
                    self._reads(self.sam, channel), (False, False, False)
                )
                with self.assertRaises(AccessError):
                    channel.with_user(self.sam).read(["name"])
                rows = (
                    self.env["discuss.channel.member"]
                    .with_user(self.sam)
                    .search_read(
                        [("channel_id", "=", channel.id)], ["partner_id"]
                    )
                )
                self.assertFalse(rows)
        self.assertNotIn(
            self.luce.partner_id,
            self.env["res.partner"].with_user(self.sam).search([]),
        )

    def test_members_read_it(self):
        """France and Luce read their channel, and each other."""
        self.assertEqual(self._reads(self.france), (True, True, True))
        self.assertIn(
            self.luce.partner_id,
            self.env["res.partner"].with_user(self.france).search([]),
        )

    def test_no_join_by_oneself(self):
        """Sam does not join the channel by himself, through
        ``add_members`` nor by creating his member row."""
        with self.assertRaises(AccessError):
            self.channel.with_user(self.sam).add_members(
                partner_ids=self.sam.partner_id.ids
            )
        with self.assertRaises(AccessError):
            self.env["discuss.channel.member"].with_user(self.sam).create(
                {
                    "channel_id": self.channel.id,
                    "partner_id": self.sam.partner_id.id,
                }
            )
        self.assertNotIn(
            self.sam.partner_id, self.channel.channel_member_ids.partner_id
        )

    def test_added_by_an_administrator(self):
        """Once a LinkUp administrator adds him, Sam reads the channel, its
        members and its messages, and Luce enters his scope."""
        self.channel.with_user(self.admin).add_members(
            partner_ids=self.sam.partner_id.ids
        )
        self.assertEqual(self._reads(self.sam), (True, True, True))
        self.assertIn(
            self.luce.partner_id,
            self.env["res.partner"].with_user(self.sam).search([]),
        )

    def test_added_by_a_linked_member(self):
        """France adds Sam once their link is active, and not before."""
        Channel = self.channel.with_user(self.france)
        with self.assertRaises(AccessError):
            Channel.add_members(partner_ids=self.sam.partner_id.ids)
        self.Link._get_or_create(self.sam, self.france).state = "active"
        Channel.add_members(partner_ids=self.sam.partner_id.ids)
        self.assertEqual(self._reads(self.sam), (True, True, True))

    def test_thread_of_a_channel(self):
        """A thread is read and joined by the members of its channel, and
        stays closed to the others."""
        self.channel.with_user(self.admin).add_members(
            partner_ids=self.sam.partner_id.ids
        )
        thread = self.channel.with_user(self.france)._create_sub_channel(
            name="Fil"
        )
        self.assertTrue(self._reads(self.sam, thread)[0])
        thread.with_user(self.sam).add_members(
            partner_ids=self.sam.partner_id.ids
        )
        self.assertIn(
            self.sam.partner_id, thread.channel_member_ids.partner_id
        )
        self.assertFalse(self._reads(self.jacques, thread)[0])
        with self.assertRaises(AccessError):
            thread.with_user(self.jacques).add_members(
                partner_ids=self.jacques.partner_id.ids
            )

    def test_administrators_and_other_users_read_it(self):
        """System administrators, LinkUp administrators and internal users
        outside LinkUp keep the native reading of an open channel."""
        linkup_admin = mail_new_test_user(
            self.env,
            login="linkup_ci_admin",
            name="Jacques administrateur",
            email="linkup_ci_admin@example.com",
            groups=f"{MEMBER},{ADMIN}",
        )
        employee = mail_new_test_user(
            self.env,
            login="linkup_ci_employee",
            name="Thomas",
            email="linkup_ci_employee@example.com",
            groups="base.group_user",
        )
        open_to_all = self._open_channel("Grand public", "base.group_user")
        self.assertEqual(self._reads(self.admin), (True, True, True))
        self.assertEqual(self._reads(linkup_admin), (True, True, True))
        self.assertEqual(
            self._reads(employee, open_to_all), (True, True, False)
        )

    def test_direct_conversations_unchanged(self):
        """A group conversation keeps the native reading: its members."""
        self.assertEqual(
            self._reads(self.sam, self.workshop)[:2], (True, True)
        )
        self.assertEqual(
            self._reads(self.luce, self.workshop), (False, False, False)
        )


@tagged("post_install", "-at_install")
class TestLinkupChannelIsolationRoutes(LinkupChannelCase, HttpCase):
    """The routes of Discuss give Sam nothing of a channel he does not
    belong to, and a wrong token of its invitation link does not let him
    in."""

    def test_routes(self):
        self.authenticate(self.sam.login, self.sam.login)
        for route, params in (
            (
                "/discuss/channel/members",
                {"channel_id": self.channel.id, "known_member_ids": []},
            ),
            ("/discuss/channel/messages", {"channel_id": self.channel.id}),
            ("/discuss/channel/info", {"channel_id": self.channel.id}),
        ):
            with self.subTest(route=route):
                response = self.url_open(
                    route,
                    data=json.dumps(
                        {"jsonrpc": "2.0", "method": "call", "params": params}
                    ),
                    headers={"Content-Type": "application/json"},
                )
                self.assertNotIn("Luce", response.text)
                self.assertNotIn("Bienvenue", response.text)
        response = self.url_open(f"/chat/{self.channel.id}/not-its-token")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(
            self.sam.partner_id, self.channel.channel_member_ids.partner_id
        )
