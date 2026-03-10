# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

import json
import logging

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestSyncModel(TransactionCase):
    """Tests for sync.model."""

    def test_create_sync_model(self):
        rec = self.env["sync.model"].create(
            {
                "name": "Test Sync",
                "model_name": "res.partner",
            }
        )
        self.assertTrue(rec.id)
        self.assertEqual(rec.name, "Test Sync")
        self.assertEqual(rec.model_name, "res.partner")

    def test_sync_model_with_metadata(self):
        metadata = {
            "header": [["Name", "name"], ["Email", "email"]],
            "index_line_header": 0,
            "nb_line_header": 1,
            "sync": ["name"],
            "filetype": "csv",
        }
        rec = self.env["sync.model"].create(
            {
                "name": "Test With Metadata",
                "model_name": "res.partner",
                "spreadsheet_extraction_metadata": json.dumps(metadata),
            }
        )
        loaded = json.loads(rec.spreadsheet_extraction_metadata)
        self.assertEqual(loaded["filetype"], "csv")
        self.assertEqual(len(loaded["header"]), 2)


class TestSyncDataCreate(TransactionCase):
    """Tests for sync.data.create."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Model",
                "model_name": "res.partner",
            }
        )

    def test_create_sync_data_create(self):
        exec_rec = self.env["sync.data.exec"].create(
            {
                "what_import": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        partner = self.env["res.partner"].create({"name": "Test"})
        sdc = self.env["sync.data.create"].create(
            {
                "res_model": "res.partner",
                "res_id": partner.id,
                "sync_data_exec_id": exec_rec.id,
            }
        )
        self.assertTrue(sdc.id)
        self.assertIn("res.partner", sdc.name)


class TestSyncDataExecCronLog(TransactionCase):
    """Tests for sync.data.exec.cron.log."""

    def test_create_cron_log(self):
        log = self.env["sync.data.exec.cron.log"].create(
            {
                "name": "Test Cron Log",
                "error_msg": "Some error occurred",
            }
        )
        self.assertTrue(log.id)
        self.assertEqual(log.name, "Test Cron Log")
        self.assertEqual(log.error_msg, "Some error occurred")


class TestSyncDataTransformFilterSearch(TransactionCase):
    """Tests for sync.data.transform.filter_search."""

    def test_create_filter_search(self):
        rec = self.env["sync.data.transform.filter_search"].create(
            {
                "name": "#%s",
                "sequence": 5,
            }
        )
        self.assertTrue(rec.id)
        self.assertEqual(rec.name, "#%s")
        self.assertTrue(rec.active)

    def test_action_generate_all_no_keys(self):
        rec = self.env["sync.data.transform.filter_search"].create(
            {"name": "test"}
        )
        result = rec.action_generate_all()
        self.assertIsNone(result)

    def test_action_generate_all_creates_records(self):
        rec = self.env["sync.data.transform.filter_search"].create(
            {"name": "test"}
        )
        initial_count = self.env[
            "sync.data.transform.filter_search"
        ].search_count([])
        rec.action_generate_all(keys=["PRJ"])
        new_count = self.env[
            "sync.data.transform.filter_search"
        ].search_count([])
        self.assertGreater(new_count, initial_count)

    def test_action_generate_all_no_duplicates(self):
        rec = self.env["sync.data.transform.filter_search"].create(
            {"name": "test"}
        )
        rec.action_generate_all(keys=["DUP"])
        count_after_first = self.env[
            "sync.data.transform.filter_search"
        ].search_count([])
        rec.action_generate_all(keys=["DUP"])
        count_after_second = self.env[
            "sync.data.transform.filter_search"
        ].search_count([])
        self.assertEqual(count_after_first, count_after_second)


class TestMailTrackingValue(TransactionCase):
    """Tests for mail.tracking.value extension."""

    def test_sync_data_exec_field_exists(self):
        """Verify the sync_data_exec_id field is available."""
        field = self.env["mail.tracking.value"]._fields.get(
            "sync_data_exec_id"
        )
        self.assertIsNotNone(field)
        self.assertEqual(field.comodel_name, "sync.data.exec")
