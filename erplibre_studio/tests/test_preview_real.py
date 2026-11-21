# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
from unittest.mock import patch

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import sql

from ..models import erplibre_studio_preview
from .common import StudioCase

MODULE = "studio_test_real"
ORDER = "x_studio_test_order"
LINE = "x_studio_test_line"
LEFT = "//group[@name='studio_left']"


@tagged("post_install", "-at_install")
class TestPreviewReal(StudioCase):
    """The real preview: the models created in a savepoint, rendered, then
    rolled back; nothing outlives it, neither in the database nor in the
    registry."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.order = self.make_model(
            self.project,
            "Studio test order",
            model=ORDER,
            chatter=self.mail_available(),
        )
        self.make_model(self.project, "Studio test line", model=LINE)
        form = self.Editor._resolve_view(ORDER, False, "form", self.project)
        self.op(
            self.project,
            form,
            type="add_field",
            target=LEFT,
            position="inside",
            field={"ttype": "char", "field_description": "Code"},
        )
        self.op(
            self.project,
            form,
            type="add_field",
            target="//group[@name='studio_right']",
            position="inside",
            field={
                "ttype": "one2many",
                "field_description": "Lines",
                "relation": LINE,
                "inverse": {"create": True},
            },
        )
        self.op(
            self.project,
            form,
            type="add_field",
            target=LEFT,
            position="inside",
            field={
                "ttype": "many2one",
                "field_description": "Customer",
                "relation": "res.partner",
            },
        )

    def preview(self, mode="real"):
        return self.Editor.get_model_preview(
            self.project.id, self.order.id, "form", mode
        )

    def state(self):
        """What a real preview must leave as it found it."""
        self.env.flush_all()
        cr = self.env.cr
        registry = self.env.registry
        counts = {}
        for table in ("ir_model", "ir_model_fields", "ir_ui_view", "ir_model_data"):
            cr.execute(f"SELECT count(*) FROM {table}")
            counts[table] = cr.fetchone()[0]
        return {
            "counts": counts,
            "tables": [
                sql.table_exists(cr, m.replace(".", "_")) for m in (ORDER, LINE)
            ],
            "registry": (ORDER in registry, LINE in registry),
            "column": sql.column_exists(cr, "res_partner", "x_studio_test_order_id"),
            "invalidated": registry.registry_invalidated,
            "caches": set(registry.cache_invalidated),
            "queue": len(registry._constraint_queue),
            "postcommit": len(cr.postcommit._funcs),
            "postrollback": len(cr.postrollback._funcs),
        }

    def test_refused_until_approved(self):
        with self.assertRaisesRegex(UserError, "approve"):
            self.preview()
        self.project.action_approve()
        self.assertTrue(self.project.approved)
        self.assertEqual(self.project.approved_uid, self.env.user)
        data = self.Editor.get_editor_data(ORDER, False, "form", self.project.id)
        self.assertTrue(data["project"]["approved"])
        self.assertTrue(data["project"]["real_preview_available"])
        # A change of the models withdraws the approval.
        form = self.Editor._resolve_view(ORDER, False, "form", self.project)
        self.op(
            self.project,
            form,
            type="add_field",
            target=LEFT,
            position="inside",
            field={"ttype": "integer", "field_description": "Size"},
        )
        self.assertFalse(self.project.approved)
        with self.assertRaisesRegex(UserError, "approve"):
            self.preview()
        # A change of an existing view does not.
        self.project.action_approve()
        self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='email']",
            value="Mail",
        )
        self.assertTrue(self.project.approved)
        self.project.action_unapprove()
        self.assertFalse(self.project.approved or self.project.approved_uid)
        # Nothing to approve without a model waiting for Apply.
        empty = self.make_project("studio_test_real_empty")
        with self.assertRaises(UserError):
            empty.action_approve()

    def test_real_preview_leaves_nothing(self):
        self.project.action_approve()
        before = self.state()
        self.assertEqual(before["registry"], (False, False))
        data = self.preview()
        self.assertEqual(self.state(), before)
        self.assertNotIn(ORDER, self.env)
        self.assertNotIn("error", data)
        self.assertEqual(data["mode"], "real")
        fields_info = data["models"][ORDER]["fields"]
        for name in ("x_name", "x_code", "x_lines", "x_customer"):
            self.assertIn(name, fields_info)
        self.assertEqual(fields_info["x_lines"]["relation"], LINE)
        self.assertIn(LINE, data["models"])
        self.assertEqual(sorted(data["pending_models"]), [LINE, ORDER])
        if self.mail_available():
            self.assertIn("message_ids", fields_info)
        form = etree.fromstring(data["views"]["form"]["arch"])
        self.assertTrue(form.xpath("//field[@name='x_code']"))
        self.assertTrue(form.xpath("//field[@name='x_lines']"))
        self.assertFalse(form.xpath("//chatter"))
        self.assertIn("x_name", data["defaults"])
        json.dumps(data)
        # Twice: the same answer, the same state.
        again = self.preview()
        self.assertEqual(again["models"][ORDER]["fields"].keys(), fields_info.keys())
        self.assertEqual(self.state(), before)
        # The simulation answers the same fields of the project.
        simulated = self.preview("simulation")
        for name in ("x_code", "x_lines", "x_customer"):
            self.assertEqual(
                simulated["models"][ORDER]["fields"][name]["type"],
                fields_info[name]["type"],
            )
        # Apply still creates them.
        self.project.action_apply()
        self.assertIn(ORDER, self.env)
        self.assertIn("x_lines", self.env[ORDER]._fields)

    def test_real_preview_of_a_settings_user(self):
        """A Settings user previews a model whose access rights only Apply
        creates: the render reads the views of the sandbox in sudo."""
        admin = self.env.ref("base.user_admin")
        project = self.project.with_user(admin)
        project.action_approve()
        before = self.state()
        data = self.Editor.with_user(admin).get_model_preview(
            project.id, self.order.id, "form", "real"
        )
        self.assertNotIn("error", data)
        self.assertIn("x_lines", data["models"][ORDER]["fields"])
        self.assertEqual(self.state(), before)

    def test_a_view_that_does_not_render(self):
        """An error of the views is the answer of the real preview, with the
        same state left. A change that shows a field the model will not have
        is an error of the draft already (``_draft_arch``): the arch of the
        test names one all the same."""
        Change = self.env["erplibre.studio.change"]
        change = Change.create(
            {
                "project_id": self.project.id,
                "change_type": "add_existing_field",
                "model": ORDER,
                "model_line_id": self.order.id,
                "view_type": "form",
                "xpath": LEFT,
                "position": "inside",
                "payload": json.dumps({"field_name": "x_studio_test_nowhere"}),
            }
        )
        form = self.Editor._resolve_view(ORDER, False, "form", self.project)
        arch, errors = self.project._draft_arch(form)
        self.assertIn("x_studio_test_nowhere", errors[change.id])
        self.assertFalse(arch.xpath("//field[@name='x_studio_test_nowhere']"))
        self.project.action_approve()
        before = self.state()
        Project = type(self.project)
        draft_arch = Project._draft_arch

        def broken(project, view):
            arch, errors = draft_arch(project, view)
            if view.type == "form":
                etree.SubElement(arch, "field", name="x_studio_test_nowhere")
            return arch, errors

        with patch.object(Project, "_draft_arch", broken):
            data = self.preview()
        self.assertIn("x_studio_test_nowhere", data["error"])
        self.assertEqual(self.state(), before)

    def test_one_real_preview_at_a_time(self):
        self.project.action_approve()
        lock = patch.object(erplibre_studio_preview, "_REAL_PREVIEW_LOCK")
        with lock as mocked:
            mocked.acquire.return_value = False
            with self.assertRaisesRegex(UserError, "Another real preview"):
                self.preview()
        registry = self.env.registry
        registry.registry_invalidated = True
        try:
            with self.assertRaisesRegex(UserError, "reload the editor"):
                self.preview()
        finally:
            registry.registry_invalidated = False
        self.assertNotIn("error", self.preview())
