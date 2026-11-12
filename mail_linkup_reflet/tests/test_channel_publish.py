# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The access of a plain member to a channel, decided by the owner
(LU-F-112 RM1): on invitation only by default, a linked member adding them
or its invitation link; published, every member reads it and joins it
alone. A LinkUp administrator or the creator of the channel publishes it.
"""

import json

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from .common import MEMBER
from .test_channel_isolation import ADMIN, LinkupChannelCase


@tagged("post_install", "-at_install")
class TestLinkupChannelPublish(LinkupChannelCase):
    def _join(self, user, channel=None):
        channel = channel or self.channel
        channel.with_user(user).add_members(partner_ids=user.partner_id.ids)

    def _publish(self, user, value=True, channel=None):
        (channel or self.channel).with_user(user).write(
            {"linkup_published": value}
        )

    def test_default_on_invitation(self):
        """A channel is not published: Sam reads nothing of it and does
        not join it alone, until a linked member adds him."""
        self.assertFalse(self.channel.linkup_published)
        self.assertEqual(self._reads(self.sam), (False, False, False))
        with self.assertRaises(AccessError):
            self._join(self.sam)
        self.Link._get_or_create(self.sam, self.france).state = "active"
        self.channel.with_user(self.france).add_members(
            partner_ids=self.sam.partner_id.ids
        )
        self.assertEqual(self._reads(self.sam), (True, True, True))

    def test_published_by_a_linkup_administrator(self):
        """A LinkUp administrator publishes the channel: Sam reads its
        name, its description, its members and its messages, then joins
        it alone."""
        linkup_admin = mail_new_test_user(
            self.env,
            login="linkup_cp_admin",
            name="Henri",
            email="linkup_cp_admin@example.com",
            groups=f"{MEMBER},{ADMIN}",
        )
        self._publish(linkup_admin)
        self.assertTrue(self.channel.linkup_published)
        self.assertEqual(self._reads(self.sam), (True, True, True))
        self.assertTrue(
            self.channel.with_user(self.sam).read(["name", "description"])
        )
        self._join(self.sam)
        self.assertIn(
            self.sam.partner_id, self.channel.channel_member_ids.partner_id
        )

    def test_published_by_its_creator(self):
        """Thomas, an internal user outside LinkUp, creates a channel, of
        which he is the administrator, and publishes it; France, a member
        of it who did not create it, can neither publish nor unpublish
        it."""
        thomas = mail_new_test_user(
            self.env,
            login="linkup_cp_thomas",
            name="Thomas",
            email="linkup_cp_thomas@example.com",
            groups="base.group_user",
        )
        channel = (
            self.env["discuss.channel"]
            .with_user(thomas)
            .create(
                {
                    "name": "Course du samedi",
                    "channel_type": "channel",
                    "group_public_id": self.env.ref("base.group_user").id,
                }
            )
        )
        self.assertTrue(channel.with_user(thomas).linkup_can_publish)
        self._publish(thomas, channel=channel)
        self.assertTrue(channel.linkup_published)
        self._join(self.france, channel)
        self.assertFalse(channel.with_user(self.france).linkup_can_publish)
        with self.assertRaises(AccessError):
            self._publish(self.france, False, channel=channel)
        with self.assertRaises(AccessError):
            channel.with_user(self.france).sudo().write(
                {"linkup_published": False}
            )
        self.assertTrue(channel.linkup_published)

    def test_plain_member_cannot_publish(self):
        """France, a plain member of the channel she did not create, does
        not publish it."""
        self.assertFalse(
            self.channel.with_user(self.france).linkup_can_publish
        )
        with self.assertRaises(AccessError):
            self._publish(self.france)
        self.assertFalse(self.channel.linkup_published)

    def test_unpublished_keeps_its_members(self):
        """Once unpublished, Sam, who joined it, stays and reads it;
        Jacques, a newcomer, needs an invitation again."""
        self._publish(self.admin)
        self._join(self.sam)
        self._publish(self.admin, False)
        self.assertEqual(self._reads(self.sam), (True, True, True))
        self.assertEqual(self._reads(self.jacques), (False, False, False))
        with self.assertRaises(AccessError):
            self._join(self.jacques)

    def test_chats_and_groups_unchanged(self):
        """A group conversation keeps the reading of its members."""
        self.assertEqual(
            self._reads(self.luce, self.workshop), (False, False, False)
        )


@tagged("post_install", "-at_install")
class TestLinkupChannelInvitationLink(LinkupChannelCase, HttpCase):
    """The invitation link of a channel lets a plain member in with the
    token of that channel only."""

    def _call_kw(self, model, method, args, kwargs=None):
        response = self.url_open(
            f"/web/dataset/call_kw/{model}/{method}",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {
                        "model": model,
                        "method": method,
                        "args": args,
                        "kwargs": kwargs or {},
                    },
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        return response.json()

    def test_join_by_the_invitation_link(self):
        """Sam opens the link with the token of the channel: he joins it,
        and reads it."""
        self.authenticate(self.sam.login, self.sam.login)
        response = self.url_open(
            f"/chat/{self.channel.id}/{self.channel.sudo().uuid}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            self.sam.partner_id, self.channel.channel_member_ids.partner_id
        )
        self.assertEqual(self._reads(self.sam), (True, True, True))

    def test_wrong_or_missing_token(self):
        """A wrong token, the token of another channel or none joins
        nobody."""
        other = self._open_channel("Autre", MEMBER)
        self.authenticate(self.sam.login, self.sam.login)
        for url in (
            f"/chat/{self.channel.id}/not-its-token",
            f"/chat/{self.channel.id}/{other.sudo().uuid}",
            f"/chat/{self.channel.id}",
        ):
            with self.subTest(url=url):
                response = self.url_open(url)
                self.assertEqual(response.status_code, 404)
        self.assertNotIn(
            self.sam.partner_id, self.channel.channel_member_ids.partner_id
        )

    def test_plain_member_cannot_publish_by_rpc(self):
        """France calls ``write`` on the channel she belongs to: refused,
        the channel stays unpublished."""
        self.authenticate(self.france.login, self.france.login)
        result = self._call_kw(
            "discuss.channel",
            "write",
            [[self.channel.id], {"linkup_published": True}],
        )
        self.assertIn("error", result)
        self.assertFalse(self.channel.linkup_published)

    def test_settings_form_holds_the_field(self):
        """ "Channel settings" of Discuss, the form of the channel, holds
        the publication, read-only to whoever may not change it."""
        arch = self.env["discuss.channel"].get_views([(False, "form")])[
            "views"
        ]["form"]["arch"]
        self.assertIn('name="linkup_published"', arch)
        self.assertIn('name="linkup_can_publish"', arch)
