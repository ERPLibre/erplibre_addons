# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from collections import Counter

from odoo.addons.erplibre_event_table.models.pin_reconcile import (
    PinReconcileError,
    PinRequest,
    improve,
    reconcile,
)
from odoo.addons.erplibre_event_table.rotation import (
    Options,
    Person,
    Placement,
    Problem,
    Table,
    evaluate,
)
from odoo.exceptions import UserError
from odoo.tests.common import BaseCase

from .test_pins import PinCommon

# Eight people at four tables of two, one round. Persons 1 and 2 are
# colleagues and start apart, every other person is alone in a company,
# so the cost reads as 100 per colleague pair and nothing else: with a
# single round no pair meets twice and no table is returned to, which
# zeroes the other two terms whatever the weights.
_COLLEAGUES = Options(
    separate_companies=True,
    avoid_repeat_neighbors=True,
    avoid_repeat_table=False,
)
_PROBLEM = Problem(
    persons=tuple(
        Person(key=key, company="Shared" if key in (1, 2) else "Own%d" % key)
        for key in range(1, 9)
    ),
    tables=tuple(Table(number=number, capacity=2) for number in range(1, 5)),
    rounds=1,
)
_PLACEMENTS = tuple(
    Placement(round=1, person=person, table=table, seat=seat)
    for table, (left, right) in enumerate(
        [(1, 3), (2, 4), (5, 7), (6, 8)], start=1
    )
    for person, seat in ((left, 1), (right, 2))
)


def _occupancy(placements):
    """How many people each (round, table) seats - the conserved multiset."""
    return Counter((p.round, p.table) for p in placements)


def _seat_numbers(placements):
    """The seat numbers each (round, table) hands out, sorted."""
    seats = {}
    for placement in placements:
        seats.setdefault((placement.round, placement.table), []).append(
            placement.seat
        )
    return {key: sorted(value) for key, value in seats.items()}


def _table_of(placements):
    return {(p.round, p.person): p.table for p in placements}


