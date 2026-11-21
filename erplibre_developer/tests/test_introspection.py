# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import unittest

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from .. import introspection
from .common import DeveloperCase

TEST_MODULE = "erplibre_developer_test"


@tagged("post_install", "-at_install")
class TestViewIntrospection(DeveloperCase):
    def setUp(self):
        super().setUp()
        self.form = self.env.ref("base.view_partner_form")
        self.extension = self.env["ir.ui.view"].create(
            {
                "name": "res.partner.form.erplibre_developer.test",
                "model": "res.partner",
                "inherit_id": self.form.id,
                "priority": 99,
                "arch": """
                    <data>
                        <xpath expr="//field[@name='email']" position="after">
                            <field name="ref"/>
                        </xpath>
                        <field name="phone" position="attributes">
                            <attribute name="placeholder">x</attribute>
                        </field>
                    </data>
                """,
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": TEST_MODULE,
                "name": "partner_form_extension",
                "model": "ir.ui.view",
                "res_id": self.extension.id,
            }
        )

    def _info(self, **kwargs):
        return self.Dev.get_view_info("res.partner", self.form.id, "form", **kwargs)

    def _view(self, info, xml_id):
        entries = [v for v in info["views"] if v["xml_id"] == xml_id]
        self.assertEqual(len(entries), 1, xml_id)
        return entries[0]

    def test_current_view(self):
        info = self._info()
        view = info["view"]
        self.assertEqual(view["id"], self.form.id)
        self.assertEqual(view["xml_id"], "base.view_partner_form")
        self.assertEqual(view["module"], "base")
        self.assertEqual(view["model"], "res.partner")
        self.assertEqual(view["type"], "form")
        self.assertEqual(view["mode"], "primary")
        self.assertTrue(view["is_current"])
        self.assertTrue(view["file"].endswith("base/views/res_partner_views.xml"))
        self.assertEqual(
            view["file_rel"][-len("res_partner_views.xml") :], "res_partner_views.xml"
        )
        self.assertIn(
            'id="view_partner_form"', self.read_line(view["file"], view["line"])
        )
        self.assertIn("base", info["modules"])

    def test_every_inheriting_view_in_order(self):
        info = self._info()
        expected = self.form._get_inheriting_views()
        self.assertEqual(sorted(v["id"] for v in info["views"]), sorted(expected.ids))
        self.assertEqual(info["views"][0]["id"], self.form.id)
        ext = self._view(info, f"{TEST_MODULE}.partner_form_extension")
        self.assertEqual(ext["module"], TEST_MODULE)
        self.assertEqual(ext["priority"], 99)
        self.assertEqual(ext["mode"], "extension")
        self.assertEqual(ext["inherit_name"], "base.view_partner_form")
        self.assertEqual(
            ext["specs"],
            [
                {
                    "expr": "//field[@name='email']",
                    "position": "after",
                    "attributes": [],
                },
                {
                    "expr": "//field[@name='phone']",
                    "position": "attributes",
                    "attributes": ["placeholder"],
                },
            ],
        )
        self.assertEqual(ext["fields"], ["email", "ref", "phone"])
        self.assertIn('name="ref"', ext["arch"])
        # A view created in the database has no file.
        self.assertFalse(ext["file"])
        self.assertNotIn(TEST_MODULE, info["modules"])

    def test_application_order_follows_priority(self):
        """Among the extensions of a view, a lower priority applies first."""
        early = self.extension.copy({"priority": 1, "arch": "<data/>"})
        ids = [v["id"] for v in self._info()["views"]]
        self.assertLess(ids.index(early.id), ids.index(self.extension.id))

    def test_combined_arch(self):
        info = self._info()
        tree = etree.fromstring(info["combined_arch"])
        self.assertEqual(tree.tag, "form")
        self.assertTrue(tree.xpath("//field[@name='ref']"))
        self.assertEqual(
            tree.xpath("//field[@name='phone']")[0].get("placeholder"), "x"
        )

    def test_mail_extension(self):
        if not self.module_installed("mail"):
            raise unittest.SkipTest("mail is not installed")
        info = self._info()
        mail = self._view(info, "mail.res_partner_view_form_inherit_mail")
        self.assertEqual(mail["module"], "mail")
        self.assertIn(
            {"expr": "//field[@name='email']", "position": "replace", "attributes": []},
            mail["specs"],
        )
        self.assertIn(
            {"expr": "//sheet", "position": "after", "attributes": []}, mail["specs"]
        )
        self.assertIn("is_blacklisted", mail["fields"])
        self.assertTrue(mail["file"].endswith("mail/views/res_partner_views.xml"))
        self.assertIn(
            "res_partner_view_form_inherit_mail",
            self.read_line(mail["file"], mail["line"]),
        )
        self.assertIn("mail", info["modules"])

    def test_default_view(self):
        info = self.Dev.get_view_info("res.partner", False, "form")
        default = self.env["ir.ui.view"].default_view("res.partner", "form")
        self.assertEqual(info["view"]["id"], default)

    def test_model_without_view(self):
        """A model without a view of the type gets the default arch Odoo
        builds; no view is listed."""
        info = self.Dev.get_view_info("res.country.group", False, "pivot")
        self.assertFalse(info["view"])
        self.assertEqual(info["views"], [])
        self.assertTrue(info["combined_arch"].startswith("<pivot"))

    def test_action(self):
        action = self.env.ref("base.action_partner_form")
        info = self._info(action_id=action.id)
        self.assertEqual(info["action"]["xml_id"], "base.action_partner_form")
        self.assertEqual(info["action"]["module"], "base")
        self.assertFalse(self._info(action_id=0)["action"])

    def test_bad_input(self):
        with self.assertRaises(UserError):
            self.Dev.get_view_info("no.such.model", False, "form")
        with self.assertRaises(UserError):
            self.Dev.get_view_info("res.partner", False, "nonsense")


