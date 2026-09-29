# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests.common import new_test_user

from .common import EventTableCommon


class TestRegistrationDeskRights(EventTableCommon):
    """The registration desk group reads the five models and writes none."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A short budget keeps the generation fast; the room fits the twelve
        # participants with none to spare, so generation proves nothing here
        # beyond producing real rows to read and write against.
        cls.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "1"
        )
        cls.plan = cls.env["event.table.plan"].create(
            {"event_id": cls.event.id, "round_count": 3}
        )
        wizard = cls.env["event.table.configure.wizard"].create(
            {
                "plan_id": cls.plan.id,
                "mode": "replace",
                "table_count": 4,
                "seats_per_table": 3,
            }
        )
        wizard.action_apply()
        cls.env["event.table.participant"].create(
            [
                {"plan_id": cls.plan.id, "name": "Person %02d" % index}
                for index in range(1, 13)
            ]
        )
        cls.plan.combination_count = 1
        cls.plan.action_generate_combinations()
        cls.plan.combination_ids.action_choose()
        cls.table = cls.plan.table_ids[0]
        cls.participant = cls.plan.participant_ids[0]
        cls.combination = cls.plan.combination_ids[0]
        cls.assignment = cls.plan.assignment_ids[0]

    def test_desk_reads_the_plan(self):
        plan = self.plan.with_user(self.desk_user)
        self.assertEqual(plan.name, self.plan.name)

    def test_desk_reads_the_table(self):
        table = self.table.with_user(self.desk_user)
        self.assertEqual(table.number, self.table.number)

    def test_desk_reads_the_participant(self):
        participant = self.participant.with_user(self.desk_user)
        self.assertEqual(participant.name, self.participant.name)

    def test_desk_reads_the_combination(self):
        combination = self.combination.with_user(self.desk_user)
        self.assertEqual(combination.rank, self.combination.rank)

    def test_desk_reads_the_assignment(self):
        assignment = self.assignment.with_user(self.desk_user)
        self.assertEqual(assignment.round_number, self.assignment.round_number)

    def test_desk_cannot_write_the_plan(self):
        plan = self.plan.with_user(self.desk_user)
        with self.assertRaises(AccessError):
            plan.write({"name": "Renamed"})

    def test_desk_cannot_write_the_table(self):
        # position_h stays editable once a plan is chosen (it moves nothing
        # structural), so this write reaches the ACL check instead of being
        # stopped earlier by the draft-only guard.
        table = self.table.with_user(self.desk_user)
        with self.assertRaises(AccessError):
            table.write({"position_h": 10.0})

    def test_desk_cannot_write_the_participant(self):
        participant = self.participant.with_user(self.desk_user)
        with self.assertRaises(AccessError):
            participant.write({"excluded": True})

    def test_desk_cannot_write_the_combination(self):
        combination = self.combination.with_user(self.desk_user)
        with self.assertRaises(AccessError):
            combination.write({"is_adjusted": True})

    def test_desk_cannot_write_the_assignment(self):
        # The model's own guard raises UserError for every caller lacking
        # this context flag, admin included: without it, the write below
        # would prove nothing about the desk group's ACL. The flag only
        # opens the path to that ACL check, it does not grant it.
        assignment = self.assignment.with_user(self.desk_user).with_context(
            event_table_assignment_write=True
        )
        with self.assertRaises(AccessError):
            assignment.write({"seat_number": 1})


class TestMultiCompanyIsolation(EventTableCommon):
    """A user of a second company sees none of the first company's rows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "1"
        )
        cls.company2 = cls.env["res.company"].create({"name": "Second Co"})
        cls.user_company1 = new_test_user(
            cls.env, login="user_company1", groups="event.group_event_user"
        )
        cls.user_company2 = new_test_user(
            cls.env,
            login="user_company2",
            groups="event.group_event_user",
            company_id=cls.company2.id,
            company_ids=[Command.set(cls.company2.ids)],
        )
        cls.plan = cls.env["event.table.plan"].create(
            {"event_id": cls.event.id, "round_count": 1}
        )
        wizard = cls.env["event.table.configure.wizard"].create(
            {
                "plan_id": cls.plan.id,
                "mode": "replace",
                "table_count": 2,
                "seats_per_table": 3,
            }
        )
        wizard.action_apply()
        cls.env["event.table.participant"].create(
            [
                {"plan_id": cls.plan.id, "name": "Person %02d" % index}
                for index in range(1, 5)
            ]
        )
        cls.plan.combination_count = 1
        cls.plan.action_generate_combinations()
        cls.plan.combination_ids.action_choose()
        cls.table = cls.plan.table_ids[0]
        cls.participant = cls.plan.participant_ids[0]
        cls.combination = cls.plan.combination_ids[0]
        cls.assignment = cls.plan.assignment_ids[0]

    def _assert_visible_to_owner_only(self, model_name, record):
        # The owner's company must see the row before the other company's
        # absence of it means anything: an empty search on an empty table
        # would pass whether the rule works or not.
        model = self.env[model_name]
        self.assertEqual(
            model.with_user(self.user_company1).search(
                [("id", "=", record.id)]
            ),
            record,
        )
        self.assertFalse(
            model.with_user(self.user_company2).search(
                [("id", "=", record.id)]
            )
        )

    def test_the_plan_is_isolated_by_company(self):
        self._assert_visible_to_owner_only("event.table.plan", self.plan)

    def test_the_table_is_isolated_by_company(self):
        self._assert_visible_to_owner_only("event.table", self.table)

    def test_the_participant_is_isolated_by_company(self):
        self._assert_visible_to_owner_only(
            "event.table.participant", self.participant
        )

    def test_the_combination_is_isolated_by_company(self):
        self._assert_visible_to_owner_only(
            "event.table.combination", self.combination
        )

    def test_the_assignment_is_isolated_by_company(self):
        self._assert_visible_to_owner_only(
            "event.table.assignment", self.assignment
        )
