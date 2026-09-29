# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""The public entry point: K diverse, budget-bound combinations.

See 01 S8 and recherche/algorithme.md S7.
"""
import random
import time
from dataclasses import dataclass
from math import comb
from typing import Sequence

from .bounds import precheck
from .construct import build_design, build_greedy, design_applicable
from .metrics import distance_from_meetings, evaluate, meetings, signature
from .model import (
    Combination,
    Diagnostic,
    Generation,
    Options,
    Problem,
    validate_problem,
)
from .search import search
from .seats import assign_seats
from .state import RotationState

SEED_STRIDE = 1_000_003  # spaces candidate seeds well apart from one another


@dataclass(frozen=True, slots=True)
class Candidate:
    """One constructed-and-searched plan, before diversity selection.

    meetings and signature are computed once, right after the plan
    comes out of search, and read from here throughout diversity
    selection: both re-derive from placements from scratch, and the
    selection loop compares every pair of surviving candidates.
    """

    placements: tuple
    cost: int
    stopped_by: str
    rank: int  # k, the candidate's index; breaks ties at equal cost
    method: str  # "design" | "greedy"
    seed: int
    meetings: dict  # m_pq, for distance_from_meetings()
    signature: tuple  # this plan's canonical fingerprint


def _diversity_threshold(rounds: int, targets: Sequence[int], n: int) -> float:
    """Return d_min, the minimum accepted distance between two plans.

    rho estimates the share of all possible pairs a plan is forced to
    repeat, capped at 1 when the tables are too small to avoid it.
    d_rand is the expected distance between two independent random
    plans of that density; d_min keeps only a quarter of it, since
    plans that already exhaust every pair offer no real choice and
    d_rand itself tends to 0 as rho tends to 1.
    """
    rho = min(1.0, rounds * sum(comb(t, 2) for t in targets) / comb(n, 2))
    d_rand = 2 * (1 - rho) / (2 - rho)
    return 0.25 * d_rand


def select_diverse(
    candidates: Sequence[Candidate], count: int, d_min: float
) -> tuple[list[Candidate], tuple[bool, ...]]:
    """Return up to count candidates, ordered by acceptance, with flags.

    Candidates are examined by increasing (cost, rank). An exact
    signature duplicate of an already chosen candidate is rejected
    outright; otherwise a candidate is accepted once its distance to
    every already chosen plan reaches d_min. When this first pass
    leaves the quota short, it is completed with the best remaining
    candidates that are not exact duplicates, flagged True in the
    parallel close_variant tuple. Reads each candidate's meetings and
    signature straight from the Candidate, never rederiving them from
    placements.
    """
    ordered = sorted(
        candidates, key=lambda candidate: (candidate.cost, candidate.rank)
    )
    chosen: list[Candidate] = []
    chosen_signatures: set = set()
    close_variant: list[bool] = []

    for candidate in ordered:
        if len(chosen) >= count:
            break
        if candidate.signature in chosen_signatures:
            continue
        if (
            chosen
            and min(
                distance_from_meetings(candidate.meetings, other.meetings)
                for other in chosen
            )
            < d_min
        ):
            continue
        chosen.append(candidate)
        chosen_signatures.add(candidate.signature)
        close_variant.append(False)

    if len(chosen) < count:
        for candidate in ordered:
            if len(chosen) >= count:
                break
            if candidate.signature in chosen_signatures:
                continue
            chosen.append(candidate)
            chosen_signatures.add(candidate.signature)
            close_variant.append(True)

    return chosen, tuple(close_variant)


def diverse_enough(
    candidates: Sequence[Candidate], count: int, d_min: float
) -> bool:
    """Return whether select_diverse already fills the quota outright.

    True only when count candidates are accepted without falling back
    to a close variant; this is the early-exit condition of the
    generation loop.
    """
    chosen, close_variant = select_diverse(candidates, count, d_min)
    return len(chosen) == count and not any(close_variant)


def fewer_if_needed(
    chosen: Sequence[Candidate], count: int
) -> tuple[Diagnostic, ...]:
    """Return a fewer_combinations warning when chosen falls short of count."""
    if len(chosen) < count:
        return (
            Diagnostic(
                "fewer_combinations",
                "warning",
                0,
                {"count": len(chosen), "requested": count},
            ),
        )
    return ()


def to_combination(
    problem: Problem,
    options: Options,
    candidate: Candidate,
    lower_bound: int,
    distance_to_first: float,
    close_variant: bool,
) -> Combination:
    """Turn a Candidate into the public Combination.

    Seats are assigned, with the candidate's own seed, before the
    indicators are recomputed: assign_seats changes none of the three
    counters, but the placements it returns must carry the seats. Seats
    scramble the (round, table, person) order state.placements() built,
    since a table is re-ordered around its seats, so the result is
    re-sorted by (round, table, seat, person) - the invariant 01 §1
    promises callers, and the one state.placements() only holds by
    accident, since every seat is 0 before this pass runs.
    """
    placements = candidate.placements
    if options.assign_seats:
        placements = assign_seats(
            problem, placements, options, seed=candidate.seed
        )
        placements = tuple(
            sorted(
                placements,
                key=lambda placement: (
                    placement.round,
                    placement.table,
                    placement.seat,
                    placement.person,
                ),
            )
        )
    indicators = evaluate(problem, placements, options)
    return Combination(
        placements=placements,
        indicators=indicators,
        lower_bound=lower_bound,
        # search stops as soon as best <= lower_bound: a proven lower
        # bound is never overshot, so equality is the only way to reach
        # it, but <= is what the stopping condition itself checks and
        # keeps the pair (stopped_by, proven_optimal) consistent.
        proven_optimal=indicators.cost <= lower_bound,
        method=candidate.method,
        stopped_by=candidate.stopped_by,
        seed=candidate.seed,
        distance_to_first=distance_to_first,
        close_variant=close_variant,
    )


def generate(
    problem: Problem,
    options: Options,
    *,
    count: int = 3,
    seed: int = 0,
    time_budget: float | None = 5.0,
    max_iterations: int | None = None,
) -> Generation:
    """Return up to count comparable combinations, under a total budget.

    validate_problem is called first: a programming error (duplicate
    keys, an out-of-range round count) must never reach precheck, which
    only ever reports user-facing situations. On a blocking diagnostic,
    returns Generation((), diagnostics, ()) without building a single
    candidate. Otherwise builds and searches up to 3*count candidates,
    seeded random.Random(seed*SEED_STRIDE + k), from build_design when
    design_applicable holds, else build_greedy - design_applicable
    depends only on problem, options and targets, so it is decided once,
    not on every one of up to 3*count passes. time_budget is the budget
    of the WHOLE generation, never of one candidate: the deadline of the
    k-th candidate is start + time_budget*min(1, (k+1)/count), so the
    last one never passes start + time_budget. This is what keeps the
    request under Odoo's own time limits whatever count is asked for.
    The loop stops early once count distinct, far-enough-apart
    candidates are accepted, or once the budget is spent with at least
    one candidate built.
    """
    validate_problem(problem, options)
    lower_bound, diagnostics, targets = precheck(problem, options)
    if any(diagnostic.severity == "blocking" for diagnostic in diagnostics):
        return Generation((), diagnostics, ())

    n = len(problem.persons)
    if max_iterations is None:
        max_iterations = 2000 * n * problem.rounds
    d_min = _diversity_threshold(problem.rounds, targets, n)
    use_design = design_applicable(problem, options, targets)

    start = time.monotonic()
    candidates: list[Candidate] = []
    for k in range(3 * count):
        seed_k = seed * SEED_STRIDE + k
        rng = random.Random(seed_k)
        state = RotationState(problem, options, targets)
        if use_design:
            build_design(state, rng)
            method = "design"
        else:
            build_greedy(state, rng)
            method = "greedy"

        deadline = None
        if time_budget is not None:
            deadline = start + time_budget * min(1, (k + 1) / count)
        cost, stopped_by = search(
            state, lower_bound, rng, max_iterations, deadline
        )
        placements = state.placements()
        candidates.append(
            Candidate(
                placements=placements,
                cost=cost,
                stopped_by=stopped_by,
                rank=k,
                method=method,
                seed=seed_k,
                meetings=meetings(placements),
                signature=signature(placements),
            )
        )

        if diverse_enough(candidates, count, d_min):
            break
        if time_budget is not None and time.monotonic() >= start + time_budget:
            break

    chosen, close_variant = select_diverse(candidates, count, d_min)
    diagnostics = diagnostics + fewer_if_needed(chosen, count)

    combinations = []
    for index, candidate in enumerate(chosen):
        distance_to_first = 0.0
        if index > 0:
            distance_to_first = distance_from_meetings(
                candidate.meetings, chosen[0].meetings
            )
        combinations.append(
            to_combination(
                problem,
                options,
                candidate,
                lower_bound,
                distance_to_first,
                close_variant[index],
            )
        )

    all_targets = tuple(
        (table.number, target)
        for table, target in zip(problem.tables, targets)
    )
    return Generation(all_targets, diagnostics, tuple(combinations))
