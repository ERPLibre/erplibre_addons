# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Decreasing sequences of a pair: rounds of free text and repeated
structured actions (LU-F-045, Q-03, Q-33, T-45)."""

from datetime import datetime, timedelta

from freezegun import freeze_time
from odoo.tests import tagged

from .common import LinkupPointsCase

# UTC times of October 20, 2026: Montréal is at UTC−4, Paris at UTC+2.
MORNING = datetime(2026, 10, 20, 13, 0)
# 23:50 in Montréal.
BEFORE_MIDNIGHT = datetime(2026, 10, 21, 3, 50)
# 00:10 in Montréal, the day after.
AFTER_MIDNIGHT = datetime(2026, 10, 21, 4, 10)


@tagged("post_install", "-at_install")
class TestLinkupPointsDecay(LinkupPointsCase):
    def _linked(self):
        """A confirmed reflection of Sam to France, and France's exact
        answer, which gives Sam the options."""
        reflet = self._confirmed()
        return reflet, self._exact(reflet, self.france)

    def _cycle(self, exact):
        """Sam continues the reflection and France answers that it is
        exactly it; return her answer, which gives Sam the options again."""
        cont = self._continue(exact, self.sam)
        return self._exact(cont, self.france)

    # Structured actions (Q-03)

    def test_structured_actions_decay(self):
        """Q-03: a repeated continuation pays half of the previous one,
        down to the cap of five a day of the pair."""
        with freeze_time(MORNING):
            _reflet, exact = self._linked()
            for _index in range(6):
                exact = self._cycle(exact)
        self.assertEqual(
            self._paid(self.sam, "continue_sent"), [250, 125, 62, 31, 15, 0]
        )
        self.assertEqual(
            self._lines(self.sam, "continue_sent")[-1].cap_reason,
            "pair_daily_cap",
        )
        self.assertEqual(
            self._paid(self.france, "continue_confirmed"),
            [250, 125, 62, 31, 15, 0],
        )
        self.assertBalanced(self.sam, self.france)

    def test_decay_starts_again_at_midnight_of_the_member(self):
        """Q-03, Q-33: the sequence starts again at midnight in the time
        zone of the member."""
        with freeze_time(BEFORE_MIDNIGHT):
            _reflet, exact = self._linked()
            exact = self._cycle(exact)
            exact = self._cycle(exact)
        with freeze_time(AFTER_MIDNIGHT):
            self._cycle(exact)
        self.assertEqual(
            self._paid(self.sam, "continue_sent"), [250, 125, 250]
        )

    def test_each_member_has_their_own_midnight(self):
        """Q-33: midnight in Paris starts France's sequence again, not
        Sam's, who is still in the evening in Montréal."""
        self.france.tz = "Europe/Paris"
        with freeze_time(datetime(2026, 10, 20, 21, 50)):
            _reflet, exact = self._linked()
            exact = self._cycle(exact)
        with freeze_time(datetime(2026, 10, 20, 22, 10)):
            self._cycle(exact)
        self.assertEqual(self._paid(self.sam, "continue_sent"), [250, 125])
        self.assertEqual(self._paid(self.france, "continue_sent"), [250, 250])

    def test_decay_starts_again_on_a_confirmation(self):
        """Q-03: a reflection confirmed in the pair starts the sequences
        again."""
        with freeze_time(MORNING):
            _reflet, exact = self._linked()
            self._cycle(self._cycle(exact))
            again = self._confirmed()
            self._cycle(self._exact(again, self.france))
        self.assertEqual(
            self._paid(self.sam, "continue_sent"), [250, 125, 250]
        )

    def test_decay_starts_again_on_an_answered_call(self):
        """Q-03: an answered call of the pair starts the sequences again."""
        with freeze_time(MORNING):
            reflet, exact = self._linked()
            exact = self._cycle(self._cycle(exact))
            sam, france = self._call_members(reflet)
            france._rtc_join_call()
            sam._rtc_join_call()
            self._cycle(exact)
        self.assertEqual(
            self._paid(self.sam, "continue_sent"), [250, 125, 250]
        )

    def test_capped_call_starts_nothing_again(self):
        """§7.3, Q-03: a call beyond the cap of the pair pays nothing, so
        it starts no sequence again; hanging up and calling again does not
        renew the rounds."""
        with freeze_time(MORNING):
            reflet = self._confirmed()
            channel = reflet.channel_id
            sam, france = self._call_members(reflet)
            for _index in range(3):
                self._post(channel, self.sam)
                self._post(channel, self.france)
                france._rtc_join_call()
                sam._rtc_join_call()
                sam._rtc_leave_call()
                france._rtc_leave_call()
        self.assertEqual(self._paid(self.sam, "call_answered"), [250, 0, 0])
        self.assertEqual(
            self._lines(self.sam, "call_answered").mapped("resets_decay"),
            [True, False, False],
        )
        self.assertEqual(self._paid(self.sam, "virtual_round"), [100, 100, 50])
        self.assertBalanced(self.sam, self.france)

    def test_confirmations_start_again_within_the_daily_cap(self):
        """Q-03: each confirmation of the pair starts the sequences again,
        including those beyond its first link, which pay nothing; past
        three a day for a member, a confirmation starts nothing again."""
        with freeze_time(MORNING):
            channel = self._confirmed().channel_id
            for _index in range(4):
                self._post(channel, self.sam)
                self._post(channel, self.france)
                self._confirmed()
        self.assertEqual(
            self._paid(self.sam, "reflect_confirmed"), [1000, 0, 0, 0, 0]
        )
        self.assertEqual(
            self._lines(self.sam, "reflect_confirmed").mapped("resets_decay"),
            [True, True, True, False, False],
        )
        self.assertEqual(
            self._paid(self.sam, "virtual_round"), [100, 100, 100, 50]
        )

    def test_time_zone_change_starts_nothing_again(self):
        """Q-33: a member who moves to a time zone whose midnight just
        passed does not start their sequence again; the other member, who
        stays in Montréal, goes on as well."""
        with freeze_time(datetime(2026, 10, 20, 12, 30)):
            channel = self._confirmed().channel_id
            for _index in range(2):
                self._post(channel, self.sam)
                self._post(channel, self.france)
        # Midnight in Nouméa (UTC+11) is 13:00 UTC.
        self.sam.tz = "Pacific/Noumea"
        with freeze_time(datetime(2026, 10, 20, 13, 10)):
            self._post(channel, self.sam)
            self._post(channel, self.france)
        self.assertEqual(self._paid(self.sam, "virtual_round"), [100, 50, 25])
        self.assertEqual(
            self._paid(self.france, "virtual_round"), [100, 50, 25]
        )
        # The next midnight of Nouméa, a day later, starts it again.
        with freeze_time(datetime(2026, 10, 21, 13, 10)):
            self._post(channel, self.sam)
            self._post(channel, self.france)
        self.assertEqual(
            self._paid(self.sam, "virtual_round"), [100, 50, 25, 100]
        )

    # Rounds of free text (LU-F-045)

    def test_four_rounds(self):
        """LU-F-045 CA1: four alternations pay 100, 50, 25 and 12 to
        each."""
        with freeze_time(MORNING):
            reflet = self._confirmed()
            channel = reflet.channel_id
            for _index in range(4):
                self._post(channel, self.sam)
                self._post(channel, self.france)
        for user in (self.sam, self.france):
            self.assertEqual(
                self._paid(user, "virtual_round"), [100, 50, 25, 12]
            )
        self.assertBalanced(self.sam, self.france)

    def test_consecutive_messages_make_one_round(self):
        """LU-F-045 CA2: three messages of Sam then one of France close a
        single round."""
        reflet = self._confirmed()
        channel = reflet.channel_id
        for _index in range(3):
            self._post(channel, self.sam)
        self._post(channel, self.france)
        self.assertEqual(self._paid(self.sam, "virtual_round"), [100])
        self._post(channel, self.france)
        self.assertEqual(self._paid(self.france, "virtual_round"), [100])

    def test_round_after_midnight(self):
        """LU-F-045 CA3: a round closed at 23:59 then another at 0:01 in
        the time zone of the members: the second one pays 100."""
        with freeze_time(MORNING):
            reflet = self._confirmed()
        channel = reflet.channel_id
        with freeze_time(datetime(2026, 10, 21, 3, 58)):
            self._post(channel, self.sam)
        with freeze_time(datetime(2026, 10, 21, 3, 59)):
            self._post(channel, self.france)
            self._post(channel, self.sam)
        with freeze_time(datetime(2026, 10, 21, 4, 1)):
            self._post(channel, self.france)
        self.assertEqual(self._paid(self.sam, "virtual_round"), [100, 100])

    def test_exhausted_sequence(self):
        """LU-F-045 RM1: the sequence 100, 50, 25, 12, 6, 3, 1 ends at 0, a
        line kept as capped."""
        with freeze_time(MORNING):
            reflet = self._confirmed()
            channel = reflet.channel_id
            for _index in range(9):
                self._post(channel, self.sam)
                self._post(channel, self.france)
        self.assertEqual(
            self._paid(self.sam, "virtual_round"),
            [100, 50, 25, 12, 6, 3, 1, 0, 0],
        )
        self.assertEqual(
            set(
                self._lines(self.sam, "virtual_round")[-2:].mapped(
                    "cap_reason"
                )
            ),
            {"decay"},
        )

    def test_round_sequence_parameter(self):
        """LU-F-045 RM4: ``linkup.virtual_round_points`` sets the
        sequence."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.virtual_round_points", "10,5"
        )
        reflet = self._confirmed()
        channel = reflet.channel_id
        for _index in range(3):
            self._post(channel, self.sam)
            self._post(channel, self.france)
        self.assertEqual(self._paid(self.sam, "virtual_round"), [10, 5, 0])

    def test_rounds_need_an_active_link(self):
        """Free text outside an active pair, and a carrier message, close
        no round."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.start_rule_mode", "off"
        )
        reflet = self._sent()
        channel = reflet.channel_id
        self._post(channel, self.sam)
        self._post(channel, self.france)
        self._post(channel, self.sam)
        self.assertFalse(self._lines(self.sam, "virtual_round"))
        reflet.with_user(self.france).action_confirm()
        # The carrier of the exact answer is not free text.
        self._exact(reflet, self.france)
        self._post(channel, self.sam)
        self.assertFalse(self._lines(self.sam, "virtual_round"))
        self._post(channel, self.france)
        self.assertEqual(self._paid(self.sam, "virtual_round"), [100])

    def test_decay_value_rounds_down(self):
        """Q-03: halving rounds down and stops at 0 below 1."""
        rule = self._rule("continue_sent")
        self.assertEqual(
            [rule._linkup_decay_value(index) for index in range(10)],
            [250, 125, 62, 31, 15, 7, 3, 1, 0, 0],
        )

    def test_midnight_of_the_member(self):
        """Q-33: a member without a time zone takes ``linkup.timezone``,
        then Montréal."""
        now = datetime(2026, 10, 21, 3, 50)
        self.assertEqual(
            self.sam._linkup_day_start(now), datetime(2026, 10, 20, 4, 0)
        )
        self.sam.tz = False
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.timezone", "Europe/Paris"
        )
        self.assertEqual(
            self.sam._linkup_day_start(now), datetime(2026, 10, 20, 22, 0)
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.timezone", "Nowhere/Invalid"
        )
        self.assertEqual(
            self.sam._linkup_day_start(now), datetime(2026, 10, 20, 4, 0)
        )
        self.assertEqual(
            self.sam._linkup_day_start(now + timedelta(hours=1)),
            datetime(2026, 10, 21, 4, 0),
        )
