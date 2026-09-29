# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Hold reserved places inside a plan the generator wrote in full.

Generation runs on the WHOLE problem - every table at its declared
capacity, every bound proven, every diagnostic computed - and this pass
edits the result afterwards. Shrinking a table's capacity to model a
reserved place is not an option the library offers: Table carries ONE
capacity for ALL rounds, while a pin occupies a seat in ONE round, so a
reduced capacity would refuse rounds that are in fact free, and
validate_problem would raise on a capacity falling below 2.

A pin is honoured by rearranging the occupants of one round among the
tables they already fill. The number of people seated at each (round,
table) is left exactly as the generator wrote it, which is what makes
the pass free of consequences: no table can overflow, assign_seats still
accepts the placements, and the plan stays inside the domain where the
library's lower bound is proven. Only WHO sits where changes, never HOW
MANY.

A pin reserves a TABLE and nothing finer. rotation/seats.py derives
every seat of a table from a single offset, so a requested seat number
is a wish this pass cannot grant; it carries the departing occupant's
seat number over instead, which leaves each table's set of seat numbers
untouched.
"""
import time
from collections import Counter
from dataclasses import replace
from math import comb
from typing import NamedTuple, Sequence

from ..rotation import Options, Placement, Problem


class PinRequest(NamedTuple):
    """One reserved place, in the terms the placements are written in."""

    round: int  # 1..R
    person: int  # Person.key
    table: int  # Table.number


class PinReconcileError(Exception):
    """A pin no rearrangement of a round can hold.

    Carries a code and its parameters rather than a sentence: the caller
    owns the wording and the translation, and is the only layer able to
    turn a person key back into a name. Codes:

    two_tables      the same person is pinned to two tables in a round
    round_absent    the pinned round is past the plan's last round
    person_absent   the pinned person is seated nowhere in that round
    table_absent    the pinned table seats nobody in that round
    table_full      more pins aim at a table than it seats in that round
    """

    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def _pair(p: int, q: int) -> tuple[int, int]:
    return (p, q) if p < q else (q, p)


def _index(placements: Sequence[Placement]):
    """Return (table_of, seat_of, members) read off the placements.

    table_of and seat_of are keyed (round, person); members maps (round,
    table) to the set of person keys seated there.
    """
    table_of: dict[tuple[int, int], int] = {}
    seat_of: dict[tuple[int, int], int] = {}
    members: dict[tuple[int, int], set[int]] = {}
    for placement in placements:
        key = (placement.round, placement.person)
        table_of[key] = placement.table
        seat_of[key] = placement.seat
        members.setdefault((placement.round, placement.table), set()).add(
            placement.person
        )
    return table_of, seat_of, members


def _pin_targets(pins: Sequence[PinRequest]) -> dict[tuple[int, int], int]:
    """Return the target table of each (round, person), or raise.

    A person named twice in one round with the same table is one wish
    stated twice and passes; two different tables is a contradiction no
    seating resolves.
    """
    targets: dict[tuple[int, int], int] = {}
    for pin in pins:
        key = (pin.round, pin.person)
        known = targets.get(key)
        if known is not None and known != pin.table:
            raise PinReconcileError(
                "two_tables", round=pin.round, person=pin.person
            )
        targets[key] = pin.table
    return targets


def reconcile(
    placements: Sequence[Placement], pins: Sequence[PinRequest]
) -> tuple[Placement, ...]:
    """Return placements where every pin sits at the table it names.

    Round by round, each table keeps the number of people the generator
    gave it and is refilled in three steps: the pins aimed at it take
    their places first, the occupants already there keep theirs while
    seats remain, and whoever is left over fills the seats still empty
    elsewhere. The rearrangement is a permutation of one round's people,
    so it is a product of transpositions and conserves the occupancy of
    every (round, table) exactly.

    Displacement is kept small rather than minimal: an occupant is moved
    only when their table has no seat left for them, and the choice
    among equals follows the person key so two runs give one answer.
    Raises PinReconcileError on a pin no rearrangement can hold; the
    placements are never returned half-honoured.
    """
    table_of, seat_of, members = _index(placements)
    targets = _pin_targets(pins)
    rounds = {placement.round for placement in placements}

    for (round_number, person), table in sorted(targets.items()):
        if round_number not in rounds:
            raise PinReconcileError(
                "round_absent", round=round_number, person=person
            )
        if (round_number, person) not in table_of:
            raise PinReconcileError(
                "person_absent", round=round_number, person=person
            )
        if (round_number, table) not in members:
            raise PinReconcileError(
                "table_absent",
                round=round_number,
                person=person,
                table=table,
            )

    load = Counter(
        (round_number, table)
        for (round_number, _person), table in targets.items()
    )
    for (round_number, table), count in sorted(load.items()):
        seats = len(members[(round_number, table)])
        if count > seats:
            raise PinReconcileError(
                "table_full",
                round=round_number,
                table=table,
                seats=seats,
                pinned=count,
            )

    original_seat = dict(seat_of)
    new_members: dict[tuple[int, int], set[int]] = {
        key: set() for key in members
    }
    for (round_number, person), table in targets.items():
        new_members[(round_number, table)].add(person)

    for round_number in sorted(rounds):
        tables = sorted(
            table for a_round, table in members if a_round == round_number
        )
        # A displaced person waits here until a table with a seat left
        # takes them. The two loops below run over sorted keys, so the
        # pool is filled and drained in one order whatever the set
        # iteration gives.
        pool: list[int] = []
        for table in tables:
            seats = len(members[(round_number, table)])
            staying = sorted(
                person
                for person in members[(round_number, table)]
                if (round_number, person) not in targets
            )
            room = seats - len(new_members[(round_number, table)])
            new_members[(round_number, table)].update(staying[:room])
            pool.extend(staying[room:])
        pool.sort()
        for table in tables:
            free = len(members[(round_number, table)]) - len(
                new_members[(round_number, table)]
            )
            if free:
                new_members[(round_number, table)].update(pool[:free])
                del pool[:free]

    for (round_number, table), occupants in new_members.items():
        seated_before = members[(round_number, table)]
        freed = sorted(
            original_seat[(round_number, person)]
            for person in seated_before - occupants
        )
        arriving = sorted(occupants - seated_before)
        for person, seat in zip(arriving, freed):
            seat_of[(round_number, person)] = seat
        for person in occupants:
            table_of[(round_number, person)] = table

    return tuple(
        replace(
            placement,
            table=table_of[(placement.round, placement.person)],
            seat=seat_of[(placement.round, placement.person)],
        )
        for placement in placements
    )


class _CostModel:
    """The cost of a plan, kept up to date across single swaps.

    Mirrors rotation/metrics.py evaluate(): cost is w1 * company pairs +
    w2 * sum C(m_pq, 2) + w3 * sum C(v_pt, 2), with a weight zeroed when
    its option is off. Swapping two people between two tables of one
    round touches only the pairs those two form with the occupants of
    the two tables, and only four visit counters, so the delta is read
    in time proportional to the two table sizes instead of rebuilding
    every counter.
    """

    def __init__(
        self,
        problem: Problem,
        placements: Sequence[Placement],
        options: Options,
    ):
        self.company_of = {
            person.key: person.company for person in problem.persons
        }
        self.table_of, self.seat_of, self.members = _index(placements)
        weights = options.weights
        self.w1 = weights[0] if options.separate_companies else 0
        self.w2 = weights[1] if options.avoid_repeat_neighbors else 0
        self.w3 = weights[2] if options.avoid_repeat_table else 0
        self.meet: dict[tuple[int, int], int] = {}
        self.visits: dict[tuple[int, int], int] = {}
        company_pairs = 0
        for (round_number, table), occupants in self.members.items():
            people = sorted(occupants)
            for index, p in enumerate(people):
                self.visits[(p, table)] = self.visits.get((p, table), 0) + 1
                for q in people[index + 1 :]:
                    pair = (p, q)
                    self.meet[pair] = self.meet.get(pair, 0) + 1
                    if self._same_company(p, q):
                        company_pairs += 1
        self.cost = (
            self.w1 * company_pairs
            + self.w2 * sum(comb(count, 2) for count in self.meet.values())
            + self.w3 * sum(comb(count, 2) for count in self.visits.values())
        )

    def _same_company(self, p: int, q: int) -> bool:
        company = self.company_of.get(p)
        return company is not None and company == self.company_of.get(q)

    def delta(self, round_number: int, a: int, b: int) -> int:
        """Return the cost change of swapping a and b in this round.

        The two must sit at different tables, which keeps every counter
        this reads from being touched twice: the pairs a forms at its
        own table and the pairs it forms at b's are disjoint sets, and
        the four visit counters name two distinct people at two
        distinct tables.
        """
        t = self.table_of[(round_number, a)]
        u = self.table_of[(round_number, b)]
        left = self.members[(round_number, t)] - {a}
        right = self.members[(round_number, u)] - {b}

        company = 0
        for q in right:
            company += self._same_company(a, q)
        for q in left:
            company += self._same_company(b, q)
        for q in left:
            company -= self._same_company(a, q)
        for q in right:
            company -= self._same_company(b, q)

        pairs = 0
        for q in left:
            pairs -= self.meet[_pair(a, q)] - 1
            pairs += self.meet.get(_pair(b, q), 0)
        for q in right:
            pairs -= self.meet[_pair(b, q)] - 1
            pairs += self.meet.get(_pair(a, q), 0)

        visits = 0
        visits -= self.visits[(a, t)] - 1
        visits += self.visits.get((a, u), 0)
        visits -= self.visits[(b, u)] - 1
        visits += self.visits.get((b, t), 0)

        return self.w1 * company + self.w2 * pairs + self.w3 * visits

    def apply(self, round_number: int, a: int, b: int, delta: int) -> None:
        """Move a to b's table and b to a's, seat numbers included.

        The two seat numbers travel with the tables, so each table keeps
        the set of seat numbers assign_seats gave it.
        """
        t = self.table_of[(round_number, a)]
        u = self.table_of[(round_number, b)]
        left = self.members[(round_number, t)] - {a}
        right = self.members[(round_number, u)] - {b}

        for q in left:
            self.meet[_pair(a, q)] -= 1
            pair = _pair(b, q)
            self.meet[pair] = self.meet.get(pair, 0) + 1
        for q in right:
            self.meet[_pair(b, q)] -= 1
            pair = _pair(a, q)
            self.meet[pair] = self.meet.get(pair, 0) + 1

        self.visits[(a, t)] -= 1
        self.visits[(a, u)] = self.visits.get((a, u), 0) + 1
        self.visits[(b, u)] -= 1
        self.visits[(b, t)] = self.visits.get((b, t), 0) + 1

        self.members[(round_number, t)] = left | {b}
        self.members[(round_number, u)] = right | {a}
        self.table_of[(round_number, a)] = u
        self.table_of[(round_number, b)] = t
        seat_a = self.seat_of[(round_number, a)]
        self.seat_of[(round_number, a)] = self.seat_of[(round_number, b)]
        self.seat_of[(round_number, b)] = seat_a
        self.cost += delta

    def placements(
        self, placements: Sequence[Placement]
    ) -> tuple[Placement, ...]:
        return tuple(
            replace(
                placement,
                table=self.table_of[(placement.round, placement.person)],
                seat=self.seat_of[(placement.round, placement.person)],
            )
            for placement in placements
        )


def improve(
    problem: Problem,
    placements: Sequence[Placement],
    pins: Sequence[PinRequest],
    options: Options,
    *,
    time_budget: float = 2.0,
    max_passes: int = 3,
) -> tuple[Placement, ...]:
    """Win back part of what holding the pins costs, without moving one.

    A hill climb over one move: swap two NON-PINNED people sitting at
    different tables of the same round, and keep the swap only when the
    cost strictly falls. A pinned person is never a candidate, so every
    pin reconcile() honoured stays honoured, and a swap conserves the
    occupancy of both tables just as reconcile() does.

    Stops at the first of three: a full pass without a single accepted
    swap, max_passes passes, or time_budget seconds - the clock is read
    every 256 candidates rather than once per candidate. Returns the
    placements unchanged when no swap pays.
    """
    pinned = {(pin.round, pin.person) for pin in pins}
    movable: dict[int, list[int]] = {}
    for placement in placements:
        key = (placement.round, placement.person)
        if key not in pinned:
            movable.setdefault(placement.round, []).append(placement.person)
    for people in movable.values():
        people.sort()

    model = _CostModel(problem, placements, options)
    deadline = time.monotonic() + time_budget
    seen = 0
    for _pass in range(max_passes):
        improved = False
        for round_number in sorted(movable):
            people = movable[round_number]
            for index, a in enumerate(people):
                for b in people[index + 1 :]:
                    seen += 1
                    if not seen % 256 and time.monotonic() > deadline:
                        return model.placements(placements)
                    if (
                        model.table_of[(round_number, a)]
                        == model.table_of[(round_number, b)]
                    ):
                        continue
                    delta = model.delta(round_number, a, b)
                    if delta < 0:
                        model.apply(round_number, a, b, delta)
                        improved = True
        if not improved:
            break
    return model.placements(placements)
