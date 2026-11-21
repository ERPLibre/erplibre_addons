# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.studio_pending import pending_view
from .common import StudioCase

FORM = """
<form>
    <sheet>
        <group name="g">
            <field name="name"/>
        </group>
    </sheet>
</form>
"""
GROUP = "//group[@name='g']"
NEW_GROUP = "//group[@name='studio_group_new_group']"
NOTEBOOK = "//notebook[@name='studio_notebook']"
FIRST_TAB = "//page[@name='studio_page_new_tab']"
ITEM = "x_studio_test_layout_item"


@tagged("post_install", "-at_install")
class TestViewsLayout(StudioCase):
    """The layout elements of a form: a group, a tab (in a notebook the
    project creates when none is there) and a separator."""

    def setUp(self):
        super().setUp()
        self.view = self.make_view("form", FORM)
        self.project = self.make_project("studio_test_layout")

    def layout_op(self, otype, target, position, view=None, **extra):
        return self.op(
            self.project,
            view or self.view,
            type=otype,
            target=target,
            position=position,
            **extra,
        )

    def add_group(self, **extra):
        return self.layout_op("add_group", GROUP, "after", **extra)

    def add_tab(self, **extra):
        return self.layout_op("add_page", GROUP, "after", **extra)

    def test_add_group_page_separator(self):
        group = self.add_group()
        self.assertEqual(group.change_type, "add_node")
        self.assertEqual(group._payload()["kind"], "group")
        self.assertIn("New group", group.summary)
        draft = self.draft(self.project, self.view)
        node = draft.xpath(NEW_GROUP)[0]
        self.assertEqual(node.get("string"), "New group")
        self.assertEqual(node.getparent().tag, "sheet")

        # The first tab comes with its notebook.
        notebook = self.add_tab()
        self.assertEqual(notebook._payload()["kind"], "notebook")
        draft = self.draft(self.project, self.view)
        pages = draft.xpath(f"{NOTEBOOK}/page")
        self.assertEqual(
            [(p.get("name"), p.get("string")) for p in pages],
            [("studio_page_new_tab", "New tab")],
        )
        # The next one goes in that notebook, under a free name.
        page = self.layout_op("add_page", NOTEBOOK, "inside", label="Notes")
        self.assertEqual(page._payload()["kind"], "page")
        self.layout_op("add_page", "//page[@name='studio_page_notes']", "before")
        draft = self.draft(self.project, self.view)
        self.assertEqual(len(draft.xpath("//notebook")), 1)
        self.assertEqual(
            [p.get("name") for p in draft.xpath(f"{NOTEBOOK}/page")],
            [
                "studio_page_new_tab",
                "studio_page_new_tab_2",
                "studio_page_notes",
            ],
        )

        # A separator goes in a group, with a title in a form.
        self.layout_op("add_separator", NEW_GROUP, "inside", label="Details")
        draft = self.draft(self.project, self.view)
        separator = draft.xpath(f"{NEW_GROUP}/separator")[0]
        self.assertEqual(separator.get("string"), "Details")
        data = self.Editor.get_editor_data(
            "res.partner", self.view.id, "form", self.project.id
        )
        for operation in ("add_group", "add_page", "add_separator"):
            self.assertIn(operation, data["operations"])

    def test_layout_places_refused(self):
        # A tab never goes inside a group: a notebook does not either.
        with self.assertRaisesRegex(UserError, "notebook goes in a sheet"):
            self.layout_op("add_page", GROUP, "inside")
        # Nothing but a tab goes into a notebook.
        self.add_tab()
        with self.assertRaises(UserError):
            self.layout_op("add_group", NOTEBOOK, "inside")
        with self.assertRaises(UserError):
            self.layout_op("add_separator", FIRST_TAB, "after")
        # A tab does not move out of its notebook.
        with self.assertRaisesRegex(UserError, "tab goes in a notebook"):
            self.layout_op("move", GROUP, "inside", source=FIRST_TAB)

    def test_drop_a_field_into_new_group_and_tab(self):
        self.add_group()
        self.add_tab()
        self.layout_op(
            "add_field",
            NEW_GROUP,
            "inside",
            field={"ttype": "char", "field_description": "Nickname"},
        )
        self.layout_op("add_existing_field", FIRST_TAB, "inside", field_name="email")
        draft = self.draft(self.project, self.view)
        self.assertTrue(draft.xpath(f"{NEW_GROUP}/field[@name='x_nickname']"))
        self.assertTrue(draft.xpath(f"{FIRST_TAB}/field[@name='email']"))

    def test_relabel_added_group(self):
        group = self.add_group()
        count = len(self.project.change_ids)
        touched = self.layout_op("relabel", NEW_GROUP, None, value="Contact")
        self.assertEqual(touched, group)
        self.assertEqual(len(self.project.change_ids), count)
        self.assertEqual(group._payload()["node"]["attrs"]["string"], "Contact")
        draft = self.draft(self.project, self.view)
        self.assertEqual(draft.xpath(NEW_GROUP)[0].get("string"), "Contact")

    def test_remove_added_group_removes_inner_changes(self):
        self.add_group()
        self.layout_op("add_existing_field", NEW_GROUP, "inside", field_name="email")
        self.layout_op(
            "relabel",
            "//field[@name='email']",
            None,
            value="Courriel de contact",
        )
        self.layout_op("add_existing_field", GROUP, "inside", field_name="phone")
        self.assertEqual(len(self.project.change_ids), 4)
        self.layout_op("remove", NEW_GROUP, None)
        self.assertEqual(
            self.project.change_ids.mapped("change_type"),
            ["add_existing_field"],
        )
        draft = self.draft(self.project, self.view)
        self.assertFalse(draft.xpath(NEW_GROUP))
        self.assertTrue(draft.xpath(f"{GROUP}/field[@name='phone']"))

    def test_remove_only_page_removes_notebook(self):
        self.add_tab()
        self.layout_op("add_existing_field", FIRST_TAB, "inside", field_name="email")
        self.layout_op("remove", FIRST_TAB, None)
        self.assertFalse(self.project.change_ids)
        self.assertFalse(self.draft(self.project, self.view).xpath("//notebook"))

    def test_remove_a_tab_of_a_notebook_with_two(self):
        notebook = self.add_tab()
        self.layout_op("add_page", NOTEBOOK, "inside", label="Notes")
        self.layout_op("add_existing_field", FIRST_TAB, "inside", field_name="email")
        self.layout_op(
            "add_existing_field",
            "//page[@name='studio_page_notes']",
            "inside",
            field_name="phone",
        )
        # The first tab, held by the change of the notebook: it leaves that
        # change with what was dropped into it; the notebook stays.
        self.layout_op("remove", FIRST_TAB, None)
        self.assertEqual(len(self.project.change_ids), 3)
        self.assertEqual(notebook._payload()["node"]["children"], [])
        draft = self.draft(self.project, self.view)
        self.assertEqual(
            [p.get("name") for p in draft.xpath(f"{NOTEBOOK}/page")],
            ["studio_page_notes"],
        )
        self.assertFalse(draft.xpath("//field[@name='email']"))
        # The last tab takes the notebook with it.
        self.layout_op("remove", "//page[@name='studio_page_notes']", None)
        self.assertFalse(self.project.change_ids)

    def test_layout_refused_outside_form(self):
        listing = self.make_view("list", "<list><field name='name'/></list>")
        with self.assertRaisesRegex(UserError, "does not apply to a list view"):
            self.layout_op("add_group", "/list", "inside", view=listing)
        data = self.Editor.get_editor_data(
            "res.partner", listing.id, "list", self.project.id
        )
        self.assertNotIn("add_page", data["operations"])

    def test_pending_model_form(self):
        line = self.make_model(self.project, "Studio test layout item", model=ITEM)
        form = pending_view(line, "form")
        self.layout_op("add_group", "//group[@name='studio_main']", "after", view=form)
        self.layout_op("add_page", "//group[@name='studio_main']", "after", view=form)
        self.layout_op(
            "add_separator",
            "//group[@name='studio_left']",
            "inside",
            view=form,
        )
        self.assertEqual(self.project.change_ids.model_line_id, line)
        self.project.action_apply()
        self.assertFalse(self.project.change_ids.model_line_id)
        view = line._studio_views()["form"]
        self.assertEqual(self.project.change_ids.view_id, view)
        arch = etree.fromstring(self.env[ITEM].get_view(view.id, "form")["arch"])
        self.assertTrue(arch.xpath(NEW_GROUP))
        self.assertTrue(arch.xpath(f"{NOTEBOOK}/page[@name='studio_page_new_tab']"))
        self.assertTrue(arch.xpath("//group[@name='studio_left']/separator"))

    def test_apply_and_revert(self):
        self.add_group()
        self.add_tab()
        self.layout_op("add_separator", GROUP, "inside")
        self.project.action_apply()
        arch = self.view._get_combined_arch()
        self.assertTrue(arch.xpath(NEW_GROUP))
        self.assertTrue(arch.xpath(f"{NOTEBOOK}/page[@name='studio_page_new_tab']"))
        self.assertTrue(arch.xpath(f"{GROUP}/separator"))
        self.project.action_revert()
        arch = self.view._get_combined_arch()
        self.assertFalse(arch.xpath("//notebook | //separator"))
        self.assertFalse(arch.xpath(NEW_GROUP))
        self.assertEqual(len(self.project.change_ids), 3)
