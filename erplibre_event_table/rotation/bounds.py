# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Precheck, diagnostics and proven lower bounds. See 01 §4."""
import math
from math import comb

from .construct import design_applicable
from .galois import is_prime_power
from .model import Diagnostic
from .targets import table_targets


def pair_floor(q: int, m: int) -> int | float:
    """Return the minimal number of pairs when q people fill m tables.

    a, b = divmod(q, m); the result is b*C(a+1, 2) + (m-b)*C(a, 2), the
    pair count of the most even split of q over m tables. Without a
    table, zero people make no pair at all and any other population is
    impossible: the result is then math.inf, which propagates the
    impossibility through sums without a special case.
    """
    if m == 0:
        return 0 if q == 0 else math.inf
    a, b = divmod(q, m)
    return b * comb(a + 1, 2) + (m - b) * comb(a, 2)


def _company_sizes(persons):
    """Return (company, size) pairs, dense order.

    First occurrence when persons are sorted by key, matching the order
    RotationState numbers companies in - never a plain iteration over a
    set of strings, whose order would depend on PYTHONHASHSEED.
    """
    sizes: dict = {}
    order = []
    for person in sorted(persons, key=lambda person: person.key):
        if person.company is None:
            continue
        if person.company not in sizes:
            sizes[person.company] = 0
            order.append(person.company)
        sizes[person.company] += 1
    return [(company, sizes[company]) for company in order]


def _suggested_tables(m, n, rounds, capacities, min_table_size):
    """Return the smallest prime power table count that would fit the
    algebraic design, or None if none of [m+1, 49] works.

    Suggesting the table count already in place would help nobody, so
    the search starts one above it.
    """
    for q in range(m + 1, 50):
        if not is_prime_power(q):
            continue
        k = -(-n // q)  # ceil(n / q)
        if k > q or rounds > q:
            continue
        if not any(capacity >= k for capacity in capacities):
            continue
        if q * k - n == 0 or k - 1 >= min_table_size:
            return q
    return None


def _tau(n, m, w2, w3, avoid_repeat_table):
    """Return the per-table share of LBT for a table of n people.

    With C3 active, the n occupants split into k who change table across
    the round pair and n-k who do not; the minimum over k of their
    combined cost. Without C3, only the C2 term remains.
    """
    if not avoid_repeat_table:
        return w2 * pair_floor(n, m)
    return min(
        w3 * k + w2 * (comb(k, 2) + pair_floor(n - k, m - 1))
        for k in range(n + 1)
    )


def precheck(
    problem, options
) -> tuple[int, tuple[Diagnostic, ...], tuple[int, ...]]:
    """Return the weighted lower bound, the diagnostics and the targets.

    Blocking checks come first, in the only order that leaves all three
    reachable: too_few_participants, no_tables, capacity_short. On a
    blocking diagnostic, returns (0, (diagnostic,), ()) without touching
    table_targets, which would raise on the very case capacity_short
    reports.
    Otherwise computes the four proven bounds (LB1, LB2, LB3, LBT) of
    01 §4 and the non-blocking diagnostics they justify.
    """
    n = len(problem.persons)
    if n < 2:
        diagnostic = Diagnostic(
            "too_few_participants", "blocking", 0, {"persons": n}
        )
        return (0, (diagnostic,), ())

    if not problem.tables:
        diagnostic = Diagnostic("no_tables", "blocking", 0, {})
        return (0, (diagnostic,), ())

    capacities = [table.capacity for table in problem.tables]
    seats = sum(capacities)
    if n > seats:
        missing = n - seats
        diagnostic = Diagnostic(
            "capacity_short",
            "blocking",
            missing,
            {"persons": n, "seats": seats, "missing": missing},
        )
        return (0, (diagnostic,), ())

    targets = table_targets(capacities, n, options.min_table_size)
    open_targets = [target for target in targets if target > 0]
    m = len(open_targets)
    n_min = min(open_targets)
    n_max = max(open_targets)
    rounds = problem.rounds

    weights = options.weights
    w1 = weights[0] if options.separate_companies else 0
    w2 = weights[1] if options.avoid_repeat_neighbors else 0
    w3 = weights[2] if options.avoid_repeat_table else 0

    company_sizes = _company_sizes(problem.persons)
    lb1 = rounds * sum(pair_floor(size, m) for _, size in company_sizes)

    lb2 = max(
        0,
        rounds * sum(comb(target, 2) for target in open_targets) - comb(n, 2),
    )

    lb3 = max(
        n * max(0, rounds - m),
        m * max(0, rounds * n_min - n),
    )

    lbt = lbt_u = 0
    if options.avoid_repeat_neighbors:
        lbt = comb(rounds, 2) * sum(
            _tau(target, m, w2, w3, options.avoid_repeat_table)
            for target in open_targets
        )
        # Same sum with w1 = w2 = w3 = 1: the diagnostic below reports a
        # count of repeated meetings and returns, never a weighted cost.
        lbt_u = comb(rounds, 2) * sum(
            _tau(target, m, 1, 1, options.avoid_repeat_table)
            for target in open_targets
        )

    lower_bound = w1 * lb1 + max(w2 * lb2 + w3 * lb3, lbt)

    diagnostics = []
    if options.separate_companies:
        for company, size in company_sizes:
            floor = pair_floor(size, m)
            if floor > 0:
                diagnostics.append(
                    Diagnostic(
                        "company_exceeds_tables",
                        "unavoidable",
                        rounds * floor,
                        {"company": company, "members": size, "tables": m},
                    )
                )
    if options.avoid_repeat_neighbors and lb2 > 0:
        diagnostics.append(
            Diagnostic(
                "pairs_exhausted", "unavoidable", lb2, {"rounds": rounds}
            )
        )
    if options.avoid_repeat_neighbors and lbt > w2 * lb2 + w3 * lb3:
        diagnostics.append(
            Diagnostic("tables_too_full", "unavoidable", lbt_u, {})
        )
    if options.avoid_repeat_table and lb3 > 0:
        diagnostics.append(
            Diagnostic(
                "rounds_exceed_tables",
                "unavoidable",
                lb3,
                {"rounds": rounds, "tables": m},
            )
        )
    if (
        options.avoid_repeat_neighbors
        and (options.separate_companies or options.avoid_repeat_table)
        and (rounds - 1) * n_max / m >= 2
        and not design_applicable(problem, options, targets)
    ):
        suggested = _suggested_tables(
            m, n, rounds, capacities, options.min_table_size
        )
        if suggested is not None:
            diagnostics.append(
                Diagnostic(
                    "tight", "warning", 0, {"suggested_tables": suggested}
                )
            )

    return (lower_bound, tuple(diagnostics), tuple(targets))
