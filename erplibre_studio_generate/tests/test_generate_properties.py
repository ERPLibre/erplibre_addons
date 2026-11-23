# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast
import logging
import os
import shutil
import tempfile
from unittest.mock import patch

from lxml import etree
from odoo import fields
from odoo.addons.erplibre_studio.tests.common import StudioCase
from odoo.tests import tagged

MODULE = "studio_test_generate_properties"
VAT = "//field[@name='vat']"
COMPANION = "x_partner_sizes"
# An invented property id, in the shape Odoo gives one.
PROPERTY = "0f1e2d3c4b5a6978"
WRITER_LOGGER = "odoo.addons.code_generator.models.code_generator_writer"


class _Records(logging.Handler):
    """The records a logger emits while the handler is attached."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class PropertiesGenerationCase(StudioCase):
    """A project that adds a properties field to the contact form, which
    reads its definition through a many2one of the contacts, generated
    into a directory of the test."""

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

    def add(self, **field):
        values = {
            "field_description": "Studio sizes",
            "ttype": "properties",
            "definition_record": "country_id",
            "definition_new": {
                "name": COMPANION,
                "field_description": "Partner sizes",
            },
        }
        values.update(field)
        return self.op(
            self.project,
            self.form,
            type="add_field",
            target=VAT,
            position="after",
            field=values,
        )

    def generate(self):
        """Apply and generate the project; the records the writer logs."""
        handler = _Records()
        logger = logging.getLogger(WRITER_LOGGER)
        logger.addHandler(handler)
        try:
            with self.server_actions():
                self.project.action_apply()
                self.project.action_generate()
        finally:
            logger.removeHandler(handler)
        return handler.records

    def read(self, *parts):
        with open(
            os.path.join(self.destination, MODULE, *parts), encoding="utf-8"
        ) as fh:
            return fh.read()

    def field_call(self, path, name):
        """The call that declares the field ``name`` in the file ``path`` of
        the generated module, which parses."""
        tree = ast.parse(self.read(*path))
        calls = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) == name for t in node.targets)
        ]
        self.assertEqual(len(calls), 1)
        return calls[0]

    def check_properties(self, name, definition):
        """The generated contacts declare ``name`` as a fields.Properties
        whose first argument is ``definition``, copied, without default nor
        compute; the class runs as Odoo imports it."""
        call = self.field_call(("models", "res_partner.py"), name)
        self.assertEqual(ast.unparse(call.func), "fields.Properties")
        # Neither the compute nor the store of the registry field, which
        # fields.Properties sets itself from the definition.
        self.assertEqual(
            [k.arg for k in call.keywords], ["definition", "string", "copy"]
        )
        keywords = {k.arg: ast.literal_eval(k.value) for k in call.keywords}
        self.assertEqual(keywords["definition"], definition)
        self.assertIs(keywords["copy"], True)
        self.assertEqual(keywords["string"], "Studio sizes")
        namespace = {"__name__": f"odoo.addons.{MODULE}.models.res_partner"}
        exec(  # pylint: disable=exec-used
            compile(self.read("models", "res_partner.py"), "res_partner.py", "exec"),
            namespace,
        )
        classes = [
            value
            for value in namespace.values()
            if isinstance(value, type) and name in vars(value)
        ]
        self.assertEqual(len(classes), 1)
        field = vars(classes[0])[name]
        self.assertIsInstance(field, fields.Properties)
        self.assertEqual(field.args["definition"], definition)
        self.assertIs(field.args["copy"], True)

    def check_no_default_warning(self, records):
        self.assertFalse(
            [
                record.getMessage()
                for record in records
                if "Not supported default type" in record.getMessage()
            ]
        )


@tagged("post_install", "-at_install")
class TestGenerateProperties(PropertiesGenerationCase):
    """The generated module declares the properties field with its
    definition and the properties definition field it creates on the
    comodel; its view, readme and dependencies follow."""

    def test_generate(self):
        self.assertEqual(self.Project._field_type_module("properties"), "base")
        name = self.add().field_name
        records = self.generate()
        definition = f"country_id.{COMPANION}"
        self.check_properties(name, definition)
        self.check_no_default_warning(records)
        companion = self.field_call(("models", "res_country.py"), COMPANION)
        self.assertEqual(ast.unparse(companion.func), "fields.PropertiesDefinition")
        keywords = {k.arg: ast.literal_eval(k.value) for k in companion.keywords}
        self.assertEqual(keywords["string"], "Partner sizes")
        self.assertNotIn("definition", keywords)
        manifest = ast.literal_eval(self.read("__manifest__.py"))
        self.assertIn("base", manifest["depends"])
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        self.assertEqual(len(views.xpath(f"//field[@name='{name}']")), 1)
        readme = self.read("readme", "DESCRIPTION.md")
        self.assertIn(f"definition `{definition}`", readme)
        self.assertIn(f"field `{COMPANION}` (properties_definition", readme)
        # The applied field reads the same definition.
        self.assertEqual(self.env["res.partner"]._fields[name].definition, definition)

    def test_depends_on_the_modules_of_its_definition(self):
        """A properties field that reads an existing definition field
        through an existing many2one depends on the module of each: the
        registry of a fresh database fails to load the field without
        them. Two modules named for the test own them."""
        Fields = self.env["ir.model.fields"]
        IrModel = self.env["ir.model"]
        definitions = Fields.create(
            {
                "name": "x_studio_test_definitions",
                "model_id": IrModel._get_id("res.country"),
                "ttype": "properties_definition",
                "state": "manual",
                "field_description": "Studio test definitions",
            }
        )
        container = Fields.create(
            {
                "name": "x_studio_test_land_id",
                "model_id": IrModel._get_id("res.partner"),
                "ttype": "many2one",
                "relation": "res.country",
                "state": "manual",
                "field_description": "Studio test land",
            }
        )
        owners = {
            definitions: "studio_test_definition_owner",
            container: "studio_test_container_owner",
        }
        for field, module in owners.items():
            self.env["ir.model.data"].create(
                {
                    "module": module,
                    "name": f"field_{field.model.replace('.', '_')}__{field.name}",
                    "model": "ir.model.fields",
                    "res_id": field.id,
                }
            )
        self.assertNotIn("studio_test_definition_owner", self.project._dependencies())
        self.add(
            definition_record=container.name,
            definition_new=False,
            definition_record_field=definitions.name,
        )
        dependencies = self.project._dependencies()
        self.assertIn("studio_test_definition_owner", dependencies)
        self.assertIn("studio_test_container_owner", dependencies)

    def test_container_comes_before_the_field(self):
        container = "commercial_partner_id"
        companion = "x_studio_definitions"
        change = self.add(
            definition_record=container, definition_new={"name": companion}
        )
        self.assertEqual(change._payload()["container"], container)
        name = change.field_name
        self.generate()
        self.check_properties(name, f"{container}.{companion}")
        # The comodel is the contacts: both fields in the same class.
        call = self.field_call(("models", "res_partner.py"), companion)
        self.assertEqual(ast.unparse(call.func), "fields.PropertiesDefinition")
        views = etree.fromstring(
            self.read("views", "erplibre_studio_views.xml").encode()
        )
        record = views.find("record[@id='base_view_partner_form_studio']")
        nodes = [node.get("name") for node in record.iter("field")]
        self.assertEqual(nodes[nodes.index(container) + 1], name)


@tagged("post_install", "-at_install")
class TestGeneratePropertiesUnprefixed(PropertiesGenerationCase):
    """On a development database, a properties field and its definition
    field without x_: the loader of the names without x_ and the check of
    the definition load both, and the generation writes them."""

    production_rule_pinned = False

    def test_load_and_generate(self):
        name = "studio_sizes"
        companion = "studio_size_definitions"
        self.add(
            name=name,
            definition_new={"name": companion, "field_description": "Sizes"},
        )
        records = self.generate()
        Fields = self.env["ir.model.fields"].sudo()
        row = Fields._get("res.partner", name)
        self.assertTrue(row.erplibre_studio_unprefixed)
        self.assertTrue(
            Fields._get("res.country", companion).erplibre_studio_unprefixed
        )
        definition = f"country_id.{companion}"
        # A new setup of the registry reads the rows: the load path.
        self.registry.setup_models(self.env.cr)
        field = self.env["res.partner"]._fields[name]
        self.assertEqual(field.definition, definition)
        self.assertEqual(
            self.env["res.country"]._fields[companion].type, "properties_definition"
        )
        country = self.env["res.country"].create(
            {"name": "Studio test land", "code": "QY"}
        )
        country[companion] = [{"name": PROPERTY, "string": "Size", "type": "char"}]
        partner = self.env["res.partner"].create(
            {"name": "Studio sizes", "country_id": country.id}
        )
        partner.write({name: {PROPERTY: "M"}})
        partner.invalidate_recordset([name])
        self.assertEqual(partner[name], {PROPERTY: "M"})
        self.check_properties(name, definition)
        self.check_no_default_warning(records)
        call = self.field_call(("models", "res_country.py"), companion)
        self.assertEqual(ast.unparse(call.func), "fields.PropertiesDefinition")
