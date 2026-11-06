# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Web client of the points: the tour of a sending, its confirmation, the
"+N" it shows and "My points" (LU-F-091, LU-F-103), and the Hoot unit tests
of the module (§12.1)."""

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER
from odoo.addons.web.tests import test_js
from odoo.tests import HttpCase, tagged

from .common import OLD_ACCOUNT_DATE

# Suite of the Hoot tests of the module, as the Hoot runner names it.
HOOT_SUITE = "@mail_linkup_gamification"


@tagged("post_install", "-at_install")
class TestLinkupPointsUi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_CA")
        cls.env["ir.module.module"].search(
            [
                (
                    "name",
                    "in",
                    ("mail_linkup_reflet", "mail_linkup_gamification"),
                )
            ]
        )._update_translations(["fr_CA"])

        def member(login, name):
            return mail_new_test_user(
                cls.env,
                login=login,
                password=login,
                name=name,
                email=f"{login}@example.com",
                groups=MEMBER,
                lang="fr_CA",
                tz="America/Toronto",
            )

        cls.sam = member("linkup_pt_ui_sam", "Sam")
        cls.france = member("linkup_pt_ui_france", "France")
        members = cls.sam | cls.france
        # The first-use tour would cover the screens the other tours use.
        members.write({"linkup_tour_done": True})
        # Accounts younger than 72 hours earn no points.
        members.flush_recordset()
        cls.env.cr.execute(
            "UPDATE res_users SET create_date = %s WHERE id IN %s",
            [OLD_ACCOUNT_DATE, tuple(members.ids)],
        )
        members.invalidate_recordset(["create_date"])
        # A shared group conversation puts each one in the other's scope.
        cls.env["discuss.channel"].create(
            {
                "name": "Atelier",
                "channel_type": "group",
                "channel_member_ids": [
                    Command.create({"partner_id": user.partner_id.id})
                    for user in members
                ],
            }
        )
        cls.chat = (
            cls.env["discuss.channel"]
            .with_user(cls.sam)
            .sudo()
            .channel_get([cls.france.partner_id.id])
            .sudo(False)
        )

    def _lines(self, user):
        return (
            self.env["linkup.points.ledger"]
            .sudo()
            .search([("user_id", "=", user.id)], order="id")
        )

    def test_points_tour(self):
        """Sam sends a reflection to France, who confirms it: "+1000"
        shows at once, and "My points" lists the confirmation; Sam finds
        in his own the confirmation and the sending, never France's
        lines."""
        chat_url = f"/odoo/discuss?active_id=discuss.channel_{self.chat.id}"
        self.start_tour(
            chat_url, "linkup_reflet_send_tour", login=self.sam.login
        )
        self.assertFalse(self._lines(self.sam))
        self.start_tour(
            chat_url, "linkup_points_confirm_tour", login=self.france.login
        )
        self.assertEqual(
            self._lines(self.france).mapped(
                lambda line: (line.rule_id.code, line.points)
            ),
            [("reflect_confirmed", 1000)],
        )
        self.assertEqual(
            sorted(
                self._lines(self.sam).mapped(
                    lambda line: (line.rule_id.code, line.points)
                )
            ),
            [("reflect_confirmed", 1000), ("reflect_sent", 100)],
        )
        self.start_tour(
            "/odoo", "linkup_points_author_tour", login=self.sam.login
        )
        self.assertEqual(self.sam.sudo().karma, 1100)
        self.assertEqual(self.france.sudo().karma, 1000)


@tagged("post_install", "-at_install")
class TestLinkupPointsHoot(HttpCase):
    def test_hoot_suite(self):
        """The Hoot tests of the module, in a desktop browser."""
        suite_id = test_js.HOOTCommon._generate_hash(self, HOOT_SUITE)
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000"
            f"&id={suite_id}",
            "",
            "",
            login="admin",
            timeout=1800,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=test_js.unit_test_error_checker,
        )
