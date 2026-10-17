# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import ast

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from .. import arch as studio_arch
from .common import StudioCase


@tagged("post_install", "-at_install")
class TestSearchStudio(StudioCase):
    """The studio on the search view of the contacts."""

    def setUp(self):
        super().setUp()
        self.search = self.env.ref("base.view_res_partner_filter")
        self.project = self.make_project("studio_test_search")

    def add_vat_filter(self, **extra):
        return self.op(
            self.project,
            self.search,
            type="add_filter",
            target="//filter[@name='type_company']",
            position="after",
            label="Has a tax ID",
            conditions=[{"field": "vat", "operator": "set"}],
            **extra,
        )

    def names(self, arch, tag="filter"):
        return [n.get("name") for n in arch.iter(tag)]

    def test_editor_payload(self):
        data = self.Editor.get_editor_data(
            "res.partner", self.search.id, "search", self.project.id
        )
        layout = data["layout"]
        self.assertEqual(data["hide_mode"], "remove")
        self.assertIn("//filter[@name='type_person']", layout["filters"])
        self.assertIn("//filter[@name='salesperson']", layout["group_bys"])
        self.assertIn("//field[@name='email']", layout["fields"])
        self.assertEqual(layout["operators"]["boolean"], ["=", "!="])
        self.assertIn("add_group_by", data["operations"])
        kinds = {b["path"]: b["kind"] for b in data["blocks"]["children"]}
        self.assertEqual(kinds["//filter[@name='inactive']"], "filter")
        self.assertEqual(kinds["/search/separator[1]"], "separator")
        self.assertEqual(kinds["//group[@name='group_by']"], "container")
        palette = {f["name"] for f in data["palette"]}
        self.assertIn("ref", palette)
        self.assertNotIn("email", palette)
        # Not searchable: never offered to a search view.
        self.assertNotIn("avatar_128", palette)

    def test_changes_and_their_xpath(self):
        self.op(
            self.project,
            self.search,
            type="add_existing_field",
            target="//field[@name='email']",
            position="after",
            field_name="ref",
        )
        self.add_vat_filter()
        self.op(
            self.project,
            self.search,
            type="add_filter",
            target="/search",
            position="inside",
            label="French companies",
            conditions=[
                {"field": "is_company", "operator": "=", "value": True},
                {"field": "email", "operator": "ilike", "value": ".fr"},
            ],
        )
        self.op(
            self.project,
            self.search,
            type="add_group_by",
            target="//group[@name='group_by']",
            position="inside",
            field_name="create_date",
            interval="month",
        )
        self.op(
            self.project,
            self.search,
            type="add_separator",
            target="//filter[@name='inactive']",
            position="after",
        )
        self.op(
            self.project,
            self.search,
            type="move",
            source="//filter[@name='inactive']",
            target="//filter[@name='type_person']",
            position="before",
        )
        self.op(
            self.project,
            self.search,
            type="hide",
            target="//filter[@name='type_company']",
            value=True,
        )
        changes = self.project.change_ids
        self.assertEqual(
            [(c.change_type, c.xpath, c.position) for c in changes],
            [
                ("add_existing_field", "//field[@name='email']", "after"),
                ("add_node", "//filter[@name='type_company']", "after"),
                ("add_node", "/search", "inside"),
                ("add_node", "//group[@name='group_by']", "inside"),
                ("add_node", "//filter[@name='inactive']", "after"),
                ("move", "//filter[@name='type_person']", "before"),
                ("remove", "//filter[@name='type_company']", "replace"),
            ],
        )
        payload = changes[1]._payload()
        self.assertEqual(payload["node_name"], "studio_filter_has_a_tax_id")
        self.assertEqual(payload["fields"], ["vat"])
        self.assertEqual(changes[3]._payload()["group_by"], "create_date:month")
        arch = self.draft(self.project, self.search)
        vat = arch.xpath("//filter[@name='studio_filter_has_a_tax_id']")[0]
        self.assertEqual(
            (vat.get("string"), vat.get("domain")),
            ("Has a tax ID", "[('vat', '!=', False)]"),
        )
        french = arch.xpath("//filter[@name='studio_filter_french_companies']")[0]
        self.assertEqual(
            french.get("domain"),
            "[('is_company', '=', True), ('email', 'ilike', '.fr')]",
        )
        self.assertIs(french.getparent(), arch)
        month = arch.xpath("//group[@name='group_by']/filter")[-1]
        self.assertEqual(month.get("context"), "{'group_by': 'create_date:month'}")
        self.assertEqual(
            arch.xpath("//field[@name='ref']")[0].getprevious().get("name"), "email"
        )
        self.assertEqual(
            arch.xpath("//filter[@name='inactive']")[0].getnext().get("name"),
            "type_person",
        )
        self.assertNotIn("type_company", self.names(arch))

        # A label of a filter of the project goes to its own change.
        count = len(self.project.change_ids)
        self.op(
            self.project,
            self.search,
            type="relabel",
            target="//filter[@name='studio_filter_has_a_tax_id']",
            value="With a tax ID",
        )
        self.assertEqual(len(self.project.change_ids), count)
        self.assertEqual(
            changes[1]._payload()["node"]["attrs"]["string"], "With a tax ID"
        )
        # Removing it drops its change; a native filter is removed by a
        # change of its own.
        self.op(
            self.project,
            self.search,
            type="remove",
            target="//filter[@name='studio_filter_has_a_tax_id']",
        )
        self.assertFalse(changes[1].exists())
        self.assertNotIn(
            "studio_filter_has_a_tax_id",
            self.names(self.draft(self.project, self.search)),
        )

    def test_refused_operations(self):
        refused = [
            {
                "type": "add_filter",
                "target": "/search",
                "position": "inside",
                "conditions": [
                    {"field": "is_company", "operator": "ilike", "value": "x"}
                ],
            },
            {
                "type": "add_filter",
                "target": "/search",
                "position": "inside",
                "conditions": [{"field": "nothing", "operator": "set"}],
            },
            {
                "type": "add_filter",
                "target": "/search",
                "position": "inside",
                "conditions": [
                    {"field": "country_id", "operator": "=", "value": "France"}
                ],
            },
            {"type": "add_filter", "target": "/search", "position": "inside"},
            {
                "type": "add_group_by",
                "target": "//group[@name='group_by']",
                "position": "inside",
                "field_name": "country_id",
            },
            {
                "type": "add_group_by",
                "target": "//group[@name='group_by']",
                "position": "inside",
                "field_name": "avatar_128",
            },
            {
                "type": "add_group_by",
                "target": "//group[@name='group_by']",
                "position": "inside",
                "field_name": "name",
                "interval": "month",
            },
            {
                "type": "add_existing_field",
                "target": "/search",
                "position": "inside",
                "field_name": "email",
            },
            {
                "type": "add_existing_field",
                "target": "/search",
                "position": "inside",
                "field_name": "avatar_128",
            },
            {
                "type": "add_separator",
                "target": "//filter[@name='inactive']",
                "position": "inside",
            },
            {"type": "hide", "target": "//filter[@name='inactive']", "value": False},
            {"type": "remove", "target": "/search"},
            {"type": "add_field", "target": "/search", "position": "inside"},
        ]
        for operation in refused:
            with self.subTest(operation=operation), self.assertRaises(UserError):
                self.op(self.project, self.search, **operation)
        self.assertFalse(self.project.change_ids)

    def test_preview_isolation(self):
        editor, other = self.make_users()
        self.project.user_id = editor
        self.add_vat_filter()
        key = self.preview_key(self.project)
        list_view = self.env.ref("base.view_partner_tree")

        def filters(user, context):
            Partner = self.env["res.partner"].with_user(user).with_context(**context)
            views = Partner.get_views(
                [[list_view.id, "list"], [self.search.id, "search"]]
            )
            return self.names(etree.fromstring(views["views"]["search"]["arch"]))

        self.assertIn("studio_filter_has_a_tax_id", filters(editor, key))
        self.assertNotIn("studio_filter_has_a_tax_id", filters(other, key))
        self.assertNotIn("studio_filter_has_a_tax_id", filters(editor, {}))
        self.assertIn("studio_filter_has_a_tax_id", filters(editor, key))

    def test_apply_discard_revert_undo(self):
        self.add_vat_filter()
        self.op(
            self.project,
            self.search,
            type="hide",
            target="//filter[@name='type_person']",
            value=True,
        )
        studio = self.check_apply_is_idempotent(self.project, self.search)
        arch = self.view_arch(self.search)
        self.assertIn("studio_filter_has_a_tax_id", self.names(arch))
        self.assertNotIn("type_person", self.names(arch))
        domain = ast.literal_eval(
            arch.xpath("//filter[@name='studio_filter_has_a_tax_id']")[0].get("domain")
        )
        partner = self.env["res.partner"].create({"name": "Studio", "vat": "X1"})
        self.assertIn(partner, self.env["res.partner"].search(domain))

        self.project.action_undo(self.search)
        self.assertEqual(self.project.state, "draft")
        self.assertIn("type_person", self.names(self.draft(self.project, self.search)))
        self.project.action_discard()
        self.assertEqual(self.project.state, "applied")
        self.assertNotIn(
            "type_person", self.names(self.draft(self.project, self.search))
        )
        self.project.action_revert()
        self.assertFalse(studio.exists())
        self.assertIn("type_person", self.names(self.view_arch(self.search)))

    def test_many2one_filter_compares_by_name(self):
        """A record id would tie the filter to the database it was made in:
        a many2one condition compares the name."""
        country = self.env.ref("base.ca")
        for operator in ("=", "!="):
            with self.subTest(operator=operator), self.assertRaises(UserError):
                self.op(
                    self.project,
                    self.search,
                    type="add_filter",
                    target="/search",
                    position="inside",
                    label="Country",
                    conditions=[
                        {
                            "field": "country_id",
                            "operator": operator,
                            "value": country.id,
                        }
                    ],
                )
        self.assertEqual(
            studio_arch.SEARCH_OPERATORS["many2one"],
            ("ilike", "not ilike", "set", "not set"),
        )
        self.op(
            self.project,
            self.search,
            type="add_filter",
            target="/search",
            position="inside",
            label="Country",
            conditions=[{"field": "country_id", "operator": "ilike", "value": "Can"}],
        )
        self.project.action_apply()
        studio = self.project.studio_view_ids
        self.assertIn("[('country_id', 'ilike', 'Can')]", studio.arch)
        domain = etree.fromstring(studio.arch).xpath("string(//filter/@domain)")
        self.assertNotIn(str(country.id), domain)

    def test_remove_a_separator_of_the_project(self):
        self.op(
            self.project,
            self.search,
            type="add_separator",
            target="/search/separator[1]",
            position="after",
        )
        self.op(self.project, self.search, type="remove", target="/search/separator[2]")
        self.assertFalse(self.project.change_ids)
        # A native separator is removed by a change of its own.
        self.op(self.project, self.search, type="remove", target="/search/separator[1]")
        self.assertEqual(self.project.change_ids.mapped("change_type"), ["remove"])
