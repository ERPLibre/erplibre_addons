# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.studio_pending import pending_view
from .common import StudioCase

FORM = """
<form>
    <sheet>
        <group name="g">
            <field name="name"/>
            <field name="type"/>
            <field name="country_id"/>
            <field name="category_id"/>
            <field name="child_ids">
                <list>
                    <field name="name"/>
                </list>
            </field>
        </group>
    </sheet>
</form>
"""
LIST = """
<list>
    <field name="name"/>
    <field name="country_id"/>
    <field name="category_id"/>
</list>
"""
MODULE = "studio_test_advanced"
ITEM = "x_studio_test_advanced_item"


def named(name, view_type="form"):
    """The path of the field ``name`` of FORM (outside the sub-view of
    child_ids) or of LIST."""
    if view_type == "list":
        return f"/list/field[@name='{name}']"
    return f"//group[@name='g']/field[@name='{name}']"


@tagged("post_install", "-at_install")
class TestViewsAdvanced(StudioCase):
    """The widget, the domain and the groups of a field of a form or a
    list, written by « set_attribute »."""

    def setUp(self):
        super().setUp()
        self.form_view = self.make_view("form", FORM)
        self.list_view = self.make_view("list", LIST)
        self.project = self.make_project(MODULE)

    def set_attr(self, name, attribute, value, view=None):
        view = view or self.form_view
        return self.op(
            self.project,
            view,
            type="set_attribute",
            target=named(name, view.type),
            attribute=attribute,
            value=value,
        )

    def node(self, name, view=None):
        view = view or self.form_view
        return self.draft(self.project, view).xpath(named(name, view.type))[0]

    def test_operations_and_settable(self):
        for view in (self.form_view, self.list_view):
            data = self.Editor.get_editor_data(
                "res.partner", view.id, view.type, self.project.id
            )
            self.assertIn("set_attribute", data["operations"])
            self.assertEqual(
                data["settable"]["field"],
                {"widget": "widget", "domain": "field_domain", "groups": "groups"},
            )

    def test_widget_on_form_and_list(self):
        change = self.set_attr("type", "widget", "radio")
        self.assertEqual(change._payload()["value"], "radio")
        self.assertEqual(self.node("type").get("widget"), "radio")
        self.set_attr("category_id", "widget", "many2many_tags", view=self.list_view)
        node = self.node("category_id", view=self.list_view)
        self.assertEqual(node.get("widget"), "many2many_tags")
        with self.assertRaises(UserError):
            self.set_attr("name", "widget", "a widget")
        # Back to the arch without the change: the change goes.
        self.set_attr("type", "widget", "")
        self.assertEqual(len(self.project.change_ids), 1)
        # An attribute outside SETTABLE_ATTRIBUTES, a field of the sub-view
        # of an x2many: neither is set from the form.
        with self.assertRaisesRegex(UserError, "cannot be set here"):
            self.set_attr("name", "colspan", "2")
        with self.assertRaisesRegex(UserError, "cannot be set here"):
            self.op(
                self.project,
                self.form_view,
                type="set_attribute",
                target="//field[@name='child_ids']/list/field[@name='name']",
                attribute="widget",
                value="char",
            )

    def test_domain_on_relational_only(self):
        change = self.set_attr("country_id", "domain", '[("code","=","FR")]')
        payload = change._payload()
        self.assertEqual(payload["value"], "[('code', '=', 'FR')]")
        self.assertEqual(payload["domain_model"], "res.country")
        self.assertEqual(payload["domain_fields"], ["code"])
        self.assertEqual(self.node("country_id").get("domain"), payload["value"])
        self.set_attr(
            "category_id", "domain", "['|', ('name', 'ilike', 'a'), ('id', '>', 0)]"
        )
        with self.assertRaisesRegex(UserError, "relational field"):
            self.set_attr("name", "domain", "[('id', '=', 1)]")
        # A domain that reads the record or the user is not a literal.
        with self.assertRaisesRegex(UserError, "not a domain"):
            self.set_attr("country_id", "domain", "[('id', '=', uid)]")
        with self.assertRaisesRegex(UserError, "not a domain"):
            self.set_attr("country_id", "domain", "('code', '=', 'FR')")
        with self.assertRaisesRegex(UserError, "does not apply"):
            self.set_attr("country_id", "domain", "[('x_no_such_field', '=', 1)]")
        # Empty: no domain, the change goes.
        self.set_attr("country_id", "domain", "")
        self.assertNotIn("domain", self.node("country_id").attrib)
        # A new many2one of the project, not created yet: read from its
        # definition.
        added = self.op(
            self.project,
            self.form_view,
            type="add_field",
            target=named("name"),
            position="after",
            field={
                "ttype": "many2one",
                "field_description": "Studio test land",
                "relation": "res.country",
            },
        )
        name = added._payload()["field_name"]
        change = self.set_attr(name, "domain", "[('code', 'in', ['CA', 'FR'])]")
        self.assertEqual(change._payload()["domain_model"], "res.country")

    def test_groups(self):
        change = self.set_attr("name", "groups", ["base.group_system"])
        self.assertEqual(change._payload()["value"], "base.group_system")
        self.assertEqual(change._payload()["groups"], ["base.group_system"])
        self.assertEqual(self.node("name").get("groups"), "base.group_system")
        # A comma text is read as a list; a leading « ! » excludes a group.
        change = self.set_attr(
            "name", "groups", "base.group_system, !base.group_portal"
        )
        self.assertEqual(
            change._payload()["groups"], ["base.group_system", "base.group_portal"]
        )
        with self.assertRaisesRegex(UserError, "studio_test_unknown.group_none"):
            self.set_attr("name", "groups", ["studio_test_unknown.group_none"])
        # A record that is not a group.
        with self.assertRaises(UserError):
            self.set_attr("name", "groups", ["base.main_company"])

        app = self.project._studio_save_app({"name": "Studio test advanced"})
        line = self.project._studio_save_group(
            {"name": "Studio test reviewer", "app_id": app.id}
        )
        xmlid = line._studio_full_xmlid()
        choices = self.Editor.get_studio_choices(self.project.id)["groups"]
        own = [g for g in choices if g.get("project")]
        self.assertEqual([(g["xml_id"], g["applied"]) for g in own], [(xmlid, False)])
        with self.assertRaisesRegex(UserError, "Apply the group"):
            self.set_attr("country_id", "groups", [xmlid])
        self.project.action_apply()
        self.assertTrue(line._studio_group_record())
        change = self.set_attr("country_id", "groups", [xmlid])
        self.assertEqual(change._payload()["groups"], [xmlid])
        # A group a view shows a node for stays.
        with self.assertRaisesRegex(UserError, "Studio test reviewer"):
            self.project._studio_remove_group(line)
        # Empty: back to the arch, the change goes.
        count = len(self.project.change_ids)
        self.set_attr("country_id", "groups", [])
        self.assertEqual(len(self.project.change_ids), count - 1)
        self.assertNotIn("groups", self.node("country_id").attrib)
        self.project._studio_remove_group(line)
        self.assertFalse(line.exists())

    def test_rename_keeps_the_groups_of_the_project(self):
        # The external id of a group of the project moves with the module:
        # the « groups » of a field follow it, a « ! » kept.
        app = self.project._studio_save_app({"name": "Studio test advanced"})
        line = self.project._studio_save_group(
            {"name": "Studio test reviewer", "app_id": app.id}
        )
        self.project.action_apply()
        old = line._studio_full_xmlid()
        change = self.set_attr("country_id", "groups", f"base.group_system,!{old}")
        self.project.action_apply()
        self.project.module_name = "studio_test_advanced_renamed"
        new = line._studio_full_xmlid()
        self.assertEqual(new, f"studio_test_advanced_renamed.{line.xml_name}")
        payload = change._payload()
        self.assertEqual(payload["value"], f"base.group_system,!{new}")
        self.assertEqual(payload["groups"], ["base.group_system", new])
        self.assertEqual(self.project.state, "draft")
        # The check of the view knows the group under its new external id.
        with self.assertNoLogs("odoo.addons.base.models.ir_ui_view", "WARNING"):
            self.project.action_apply()
        arch = self.form_view._get_combined_arch()
        self.assertEqual(
            arch.xpath(named("country_id"))[0].get("groups"),
            f"base.group_system,!{new}",
        )
        self.assertEqual(self.env.ref(new), line._studio_group_record())

    def test_pending_model_view(self):
        model_line = self.make_model(
            self.project, "Studio test advanced item", model=ITEM
        )
        list_view = pending_view(model_line, "list")
        data = self.Editor.get_editor_data(ITEM, list_view.id, "list", self.project.id)
        self.assertIn("set_attribute", data["operations"])
        name = self.draft(self.project, list_view).xpath("/list/field")[0].get("name")
        self.op(
            self.project,
            list_view,
            type="set_attribute",
            target=named(name, "list"),
            attribute="widget",
            value="char",
        )
        self.assertEqual(
            self.draft(self.project, list_view)
            .xpath(named(name, "list"))[0]
            .get("widget"),
            "char",
        )

    def test_apply_revert(self):
        self.set_attr("type", "widget", "radio")
        self.set_attr("country_id", "domain", "[('code', '=', 'FR')]")
        self.set_attr("name", "groups", "base.group_system")
        self.project.action_apply()
        arch = self.form_view._get_combined_arch()
        self.assertEqual(arch.xpath(named("type"))[0].get("widget"), "radio")
        self.assertEqual(
            arch.xpath(named("country_id"))[0].get("domain"), "[('code', '=', 'FR')]"
        )
        self.assertEqual(
            arch.xpath(named("name"))[0].get("groups"), "base.group_system"
        )
        self.project.action_revert()
        arch = self.form_view._get_combined_arch()
        self.assertFalse(arch.xpath("//field[@widget or @domain or @groups]"))
        self.assertEqual(len(self.project.change_ids), 3)
