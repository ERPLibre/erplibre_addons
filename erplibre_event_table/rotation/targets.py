# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from typing import Sequence


def table_targets(
    capacities: Sequence[int], n: int, min_size: int = 2
) -> list[int]:
    """Return the target occupancy of each table, in the given order.

    The "equalise, never alone" rule of 01 §2. The result has the length
    of capacities; a closed table carries 0. Raises ValueError if n
    exceeds the sum of capacities: the caller has already seen the
    blocking diagnostic.
    """
    if n > sum(capacities):
        raise ValueError("n exceeds the sum of capacities")

    targets = [0] * len(capacities)
    open_indexes = list(range(len(capacities)))

    while True:
        # Largest lambda such that sum(min(c, lambda)) <= n, over the
        # tables still open.
        open_capacities = [capacities[i] for i in open_indexes]
        lam = 0
        for candidate in range(max(open_capacities, default=0) + 1):
            if sum(min(c, candidate) for c in open_capacities) <= n:
                lam = candidate
            else:
                break

        for index in open_indexes:
            targets[index] = min(capacities[index], lam)
        remaining = n - sum(targets[index] for index in open_indexes)

        # Distribute the rest, one person per table, to tables whose
        # capacity exceeds lambda, in increasing index order.
        for index in open_indexes:
            if remaining <= 0:
                break
            if capacities[index] > lam:
                targets[index] += 1
                remaining -= 1

        if not any(targets[index] < min_size for index in open_indexes):
            return targets

        # Close the highest-index open table if the remaining ones still
        # have enough capacity for n, and restart from lambda.
        candidate = open_indexes[-1]
        kept_indexes = open_indexes[:-1]
        if sum(capacities[index] for index in kept_indexes) < n:
            return targets

        targets[candidate] = 0
        open_indexes = kept_indexes
