# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Collusion: young and unverified accounts, loops of accounts, alerts of
the moderation and minimum duration of a call (§7.3, T-46)."""

from datetime import datetime, timedelta

from freezegun import freeze_time
from odoo.tests import tagged

from .common import LinkupPointsCase

NOON = datetime(2026, 10, 20, 16, 0)


@tagged("post_install", "-at_install")
class TestLinkupPointsAntiAbuse(LinkupPointsCase):
    def _reports(self, user, reason):
        return (
            self.env["linkup.report"]
            .sudo()
            .search(
                [("reported_user_id", "=", user.id), ("reason", "=", reason)]
            )
        )

    def test_young_accounts_earn_nothing(self):
        """§7.3: two accounts younger than 72 hours that confirm each other
        earn nothing, and hear nothing of it; once 72 hours old, they
        do."""
        young = self._new_members(2, "young", age=False)
        self._age_accounts(young, NOON)
        with freeze_time(NOON + timedelta(hours=71)):
            self._bus_reset()
            self._confirmed_by(young[0], young[1])
            lines = self._lines(young[0]) | self._lines(young[1])
            self.assertEqual(set(lines.mapped("points")), {0})
            self.assertEqual(set(lines.mapped("cap_reason")), {"new_account"})
            self.assertFalse(self._awarded(young[0]))
            self.assertFalse(young[0].sudo().badge_ids)
        with freeze_time(NOON + timedelta(hours=73)):
            self._confirmed_by(young[1], young[0])
        self.assertEqual(self._paid(young[1], "reflect_sent"), [100])
        self.assertBalanced(*young)

    def test_penalty_of_a_young_account(self):
        """A penalty applies to a young account too."""
        young = self._new_members(1, "fresh", age=False)
        self._sent_to(young, self.france).with_user(
            self.france
        ).action_reject()
        self.assertEqual(self._paid(young), [-150])

    def test_unverified_account_earns_nothing(self):
        """§7.3: an account that is not verified earns nothing."""
        ResUsers = type(self.env["res.users"])
        self.patch(
            ResUsers,
            "_linkup_points_verified",
            lambda user: user != self.france,
        )
        self._confirmed()
        line = self._lines(self.france)
        self.assertEqual((line.points, line.cap_reason), (0, "unverified"))
        self.assertEqual(self._paid(self.sam), [1000, 100])

    def test_loop_of_three_accounts(self):
        """T-46: three accounts confirming each other in a loop earn the
        confirmation once per pair, ever."""
        trio = self._new_members(3, "trio")
        for day in range(3):
            with freeze_time(NOON + timedelta(days=day)):
                for index in range(3):
                    self._confirmed_by(trio[index], trio[(index + 1) % 3])
        for user in trio:
            self.assertEqual(
                self._paid(user, "reflect_confirmed"),
                [1000, 1000] + [0] * 4,
            )
        self.assertBalanced(*trio)

    def test_pair_confirmations_alert(self):
        """§7.3: past X = 3 confirmations in 7 days, a pair reports both of
        its members to the moderation, once."""
        for day in range(3):
            with freeze_time(NOON + timedelta(days=day)):
                self._confirmed()
        self.assertFalse(self._reports(self.sam, "confirmation_loop"))
        with freeze_time(NOON + timedelta(days=3)):
            self._confirmed()
        with freeze_time(NOON + timedelta(days=4)):
            self._confirmed()
        for user in (self.sam, self.france):
            report = self._reports(user, "confirmation_loop")
            self.assertEqual(len(report), 1)
            self.assertTrue(report.auto_generated)
        self.assertEqual(self.sam.sudo().linkup_suspended_until, False)

    def test_new_account_confirmations_alert(self):
        """§7.3: past Y = 5 confirmations of reflections of accounts younger
        than 48 hours, the member who confirms is reported."""
        young = self._new_members(6, "new", age=False)
        self._age_accounts(young, NOON)
        with freeze_time(NOON + timedelta(hours=1)):
            for user in young[:5]:
                self._confirmed_by(user, self.france)
            self.assertFalse(
                self._reports(self.france, "new_account_confirmations")
            )
            self._confirmed_by(young[5], self.france)
        self.assertEqual(
            len(self._reports(self.france, "new_account_confirmations")), 1
        )

    def test_call_minimum_duration(self):
        """§7.3: with a minimum duration, an answered call pays at its end
        if it lasted that long, and the turn still ends at the answer."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.call_min_duration", "60"
        )
        with freeze_time(NOON):
            reflet = self._confirmed()
            exact = self._exact(reflet, self.france)
            sam, france = self._call_members(reflet)
            sam._rtc_join_call()
            france._rtc_join_call()
            self.assertFalse(reflet.link_id.turn_reflet_id)
            self.assertFalse(self._lines(self.sam, "call_answered"))
        with freeze_time(NOON + timedelta(seconds=30)):
            france._rtc_leave_call()
            sam._rtc_leave_call()
        self.assertFalse(self._lines(self.sam, "call_answered"))
        self.assertFalse(self.env["linkup.points.call"].sudo().search([]))
        self.assertTrue(exact)
        with freeze_time(NOON + timedelta(days=1)):
            france._rtc_join_call()
            sam._rtc_join_call()
        with freeze_time(NOON + timedelta(days=1, seconds=90)):
            sam._rtc_leave_call()
        self.assertEqual(self._paid(self.sam, "call_answered"), [250])
        self.assertEqual(self._paid(self.france, "call_answered"), [250])
        self.assertBalanced(self.sam, self.france)
