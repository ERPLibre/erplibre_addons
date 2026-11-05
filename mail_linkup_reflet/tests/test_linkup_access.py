# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Access of a LinkUp member: groups, home action, menus (LU-F-001,
LU-NF-008)."""

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestLinkupAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_member = cls.env.ref(
            "mail_linkup_reflet.group_linkup_member"
        )
        cls.group_moderator = cls.env.ref(
            "mail_linkup_reflet.group_linkup_moderator"
        )
        cls.group_admin = cls.env.ref("mail_linkup_reflet.group_linkup_admin")
        cls.home_action = cls.env.ref("mail_linkup_reflet.action_linkup_home")
        cls.discuss_root = cls.env.ref("mail.menu_root_discuss")
        cls.member = mail_new_test_user(
            cls.env,
            login="linkup_sam",
            name="Sam",
            email="sam@example.com",
            groups="mail_linkup_reflet.group_linkup_member",
        )

    def test_groups_chain(self):
        """The member implies an internal user; the levels chain upwards."""
        self.assertIn(
            self.env.ref("base.group_user"), self.group_member.implied_ids
        )
        self.assertIn(self.group_member, self.group_moderator.implied_ids)
        self.assertIn(self.group_moderator, self.group_admin.implied_ids)
        self.assertEqual(
            self.group_member.category_id,
            self.env.ref("mail_linkup_reflet.module_category_linkup"),
        )

    def test_technical_features_for_system_only(self):
        """The technical features follow the system admins, not the users."""
        group_no_one = self.env.ref("base.group_no_one")
        self.assertNotIn(
            group_no_one, self.env.ref("base.group_user").implied_ids
        )
        self.assertIn(
            group_no_one, self.env.ref("base.group_system").implied_ids
        )
        self.assertIn(group_no_one, self.env.ref("base.user_admin").groups_id)

    def test_member_groups(self):
        """A member holds the member group and no technical features."""
        self.assertIn(self.group_member, self.member.groups_id)
        self.assertNotIn(
            self.env.ref("base.group_no_one"), self.member.groups_id
        )
        self.assertNotIn(self.group_moderator, self.member.groups_id)

    def test_member_home_action(self):
        """A new member lands in the Reflet view, the LinkUp home action."""
        self.assertEqual(self.home_action.tag, "linkup.reflet_view")
        self.assertEqual(self.home_action.path, "linkup")
        self.assertEqual(self.member.action_id.id, self.home_action.id)

    def test_member_added_later_gets_home_action(self):
        """Granting the member group to a user sets the home action."""
        user = mail_new_test_user(
            self.env, login="linkup_france", groups="base.group_user"
        )
        self.assertFalse(user.action_id)
        user.write({"groups_id": [Command.link(self.group_member.id)]})
        self.assertEqual(user.action_id.id, self.home_action.id)

    def test_member_menus_discuss_only(self):
        """The app switcher of a member shows Discuss only, LinkUp below."""
        menus = self.env["ir.ui.menu"].with_user(self.member)
        roots = menus.load_menus_root()["children"]
        self.assertEqual(
            [root["id"] for root in roots], [self.discuss_root.id]
        )
        all_menus = menus.load_menus(debug=False)
        menu_ids = {key for key in all_menus if key != "root"}
        for xmlid in ("menu_linkup_root", "menu_linkup_reflet_view"):
            self.assertIn(
                self.env.ref(f"mail_linkup_reflet.{xmlid}").id, menu_ids
            )
        for menu in self.env["ir.ui.menu"].browse(menu_ids):
            self.assertTrue(
                menu.parent_path.startswith(f"{self.discuss_root.id}/"),
                f"menu outside Discuss: {menu.complete_name}",
            )

    def test_system_admin_keeps_other_menus(self):
        """The restriction applies to members, not to system admins."""
        roots = (
            self.env["ir.ui.menu"]
            .with_user(self.env.ref("base.user_admin"))
            .load_menus_root()["children"]
        )
        self.assertGreater(len(roots), 1)

    def test_member_cannot_read_settings(self):
        """A reserved model read by RPC fails for a member."""
        with self.assertRaises(AccessError):
            self.env["res.config.settings"].with_user(self.member).search_read(
                [], ["id"]
            )

    def test_member_refuses_technical_features(self):
        """Granting the technical features to a member is refused."""
        with self.assertRaises(ValidationError):
            self.member.write(
                {
                    "groups_id": [
                        Command.link(self.env.ref("base.group_no_one").id)
                    ]
                }
            )

    def test_member_not_in_general_channel(self):
        """A new member is subscribed to no channel by default."""
        channels = self.env["discuss.channel"].search(
            [("channel_member_ids.partner_id", "=", self.member.partner_id.id)]
        )
        self.assertFalse(
            channels.filtered(lambda c: c.channel_type == "channel")
        )
        general = self.env.ref(
            "mail.channel_all_employees", raise_if_not_found=False
        )
        if general:
            self.assertFalse(general.group_ids)
            self.assertEqual(
                general.group_public_id, self.env.ref("base.group_system")
            )
