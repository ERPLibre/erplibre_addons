# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.addons.erplibre_event_table.rotation import (
    Options,
    Person,
    Placement,
    Problem,
    Table,
    assign_seats,
    distance,
    evaluate,
    signature,
    table_conflicts,
)
from odoo.tests.common import BaseCase

ALL_OPTIONS = Options(
    separate_companies=True,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)
C2_ONLY = Options(
    separate_companies=False,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=False,
)


def _six_persons():
    companies = ["a", "a", "b", "b", None, None]
    return tuple(
        Person(key, company) for key, company in zip(range(1, 7), companies)
    )


def _plan(rounds_and_tables):
    """rounds_and_tables[r][t] is a list of person keys."""
    placements = []
    for index, seating in enumerate(rounds_and_tables):
        for table, keys in enumerate(seating, start=1):
            for key in keys:
                placements.append(Placement(index + 1, key, table, 0))
    return tuple(placements)


TWICE_THE_SAME = _plan(
    [
        [[1, 2, 3], [4, 5, 6]],
        [[1, 2, 3], [4, 5, 6]],
    ]
)


class TestRotationMetricsAndSeats(BaseCase):
    """Indicators, per-table conflicts, distance, signature, seats."""

    def _problem(self, capacity=3, rounds=2):
        tables = (Table(1, capacity), Table(2, capacity))
        return Problem(_six_persons(), tables, rounds)

    # --- evaluate ---

    def test_evaluate_reads_a_hand_made_plan(self):
        indicators = evaluate(self._problem(), TWICE_THE_SAME, ALL_OPTIONS)
        self.assertEqual(indicators.company_pairs, 2)
        self.assertEqual(indicators.repeated_pairs, 6)
        self.assertEqual(indicators.extra_meetings, 6)
        self.assertEqual(indicators.max_pair_meetings, 2)
        self.assertEqual(indicators.table_returns, 6)
        self.assertEqual(indicators.met_distinct_avg, 2.0)
        self.assertEqual(indicators.met_distinct_min, 2)
        self.assertEqual(indicators.cost, 266)

    def test_evaluate_counts_every_indicator_even_when_options_are_off(self):
        indicators = evaluate(self._problem(), TWICE_THE_SAME, C2_ONLY)
        self.assertEqual(indicators.company_pairs, 2)
        self.assertEqual(indicators.table_returns, 6)
        # Only the cost follows the options: 10 x 6 repeated meetings.
        self.assertEqual(indicators.cost, 60)

    def test_evaluate_sees_a_conflict_free_plan(self):
        plan = _plan([[[1, 3, 5], [2, 4, 6]]])
        indicators = evaluate(self._problem(rounds=1), plan, ALL_OPTIONS)
        self.assertEqual(indicators.company_pairs, 0)
        self.assertEqual(indicators.repeated_pairs, 0)
        self.assertEqual(indicators.extra_meetings, 0)
        self.assertEqual(indicators.max_pair_meetings, 1)
        self.assertEqual(indicators.table_returns, 0)
        self.assertEqual(indicators.cost, 0)

    def test_evaluate_survives_a_hand_adjusted_plan(self):
        # A hand adjustment unbalanced the tables: 4 and 2 in round 2.
        plan = _plan([[[1, 2, 3], [4, 5, 6]], [[1, 2, 3, 4], [5, 6]]])
        indicators = evaluate(self._problem(capacity=4), plan, ALL_OPTIONS)
        self.assertEqual(indicators.company_pairs, 3)
        self.assertEqual(indicators.max_pair_meetings, 2)

    # --- table_conflicts ---

    def test_table_conflicts_point_at_the_guilty_tables(self):
        conflicts = table_conflicts(
            self._problem(), TWICE_THE_SAME, ALL_OPTIONS
        )
        self.assertEqual(len(conflicts), 4)
        self.assertEqual(
            [(c.round, c.table) for c in conflicts],
            [(1, 1), (1, 2), (2, 1), (2, 2)],
        )
        first = conflicts[0]
        self.assertEqual(first.company_pairs, 1)
        self.assertEqual(first.repeated_pairs, 3)
        self.assertEqual(first.table_returns, 3)
        self.assertEqual(conflicts[1].company_pairs, 0)

    def test_table_conflicts_only_count_active_options(self):
        conflicts = table_conflicts(self._problem(), TWICE_THE_SAME, C2_ONLY)
        for conflict in conflicts:
            self.assertEqual(conflict.company_pairs, 0)
            self.assertEqual(conflict.table_returns, 0)
            self.assertEqual(conflict.repeated_pairs, 3)

    def test_table_conflicts_is_empty_on_a_clean_plan(self):
        plan = _plan([[[1, 3, 5], [2, 4, 6]]])
        self.assertEqual(
            table_conflicts(self._problem(rounds=1), plan, ALL_OPTIONS), ()
        )

    # --- signature and distance ---

    def test_signature_ignores_table_numbers_and_round_order(self):
        straight = _plan([[[1, 2, 3], [4, 5, 6]], [[1, 4, 5], [2, 3, 6]]])
        shuffled = _plan([[[2, 3, 6], [1, 4, 5]], [[4, 5, 6], [1, 2, 3]]])
        self.assertEqual(signature(straight), signature(shuffled))

    def test_signature_separates_two_different_plans(self):
        first = _plan([[[1, 2, 3], [4, 5, 6]]])
        second = _plan([[[1, 2, 4], [3, 5, 6]]])
        self.assertNotEqual(signature(first), signature(second))

    def test_distance_to_itself_is_zero(self):
        self.assertEqual(distance(TWICE_THE_SAME, TWICE_THE_SAME), 0.0)

    def test_distance_is_one_when_nobody_meets_the_same_person(self):
        first = _plan([[[1, 2], [3, 4]]])
        second = _plan([[[1, 3], [2, 4]]])
        self.assertEqual(distance(first, second), 1.0)
        self.assertEqual(distance(second, first), 1.0)

    def test_distance_is_partial_when_half_the_meetings_are_shared(self):
        first = _plan([[[1, 2], [3, 4]], [[1, 2], [3, 4]]])
        second = _plan([[[1, 2], [3, 4]], [[1, 3], [2, 4]]])
        # min: 1 + 1 = 2; max: 2 + 2 + 1 + 1 = 6.
        self.assertAlmostEqual(distance(first, second), 1 - 2 / 6)

    # --- assign_seats ---

    def _seats_of(self, placements, round_number, table):
        return sorted(
            placement.seat
            for placement in placements
            if placement.round == round_number and placement.table == table
        )

    def test_seats_are_distinct_and_within_the_table(self):
        problem = self._problem()
        seated = assign_seats(problem, TWICE_THE_SAME, ALL_OPTIONS, seed=1)
        self.assertEqual(len(seated), len(TWICE_THE_SAME))
        for round_number in (1, 2):
            for table in (1, 2):
                seats = self._seats_of(seated, round_number, table)
                self.assertEqual(len(set(seats)), 3)
                for seat in seats:
                    self.assertGreaterEqual(seat, 1)
                    self.assertLessEqual(seat, 3)

    def test_free_seats_are_spread_around_the_table(self):
        problem = Problem(_six_persons(), (Table(1, 6), Table(2, 6)), 1)
        plan = _plan([[[1, 2, 3], [4, 5, 6]]])
        seated = assign_seats(problem, plan, ALL_OPTIONS, seed=2)
        for table in (1, 2):
            seats = self._seats_of(seated, 1, table)
            gaps = [(seats[(i + 1) % 3] - seats[i]) % 6 for i in range(3)]
            self.assertEqual(gaps, [2, 2, 2])

    def test_nobody_keeps_the_same_table_and_seat_when_a_shift_avoids_it(self):
        problem = Problem(_six_persons(), (Table(1, 6), Table(2, 6)), 2)
        plan = _plan([[[1, 2, 3], [4, 5, 6]], [[1, 2, 3], [4, 5, 6]]])
        seated = assign_seats(problem, plan, ALL_OPTIONS, seed=3)
        first = {p.person: (p.table, p.seat) for p in seated if p.round == 1}
        second = {p.person: (p.table, p.seat) for p in seated if p.round == 2}
        for key in first:
            self.assertNotEqual(first[key], second[key])

    def test_colleagues_do_not_sit_next_to_each_other(self):
        persons = (
            Person(1, "a"),
            Person(2, "a"),
            Person(3, "b"),
            Person(4, "b"),
        )
        problem = Problem(persons, (Table(1, 4),), 1)
        plan = _plan([[[1, 2, 3, 4]]])
        seated = assign_seats(problem, plan, ALL_OPTIONS, seed=4)
        company_of = {person.key: person.company for person in persons}
        by_seat = {p.seat: p.person for p in seated}
        self.assertEqual(sorted(by_seat), [1, 2, 3, 4])
        for seat in (1, 2, 3, 4):
            here = company_of[by_seat[seat]]
            there = company_of[by_seat[seat % 4 + 1]]
            self.assertNotEqual(here, there)

    def test_seats_do_not_change_the_cost(self):
        problem = self._problem()
        seated = assign_seats(problem, TWICE_THE_SAME, ALL_OPTIONS, seed=5)
        self.assertEqual(
            evaluate(problem, seated, ALL_OPTIONS),
            evaluate(problem, TWICE_THE_SAME, ALL_OPTIONS),
        )

    def test_seats_are_deterministic_for_a_seed(self):
        problem = self._problem()
        first = assign_seats(problem, TWICE_THE_SAME, ALL_OPTIONS, seed=6)
        second = assign_seats(problem, TWICE_THE_SAME, ALL_OPTIONS, seed=6)
        self.assertEqual(first, second)

    # --- robustness on hand-edited placements ---

    def test_evaluate_rejects_a_placement_naming_an_unknown_table(self):
        plan = _plan([[[1, 2, 3], [4, 5, 6]]])
        plan = plan + (Placement(2, 1, 99, 0),)
        with self.assertRaises(ValueError):
            evaluate(self._problem(), plan, ALL_OPTIONS)

    def test_table_conflicts_rejects_a_placement_naming_an_unknown_table(
        self,
    ):
        plan = _plan([[[1, 2, 3], [4, 5, 6]]])
        plan = plan + (Placement(2, 1, 99, 0),)
        with self.assertRaises(ValueError):
            table_conflicts(self._problem(), plan, ALL_OPTIONS)

    def test_assign_seats_rejects_a_placement_naming_an_unknown_table(self):
        plan = _plan([[[1, 2, 3], [4, 5, 6]]])
        plan = plan + (Placement(2, 1, 99, 0),)
        with self.assertRaises(ValueError):
            assign_seats(self._problem(), plan, ALL_OPTIONS, seed=1)

    def test_assign_seats_rejects_a_table_over_its_capacity(self):
        problem = Problem(_six_persons(), (Table(1, 3), Table(2, 3)), 1)
        plan = _plan([[[1, 2, 3, 4, 5], [6]]])
        with self.assertRaises(ValueError):
            assign_seats(problem, plan, ALL_OPTIONS, seed=1)