@tagged("post_install", "-at_install")
class TestFieldIntrospection(DeveloperCase):
    def setUp(self):
        super().setUp()
        self.Partner = self.env["res.partner"]
        self.cache = introspection.SourceCache()

    def _field(self, info, name):
        entries = [f for f in info["fields"] if f["name"] == name]
        self.assertEqual(len(entries), 1, name)
        return entries[0]

    def test_defined_in(self):
        info = self.Dev.get_view_info(
            "res.partner", self.env.ref("base.view_partner_form").id, "form"
        )
        name = self._field(info, "name")
        self.assertEqual(name["type"], "char")
        self.assertEqual(name["defined_in"]["module"], "base")
        self.assertTrue(
            name["defined_in"]["file"].endswith("base/models/res_partner.py")
        )
        self.assertRegex(
            self.read_line(name["defined_in"]["file"], name["defined_in"]["line"]),
            r"^\s+name\s*=\s*fields\.",
        )
        self.assertEqual(name["node"]["name"], "name")

    def test_overridden_by_mail(self):
        if not self.module_installed("mail"):
            raise unittest.SkipTest("mail is not installed")
        info = introspection.field_origins(self.Partner, "name", self.cache)
        self.assertIn("mail", info["override_modules"])
        override = [o for o in info["overrides"] if o["module"] == "mail"][0]
        self.assertEqual(override["kind"], "field")
        self.assertIn("tracking", override["attrs"])
        self.assertFalse(override["behaviour"])
        self.assertTrue(override["file"].endswith("mail/models/res_partner.py"))

    def test_compute(self):
        info = introspection.field_origins(
            self.Partner, "commercial_partner_id", self.cache
        )
        self.assertEqual(info["compute"], "_compute_commercial_partner")
        computes = [o for o in info["overrides"] if o["kind"] == "compute"]
        self.assertTrue(computes)
        self.assertEqual(computes[0]["module"], "base")
        self.assertEqual(computes[0]["method"], "_compute_commercial_partner")
        self.assertIn(
            "def _compute_commercial_partner",
            self.read_line(computes[0]["file"], computes[0]["line"]),
        )

    def test_onchange(self):
        info = introspection.field_origins(self.Partner, "parent_id", self.cache)
        onchanges = {
            (o["module"], o["method"])
            for o in info["overrides"]
            if o["kind"] == "onchange"
        }
        self.assertIn(("base", "onchange_parent_id"), onchanges)

    def test_related(self):
        info = introspection.field_origins(self.Partner, "parent_name", self.cache)
        self.assertEqual(info["related"], "parent_id.name")

    def test_delegated_field(self):
        info = introspection.field_origins(self.env["res.users"], "email", self.cache)
        self.assertEqual(info["inherited_model"], "res.partner")

    def test_core_method(self):
        """A method of the Odoo core is attributed to no module."""
        entries = introspection.method_origins(
            self.Partner, "_compute_display_name", self.cache
        )
        self.assertTrue(entries[0]["core"])
        self.assertFalse(entries[0]["module"])
        self.assertTrue(entries[0]["file"].endswith(os.path.join("odoo", "models.py")))

    def test_arch_fields_skip_subviews(self):
        tree = etree.fromstring(
            "<form><field name='name' invisible='1'/><field name='child_ids'>"
            "<list><field name='email'/></list></field><field name='name'/></form>"
        )
        nodes = introspection.arch_fields(tree)
        self.assertEqual([n["name"] for n in nodes], ["name", "child_ids"])
        self.assertEqual(nodes[0]["invisible"], "1")

    def test_view_specs_shapes(self):
        specs, fields = introspection.view_specs(
            "<field name='email' position='before'><field name='ref'/></field>"
        )
        self.assertEqual(
            specs,
            [
                {
                    "expr": "//field[@name='email']",
                    "position": "before",
                    "attributes": [],
                }
            ],
        )
        self.assertEqual(fields, ["email", "ref"])
        self.assertEqual(introspection.view_specs("<data><broken"), ([], []))
