# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os
import unittest
from unittest.mock import patch

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from .. import introspection
from .common import DeveloperCase

TEST_MODULE = "erplibre_developer_test"
MODEL_MODULE = "odoo.addons.erplibre_developer.models.erplibre_developer"


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
                    "content": [{"tag": "field", "name": "ref", "string": False}],
                    "content_more": 0,
                },
                {
                    "expr": "//field[@name='phone']",
                    "position": "attributes",
                    "attributes": ["placeholder"],
                    "content": [],
                    "content_more": 0,
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

    def test_combined_lines(self):
        """The lines of the combined arch name the module of the view that
        brought each node and of the views that changed its attributes."""
        info = self._info()
        lines = info["combined_lines"]
        self.assertTrue(lines)
        self.assertEqual(lines[0]["depth"], 0)
        self.assertTrue(lines[0]["text"].startswith("<form"))
        self.assertEqual(lines[0]["origin"], "base")
        self.assertEqual(lines[0]["view_id"], self.form.id)
        self.assertEqual(lines[-1]["text"], "</form>")
        by_text = {line["text"]: line for line in lines}
        ref = by_text['<field name="ref"/>']
        self.assertEqual(ref["origin"], TEST_MODULE)
        self.assertEqual(ref["view_id"], self.extension.id)
        phone = next(line for line in lines if 'name="phone"' in line["text"])
        self.assertIn('placeholder="x"', phone["text"])
        self.assertIn(TEST_MODULE, phone["attr_origin"])
        self.assertIn(self.extension.id, phone["attr_view_ids"])
        self.assertFalse(any("data-erplibre-dev" in line["text"] for line in lines))
        self.assertNotIn("data-erplibre-dev", info["combined_arch"])
        if self.module_installed("mail"):
            # mail replaces the email field of the partner form.
            email = next(line for line in lines if 'name="email"' in line["text"])
            self.assertEqual(email["origin"], "mail")

    def test_mail_extension(self):
        if not self.module_installed("mail"):
            raise unittest.SkipTest("mail is not installed")
        info = self._info()
        mail = self._view(info, "mail.res_partner_view_form_inherit_mail")
        self.assertEqual(mail["module"], "mail")
        specs = [(s["expr"], s["position"]) for s in mail["specs"]]
        self.assertIn(("//field[@name='email']", "replace"), specs)
        self.assertIn(("//sheet", "after"), specs)
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
        self.assertFalse(info["combined_lines"])

    def test_action(self):
        action = self.env.ref("base.action_partner_form")
        info = self._info(action_id=action.id)
        self.assertEqual(info["action"]["xml_id"], "base.action_partner_form")
        self.assertEqual(info["action"]["module"], "base")
        self.assertFalse(self._info(action_id=0)["action"])

    def test_views_touching_each_field(self):
        """A field lists the views that show it: the root of the chain by
        its own arch, an extension by the fields its specs add or target."""
        info = self._info()
        fields_info = {f["name"]: f for f in info["fields"]}
        self.assertIn(self.extension.id, fields_info["ref"]["view_ids"])
        self.assertIn(self.form.id, fields_info["phone"]["view_ids"])
        self.assertIn(self.extension.id, fields_info["phone"]["view_ids"])
        self.assertEqual(fields_info["name"]["view_ids"][0], self.form.id)
        self.assertNotIn(self.extension.id, fields_info["name"]["view_ids"])

    def test_module_versions(self):
        info = self._info()
        base = self.env["ir.module.module"].search([("name", "=", "base")])
        versions = info["module_versions"]
        self.assertEqual(set(versions), set(info["modules"]))
        self.assertEqual(versions["base"]["installed"], base.latest_version)
        self.assertEqual(versions["base"]["code"], base.latest_version)
        self.assertFalse(versions["base"]["pending"])
        with patch(f"{MODEL_MODULE}.get_manifest", lambda name: {"version": "99.0.0"}):
            versions = self._info()["module_versions"]
        self.assertTrue(versions["base"]["code"].endswith("99.0.0"))
        self.assertTrue(versions["base"]["pending"])

    def test_snapshot_date(self):
        self.assertIn("snapshot_date", self._info())

    def test_server_actions_checks(self):
        with self.server_actions(flag=False):
            checks = self._info()["server_actions_checks"]
        self.assertFalse(checks["flag"])
        self.assertTrue(checks["group"])
        self.assertTrue(checks["debug"])
        self.assertIn("erplibre_info_allow_server_actions", checks["problem"])
        with self.server_actions():
            checks = self._info()["server_actions_checks"]
        self.assertEqual(
            checks, {"flag": True, "group": True, "debug": True, "problem": False}
        )

    def test_bad_input(self):
        with self.assertRaises(UserError):
            self.Dev.get_view_info("no.such.model", False, "form")
        with self.assertRaises(UserError):
            self.Dev.get_view_info("res.partner", False, "nonsense")


@tagged("post_install", "-at_install")
class TestCombinedLines(DeveloperCase):
    """A primary view and two extensions from two modules, created in the
    test with an external id each."""

    ROOT = """
        <form>
            <sheet>
                <group name="main">
                    <field name="name"/>
                    <field name="email"/>
                    <!-- contact -->
                </group>
            </sheet>
        </form>
    """
    ADD = """
        <field name="email" position="after">
            <field name="phone"/>
            <group name="extra">
                <field name="ref"/>
            </group>
        </field>
    """
    ATTRIBUTES = """
        <data>
            <field name="email" position="attributes">
                <attribute name="readonly">1</attribute>
            </field>
            <field name="phone" position="attributes">
                <attribute name="placeholder">x</attribute>
            </field>
        </data>
    """

    def setUp(self):
        super().setUp()
        self.root = self._view("root", "primary_module", self.ROOT)
        self.adding = self._view("adding", "adding_module", self.ADD, 10)
        self.setting = self._view("setting", "attributes_module", self.ATTRIBUTES, 20)

    def _view(self, name, module, arch, priority=None):
        vals = {
            "name": f"res.partner.erplibre_developer.test.{name}",
            "model": "res.partner",
            "type": "form",
            "arch": arch,
            "priority": priority or 1000,
        }
        if priority:
            vals["inherit_id"] = self.root.id
        view = self.env["ir.ui.view"].create(vals)
        self.env["ir.model.data"].create(
            {
                "module": module,
                "name": f"view_{name}",
                "model": "ir.ui.view",
                "res_id": view.id,
            }
        )
        return view

    def _lines(self):
        info = self.Dev.get_view_info("res.partner", self.root.id, "form")
        return info, [
            (line["depth"], line["text"], line["origin"], line["attr_origin"])
            for line in info["combined_lines"]
        ]

    def test_origin_of_each_node(self):
        info, lines = self._lines()
        self.assertEqual(
            lines,
            [
                (0, "<form>", "primary_module", []),
                (1, "<sheet>", "primary_module", []),
                (2, '<group name="main">', "primary_module", []),
                (3, '<field name="name"/>', "primary_module", []),
                (
                    3,
                    '<field name="email" readonly="1"/>',
                    "primary_module",
                    ["attributes_module"],
                ),
                (
                    3,
                    '<field name="phone" placeholder="x"/>',
                    "adding_module",
                    ["attributes_module"],
                ),
                (3, '<group name="extra">', "adding_module", []),
                (4, '<field name="ref"/>', "adding_module", []),
                (3, "</group>", "adding_module", []),
                (3, "<!-- contact -->", False, []),
                (2, "</group>", "primary_module", []),
                (1, "</sheet>", "primary_module", []),
                (0, "</form>", "primary_module", []),
            ],
        )
        phone = info["combined_lines"][5]
        self.assertEqual(phone["view_id"], self.adding.id)
        self.assertEqual(phone["attr_view_ids"], [self.setting.id])

    def test_moved_and_wrapped_nodes_keep_their_origin(self):
        """A node moved by ``position="move"`` or wrapped by ``$0`` keeps
        the module that brought it; the wrapper takes the module of the
        view that adds it."""
        self._view(
            "moving",
            "moving_module",
            """
            <data>
                <field name="name" position="before">
                    <field name="email" position="move"/>
                </field>
                <field name="ref" position="replace">
                    <div class="wrap">$0</div>
                </field>
            </data>
            """,
            30,
        )
        lines = self._lines()[1]
        self.assertEqual(
            lines[3][1:3], ('<field name="email" readonly="1"/>', "primary_module")
        )
        self.assertEqual(lines[4][1:3], ('<field name="name"/>', "primary_module"))
        self.assertIn((4, '<div class="wrap">', "moving_module", []), lines)
        self.assertIn((5, '<field name="ref"/>', "adding_module", []), lines)

    def test_text_lines(self):
        """Text takes the origin of the element that holds it."""
        self._view(
            "text",
            "text_module",
            """
            <field name="ref" position="after">
                <span>One &amp; two</span>
                <p>first line
                    second line<b>bold</b> tail</p>
            </field>
            """,
            30,
        )
        lines = self._lines()[1]
        start = lines.index((4, '<field name="ref"/>', "adding_module", []))
        self.assertEqual(
            lines[start + 1 : start + 8],
            [
                (4, "<span>One &amp; two</span>", "text_module", []),
                (4, "<p>", "text_module", []),
                (5, "first line", "text_module", []),
                (5, "second line", "text_module", []),
                (5, "<b>bold</b>", "text_module", []),
                (5, "tail", "text_module", []),
                (4, "</p>", "text_module", []),
            ],
        )

    def test_view_without_external_id(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "res.partner.erplibre_developer.test.bare",
                "model": "res.partner",
                "inherit_id": self.root.id,
                "arch": '<field name="name" position="after"><field name="vat"/>'
                "</field>",
            }
        )
        info = self.Dev.get_view_info("res.partner", self.root.id, "form")
        vat = next(
            line for line in info["combined_lines"] if 'name="vat"' in line["text"]
        )
        self.assertFalse(vat["origin"])
        self.assertEqual(vat["view_id"], view.id)

    def test_fallback_on_error(self):
        """Any failure leaves combined_lines False and the payload whole."""
        with (
            patch.object(introspection, "_stamp_specs", side_effect=ValueError),
            self.assertLogs(introspection.__name__, "WARNING"),
        ):
            info = self.Dev.get_view_info("res.partner", self.root.id, "form")
        self.assertFalse(info["combined_lines"])
        self.assertIn('name="ref"', info["combined_arch"])
        self.assertTrue(info["views"])

    def test_fallback_on_different_result(self):
        """A rebuilt arch that differs from the arch of the ORM gives
        False rather than lines that do not match it."""
        chain = introspection.applied_views(self.root)
        modules = {view.id: False for view in chain}
        expected = self.root._get_combined_arch()
        self.assertTrue(introspection.combined_lines(chain, modules, expected))
        expected.set("string", "other")
        with self.assertLogs(introspection.__name__, "WARNING"):
            self.assertFalse(introspection.combined_lines(chain, modules, expected))
        self.assertFalse(introspection.combined_lines([], modules, expected))


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

    def test_declaration_source(self):
        lines = [
            "class SampleModel(models.Model):",
            '    sample_code = fields.Char("Sample code", index=True)  # note',
            "    sample_level = fields.Selection(",
            '        [("low", "Low"), ("high", "High")],',
            "        string='Level',",
            "    )",
            "    sample_note: str = fields.Text()",
            "    def _sample(self):",
            "    sample_open = fields.Char(",
        ]
        source = introspection.declaration_source
        self.assertEqual(
            source(lines, 2), "fields.Char('Sample code', index=True)"
        )
        self.assertEqual(
            source(lines, 3),
            "fields.Selection([('low', 'Low'), ('high', 'High')], string='Level')",
        )
        self.assertEqual(source(lines, 7), "fields.Text()")
        # The class line, a method, a statement never closed, out of range.
        self.assertFalse(source(lines, 1))
        self.assertFalse(source(lines, 8))
        self.assertFalse(source(lines, 9))
        self.assertFalse(source(lines, 0))
        self.assertFalse(source(lines, 42))
        long_help = "x" * 400
        long_source = source([f'    sample = fields.Char(help="{long_help}")'], 1)
        self.assertEqual(len(long_source), introspection.DECLARATION_MAX_CHARS)
        self.assertTrue(long_source.endswith("…"))

    def test_definition_source(self):
        info = introspection.field_origins(self.Partner, "name", self.cache)
        self.assertRegex(info["defined_in"]["source"], r"^fields\.Char\(")

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

    def test_flags(self):
        info = introspection.field_origins(self.Partner, "name", self.cache)
        self.assertFalse(info["company_dependent"])
        self.assertTrue(info["store"])
        found = next(
            (
                (model, field.name)
                for model in self.env.registry.models
                for field in self.env[model]._fields.values()
                if getattr(field, "company_dependent", False)
            ),
            None,
        )
        if not found:
            raise unittest.SkipTest("no company dependent field installed")
        info = introspection.field_origins(self.env[found[0]], found[1], self.cache)
        self.assertTrue(info["company_dependent"])

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
        self.assertFalse(nodes[0]["page"])

    def test_arch_fields_page(self):
        """A field names its nearest notebook page."""
        tree = etree.fromstring(
            "<form><field name='name'/><notebook>"
            "<page name='sales' string='Sales'><group><field name='ref'/></group>"
            "<notebook><page string='Inner'><field name='email'/></page></notebook>"
            "</page><page><field name='phone'/></page></notebook></form>"
        )
        pages = {n["name"]: n["page"] for n in introspection.arch_fields(tree)}
        self.assertFalse(pages["name"])
        self.assertEqual(pages["ref"], {"name": "sales", "string": "Sales"})
        self.assertEqual(pages["email"], {"name": False, "string": "Inner"})
        self.assertEqual(pages["phone"], {"name": False, "string": False})

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
                    "content": [{"tag": "field", "name": "ref", "string": False}],
                    "content_more": 0,
                }
            ],
        )
        self.assertEqual(fields, ["email", "ref"])
        self.assertEqual(introspection.view_specs("<data><broken"), ([], []))

    def test_view_specs_content_capped(self):
        """The content summary keeps the first element nodes, comments
        aside, and counts the others."""
        specs, _fields = introspection.view_specs(
            "<xpath expr='//notebook' position='inside'><!-- note -->"
            "<page name='extra' string='Extra'/><button name='act' string='Go'/>"
            "<field name='ref'/><div/><span/></xpath>"
        )
        self.assertEqual(
            specs[0]["content"],
            [
                {"tag": "page", "name": "extra", "string": "Extra"},
                {"tag": "button", "name": "act", "string": "Go"},
                {"tag": "field", "name": "ref", "string": False},
            ],
        )
        self.assertEqual(specs[0]["content_more"], 2)
        specs, _fields = introspection.view_specs(
            "<xpath expr='//field[@name=\"vat\"]' position='replace'/>"
        )
        self.assertEqual((specs[0]["content"], specs[0]["content_more"]), ([], 0))
