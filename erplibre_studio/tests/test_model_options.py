# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import StudioCase

MODULE = "studio_test_options"
MODEL = "x_studio_test_option_item"
LEFT = "//group[@name='studio_left']"


@tagged("post_install", "-at_install")
class TestModelOptions(StudioCase):
    """The options of a model of the project: its default order, archivable
    (``x_active``) and manual order (``x_sequence``)."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.line = self.make_model(self.project, "Studio test item", model=MODEL)

    def update(self, **values):
        return self.project._studio_update_model(self.line, values)

    def add_code_field(self):
        """A new char field « Code » (x_code) on the form of the model."""
        self.Editor.apply_operation(
            self.project.id,
            MODEL,
            False,
            "form",
            {
                "type": "add_field",
                "target": LEFT,
                "position": "inside",
                "field": {"ttype": "char", "field_description": "Code"},
            },
            self.project.draft_revision,
        )

    def test_order_checked(self):
        self.update(order="x_name DESC")
        self.assertEqual(self.line.order, "x_name desc")
        self.update(order=" x_name,  id desc ")
        self.assertEqual(self.line.order, "x_name asc, id desc")
        for order in ("display_name asc", "x_unknown", "x_name; drop table"):
            with self.subTest(order=order), self.assertRaises(UserError):
                with self.env.cr.savepoint():
                    self.update(order=order)
        self.assertEqual(self.line.order, "x_name asc, id desc")
        # x_sequence sorts once « Manual order » gives it.
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.update(order="x_sequence asc")
        self.update(order="")
        self.assertFalse(self.line.order)
        self.update(manual_order=True)
        self.assertEqual(self.line.order, "x_sequence asc, id asc")
        # An order set by hand stays when the option comes and goes.
        self.update(order="x_name desc")
        self.update(manual_order=False)
        self.update(manual_order=True)
        self.assertEqual(self.line.order, "x_name desc")
        self.update(order="x_sequence asc, id asc")
        self.update(manual_order=False)
        self.assertFalse(self.line.order)
        # The editor offers the sortable fields of the model.
        payload = self.Editor._model_payload(self.line)
        self.assertEqual(
            (payload["order"], payload["archivable"], payload["manual_order"]),
            ("", False, False),
        )
        names = [name for name, _label in payload["sort_fields"]]
        self.assertIn("x_name", names)
        self.assertNotIn("display_name", names)
        self.assertNotIn("x_sequence", names)

    def test_pending_simulation(self):
        self.update(archivable=True, manual_order=True)
        fields_info = self.project._studio_simulated_fields(self.line)
        self.assertEqual(fields_info["x_active"]["type"], "boolean")
        self.assertEqual(fields_info["x_sequence"]["type"], "integer")
        self.assertIn(
            "x_sequence",
            [n for n, _l in self.Editor._model_payload(self.line)["sort_fields"]],
        )
        data = self.Editor.get_editor_data(MODEL, False, "form", self.project.id)
        palette = [item["name"] for item in data["palette"]]
        # The form shows x_active (the ribbon); x_sequence is offered.
        self.assertIn("x_sequence", palette)
        self.assertNotIn("x_active", palette)
        self.assertEqual(data["fields"]["x_active"]["type"], "boolean")
        arch = etree.fromstring(self.project._studio_default_arch(self.line, "form"))
        self.assertTrue(arch.xpath("//widget[@name='web_ribbon']"))
        simulation = self.project._studio_simulated_views(self.line)
        self.assertEqual(simulation["defaults"]["x_active"], True)
        self.assertEqual(simulation["defaults"]["x_sequence"], 10)
        # A new field of the project cannot take the name of an option.
        self.assertIn("x_active", self.project._taken_field_names(MODEL))
        with self.assertRaises(UserError):
            self.Editor.apply_operation(
                self.project.id,
                MODEL,
                False,
                "form",
                {
                    "type": "add_field",
                    "target": LEFT,
                    "position": "inside",
                    "field": {
                        "ttype": "boolean",
                        "field_description": "Active",
                        "name": "x_active",
                    },
                },
                self.project.draft_revision,
            )

    def test_apply_creates_options(self):
        self.add_code_field()
        self.update(archivable=True, manual_order=True, order="x_code desc")
        self.project.action_apply()
        Model = self.env[MODEL]
        self.assertEqual(Model._active_name, "x_active")
        self.assertEqual(Model._order, "x_code desc")
        self.assertEqual(self.env["ir.model"]._get(MODEL).order, "x_code desc")
        record = Model.create({"x_name": "One"})
        self.assertTrue(record.x_active)
        self.assertEqual(record.x_sequence, 10)
        record.x_active = False
        self.assertFalse(Model.search([("id", "=", record.id)]))
        views = self.line._studio_views()
        listing = etree.fromstring(views["list"].arch)
        self.assertEqual(listing[0].attrib, {"name": "x_sequence", "widget": "handle"})
        search = etree.fromstring(views["search"].arch)
        self.assertTrue(search.xpath("//filter[@name='inactive']"))
        form = etree.fromstring(views["form"].arch)
        self.assertTrue(form.xpath("//widget[@name='web_ribbon']"))
        # The fields of the options leave with the model, not as fields of
        # the project.
        self.assertNotIn("x_active", self.project.field_ids.mapped("name"))
        self.assertEqual(
            self.Editor._model_payload(self.line)["options_applied"],
            {"archivable": True, "manual_order": True},
        )
        self.assertEqual(self.project.state, "applied")
        # Applying again changes nothing; the order changes after Apply.
        self.project.action_apply()
        self.assertTrue(record.x_active is False)
        self.update(order="x_name asc")
        self.project.action_apply()
        self.assertEqual(self.env[MODEL]._order, "x_name asc")
        self.update(order="")
        self.project.action_apply()
        self.assertEqual(self.env["ir.model"]._get(MODEL).order, "id")
        # The model and its options leave the database together.
        self.line.unlink()
        self.project.action_apply()
        self.assertNotIn(MODEL, self.env)
        self.assertFalse(self.env["ir.model.fields"].search([("model", "=", MODEL)]))

    def test_archivable_after_apply_keeps_records_visible(self):
        self.project.action_apply()
        Model = self.env[MODEL]
        records = Model.create([{"x_name": "One"}, {"x_name": "Two"}])
        self.update(archivable=True)
        self.project.action_apply()
        Model = self.env[MODEL]
        self.assertEqual(Model._active_name, "x_active")
        self.assertEqual(Model.search([]), Model.browse(records.ids))
        self.assertEqual(Model.browse(records.ids).mapped("x_active"), [True, True])

    def test_options_frozen_after_apply(self):
        self.update(archivable=True)
        self.project.action_apply()
        with self.assertRaises(UserError):
            with self.env.cr.savepoint():
                self.update(archivable=False)
        self.assertTrue(self.line.archivable)
        self.line.invalidate_recordset()
        # The other option and the order still change.
        self.update(manual_order=True)
        self.assertEqual(self.line.order, "x_sequence asc, id asc")
        self.project.action_apply()
        self.assertEqual(self.env[MODEL]._order, "x_sequence asc, id asc")
        with self.assertRaises(UserError):
            with self.env.cr.savepoint():
                self.update(manual_order=False)
        self.update(order="x_name desc")
        self.project.action_apply()
        self.assertEqual(self.env[MODEL]._order, "x_name desc")

    def test_archived_term_translated(self):
        """The views keep the source term « Archived »; each installed
        language reads it from the catalogue of the studio."""
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"].search(
            [("name", "=", "erplibre_studio")]
        )._update_translations(["fr_CA"])
        self.update(archivable=True)
        self.project.action_apply()
        views = self.line._studio_views()
        for view_type in ("form", "search"):
            view = views[view_type]
            self.assertIn('"Archived"', view.with_context(lang=None).arch_db)
            self.assertIn('"Archivé"', view.with_context(lang="fr_CA").arch_db)

    def test_discard_restores_options(self):
        self.project.action_apply()
        snapshot = self.project.applied_snapshot
        # A model applied without options keeps the snapshot it had.
        self.assertNotIn("archivable", snapshot)
        self.update(order="x_name desc", manual_order=True)
        self.project.action_apply()
        self.update(archivable=True, order="id desc")
        self.assertEqual(self.project.state, "draft")
        self.project.action_discard()
        line = self.project.new_model_ids
        self.assertEqual(
            (line.order, line.archivable, line.manual_order),
            ("x_name desc", False, True),
        )
        self.assertEqual(self.project.state, "applied")

    def test_order_naming_removed_field_refused_at_apply(self):
        self.add_code_field()
        self.update(order="x_code desc")
        self.project.change_ids.unlink()
        with self.assertRaisesRegex(UserError, "x_code"):
            self.project.action_apply()
        self.update(order="x_name desc")
        self.project.action_apply()
        self.assertEqual(self.env[MODEL]._order, "x_name desc")
        # A field removed from the draft once applied: Apply would remove it.
        self.add_code_field()
        self.project.action_apply()
        self.update(order="x_code asc")
        self.project.change_ids.unlink()
        with self.assertRaisesRegex(UserError, "x_code"):
            self.project.action_apply()
