# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.tests import tagged

MODULE = "studio_test_generate_json"


@tagged("post_install", "-at_install")
class TestGenerateJson(StudioCase):
    """Generation of a project that adds a JSON field to the contact form:
    the module declares it as fields.Json, with no default, and its view
    shows it through the widget « jsonb »."""

    def setUp(self):
        super().setUp()
        self.destination = tempfile.mkdtemp(prefix="erplibre_studio_test_")
        self.addCleanup(shutil.rmtree, self.destination, True)
        choices = [(self.destination, self.destination)]
        patcher = patch.object(
            type(self.Project), "_destination_choices", lambda self_: choices
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.make_project(MODULE, destination=self.destination)
        self.name = self.op(
            self.project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={"ttype": "json", "field_description": "Extra data"},
        ).field_name

    def read(self, *parts):
        with open(
            os.path.join(self.destination, MODULE, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def test_generate(self):
        self.assertEqual(self.Project._field_type_module("json"), "base")
        with self.server_actions():
            self.project.action_apply()
            self.project.action_generate()
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertIn("base", manifest["depends"])
        model = self.read("models", "res_partner.py")
        tree = ast.parse(model)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) == self.name for t in node.targets)
        ]
        self.assertEqual(len(calls), 1)
        call = calls[0].value
        self.assertEqual(ast.unparse(call.func), "fields.Json")
        keywords = {k.arg: k.value for k in call.keywords}
        self.assertEqual(ast.literal_eval(keywords["string"]), "Extra data")
        self.assertNotIn("default", keywords)
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        self.assertEqual(
            views.xpath(f"//field[@name='{self.name}']/@widget"), ["jsonb"]
        )
