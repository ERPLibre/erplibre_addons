# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from math import comb
from typing import Sequence

from .model import Placement


class RotationState:
    """Working plan, in dense indices, with its counters.

    Persons are numbered 0 to N-1 in increasing order of Person.key,
    tables 0 to T-1 in the order of the Problem, companies 0.. by first
    occurrence in that order of persons. Rounds run 0 to R-1;
    Placement.round runs 1 to R. meet and visits are bytearrays, hence
    the 50-round limit.
    """

    def __init__(self, problem, options, targets: Sequence[int]) -> None:
        """Build an empty plan: nobody is seated yet.

        Sorts the persons by Person.key and keeps their keys in keys;
        keeps the table numbers in numbers, in the order of the Problem;
        numbers the companies 0.. by first occurrence in that order of
        persons, and sets comp[p] to -1 for a person without a company.
        Derives w1, w2 and w3 from the weights and the options - an
        inactive option carries a zero weight - then open_tables, the
        indices whose target is nonzero. Finally allocates the counters.
        """
        sorted_persons = sorted(problem.persons, key=lambda person: person.key)
        self.keys: tuple[int, ...] = tuple(
            person.key for person in sorted_persons
        )
        self.numbers: tuple[int, ...] = tuple(
            table.number for table in problem.tables
        )
        self.targets: tuple[int, ...] = tuple(targets)
        self.open_tables: tuple[int, ...] = tuple(
            index for index, target in enumerate(self.targets) if target > 0
        )

        self.N = len(sorted_persons)
        self.T = len(problem.tables)
        self.R = problem.rounds

        weights = options.weights
        self.w1 = weights[0] if options.separate_companies else 0
        self.w2 = weights[1] if options.avoid_repeat_neighbors else 0
        self.w3 = weights[2] if options.avoid_repeat_table else 0

        company_index: dict = {}
        comp = []
        for person in sorted_persons:
            if person.company is None:
                comp.append(-1)
                continue
            if person.company not in company_index:
                company_index[person.company] = len(company_index)
            comp.append(company_index[person.company])
        self.comp: list[int] = comp

        self._reset_counters()

    def _reset_counters(self) -> None:
        """Bring every dense counter back to its empty-plan state."""
        self.table_of: list[list[int]] = [[-1] * self.N for _ in range(self.R)]
        self.members: list[list[list[int]]] = [
            [[] for _ in range(self.T)] for _ in range(self.R)
        ]
        self.pos: list[list[int]] = [[-1] * self.N for _ in range(self.R)]
        self.meet: list[bytearray] = [bytearray(self.N) for _ in range(self.N)]
        self.visits: list[bytearray] = [
            bytearray(self.T) for _ in range(self.N)
        ]

    def place(self, r: int, p: int, t: int) -> None:
        """Seat p at table t in round r. O(table size).

        Updates meet, visits, members, pos and table_of. Assumes p is
        not already seated in this round.
        """
        for x in self.members[r][t]:
            self.meet[p][x] += 1
            self.meet[x][p] += 1
        self.visits[p][t] += 1
        self.pos[r][p] = len(self.members[r][t])
        self.members[r][t].append(p)
        self.table_of[r][p] = t

    def delta_swap(self, r: int, p: int, q: int) -> int:
        """Return the exact cost change of swapping p and q in round r.

        O(size of the two tables involved). Precondition:
        table_of[r][p] != table_of[r][q].
        """
        t, u = self.table_of[r][p], self.table_of[r][q]
        d1 = d2 = 0
        for x in self.members[r][t]:
            if x != p:
                d2 += self.meet[q][x] - self.meet[p][x] + 1
                if self.comp[x] >= 0:
                    d1 += (self.comp[x] == self.comp[q]) - (
                        self.comp[x] == self.comp[p]
                    )
        for y in self.members[r][u]:
            if y != q:
                d2 += self.meet[p][y] - self.meet[q][y] + 1
                if self.comp[y] >= 0:
                    d1 += (self.comp[y] == self.comp[p]) - (
                        self.comp[y] == self.comp[q]
                    )
        d3 = (
            self.visits[p][u]
            - self.visits[p][t]
            + self.visits[q][t]
            - self.visits[q][u]
            + 2
        )
        return self.w1 * d1 + self.w2 * d2 + self.w3 * d3

    def apply_swap(self, r: int, p: int, q: int) -> None:
        """Swap p and q in round r. O(size of the two tables involved)."""
        t, u = self.table_of[r][p], self.table_of[r][q]
        for x in self.members[r][t]:
            if x != p:
                self.meet[p][x] -= 1
                self.meet[x][p] -= 1
                self.meet[q][x] += 1
                self.meet[x][q] += 1
        for y in self.members[r][u]:
            if y != q:
                self.meet[q][y] -= 1
                self.meet[y][q] -= 1
                self.meet[p][y] += 1
                self.meet[y][p] += 1
        i, j = self.pos[r][p], self.pos[r][q]
        self.members[r][t][i], self.members[r][u][j] = q, p
        self.pos[r][p], self.pos[r][q] = j, i
        self.table_of[r][p], self.table_of[r][q] = u, t
        self.visits[p][t] -= 1
        self.visits[p][u] += 1
        self.visits[q][u] -= 1
        self.visits[q][t] += 1

    def delta_label(self, r: int, t: int, u: int) -> int:
        """Return the exact cost change of swapping the numbers of t and u.

        O(table size). k1 and k2 do not move: only k3 changes.
        Precondition: len(members[r][t]) == len(members[r][u]).
        """
        return self.w3 * (
            sum(
                self.visits[p][u] - self.visits[p][t] + 1
                for p in self.members[r][t]
            )
            + sum(
                self.visits[q][t] - self.visits[q][u] + 1
                for q in self.members[r][u]
            )
        )

    def apply_label(self, r: int, t: int, u: int) -> None:
        """Swap the numbers of tables t and u in round r.

        k1 and k2 are untouched; pos stays valid since whole member
        lists are exchanged.
        """
        for p in self.members[r][t]:
            self.visits[p][t] -= 1
            self.visits[p][u] += 1
            self.table_of[r][p] = u
        for q in self.members[r][u]:
            self.visits[q][u] -= 1
            self.visits[q][t] += 1
            self.table_of[r][q] = t
        self.members[r][t], self.members[r][u] = (
            self.members[r][u],
            self.members[r][t],
        )

    def local_cost(self, r: int, p: int) -> int:
        """Return the part of the cost that moving p in round r can cut.

        O(table size).
        """
        t = self.table_of[r][p]
        cost = 0
        for x in self.members[r][t]:
            if x != p:
                if self.meet[p][x] >= 2:
                    cost += self.w2 * (self.meet[p][x] - 1)
                if self.comp[p] >= 0 and self.comp[x] == self.comp[p]:
                    cost += self.w1
        if self.visits[p][t] >= 2:
            cost += self.w3 * (self.visits[p][t] - 1)
        return cost

    def full_cost(self) -> int:
        """Recompute the whole cost from the counters.

        k1 counts companies at each table (never over a set of strings:
        counted through comp, indexed by dense company number), k2
        counts repeated meetings, k3 counts repeated table visits.
        """
        k1 = 0
        for r in range(self.R):
            for t in range(self.T):
                counts: dict = {}
                for p in self.members[r][t]:
                    c = self.comp[p]
                    if c >= 0:
                        counts[c] = counts.get(c, 0) + 1
                for count in counts.values():
                    k1 += comb(count, 2)

        k2 = 0
        for p in range(self.N):
            for q in range(p + 1, self.N):
                k2 += comb(self.meet[p][q], 2)

        k3 = 0
        for p in range(self.N):
            for t in range(self.T):
                k3 += comb(self.visits[p][t], 2)

        return self.w1 * k1 + self.w2 * k2 + self.w3 * k3

    def snapshot(self) -> tuple[tuple[int, ...], ...]:
        """Return the current plan as one tuple of table indices per round."""
        return tuple(tuple(self.table_of[r]) for r in range(self.R))

    def restore(self, snap: tuple[tuple[int, ...], ...]) -> None:
        """Bring the plan back to a snapshot. O(N.R.table size).

        Resets every counter to empty, then replays place() in round and
        person order, so no counter can drift from the snapshot.
        """
        self._reset_counters()
        for r, row in enumerate(snap):
            for p, t in enumerate(row):
                if t != -1:
                    self.place(r, p, t)

    def placements(self) -> tuple[Placement, ...]:
        """Return the plan as public Placements, seat always 0.

        Sorted by (round, table number, person key); rounds and table
        numbers are converted back from dense indices.
        """
        result = [
            Placement(r + 1, self.keys[p], self.numbers[t], 0)
            for r in range(self.R)
            for t in range(self.T)
            for p in self.members[r][t]
        ]
        result.sort(
            key=lambda placement: (
                placement.round,
                placement.table,
                placement.person,
            )
        )
        return tuple(result)
