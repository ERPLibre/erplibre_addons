# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import os
import shutil
from unittest import mock

from odoo.addons.code_generator import code_generator_data
from odoo.tests.common import TransactionCase


class TestSyncWriterEmits(TransactionCase):
    """Drives code.generator.writer.create for a sync-configured module and
    asserts the emitted files on disk (the writer end-to-end, exercising the
    numbercall/ondelete fixes through real generation)."""

    def setUp(self):
        super().setUp()
        # auto_format shells out to format.sh (black/isort/prettier via GNU
        # parallel) over the temp module; skip it for speed + hermeticity.
        patcher = mock.patch.object(
            code_generator_data.CodeGeneratorData,
            "auto_format",
            lambda self: None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _generate(self):
        dv_module = self.env["devops.cg.module"].create(
            {"name": "test_sync_writer"}
        )
        dv_model = self.env["devops.cg.model"].create(
            {
                "name": "test.sync.entry",
                "module_id": dv_module.id,
                "enable_sync_external": True,
                "sync_external_file_type": "csv",
                "sync_external_transform_context": "QC - update",
                "sync_external_enable_cron": True,
            }
        )
        self.env["devops.cg.field"].create(
            {
                "model_id": dv_model.id,
                "name": "project_code",
                "type": "char",
                "sync_external_associate_header_name": "Code projet",
                "sync_external_is_primary": True,
            }
        )
        self.env["devops.cg.field"].create(
            {
                "model_id": dv_model.id,
                "name": "client_name",
                "type": "char",
                "sync_external_associate_header_name": "Nom client",
            }
        )
        self.env["devops.cg.sync.bind"].create(
            {
                "model_id": dv_model.id,
                "target_model": "project.project",
                "bind_field_reverse": "project_id",
                "binding_ids": [
                    (0, 0, {"field_name": "name", "is_sync": True})
                ],
            }
        )
        cg_module = self.env["code.generator.module"].create(
            [
                {
                    "name": "test_sync_writer",
                    "shortdesc": "Test Sync Writer",
                    "enable_sync_code": False,
                    "enable_sync_external_data_write": True,
                    "devops_cg_model_ids": [(6, 0, dv_model.ids)],
                }
            ]
        )
        cg_module.add_update_model(
            "x_test.sync.holder",
            dct_field={
                # Manual ir.model.fields must be x_-prefixed
                # (ir_model_fields_name_manual_field constraint).
                "x_name": {"ttype": "char", "field_description": "Name"}
            },
        )
        writer = self.env["code.generator.writer"].create(
            [{"code_generator_ids": cg_module.ids}]
        )
        self.addCleanup(
            shutil.rmtree,
            os.path.dirname(writer.rootdir),
            ignore_errors=True,
        )
        return writer

    def _read(self, writer, suffix):
        for path in writer.get_list_path_file():
            if path.endswith(suffix):
                with open(path) as fh:
                    return fh.read()
        return None

    def test_writer_emits_sync_chain(self):
        writer = self._generate()

        sync_xml = self._read(writer, "data/sync_model.xml")
        self.assertTrue(sync_xml, "data/sync_model.xml was not emitted")
        self.assertIn("sync.model", sync_xml)
        self.assertIn("test_sync_entry", sync_xml)
        self.assertIn("spreadsheet_extraction_metadata", sync_xml)
        self.assertIn("bind_field_model", sync_xml)
        self.assertIn("project.project", sync_xml)

        transform_py = self._read(writer, "models/sync_data_transform.py")
        self.assertTrue(
            transform_py, "models/sync_data_transform.py was not emitted"
        )
        self.assertIn('_inherit = "sync.data.transform"', transform_py)
        self.assertIn("selection_add", transform_py)
        # ondelete fix: must be "set null", never "set default"
        self.assertIn("set null", transform_py)
        self.assertNotIn("set default", transform_py)

        cron_xml = self._read(writer, "data/ir_cron.xml")
        self.assertTrue(cron_xml, "data/ir_cron.xml was not emitted")
        self.assertIn("ir.cron", cron_xml)
        # Odoo 18 fix: numbercall must NOT be emitted
        self.assertNotIn("numbercall", cron_xml)
