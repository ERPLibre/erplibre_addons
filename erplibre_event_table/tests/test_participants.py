# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import EventTableCommon


class TestParticipants(EventTableCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_booker = cls.env["res.partner"].create(
            {"name": "Ada Brightwood", "email": "ada@example.com"}
        )
        cls.partner_guest = cls.env["res.partner"].create(
            {"name": "Milo Fernsby", "email": "milo@example.com"}
        )
        cls.reg_attended = cls.env["event.registration"].create(
            {
                "event_id": cls.event.id,
                "partner_id": cls.partner_booker.id,
                "name": "Ada Brightwood",
                "email": "ada@example.com",
                "state": "done",
            }
        )
        cls.reg_same_booker = cls.env["event.registration"].create(
            {
                "event_id": cls.event.id,
                "partner_id": cls.partner_booker.id,
                "name": "Nils Brightwood",
                "email": "nils@example.com",
                "state": "done",
            }
        )
        cls.reg_registered = cls.env["event.registration"].create(
            {
                "event_id": cls.event.id,
                "name": "Rosa Kilmarnock",
                "email": "rosa@example.com",
                "state": "open",
            }
        )
        cls.reg_cancelled = cls.env["event.registration"].create(
            {
                "event_id": cls.event.id,
                "name": "Otto Vance",
                "email": "otto@example.com",
                "state": "cancel",
            }
        )

    def _run_wizard(self, scope, plan=None, partners=None):
        vals = {"event_id": self.event.id, "registration_scope": scope}
        if plan is not None:
            vals["plan_id"] = plan.id
        if partners is not None:
            vals["partner_ids"] = [(6, 0, partners.ids)]
        wizard = self.env["event.table.participant.wizard"].create(vals)
        action = wizard.action_add()
        return self.env["event.table.plan"].browse(action["res_id"])

    def test_attended_only_keeps_the_done_registrations(self):
        plan = self._run_wizard("attended")
        self.assertEqual(plan.participant_count, 1)
        self.assertEqual(
            plan.participant_ids.mapped("name"), ["Ada Brightwood"]
        )

    def test_registered_keeps_open_and_done_but_never_cancelled(self):
        plan = self._run_wizard("registered")
        self.assertEqual(
            sorted(plan.participant_ids.mapped("name")),
            ["Ada Brightwood", "Rosa Kilmarnock"],
        )

    def test_no_registration_adds_nobody_from_the_event(self):
        plan = self._run_wizard("none")
        self.assertEqual(plan.participant_count, 0)

    def test_two_registrations_of_one_booker_become_one_participant(self):
        plan = self._run_wizard("attended")
        self.assertEqual(plan.participant_count, 1)
        self.assertEqual(plan.participant_ids.partner_id, self.partner_booker)

    def test_a_second_pass_adds_no_duplicate(self):
        plan = self._run_wizard("registered")
        self.assertEqual(plan.participant_count, 2)
        self._run_wizard("registered", plan=plan)
        self.assertEqual(plan.participant_count, 2)

    def test_a_second_pass_widens_the_scope_without_duplicating(self):
        plan = self._run_wizard("attended")
        self.assertEqual(plan.participant_count, 1)
        self._run_wizard("registered", plan=plan)
        self.assertEqual(
            sorted(plan.participant_ids.mapped("name")),
            ["Ada Brightwood", "Rosa Kilmarnock"],
        )

    def test_the_merge_count_is_reported(self):
        plan = self._make_plan()
        created, merged = plan._add_registrations(
            self.reg_attended + self.reg_same_booker
        )
        self.assertEqual((created, merged), (1, 1))

    def test_a_known_registration_is_skipped_without_counting_as_merged(self):
        plan = self._make_plan()
        plan._add_registrations(self.reg_attended)
        created, merged = plan._add_registrations(self.reg_attended)
        self.assertEqual((created, merged), (0, 0))

    def test_contacts_are_added_next_to_the_registrations(self):
        plan = self._run_wizard("attended", partners=self.partner_guest)
        self.assertEqual(
            sorted(plan.participant_ids.mapped("name")),
            ["Ada Brightwood", "Milo Fernsby"],
        )

    def test_a_contact_already_in_the_plan_is_not_added_twice(self):
        plan = self._run_wizard("attended")
        added = plan._add_partners(self.partner_booker)
        self.assertEqual(added, 0)
        self.assertEqual(plan.participant_count, 1)

    def test_the_wizard_creates_a_plan_when_none_is_given(self):
        self.assertEqual(self.event.table_plan_count, 0)
        plan = self._run_wizard("attended")
        self.assertEqual(plan.event_id, self.event)
        self.assertEqual(plan.state, "draft")

    def test_the_wizard_reuses_the_latest_plan_by_default(self):
        plan = self._make_plan()
        wizard = self.env["event.table.participant.wizard"].create(
            {"event_id": self.event.id}
        )
        self.assertEqual(wizard.plan_id, plan)

    def test_a_registration_participant_says_where_it_comes_from(self):
        plan = self._run_wizard("attended")
        self.assertEqual(plan.participant_ids.source, "registration")

    def test_a_contact_participant_says_where_it_comes_from(self):
        plan = self._make_plan()
        participant = self._add_participant(
            plan, "Milo Fernsby", partner_id=self.partner_guest.id
        )
        self.assertEqual(participant.source, "partner")

    def test_a_typed_in_person_is_a_guest(self):
        plan = self._make_plan()
        self.assertEqual(
            self._add_participant(plan, "Walk-in Visitor").source, "guest"
        )

    def test_picking_a_contact_fills_the_name_and_the_email(self):
        plan = self._make_plan()
        participant = self.env["event.table.participant"].new(
            {"plan_id": plan.id}
        )
        participant.partner_id = self.partner_guest
        participant._onchange_partner_id()
        self.assertEqual(participant.name, "Milo Fernsby")
        self.assertEqual(participant.email, "milo@example.com")

    def test_a_company_contact_carries_its_commercial_name(self):
        company = self.env["res.partner"].create(
            {"name": "Northwind Tooling", "is_company": True}
        )
        employee = self.env["res.partner"].create(
            {"name": "Ines Calloway", "parent_id": company.id}
        )
        plan = self._make_plan()
        participant = self._add_participant(
            plan, "Ines Calloway", partner_id=employee.id
        )
        self.assertEqual(participant.company_label, "Northwind Tooling")
        self.assertEqual(participant.company_key, "northwind tooling")

    def test_a_free_text_company_falls_back_on_the_registration(self):
        registration = self.env["event.registration"].create(
            {
                "event_id": self.event.id,
                "name": "Pat Oyelaran",
                "email": "pat@example.com",
                "company_name": "Harbour Lights Ltd.",
                "state": "done",
            }
        )
        plan = self._make_plan()
        plan._add_registrations(registration)
        participant = plan.participant_ids.filtered(
            lambda p: p.name == "Pat Oyelaran"
        )
        self.assertEqual(participant.company_label, "Harbour Lights Ltd.")
        self.assertEqual(participant.company_key, "harbour lights ltd")

    def test_two_spellings_of_one_company_share_a_key(self):
        plan = self._make_plan()
        first = self._add_participant(
            plan, "Ines Calloway", company_label="Harbour-Lights, Ltd."
        )
        second = self._add_participant(
            plan, "Pat Oyelaran", company_label="  harbour   lights ltd  "
        )
        self.assertEqual(first.company_key, second.company_key)

    def test_clearing_the_company_exempts_the_person(self):
        plan = self._make_plan()
        participant = self._add_participant(
            plan, "Ines Calloway", company_label="Northwind Tooling"
        )
        participant.company_label = False
        self.assertFalse(participant.company_key)

    def test_an_excluded_person_is_not_counted_against_the_seats(self):
        plan = self._make_plan()
        self._configure_tables(plan, 2, 4)
        for index in range(8):
            self._add_participant(plan, "Guest %s" % index)
        self.assertEqual(plan.participant_count, 8)
        self.assertEqual(plan.seat_balance, 0)
        plan.participant_ids[0].excluded = True
        self.assertEqual(plan.participant_count, 7)
        self.assertEqual(plan.seat_balance, 1)
        self.assertEqual(len(plan._included_participants()), 7)

    def test_a_plan_short_of_seats_says_how_many_are_missing(self):
        plan = self._make_plan()
        self._configure_tables(plan, 1, 4)
        for index in range(6):
            self._add_participant(plan, "Guest %s" % index)
        self.assertEqual(plan.seat_balance, -2)
        self.assertEqual(
            plan.capacity_message,
            "Participants: 6. Seats: 4. Missing: 2.",
        )

    @mute_logger("odoo.sql_db")
    def test_a_contact_takes_part_once_per_plan(self):
        plan = self._make_plan()
        self._add_participant(
            plan, "Milo Fernsby", partner_id=self.partner_guest.id
        )
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self._add_participant(
                plan, "Milo Fernsby", partner_id=self.partner_guest.id
            )

    def test_several_guests_have_no_contact_and_do_not_collide(self):
        plan = self._make_plan()
        self._add_participant(plan, "Walk-in One")
        self._add_participant(plan, "Walk-in Two")
        self.assertEqual(plan.participant_count, 2)
