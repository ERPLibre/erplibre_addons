# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.addons.erplibre_event_table.rotation import (
    Options,
    Person,
    Placement,
    Problem,
    Table,
    normalize_company,
    table_targets,
    validate_problem,
)
from odoo.tests.common import BaseCase


class TestRotationTargets(BaseCase):
    """Target occupancy, company key and input validation."""

    def _problem(self, **kwargs):
        vals = {
            "persons": (Person(1), Person(2)),
            "tables": (Table(1, 4),),
            "rounds": 2,
        }
        vals.update(kwargs)
        return Problem(**vals)

    # --- table_targets, the five reference cases from 01 §2 ---

    def test_targets_two_tables_of_unequal_capacity(self):
        self.assertEqual(table_targets([10, 6], 13), [7, 6])

    def test_targets_ten_equal_tables(self):
        self.assertEqual(table_targets([8] * 10, 30), [3] * 10)

    def test_targets_close_tables_that_would_seat_one_person(self):
        self.assertEqual(
            table_targets([8] * 10, 15),
            [3, 2, 2, 2, 2, 2, 2, 0, 0, 0],
        )

    def test_targets_equalise_mixed_capacities(self):
        self.assertEqual(table_targets([12, 10, 8, 6], 20), [5, 5, 5, 5])

    def test_targets_keep_a_lonely_person_when_capacity_is_needed(self):
        self.assertEqual(table_targets([2] * 5, 9), [2, 2, 2, 2, 1])

    def test_targets_raise_when_capacity_is_short(self):
        with self.assertRaises(ValueError):
            table_targets([4, 4], 9)

    def test_targets_never_exceed_capacity(self):
        capacities = [6, 4, 4]
        targets = table_targets(capacities, 12)
        self.assertEqual(sum(targets), 12)
        for capacity, target in zip(capacities, targets):
            self.assertLessEqual(target, capacity)

    def test_targets_honour_a_larger_min_size(self):
        self.assertEqual(table_targets([4] * 4, 6, min_size=3), [3, 3, 0, 0])

    # --- normalize_company ---

    def test_normalize_company_folds_accents_and_punctuation(self):
        self.assertEqual(normalize_company("Café  Déjà-Vu!!"), "cafe deja vu")

    def test_normalize_company_gives_one_key_to_two_spellings(self):
        self.assertEqual(normalize_company("ACME Inc."), "acme inc")
        self.assertEqual(
            normalize_company("ACME Inc."), normalize_company("acme  inc")
        )

    def test_normalize_company_turns_an_empty_label_into_none(self):
        self.assertIsNone(normalize_company(None))
        self.assertIsNone(normalize_company(""))
        self.assertIsNone(normalize_company("   "))
        self.assertIsNone(normalize_company("!!!"))

    # --- dataclasses ---

    def test_options_defaults(self):
        options = Options()
        self.assertTrue(options.separate_companies)
        self.assertTrue(options.avoid_repeat_neighbors)
        self.assertFalse(options.avoid_repeat_table)
        self.assertFalse(options.assign_seats)
        self.assertEqual(options.weights, (100, 10, 1))
        self.assertEqual(options.min_table_size, 2)

    def test_placement_seat_defaults_to_zero(self):
        self.assertEqual(Placement(1, 7, 3).seat, 0)

    def test_person_company_defaults_to_none(self):
        self.assertIsNone(Person(12).company)

    # --- validate_problem ---

    def test_validate_problem_accepts_a_sound_problem(self):
        self.assertIsNone(validate_problem(self._problem()))

    def test_validate_problem_rejects_duplicate_person_keys(self):
        with self.assertRaises(ValueError):
            validate_problem(self._problem(persons=(Person(1), Person(1))))

    def test_validate_problem_rejects_duplicate_table_numbers(self):
        with self.assertRaises(ValueError):
            validate_problem(self._problem(tables=(Table(1, 4), Table(1, 6))))

    def test_validate_problem_rejects_a_table_number_below_one(self):
        with self.assertRaises(ValueError):
            validate_problem(self._problem(tables=(Table(0, 4),)))

    def test_validate_problem_rejects_a_capacity_below_two(self):
        with self.assertRaises(ValueError):
            validate_problem(self._problem(tables=(Table(1, 1),)))

    def test_validate_problem_rejects_rounds_out_of_range(self):
        for rounds in (0, 51):
            with self.assertRaises(ValueError):
                validate_problem(self._problem(rounds=rounds))

    def test_validate_problem_accepts_the_fifty_round_limit(self):
        self.assertIsNone(validate_problem(self._problem(rounds=50)))

    def test_validate_problem_accepts_options_with_no_contradiction(self):
        self.assertIsNone(validate_problem(self._problem(), Options()))

    def test_validate_problem_rejects_an_active_option_with_zero_weight(self):
        cases = (
            Options(separate_companies=True, weights=(0, 10, 1)),
            Options(avoid_repeat_neighbors=True, weights=(100, 0, 1)),
            Options(avoid_repeat_table=True, weights=(100, 10, 0)),
        )
        for options in cases:
            with self.assertRaises(ValueError):
                validate_problem(self._problem(), options)

    def test_validate_problem_accepts_a_zero_weight_on_an_inactive_option(
        self,
    ):
        options = Options(avoid_repeat_table=False, weights=(100, 10, 0))
        self.assertIsNone(validate_problem(self._problem(), options))
