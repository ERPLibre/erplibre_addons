# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import EventTableCommon


class PinCommon(EventTableCommon):
    """A four-table plan with twelve people, ready to pin and generate."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 1 second is the floor _search_time_budget() accepts, and the
        # room fits the twelve exactly: generation proves nothing here
        # beyond moving the plan to its next state.
        cls.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "1"
        )

    def _pin_plan(self, persons=12, **options):
        plan = self._make_plan(round_count=3, combination_count=1, **options)
        self._configure_tables(plan, 4, 3)
        for index in range(1, persons + 1):
            self._add_participant(plan, "Person %02d" % index)
        return plan

    def _pin(self, plan, participant, table, round_number=1, seat=0):
        return self.env["event.table.pin"].create(
            {
                "plan_id": plan.id,
                "round_number": round_number,
                "table_id": table.id,
                "participant_id": participant.id,
                "seat_number": seat,
            }
        )


class TestPinConstraints(PinCommon):
    def test_a_participant_is_pinned_once_per_round(self):
        plan = self._pin_plan()
        person = plan.participant_ids[0]
        self._pin(plan, person, plan.table_ids[0], round_number=1)
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self._pin(plan, person, plan.table_ids[1], round_number=1)

    def test_the_same_participant_is_pinned_in_another_round(self):
        plan = self._pin_plan()
        person = plan.participant_ids[0]
        self._pin(plan, person, plan.table_ids[0], round_number=1)
        self._pin(plan, person, plan.table_ids[1], round_number=2)
        self.assertEqual(len(plan.pin_ids), 2)

    def test_two_people_cannot_request_one_seat(self):
        plan = self._pin_plan()
        table = plan.table_ids[0]
        self._pin(plan, plan.participant_ids[0], table, seat=2)
        with self.assertRaises(ValidationError) as caught:
            self._pin(plan, plan.participant_ids[1], table, seat=2)
        self.assertEqual(
            str(caught.exception),
            "A seat is requested once per table and round.",
        )

    def test_seat_zero_never_collides(self):
        plan = self._pin_plan()
        table = plan.table_ids[0]
        self._pin(plan, plan.participant_ids[0], table, seat=0)
        self._pin(plan, plan.participant_ids[1], table, seat=0)
        self.assertEqual(len(plan.pin_ids), 2)

    def test_one_seat_is_free_again_at_another_table(self):
        plan = self._pin_plan()
        self._pin(plan, plan.participant_ids[0], plan.table_ids[0], seat=2)
        self._pin(plan, plan.participant_ids[1], plan.table_ids[1], seat=2)
        self.assertEqual(len(plan.pin_ids), 2)

    def test_a_round_starts_at_one(self):
        plan = self._pin_plan()
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self._pin(
                    plan,
                    plan.participant_ids[0],
                    plan.table_ids[0],
                    round_number=0,
                )


class TestPinStates(PinCommon):
    def test_a_pin_is_created_on_a_draft_plan(self):
        plan = self._pin_plan()
        self.assertEqual(plan.state, "draft")
        pin = self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        self.assertEqual(pin.plan_id, plan)

    def test_a_pin_is_created_on_a_proposed_plan(self):
        plan = self._pin_plan()
        plan.action_generate_combinations()
        self.assertEqual(plan.state, "proposed")
        pin = self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        self.assertEqual(pin.plan_id, plan)

    def test_a_pin_is_refused_on_a_chosen_plan(self):
        plan = self._pin_plan()
        plan.action_generate_combinations()
        plan.combination_ids[0].action_choose()
        self.assertEqual(plan.state, "chosen")
        # A pin feeds the NEXT generation, so a chosen plan takes one:
        # reserving a seat disturbs no assignment standing now.
        pin = self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        self.assertEqual(pin.plan_id, plan)

    def test_a_locked_plan_refuses_a_new_pin(self):
        plan = self._pin_plan()
        plan.action_lock()
        with self.assertRaises(UserError) as caught:
            self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        self.assertEqual(
            str(caught.exception),
            "This plan is locked. Unlock it before pinning anyone.",
        )

    def test_a_locked_plan_freezes_the_pins_it_already_holds(self):
        plan = self._pin_plan()
        pin = self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        plan.action_lock()
        with self.assertRaises(UserError):
            pin.write({"seat_number": 1})
        with self.assertRaises(UserError):
            pin.unlink()

    def test_unlocking_reopens_pinning(self):
        plan = self._pin_plan()
        plan.action_lock()
        plan.action_unlock()
        pin = self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        self.assertEqual(pin.plan_id, plan)

    def test_a_pin_is_not_a_structural_change(self):
        # A pin feeds the NEXT generation, so it invalidates no
        # combination: the plan stays proposed and keeps the ones it has.
        plan = self._pin_plan()
        plan.action_generate_combinations()
        combinations = plan.combination_ids
        self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        self.assertEqual(plan.state, "proposed")
        self.assertEqual(plan.combination_ids, combinations)


class TestPinsOutliveGeneration(PinCommon):
    """The whole reason a pin is not an assignment."""

    def test_a_pin_outlives_generation_and_choice(self):
        plan = self._pin_plan()
        person = plan.participant_ids[0]
        table = plan.table_ids[0]
        pin = self._pin(plan, person, table, round_number=2, seat=1)
        plan.action_generate_combinations()
        plan.combination_ids[0].action_choose()
        self.assertTrue(pin.exists())
        self.assertEqual(plan.pin_ids, pin)
        self.assertEqual(pin.participant_id, person)
        self.assertEqual(pin.table_id, table)
        self.assertEqual(pin.round_number, 2)
        self.assertEqual(pin.seat_number, 1)

    def test_a_pin_outlives_a_generation_and_a_choice(self):
        # Outliving the run it constrained is the whole point of a pin:
        # the next generation must honour it again without being told.
        plan = self._pin_plan()
        pin = self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        plan.action_generate_combinations()
        plan.combination_ids[0].action_choose()
        self.assertEqual(plan.pin_ids, pin)
        plan.action_generate_combinations()
        self.assertEqual(plan.pin_ids, pin)

    def test_a_pin_is_no_assignment(self):
        # Eight readers walk assignment_ids as "who sits where". A pin
        # must never show up among them, or a table sheet would print it.
        plan = self._pin_plan()
        self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        plan.action_generate_combinations()
        plan.combination_ids[0].action_choose()
        self.assertEqual(len(plan.assignment_ids), 12 * 3)


class TestPinDuplication(PinCommon):
    def test_a_pin_follows_the_plan_to_its_copy(self):
        plan = self._pin_plan()
        person = plan.participant_ids[0]
        table = plan.table_ids[0]
        self._pin(plan, person, table, round_number=2, seat=3)
        duplicate = plan.copy()
        self.assertEqual(len(duplicate.pin_ids), 1)
        copied = duplicate.pin_ids
        # Re-aimed, not copied: the twin rows belong to the duplicate.
        self.assertEqual(copied.plan_id, duplicate)
        self.assertNotEqual(copied.table_id, table)
        self.assertEqual(copied.table_id.plan_id, duplicate)
        self.assertEqual(copied.table_id.number, table.number)
        self.assertNotEqual(copied.participant_id, person)
        self.assertEqual(copied.participant_id.plan_id, duplicate)
        self.assertEqual(copied.participant_id.name, person.name)
        self.assertEqual(copied.round_number, 2)
        self.assertEqual(copied.seat_number, 3)

    def test_the_original_keeps_its_own_pins(self):
        plan = self._pin_plan()
        pin = self._pin(plan, plan.participant_ids[0], plan.table_ids[0])
        plan.copy()
        self.assertEqual(plan.pin_ids, pin)

    def test_a_contact_is_matched_through_its_namesake(self):
        # Two contacts sharing a name are still told apart: a
        # participant carrying a contact is keyed on that contact, which
        # event.table.participant already keeps unique per plan.
        plan = self._pin_plan(persons=10)
        partners = self.env["res.partner"].create(
            [{"name": "Dominique Roy"}, {"name": "Dominique Roy"}]
        )
        pinned = self._add_participant(
            plan, "Dominique Roy", partner_id=partners[0].id
        )
        self._add_participant(plan, "Dominique Roy", partner_id=partners[1].id)
        self._pin(plan, pinned, plan.table_ids[0])
        duplicate = plan.copy()
        self.assertEqual(len(duplicate.pin_ids), 1)
        self.assertEqual(
            duplicate.pin_ids.participant_id.partner_id, partners[0]
        )

    def test_two_guests_of_one_name_leave_their_pin_behind(self):
        plan = self._pin_plan(persons=10)
        pinned = self._add_participant(plan, "Camille Tremblay")
        self._add_participant(plan, "Camille Tremblay")
        told_apart = plan.participant_ids.filtered(
            lambda person: person.name == "Person 01"
        )
        self._pin(plan, pinned, plan.table_ids[0])
        self._pin(plan, told_apart, plan.table_ids[1])
        duplicate = plan.copy()
        self.assertEqual(len(duplicate.pin_ids), 1)
        self.assertEqual(duplicate.pin_ids.participant_id.name, "Person 01")
        bodies = "".join(str(b) for b in duplicate.message_ids.mapped("body"))
        self.assertIn("Pins carried over: 1", bodies)

    def test_guests_of_one_name_keep_their_pin_when_told_apart(self):
        plan = self._pin_plan(persons=10)
        pinned = self._add_participant(
            plan, "Camille Tremblay", email="camille1@example.com"
        )
        self._add_participant(
            plan, "Camille Tremblay", email="camille2@example.com"
        )
        self._pin(plan, pinned, plan.table_ids[0])
        duplicate = plan.copy()
        self.assertEqual(len(duplicate.pin_ids), 1)
        self.assertEqual(
            duplicate.pin_ids.participant_id.email, "camille1@example.com"
        )


class TestPinRights(PinCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company2 = cls.env["res.company"].create({"name": "Second Co"})
        cls.user_company1 = new_test_user(
            cls.env, login="pin_user_company1", groups="event.group_event_user"
        )
        cls.user_company2 = new_test_user(
            cls.env,
            login="pin_user_company2",
            groups="event.group_event_user",
            company_id=cls.company2.id,
            company_ids=[(6, 0, cls.company2.ids)],
        )

    def _a_pin(self):
        plan = self._pin_plan()
        return self._pin(plan, plan.participant_ids[0], plan.table_ids[0])

    def test_desk_reads_the_pin(self):
        pin = self._a_pin()
        self.assertEqual(
            pin.with_user(self.desk_user).round_number, pin.round_number
        )

    def test_desk_cannot_write_the_pin(self):
        pin = self._a_pin()
        with self.assertRaises(AccessError):
            pin.with_user(self.desk_user).write({"seat_number": 1})

    def test_desk_cannot_create_a_pin(self):
        pin = self._a_pin()
        with self.assertRaises(AccessError):
            self.env["event.table.pin"].with_user(self.desk_user).create(
                {
                    "plan_id": pin.plan_id.id,
                    "round_number": 3,
                    "table_id": pin.table_id.id,
                    "participant_id": pin.plan_id.participant_ids[1].id,
                }
            )

    def test_desk_cannot_delete_the_pin(self):
        pin = self._a_pin()
        with self.assertRaises(AccessError):
            pin.with_user(self.desk_user).unlink()

    def test_an_event_user_writes_the_pin(self):
        pin = self._a_pin()
        pin.with_user(self.user_company1).write({"seat_number": 2})
        self.assertEqual(pin.seat_number, 2)

    def test_the_pin_is_isolated_by_company(self):
        pin = self._a_pin()
        model = self.env["event.table.pin"]
        # The owning company must see the row first: an empty search on
        # an empty table would pass whether the rule works or not.
        self.assertEqual(
            model.with_user(self.user_company1).search([("id", "=", pin.id)]),
            pin,
        )
        self.assertFalse(
            model.with_user(self.user_company2).search([("id", "=", pin.id)])
        )
