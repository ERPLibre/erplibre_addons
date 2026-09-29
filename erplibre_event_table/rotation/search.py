# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Iterated local search that turns a constructed plan into a good one.

See 01 S7 and recherche/algorithme.md S7.
"""
import random
import time

from .state import RotationState


def _conflict_pool(state: RotationState) -> list[tuple[int, int]]:
    """Return every (round, person) pair with a nonzero local cost."""
    return [
        (r, p)
        for r in range(state.R)
        for p in range(state.N)
        if state.local_cost(r, p)
    ]


def _same_size_open_tables(state: RotationState, r: int, t: int) -> list[int]:
    """Return the open tables of round r seating as many people as t."""
    size = len(state.members[r][t])
    return [
        u
        for u in state.open_tables
        if u != t and len(state.members[r][u]) == size
    ]


def _accept(delta: int, rng: random.Random) -> bool:
    """Return whether a move of this delta is accepted.

    An improving move is always taken; a move at equal cost is taken
    one time out of two, which is what lets the search cross plateaus.
    """
    return delta < 0 or (delta == 0 and rng.randrange(2))


def _try_label_move(
    state: RotationState,
    rng: random.Random,
    r: int,
    t: int,
    candidates: list[int],
) -> tuple[int, int] | None:
    """Try swapping t's number with the best of the given candidates.

    Called only once search() has already picked this branch over a
    person swap - w3 active, p returned to t at least once, a
    same-size open table exists, and the coin flip landed on it. Keeps
    the candidate with the best delta. Returns (delta, other table) on
    acceptance, else None: a rejection here ends the move for this
    iteration, it does not fall back to a person swap, matching the
    skeleton's if/else between the two moves.
    """
    delta, u = min((state.delta_label(r, t, v), v) for v in candidates)
    if not _accept(delta, rng):
        return None
    state.apply_label(r, t, u)
    return delta, u


def _try_swap_move(
    state: RotationState,
    rng: random.Random,
    r: int,
    p: int,
    t: int,
    sample: int,
) -> tuple[int, int] | None:
    """Try swapping p with the best of `sample` randomly drawn people.

    Only people seated at another table in round r are candidates.
    Returns (delta, the partner's table) on acceptance, else None.
    """
    best_delta = best_partner = None
    for _ in range(sample):
        q = rng.randrange(state.N)
        if state.table_of[r][q] == t:
            continue
        delta = state.delta_swap(r, p, q)
        if best_delta is None or delta < best_delta:
            best_delta, best_partner = delta, q
    if best_partner is None or not _accept(best_delta, rng):
        return None
    u = state.table_of[r][best_partner]
    state.apply_swap(r, p, best_partner)
    return best_delta, u


def _kick(
    state: RotationState, rng: random.Random, count: int, cost: int
) -> int:
    """Apply `count` random person swaps and return the resulting cost.

    Meant to shake the plan out of a stall. A draw that would swap a
    person with themselves - same table in that round - is skipped
    without retrying, since it never changes the cost anyway.
    """
    for _ in range(count):
        r = rng.randrange(state.R)
        a, b = rng.randrange(state.N), rng.randrange(state.N)
        if state.table_of[r][a] != state.table_of[r][b]:
            cost += state.delta_swap(r, a, b)
            state.apply_swap(r, a, b)
    return cost


def search(
    state: RotationState,
    lower_bound: int,
    rng: random.Random,
    max_iterations: int,
    deadline: float | None,
    sample: int = 12,
) -> tuple[int, str]:
    """Improve the plan in state through iterated local search.

    Returns (best cost, stop cause) and leaves in state the BEST
    solution encountered, never the last one. Stops at the first of
    four causes, checked in this order: "lower_bound" once the cost
    reaches the proven bound, "iterations" at the ceiling, "no_conflict"
    when the conflict pool is rebuilt and comes back empty, and
    "time" at the deadline - checked every 256 iterations so the
    search does not pay a clock call per iteration.

    Moves start from a (round, person) pair drawn from a pool of people
    still in conflict. The pool is lazy: a stale entry - its local cost
    has fallen to zero since it was added - is dropped when drawn
    rather than the whole pool being rebuilt, since rebuilding it on
    every draw turned a 40-person instance from a 0.29 s median into as
    much as 18.4 s. It is rebuilt only when empty or every `refresh`
    iterations. After `stall` iterations without improvement, the plan
    is brought back to the best solution seen and shaken with `kick`
    random swaps, and the pool is cleared.
    """
    cost = state.full_cost()
    best = cost
    best_snapshot = state.snapshot()
    stall = max(300, 5 * state.N)
    kick_size = max(3, state.N // 20)
    refresh = max(50, state.N)

    pool: list[tuple[int, int]] = []
    iteration = 0
    last_improvement = 0
    while True:
        if best <= lower_bound:
            stop = "lower_bound"
            break
        if iteration >= max_iterations:
            stop = "iterations"
            break
        iteration += 1

        if not pool or iteration % refresh == 0:
            pool = _conflict_pool(state)
            if not pool:
                stop = "no_conflict"
                break
        index = rng.randrange(len(pool))
        r, p = pool[index]
        if not state.local_cost(r, p):
            pool[index] = pool[-1]
            pool.pop()
            continue

        t = state.table_of[r][p]
        same_size = _same_size_open_tables(state, r, t)
        if (
            state.w3
            and state.visits[p][t] >= 2
            and same_size
            and rng.randrange(2)
        ):
            move = _try_label_move(state, rng, r, t, same_size)
        else:
            move = _try_swap_move(state, rng, r, p, t, sample)
        if move is not None:
            delta, u = move
            cost += delta
            pool.extend((r, x) for x in state.members[r][t])
            pool.extend((r, x) for x in state.members[r][u])
            if cost < best:
                best = cost
                best_snapshot = state.snapshot()
                last_improvement = iteration

        if iteration - last_improvement > stall:
            if cost > best:
                state.restore(best_snapshot)
                cost = best
            cost = _kick(state, rng, kick_size, cost)
            last_improvement = iteration
            pool = []

        if (
            deadline is not None
            and iteration % 256 == 0
            and time.monotonic() > deadline
        ):
            stop = "time"
            break

    if cost > best:
        state.restore(best_snapshot)
    return best, stop