class TestReconcile(BaseCase):
    """The rearrangement itself, on placements written by hand."""

    def test_a_pin_is_held(self):
        pins = [PinRequest(round=1, person=1, table=2)]
        held = reconcile(_PLACEMENTS, pins)
        self.assertEqual(_table_of(held)[(1, 1)], 2)

    def test_a_pin_on_the_current_table_changes_nothing(self):
        pins = [PinRequest(round=1, person=1, table=1)]
        self.assertEqual(reconcile(_PLACEMENTS, pins), _PLACEMENTS)

    def test_the_occupancy_multiset_is_identical(self):
        pins = [PinRequest(round=1, person=1, table=2)]
        held = reconcile(_PLACEMENTS, pins)
        self.assertEqual(_occupancy(held), _occupancy(_PLACEMENTS))
        self.assertEqual(sorted(_occupancy(held).values()), [2, 2, 2, 2])

    def test_every_table_keeps_its_seat_numbers(self):
        pins = [PinRequest(round=1, person=1, table=2)]
        held = reconcile(_PLACEMENTS, pins)
        self.assertEqual(_seat_numbers(held), _seat_numbers(_PLACEMENTS))

    def test_a_cycle_of_three_pins_is_held(self):
        # Each of the three is pinned to a table another one occupies, so
        # no single swap frees a seat: the rearrangement has to move the
        # whole cycle at once.
        pins = [
            PinRequest(round=1, person=1, table=2),
            PinRequest(round=1, person=2, table=3),
            PinRequest(round=1, person=5, table=1),
        ]
        held = reconcile(_PLACEMENTS, pins)
        table_of = _table_of(held)
        for pin in pins:
            self.assertEqual(table_of[(pin.round, pin.person)], pin.table)
        self.assertEqual(_occupancy(held), _occupancy(_PLACEMENTS))

    def test_a_person_pinned_to_two_tables(self):
        with self.assertRaises(PinReconcileError) as caught:
            reconcile(
                _PLACEMENTS,
                [
                    PinRequest(round=1, person=1, table=2),
                    PinRequest(round=1, person=1, table=3),
                ],
            )
        self.assertEqual(caught.exception.code, "two_tables")

    def test_the_same_pin_stated_twice_passes(self):
        pins = [
            PinRequest(round=1, person=1, table=2),
            PinRequest(round=1, person=1, table=2),
        ]
        self.assertEqual(_table_of(reconcile(_PLACEMENTS, pins))[(1, 1)], 2)

    def test_a_pin_past_the_last_round(self):
        with self.assertRaises(PinReconcileError) as caught:
            reconcile(_PLACEMENTS, [PinRequest(round=2, person=1, table=2)])
        self.assertEqual(caught.exception.code, "round_absent")

    def test_a_pin_on_somebody_nobody_seats(self):
        with self.assertRaises(PinReconcileError) as caught:
            reconcile(_PLACEMENTS, [PinRequest(round=1, person=99, table=2)])
        self.assertEqual(caught.exception.code, "person_absent")

    def test_a_pin_on_a_table_seating_nobody(self):
        with self.assertRaises(PinReconcileError) as caught:
            reconcile(_PLACEMENTS, [PinRequest(round=1, person=1, table=9)])
        self.assertEqual(caught.exception.code, "table_absent")

    def test_more_pins_than_the_table_seats(self):
        with self.assertRaises(PinReconcileError) as caught:
            reconcile(
                _PLACEMENTS,
                [
                    PinRequest(round=1, person=person, table=2)
                    for person in (1, 3, 5)
                ],
            )
        self.assertEqual(caught.exception.code, "table_full")
        self.assertEqual(
            caught.exception.params,
            {"round": 1, "table": 2, "seats": 2, "pinned": 3},
        )

    def test_a_table_filled_entirely_with_pins(self):
        pins = [
            PinRequest(round=1, person=1, table=2),
            PinRequest(round=1, person=5, table=2),
        ]
        held = reconcile(_PLACEMENTS, pins)
        table_of = _table_of(held)
        self.assertEqual(table_of[(1, 1)], 2)
        self.assertEqual(table_of[(1, 5)], 2)
        self.assertEqual(_occupancy(held), _occupancy(_PLACEMENTS))


class TestPinSearch(BaseCase):
    """The pin-aware hill climb that follows the rearrangement."""

    def test_the_search_wins_back_what_holding_the_pin_costs(self):
        # The free plan seats no colleague pair. Pinning person 1 to
        # table 2 puts them next to their colleague and costs 100;
        # swapping person 2 with a stranger wins it all back. A search
        # that accepted no move would leave the cost at 100 and fail
        # here.
        pins = [PinRequest(round=1, person=1, table=2)]
        free = evaluate(_PROBLEM, _PLACEMENTS, _COLLEAGUES).cost
        held = reconcile(_PLACEMENTS, pins)
        repaired = evaluate(_PROBLEM, held, _COLLEAGUES).cost
        searched = improve(_PROBLEM, held, pins, _COLLEAGUES)
        after = evaluate(_PROBLEM, searched, _COLLEAGUES).cost
        self.assertEqual(free, 0)
        self.assertEqual(repaired, 100)
        self.assertLess(after, repaired)

    def test_the_search_never_moves_a_pinned_person(self):
        pins = [PinRequest(round=1, person=1, table=2)]
        held = reconcile(_PLACEMENTS, pins)
        searched = improve(_PROBLEM, held, pins, _COLLEAGUES)
        self.assertEqual(_table_of(searched)[(1, 1)], 2)

    def test_the_search_conserves_the_occupancy_multiset(self):
        pins = [PinRequest(round=1, person=1, table=2)]
        held = reconcile(_PLACEMENTS, pins)
        searched = improve(_PROBLEM, held, pins, _COLLEAGUES)
        self.assertEqual(_occupancy(searched), _occupancy(_PLACEMENTS))
        self.assertEqual(_seat_numbers(searched), _seat_numbers(_PLACEMENTS))

    def test_the_search_leaves_a_plan_it_cannot_better_alone(self):
        searched = improve(_PROBLEM, _PLACEMENTS, [], _COLLEAGUES)
        self.assertEqual(evaluate(_PROBLEM, searched, _COLLEAGUES).cost, 0)


