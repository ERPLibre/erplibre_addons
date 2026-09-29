# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Measuring a plan after the fact. See 01 S3 and S10."""
from math import comb
from typing import Sequence

from .model import Indicators, Options, Placement, Problem, TableConflict


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


def _meetings(
    groups: dict[tuple[int, int], list[int]],
) -> dict[tuple[int, int], int]:
    """Return m_pq: the rounds where p and q share a table, keyed p < q."""
    meet: dict[tuple[int, int], int] = {}
    for members in groups.values():
        for index, person in enumerate(members):
            for other in members[index + 1 :]:
                pair = (person, other) if person < other else (other, person)
                meet[pair] = meet.get(pair, 0) + 1
    return meet


def _visits(
    groups: dict[tuple[int, int], list[int]],
) -> dict[tuple[int, int], int]:
    """Return v_pt: the rounds person p spends at table t, keyed (p, t)."""
    visits: dict[tuple[int, int], int] = {}
    for (_, table), members in groups.items():
        for person in members:
            visits[(person, table)] = visits.get((person, table), 0) + 1
    return visits


def _check_known_tables(
    problem: Problem, groups: dict[tuple[int, int], list[int]]
) -> None:
    """Raise ValueError if a placement names a table absent from problem.

    A hand-edited plan is the intended caller here: failing loudly on a
    stale table number beats silently under-counting its conflicts.
    assign_seats() raises the same way, on top of its own capacity check.
    """
    known = {table.number for table in problem.tables}
    for _, table in groups:
        if table not in known:
            raise ValueError(
                f"placement names table {table}, not part of the problem"
            )


def _company_pairs(
    members: Sequence[int], company_of: dict[int, str | None]
) -> int:
    """Return C(a, 2) summed over the companies seated at one table."""
    counts: dict[str, int] = {}
    for person in members:
        company = company_of.get(person)
        if company is not None:
            counts[company] = counts.get(company, 0) + 1
    return sum(comb(count, 2) for count in counts.values())


def evaluate(
    problem: Problem, placements: Sequence[Placement], options: Options
) -> Indicators:
    """Recompute every indicator from the placements alone.

    Serves the generator as well as a manually adjusted plan, which may
    have broken the even occupancy: nothing is read but the placements
    and the problem's persons. Every indicator is computed whatever the
    options; only cost follows the effective weights. met_distinct_avg
    and met_distinct_min are computed over the persons who appear in
    placements, not problem.persons, so met_distinct_min reads as the
    minimum among those actually seated, silently excluding a
    registered participant nobody seated.
    """
    company_of = {person.key: person.company for person in problem.persons}
    groups = _table_groups(placements)
    _check_known_tables(problem, groups)
    meet = _meetings(groups)
    visits = _visits(groups)

    weights = options.weights
    w1 = weights[0] if options.separate_companies else 0
    w2 = weights[1] if options.avoid_repeat_neighbors else 0
    w3 = weights[2] if options.avoid_repeat_table else 0

    company_pairs = sum(
        _company_pairs(members, company_of) for members in groups.values()
    )

    repeated_pairs = extra_meetings = max_pair_meetings = k2 = 0
    distinct_partners: dict[int, set[int]] = {}
    for (p, q), count in meet.items():
        distinct_partners.setdefault(p, set()).add(q)
        distinct_partners.setdefault(q, set()).add(p)
        if count >= 2:
            repeated_pairs += 1
        extra_meetings += max(0, count - 1)
        max_pair_meetings = max(max_pair_meetings, count)
        k2 += comb(count, 2)

    table_returns = k3 = 0
    for count in visits.values():
        table_returns += max(0, count - 1)
        k3 += comb(count, 2)

    persons = {person for members in groups.values() for person in members}
    met_counts = [len(distinct_partners.get(person, ())) for person in persons]
    met_distinct_avg = sum(met_counts) / len(met_counts) if met_counts else 0.0
    met_distinct_min = min(met_counts, default=0)

    return Indicators(
        company_pairs=company_pairs,
        repeated_pairs=repeated_pairs,
        extra_meetings=extra_meetings,
        max_pair_meetings=max_pair_meetings,
        table_returns=table_returns,
        met_distinct_avg=met_distinct_avg,
        met_distinct_min=met_distinct_min,
        cost=w1 * company_pairs + w2 * k2 + w3 * k3,
    )


