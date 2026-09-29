# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.tests.common import TransactionCase


class TestAfterChoice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "1"
        )
        cls.event = cls.env["event.event"].create(
            {
                "name": "Rotating Tables After Choice",
                "date_begin": "2026-03-02 09:00:00",
                "date_end": "2026-03-02 17:00:00",
            }
        )

    def setUp(self):
        super().setUp()
        self.plan = self.env["event.table.plan"].create(
            {
                "name": "Plan",
                "event_id": self.event.id,
                "round_count": 3,
                "combination_count": 1,
            }
        )
        self.env["event.table"].create(
            [
                {"plan_id": self.plan.id, "number": number, "seat_count": 4}
                for number in range(1, 5)
            ]
        )
        self.env["event.table.participant"].create(
            [
                {"plan_id": self.plan.id, "name": "Person %02d" % index}
                for index in range(1, 13)
            ]
        )
        self.plan.action_generate_combinations()
        self.plan.combination_ids.filtered(
            lambda c: c.rank == 1
        ).action_choose()

    def _add(self, name):
        return self.env["event.table.participant"].create(
            {"plan_id": self.plan.id, "name": name}
        )

    def test_a_latecomer_waits_without_a_seat(self):
        latecomer = self._add("Person 13")
        self.assertEqual(self.plan.participant_count, 13)
        self.assertEqual(self.plan.unseated_count, 1)
        self.assertEqual(
            self.plan.sync_message,
            "The plan no longer matches its participants. Not seated: 1.",
        )
        self.assertFalse(
            self.plan.assignment_ids.filtered(
                lambda a: a.participant_id == latecomer
            )
        )
        self.assertIn(
            "Person 13 added to the plan.", self.plan.message_ids[0].body
        )
        self.assertTrue(self.plan.chosen_combination_id.is_adjusted)

    def test_seating_the_latecomer_creates_one_line(self):
        latecomer = self._add("Person 13")
        table = self.plan.table_ids.filtered(lambda t: t.number == 1)
        self.plan.action_move_participant(2, latecomer.id, table.id)
        line = self.plan.assignment_ids.filtered(
            lambda a: a.participant_id == latecomer
        )
        self.assertEqual(len(line), 1)
        self.assertEqual(line.round_number, 2)
        self.assertEqual(line.table_id, table)
        self.assertEqual(line.combination_id, self.plan.chosen_combination_id)
        self.assertEqual(len(self.plan.assignment_ids), 37)
        self.assertEqual(self.plan.unseated_count, 0)
        self.assertFalse(self.plan.sync_message)

    def test_excluding_someone_empties_every_round(self):
        victim = self.plan.participant_ids.filtered(
            lambda p: p.name == "Person 01"
        )
        victim.excluded = True
        self.assertFalse(
            self.plan.assignment_ids.filtered(
                lambda a: a.participant_id == victim
            )
        )
        self.assertEqual(len(self.plan.assignment_ids), 33)
        self.assertEqual(self.plan.participant_count, 11)
        self.assertEqual(self.plan.unseated_count, 0)
        self.assertIn(
            "Person 01 excluded: removed from every round.",
            self.plan.message_ids[0].body,
        )

    def test_including_someone_again_leaves_them_unseated(self):
        victim = self.plan.participant_ids.filtered(
            lambda p: p.name == "Person 01"
        )
        victim.excluded = True
        victim.excluded = False
        self.assertFalse(
            self.plan.assignment_ids.filtered(
                lambda a: a.participant_id == victim
            )
        )
        self.assertEqual(self.plan.participant_count, 12)
        self.assertEqual(self.plan.unseated_count, 1)
        self.assertEqual(
            self.plan.sync_message,
            "The plan no longer matches its participants. Not seated: 1.",
        )
        self.assertIn(
            "Person 01 is included again and waits to be seated.",
            self.plan.message_ids[0].body,
        )

    def test_removing_someone_drops_their_lines(self):
        victim = self.plan.participant_ids.filtered(
            lambda p: p.name == "Person 01"
        )
        victim.unlink()
        self.assertEqual(len(self.plan.assignment_ids), 33)
        self.assertEqual(self.plan.participant_count, 11)
        self.assertIn(
            "Person 01 removed from the plan.",
            self.plan.message_ids[0].body,
        )
