# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import random

from odoo.addons.erplibre_event_table.rotation import (
    Options,
    Person,
    Placement,
    Problem,
    RotationState,
    Table,
)
from odoo.tests.common import BaseCase

ALL_OPTIONS = Options(
    separate_companies=True,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=True,
)


def _six_persons():
    """Keys 1..6; 1 and 2 at "a", 3 and 4 at "b", 5 and 6 without a company."""
    companies = ["a", "a", "b", "b", None, None]
    return tuple(
        Person(key, company) for key, company in zip(range(1, 7), companies)
    )


def _two_tables_of_three():
    return (Table(1, 3), Table(2, 3))


def _seat(state, seating_by_round):
    """Seat persons: seating_by_round[r][t] is a list of person indices."""
    for r, seating in enumerate(seating_by_round):
        for t, group in enumerate(seating):
            for p in group:
                state.place(r, p, t)


class TestRotationState(BaseCase):
    """Dense counters, exact deltas, snapshot and restore."""

    def _state(self, rounds=2):
        problem = Problem(_six_persons(), _two_tables_of_three(), rounds)
        return RotationState(problem, ALL_OPTIONS, (3, 3))

    def _twice_the_same(self):
        state = self._state()
        _seat(state, [[[0, 1, 2], [3, 4, 5]], [[0, 1, 2], [3, 4, 5]]])
        return state

    def test_dense_indices_follow_the_person_keys(self):
        state = self._state()
        self.assertEqual(state.keys, (1, 2, 3, 4, 5, 6))
        self.assertEqual(state.numbers, (1, 2))
        self.assertEqual(state.comp, [0, 0, 1, 1, -1, -1])
        self.assertEqual(state.open_tables, (0, 1))
        self.assertEqual((state.N, state.T, state.R), (6, 2, 2))
        self.assertEqual((state.w1, state.w2, state.w3), (100, 10, 1))

    def test_inactive_options_carry_a_zero_weight(self):
        problem = Problem(_six_persons(), _two_tables_of_three(), 2)
        state = RotationState(problem, Options(), (3, 3))
        self.assertEqual((state.w1, state.w2, state.w3), (100, 10, 0))

    def test_place_fills_the_counters(self):
        state = self._twice_the_same()
        self.assertEqual(state.members[0][0], [0, 1, 2])
        self.assertEqual(state.table_of[1][4], 1)
        self.assertEqual(state.meet[0][1], 2)
        self.assertEqual(state.meet[0][3], 0)
        self.assertEqual(state.meet[0][0], 0)
        self.assertEqual(state.visits[0][0], 2)
        self.assertEqual(state.visits[0][1], 0)

    def test_full_cost_adds_the_three_penalties(self):
        # k1 = 2 (the "a" pair each round), k2 = 6 (six pairs met twice),
        # k3 = 6 (six persons at a single table).
        self.assertEqual(self._twice_the_same().full_cost(), 266)

    def test_delta_swap_is_exact(self):
        state = self._twice_the_same()
        delta = state.delta_swap(1, 2, 3)
        self.assertEqual(delta, -42)
        state.apply_swap(1, 2, 3)
        self.assertEqual(state.full_cost(), 224)

    def test_delta_label_leaves_companies_and_meetings_untouched(self):
        state = self._twice_the_same()
        state.apply_swap(1, 2, 3)
        delta = state.delta_label(1, 0, 1)
        self.assertEqual(delta, -2)
        state.apply_label(1, 0, 1)
        self.assertEqual(state.full_cost(), 222)
        # Only table returns change: k1 and k2 stay untouched.
        self.assertEqual(state.meet[0][1], 2)
        self.assertEqual(state.table_of[1][0], 1)

    def test_local_cost_sees_the_conflicts_of_one_person(self):
        state = self._twice_the_same()
        # Person 0: one colleague (100), two pairs met again (2 x 10),
        # one table visited again (1).
        self.assertEqual(state.local_cost(0, 0), 121)
        self.assertEqual(state.local_cost(0, 4), 21)

    def test_local_cost_is_zero_without_conflict(self):
        state = self._state(rounds=1)
        _seat(state, [[[0, 2, 4], [1, 3, 5]]])
        for p in range(6):
            self.assertEqual(state.local_cost(0, p), 0)
        self.assertEqual(state.full_cost(), 0)

    def test_snapshot_and_restore_come_back_to_the_same_plan(self):
        state = self._twice_the_same()
        snap = state.snapshot()
        before = state.placements()
        state.apply_swap(0, 0, 3)
        state.apply_swap(1, 1, 4)
        self.assertNotEqual(state.placements(), before)
        state.restore(snap)
        self.assertEqual(state.placements(), before)
        self.assertEqual(state.full_cost(), 266)

    def test_placements_are_sorted_and_carry_public_numbers(self):
        placements = self._twice_the_same().placements()
        self.assertEqual(len(placements), 12)
        self.assertEqual(placements[0], Placement(1, 1, 1, 0))
        self.assertEqual(placements[3], Placement(1, 4, 2, 0))
        self.assertEqual([pl.round for pl in placements], [1] * 6 + [2] * 6)

    def test_two_thousand_mixed_moves_keep_the_cost_exact(self):
        """The decisive test: the incremental cost never drifts."""
        persons = tuple(
            Person(key, "a" if key <= 6 else ("b" if key <= 12 else None))
            for key in range(1, 25)
        )
        tables = tuple(Table(number, 4) for number in range(1, 7))
        problem = Problem(persons, tables, 5)
        targets = (4,) * 6
        state = RotationState(problem, ALL_OPTIONS, targets)
        for r in range(5):
            for p in range(24):
                state.place(r, p, (p + r) % 6)
        cost = state.full_cost()
        rng = random.Random(20260915)
        moves = 0
        while moves < 2000:
            r = rng.randrange(5)
            if rng.randrange(2):
                p, q = rng.randrange(24), rng.randrange(24)
                if state.table_of[r][p] == state.table_of[r][q]:
                    continue
                delta = state.delta_swap(r, p, q)
                state.apply_swap(r, p, q)
            else:
                t, u = rng.randrange(6), rng.randrange(6)
                if t == u or len(state.members[r][t]) != len(
                    state.members[r][u]
                ):
                    continue
                delta = state.delta_label(r, t, u)
                state.apply_label(r, t, u)
            cost += delta
            moves += 1
            self.assertEqual(cost, state.full_cost())
        self.assertEqual(moves, 2000)

    def test_a_swap_keeps_every_person_seated_once_per_round(self):
        state = self._twice_the_same()
        state.apply_swap(0, 1, 5)
        for r in range(2):
            seated = [p for t in range(2) for p in state.members[r][t]]
            self.assertEqual(sorted(seated), list(range(6)))
            self.assertEqual(
                sorted(len(state.members[r][t]) for t in range(2)), [3, 3]
            )
        for r in range(2):
            for t in range(2):
                for index, p in enumerate(state.members[r][t]):
                    self.assertEqual(state.pos[r][p], index)
                    self.assertEqual(state.table_of[r][p], t)