class TestGenerationHoldsPins(PinCommon):
    """Generation on a plan that carries reserved places."""

    def _generated_tables(self, plan, combination=None):
        """Map (round, participant id) to the table number they sit at."""
        combination = combination or plan.combination_ids[0]
        return {
            (placement.round, placement.person): placement.table
            for placement in plan._combination_placements(combination)
        }

    def test_a_pin_is_held_by_every_combination(self):
        plan = self._pin_plan()
        plan.combination_count = 3
        person = plan.participant_ids[0]
        table = plan.table_ids[2]
        self._pin(plan, person, table, round_number=2)
        plan.action_generate_combinations()
        self.assertEqual(len(plan.combination_ids), 3)
        for combination in plan.combination_ids:
            seated = self._generated_tables(plan, combination)
            self.assertEqual(seated[(2, person.id)], table.number)

    def test_holding_a_pin_seats_everybody_exactly_once(self):
        plan = self._pin_plan()
        self._pin(plan, plan.participant_ids[0], plan.table_ids[2])
        plan.action_generate_combinations()
        placements = plan._combination_placements(plan.combination_ids[0])
        self.assertEqual(len(placements), 12 * 3)
        self.assertEqual(
            len({(p.round, p.person) for p in placements}), 12 * 3
        )
        # Four tables of three seats, three rounds: every table is full
        # in every round, before as after the pin is held.
        self.assertEqual(
            sorted(Counter((p.round, p.table) for p in placements).values()),
            [3] * 12,
        )

    def test_a_held_combination_remembers_it(self):
        plan = self._pin_plan()
        self._pin(plan, plan.participant_ids[0], plan.table_ids[2])
        plan.action_generate_combinations()
        self.assertTrue(all(plan.combination_ids.mapped("is_pin_constrained")))

    def test_a_plan_without_a_pin_generates_as_before(self):
        plan = self._pin_plan()
        self.assertFalse(plan.action_generate_combinations())
        self.assertEqual(plan.state, "proposed")
        self.assertEqual(len(plan.combination_ids), 1)
        self.assertFalse(
            any(plan.combination_ids.mapped("is_pin_constrained"))
        )

    def test_starting_over_ignores_the_pins_and_keeps_them(self):
        plan = self._pin_plan()
        person = plan.participant_ids[0]
        # Every table but this one, for every round: whatever the
        # generator draws, holding the pins would have to move somebody.
        for round_number in (1, 2, 3):
            self._pin(
                plan, person, plan.table_ids[2], round_number=round_number
            )
        plan.action_generate_combinations(honour_pins=False)
        self.assertEqual(len(plan.pin_ids), 3)
        self.assertFalse(
            any(plan.combination_ids.mapped("is_pin_constrained"))
        )

    def test_a_pinned_table_that_closed_is_named(self):
        # Ten tables of three for twelve people: the "never alone" rule
        # of rotation/targets.py opens six of them and closes the rest,
        # starting from the highest number, so table 10 seats nobody in
        # any round whatever the draw.
        plan = self._pin_plan()
        self._configure_tables(plan, 10, 3)
        closed = plan.table_ids.filtered(lambda table: table.number == 10)
        self._pin(plan, plan.participant_ids[0], closed)
        with self.assertRaises(UserError) as caught:
            plan.action_generate_combinations()
        self.assertIn("Table 10 seats nobody", str(caught.exception))

    def test_more_pins_than_a_table_seats_is_named(self):
        plan = self._pin_plan()
        table = plan.table_ids[0]
        for index in range(4):
            self._pin(plan, plan.participant_ids[index], table)
        with self.assertRaises(UserError) as caught:
            plan.action_generate_combinations()
        self.assertIn("4 people are pinned to table 1", str(caught.exception))

    def test_a_pin_past_the_last_round_is_named(self):
        plan = self._pin_plan()
        self._pin(
            plan, plan.participant_ids[0], plan.table_ids[0], round_number=9
        )
        with self.assertRaises(UserError) as caught:
            plan.action_generate_combinations()
        self.assertIn("round 9", str(caught.exception))

    def test_a_pin_on_an_excluded_participant_is_named(self):
        plan = self._pin_plan()
        person = plan.participant_ids[0]
        self._pin(plan, person, plan.table_ids[0])
        person.excluded = True
        with self.assertRaises(UserError) as caught:
            plan.action_generate_combinations()
        self.assertIn("seated nowhere", str(caught.exception))


