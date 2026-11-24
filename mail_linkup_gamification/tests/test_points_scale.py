# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The default point scale (§7.1), rule by rule, and the point criteria of
LU-F-016 to LU-F-044 at Lot 2 (T-12)."""

from datetime import datetime, timedelta

from freezegun import freeze_time
from odoo import fields
from odoo.tests import tagged

from .common import LinkupPointsCase

# A frozen time earlier than the RTC sessions of the tests: the server drops
# a session whose last update is more than a minute older than now.
NOON = datetime(2026, 10, 20, 16, 0)

# The default scale: points, beneficiaries, then the caps daily, weekly,
# pair daily, pair weekly, pair lifetime, the cap group, the decay and the
# reset of the decay.
SCALE = {
    "reflect_sent": (100, "author", 5, 0, 0, 0, 0, False, False, False),
    "reflect_rejected": (-150, "author", 0, 0, 0, 0, 0, False, False, False),
    "reflect_confirmed": (1000, "both", 3, 10, 0, 0, 1, False, False, True),
    "answer_exact": (250, "both", 0, 0, 0, 0, 0, False, True, False),
    "precision_sent": (1000, "both", 3, 0, 0, 0, 1, False, False, False),
    "theme_guessed": (100, "both", 0, 0, 0, 1, 0, False, False, False),
    "theme_missed": (0, "none", 0, 0, 0, 0, 0, False, False, False),
    "continue_sent": (250, "both", 0, 0, 5, 0, 0, False, True, False),
    "continue_confirmed": (250, "both", 0, 0, 5, 0, 0, False, True, False),
    "close": (0, "none", 0, 0, 0, 0, 0, False, False, False),
    "call_answered": (250, "both", 0, 0, 1, 0, 0, False, False, True),
    "virtual_round": (100, "both", 0, 0, 0, 0, 0, False, True, False),
    "highlight": (0, "none", 0, 0, 0, 0, 0, False, False, False),
}


@tagged("post_install", "-at_install")
class TestLinkupPointsScale(LinkupPointsCase):
    def test_default_scale(self):
        """Each code of §7.1 has its rule, with the values of the scale."""
        rules = self.Rule.sudo().search([])
        self.assertEqual(set(rules.mapped("code")), set(SCALE))
        for rule in rules:
            self.assertEqual(
                (
                    rule.points,
                    rule.beneficiaries,
                    rule.daily_cap,
                    rule.weekly_cap,
                    rule.pair_daily_cap,
                    rule.pair_weekly_cap,
                    rule.pair_lifetime_cap,
                    rule.cap_group,
                    rule.decay,
                    rule.resets_decay,
                ),
                SCALE[rule.code],
                rule.code,
            )

    # Sending and confirmation (LU-F-016, LU-F-022, LU-F-100)

    def test_reflect_sent_is_paid_at_the_confirmation(self):
        """LU-F-016 CA1, LU-F-022 CA1, LU-F-100 CA1, Q-01, Q-37: sending
        pays nothing; the confirmation pays 100 to Sam for his reflection
        and 1000 to each, each line naming the other party."""
        reflet = self._sent()
        self.assertFalse(self._lines(self.sam) | self._lines(self.france))
        self._bus_reset()
        reflet.with_user(self.france).action_confirm()
        self.assertEqual(
            [
                (line.rule_id.code, line.points)
                for line in self._lines(self.sam)
            ],
            [("reflect_confirmed", 1000), ("reflect_sent", 100)],
        )
        france_lines = self._lines(self.france)
        self.assertEqual(france_lines.mapped("points"), [1000])
        self.assertEqual(france_lines.partner_user_id, self.sam)
        self.assertEqual(self._lines(self.sam).partner_user_id, self.france)
        self.assertEqual(
            (self._lines(self.sam) | france_lines).reflet_id, reflet
        )
        self.assertEqual(self.sam.sudo().karma, 1100)
        self.assertEqual(self.france.sudo().karma, 1000)
        self.assertBalanced(self.sam, self.france)
        awarded = self._awarded(self.france)
        self.assertEqual(
            [(p["rule_code"], p["points"], p["capped"]) for p in awarded],
            [("reflect_confirmed", 1000, False)],
        )
        self.assertEqual(awarded[0]["counterpart_id"], self.sam.partner_id.id)
        tracking = self._lines(self.sam).karma_tracking_id
        self.assertEqual(len(tracking), 1)
        self.assertEqual(tracking.origin_ref, reflet)

    def test_confirming_again_pays_nothing(self):
        """LU-F-022 CA2: a second confirmation is refused and pays
        nothing."""
        reflet = self._confirmed()
        with self.assertLinkupCode("linkup.already_answered"):
            reflet.with_user(self.france).action_confirm()
        self.assertEqual(self._paid(self.france), [1000])

    def test_same_event_twice_pays_once(self):
        """LU-F-100 RM1: a scoring event reported twice with its key writes
        its lines once."""
        reflet = self._confirmed()
        lines = self.Ledger.sudo().search([])
        reflet.sudo()._linkup_event(
            "reflect_confirmed",
            reflet.author_id | reflet.recipient_id,
            link=reflet.link_id,
        )
        self.assertEqual(self.Ledger.sudo().search([]), lines)
        self.assertBalanced(self.sam, self.france)

    def test_blocked_recipient_pays_nothing(self):
        """LU-F-016 CA3: a reflection to a member who blocked its author
        pays nothing, now or later."""
        self.env["linkup.block"].with_user(self.france).action_block(
            user_id=self.sam.id
        )
        self._sent()
        self.assertFalse(
            self.Ledger.sudo().search([("user_id", "in", self.members.ids)])
        )

    def test_withdrawal_keeps_the_balance(self):
        """LU-F-019 CA1: withdrawing an unread reflection leaves the balance
        of Sam as it was."""
        before = self.sam.sudo().karma
        reflet = self._sent()
        reflet.with_user(self.sam).action_withdraw()
        self.assertEqual(self.sam.sudo().karma, before)
        self.assertFalse(self._lines(self.sam))

    def test_rejection_costs_150(self):
        """LU-F-023 CA1, Q-01: a rejection costs 150 to Sam alone, and the
        karma goes negative."""
        reflet = self._sent()
        reflet.with_user(self.france).action_reject()
        self.assertEqual(self._paid(self.sam, "reflect_rejected"), [-150])
        self.assertFalse(self._lines(self.france))
        self.assertEqual(self.sam.sudo().karma, -150)
        self.assertBalanced(self.sam)

    def test_neutral_issues_pay_nothing(self):
        """LU-F-025 CA1 and CA2, LU-F-024 CA1: ignoring, marking inaccurate
        and the expiry pay nothing and cost nothing."""
        ignored = self._sent()
        ignored.with_user(self.france).action_ignore()
        inaccurate = self._sent(recipient=self.jacques)
        inaccurate.with_user(self.jacques).action_mark_inaccurate(
            "Ce n'est pas ce que j'ai dit."
        )
        ignored.sudo().sent_date = fields.Datetime.now() - timedelta(days=31)
        self.Reflet._cron_expire_reflets()
        self.assertEqual(ignored.state, "expired")
        self.assertFalse(
            self.Ledger.sudo().search([("user_id", "in", self.members.ids)])
        )

    # Answers (LU-F-030 to LU-F-033)

    def test_answer_exact(self):
        """LU-F-030 CA1 and LU-F-071 CA1: the exact answer pays 250 to
        each; the energy of the link is 1350 for Sam, 1250 for France."""
        reflet = self._confirmed()
        self._exact(reflet, self.france)
        self.assertEqual(self._paid(self.sam, "answer_exact"), [250])
        self.assertEqual(self._paid(self.france, "answer_exact"), [250])
        link = reflet.link_id
        self.assertEqual(link._linkup_energy_for(self.sam), 1350)
        self.assertEqual(link._linkup_energy_for(self.france), 1250)
        self.assertBalanced(self.sam, self.france)

    def test_precision_and_guess(self):
        """LU-F-031 CA1, LU-F-033 CA1, Q-02: the precision pays 1000 to
        each, on top of the confirmation; the theme found pays 100 to
        each."""
        reflet = self._confirmed()
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Je voudrais préciser.", [self.goals.id, self.emotions.id]
            )
        )
        self.assertEqual(self._paid(self.france), [1000, 1000])
        precision.with_user(self.sam).action_guess(self.goals.id)
        self.assertEqual(self._paid(self.sam, "theme_guessed"), [100])
        self.assertEqual(self._paid(self.france, "theme_guessed"), [100])
        self.assertBalanced(self.sam, self.france)

    def test_missed_guess_pays_nothing(self):
        """LU-F-033 CA3: a missed guess writes no line."""
        reflet = self._confirmed()
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Je voudrais préciser.", [self.goals.id]
            )
        )
        lines = self.Ledger.sudo().search([])
        precision.with_user(self.sam).action_guess(self.needs.id)
        self.assertEqual(self.Ledger.sudo().search([]), lines)

    # Follow-up options (LU-F-041 to LU-F-043)

    def test_continue_and_its_exact_answer(self):
        """LU-F-042 CA1 and CA2: continuing pays 250 to each, and its exact
        answer 250 to each."""
        reflet = self._confirmed()
        exact = self._exact(reflet, self.france)
        cont = self._continue(exact, self.sam)
        self.assertEqual(self._paid(self.france, "continue_sent"), [250])
        self.assertEqual(self._paid(self.sam, "continue_sent"), [250])
        self._exact(cont, self.france)
        self.assertEqual(self._paid(self.sam, "continue_confirmed"), [250])
        self.assertEqual(self._paid(self.france, "continue_confirmed"), [250])

    def test_close_and_self_disclosure_pay_nothing(self):
        """LU-F-041 CA1, LU-F-043 RM4: closing and talking about oneself by
        text pay nothing."""
        reflet = self._confirmed()
        exact = self._exact(reflet, self.france)
        lines = self.Ledger.sudo().search([])
        disclosure = self._child(
            exact.with_user(self.sam).action_self_disclosure(
                self.needs.id, "J'ai besoin de : plus de concentration."
            )
        )
        self.assertEqual(self.Ledger.sudo().search([]), lines)
        cont = self._continue(disclosure, self.france)
        answer = self._exact(cont, self.sam)
        lines = self.Ledger.sudo().search([])
        answer.with_user(self.france).action_close()
        self.assertEqual(self.Ledger.sudo().search([]), lines)

    # Calls (LU-F-044, Q-42)

    def test_call_from_talking_about_oneself(self):
        """LU-F-044 CA1 and CA3: the first participant pays nothing; the
        answer of a call Sam started from the options pays 250 to each,
        once."""
        reflet = self._confirmed()
        self._exact(reflet, self.france)
        sam, france = self._call_members(reflet)
        lines = self.Ledger.sudo().search([])
        sam._rtc_join_call()
        self.assertEqual(self.Ledger.sudo().search([]), lines)
        france._rtc_join_call()
        self.assertEqual(self._paid(self.sam, "call_answered"), [250])
        self.assertEqual(self._paid(self.france, "call_answered"), [250])
        france._rtc_leave_call()
        france._rtc_join_call()
        self.assertEqual(self._paid(self.france, "call_answered"), [250])
        self.assertBalanced(self.sam, self.france)

    def test_unanswered_call_pays_nothing(self):
        """LU-F-044 CA2: a call nobody answers pays nothing."""
        reflet = self._confirmed()
        self._exact(reflet, self.france)
        sam, _france = self._call_members(reflet)
        lines = self.Ledger.sudo().search([])
        sam._rtc_join_call()
        sam._rtc_leave_call()
        self.assertEqual(self.Ledger.sudo().search([]), lines)

    def test_any_call_pays_the_same_within_one_cap(self):
        """Q-42: a call answered outside "Talking about oneself" pays 250
        to each as well; one call a day per pair, whoever starts it and
        from wherever, and the cap opens again 24 hours later."""
        with freeze_time(NOON):
            reflet = self._confirmed()
            sam, france = self._call_members(reflet)
            france._rtc_join_call()
            sam._rtc_join_call()
            self.assertEqual(self._paid(self.sam, "call_answered"), [250])
            sam._rtc_leave_call()
            france._rtc_leave_call()
            exact = self._exact(reflet, self.france)
        with freeze_time(NOON + timedelta(hours=2)):
            self._bus_reset()
            sam._rtc_join_call()
            france._rtc_join_call()
            # The call of the options ends the turn even beyond the cap.
            self.assertFalse(exact.link_id.turn_reflet_id)
            line = self._lines(self.sam, "call_answered")[-1:]
            self.assertEqual(
                (line.points, line.cap_reason), (0, "pair_daily_cap")
            )
            self.assertEqual(
                self._awarded(self.sam)[-1]["linkup_code"],
                "linkup.cap_reached",
            )
            sam._rtc_leave_call()
            france._rtc_leave_call()
        with freeze_time(NOON + timedelta(hours=24, seconds=1)):
            france._rtc_join_call()
            sam._rtc_join_call()
        self.assertEqual(self._paid(self.sam, "call_answered"), [250, 0, 250])
        self.assertBalanced(self.sam, self.france)

    # Scale edited by the administrator (LU-F-101)

    def test_edited_rule(self):
        """LU-F-101 CA1: the confirmation rule set to 800 pays 800 to
        each."""
        self._rule("reflect_confirmed").points = 800
        self._confirmed()
        self.assertEqual(self._paid(self.france), [800])
        self.assertEqual(self._paid(self.sam, "reflect_confirmed"), [800])

    def test_archived_rule_writes_nothing(self):
        """An archived rule pays nothing and writes no line."""
        self._rule("reflect_sent").active = False
        self._confirmed()
        self.assertFalse(self._lines(self.sam, "reflect_sent"))
        self.assertEqual(self._paid(self.sam), [1000])
