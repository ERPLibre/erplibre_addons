# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import random
import time

from odoo.addons.erplibre_event_table.rotation import (
    Options,
    Person,
    Problem,
    RotationState,
    Table,
    build_design,
    build_greedy,
    design_applicable,
    precheck,
    search,
)
from odoo.tests.common import BaseCase

ALL_OPTIONS = Options(
    separate_companies=True,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)
C2 = Options(
    separate_companies=False,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=False,
)
C2C3 = Options(
    separate_companies=False,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)


def _uniform(count, tables, capacity, rounds, company_size=0):
    persons = tuple(
        Person(key, "a" if key <= company_size else None)
        for key in range(1, count + 1)
    )
    numbers = tuple(Table(number, capacity) for number in range(1, tables + 1))
    return Problem(persons, numbers, rounds)


def _built(problem, options, seed, force_greedy=False):
    """Return (built state, bound, targets) ready for search."""
    lower_bound, _, targets = precheck(problem, options)
    state = RotationState(problem, options, targets)
    rng = random.Random(seed)
    if not force_greedy and design_applicable(problem, options, targets):
        build_design(state, rng)
    else:
        build_greedy(state, rng)
    return state, lower_bound, targets


class TestRotationSearch(BaseCase):
    """Four stop causes, two moves, determinism."""

    def _assert_plan_is_valid(self, state, targets):
        for r in range(state.R):
            seated = [p for t in range(state.T) for p in state.members[r][t]]
            self.assertEqual(sorted(seated), list(range(state.N)))
            sizes = [len(state.members[r][t]) for t in range(state.T)]
            self.assertEqual(sorted(sizes), sorted(targets))

    def test_search_stops_at_once_on_a_plan_already_at_the_bound(self):
        problem = _uniform(40, 8, 5, 4)
        state, lower_bound, targets = _built(problem, C2C3, 1)
        self.assertEqual(lower_bound, 0)
        self.assertEqual(state.full_cost(), 0)
        best, stopped_by = search(
            state, lower_bound, random.Random(1), 10**6, None
        )
        self.assertEqual(best, 0)
        self.assertEqual(stopped_by, "lower_bound")

    def test_search_reaches_zero_on_forty_persons_with_a_company_of_seven(
        self,
    ):
        problem = _uniform(40, 8, 5, 4, company_size=7)
        state, lower_bound, targets = _built(
            problem, ALL_OPTIONS, 3, force_greedy=True
        )
        self.assertEqual(lower_bound, 0)
        best, stopped_by = search(
            state, lower_bound, random.Random(3), 200000, None
        )
        self.assertEqual(best, 0)
        self.assertEqual(stopped_by, "lower_bound")
        self.assertEqual(state.full_cost(), 0)
        self._assert_plan_is_valid(state, targets)

    def test_search_reaches_zero_on_two_hundred_persons(self):
        problem = _uniform(200, 25, 8, 6, company_size=24)
        state, lower_bound, targets = _built(
            problem, ALL_OPTIONS, 5, force_greedy=True
        )
        self.assertEqual(lower_bound, 0)
        best, stopped_by = search(
            state, lower_bound, random.Random(5), 200000, None
        )
        self.assertEqual(best, 0)
        self.assertEqual(stopped_by, "lower_bound")
        self._assert_plan_is_valid(state, targets)

    def test_search_reaches_the_proven_bound_on_thirty_six_persons(self):
        problem = _uniform(36, 6, 6, 3)
        state, lower_bound, targets = _built(problem, C2C3, 7)
        self.assertEqual(lower_bound, 18)
        best, stopped_by = search(
            state, lower_bound, random.Random(7), 200000, None
        )
        self.assertEqual(best, 18)
        self.assertEqual(stopped_by, "lower_bound")
        self._assert_plan_is_valid(state, targets)

    def test_search_stops_on_the_iteration_ceiling(self):
        # This instance has no solution without a repeat: it would take
        # two mutually orthogonal Latin squares of order six.
        problem = _uniform(36, 6, 6, 4)
        state, lower_bound, targets = _built(problem, C2, 11)
        self.assertEqual(lower_bound, 0)
        best, stopped_by = search(
            state, lower_bound, random.Random(11), 500, None
        )
        self.assertEqual(stopped_by, "iterations")
        self.assertGreater(best, 0)
        self._assert_plan_is_valid(state, targets)

    def test_search_stops_on_the_deadline(self):
        problem = _uniform(120, 12, 10, 4)
        state, lower_bound, targets = _built(problem, C2C3, 13)
        before = state.full_cost()
        best, stopped_by = search(
            state,
            lower_bound,
            random.Random(13),
            10**9,
            time.monotonic() - 1.0,
        )
        self.assertEqual(stopped_by, "time")
        self.assertLessEqual(best, before)
        self._assert_plan_is_valid(state, targets)

    def test_search_stops_when_no_conflict_is_left(self):
        problem = _uniform(40, 8, 5, 4, company_size=7)
        state, _, targets = _built(problem, ALL_OPTIONS, 17, force_greedy=True)
        # A negative bound can never be reached, so once the cost hits
        # zero, the only remaining exit is the absence of conflict.
        best, stopped_by = search(state, -1, random.Random(17), 200000, None)
        self.assertEqual(best, 0)
        self.assertEqual(stopped_by, "no_conflict")

    def test_search_is_deterministic_for_a_seed(self):
        problem = _uniform(40, 8, 5, 4, company_size=7)
        first, lower_bound, _ = _built(
            problem, ALL_OPTIONS, 19, force_greedy=True
        )
        first_best, first_stop = search(
            first, lower_bound, random.Random(19), 4000, None
        )
        second, _, _ = _built(problem, ALL_OPTIONS, 19, force_greedy=True)
        second_best, second_stop = search(
            second, lower_bound, random.Random(19), 4000, None
        )
        self.assertEqual(first_best, second_best)
        self.assertEqual(first_stop, second_stop)
        self.assertEqual(first.placements(), second.placements())

    def test_search_leaves_the_best_plan_in_the_state(self):
        problem = _uniform(120, 12, 10, 4)
        state, lower_bound, _ = _built(problem, C2C3, 23)
        best, _ = search(state, lower_bound, random.Random(23), 3000, None)
        self.assertEqual(state.full_cost(), best)

    def test_search_lowers_the_cost_of_a_dense_instance(self):
        problem = _uniform(24, 6, 4, 3)
        state, lower_bound, targets = _built(problem, C2C3, 29)
        before = state.full_cost()
        best, _ = search(state, lower_bound, random.Random(29), 20000, None)
        self.assertLessEqual(best, before)
        self.assertGreaterEqual(best, lower_bound)
        self._assert_plan_is_valid(state, targets)
