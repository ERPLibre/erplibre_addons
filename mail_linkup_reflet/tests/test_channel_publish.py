# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The access of a plain member to a channel, decided by the owner
(LU-F-112 RM1): on invitation only by default, a linked member adding them
or its invitation link; published, every member reads it and joins it
alone. A LinkUp administrator or the creator of the channel publishes it.
"""

import json

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from .common import MEMBER
from .test_channel_isolation import ADMIN, LinkupChannelCase


def outside_group(env):
    """A group created by Thomas with Paule, two internal users outside
    LinkUp."""
    thomas, paule = (
        mail_new_test_user(
            env,
            login=login,
            name=name,
            email=f"{login}@example.com",
            groups="base.group_user",
        )
        for login, name in (
            ("linkup_cp_out_thomas", "Thomas"),
            ("linkup_cp_out_paule", "Paule"),
        )
    )
    return (
        env["discuss.channel"]
        .with_user(thomas)
        .create_group(partners_to=paule.partner_id.ids, name="Réunion")
    )


def linkup_admin(env, login):
    """Henri, a LinkUp administrator who is not a system administrator."""
    return mail_new_test_user(
        env,
        login=login,
        name="Henri",
        email=f"{login}@example.com",
        groups=f"{MEMBER},{ADMIN}",
    )


def portal_user(env):
    """Pia, a portal user."""
    return mail_new_test_user(
        env,
        login="linkup_cp_portal_pia",
        name="Pia",
        email="linkup_cp_portal_pia@example.com",
        groups="base.group_portal",
    )


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

    def test_plain_member_cannot_create_a_published_thread(self):
        """France, a plain member of the channel, creates a thread of it
        already published: refused, a thread follows its channel. Without
        the publication, the thread opens."""
        vals = {
            "name": "Fil",
            "channel_type": "channel",
            "parent_channel_id": self.channel.id,
        }
        Channel = self.env["discuss.channel"].with_user(self.france)
        with self.assertRaises(AccessError):
            Channel.create(dict(vals, linkup_published=True))
        with self.assertRaises(AccessError):
            Channel.sudo().create(dict(vals, linkup_published=True))
        with self.assertRaises(AccessError):
            Channel.with_context(default_linkup_published=True).create(vals)
        with self.assertRaises(AccessError):
            Channel.sudo().with_context(
                default_linkup_published=True,
                default_parent_channel_id=self.channel.id,
            ).create({"name": "Fil", "channel_type": "channel"})
        thread = Channel.create(vals)
        self.assertFalse(thread.linkup_published)
        self.assertEqual(self._reads(self.sam, thread), (False, False, False))

    def test_plain_member_cannot_create_a_published_group(self):
        """France creates a group published through the defaults of the
        context: refused, a group is never published."""
        Channel = self.env["discuss.channel"].with_user(self.france)
        with self.assertRaises(AccessError):
            Channel.with_context(default_linkup_published=True).create(
                {"name": "Cercle publié", "channel_type": "group"}
            )
        with self.assertRaises(AccessError):
            Channel.with_context(
                default_linkup_published=True, default_channel_type="group"
            ).create({"name": "Cercle publié"})
        self.assertFalse(
            self.env["discuss.channel"].search(
                [("name", "=", "Cercle publié")]
            )
        )

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

    def test_nobody_joins_a_group_alone(self):
        """Luce, linked to none of the members of a group, does not enter
        it by herself, under ``sudo`` as the invitation link adds her, and
        an anonymous visitor does not enter it as a guest."""
        with self.assertRaises(AccessError):
            self.workshop.with_user(self.luce).sudo().add_members(
                partner_ids=self.luce.partner_id.ids
            )
        guest = self.env["mail.guest"].create({"name": "Visiteur"})
        public = self.env.ref("base.public_user")
        with self.assertRaises(AccessError):
            self.workshop.with_user(public).sudo().add_members(
                guest_ids=guest.ids
            )
        members = self.workshop.channel_member_ids
        self.assertNotIn(self.luce.partner_id, members.partner_id)
        self.assertFalse(members.guest_id)

    def test_linkup_administrator_adds_a_guest(self):
        """A LinkUp administrator adds a guest to a group of members, under
        ``sudo`` as the invitation link does."""
        linkup_admin = mail_new_test_user(
            self.env,
            login="linkup_cp_guest_admin",
            name="Henri",
            email="linkup_cp_guest_admin@example.com",
            groups=f"{MEMBER},{ADMIN}",
        )
        guest = self.env["mail.guest"].create({"name": "Visiteur"})
        self.workshop.with_user(linkup_admin).sudo().add_members(
            guest_ids=guest.ids
        )
        self.assertIn(guest, self.workshop.channel_member_ids.guest_id)

    def test_plain_member_kept_from_a_group_with_a_guest(self):
        """An anonymous visitor joins the meeting of Thomas, an internal
        user outside LinkUp, as a guest; Thomas then adds Sam, a plain
        member: refused, the guest would read him. A new group of Thomas
        takes Sam and a guest in the same creation as little. The
        administrator adds Sam."""
        group = outside_group(self.env)
        thomas = group.create_uid
        guest = self.env["mail.guest"].create({"name": "Visiteur"})
        public = self.env.ref("base.public_user")
        group.with_user(public).sudo().add_members(guest_ids=guest.ids)
        with self.assertRaises(AccessError):
            group.with_user(thomas).add_members(
                partner_ids=self.sam.partner_id.ids
            )
        with self.assertRaises(AccessError):
            self.env["discuss.channel"].with_user(thomas).sudo().create(
                {
                    "name": "Réunion mixte",
                    "channel_type": "group",
                    "channel_member_ids": [
                        Command.create({"partner_id": self.sam.partner_id.id}),
                        Command.create({"guest_id": guest.id}),
                    ],
                }
            )
        self.assertNotIn(
            self.sam.partner_id, group.channel_member_ids.partner_id
        )
        group.with_user(self.admin).add_members(
            partner_ids=self.sam.partner_id.ids
        )
        self.assertIn(self.sam.partner_id, group.channel_member_ids.partner_id)

    def test_linkup_administrator_creates_a_channel(self):
        """Henri, a LinkUp administrator who is not a system
        administrator, creates a channel from "Add a channel" of Discuss,
        and without a type."""
        linkup_admin = mail_new_test_user(
            self.env,
            login="linkup_cp_creator_admin",
            name="Henri",
            email="linkup_cp_creator_admin@example.com",
            groups=f"{MEMBER},{ADMIN}",
        )
        self.assertFalse(linkup_admin.has_group("base.group_system"))
        Channel = self.env["discuss.channel"].with_user(linkup_admin)
        Channel.channel_create("Atelier", None)
        place = Channel.create({"name": "Place"})
        self.assertEqual(place.channel_type, "channel")
        self.assertTrue(
            self.env["discuss.channel"].search(
                [("name", "=", "Atelier"), ("channel_type", "=", "channel")]
            )
        )

    def test_outsiders_kept_from_a_group_of_members(self):
        """Pia, a portal user, does not enter a group of members by herself,
        under ``sudo`` as the invitation link adds her; Thomas, an internal
        user outside LinkUp, adds neither her nor a contact without a user
        to it."""
        pia = portal_user(self.env)
        contact = self.env["res.partner"].create({"name": "Contact"})
        thomas = outside_group(self.env).create_uid
        with self.assertRaises(AccessError):
            self.workshop.with_user(pia).sudo().add_members(
                partner_ids=pia.partner_id.ids
            )
        for partner in (pia.partner_id, contact):
            with self.subTest(partner=partner.name):
                with self.assertRaises(AccessError):
                    self.workshop.with_user(thomas).sudo().add_members(
                        partner_ids=partner.ids
                    )
        partners = self.workshop.channel_member_ids.partner_id
        self.assertNotIn(pia.partner_id, partners)
        self.assertNotIn(contact, partners)

    def test_plain_member_kept_from_a_group_with_a_portal_user(self):
        """Thomas adds Pia, a portal user, to his meeting, as ``mail``
        does; he then adds Sam, a plain member: refused. A new group of
        Thomas takes Sam and Pia in the same creation as little. The
        administrator adds Sam."""
        pia = portal_user(self.env)
        group = outside_group(self.env)
        thomas = group.create_uid
        group.with_user(thomas).add_members(partner_ids=pia.partner_id.ids)
        self.assertIn(pia.partner_id, group.channel_member_ids.partner_id)
        with self.assertRaises(AccessError):
            group.with_user(thomas).add_members(
                partner_ids=self.sam.partner_id.ids
            )
        with self.assertRaises(AccessError):
            self.env["discuss.channel"].with_user(thomas).create_group(
                partners_to=(self.sam.partner_id | pia.partner_id).ids
            )
        self.assertNotIn(
            self.sam.partner_id, group.channel_member_ids.partner_id
        )
        group.with_user(self.admin).add_members(
            partner_ids=self.sam.partner_id.ids
        )
        self.assertIn(self.sam.partner_id, group.channel_member_ids.partner_id)

    def test_linkup_administrator_populates_a_channel(self):
        """Henri, a LinkUp administrator who is not a system administrator,
        creates a channel and adds Sam and Luce, linked to nobody, then
        opens a group and a direct conversation with Luce."""
        henri = linkup_admin(self.env, "linkup_cp_populate_admin")
        Channel = self.env["discuss.channel"].with_user(henri)
        place = Channel.create({"name": "Place"})
        place.add_members(partner_ids=(self.sam | self.luce).partner_id.ids)
        self.assertEqual(
            place.channel_member_ids.partner_id,
            (henri | self.sam | self.luce).partner_id,
        )
        group = Channel.create_group(partners_to=self.luce.partner_id.ids)
        self.assertIn(
            self.luce.partner_id, group.channel_member_ids.partner_id
        )
        chat = Channel.channel_get(self.luce.partner_id.ids)
        self.assertEqual(
            chat.channel_member_ids.partner_id,
            (henri | self.luce).partner_id,
        )

    def test_linkup_administrator_talks_without_a_reflection(self):
        """In a ``strict`` direct conversation with Luce, linked to nobody,
        Henri, a LinkUp administrator who is not a system administrator,
        writes and starts a call: the start rule binds plain members only,
        and a pair holding one of them reads it satisfied, as it does with
        a system administrator."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.start_rule_mode", "strict"
        )
        henri = linkup_admin(self.env, "linkup_cp_talk_admin")
        chat = (
            self.env["discuss.channel"]
            .with_user(henri)
            .channel_get(self.luce.partner_id.ids)
        )
        self.assertFalse(chat._linkup_start_rule_blocks(henri))
        self.assertFalse(chat._linkup_start_rule_blocks(self.luce))
        chat.with_user(henri).message_post(
            body="Bonjour", message_type="comment"
        )
        member = chat.sudo().channel_member_ids.filtered(
            lambda m: m.partner_id == henri.partner_id
        )
        member.with_user(henri).sudo()._rtc_join_call()
        self.assertTrue(chat.sudo().rtc_session_ids)

    def test_linkup_administrator_meets_an_outsider(self):
        """Henri starts a meeting with Thomas, an internal user outside
        LinkUp, and Pia, a portal user, then adds a guest to it."""
        henri = linkup_admin(self.env, "linkup_cp_outsider_admin")
        thomas = outside_group(self.env).create_uid
        pia = portal_user(self.env)
        meeting = (
            self.env["discuss.channel"]
            .with_user(henri)
            .create_group(
                partners_to=(thomas | pia).partner_id.ids,
                default_display_mode="video_full_screen",
            )
        )
        guest = self.env["mail.guest"].create({"name": "Visiteur"})
        meeting.with_user(henri).add_members(guest_ids=guest.ids)
        members = meeting.channel_member_ids
        self.assertEqual(members.partner_id, (henri | thomas | pia).partner_id)
        self.assertEqual(members.guest_id, guest)

    def test_group_without_members_takes_a_guest(self):
        """A group of internal users outside LinkUp takes a guest added by
        an anonymous visitor, as ``mail`` does for a meeting."""
        group = outside_group(self.env)
        guest = self.env["mail.guest"].create({"name": "Visiteur"})
        public = self.env.ref("base.public_user")
        group.with_user(public).sudo().add_members(guest_ids=guest.ids)
        self.assertIn(guest, group.channel_member_ids.guest_id)


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

    def test_group_invitation_link_opens_nothing(self):
        """The link of a group conversation lets in neither Luce, a member
        linked to none of its members, nor an anonymous visitor: a group
        takes a member from a linked member of it only."""
        url = f"/chat/{self.workshop.id}/{self.workshop.sudo().uuid}"
        self.assertEqual(self.url_open(url).status_code, 404)
        self.authenticate(self.luce.login, self.luce.login)
        self.assertEqual(self.url_open(url).status_code, 404)
        members = self.workshop.sudo().channel_member_ids
        self.assertNotIn(self.luce.partner_id, members.partner_id)
        self.assertFalse(members.guest_id)

    def test_member_of_the_group_opens_its_link(self):
        """Sam, a member of the group, opens its link: the page of
        ``mail`` shows it, and the members stay the same."""
        members = self.workshop.sudo().channel_member_ids
        self.authenticate(self.sam.login, self.sam.login)
        response = self.url_open(
            f"/chat/{self.workshop.id}/{self.workshop.sudo().uuid}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workshop.sudo().channel_member_ids, members)

    def test_meeting_link_of_internal_users_takes_a_guest(self):
        """An anonymous visitor opens the link of a group of internal users
        outside LinkUp, as "Start a meeting" shares it: ``mail`` adds them
        as a guest."""
        group = outside_group(self.env)
        response = self.url_open(group.invitation_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(group.sudo().channel_member_ids.guest_id)

    def test_meeting_link_of_administrators_takes_a_guest(self):
        """An anonymous visitor opens the link of a meeting of the default
        administrator with an internal user outside LinkUp, then of two of
        a LinkUp administrator, alone and with that user: ``mail`` adds
        them as a guest, no plain member belongs to any."""
        henri = linkup_admin(self.env, "linkup_cp_meeting_admin")
        outsider = outside_group(self.env).create_uid
        Channel = self.env["discuss.channel"]
        for creator, partners in (
            (self.admin, outsider.partner_id.ids),
            (henri, []),
            (henri, outsider.partner_id.ids),
        ):
            with self.subTest(creator=creator.name):
                group = Channel.with_user(creator).create_group(
                    partners_to=partners, name="Réunion"
                )
                response = self.url_open(group.invitation_url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(group.sudo().channel_member_ids.guest_id)

    def test_portal_user_kept_from_a_group_of_members(self):
        """Pia, a portal user, opens the link of a group that holds plain
        members: not found, and she does not join it. The link of a group
        of internal users outside LinkUp adds her, as ``mail`` does."""
        pia = portal_user(self.env)
        self.authenticate(pia.login, pia.login)
        response = self.url_open(
            f"/chat/{self.workshop.id}/{self.workshop.sudo().uuid}"
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(
            pia.partner_id, self.workshop.sudo().channel_member_ids.partner_id
        )
        group = outside_group(self.env)
        response = self.url_open(group.invitation_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            pia.partner_id, group.sudo().channel_member_ids.partner_id
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
