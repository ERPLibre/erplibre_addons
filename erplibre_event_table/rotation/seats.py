# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Seat numbers within a table: a post-processing pass. See 01 S9."""
import random
from dataclasses import replace
from typing import Sequence

from .model import Options, Placement, Problem

COLLEAGUE_WEIGHT = 10
MET_BEFORE_WEIGHT = 1


def _table_groups(
    placements: Sequence[Placement],
) -> dict[tuple[int, int], list[int]]:
    """Group person keys by (round, table number), in placement order."""
    groups: dict[tuple[int, int], list[int]] = {}
    for placement in placements:
        groups.setdefault((placement.round, placement.table), []).append(
            placement.person
        )
    return groups


def _pair_cost(
    p: int,
    q: int,
    company_of: dict[int, str | None],
    met_before: set[tuple[int, int]],
) -> int:
    """Return the seating-adjacency penalty of putting p and q side by side."""
    cost = 0
    if company_of.get(p) is not None and company_of.get(p) == company_of.get(
        q
    ):
        cost += COLLEAGUE_WEIGHT
    pair = (p, q) if p < q else (q, p)
    if pair in met_before:
        cost += MET_BEFORE_WEIGHT
    return cost


def _circular_cost(
    order: Sequence[int],
    company_of: dict[int, str | None],
    met_before: set[tuple[int, int]],
) -> int:
    """Return the sum of the adjacency penalty over every seat neighbour."""
    n = len(order)
    return sum(
        _pair_cost(order[i], order[(i + 1) % n], company_of, met_before)
        for i in range(n)
    )


def _greedy_order(
    members: Sequence[int],
    company_of: dict[int, str | None],
    met_before: set[tuple[int, int]],
    rng: random.Random,
) -> list[int]:
    """Build a starting order by always appending the cheapest candidate.

    Ties are broken through rng, the only source of randomness the
    caller controls with its seed.
    """
    remaining = list(members)
    order = [remaining.pop(0)]
    while remaining:
        last = order[-1]
        costs = [
            _pair_cost(last, candidate, company_of, met_before)
            for candidate in remaining
        ]
        best = min(costs)
        ties = [
            candidate
            for candidate, cost in zip(remaining, costs)
            if cost == best
        ]
        chosen = rng.choice(ties)
        remaining.remove(chosen)
        order.append(chosen)
    return order


def _two_opt(
    order: list[int],
    company_of: dict[int, str | None],
    met_before: set[tuple[int, int]],
) -> None:
    """Swap seats in place until no swap lowers the circular cost.

    A table seats at most a dozen people in practice, so a full O(n^2)
    sweep per pass costs nothing worth optimizing away.
    """
    n = len(order)
    improved = True
    while improved:
        improved = False
        best_cost = _circular_cost(order, company_of, met_before)
        for i in range(n):
            for j in range(i + 1, n):
                order[i], order[j] = order[j], order[i]
                cost = _circular_cost(order, company_of, met_before)
                if cost < best_cost:
                    best_cost = cost
                    improved = True
                else:
                    order[i], order[j] = order[j], order[i]


def _check_capacities(
    problem: Problem, groups: dict[tuple[int, int], list[int]]
) -> dict[int, int]:
    """Return capacity_of, after checking every group against it.

    Raises ValueError on a placement naming a table absent from the
    problem - the same failure evaluate() and table_conflicts() raise -
    or on a table seated past its capacity, which would otherwise hand
    out the same seat number twice at _best_offset() below.
    """
    capacity_of = {table.number: table.capacity for table in problem.tables}
    for (_, table), members in groups.items():
        if table not in capacity_of:
            raise ValueError(
                f"placement names table {table}, not part of the problem"
            )
        if len(members) > capacity_of[table]:
            raise ValueError(
                f"table {table} seats {len(members)} people over its "
                f"capacity of {capacity_of[table]}"
            )
    return capacity_of


def _order_table(
    members: Sequence[int],
    company_of: dict[int, str | None],
    met_before: set[tuple[int, int]],
    rng: random.Random,
) -> list[int]:
    """Return the seating order around one table, colleagues kept apart."""
    order = sorted(members)
    if len(order) > 1:
        order = _greedy_order(order, company_of, met_before, rng)
        _two_opt(order, company_of, met_before)
    return order


def _meetings_before_each_round(
    groups: dict[tuple[int, int], list[int]], rounds: Sequence[int]
) -> dict[int, set[tuple[int, int]]]:
    """Return, for each round, the pairs already sharing a table earlier.

    Read straight off the input placements - never from the seats being
    built - so the "already met" criterion does not depend on how this
    round's table is ordered.
    """
    meet_before: dict[int, set[tuple[int, int]]] = {}
    known: set[tuple[int, int]] = set()
    for round_number in rounds:
        meet_before[round_number] = set(known)
        for (r, _table), members in groups.items():
            if r != round_number:
                continue
            for index, person in enumerate(members):
                for other in members[index + 1 :]:
                    pair = (
                        (person, other) if person < other else (other, person)
                    )
                    known.add(pair)
    return meet_before


def _best_offset(
    order: Sequence[int],
    table: int,
    capacity: int,
    seat_history: dict[int, set[tuple[int, int]]],
    rng: random.Random,
) -> int:
    """Return the seat offset that reuses the fewest earlier (table, seat).

    Ties - typically every offset, the first round of any table - are
    broken through rng.
    """
    n = len(order)
    best_count = None
    best_offsets = []
    for offset in range(capacity):
        count = 0
        for index, person in enumerate(order):
            seat = 1 + ((index * capacity // n + offset) % capacity)
            if (table, seat) in seat_history.get(person, ()):
                count += 1
        if best_count is None or count < best_count:
            best_count = count
            best_offsets = [offset]
        elif count == best_count:
            best_offsets.append(offset)
    return rng.choice(best_offsets)


def assign_seats(
    problem: Problem,
    placements: Sequence[Placement],
    options: Options,
    *,
    seed: int = 0,
) -> tuple[Placement, ...]:
    """Give every placement a seat number, table by table, round by round.

    A decoupled post-processing pass: seats change none of the three
    counters (company pairs, repeat meetings, table returns), only how
    a table looks on paper. Returns a new Placement sequence in the same
    order as the input. Rounds are handled in increasing order, so the
    offset choice below always sees the seat history already built.
    Raises ValueError on a placement naming an unknown table or on a
    table seated past its capacity - see _check_capacities().
    """
    company_of = {person.key: person.company for person in problem.persons}
    groups = _table_groups(placements)
    capacity_of = _check_capacities(problem, groups)
    rounds = sorted({round_number for round_number, _ in groups})
    meet_before_round = _meetings_before_each_round(groups, rounds)

    rng = random.Random(seed)
    seat_history: dict[int, set[tuple[int, int]]] = {}
    seats: dict[tuple[int, int, int], int] = {}
    for round_number in rounds:
        met_before = meet_before_round[round_number]
        tables = sorted(table for r, table in groups if r == round_number)
        for table in tables:
            members = groups[(round_number, table)]
            order = _order_table(members, company_of, met_before, rng)
            capacity = capacity_of[table]
            offset = _best_offset(order, table, capacity, seat_history, rng)
            n = len(order)
            for index, person in enumerate(order):
                seat = 1 + ((index * capacity // n + offset) % capacity)
                seats[(round_number, table, person)] = seat
                seat_history.setdefault(person, set()).add((table, seat))

    return tuple(
        replace(
            placement,
            seat=seats[(placement.round, placement.table, placement.person)],
        )
        for placement in placements
    )
