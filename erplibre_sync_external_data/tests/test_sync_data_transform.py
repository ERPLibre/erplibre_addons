# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSyncDataTransform(TransactionCase):
    """Tests for sync.data.transform model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Sync Model",
                "model_name": "res.partner",
            }
        )

    def test_create_transform(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertTrue(transform.id)
        self.assertEqual(transform.context_name, "default")

    def test_compute_name_from_context(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertEqual(transform.name, "default")

    def test_compute_name_empty_context(self):
        transform = self.env["sync.data.transform"].create(
            {
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertEqual(transform.name, "")

    def test_has_data_to_write_no_execs(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertFalse(transform.has_data_to_write)

    def test_has_data_to_write_with_exec(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "sync_data_transform_id": transform.id,
                "method": "create",
                "modification": '{"name": "Test"}',
            }
        )
        transform.invalidate_recordset()
        self.assertTrue(transform.has_data_to_write)

    def test_has_data_to_write_false_after_wrote(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
                "data_was_wrote": True,
            }
        )
        self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "sync_data_transform_id": transform.id,
                "method": "create",
                "modification": '{"name": "Test"}',
            }
        )
        transform.invalidate_recordset()
        self.assertFalse(transform.has_data_to_write)

    def test_exec_count(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertEqual(transform.sync_data_transform_exec_count, 0)
        self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "sync_data_transform_id": transform.id,
                "method": "create",
                "modification": '{"name": "Test"}',
            }
        )
        transform.invalidate_recordset()
        self.assertEqual(transform.sync_data_transform_exec_count, 1)

    def test_time_duration_no_start_no_end(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertEqual(transform.time_duration_extract, 0)

    def test_time_duration_with_start_and_end(self):
        now = fields.Datetime.now()
        later = now + timedelta(seconds=300)
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
                "time_execution_transform_start": now,
                "time_execution_transform_end": later,
            }
        )
        self.assertEqual(transform.time_duration_extract, 300.0)

    def test_set_end_execution_time(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertFalse(transform.time_execution_transform_end)
        transform._set_end_execution_time()
        self.assertTrue(transform.time_execution_transform_end)

    def test_set_start_execution_time(self):
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
            }
        )
        self.assertFalse(transform.time_execution_transform_start)
        transform._set_start_execution_time()
        self.assertTrue(transform.time_execution_transform_start)

    def test_set_start_does_not_overwrite(self):
        now = fields.Datetime.now()
        transform = self.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [self.sync_model.id])],
                "time_execution_transform_start": now,
            }
        )
        transform._set_start_execution_time()
        self.assertEqual(transform.time_execution_transform_start, now)


class TestSyncDataTransformExec(TransactionCase):
    """Tests for sync.data.transform.exec model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync_model = cls.env["sync.model"].create(
            {
                "name": "Test Sync Model",
                "model_name": "res.partner",
            }
        )
        cls.transform = cls.env["sync.data.transform"].create(
            {
                "context_name": "default",
                "sync_model_ids": [(6, 0, [cls.sync_model.id])],
            }
        )

    def test_create_exec(self):
        exec_rec = self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "sync_data_transform_id": self.transform.id,
                "method": "create",
                "modification": '{"name": "Test Partner"}',
            }
        )
        self.assertTrue(exec_rec.id)
        self.assertEqual(exec_rec.method, "create")

    def test_compute_name(self):
        exec_rec = self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "from_model_name": "sync.model",
                "sync_data_transform_id": self.transform.id,
                "method": "create",
                "modification": '{"name": "Test"}',
            }
        )
        self.assertIn("create", exec_rec.name)
        self.assertIn("res.partner", exec_rec.name)
        self.assertIn("sync.model", exec_rec.name)

    def test_id_depend_name_generated(self):
        exec_rec = self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "sync_data_transform_id": self.transform.id,
                "method": "create",
                "modification": '{"name": "Test"}',
            }
        )
        self.assertTrue(exec_rec.id_depend_name)
        self.assertTrue(exec_rec.id_depend_name.startswith("#REPLACE."))

    def test_action_write_modification_create(self):
        exec_rec = self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "sync_data_transform_id": self.transform.id,
                "method": "create",
                "modification": '{"name": "Test Write Modif Partner"}',
            }
        )
        self.assertFalse(exec_rec.modification_done)
        exec_rec.action_write_modification()
        self.assertTrue(exec_rec.modification_done)
        self.assertTrue(exec_rec.to_id_ref)
        partner = self.env["res.partner"].browse(exec_rec.to_id_ref)
        self.assertEqual(partner.name, "Test Write Modif Partner")

    def test_action_write_modification_write(self):
        partner = self.env["res.partner"].create(
            {"name": "Original Name"}
        )
        exec_rec = self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "to_id_ref": partner.id,
                "sync_data_transform_id": self.transform.id,
                "method": "write",
                "modification": '{"name": "Updated Name"}',
            }
        )
        exec_rec.action_write_modification()
        self.assertTrue(exec_rec.modification_done)
        self.assertEqual(partner.name, "Updated Name")

    def test_action_set_no_match(self):
        self.transform.enable_default_option_no_match = True
        self.transform.default_option_no_match = '{"name": "No Match"}'
        exec_rec = self.env["sync.data.transform.exec"].create(
            {
                "to_model_name": "res.partner",
                "sync_data_transform_id": self.transform.id,
                "method": "create",
                "modification": '{"name": "Test"}',
            }
        )
        exec_rec.action_set_no_match()
        self.assertTrue(exec_rec.has_no_match)
        self.assertEqual(exec_rec.modification, '{"name": "No Match"}')
