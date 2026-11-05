# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Isolation of a LinkUp member over contacts and users (R-01, LU-NF-009,
LU-F-112 CA2 and CA3).

Sam and France share a channel; Luce shares none with Sam. Sam reads France
and not Luce, through the ORM and through the people searches of Discuss,
and Discuss keeps working for Sam.
"""

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

MEMBER = "mail_linkup_reflet.group_linkup_member"


def _partner_ids(store_data):
    """Ids of the partners held by the result of a ``Store``."""
    return {vals["id"] for vals in store_data.get("res.partner", [])}


@tagged("post_install", "-at_install")
class TestLinkupIsolation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sam = mail_new_test_user(
            cls.env,
            login="linkup_iso_sam",
            name="Sam",
            email="sam@example.com",
            groups=MEMBER,
        )
        cls.luce = mail_new_test_user(
            cls.env,
            login="linkup_iso_luce",
            name="Luce",
            email="luce@example.com",
            groups=MEMBER,
        )
        cls.france = mail_new_test_user(
            cls.env,
            login="linkup_iso_france",
            name="France",
            email="france@example.com",
            groups=MEMBER,
        )
        cls.admin = cls.env.ref("base.user_admin")
        Channel = cls.env["discuss.channel"]
        # A channel opened to the members names its group: without one, a
        # new channel is kept to the LinkUp administrators.
        cls.channel_shared = Channel.create(
            {
                "name": "Atelier",
                "channel_type": "channel",
                "group_public_id": cls.env.ref(MEMBER).id,
                "channel_partner_ids": [
                    Command.link(cls.sam.partner_id.id),
                    Command.link(cls.france.partner_id.id),
                ],
            }
        )
        cls.channel_other = Channel.create(
            {
                "name": "Jardin",
                "channel_type": "channel",
                "channel_partner_ids": [
                    Command.link(cls.luce.partner_id.id),
                    Command.link(cls.admin.partner_id.id),
                ],
            }
        )

    # ORM reads

    def test_member_search_returns_own_scope(self):
        """A member lists themself, their channel peers and their company."""
        partners = self.env["res.partner"].with_user(self.sam).search([])
        self.assertIn(self.sam.partner_id, partners)
        self.assertIn(self.france.partner_id, partners)
        self.assertIn(self.env.company.partner_id, partners)
        self.assertNotIn(self.luce.partner_id, partners)
        self.assertNotIn(self.admin.partner_id, partners)
        users = self.env["res.users"].with_user(self.sam).search([])
        self.assertEqual(users, self.sam | self.france)

    def test_member_search_read_users_hides_outsiders(self):
        """``search_read`` of users returns no login or email of outsiders."""
        rows = (
            self.env["res.users"]
            .with_user(self.sam)
            .search_read([], ["login", "email"])
        )
        logins = {row["login"] for row in rows}
        emails = {row["email"] for row in rows}
        self.assertNotIn(self.luce.login, logins)
        self.assertNotIn(self.admin.login, logins)
        self.assertNotIn("luce@example.com", emails)

    def test_member_cannot_read_outsider(self):
        """Reading an outsider by id is refused, user and partner alike."""
        with self.assertRaises(AccessError):
            self.luce.partner_id.with_user(self.sam).read(["name"])
        with self.assertRaises(AccessError):
            self.luce.with_user(self.sam).read(["name"])
        found = (
            self.env["res.partner"]
            .with_user(self.sam)
            .search([("email", "=", "luce@example.com")])
        )
        self.assertFalse(found)

    def test_member_reads_channel_peer(self):
        """A member reads the people of a channel they belong to."""
        partner = self.france.partner_id.with_user(self.sam)
        self.assertEqual(partner.read(["name"])[0]["name"], "France")
        user = self.france.with_user(self.sam)
        self.assertEqual(user.read(["name"])[0]["name"], "France")

    def test_scope_follows_membership(self):
        """Joining a channel opens its people; leaving closes them."""
        Partner = self.env["res.partner"].with_user(self.sam)
        self.channel_other.add_members(partner_ids=self.sam.partner_id.ids)
        self.assertIn(self.luce.partner_id, Partner.search([]))
        self.channel_other.channel_member_ids.filtered(
            lambda member: member.partner_id == self.sam.partner_id
        ).unlink()
        self.assertNotIn(self.luce.partner_id, Partner.search([]))

    def test_admin_reads_everyone(self):
        """The administrator keeps the native reading of contacts."""
        partners = self.env["res.partner"].with_user(self.admin).search([])
        self.assertIn(self.luce.partner_id, partners)
        self.assertIn(self.france.partner_id, partners)
        users = self.env["res.users"].with_user(self.admin).search([])
        self.assertTrue(self.sam | self.luce | self.france <= users)

    def test_non_member_internal_user_unchanged(self):
        """An internal user outside LinkUp keeps the native reading."""
        employee = mail_new_test_user(
            self.env, login="linkup_iso_employee", groups="base.group_user"
        )
        partners = self.env["res.partner"].with_user(employee).search([])
        self.assertIn(self.luce.partner_id, partners)

    def test_member_cannot_widen_scope_by_invitation(self):
        """Inviting an outsider by id is refused on every Discuss path."""
        Channel = self.env["discuss.channel"].with_user(self.sam)
        luce_id = self.luce.partner_id.id
        with self.assertRaises(AccessError):
            Channel.channel_get([luce_id])
        with self.assertRaises(AccessError):
            Channel.create_group([luce_id])
        with self.assertRaises(AccessError):
            Channel.create(
                {
                    "name": "Verger",
                    "channel_type": "group",
                    "channel_member_ids": [
                        Command.create({"partner_id": self.sam.partner_id.id}),
                        Command.create({"partner_id": luce_id}),
                    ],
                }
            )
        with self.assertRaises(AccessError):
            self.channel_shared.with_user(self.sam).add_members(
                partner_ids=[luce_id]
            )
        self.assertNotIn(
            self.luce.partner_id,
            self.env["res.partner"].with_user(self.sam).search([]),
        )
        # A group takes the people of a confirmed reflection only
        # (LU-F-063 RM1): France, in the scope, joins once the link is
        # active.
        with self.assertRaises(AccessError):
            Channel.create_group([self.france.partner_id.id])
        self.env["linkup.link"]._get_or_create(self.sam, self.france).write(
            {"state": "active"}
        )
        group = Channel.create_group([self.france.partner_id.id])
        self.assertIn(
            self.france.partner_id, group.channel_member_ids.partner_id
        )

    # Discuss searches of people (LU-F-112 CA2)

    def test_im_search_limited(self):
        """The "start a conversation" search stays in the scope."""
        Partner = self.env["res.partner"].with_user(self.sam)
        self.assertFalse(_partner_ids(Partner.im_search("Luce")))
        self.assertEqual(
            _partner_ids(Partner.im_search("")),
            set(self.france.partner_id.ids),
        )

    def test_mention_suggestions_limited(self):
        """The ``@`` suggestions skip outsiders, by name and by email."""
        Partner = self.env["res.partner"].with_user(self.sam)
        luce_id = self.luce.partner_id.id
        for term in ("Luce", "luce@example.com"):
            self.assertNotIn(
                luce_id, _partner_ids(Partner.get_mention_suggestions(term))
            )
            self.assertNotIn(
                luce_id,
                _partner_ids(
                    Partner.get_mention_suggestions_from_channel(
                        self.channel_shared.id, term
                    )
                ),
            )
        self.assertIn(
            self.france.partner_id.id,
            _partner_ids(Partner.get_mention_suggestions("France")),
        )

    def test_channel_invite_search_limited(self):
        """The invitation search counts and returns no outsider."""
        Partner = self.env["res.partner"].with_user(self.sam)
        for term in ("Luce", "luce@example.com"):
            result = Partner.search_for_channel_invite(term)
            self.assertEqual(result["count"], 0)
            self.assertFalse(_partner_ids(result["data"]))
        result = Partner.search_for_channel_invite("France")
        self.assertIn(self.france.partner_id.id, _partner_ids(result["data"]))

    def test_channel_mention_suggestions_limited(self):
        """The ``#`` suggestions list the member's own channels only."""
        Channel = self.env["discuss.channel"].with_user(self.sam)
        self.assertFalse(Channel.get_mention_suggestions("Jardin"))
        found = Channel.get_mention_suggestions("Atelier")
        self.assertEqual(
            [vals["id"] for vals in found], self.channel_shared.ids
        )

    # Discuss stays usable

    def test_discuss_usable_for_member(self):
        """A member loads Discuss, opens a channel, posts and reads back."""
        # The ORM cache is shared between users and skips the access check:
        # emptying it makes every read below hit the record rules.
        self.env.invalidate_all()
        store = Store()
        self.sam._init_store_data(store)
        self.sam._init_messaging(store)
        channel = self.channel_shared.with_user(self.sam)
        Store(channel).get_result()
        self.assertIn(
            self.france.partner_id.id,
            _partner_ids(channel._load_more_members([])),
        )
        self.channel_shared.with_user(self.france).message_post(
            body="Bonjour",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        message = channel.message_post(
            body="Salut",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.assertEqual(message.author_id, self.sam.partner_id)
        messages = (
            self.env["mail.message"]
            .with_user(self.sam)
            ._message_fetch(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", self.channel_shared.id),
                ]
            )["messages"]
        )
        self.assertEqual(len(messages), 2)
        self.env.invalidate_all()
        data = Store(messages, for_current_user=True).get_result()
        self.assertIn(self.france.partner_id.id, _partner_ids(data))

    def test_direct_chat_with_peer(self):
        """A member opens a direct conversation with a channel peer once
        their link is active, and not before (LU-F-063 RM1). The start
        rule, covered by ``test_start_rule``, is off here."""
        self.env["ir.config_parameter"].set_param(
            "linkup.start_rule_mode", "off"
        )
        Channel = self.env["discuss.channel"].with_user(self.sam)
        with self.assertRaises(AccessError):
            Channel.channel_get([self.france.partner_id.id])
        self.env["linkup.link"]._get_or_create(
            self.sam, self.france
        ).state = "active"
        self.env.invalidate_all()
        chat = Channel.channel_get([self.france.partner_id.id])
        self.assertEqual(chat.channel_type, "chat")
        chat.message_post(
            body="Salut",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.env.invalidate_all()
        data = Store(chat).get_result()
        self.assertIn(self.france.partner_id.id, _partner_ids(data))
