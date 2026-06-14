# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import ast

from odoo.tests.common import TransactionCase


class TestSyncTransformPy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module = cls.env["devops.cg.module"].create(
            {"name": "test_sync_transform"}
        )

    def _make_model(self, vals=None, fields_vals=None):
        defaults = {
            "name": "test.sync.entry",
            "module_id": self.module.id,
            "enable_sync_external": True,
        }
        if vals:
            defaults.update(vals)
        model = self.env["devops.cg.model"].create(defaults)
        for field_vals in fields_vals or []:
            self.env["devops.cg.field"].create(
                dict(field_vals, model_id=model.id)
            )
        return model

    def test_empty_when_nothing_configured(self):
        model = self._make_model()
        self.assertEqual(model.build_sync_external_transform_py(), "")

    def test_valid_python_and_inherit(self):
        model = self._make_model(
            {
                "sync_external_transform_context": "QC - update",
                "sync_external_transform_context_label": "QC update",
            }
        )
        src = model.build_sync_external_transform_py()
        # It is syntactically valid python.
        ast.parse(src)
        self.assertIn('_inherit = "sync.data.transform"', src)

    def test_selection_add_and_compute(self):
        model = self._make_model(
            {
                "sync_external_transform_context": "QC - update",
                "sync_external_transform_context_label": "QC update",
                "sync_external_no_match_json": '{"ignore_x": true}',
            }
        )
        src = model.build_sync_external_transform_py()
        self.assertIn("selection_add=[('QC - update', 'QC update')]", src)
        self.assertIn("ondelete={'QC - update': \"set null\"}", src)
        self.assertIn("def _compute_context_name(self):", src)
        self.assertIn("super()._compute_context_name()", src)
        self.assertIn(
            "rec.default_option_no_match = '{\"ignore_x\": true}'", src
        )

    def test_method_call_stub_emitted(self):
        model = self._make_model(
            {"sync_external_file_type": "csv"},
            [{"name": "a", "type": "char", "sync_external_is_primary": True}],
        )
        self.env["devops.cg.sync.bind"].create(
            {
                "model_id": model.id,
                "target_model": "crm.lead",
                "method_call": "action_transform_qc_devis",
            }
        )
        src = model.build_sync_external_transform_py()
        ast.parse(src)
        self.assertIn("def action_transform_qc_devis(", src)
        self.assertIn("metadata,", src)
        self.assertIn("do_link=False,", src)
        self.assertIn("TODO", src)
        # The stub must STAGE via sync.data.transform.exec (validation step),
        # not create directly: a shared _stage_exec helper, a per-method loop
        # that stages a create row targeting the bind's target_model, and no
        # leftover no-op "TODO: implement" warning.
        self.assertIn("def _stage_exec(self, vals):", src)
        self.assertIn("sync.data.transform.exec", src)
        self.assertIn("self._stage_exec(", src)
        self.assertIn("\"to_model_name\": 'crm.lead'", src)
        self.assertNotIn("TODO: implement", src)
        self.assertNotIn("_logger.warning", src)

    def test_queue_job_worker_stub_emitted(self):
        model = self._make_model({"sync_external_enable_queue_job": True})
        src = model.build_sync_external_transform_py()
        ast.parse(src)
        self.assertIn("_queue_transform_worker", src)

    def test_aggregates_over_recordset(self):
        m1 = self._make_model({"sync_external_transform_context": "CTX1"})
        m2 = self._make_model(
            {"name": "test.sync.two", "sync_external_enable_queue_job": True}
        )
        src = (m1 | m2).build_sync_external_transform_py()
        ast.parse(src)
        self.assertIn("CTX1", src)
        self.assertIn("_queue_transform_worker", src)

    def test_cron_code_default_scaffold(self):
        model = self._make_model({"sync_external_enable_cron": True})
        code = model.build_sync_external_cron_code()
        self.assertIn("modification_text", code)
        self.assertIn("sync.data.transform", code)

    def test_cron_code_uses_configured_body(self):
        model = self._make_model(
            {
                "sync_external_enable_cron": True,
                "sync_external_cron_code": "model.do_link()",
            }
        )
        self.assertEqual(
            model.build_sync_external_cron_code(), "model.do_link()"
        )
