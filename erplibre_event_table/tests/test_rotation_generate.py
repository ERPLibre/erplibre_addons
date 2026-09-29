# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import time

from odoo.addons.erplibre_event_table.rotation import (
    Options,
    Person,
    Problem,
    Table,
    generate,
    signature,
)
from odoo.tests.common import BaseCase

ALL_OPTIONS = Options(
    separate_companies=True,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)
C2C3 = Options(
    separate_companies=False,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)
NOTHING = Options(
    separate_companies=False,
    avoid_repeat_neighbors=False,
    avoid_repeat_table=False,
)


def _uniform(count, tables, capacity, rounds, company_size=0):
    persons = tuple(
        Person(key, "a" if key <= company_size else None)
        for key in range(1, count + 1)
    )
    numbers = tuple(Table(number, capacity) for number in range(1, tables + 1))
    return Problem(persons, numbers, rounds)


def _codes(diagnostics):
    return [diagnostic.code for diagnostic in diagnostics]


class TestRotationGenerate(BaseCase):
    """Determinism, diversity, the global budget, seats."""

    def test_generate_rejects_a_problem_with_duplicate_person_keys(self):
        problem = Problem((Person(1), Person(1)), (Table(1, 4),), 2)
        with self.assertRaises(ValueError):
            generate(problem, ALL_OPTIONS)

    def test_generate_rejects_rounds_out_of_range(self):
        problem = _uniform(9, 2, 4, 60)
        with self.assertRaises(ValueError):
            generate(problem, ALL_OPTIONS)

    def test_a_blocking_diagnostic_returns_no_combination(self):
        result = generate(_uniform(9, 2, 4, 2), ALL_OPTIONS)
        self.assertEqual(_codes(result.diagnostics), ["capacity_short"])
        self.assertEqual(result.combinations, ())
        self.assertEqual(result.targets, ())

    def test_the_targets_name_every_configured_table(self):
        result = generate(
            _uniform(15, 10, 8, 2),
            ALL_OPTIONS,
            count=1,
            time_budget=None,
            max_iterations=2000,
        )
        self.assertEqual(
            result.targets,
            (
                (1, 3),
                (2, 2),
                (3, 2),
                (4, 2),
                (5, 2),
                (6, 2),
                (7, 2),
                (8, 0),
                (9, 0),
                (10, 0),
            ),
        )

    def test_the_same_seed_gives_the_same_plan(self):
        problem = _uniform(40, 8, 5, 4, company_size=7)
        first = generate(
            problem,
            ALL_OPTIONS,
            count=3,
            seed=7,
            time_budget=None,
            max_iterations=50000,
        )
        second = generate(
            problem,
            ALL_OPTIONS,
            count=3,
            seed=7,
            time_budget=None,
            max_iterations=50000,
        )
        self.assertEqual(len(first.combinations), 3)
        for left, right in zip(first.combinations, second.combinations):
            self.assertEqual(left.placements, right.placements)
            self.assertEqual(left.indicators, right.indicators)
            self.assertEqual(left.seed, right.seed)

    def test_the_person_order_does_not_change_the_plan(self):
        straight = _uniform(40, 8, 5, 4, company_size=7)
        reversed_order = Problem(
            tuple(reversed(straight.persons)), straight.tables, 4
        )
        first = generate(
            straight,
            ALL_OPTIONS,
            count=2,
            seed=11,
            time_budget=None,
            max_iterations=50000,
        )
        second = generate(
            reversed_order,
            ALL_OPTIONS,
            count=2,
            seed=11,
            time_budget=None,
            max_iterations=50000,
        )
        for left, right in zip(first.combinations, second.combinations):
            self.assertEqual(left.placements, right.placements)

    def test_the_combinations_are_distinct_and_far_apart(self):
        result = generate(
            _uniform(40, 8, 5, 4, company_size=7),
            ALL_OPTIONS,
            count=3,
            seed=13,
            time_budget=None,
            max_iterations=50000,
        )
        self.assertEqual(len(result.combinations), 3)
        signatures = {
            signature(combination.placements)
            for combination in result.combinations
        }
        self.assertEqual(len(signatures), 3)
        self.assertEqual(result.combinations[0].distance_to_first, 0.0)
        for combination in result.combinations[1:]:
            self.assertFalse(combination.close_variant)
            self.assertGreaterEqual(combination.distance_to_first, 0.1855)
        self.assertNotIn("fewer_combinations", _codes(result.diagnostics))

    def test_four_persons_on_two_tables_of_two_give_three_combinations(self):
        result = generate(
            _uniform(4, 2, 2, 1),
            ALL_OPTIONS,
            count=5,
            seed=17,
            time_budget=None,
            max_iterations=1000,
        )
        self.assertEqual(len(result.combinations), 3)
        signatures = {
            signature(combination.placements)
            for combination in result.combinations
        }
        self.assertEqual(len(signatures), 3)
        diagnostic = [
            d for d in result.diagnostics if d.code == "fewer_combinations"
        ]
        self.assertEqual(len(diagnostic), 1)
        self.assertEqual(diagnostic[0].severity, "warning")
        self.assertEqual(diagnostic[0].params, {"count": 3, "requested": 5})

    def test_every_option_off_costs_nothing(self):
        result = generate(
            _uniform(40, 8, 5, 4, company_size=7),
            NOTHING,
            count=2,
            seed=19,
            time_budget=None,
            max_iterations=1000,
        )
        for combination in result.combinations:
            self.assertEqual(combination.indicators.cost, 0)
            self.assertEqual(combination.lower_bound, 0)
            self.assertTrue(combination.proven_optimal)
            self.assertEqual(combination.stopped_by, "lower_bound")

    def test_the_design_proves_the_bound_of_eighty(self):
        result = generate(
            _uniform(64, 8, 8, 5),
            C2C3,
            count=1,
            seed=23,
            time_budget=None,
            max_iterations=50000,
        )
        combination = result.combinations[0]
        self.assertEqual(combination.method, "design")
        self.assertEqual(combination.lower_bound, 80)
        self.assertEqual(combination.indicators.cost, 80)
        self.assertTrue(combination.proven_optimal)

    def test_a_composite_table_count_falls_back_to_the_greedy_build(self):
        result = generate(
            _uniform(120, 12, 10, 4),
            C2C3,
            count=1,
            seed=29,
            time_budget=None,
            max_iterations=2000,
        )
        self.assertEqual(result.combinations[0].method, "greedy")
        self.assertIn("tight", _codes(result.diagnostics))

    def test_the_time_budget_is_the_budget_of_the_whole_generation(self):
        started = time.monotonic()
        result = generate(
            _uniform(120, 12, 10, 4), C2C3, count=3, seed=31, time_budget=0.05
        )
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(len(result.combinations), 1)
        self.assertLess(elapsed, 2.0)
        self.assertIn(
            "time",
            [c.stopped_by for c in result.combinations],
        )

    def test_the_plan_seats_everyone_once_per_round(self):
        result = generate(
            _uniform(40, 8, 5, 4, company_size=7),
            ALL_OPTIONS,
            count=1,
            seed=37,
            time_budget=None,
            max_iterations=50000,
        )
        placements = result.combinations[0].placements
        self.assertEqual(len(placements), 160)
        for round_number in range(1, 5):
            of_round = [p for p in placements if p.round == round_number]
            self.assertEqual(
                sorted(p.person for p in of_round), list(range(1, 41))
            )
            sizes = {}
            for placement in of_round:
                sizes[placement.table] = sizes.get(placement.table, 0) + 1
            self.assertEqual(sorted(sizes.values()), [5] * 8)

    def test_seats_are_applied_when_the_option_asks_for_them(self):
        options = Options(
            separate_companies=True,
            avoid_repeat_neighbors=True,
            avoid_repeat_table=True,
            assign_seats=True,
        )
        result = generate(
            _uniform(40, 8, 5, 4, company_size=7),
            options,
            count=1,
            seed=41,
            time_budget=None,
            max_iterations=50000,
        )
        placements = result.combinations[0].placements
        seen = {}
        for placement in placements:
            self.assertGreaterEqual(placement.seat, 1)
            self.assertLessEqual(placement.seat, 5)
            key = (placement.round, placement.table, placement.seat)
            self.assertNotIn(key, seen)
            seen[key] = placement.person
        # 01 §1: placements stay sorted by (round, table, seat, person)
        # even once seats are assigned, not just table by table.
        keys = [(p.round, p.table, p.seat, p.person) for p in placements]
        self.assertEqual(keys, sorted(keys))

    def test_no_seat_is_given_when_the_option_is_off(self):
        result = generate(
            _uniform(40, 8, 5, 4),
            C2C3,
            count=1,
            seed=43,
            time_budget=None,
            max_iterations=1000,
        )
        for placement in result.combinations[0].placements:
            self.assertEqual(placement.seat, 0)
