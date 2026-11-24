# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from freezegun import freeze_time
from odoo import fields
from odoo.tests import TransactionCase, tagged

DEMO = "mail_linkup_reflet.demo_"
# Half-life of the energy, which mail_linkup_network reads when installed.
HALF_LIFE_PARAM = "linkup.energy_half_life_days"


@tagged("post_install", "-at_install")
class TestPointsDemo(TransactionCase):
    """The demonstration pays its points through the ledger (LU-NF-043)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sam = cls.env.ref(f"{DEMO}user_sam", raise_if_not_found=False)
        if not cls.sam:
            return
        cls.france = cls.env.ref(f"{DEMO}user_france")
        cls.members = (
            cls.env["ir.model.data"]
            .search(
                [
                    ("module", "=", "mail_linkup_reflet"),
                    ("model", "=", "res.users"),
                    ("name", "=like", "demo_user_%"),
                ]
            )
            .mapped(lambda data: cls.env["res.users"].browse(data.res_id))
        )
        cls.Ledger = cls.env["linkup.points.ledger"].sudo()

    def setUp(self):
        super().setUp()
        if not self.sam:
            self.skipTest("The demonstration data is not loaded.")
        # The lines of the demonstration are dated at its installation: the
        # decay of mail_linkup_network off, the energy of a link holds
        # whatever the age of the database.
        self.env["ir.config_parameter"].sudo().set_param(HALF_LIFE_PARAM, "0")

    def _total(self, user):
        return sum(
            self.Ledger.search([("user_id", "=", user.id)]).mapped("points")
        )

    def test_karma_equals_ledger(self):
        """Each member of the demonstration holds the sum of their lines,
        and the daily control reports nobody."""
        self.assertEqual(len(self.members), 11)
        for user in self.members:
            self.assertEqual(user.karma, self._total(user), user.name)
        self.assertEqual(self.Ledger._cron_check_karma(), [])

    def test_demo_content(self):
        """The demonstration gives "My points", the energy of the link and
        the ranks something to show, every line paid in full, and leaves
        the pair Sam-Jacques without points, for the acceptance."""
        self.assertEqual(self.sam.karma, 2700)
        self.assertEqual(self.france.karma, 2250)
        self.assertEqual(self.sam.rank_id.name, "Flame")
        self.assertEqual(self.france.rank_id.name, "Spark")
        lines = self.Ledger.search([("user_id", "in", self.members.ids)])
        self.assertTrue(lines)
        self.assertFalse(lines.filtered("capped"))
        link = self.env.ref(f"{DEMO}link_sam_france").sudo()
        with freeze_time(fields.Datetime.now() + timedelta(days=30)):
            self.assertEqual(link._linkup_energy_for(self.sam), 1950)
            self.assertEqual(link._linkup_energy_for(self.france), 2000)
        fresh = self.env.ref(f"{DEMO}link_sam_jacques")
        self.assertFalse(self.Ledger.search([("link_id", "=", fresh.id)]))
        points = self.Ledger.with_user(self.sam).linkup_my_points()
        self.assertEqual(points["balance"], 2700)
        self.assertEqual(
            {line["rule_code"] for line in points["lines"]},
            {
                "reflect_sent",
                "reflect_confirmed",
                "precision_sent",
                "reflect_rejected",
                "call_answered",
            },
        )
        badges = self.env.ref(
            "mail_linkup_gamification.badge_first_reflection"
        ) | self.env.ref("mail_linkup_gamification.badge_first_link")
        self.assertEqual(badges & self.sam.badge_ids.badge_id, badges)
