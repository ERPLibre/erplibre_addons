# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import itertools
import math

from odoo.addons.erplibre_event_table.rotation import (
    Options,
    Person,
    Problem,
    RotationState,
    Table,
    pair_floor,
    precheck,
)
from odoo.tests.common import BaseCase

C1 = Options(
    separate_companies=True,
    avoid_repeat_neighbors=False,
    avoid_repeat_table=False,
)
C2 = Options(
    separate_companies=False,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=False,
)
C3 = Options(
    separate_companies=False,
    avoid_repeat_neighbors=False,
    avoid_repeat_table=True,
)
C2C3 = Options(
    separate_companies=False,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)


def _plain(count, tables, capacity, rounds):
    """count persons without a company, identical tables."""
    persons = tuple(Person(key) for key in range(1, count + 1))
    numbers = tuple(Table(number, capacity) for number in range(1, tables + 1))
    return Problem(persons, numbers, rounds)


def _codes(diagnostics):
    return [diagnostic.code for diagnostic in diagnostics]


def _by_code(diagnostics, code):
    for diagnostic in diagnostics:
        if diagnostic.code == code:
            return diagnostic
    raise AssertionError(
        "diagnostic %s missing from %s" % (code, _codes(diagnostics))
    )


def _seatings(people, sizes):
    """All distributions of people over NUMBERED tables."""
    if not sizes:
        yield ()
        return
    head, rest = sizes[0], sizes[1:]
    for group in itertools.combinations(people, head):
        remaining = [x for x in people if x not in group]
        for tail in _seatings(remaining, rest):
            yield (group,) + tail


def _plan_cost(problem, options, targets, plan):
    state = RotationState(problem, options, targets)
    for r, seating in enumerate(plan):
        for t, group in enumerate(seating):
            for p in group:
                state.place(r, p, t)
    return state.full_cost()


def _brute_force_minimum(problem, options, targets):
    people = list(range(len(problem.persons)))
    seatings = list(_seatings(people, list(targets)))
    best = None
    for plan in itertools.product(seatings, repeat=problem.rounds):
        cost = _plan_cost(problem, options, targets, plan)
        if best is None or cost < best:
            best = cost
    return best


def _all_occupations(n_people, capacities):
    """Every occupation (o_1, ..., o_m), 0 <= o_i <= capacity_i, summing
    to n_people — not only the ONE `table_targets` would pick for it.
    Needed to test the bounds' real scope (01 §4): a floor for plans
    that occupy the tables as `targets` prescribes, never a floor over
    every capacity-respecting occupation, which nothing in `precheck`
    or `generate` ever searches.
    """

    def rec(caps):
        if not caps:
            yield ()
            return
        for count in range(caps[0] + 1):
            for rest in rec(caps[1:]):
                yield (count,) + rest

    for occupation in rec(list(capacities)):
        if sum(occupation) == n_people:
            yield occupation


def _brute_force_minimum_any_occupation(problem, options):
    """Like _brute_force_minimum, but over EVERY capacity-respecting
    occupation, not only `targets`. `_brute_force_minimum` enumerates
    the prescribed occupation ALONE, which is exactly why a bound
    valid only for that one occupation could stand unnoticed as if it
    were valid for all of them — this is the check that would have
    caught it.
    """
    capacities = [table.capacity for table in problem.tables]
    people = list(range(len(problem.persons)))
    best = None
    for occupation in _all_occupations(len(problem.persons), capacities):
        seatings = list(_seatings(people, list(occupation)))
        for plan in itertools.product(seatings, repeat=problem.rounds):
            cost = _plan_cost(problem, options, occupation, plan)
            if best is None or cost < best:
                best = cost
    return best


