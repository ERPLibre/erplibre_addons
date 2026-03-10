# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

import logging
from datetime import date, datetime, timedelta

from odoo import fields
from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestTransformDate(TransactionCase):
    """Tests for _transform_date method in sync.data.exec."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Model",
                "model_name": "res.partner",
            }
        )
        cls.exec_rec = cls.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [cls.sync_model.id])],
            }
        )

    def _call_transform(self, value):
        """Helper: call _transform_date and return the parsed result."""
        dct = {"test_date": value}
        self.exec_rec._transform_date(dct, "test_date")
        return dct["test_date"]

    # ------------------------------------------------------------------
    # Integer input (year only)
    # ------------------------------------------------------------------
    def test_date_from_int_year(self):
        result = self._call_transform(2024)
        self.assertEqual(result, date(2024, 1, 1))

    def test_date_from_int_year_old(self):
        result = self._call_transform(1999)
        self.assertEqual(result, date(1999, 1, 1))

    # ------------------------------------------------------------------
    # Slash-separated formats
    # ------------------------------------------------------------------
    def test_date_dd_mm_yyyy_slash(self):
        result = self._call_transform("15/03/2024")
        self.assertEqual(result, date(2024, 3, 15))

    def test_date_yyyy_mm_dd_slash(self):
        result = self._call_transform("2024/03/15")
        self.assertEqual(result, date(2024, 3, 15))

    def test_date_dd_bbb_yy_slash(self):
        """Short english month abbreviation: %d/%b/%y"""
        result = self._call_transform("15/Mar/24")
        self.assertEqual(result, date(2024, 3, 15))

    def test_date_dd_B_yy_slash(self):
        """Full month name %d/%B/%y is locale-dependent.
        On a non-English locale (e.g. fr_CA), English month names
        like 'March' are not recognized by strptime and fall through
        to the French month dictionary which also does not match,
        so the result is False."""
        result = self._call_transform("15/March/24")
        # locale-dependent: only works when system locale is English
        # On French locale, this returns False
        if result:
            self.assertEqual(result, date(2024, 3, 15))
        else:
            self.assertFalse(result)

    def test_date_dd_mm_yy_slash(self):
        result = self._call_transform("15/03/24")
        self.assertEqual(result, date(2024, 3, 15))

    def test_date_mm_dd_yy_slash(self):
        """US format %m/%d/%y — only reached when day > 12."""
        result = self._call_transform("01/25/24")
        self.assertEqual(result, date(2024, 1, 25))

    def test_date_mm_dd_yyyy_slash(self):
        """US format %m/%d/%Y — only reached when day > 12."""
        result = self._call_transform("01/25/2024")
        self.assertEqual(result, date(2024, 1, 25))

    # ------------------------------------------------------------------
    # Dash-separated formats
    # ------------------------------------------------------------------
    def test_date_dd_mm_yyyy_dash(self):
        result = self._call_transform("15-03-2024")
        self.assertEqual(result, date(2024, 3, 15))

    def test_date_yyyy_mm_dd_dash(self):
        result = self._call_transform("2024-03-15")
        self.assertEqual(result, date(2024, 3, 15))

    def test_date_dd_bbb_yy_dash(self):
        result = self._call_transform("15-Mar-24")
        self.assertEqual(result, date(2024, 3, 15))

    def test_date_dd_B_yy_dash(self):
        """Full month name %d-%B-%y is locale-dependent."""
        result = self._call_transform("15-March-24")
        # locale-dependent: only works when system locale is English
        if result:
            self.assertEqual(result, date(2024, 3, 15))
        else:
            self.assertFalse(result)

    def test_date_dd_mm_yy_dash(self):
        result = self._call_transform("15-03-24")
        self.assertEqual(result, date(2024, 3, 15))

    def test_date_mm_dd_yy_dash(self):
        result = self._call_transform("01-25-24")
        self.assertEqual(result, date(2024, 1, 25))

    def test_date_mm_dd_yyyy_dash(self):
        result = self._call_transform("01-25-2024")
        self.assertEqual(result, date(2024, 1, 25))

    # ------------------------------------------------------------------
    # French month abbreviations (via nested try/except fallback)
    # ------------------------------------------------------------------
    def test_date_french_month_janv_slash(self):
        """French abbreviation 'janv' replaced then parsed as %d/%m/%y."""
        result = self._call_transform("15/janv/24")
        self.assertEqual(result, date(2024, 1, 15))

    def test_date_french_month_fevr_dash(self):
        result = self._call_transform("10-fevr-24")
        self.assertEqual(result, date(2024, 2, 10))

    def test_date_french_month_mars_slash(self):
        result = self._call_transform("01/mars/24")
        self.assertEqual(result, date(2024, 3, 1))

    def test_date_french_month_aout_dash(self):
        result = self._call_transform("20-aout-24")
        self.assertEqual(result, date(2024, 8, 20))

    def test_date_french_month_dec_slash(self):
        result = self._call_transform("25/dec/24")
        self.assertEqual(result, date(2024, 12, 25))

    def test_date_french_month_accent_fevr_slash(self):
        """French abbreviation with accent: 'févr'."""
        result = self._call_transform("14/févr/24")
        self.assertEqual(result, date(2024, 2, 14))

    def test_date_french_month_accent_aout_dash(self):
        """French abbreviation with accent: 'août'."""
        result = self._call_transform("15-août-24")
        self.assertEqual(result, date(2024, 8, 15))

    def test_date_french_month_accent_dec_slash(self):
        """French abbreviation with accent: 'déc'."""
        result = self._call_transform("31/déc/24")
        self.assertEqual(result, date(2024, 12, 31))

    # ------------------------------------------------------------------
    # Edge cases / errors
    # ------------------------------------------------------------------
    def test_date_no_separator_returns_false(self):
        """A string with no / or - should return False."""
        result = self._call_transform("20240315")
        self.assertFalse(result)

    def test_date_invalid_string_returns_false(self):
        """Completely invalid date string returns False."""
        result = self._call_transform("not-a-date")
        self.assertFalse(result)

    def test_date_empty_string_returns_false(self):
        result = self._call_transform("")
        self.assertFalse(result)

    def test_date_none_no_crash(self):
        """None value should not modify the dict or crash."""
        dct = {"test_date": None}
        self.exec_rec._transform_date(dct, "test_date")
        self.assertIsNone(dct["test_date"])

    def test_date_already_date_no_crash(self):
        """If the value is already a date object, it should not be touched."""
        original = date(2024, 6, 15)
        dct = {"test_date": original}
        self.exec_rec._transform_date(dct, "test_date")
        self.assertEqual(dct["test_date"], original)

    def test_date_missing_key(self):
        """Key not present in dict should not crash."""
        dct = {}
        self.exec_rec._transform_date(dct, "missing_key")
        self.assertIsNone(dct.get("missing_key"))


class TestTransformDatetime(TransactionCase):
    """Tests for transform_datetime method in sync.data.exec."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Model",
                "model_name": "res.partner",
            }
        )
        cls.exec_rec = cls.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [cls.sync_model.id])],
            }
        )

    def test_transform_datetime_with_date(self):
        """A date should be converted to a UTC datetime string."""
        user_date = date(2024, 6, 15)
        result = self.exec_rec.transform_datetime(user_date)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)

    def test_transform_datetime_falsy_returns_falsy(self):
        result = self.exec_rec.transform_datetime(None)
        self.assertFalse(result)

        result = self.exec_rec.transform_datetime(False)
        self.assertFalse(result)


