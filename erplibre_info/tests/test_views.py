# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Every ``type="object"`` button of the module's views can be called the
way the web client calls it."""

from lxml import etree

from odoo.tests import TransactionCase, tagged

MODULES = ("erplibre_info", "erplibre_info_developer_menu")


def _object_buttons(node, model):
    """Yield ``(model, name)`` for every object button under ``node``; a
    button inside a relational field's subview belongs to its comodel."""
    for child in node:
        if not isinstance(child.tag, str):
            continue
        sub = model
        if child.tag == "field":
            field = model._fields.get(child.get("name"))
            if field is not None and field.relational:
                sub = model.env[field.comodel_name]
        if child.tag == "button" and child.get("type") == "object":
            yield model, child.get("name")
        yield from _object_buttons(child, sub)


@tagged("post_install", "-at_install")
class TestViewButtons(TransactionCase):
    def test_object_buttons_are_record_methods(self):
        """A button sends the ids of its records to ``call_kw``, which passes
        them to an ``@api.model`` method as an extra argument: such a method
        fails with a TypeError on every click."""
        data = self.env["ir.model.data"].search(
            [("model", "=", "ir.ui.view"), ("module", "in", MODULES)]
        )
        views = (
            self.env["ir.ui.view"]
            .browse(data.mapped("res_id"))
            .filtered(lambda v: v.type != "qweb")
        )
        checked = 0
        for view in views:
            arch = etree.fromstring(view.arch_db)
            for model, name in _object_buttons([arch], self.env[view.model]):
                method = getattr(model, name, None)
                with self.subTest(view=view.xml_id, button=name):
                    self.assertTrue(callable(method), f"{model._name}.{name}")
                    self.assertIsNone(
                        getattr(method, "_api", None),
                        f"{model._name}.{name} is @api.model",
                    )
                checked += 1
        self.assertGreater(checked, 10)
