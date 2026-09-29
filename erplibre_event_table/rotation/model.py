# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Person:
    key: int  # Odoo participant id ; sets the processing order
    company: str | None = None  # normalized company key


@dataclass(frozen=True, slots=True)
class Table:
    number: int  # displayed number, >= 1
    capacity: int  # >= 2


@dataclass(frozen=True, slots=True)
class Placement:
    round: int  # 1..R
    person: int  # Person.key
    table: int  # Table.number
    seat: int = 0  # 1..capacity, 0 = no seat assigned


@dataclass(frozen=True, slots=True)
class Options:
    separate_companies: bool = True  # C1
    avoid_repeat_neighbors: bool = True  # C2
    avoid_repeat_table: bool = False  # C3
    assign_seats: bool = False  # C4
    weights: tuple[int, int, int] = (100, 10, 1)
    min_table_size: int = 2


@dataclass(frozen=True, slots=True)
class Problem:
    persons: tuple[Person, ...]
    tables: tuple[Table, ...]
    rounds: int  # 1..50


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str  # see 01 §4
    severity: str  # "blocking" | "unavoidable" | "warning"
    minimum: int = 0
    params: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Indicators:
    company_pairs: int
    repeated_pairs: int
    extra_meetings: int  # sum of max(0, m_pq - 1) : the unit proven bounds use
    max_pair_meetings: int
    table_returns: int
    met_distinct_avg: float
    met_distinct_min: int
    cost: int


@dataclass(frozen=True, slots=True)
class TableConflict:
    round: int
    table: int
    company_pairs: int
    repeated_pairs: int
    table_returns: int


@dataclass(frozen=True, slots=True)
class Combination:
    placements: tuple[Placement, ...]
    indicators: Indicators
    lower_bound: int
    proven_optimal: bool
    method: str  # "design" | "greedy"
    stopped_by: str  # "lower_bound" | "no_conflict" | "iterations" | "time"
    seed: int
    distance_to_first: float
    close_variant: bool


@dataclass(frozen=True, slots=True)
class Generation:
    targets: tuple[tuple[int, int], ...]  # (table number, target occupancy)
    diagnostics: tuple[Diagnostic, ...]
    combinations: tuple[Combination, ...]


def validate_problem(problem: Problem, options: Options | None = None) -> None:
    """Raise ValueError on a programming error of the caller.

    A user-facing situation - not enough seats, no table - passes through
    here silently: it is reported by precheck as a diagnostic instead.
    Checks: duplicate person keys, duplicate table numbers, a table number
    below 1, a capacity below 2, rounds outside 1..50. The 50-round limit
    comes from bytearray counters, capped at 255. When options is given,
    also checks that no active option carries a zero weight -
    separate_companies with weights[0] == 0, avoid_repeat_neighbors with
    weights[1] == 0, avoid_repeat_table with weights[2] == 0 - since a
    zero weight is itself the mark of an inactive option (01 §3), and the
    contradictory pair is a programming error of the same class as the
    others this function catches.
    """
    person_keys = [person.key for person in problem.persons]
    if len(person_keys) != len(set(person_keys)):
        raise ValueError("duplicate person keys")

    table_numbers = [table.number for table in problem.tables]
    if len(table_numbers) != len(set(table_numbers)):
        raise ValueError("duplicate table numbers")

    for table in problem.tables:
        if table.number < 1:
            raise ValueError("table number below 1")
        if table.capacity < 2:
            raise ValueError("table capacity below 2")

    if not 1 <= problem.rounds <= 50:
        raise ValueError("rounds outside 1..50")

    if options is None:
        return
    if options.separate_companies and options.weights[0] == 0:
        raise ValueError("separate_companies is active with a zero weight")
    if options.avoid_repeat_neighbors and options.weights[1] == 0:
        raise ValueError("avoid_repeat_neighbors is active with a zero weight")
    if options.avoid_repeat_table and options.weights[2] == 0:
        raise ValueError("avoid_repeat_table is active with a zero weight")
