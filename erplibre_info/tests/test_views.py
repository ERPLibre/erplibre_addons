# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Every ``type="object"`` button of the module's views can be called the
way the web client calls it. ``check_object_buttons`` serves the modules
that extend erplibre_info as well."""

from types import SimpleNamespace
from unittest.mock import patch

from lxml import etree

from odoo.tests import TransactionCase, tagged


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


def check_object_buttons(case, modules):
    """Check, in the test ``case``, every object button of the views of
    ``modules``; return how many were checked.

    A button sends the ids of its records to ``call_kw``, which passes them
    to an ``@api.model`` method as an extra argument: such a method fails
    with a TypeError on every click.
    """
    data = case.env["ir.model.data"].search(
        [("model", "=", "ir.ui.view"), ("module", "in", list(modules))]
    )
    views = (
        case.env["ir.ui.view"]
        .browse(data.mapped("res_id"))
        .filtered(lambda v: v.type != "qweb")
    )
    checked = 0
    for view in views:
        arch = etree.fromstring(view.arch_db)
        for model, name in _object_buttons([arch], case.env[view.model]):
            method = getattr(model, name, None)
            with case.subTest(view=view.xml_id, button=name):
                case.assertTrue(callable(method), f"{model._name}.{name}")
                case.assertIsNone(
                    getattr(method, "_api", None),
                    f"{model._name}.{name} is @api.model",
                )
            checked += 1
    return checked


@tagged("post_install", "-at_install")
class TestViewButtons(TransactionCase):
    def test_object_buttons_are_record_methods(self):
        self.assertTrue(check_object_buttons(self, ["erplibre_info"]))

    def test_no_empty_settings_page(self):
        """With or without the developer mode, the ERPLibre page and its
        block of the Settings show only when they hold a setting; in the
        developer mode, the server actions are there.

        ``base.group_no_one`` counts only in a session in debug mode: the
        view reads it from ``request``, which the test stands in for."""
        admin = self.env["res.users"].create(
            {
                "name": "ERPLibre settings admin",
                "login": "erplibre_info_settings_admin",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_system").id,
                            self.env.ref("base.group_no_one").id,
                        ],
                    )
                ],
            }
        )
        settings = self.env["res.config.settings"].with_user(admin)
        for developer in (False, True):
            session = SimpleNamespace(session=SimpleNamespace(debug="1"))
            with patch(
                "odoo.addons.base.models.ir_ui_view.request",
                session if developer else None,
            ):
                arch = etree.fromstring(settings.get_view(view_type="form")["arch"])
            with self.subTest(developer=developer):
                pages = arch.xpath("//app[@name='erplibre_info']")
                if developer:
                    self.assertTrue(pages)
                    self.assertTrue(
                        arch.xpath("//setting[@id='erplibre_server_actions']")
                    )
                for node in pages + arch.xpath(
                    "//block[@name='erplibre_code_environment']"
                ):
                    self.assertTrue(node.xpath(".//setting"))
