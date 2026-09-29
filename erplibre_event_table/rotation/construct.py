# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Starting plans: the algebraic design over GF(q), and a greedy one.

See 01 §6 and recherche/algorithme.md S7.
"""
import random
from typing import Sequence

from .galois import gf_tables, is_prime_power
from .model import Options, Problem
from .state import RotationState


def design_applicable(
    problem: Problem, options: Options, targets: Sequence[int]
) -> bool:
    """Return whether the algebraic design over GF(T) fits this plan.

    Requires every table open, their count T a prime power at most 49,
    k = ceil(N/T) at most T, every table able to seat k, R at most T,
    and either an exact fit (T*k == N) or at least min_table_size seats
    left on a partial last column.

    C3's own restriction is not on k but on the draw of mu in
    build_design: at k == T, GF(T) has no room left for k distinct
    nonzero values, so one column is forced to mu = 0 and keeps its
    table every round. The design stays the best known start even then
    - it is what reaches the proven bound of 80 on a 64-person,
    eight-table-of-eight, five-round instance under C2 and C3.
    """
    if any(target == 0 for target in targets):
        return False
    table_count = len(problem.tables)
    if not is_prime_power(table_count) or table_count > 49:
        return False
    n = len(problem.persons)
    k = -(-n // table_count)  # ceil(n / table_count)
    if k > table_count or problem.rounds > table_count:
        return False
    if min(table.capacity for table in problem.tables) < k:
        return False
    return table_count * k - n == 0 or k - 1 >= options.min_table_size


def _company_groups(state: RotationState) -> list[list[int]]:
    """Return each company's members, one list per company.

    In the dense company order RotationState.__init__ assigned - first
    occurrence among persons sorted by key - which this walk over
    range(state.N) reproduces exactly, so company c's list always
    exists by the time c is first seen.
    """
    groups: list[list[int]] = []
    for p in range(state.N):
        c = state.comp[p]
        if c < 0:
            continue
        if c == len(groups):
            groups.append([])
        groups[c].append(p)
    return groups


def _companies_by_size_desc(
    state: RotationState, rng: random.Random
) -> list[list[int]]:
    """Return company groups, largest first, ties broken by rng.

    Shuffles first, then stably sorts by decreasing size: groups tied
    on size keep the random order the shuffle gave them.
    """
    groups = _company_groups(state)
    rng.shuffle(groups)
    groups.sort(key=lambda group: -len(group))
    return groups


def build_design(state: RotationState, rng: random.Random) -> None:
    """Seat everyone with the algebraic design over GF(T).

    Precondition: design_applicable held for the Problem and Options
    state was built from - not re-checked here, since state alone does
    not carry the table capacities that check also needs.

    Persons fill k = ceil(N/T) columns of up to T rows: companies are
    packed in largest first, one company per column when the column has
    room, otherwise split into the "loose" list for the local search
    that follows to repair; persons without a company fill what is
    left. The T*k - N cells with nobody in them are free seats, placed
    at the head of the last column. Row i of column j sits, in round r,
    at table label[add[i][mul[rho[r]][mu[j]]]] in GF(T): distinct rho
    and distinct mu keep any two columns from crossing twice (C2), a
    column never crosses itself (C1), and mu != 0 forbids a repeat
    table (C3). At k == T there is no room left for k distinct nonzero
    mu, so one column draws mu = 0 and keeps its table every round.
    """
    add, mul = gf_tables(state.T)
    k = -(-state.N // state.T)  # ceil(N / T)
    ghosts = state.T * k - state.N
    room = [state.T] * k
    room[-1] -= ghosts

    columns: list[list[int]] = [[] for _ in range(k)]
    loose: list[int] = []
    for group in _companies_by_size_desc(state, rng):
        j = max(range(k), key=lambda j: room[j] - len(columns[j]))
        if room[j] - len(columns[j]) >= len(group):
            columns[j].extend(group)
        else:
            loose = group + loose  # split company: local search repairs it

    solitary = [p for p in range(state.N) if state.comp[p] < 0]
    rng.shuffle(solitary)
    for p in loose + solitary:
        j = max(range(k), key=lambda j: room[j] - len(columns[j]))
        columns[j].append(p)
    for column in columns:
        rng.shuffle(column)

    if state.w3 and k <= state.T - 1:
        mu = rng.sample(range(1, state.T), k)
    else:
        mu = rng.sample(range(state.T), k)
    rho = rng.sample(range(state.T), state.R)
    label = list(range(state.T))
    rng.shuffle(label)

    for r in range(state.R):
        for j, column in enumerate(columns):
            off = ghosts if j == k - 1 else 0
            for i, p in enumerate(column):
                table = label[add[i + off][mul[rho[r]][mu[j]]]]
                state.place(r, p, table)


def _company_size_by_person(state: RotationState) -> list[int]:
    """Return each person's company size, 0 for a person without one."""
    sizes: dict[int, int] = {}
    for c in state.comp:
        if c >= 0:
            sizes[c] = sizes.get(c, 0) + 1
    return [sizes.get(c, 0) if c >= 0 else 0 for c in state.comp]


def build_greedy(
    state: RotationState, rng: random.Random, sample: int = 16
) -> None:
    """Fill every round with a randomised greedy construction.

    Used when the algebraic design does not apply. Each round shuffles
    the seating order, then stably sorts it by decreasing company size
    - ties keep the shuffle's order, which is what makes the result
    depend only on RotationState's dense indices, never on the order
    Problem.persons arrived in. Each person then joins whichever of at
    most `sample` candidate tables with room left minimises
    w3*visits[p][t] plus, summed over its current occupants,
    w2*meetings already shared plus w1 for a colleague; ties keep the
    first table in the drawn order.
    """
    company_size = _company_size_by_person(state)
    for r in range(state.R):
        slots = list(state.targets)
        order = list(range(state.N))
        rng.shuffle(order)
        order.sort(key=lambda p: -company_size[p])
        for p in order:
            candidates = [t for t in range(state.T) if slots[t] > 0]
            if len(candidates) > sample:
                candidates = rng.sample(candidates, sample)
            else:
                rng.shuffle(candidates)
            table = min(
                candidates,
                key=lambda t: state.w3 * state.visits[p][t]
                + sum(
                    state.w2 * state.meet[p][x]
                    + (
                        state.w1
                        if state.comp[p] >= 0
                        and state.comp[x] == state.comp[p]
                        else 0
                    )
                    for x in state.members[r][t]
                ),
            )
            state.place(r, p, table)
            slots[table] -= 1
