# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.addons.erplibre_event_table.rotation import Diagnostic
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestGeneration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A short budget keeps the suite fast; 1 second is the floor
        # _search_time_budget() accepts.
        cls.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "1"
        )
        cls.event = cls.env["event.event"].create(
            {
                "name": "Rotating Tables Test",
                "date_begin": "2026-03-02 09:00:00",
                "date_end": "2026-03-02 17:00:00",
            }
        )

    def _make_plan(self, seats=(3, 3, 3, 3), persons=12, rounds=3, **options):
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

    def test_missing_seats_block_the_generation(self):
        plan = self._make_plan(seats=(2,), persons=5, rounds=2)
        with self.assertRaises(UserError) as caught:
            plan.action_generate_combinations()
        message = str(caught.exception)
        self.assertIn("Participants: 5. Seats: 2. Missing: 3.", message)
        self.assertIn("Add tables or seats.", message)
        self.assertEqual(plan.state, "draft")
        self.assertFalse(plan.combination_ids)

    def test_generation_creates_combinations_with_indicators(self):
        plan = self._make_plan()
        plan.combination_count = 3
        plan.action_generate_combinations()
        self.assertEqual(plan.state, "proposed")
        self.assertEqual(len(plan.combination_ids), 3)
        self.assertEqual(
            sorted(plan.combination_ids.mapped("rank")), [1, 2, 3]
        )
        first = plan.combination_ids.filtered(lambda c: c.rank == 1)
        self.assertEqual(first.name, "Combination 1")
        # 12 people x 3 rounds, one row each, no seat number.
        self.assertEqual(len(first.placement_data), 36)
        self.assertEqual(
            len({(row[0], row[1]) for row in first.placement_data}), 36
        )
        self.assertEqual({row[3] for row in first.placement_data}, {0})
        self.assertEqual(
            sorted({row[2] for row in first.placement_data}), [1, 2, 3, 4]
        )
        # 4 tables of 3 over 3 rounds is an algebraic design: nobody meets
        # twice, and the search proves it.
        self.assertEqual(first.method, "design")
        self.assertEqual(first.cost, 0)
        self.assertEqual(first.lower_bound, 0)
        self.assertEqual(first.repeated_pair_count, 0)
        self.assertEqual(first.extra_meeting_count, 0)
        self.assertEqual(first.company_pair_count, 0)
        self.assertTrue(first.is_proven_optimal)
        self.assertFalse(first.is_adjusted)
        self.assertEqual(first.met_distinct_min, 6)
        self.assertTrue(plan.generation_seed)
        self.assertGreaterEqual(plan.generation_duration, 0.0)
        bodies = plan.message_ids.mapped("body")
        self.assertTrue(
            any("Combinations generated: 3" in body for body in bodies)
        )
        self.assertTrue(any("Seed:" in body for body in bodies))

    def test_generating_again_adds_to_the_combinations(self):
        # Runs accumulate, so an operator can compare what several
        # settings produce side by side. The ranks are renumbered over
        # the whole set, which is what makes them comparable at all.
        plan = self._make_plan()
        plan.combination_count = 3
        plan.action_generate_combinations()
        former_ids = plan.combination_ids.ids
        plan.action_generate_combinations()
        self.assertEqual(len(plan.combination_ids), 6)
        self.assertTrue(set(plan.combination_ids.ids) > set(former_ids))
        self.assertEqual(
            sorted(plan.combination_ids.mapped("rank")), list(range(1, 7))
        )

    def test_diagnostic_text_names_the_company_and_the_minimum(self):
        plan = self._make_plan(seats=(6, 6), persons=12, rounds=2)
        plan.participant_ids[:4].write({"company_label": "Northwind Tools"})
        diagnostic = Diagnostic(
            code="company_exceeds_tables",
            severity="unavoidable",
            minimum=8,
            params={
                "company": "northwind tools",
                "members": 4,
                "tables": 2,
            },
        )
        self.assertEqual(
            plan._diagnostic_message_text(diagnostic),
            "Northwind Tools has 4 participants for 2 open tables."
            " Colleague pairs that cannot be avoided: 8.",
        )

    def test_diagnostic_text_follows_the_table_return_option(self):
        plan = self._make_plan(avoid_repeat_table=True)
        diagnostic = Diagnostic(
            code="tables_too_full", severity="unavoidable", minimum=12
        )
        self.assertEqual(
            plan._diagnostic_message_text(diagnostic),
            "Tables too full for this number of tables. Repeated meetings"
            " or table returns that cannot be avoided: 12.",
        )
        plan.avoid_repeat_table = False
        self.assertEqual(
            plan._diagnostic_message_text(diagnostic),
            "Tables too full for this number of tables. Repeated meetings"
            " that cannot be avoided: 12.",
        )

    def test_diagnostic_message_reports_more_rounds_than_tables(self):
        plan = self._make_plan(
            seats=(8, 8), persons=12, rounds=4, avoid_repeat_table=True
        )
        self.assertIn(
            "More rounds (4) than open tables (2).", plan.diagnostic_message
        )

    def test_seed_holds_a_value_beyond_32_bits(self):
        # The library composes a candidate's seed as top_level_seed *
        # SEED_STRIDE + k, routinely past a 4-byte Integer column; this
        # pins the field to a type that still holds it exactly.
        plan = self._make_plan()
        combination = self.env["event.table.combination"].create(
            {"plan_id": plan.id, "rank": 1, "seed": 2**40}
        )
        self.assertEqual(combination.seed, 2**40)

    def test_the_plan_form_declares_the_combination_columns(self):
        # A field used only by a decoration must be declared
        # column_invisible, otherwise the view refuses to load.
        view = self.env.ref("erplibre_event_table.event_table_plan_view_form")
        arch = self.env["event.table.plan"].get_view(view.id, "form")["arch"]
        self.assertIn('name="is_chosen"', arch)
        self.assertIn('name="plan_state"', arch)


