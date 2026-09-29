# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import random

from odoo.addons.erplibre_event_table.rotation import (
    Options,
    Person,
    Problem,
    RotationState,
    Table,
    build_design,
    build_greedy,
    design_applicable,
    gf_tables,
    is_prime_power,
    table_targets,
)
from odoo.tests.common import BaseCase

C2C3 = Options(
    separate_companies=False,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)
ALL_OPTIONS = Options(
    separate_companies=True,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)


def _uniform(count, tables, capacity, rounds, company_size=0):
    """count persons; the first company_size of them share company "a"."""
    persons = tuple(
        Person(key, "a" if key <= company_size else None)
        for key in range(1, count + 1)
    )
    numbers = tuple(Table(number, capacity) for number in range(1, tables + 1))
    return Problem(persons, numbers, rounds)


def _state(problem, options):
    targets = table_targets(
        [table.capacity for table in problem.tables],
        len(problem.persons),
        options.min_table_size,
    )
    return RotationState(problem, options, targets), tuple(targets)


class TestRotationConstruct(BaseCase):
    """Finite fields, algebraic design, greedy construction."""

    # --- finite fields ---

    def test_is_prime_power(self):
        for q in (2, 3, 4, 5, 7, 8, 9, 11, 13, 16, 25, 27, 32, 49):
            self.assertTrue(is_prime_power(q), q)
        for q in (1, 6, 10, 12, 14, 15, 36, 48):
            self.assertFalse(is_prime_power(q), q)

    def test_every_non_zero_element_has_an_inverse(self):
        for q in (2, 3, 5, 7, 11, 13, 4, 8, 9, 16, 25, 27, 32, 49):
            add, mul = gf_tables(q)
            self.assertEqual(len(add), q)
            self.assertEqual(len(mul), q)
            for x in range(1, q):
                inverses = [y for y in range(1, q) if mul[x][y] == 1]
                self.assertEqual(len(inverses), 1, (q, x))

    def test_the_field_axioms_hold(self):
        for q in (4, 9, 25, 32):
            add, mul = gf_tables(q)
            for x in range(q):
                self.assertEqual(add[x][0], x)
                self.assertEqual(mul[x][1], x)
                self.assertEqual(mul[x][0], 0)
                for y in range(q):
                    self.assertEqual(add[x][y], add[y][x])
                    self.assertEqual(mul[x][y], mul[y][x])
                    for z in range(q):
                        self.assertEqual(
                            mul[x][add[y][z]],
                            add[mul[x][y]][mul[x][z]],
                        )

    def test_gf_tables_refuses_a_field_without_polynomial(self):
        with self.assertRaises(ValueError):
            gf_tables(121)
        with self.assertRaises(ValueError):
            gf_tables(6)

    # --- design_applicable ---

    def test_design_applies_to_a_full_prime_power_plan(self):
        problem = _uniform(40, 8, 5, 4)
        _, targets = _state(problem, C2C3)
        self.assertTrue(design_applicable(problem, C2C3, targets))

    def test_design_accepts_k_equal_to_the_table_count(self):
        problem = _uniform(64, 8, 8, 5)
        _, targets = _state(problem, C2C3)
        self.assertTrue(design_applicable(problem, C2C3, targets))

    def test_design_refuses_a_composite_table_count(self):
        problem = _uniform(120, 12, 10, 4)
        _, targets = _state(problem, C2C3)
        self.assertFalse(design_applicable(problem, C2C3, targets))

    def test_design_refuses_more_rounds_than_tables(self):
        problem = _uniform(30, 5, 6, 6)
        _, targets = _state(problem, C2C3)
        self.assertFalse(design_applicable(problem, C2C3, targets))

    def test_design_refuses_a_closed_table(self):
        problem = _uniform(15, 10, 8, 3)
        _, targets = _state(problem, C2C3)
        self.assertIn(0, targets)
        self.assertFalse(design_applicable(problem, C2C3, targets))

    def test_design_needs_a_thick_enough_last_column(self):
        # 19 people over 7 columns: k = 3 with two ghost cells, so the
        # last column carries only 2 real people.
        problem = _uniform(19, 7, 6, 4)
        targets = (3, 3, 3, 3, 3, 2, 2)
        loose = Options(
            separate_companies=False,
            avoid_repeat_neighbors=True,
            avoid_repeat_table=True,
            min_table_size=2,
        )
        strict = Options(
            separate_companies=False,
            avoid_repeat_neighbors=True,
            avoid_repeat_table=True,
            min_table_size=3,
        )
        self.assertTrue(design_applicable(problem, loose, targets))
        self.assertFalse(design_applicable(problem, strict, targets))

    # --- build_design ---

    def test_the_design_leaves_no_violation(self):
        cases = [
            (28, 7, 4, 4),
            (26, 7, 4, 4),
            (40, 8, 5, 4),
            (37, 8, 5, 4),
            (45, 9, 5, 4),
            (43, 9, 5, 4),
            (66, 11, 6, 5),
            (64, 11, 6, 5),
        ]
        for count, tables, capacity, rounds in cases:
            problem = _uniform(count, tables, capacity, rounds)
            state, targets = _state(problem, C2C3)
            self.assertTrue(design_applicable(problem, C2C3, targets))
            build_design(state, random.Random(11))
            self.assertEqual(state.full_cost(), 0, (count, tables))
            for r in range(rounds):
                seated = [
                    p for t in range(tables) for p in state.members[r][t]
                ]
                self.assertEqual(sorted(seated), list(range(count)))
                sizes = [len(state.members[r][t]) for t in range(tables)]
                self.assertEqual(sorted(sizes), sorted(targets))
                for size in sizes:
                    self.assertLessEqual(size, capacity)

    def test_the_design_reaches_the_bound_when_k_equals_the_table_count(self):
        problem = _uniform(64, 8, 8, 5)
        state, targets = _state(problem, C2C3)
        build_design(state, random.Random(3))
        # One column draws mu = 0: its eight members keep their table for
        # all five rounds, which equals exactly the proven bound.
        self.assertEqual(state.full_cost(), 80)

    def test_the_design_is_deterministic_for_a_seed(self):
        problem = _uniform(40, 8, 5, 4)
        first, targets = _state(problem, C2C3)
        build_design(first, random.Random(5))
        second, _ = _state(problem, C2C3)
        build_design(second, random.Random(5))
        self.assertEqual(first.placements(), second.placements())

    # --- build_greedy ---

    def test_the_greedy_construction_keeps_the_invariants(self):
        problem = _uniform(40, 8, 5, 4, company_size=7)
        state, targets = _state(problem, ALL_OPTIONS)
        build_greedy(state, random.Random(2))
        for r in range(4):
            seated = [p for t in range(8) for p in state.members[r][t]]
            self.assertEqual(sorted(seated), list(range(40)))
            sizes = [len(state.members[r][t]) for t in range(8)]
            self.assertEqual(sorted(sizes), sorted(targets))
        self.assertGreaterEqual(state.full_cost(), 0)

    def test_the_greedy_construction_fills_uneven_targets(self):
        problem = _uniform(15, 10, 8, 3)
        state, targets = _state(problem, ALL_OPTIONS)
        build_greedy(state, random.Random(4))
        self.assertEqual(sorted(targets), [0, 0, 0, 2, 2, 2, 2, 2, 2, 3])
        for r in range(3):
            sizes = [len(state.members[r][t]) for t in range(10)]
            self.assertEqual(sorted(sizes), sorted(targets))

    def test_the_greedy_construction_is_deterministic_for_a_seed(self):
        problem = _uniform(40, 8, 5, 4, company_size=7)
        first, _ = _state(problem, ALL_OPTIONS)
        build_greedy(first, random.Random(9))
        second, _ = _state(problem, ALL_OPTIONS)
        build_greedy(second, random.Random(9))
        self.assertEqual(first.placements(), second.placements())

    def test_the_greedy_construction_ignores_the_person_order(self):
        straight = _uniform(40, 8, 5, 4, company_size=7)
        shuffled = Problem(
            tuple(reversed(straight.persons)), straight.tables, 4
        )
        first, _ = _state(straight, ALL_OPTIONS)
        build_greedy(first, random.Random(9))
        second, _ = _state(shuffled, ALL_OPTIONS)
        build_greedy(second, random.Random(9))
        self.assertEqual(first.placements(), second.placements())