class TestRotationBounds(BaseCase):
    """pair_floor, order of blocking checks, validity of the bounds."""

    # --- pair_floor ---

    def test_pair_floor_spreads_people_over_tables(self):
        self.assertEqual(pair_floor(12, 8), 4)
        self.assertEqual(pair_floor(11, 8), 3)
        self.assertEqual(pair_floor(30, 25), 5)
        self.assertEqual(pair_floor(10, 5), 5)
        self.assertEqual(pair_floor(6, 5), 1)

    def test_pair_floor_is_zero_when_everyone_fits_apart(self):
        self.assertEqual(pair_floor(6, 6), 0)
        self.assertEqual(pair_floor(3, 8), 0)

    def test_pair_floor_without_table(self):
        self.assertEqual(pair_floor(0, 0), 0)
        self.assertEqual(pair_floor(3, 0), math.inf)

    # --- blocking checks ---

    def test_a_plan_with_tables_and_no_participant_asks_for_participants(
        self,
    ):
        lower_bound, diagnostics, targets = precheck(_plain(0, 4, 6, 3), C2C3)
        self.assertEqual(_codes(diagnostics), ["too_few_participants"])
        self.assertEqual(diagnostics[0].severity, "blocking")
        self.assertEqual(diagnostics[0].params, {"persons": 0})
        self.assertEqual(lower_bound, 0)
        self.assertEqual(targets, ())

    def test_one_participant_is_still_too_few(self):
        _, diagnostics, _ = precheck(_plain(1, 4, 6, 3), C2C3)
        self.assertEqual(_codes(diagnostics), ["too_few_participants"])

    def test_a_plan_without_table_asks_for_tables(self):
        lower_bound, diagnostics, targets = precheck(
            Problem(tuple(Person(k) for k in range(1, 5)), (), 3), C2C3
        )
        self.assertEqual(_codes(diagnostics), ["no_tables"])
        self.assertEqual(diagnostics[0].severity, "blocking")
        self.assertEqual(lower_bound, 0)
        self.assertEqual(targets, ())

    def test_missing_seats_are_counted(self):
        _, diagnostics, _ = precheck(_plain(9, 2, 4, 2), C2C3)
        diagnostic = _by_code(diagnostics, "capacity_short")
        self.assertEqual(_codes(diagnostics), ["capacity_short"])
        self.assertEqual(diagnostic.severity, "blocking")
        self.assertEqual(diagnostic.minimum, 1)
        self.assertEqual(
            diagnostic.params, {"persons": 9, "seats": 8, "missing": 1}
        )

    # --- known values ---

    def test_known_bound_36_persons_6_tables_of_6_3_rounds(self):
        lower_bound, diagnostics, targets = precheck(_plain(36, 6, 6, 3), C2C3)
        self.assertEqual(targets, (6, 6, 6, 6, 6, 6))
        self.assertEqual(lower_bound, 18)
        self.assertIn("tables_too_full", _codes(diagnostics))

    def test_known_bound_50_persons_5_tables_of_10_3_rounds(self):
        lower_bound, _, targets = precheck(_plain(50, 5, 10, 3), C2)
        self.assertEqual(targets, (10, 10, 10, 10, 10))
        self.assertEqual(lower_bound, 750)

    def test_a_company_of_twelve_over_eight_tables(self):
        persons = tuple(
            Person(key, "a" if key <= 12 else None) for key in range(1, 41)
        )
        tables = tuple(Table(number, 5) for number in range(1, 9))
        lower_bound, diagnostics, _ = precheck(Problem(persons, tables, 4), C1)
        diagnostic = _by_code(diagnostics, "company_exceeds_tables")
        self.assertEqual(diagnostic.severity, "unavoidable")
        self.assertEqual(diagnostic.minimum, 16)
        self.assertEqual(
            diagnostic.params, {"company": "a", "members": 12, "tables": 8}
        )
        self.assertEqual(lower_bound, 1600)

    def test_the_minimum_of_each_diagnostic_keeps_its_own_unit(self):
        lower_bound, diagnostics, _ = precheck(_plain(16, 2, 8, 3), C2)
        # LB2 counts extra meetings; tables_too_full reports LBT_u, the
        # same sum as the weighted LBT with w1 = w2 = w3 = 1:
        # pair_floor(8, 2) = 12, summed over the two open tables gives
        # 24, and C(3, 2) = 3, so LBT_u = 72 - the weighted lower_bound
        # stays 720, since it is what the search's stopping condition
        # compares against.
        self.assertEqual(_by_code(diagnostics, "pairs_exhausted").minimum, 48)
        self.assertEqual(
            _by_code(diagnostics, "pairs_exhausted").params, {"rounds": 3}
        )
        self.assertEqual(_by_code(diagnostics, "tables_too_full").minimum, 72)
        self.assertEqual(lower_bound, 720)

    def test_more_rounds_than_tables_forces_returns(self):
        lower_bound, diagnostics, _ = precheck(_plain(12, 3, 4, 5), C3)
        diagnostic = _by_code(diagnostics, "rounds_exceed_tables")
        self.assertEqual(diagnostic.severity, "unavoidable")
        self.assertEqual(diagnostic.minimum, 24)
        self.assertEqual(diagnostic.params, {"rounds": 5, "tables": 3})
        self.assertEqual(lower_bound, 24)

    def test_a_tight_configuration_suggests_a_prime_power(self):
        _, diagnostics, _ = precheck(_plain(120, 12, 10, 4), C2C3)
        diagnostic = _by_code(diagnostics, "tight")
        self.assertEqual(diagnostic.severity, "warning")
        self.assertEqual(diagnostic.minimum, 0)
        self.assertEqual(diagnostic.params, {"suggested_tables": 13})

    def test_no_tight_warning_when_the_design_applies(self):
        _, diagnostics, _ = precheck(_plain(64, 8, 8, 5), C2C3)
        self.assertNotIn("tight", _codes(diagnostics))

    # --- validity by brute force ---

    def test_bounds_hold_on_six_persons_two_tables_of_three(self):
        problem = _plain(6, 2, 3, 3)
        for options in (C2, C3, C2C3):
            lower_bound, _, targets = precheck(problem, options)
            best = _brute_force_minimum(problem, options, targets)
            self.assertGreater(lower_bound, 0)
            self.assertGreaterEqual(best, lower_bound)

    def test_bounds_hold_on_six_persons_three_tables_of_two(self):
        persons = tuple(
            Person(key, "a" if key <= 4 else None) for key in range(1, 7)
        )
        problem = Problem(persons, tuple(Table(n, 2) for n in (1, 2, 3)), 2)
        for options in (C1, C2C3):
            lower_bound, _, targets = precheck(problem, options)
            best = _brute_force_minimum(problem, options, targets)
            self.assertGreaterEqual(best, lower_bound)
        lower_bound, _, targets = precheck(problem, C1)
        self.assertEqual(lower_bound, 200)
        self.assertEqual(_brute_force_minimum(problem, C1, targets), 200)

    def test_lb1_is_a_floor_for_the_targets_occupation_only(self):
        """LB1 (01 §4) majorizes plans that occupy the tables as
        `targets` prescribes — the only occupation `generate` ever
        searches — not every capacity-respecting occupation.
        `table_targets` optimizes table sizes for C2/C3, not for
        company spread, and can leave a table closed (occupation 0)
        where opening it would scatter a company further: 5 people,
        one company of 4, 3 tables of 4 seats, C1 alone. `targets`
        closes the third table, (3, 2, 0), and LB1 gives 400; the SAME
        capacity, occupied instead as (1, 1, 3) — never searched,
        since generation only ever seats people onto `targets` — opens
        all three and reaches 200, below the bound `precheck` reports
        as the minimum. A test asserting the general property here —
        that no capacity-respecting occupation beats the bound — would
        fail on this exact instance.
        """
        persons = tuple(
            Person(key, "a" if key <= 4 else None) for key in range(1, 6)
        )
        problem = Problem(persons, tuple(Table(n, 4) for n in (1, 2, 3)), 2)

        lower_bound, _, targets = precheck(problem, C1)
        self.assertEqual(targets, (3, 2, 0))
        self.assertEqual(lower_bound, 400)

        # The property LB1 actually proves: tight for the occupation
        # `targets` prescribes.
        self.assertEqual(
            _brute_force_minimum(problem, C1, targets), lower_bound
        )

        # The property it does NOT prove, checked over every
        # capacity-respecting occupation rather than assumed: this
        # same bound does not majorize all of them.
        best_any_occupation = _brute_force_minimum_any_occupation(problem, C1)
        self.assertEqual(best_any_occupation, 200)
        self.assertLess(best_any_occupation, lower_bound)