class TestGenerationQuestion(PinCommon):
    """The question the button asks, and the demo path that must not see it."""

    def test_a_plan_without_a_pin_generates_without_asking(self):
        plan = self._pin_plan()
        self.assertFalse(plan.action_request_generation())
        self.assertEqual(plan.state, "proposed")

    def test_a_plan_with_a_pin_asks_first(self):
        plan = self._pin_plan()
        self._pin(plan, plan.participant_ids[0], plan.table_ids[2])
        action = plan.action_request_generation()
        self.assertEqual(
            action["res_model"], "event.table.pin.generate.wizard"
        )
        self.assertEqual(action["context"]["default_plan_id"], plan.id)
        self.assertEqual(plan.state, "draft")

    def test_the_wizard_holds_the_pins(self):
        plan = self._pin_plan()
        person = plan.participant_ids[0]
        table = plan.table_ids[2]
        self._pin(plan, person, table)
        wizard = self.env["event.table.pin.generate.wizard"].create(
            {"plan_id": plan.id, "mode": "keep"}
        )
        self.assertEqual(wizard.pin_count, 1)
        self.assertEqual(wizard.pin_summary, "One place is reserved by hand.")
        wizard.action_apply()
        seated = {
            (p.round, p.person): p.table
            for p in plan._combination_placements(plan.combination_ids[0])
        }
        self.assertEqual(seated[(1, person.id)], table.number)
        self.assertTrue(plan.combination_ids[0].is_pin_constrained)

    def test_the_wizard_starts_over(self):
        plan = self._pin_plan()
        self._pin(plan, plan.participant_ids[0], plan.table_ids[2])
        wizard = self.env["event.table.pin.generate.wizard"].create(
            {"plan_id": plan.id, "mode": "reset"}
        )
        wizard.action_apply()
        self.assertEqual(plan.state, "proposed")
        self.assertEqual(len(plan.pin_ids), 1)
        self.assertFalse(plan.combination_ids[0].is_pin_constrained)

    def test_the_wizard_counts_more_than_one_place(self):
        plan = self._pin_plan()
        self._pin(plan, plan.participant_ids[0], plan.table_ids[2])
        self._pin(plan, plan.participant_ids[1], plan.table_ids[2])
        wizard = self.env["event.table.pin.generate.wizard"].create(
            {"plan_id": plan.id}
        )
        self.assertEqual(wizard.pin_count, 2)
        self.assertEqual(wizard.pin_summary, "2 places are reserved by hand.")

    def test_the_demo_path_never_meets_the_question(self):
        # data/event_table_demo.xml reaches generation through
        # _demo_seat_first_combination, whose return value is discarded:
        # an action returned here would skip the generation and break
        # the install of the module.
        plan = self._pin_plan()
        self.assertFalse(plan._demo_seat_first_combination())
        self.assertEqual(plan.state, "chosen")
