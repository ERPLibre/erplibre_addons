# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Caps of the point scale over sliding windows (§7.3, Q-33, T-12)."""

from datetime import datetime, timedelta

from freezegun import freeze_time
from odoo.tests import tagged

from .common import LinkupPointsCase

# A Tuesday of October in Montréal, 10:00 local time, far from a change of
# daylight saving time.
NOON = datetime(2026, 10, 20, 14, 0)


@tagged("post_install", "-at_install")
class TestLinkupPointsCaps(LinkupPointsCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.others = cls._new_members(6, "cap")

    def test_reflect_sent_daily_cap(self):
        """LU-F-016 CA4: past five paid reflections in 24 hours, the next
        confirmed one still goes through, pays Sam nothing for its sending,
        and tells him ``linkup.cap_reached``."""
        with freeze_time(NOON):
            for other in self.others[:5]:
                self._confirmed_by(self.sam, other)
            self._bus_reset()
            reflet = self._confirmed_by(self.sam, self.others[5])
            self.assertEqual(reflet.state, "confirmed")
            line = self._lines(self.sam, "reflect_sent")[-1]
            self.assertEqual(
                (line.points, line.capped, line.cap_reason),
                (0, True, "daily_cap"),
            )
            payload = [
                p
                for p in self._awarded(self.sam)
                if p["rule_code"] == "reflect_sent"
            ]
            self.assertEqual(payload[0]["linkup_code"], "linkup.cap_reached")
            self.assertEqual(
                self._paid(self.sam, "reflect_sent"), [100] * 5 + [0]
            )
        self.assertBalanced(self.sam, *self.others)

    def test_daily_cap_is_a_sliding_window(self):
        """Q-33: three confirmations a day per member; the fourth, 23 hours
        later and after a change of time zone, is capped; 24 hours after
        the first one, it pays again."""
        with freeze_time(NOON):
            for other in self.others[:3]:
                self._confirmed_by(other, self.sam)
        self.sam.tz = "Pacific/Auckland"
        with freeze_time(NOON + timedelta(hours=23)):
            self._confirmed_by(self.others[3], self.sam)
            line = self._lines(self.sam, "reflect_confirmed")[-1]
            self.assertEqual(line.cap_reason, "daily_cap")
        with freeze_time(NOON + timedelta(hours=24, seconds=1)):
            self._confirmed_by(self.others[4], self.sam)
        self.assertEqual(
            self._paid(self.sam, "reflect_confirmed"),
            [1000, 1000, 1000, 0, 1000],
        )
        self.assertBalanced(self.sam)

    def test_weekly_cap(self):
        """A weekly cap counts the paid lines of seven sliding days."""
        rule = self._rule("reflect_confirmed")
        rule.write({"daily_cap": 0, "weekly_cap": 2})
        for day, other in enumerate(self.others[:3]):
            with freeze_time(NOON + timedelta(days=day)):
                self._confirmed_by(other, self.sam)
        with freeze_time(NOON + timedelta(days=7, seconds=1)):
            self._confirmed_by(self.others[3], self.sam)
        self.assertEqual(
            self._paid(self.sam, "reflect_confirmed"), [1000, 1000, 0, 1000]
        )
        self.assertEqual(
            self._lines(self.sam, "reflect_confirmed")[2].cap_reason,
            "weekly_cap",
        )

    def test_pair_lifetime_cap(self):
        """§7.3: the confirmation and the precision pay once per pair,
        ever; the sending of a new reflection still pays its author."""
        with freeze_time(NOON):
            first = self._confirmed()
            self._child(
                first.with_user(self.france).action_answer_precision(
                    "Je voudrais préciser."
                )
            )
        with freeze_time(NOON + timedelta(days=30)):
            second = self._confirmed()
            self._child(
                second.with_user(self.france).action_answer_precision(
                    "Je voudrais préciser encore."
                )
            )
        self.assertEqual(
            self._paid(self.france, "reflect_confirmed"), [1000, 0]
        )
        self.assertEqual(self._paid(self.france, "precision_sent"), [1000, 0])
        self.assertEqual(
            self._lines(self.france, "precision_sent")[1].cap_reason,
            "pair_lifetime_cap",
        )
        self.assertEqual(self._paid(self.sam, "reflect_sent"), [100, 100])
        self.assertBalanced(self.sam, self.france)

    def test_theme_guessed_weekly_cap_of_the_pair(self):
        """§7.1: a found theme pays once per pair and per week."""
        reflet = self._confirmed()
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Je voudrais préciser.", [self.goals.id]
            )
        )
        precision.with_user(self.sam).action_guess(self.goals.id)
        cont = self._continue(precision, self.sam)
        second = self._child(
            cont.with_user(self.france).action_answer_precision(
                "À mon tour.", [self.needs.id]
            )
        )
        second.with_user(self.sam).action_guess(self.needs.id)
        self.assertEqual(self._paid(self.sam, "theme_guessed"), [100, 0])
        self.assertEqual(
            self._lines(self.sam, "theme_guessed")[1].cap_reason,
            "pair_weekly_cap",
        )

    def test_penalty_has_no_cap(self):
        """§7.3: penalties have no cap."""
        for other in self.others[:6]:
            self._sent_to(self.sam, other).with_user(other).action_reject()
        self.assertEqual(self._paid(self.sam), [-150] * 6)
        self.assertBalanced(self.sam)
