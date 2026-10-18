# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StudioCase

MODULE = "studio_test_pending"
ORDER = "x_studio_test_order"
LINE = "x_studio_test_line"
LEFT = "//group[@name='studio_left']"


@tagged("post_install", "-at_install")
class TestPreviewModels(StudioCase):
    """The default views of a model not created yet: edited in the editor,
    previewed by simulation, bound to the views Apply creates."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.order = self.make_model(
            self.project,
            "Studio test order",
            model=ORDER,
            chatter=self.mail_available(),
        )
        self.line = self.make_model(self.project, "Studio test line", model=LINE)

    def call(self, method, *args, view_type="form", model=ORDER):
        return getattr(self.Editor, method)(
            self.project.id,
            *args,
            model,
            False,
            view_type,
            self.project.draft_revision,
        )

    def operation(self, view_type="form", model=ORDER, **operation):
        return self.Editor.apply_operation(
            self.project.id,
            model,
            False,
            view_type,
            operation,
            self.project.draft_revision,
        )

    def edit_the_order(self):
        self.operation(
            type="add_field",
            target=LEFT,
            position="inside",
            field={"ttype": "char", "field_description": "Code"},
        )
        self.operation(
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
        self.operation(
            view_type="list",
            type="add_existing_field",
            target="//field[@name='x_name']",
            position="after",
            field_name="x_code",
        )

    def database_counts(self):
        self.env.flush_all()
        counts = {}
        for table in ("ir_model", "ir_model_fields", "ir_ui_view", "ir_model_data"):
            self.env.cr.execute(f"SELECT count(*) FROM {table}")
            counts[table] = self.env.cr.fetchone()[0]
        return counts

    def test_the_pending_form_is_edited(self):
        data = self.Editor.get_editor_data(ORDER, False, "form", self.project.id)
        self.assertEqual(
            (
                data["view"]["id"],
                data["view"]["pending"],
                data["view"]["model_line_id"],
            ),
            (False, True, self.order.id),
        )
        self.assertEqual(data["model_name"], "Studio test order")
        self.assertIn("x_name", data["fields"])
        self.assertNotIn("add_filter", data["operations"])
        self.edit_the_order()
        changes = self.project.change_ids
        self.assertEqual(len(changes), 3)
        self.assertFalse(changes.view_id)
        self.assertEqual(changes.model_line_id, self.order)
        payload = self.Editor.get_editor_data(ORDER, False, "list", self.project.id)
        self.assertEqual(len(payload["changes"]), 1)
        self.assertEqual(
            self.Editor._model_payload(self.order)["pending_views"],
            {"form": True, "list": True, "search": False},
        )
        # What needs records or the model waits for Apply.
        with self.assertRaisesRegex(UserError, "Apply the model first"):
            self.operation(view_type="kanban", type="add_existing_field")
        with self.assertRaisesRegex(UserError, "Apply the model first"):
            self.operation(
                view_type="search",
                type="add_filter",
                target="/search",
                position="inside",
                field="x_name",
                value="A",
            )
        # A monetary field needs a currency on the model, a new one does.
        with self.assertRaisesRegex(UserError, "res.currency"):
            self.operation(
                type="add_field",
                target=LEFT,
                position="inside",
                field={"ttype": "monetary", "field_description": "Price"},
            )
        self.operation(
            type="add_field",
            target=LEFT,
            position="inside",
            field={
                "ttype": "many2one",
                "field_description": "Currency",
                "relation": "res.currency",
            },
        )
        self.operation(
            type="add_field",
            target=LEFT,
            position="inside",
            field={
                "ttype": "monetary",
                "field_description": "Price",
                "currency_field": "x_currency",
            },
        )
        price = self.project._field_add_change(ORDER, "x_price")
        self.assertEqual(price._payload()["field"]["currency_field"], "x_currency")
        # A new technical name moves the changes with the model.
        self.project._studio_update_model(self.line, {"model": "x_studio_test_item"})
        self.assertEqual(
            self.project._field_add_change(ORDER, "x_lines")._payload()["field"][
                "relation"
            ],
            "x_studio_test_item",
        )
        self.project._studio_update_model(self.order, {"model": "x_studio_test_sale"})
        self.assertEqual(
            set(self.project.change_ids.mapped("model")), {"x_studio_test_sale"}
        )

    def test_simulation_writes_nothing(self):
        self.edit_the_order()
        revision = self.project.draft_revision
        write_date = self.project.write_date
        counts = self.database_counts()
        data = self.Editor.get_model_preview(self.project.id, self.order.id, "form")
        self.assertEqual(self.database_counts(), counts)
        self.assertEqual(
            (self.project.draft_revision, self.project.write_date),
            (revision, write_date),
        )
        self.assertEqual(data["mode"], "simulation")
        self.assertEqual(sorted(data["views"]), ["form", "list", "search"])
        form = etree.fromstring(data["views"]["form"]["arch"])
        self.assertTrue(form.xpath(f"{LEFT}/field[@name='x_code']"))
        self.assertTrue(
            form.xpath("//field[@name='x_lines']/list/field[@name='x_name']")
        )
        self.assertFalse(form.xpath("//chatter"))
        if self.mail_available():
            self.assertTrue(
                form.xpath("//div[contains(@class, 'o_erplibre_studio_pending')]")
            )
        fields_info = data["models"][ORDER]["fields"]
        self.assertEqual(fields_info["x_code"]["type"], "char")
        self.assertEqual(
            (
                fields_info["x_lines"]["relation"],
                fields_info["x_lines"]["relation_field"],
            ),
            (LINE, "x_studio_test_order_id"),
        )
        self.assertEqual(
            data["models"][LINE]["fields"]["x_studio_test_order_id"]["relation"], ORDER
        )
        self.assertEqual(sorted(data["pending_models"]), [LINE, ORDER])
        self.assertEqual(data["defaults"]["x_code"], False)
        self.assertEqual(data["defaults"]["x_lines"], [])
        self.assertFalse(data["approved"])
        list_arch = etree.fromstring(data["views"]["list"]["arch"])
        self.assertEqual(
            [n.get("name") for n in list_arch.iter("field")], ["x_name", "x_code"]
        )
        # Not for a model that exists.
        self.project.action_apply()
        with self.assertRaises(UserError):
            self.Editor.get_model_preview(self.project.id, self.order.id, "form")

    def test_apply_binds_the_pending_changes(self):
        self.edit_the_order()
        self.project.action_apply()
        self.assertEqual(self.project.state, "applied")
        views = self.order._studio_views()
        changes = self.project.change_ids
        self.assertFalse(changes.model_line_id)
        self.assertEqual(changes.view_id, views["form"] | views["list"])
        studio = self.project.studio_view_ids
        self.assertEqual(studio.inherit_id, views["form"] | views["list"])
        form = etree.fromstring(
            self.env[ORDER].get_view(views["form"].id, "form")["arch"]
        )
        self.assertTrue(form.xpath(f"{LEFT}/field[@name='x_code']"))
        self.assertTrue(form.xpath("//field[@name='x_lines']"))
        listing = etree.fromstring(
            self.env[ORDER].get_view(views["list"].id, "list")["arch"]
        )
        self.assertEqual(
            [n.get("name") for n in listing.iter("field")], ["x_name", "x_code"]
        )
        record = self.env[ORDER].create(
            {"x_name": "First", "x_lines": [(0, 0, {"x_name": "A"})]}
        )
        self.assertEqual(record.x_lines.x_studio_test_order_id, record)
        # Reverted, the changes go with the default views.
        self.project.action_revert()
        self.assertFalse(self.project.change_ids)

    def test_undo_and_remove_on_a_pending_view(self):
        self.edit_the_order()
        data = self.call("project_action", "action_undo", view_type="list")
        self.assertTrue(data["view"]["pending"])
        self.assertEqual(len(self.project.change_ids), 2)
        data = self.operation(type="remove", target=f"{LEFT}/field[@name='x_code']")
        self.assertEqual(len(self.project.change_ids), 1)
        self.assertFalse(data["changes"][0]["error"])
        # Removing the model removes its changes.
        self.project._studio_remove_model(self.order)
        self.assertFalse(self.project.change_ids)
