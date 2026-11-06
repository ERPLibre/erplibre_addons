# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The context a client sends changes neither what a member reads nor what
the server writes (LU-NF-001, LU-NF-004): ``active_test`` turned off,
``default_<field>`` keys and the other keys of a call are dropped at the
entry of the public methods, and the records the server writes ignore the
defaults of the context. The conflicts of interest of the moderation bind
the administrators too, and a block stays unknown to the moderator it
holds (LU-F-114 RM3, LU-F-115 RM2, LU-F-116 RM5)."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import LinkupRefletCase

ADMIN = "mail_linkup_reflet.group_linkup_admin"
MODERATOR = "mail_linkup_reflet.group_linkup_moderator"
# What a client may add to the context of a call to widen it.
WIDENING_CONTEXT = {
    "active_test": False,
    "default_urgent": True,
    "default_auto_generated": True,
    "default_state": "dismissed",
    "default_phantom": True,
}


@tagged("post_install", "-at_install")
class TestLinkupClientContext(LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def user(login, name, group):
            return mail_new_test_user(
                cls.env,
                login=login,
                name=name,
                email=f"{login}@example.com",
                groups=group,
            )

        cls.henri = user("linkup_cc_henri", "Henri", ADMIN)
        cls.joanna = user("linkup_cc_joanna", "Joanna", MODERATOR)
        cls.workshop.add_members(
            partner_ids=(cls.henri | cls.joanna).partner_id.ids
        )
        cls.Report = cls.env["linkup.report"]

    def test_report_ignores_the_defaults_of_the_context(self):
        """LU-F-114 CA3: neither the arguments nor the context of a member
        make a report urgent, automatic or closed; the server writes the
        report with the defaults of its fields."""
        report = self.Report.browse(
            self.Report.with_user(self.sam)
            .with_context(**WIDENING_CONTEXT)
            .action_create_report(user_id=self.france.id, reason="spam")
        )
        self.assertFalse(report.urgent)
        self.assertFalse(report.auto_generated)
        self.assertEqual(report.state, "new")
        created = (
            self.Report.sudo()
            .with_context(**WIDENING_CONTEXT)
            .create({"reported_user_id": self.france.id, "reason": "spam"})
        )
        self.assertFalse(created.urgent)
        self.assertEqual(created.state, "new")

    def test_archived_member_stays_out_of_reach(self):
        """``active_test`` turned off by the client neither lists an
        archived member among the contacts nor lets a reflection reach
        them."""
        Reflet = self.Reflet.with_user(self.sam).with_context(
            active_test=False
        )
        contacts = Reflet.linkup_reflet_view_info()["contacts"]
        self.assertIn(self.jacques.id, [c["user_id"] for c in contacts])
        self.jacques.active = False
        contacts = Reflet.linkup_reflet_view_info()["contacts"]
        self.assertNotIn(self.jacques.id, [c["user_id"] for c in contacts])
        draft = self._draft()
        with self.assertLinkupCode("linkup.unavailable"):
            draft.with_user(self.sam).with_context(
                active_test=False
            ).action_send(self.jacques.id)
        self.assertEqual(draft.state, "draft")

    def test_reflection_ignores_the_defaults_of_the_context(self):
        """A draft saved and sent with ``default_phantom`` in its context
        still reaches its recipient."""
        Reflet = self.Reflet.with_user(self.sam).with_context(
            **WIDENING_CONTEXT
        )
        draft = self.Reflet.browse(
            Reflet.action_save_draft(
                {
                    "category_id": self.needs.id,
                    "you_said": "Que tu cherches du temps pour ton jardin.",
                    "understood": "Que tu as besoin de calme.",
                    "real_world_declared": True,
                }
            )
        )
        self.assertFalse(draft.phantom)
        draft.with_user(self.sam).with_context(**WIDENING_CONTEXT).action_send(
            self.france.id
        )
        self.assertFalse(draft.phantom)
        self.assertEqual(draft.state, "sent")
        self.assertTrue(draft.message_id)

    def test_conflict_of_interest_binds_the_administrator(self):
        """A report about a LinkUp administrator is out of their reach:
        they neither read it, nor learn who made it, nor process or delete
        it; a report without a conflict stays theirs to manage."""
        about_henri = self.Report.browse(
            self.Report.with_user(self.sam).action_create_report(
                user_id=self.henri.id, reason="harassment"
            )
        )
        other = self.Report.browse(
            self.Report.with_user(self.sam).action_create_report(
                user_id=self.france.id, reason="harassment"
            )
        )
        Report = self.Report.with_user(self.henri)
        self.assertEqual(
            Report.search([("id", "in", (about_henri | other).ids)]), other
        )
        with self.assertRaises(AccessError):
            about_henri.with_user(self.henri).write({"state": "dismissed"})
        with self.assertRaises(AccessError):
            about_henri.with_user(self.henri).unlink()
        self.assertEqual(about_henri.state, "new")
        other.with_user(self.henri).write({"state": "dismissed"})
        self.assertEqual(other.state, "dismissed")

    def test_moderator_does_not_read_a_block_held_on_them(self):
        """LU-F-115 RM2: a moderator reads the blocks of the others, never
        one a member holds on them."""
        Block = self.env["linkup.block"]
        Block.with_user(self.sam).action_block(self.joanna.id)
        Block.with_user(self.france).action_block(self.jacques.id)
        on_joanna = Block.sudo().search([("blocked_id", "=", self.joanna.id)])
        between_others = Block.sudo().search(
            [("blocked_id", "=", self.jacques.id)]
        )
        self.assertTrue(on_joanna and between_others)
        visible = Block.with_user(self.joanna).search([])
        self.assertIn(between_others, visible)
        self.assertNotIn(on_joanna, visible)
        self.assertFalse(
            Block.with_user(self.joanna).search_count(
                [("blocked_id", "=", self.joanna.id)]
            )
        )