def table_conflicts(
    problem: Problem, placements: Sequence[Placement], options: Options
) -> tuple[TableConflict, ...]:
    """Return one entry per (round, table) that carries a conflict.

    Sorted by (round, table number). Unlike evaluate, only the active
    options count here: a counter whose option is off is forced to 0,
    and a table whose three counters are all zero produces no entry.
    """
    company_of = {person.key: person.company for person in problem.persons}
    groups = _table_groups(placements)
    _check_known_tables(problem, groups)
    meet = _meetings(groups)
    visits = _visits(groups)

    conflicts = []
    for round_number, table in sorted(groups):
        members = groups[(round_number, table)]

        company_pairs = 0
        if options.separate_companies:
            company_pairs = _company_pairs(members, company_of)

        repeated_pairs = 0
        if options.avoid_repeat_neighbors:
            for index, person in enumerate(members):
                for other in members[index + 1 :]:
                    pair = (
                        (person, other) if person < other else (other, person)
                    )
                    if meet[pair] >= 2:
                        repeated_pairs += 1

        table_returns = 0
        if options.avoid_repeat_table:
            table_returns = sum(
                1 for person in members if visits[(person, table)] >= 2
            )

        if company_pairs or repeated_pairs or table_returns:
            conflicts.append(
                TableConflict(
                    round_number,
                    table,
                    company_pairs,
                    repeated_pairs,
                    table_returns,
                )
            )
    return tuple(conflicts)


def signature(placements: Sequence[Placement]) -> tuple:
    """Return a plan's social fingerprint, blind to labels and order.

    For each round, the sorted tuple of sorted person-key tuples per
    table (empty tables never appear, since they carry no placement);
    then the sorted tuple of these round signatures. Two plans that only
    differ by table numbering or round order come out equal.
    """
    by_round: dict[int, dict[int, list[int]]] = {}
    for placement in placements:
        by_round.setdefault(placement.round, {}).setdefault(
            placement.table, []
        ).append(placement.person)

    round_signatures = [
        tuple(sorted(tuple(sorted(members)) for members in tables.values()))
        for tables in by_round.values()
    ]
    return tuple(sorted(round_signatures))


def meetings(placements: Sequence[Placement]) -> dict[tuple[int, int], int]:
    """Return m_pq, the rounds each pair of persons shares a table.

    A public wrapper around the same computation evaluate() and
    distance() build internally, so a caller holding several plans -
    generate()'s diversity selection - can compute each plan's map once
    and reuse it, instead of rebuilding it from raw placements on every
    comparison.
    """
    return _meetings(_table_groups(placements))


def distance_from_meetings(
    meet_a: dict[tuple[int, int], int], meet_b: dict[tuple[int, int], int]
) -> float:
    """Return the weighted Jaccard distance between two meeting maps.

    1 - sum(min(m_pq, m'_pq)) / sum(max(m_pq, m'_pq)) over the union of
    the pairs either map carries. Two plans without a single pair in
    common - typically two plans of one round each with no repeat
    possible - have a zero denominator and are declared at distance 0.0
    rather than dividing by zero. Factored out of distance() so a caller
    that already holds both maps does not pay to rebuild them.
    """
    pairs = set(meet_a) | set(meet_b)
    numerator = sum(
        min(meet_a.get(pair, 0), meet_b.get(pair, 0)) for pair in pairs
    )
    denominator = sum(
        max(meet_a.get(pair, 0), meet_b.get(pair, 0)) for pair in pairs
    )
    if denominator == 0:
        return 0.0
    return 1 - numerator / denominator


def distance(a: Sequence[Placement], b: Sequence[Placement]) -> float:
    """Return the weighted Jaccard distance between two plans' meetings.

    See distance_from_meetings() for the formula; this wrapper builds
    each plan's meeting map from its placements first.
    """
    return distance_from_meetings(meetings(a), meetings(b))