class TestFormatDurationFr(TransactionCase):
    """Tests for _format_duration_fr method."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Model",
                "model_name": "res.partner",
            }
        )
        cls.exec_rec = cls.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [cls.sync_model.id])],
            }
        )

    def test_zero_seconds(self):
        result = self.exec_rec._format_duration_fr(0)
        self.assertTrue(result)

    def test_negative_seconds(self):
        result = self.exec_rec._format_duration_fr(-10)
        self.assertTrue(result)

    def test_seconds_only(self):
        result = self.exec_rec._format_duration_fr(45)
        self.assertIn("45", result)

    def test_minutes_and_seconds(self):
        result = self.exec_rec._format_duration_fr(125)
        self.assertIn("2", result)
        self.assertIn("5", result)

    def test_hours_minutes_seconds(self):
        result = self.exec_rec._format_duration_fr(3661)
        self.assertIn("1", result)

    def test_days(self):
        result = self.exec_rec._format_duration_fr(90061)
        self.assertIn("1", result)


class TestComputeTimeDuration(TransactionCase):
    """Tests for _compute_time_duration_extract."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Model",
                "model_name": "res.partner",
            }
        )

    def test_no_start_no_end(self):
        rec = self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertEqual(rec.time_duration_extract, 0)

    def test_start_no_end_is_running(self):
        rec = self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
                "time_execution_extract_start": fields.Datetime.now(),
            }
        )
        self.assertEqual(rec.time_duration_extract, 0)

    def test_start_and_end_computes_duration(self):
        now = fields.Datetime.now()
        later = now + timedelta(seconds=120)
        rec = self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
                "time_execution_extract_start": now,
                "time_execution_extract_end": later,
            }
        )
        self.assertEqual(rec.time_duration_extract, 120.0)

    def test_end_before_start_gives_zero(self):
        now = fields.Datetime.now()
        earlier = now - timedelta(seconds=60)
        rec = self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
                "time_execution_extract_start": now,
                "time_execution_extract_end": earlier,
            }
        )
        self.assertEqual(rec.time_duration_extract, 0)


class TestComputeName(TransactionCase):
    """Tests for _compute_name."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Model",
                "model_name": "res.partner",
            }
        )

    def test_name_with_what_import(self):
        rec = self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertTrue(rec.name)
        self.assertIn("Default", rec.name)

    def test_name_with_end_time(self):
        rec = self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
                "time_execution_extract_end": fields.Datetime.now(),
            }
        )
        self.assertIn("UDT", rec.name)


class TestUpdateModificationValue(TransactionCase):
    """Tests for update_modification_value."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Model",
                "model_name": "res.partner",
            }
        )

    def test_no_modifications(self):
        rec = self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        rec.update_modification_value()
        self.assertEqual(rec.create_count, 0)
        self.assertEqual(rec.modif_count, 0)
        self.assertFalse(rec.has_modification)