class TestChoice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "1"
        )
        cls.event = cls.env["event.event"].create(
            {
                "name": "Rotating Tables Choice",
                "date_begin": "2026-03-02 09:00:00",
                "date_end": "2026-03-02 17:00:00",
            }
        )

    def _make_plan(self, seats=(3, 3, 3, 3), persons=12, rounds=3, **options):
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
        plan.combination_count = 2
        plan.action_generate_combinations()
        plan.combination_ids.filtered(lambda c: c.rank == 1).action_choose()
        return plan

    def test_choosing_seats_every_person_in_every_round(self):
        plan = self._chosen_plan()
        self.assertEqual(plan.state, "chosen")
        chosen = plan.combination_ids.filtered(lambda c: c.rank == 1)
        self.assertEqual(plan.chosen_combination_id, chosen)
        self.assertTrue(chosen.is_chosen)
        self.assertFalse(chosen.is_adjusted)
        # 12 people x 3 rounds
        self.assertEqual(len(plan.assignment_ids), 36)
        self.assertEqual(plan.assignment_ids.combination_id, chosen)
        for participant in plan.participant_ids:
            rounds = plan.assignment_ids.filtered(
                lambda a: a.participant_id == participant
            ).mapped("round_number")
            self.assertEqual(sorted(rounds), [1, 2, 3])
        for line in plan.assignment_ids:
            self.assertEqual(line.table_number, line.table_id.number)
            self.assertEqual(line.seat_number, 0)
        for round_number in (1, 2, 3):
            for table in plan.table_ids:
                seated = plan.assignment_ids.filtered(
                    lambda a: a.round_number == round_number
                    and a.table_id == table
                )
                self.assertLessEqual(len(seated), table.seat_count)
        self.assertEqual(plan.unseated_count, 0)
        self.assertFalse(plan.sync_message)
        self.assertIn("Combination 1 chosen.", plan.message_ids[0].body)

    def test_choosing_another_combination_replaces_the_assignments(self):
        plan = self._chosen_plan()
        second = plan.combination_ids.filtered(lambda c: c.rank == 2)
        second.action_choose()
        self.assertEqual(plan.chosen_combination_id, second)
        self.assertEqual(len(plan.assignment_ids), 36)
        self.assertEqual(plan.assignment_ids.combination_id, second)

    def test_deleting_the_chosen_combination_is_refused(self):
        plan = self._chosen_plan()
        chosen = plan.chosen_combination_id
        other = plan.combination_ids - chosen
        with self.assertRaises(UserError) as caught:
            chosen.unlink()
        self.assertEqual(
            str(caught.exception),
            "This combination is the one in use. Choose another one"
            " before deleting it.",
        )
        other.unlink()
        self.assertFalse(other.exists())

    def test_choosing_locks_the_plan_row(self):
        plan = self._make_plan()
        plan.action_generate_combinations()
        statements = []
        original = self.env.cr.execute

        def spy(query, params=None, **kwargs):
            statements.append(str(query))
            return original(query, params)

        self.patch(self.env.cr, "execute", spy)
        plan.combination_ids.filtered(lambda c: c.rank == 1).action_choose()
        self.assertTrue(
            any(
                "event_table_plan" in q and "FOR UPDATE" in q
                for q in statements
            )
        )

    def test_choosing_before_generating_is_refused(self):
        plan = self._make_plan()
        plan.action_generate_combinations()
        combination = plan.combination_ids.filtered(lambda c: c.rank == 1)
        # Nothing is chosen, so the whole list goes: the point below is
        # that a combination deleted from under a plan is gone for good.
        plan.combination_ids.unlink()
        self.assertFalse(combination.exists())
        other = self._make_plan()
        other.action_generate_combinations()
        candidate = other.combination_ids.filtered(lambda c: c.rank == 1)
        other.write({"state": "draft"})
        with self.assertRaises(UserError) as caught:
            candidate.action_choose()
        self.assertEqual(
            str(caught.exception), "Generate combinations before choosing one."
        )

    def test_choosing_after_a_participant_left_is_refused(self):
        plan = self._make_plan()
        plan.action_generate_combinations()
        combination = plan.combination_ids.filtered(lambda c: c.rank == 1)
        plan.participant_ids[0].unlink()
        with self.assertRaises(UserError) as caught:
            combination.action_choose()
        self.assertIn(
            "Participants or tables changed since this combination was"
            " generated.",
            str(caught.exception),
        )

    def test_seat_numbers_are_unique_within_a_table_and_round(self):
        plan = self._chosen_plan(assign_seats=True)
        for round_number in (1, 2, 3):
            for table in plan.table_ids:
                seats = plan.assignment_ids.filtered(
                    lambda a: a.round_number == round_number
                    and a.table_id == table
                ).mapped("seat_number")
                self.assertEqual(len(seats), len(set(seats)))
                for seat in seats:
                    self.assertTrue(1 <= seat <= table.seat_count)
        line = plan.assignment_ids[0]
        twin = plan.assignment_ids.filtered(
            lambda a: a.round_number == line.round_number
            and a.table_id == line.table_id
            and a != line
        )[0]
        with self.assertRaises(ValidationError):
            twin.with_context(
                event_table_assignment_write=True
            ).seat_number = line.seat_number

    def test_writing_an_assignment_directly_is_refused(self):
        plan = self._chosen_plan()
        line = plan.assignment_ids[0]
        with self.assertRaises(UserError) as caught:
            line.write({"seat_number": 2})
        self.assertEqual(
            str(caught.exception),
            "Assignments change only through the floor plan.",
        )
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            self.env["event.table.assignment"].create(
                {
                    "plan_id": plan.id,
                    "combination_id": plan.chosen_combination_id.id,
                    "round_number": 1,
                    "table_id": plan.table_ids[0].id,
                    "participant_id": plan.participant_ids[0].id,
                }
            )

    def test_a_participant_sits_once_per_round(self):
        plan = self._chosen_plan()
        line = plan.assignment_ids.filtered(lambda a: a.round_number == 1)[0]
        with self.assertRaises(Exception):
            with self.cr.savepoint():
                self.env["event.table.assignment"].with_context(
                    event_table_assignment_write=True
                ).create(
                    {
                        "plan_id": plan.id,
                        "combination_id": plan.chosen_combination_id.id,
                        "round_number": 1,
                        "table_id": plan.table_ids[3].id,
                        "participant_id": line.participant_id.id,
                    }
                )

    def test_only_a_locked_plan_refuses_a_structural_change(self):
        # A proposed plan takes a structural change and keeps the
        # combinations it holds: they may no longer describe the room,
        # which the drift warning says without blocking anyone.
        plan = self._make_plan()
        plan.action_generate_combinations()
        plan.round_count = 4
        self.assertEqual(plan.round_count, 4)
        plan.table_ids[0].write({"position_h": 250.0, "position_v": 80.0})
        self.assertEqual(plan.table_ids[0].position_h, 250.0)
        # Locking refuses both, the layout included.
        plan.action_lock()
        with self.assertRaises(UserError) as caught:
            plan.round_count = 5
        self.assertIn("This plan is locked.", str(caught.exception))
        with self.assertRaises(UserError):
            plan.table_ids[0].write({"position_h": 300.0})
        with self.assertRaises(UserError):
            self.env["event.table"].create(
                {"plan_id": plan.id, "number": 9, "seat_count": 4}
            )

    def test_clicking_draft_destroys_nothing(self):
        # The status bar sets a label and nothing else: draft, proposed
        # and chosen order the work without restricting it, so returning
        # to draft keeps the combinations, the seating and the choice.
        # Pruning the list is an explicit action of its own.
        plan = self._chosen_plan()
        chosen = plan.chosen_combination_id
        plan.write({"state": "draft"})
        self.assertEqual(plan.state, "draft")
        self.assertTrue(plan.combination_ids)
        self.assertTrue(plan.assignment_ids)
        self.assertEqual(plan.chosen_combination_id, chosen)
        plan.round_count = 4
        self.assertEqual(plan.round_count, 4)

    def test_clearing_the_combinations_spares_the_chosen_one(self):
        plan = self._chosen_plan()
        chosen = plan.chosen_combination_id
        self.assertGreater(len(plan.combination_ids), 1)
        plan.action_clear_combinations()
        self.assertEqual(plan.combination_ids, chosen)
        # The survivor is renumbered: rank is read to compare what is on
        # the plan NOW, so it always starts at 1.
        self.assertEqual(chosen.rank, 1)
        self.assertTrue(plan.assignment_ids)
