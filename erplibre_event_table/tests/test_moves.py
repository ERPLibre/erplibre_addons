# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestMoves(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "1"
        )
        cls.event = cls.env["event.event"].create(
            {
                "name": "Rotating Tables Moves",
                "date_begin": "2026-03-02 09:00:00",
                "date_end": "2026-03-02 17:00:00",
            }
        )

    def _make_plan(self, seats=(3, 3, 3, 5), persons=12, rounds=3, **options):
        values = {
            "name": "Plan",
            "event_id": self.event.id,
            "round_count": rounds,
        }
        values.update(options)
        plan = self.env["event.table.plan"].create(values)
        self.env["event.table"].create(
            [
                {"plan_id": plan.id, "number": number, "seat_count": count}
                for number, count in enumerate(seats, start=1)
            ]
        )
        self.env["event.table.participant"].create(
            [
                {"plan_id": plan.id, "name": "Person %02d" % index}
                for index in range(1, persons + 1)
            ]
        )
        return plan

    def _chosen_plan(self, **options):
        plan = self._make_plan(**options)
        plan.combination_count = 1
        plan.action_generate_combinations()
        plan.combination_ids.filtered(lambda c: c.rank == 1).action_choose()
        return plan

    def _table(self, plan, number):
        return plan.table_ids.filtered(lambda t: t.number == number)

    def _line(self, plan, round_number, participant):
        return plan.assignment_ids.filtered(
            lambda a: a.round_number == round_number
            and a.participant_id == participant
        )

    def _occupants(self, plan, round_number, table):
        return plan.assignment_ids.filtered(
            lambda a: a.round_number == round_number and a.table_id == table
        ).mapped("participant_id")

    def test_moving_someone_to_a_table_with_room(self):
        plan = self._chosen_plan()
        spare = self._table(plan, 4)
        mover = self._occupants(plan, 1, self._table(plan, 1))[0]
        before = len(self._occupants(plan, 1, spare))
        payload = plan.action_move_participant(1, mover.id, spare.id)
        self.assertEqual(self._line(plan, 1, mover).table_id, spare)
        self.assertEqual(len(self._occupants(plan, 1, spare)), before + 1)
        self.assertEqual(
            len(self._occupants(plan, 1, self._table(plan, 1))), 2
        )
        self.assertEqual(len(plan.assignment_ids), 36)
        self.assertEqual(payload["plan"]["id"], plan.id)
        self.assertIn(
            "Round 1: %s now sits at table 4." % mover.name,
            plan.message_ids[0].body,
        )

    def test_swapping_two_people_across_two_full_tables(self):
        plan = self._chosen_plan()
        first_table = self._table(plan, 1)
        second_table = self._table(plan, 2)
        first = self._occupants(plan, 1, first_table)[0]
        second = self._occupants(plan, 1, second_table)[0]
        self.assertEqual(len(self._occupants(plan, 1, second_table)), 3)
        plan.action_move_participant(
            1, first.id, second_table.id, swap_participant_id=second.id
        )
        self.assertEqual(self._line(plan, 1, first).table_id, second_table)
        self.assertEqual(self._line(plan, 1, second).table_id, first_table)
        self.assertEqual(len(self._occupants(plan, 1, first_table)), 3)
        self.assertEqual(len(self._occupants(plan, 1, second_table)), 3)
        self.assertEqual(len(plan.assignment_ids), 36)
        self.assertIn(
            "Round 1: %s and %s swapped places." % (first.name, second.name),
            plan.message_ids[0].body,
        )

    def test_swapping_exchanges_the_seat_numbers(self):
        plan = self._chosen_plan(assign_seats=True)
        first_table = self._table(plan, 1)
        second_table = self._table(plan, 2)
        first = self._occupants(plan, 1, first_table)[0]
        second = self._occupants(plan, 1, second_table)[0]
        first_seat = self._line(plan, 1, first).seat_number
        second_seat = self._line(plan, 1, second).seat_number
        plan.action_move_participant(
            1, first.id, second_table.id, swap_participant_id=second.id
        )
        self.assertEqual(self._line(plan, 1, first).seat_number, second_seat)
        self.assertEqual(self._line(plan, 1, second).seat_number, first_seat)
        self.assertEqual(self._line(plan, 1, first).table_id, second_table)
        self.assertEqual(self._line(plan, 1, second).table_id, first_table)

    def test_swapping_from_the_tray_seats_the_mover_and_frees_the_seat(self):
        plan = self._chosen_plan(assign_seats=True)
        table = self._table(plan, 1)
        mover = self._occupants(plan, 1, table)[0]
        plan.action_unseat_participant(1, mover.id)
        occupant = self._occupants(plan, 1, table)[0]
        occupant_seat = self._line(plan, 1, occupant).seat_number
        plan.action_move_participant(
            1, mover.id, table.id, swap_participant_id=occupant.id
        )
        self.assertFalse(self._line(plan, 1, occupant))
        self.assertEqual(self._line(plan, 1, mover).seat_number, occupant_seat)
        self.assertEqual(self._line(plan, 1, mover).table_id, table)
        self.assertIn(
            "Round 1: %s and %s swapped places." % (mover.name, occupant.name),
            plan.message_ids[0].body,
        )

    def test_a_full_table_without_a_swap_is_refused(self):
        plan = self._chosen_plan()
        second_table = self._table(plan, 2)
        mover = self._occupants(plan, 1, self._table(plan, 1))[0]
        with self.assertRaises(UserError) as caught:
            plan.action_move_participant(1, mover.id, second_table.id)
        self.assertEqual(
            str(caught.exception),
            "Table 2 is full in round 1. Drop the person onto someone to"
            " swap them.",
        )
        self.assertEqual(
            self._line(plan, 1, mover).table_id, self._table(plan, 1)
        )

    def test_a_seat_outside_the_table_is_refused(self):
        plan = self._chosen_plan(assign_seats=True)
        spare = self._table(plan, 4)
        mover = self._occupants(plan, 1, self._table(plan, 1))[0]
        with self.assertRaises(UserError) as caught:
            plan.action_move_participant(1, mover.id, spare.id, seat_number=9)
        self.assertEqual(str(caught.exception), "Table 4 has no seat 9.")

    def test_a_taken_seat_with_room_elsewhere_is_refused(self):
        plan = self._chosen_plan(assign_seats=True)
        spare = self._table(plan, 4)
        mover = self._occupants(plan, 1, self._table(plan, 1))[0]
        occupant = self._occupants(plan, 1, spare)[0]
        taken_seat = self._line(plan, 1, occupant).seat_number
        with self.assertRaises(UserError) as caught:
            plan.action_move_participant(
                1, mover.id, spare.id, seat_number=taken_seat
            )
        self.assertEqual(
            str(caught.exception),
            "Seat %s at table 4 is taken by %s. Drop the person onto them"
            " to swap." % (taken_seat, occupant.name),
        )
        self.assertEqual(
            self._line(plan, 1, mover).table_id, self._table(plan, 1)
        )

    def test_a_round_outside_the_plan_is_refused(self):
        plan = self._chosen_plan()
        mover = plan.participant_ids[0]
        with self.assertRaises(UserError) as caught:
            plan.action_move_participant(4, mover.id, self._table(plan, 4).id)
        self.assertEqual(
            str(caught.exception), "Round 4 does not exist in this plan."
        )

    def test_swapping_with_someone_seated_elsewhere_is_refused(self):
        plan = self._chosen_plan()
        first_table = self._table(plan, 1)
        second_table = self._table(plan, 2)
        mover = self._occupants(plan, 1, first_table)[0]
        elsewhere = self._occupants(plan, 1, self._table(plan, 3))[0]
        with self.assertRaises(UserError) as caught:
            plan.action_move_participant(
                1,
                mover.id,
                second_table.id,
                swap_participant_id=elsewhere.id,
            )
        self.assertEqual(
            str(caught.exception),
            "%s is not at table 2 in round 1." % elsewhere.name,
        )

    def test_moving_to_a_table_outside_the_plan_is_refused(self):
        plan = self._chosen_plan()
        other_plan = self._make_plan(seats=(4,), persons=4, rounds=1)
        foreign_table = other_plan.table_ids[0]
        mover = plan.participant_ids[0]
        with self.assertRaises(UserError) as caught:
            plan.action_move_participant(1, mover.id, foreign_table.id)
        self.assertEqual(
            str(caught.exception),
            "Table %s does not belong to this plan." % foreign_table.number,
        )

    def test_moving_an_unknown_participant_is_refused(self):
        plan = self._chosen_plan()
        unknown_id = max(plan.participant_ids.ids) + 1000
        with self.assertRaises(UserError) as caught:
            plan.action_move_participant(
                1, unknown_id, self._table(plan, 4).id
            )
        self.assertEqual(
            str(caught.exception),
            "%s does not take part in this plan." % unknown_id,
        )

    def test_moving_before_a_combination_reserves_a_seat(self):
        # The gesture is the one that moves somebody in a chosen plan;
        # with nothing assigned it writes a pin instead, which the
        # generation to come honours and outlives.
        plan = self._make_plan()
        participant = plan.participant_ids[0]
        table = self._table(plan, 4)
        plan.action_move_participant(1, participant.id, table.id)
        self.assertFalse(plan.assignment_ids)
        pin = plan.pin_ids
        self.assertEqual(len(pin), 1)
        self.assertEqual(pin.participant_id, participant)
        self.assertEqual(pin.table_id, table)
        self.assertEqual(pin.round_number, 1)
        # And the floor plan draws it, or the operator would fill a room
        # that stayed empty on screen.
        data = plan.get_floor_plan_data()
        self.assertTrue(data["plan"]["draws_pins"])
        seats = data["rounds"][0]["seats"]
        self.assertEqual(
            [s["participant_id"] for s in seats], [participant.id]
        )

    def test_unseating_before_a_combination_drops_the_reservation(self):
        plan = self._make_plan()
        participant = plan.participant_ids[0]
        plan.action_move_participant(
            1, participant.id, self._table(plan, 4).id
        )
        plan.action_unseat_participant(1, participant.id)
        self.assertFalse(plan.pin_ids)

    def test_swapping_two_reservations_trades_their_places(self):
        # A seat is claimed once per table and round at every moment,
        # not only once the swap is over: a two-write trade breaks that
        # halfway through, which is why the move parks a seat at zero.
        plan = self._make_plan(assign_seats=True)
        first, second = plan.participant_ids[0], plan.participant_ids[1]
        table_a, table_b = self._table(plan, 1), self._table(plan, 2)
        plan.action_move_participant(1, first.id, table_a.id, 2)
        plan.action_move_participant(1, second.id, table_b.id, 3)
        plan.action_move_participant(
            1, first.id, table_b.id, swap_participant_id=second.id
        )
        pin_first = plan.pin_ids.filtered(lambda p: p.participant_id == first)
        pin_second = plan.pin_ids.filtered(
            lambda p: p.participant_id == second
        )
        self.assertEqual(pin_first.table_id, table_b)
        self.assertEqual(pin_first.seat_number, 3)
        self.assertEqual(pin_second.table_id, table_a)
        self.assertEqual(pin_second.seat_number, 2)

    def test_a_full_table_refuses_one_more_reservation(self):
        plan = self._make_plan()
        table = self._table(plan, 1)
        for participant in plan.participant_ids[:3]:
            plan.action_move_participant(1, participant.id, table.id)
        with self.assertRaises(UserError) as caught:
            plan.action_move_participant(
                1, plan.participant_ids[3].id, table.id
            )
        self.assertIn("is full in round 1", str(caught.exception))

    def test_retaining_a_placement_seats_everyone_around_the_pins(self):
        # The button COMPLETES a partial placement rather than refusing
        # it: reserving one seat out of twelve is the ordinary case.
        plan = self._make_plan()
        pinned = plan.participant_ids[0]
        table = self._table(plan, 4)
        plan.action_move_participant(1, pinned.id, table.id)
        plan.action_retain_placement()
        self.assertEqual(plan.state, "chosen")
        self.assertTrue(plan.chosen_combination_id)
        self.assertEqual(plan.unseated_count, 0)
        seated = plan.assignment_ids.filtered(
            lambda a: a.round_number == 1 and a.participant_id == pinned
        )
        self.assertEqual(seated.table_id, table)

    def test_retaining_refuses_when_nobody_is_placed(self):
        plan = self._make_plan()
        with self.assertRaises(UserError) as caught:
            plan.action_retain_placement()
        self.assertIn("Nobody is placed yet.", str(caught.exception))

    def test_a_move_rewrites_the_placements_and_marks_the_combination(self):
        plan = self._chosen_plan()
        combination = plan.chosen_combination_id
        before = list(combination.placement_data)
        self.assertFalse(combination.is_adjusted)
        spare = self._table(plan, 4)
        mover = self._occupants(plan, 1, self._table(plan, 1))[0]
        plan.action_move_participant(1, mover.id, spare.id)
        self.assertTrue(combination.is_adjusted)
        self.assertNotEqual(combination.placement_data, before)
        self.assertEqual(len(combination.placement_data), 36)
        moved = [
            row
            for row in combination.placement_data
            if row[0] == 1 and row[1] == mover.id
        ]
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0][2], 4)

    def test_unseating_frees_the_round_and_posts_a_note(self):
        plan = self._chosen_plan()
        person = self._occupants(plan, 1, self._table(plan, 1))[0]
        payload = plan.action_unseat_participant(1, person.id)
        self.assertFalse(self._line(plan, 1, person))
        self.assertEqual(len(plan.assignment_ids), 35)
        self.assertIn(person.id, payload["rounds"][0]["unseated"])
        self.assertIn(
            "Round 1: %s no longer sits at a table." % person.name,
            plan.message_ids[0].body,
        )
        # Still seated in rounds 2 and 3, so the plan still matches its
        # participants: unseated_count counts people seated nowhere.
        self.assertEqual(plan.unseated_count, 0)
        self.assertFalse(plan.sync_message)
        self.assertTrue(plan.chosen_combination_id.is_adjusted)

    def test_unseating_an_unknown_participant_is_refused(self):
        plan = self._chosen_plan()
        unknown_id = max(plan.participant_ids.ids) + 1000
        with self.assertRaises(UserError) as caught:
            plan.action_unseat_participant(1, unknown_id)
        self.assertEqual(
            str(caught.exception),
            "%s does not take part in this plan." % unknown_id,
        )
