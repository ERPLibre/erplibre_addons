# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import StudioCase


@tagged("post_install", "-at_install")
class TestProject(StudioCase):
    def test_module_name_validation(self):
        for name in (
            "Studio",
            "1studio",
            "studio-partner",
            "studio partner",
            "",
        ):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.make_project(name)
        # A module of the addons path, installed or not.
        for name in ("base", "erplibre_studio", "erplibre_studio_generate"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.make_project(name)
        project = self.make_project("studio_test_unique")
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self.make_project("studio_test_unique")
        self.assertEqual(project.state, "draft")
        self.assertEqual(project.user_id, self.env.user)

    def test_list_operations(self):
        project = self.make_project()
        before = self.columns(self.draft(project, self.list))
        self.assertIn("email", before)
        self.op(
            project,
            self.list,
            type="move",
            source="//field[@name='email']",
            target="//field[@name='complete_name']",
            position="before",
        )
        after = self.columns(self.draft(project, self.list))
        self.assertEqual(after[0], "email")
        self.assertEqual(sorted(after), sorted(before))
        # A second relabel of the same node updates the first change.
        for label in ("Mail", "E-mail"):
            self.op(
                project,
                self.list,
                type="relabel",
                target="//field[@name='email']",
                value=label,
            )
        relabels = project.change_ids.filtered(lambda c: c.change_type == "relabel")
        self.assertEqual(len(relabels), 1)
        arch = self.draft(project, self.list)
        self.assertEqual(
            arch.xpath("//field[@name='email']")[0].get("string"), "E-mail"
        )
        self.op(
            project,
            self.list,
            type="optional",
            target="//field[@name='email']",
            value="hide",
        )
        self.op(
            project,
            self.list,
            type="hide",
            target="//field[@name='city']",
            value=True,
        )
        arch = self.draft(project, self.list)
        self.assertEqual(
            arch.xpath("//field[@name='email']")[0].get("optional"), "hide"
        )
        self.assertEqual(
            arch.xpath("//field[@name='city']")[0].get("column_invisible"),
            "True",
        )
        self.assertEqual(project.draft_revision, 5)
        project.action_undo(self.list)
        arch = self.draft(project, self.list)
        self.assertFalse(arch.xpath("//field[@name='city']")[0].get("column_invisible"))

    def test_new_field_and_removal(self):
        project = self.make_project()
        change = self.op(
            project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={
                "ttype": "selection",
                "field_description": "Partner level",
                "selection": [
                    ["gold", "Gold"],
                    ["silver", ""],
                    ["gold", "Twice"],
                ],
            },
        )
        self.assertEqual(change.field_name, "x_partner_level")
        payload = change._payload()
        self.assertEqual(
            payload["field"]["selection"],
            [["gold", "Gold"], ["silver", "silver"]],
        )
        arch = self.draft(project, self.form)
        node = arch.xpath("//field[@name='x_partner_level']")[0]
        self.assertEqual(node.getprevious().get("name"), "vat")
        # Relabelling a field of the project changes its definition.
        self.op(
            project,
            self.form,
            type="relabel",
            target="//field[@name='x_partner_level']",
            value="Level",
        )
        self.assertEqual(len(project.change_ids), 1)
        self.assertEqual(change._payload()["field"]["field_description"], "Level")
        self.op(
            project,
            self.form,
            type="hide",
            target="//field[@name='x_partner_level']",
            value=True,
        )
        self.assertEqual(len(project.change_ids), 2)
        # The same label again makes another name.
        other = self.op(
            project,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="before",
            field={"ttype": "char", "field_description": "Partner level"},
        )
        self.assertEqual(other.field_name, "x_partner_level_2")
        # Removing a field of the project removes the changes that name it.
        self.op(
            project,
            self.form,
            type="remove",
            target="//field[@name='x_partner_level']",
        )
        self.assertEqual(project.change_ids, other)
        # Removing a field of the base view hides it.
        self.op(
            project,
            self.form,
            type="remove",
            target="//field[@name='website']",
        )
        arch = self.draft(project, self.form)
        self.assertEqual(
            arch.xpath("//field[@name='website']")[0].get("invisible"), "True"
        )

    def test_operations_refused(self):
        project = self.make_project()
        cases = [
            {
                "type": "add_field",
                "target": "//field[@name='vat']",
                "field": {"ttype": "binary"},
            },
            {
                "type": "add_field",
                "target": "//field[@name='vat']",
                "field": {"ttype": "char", "name": "vat_bis"},
            },
            {
                "type": "add_field",
                "target": "//field[@name='vat']",
                "field": {"ttype": "many2one", "relation": "no.such.model"},
            },
            {
                "type": "add_field",
                "target": "//field[@name='vat']",
                "field": {"ttype": "monetary"},
            },
            {
                "type": "add_existing_field",
                "target": "//field[@name='vat']",
                "field_name": "email",
            },
            {
                "type": "add_existing_field",
                "target": "//field[@name='nothing']",
                "field_name": "ref",
            },
            {
                "type": "move",
                "source": "//sheet",
                "target": "//field[@name='vat']",
            },
            {
                "type": "move",
                "source": "//field[@name='vat']",
                "target": "/form",
                "position": "inside",
            },
            {
                "type": "optional",
                "target": "//field[@name='vat']",
                "value": "show",
            },
            {"type": "drop_table"},
        ]
        for operation in cases:
            with self.subTest(operation=operation), self.assertRaises(UserError):
                with self.env.cr.savepoint():
                    project._apply_operation(self.form, operation)
        with self.assertRaises(UserError):
            project._apply_operation(
                self.env.ref("base.view_res_partner_filter"), {"type": "hide"}
            )
        self.assertFalse(project.change_ids)

    def test_editor_payload(self):
        project_id = self.Editor.create_project("Studio test", "studio_test_payload")
        data = self.Editor.get_editor_data("res.partner", False, "list", project_id)
        self.assertEqual(data["view"]["id"], self.list.id)
        self.assertEqual(data["project"]["id"], project_id)
        self.assertEqual(data["blocks"]["tag"], "list")
        names = [b.get("name") for b in data["blocks"]["children"]]
        self.assertIn("email", names)
        palette = [f["name"] for f in data["palette"]]
        self.assertIn("ref", palette)
        self.assertNotIn("email", palette)
        email = next(b for b in data["blocks"]["children"] if b.get("name") == "email")
        data = self.Editor.apply_operation(
            project_id,
            "res.partner",
            data["view"]["id"],
            "list",
            {
                "type": "add_field",
                "target": email["path"],
                "position": "after",
                "field": {"ttype": "char", "field_description": "Nickname"},
            },
        )
        self.assertTrue(data["fields"]["x_nickname"]["pending"])
        names = [b.get("name") for b in data["blocks"]["children"]]
        self.assertEqual(names[names.index("email") + 1], "x_nickname")
        self.assertEqual(data["changes"][0]["type"], "add_field")
        self.assertEqual(data["project"]["preview_value"], f"{project_id}:1")
        data = self.Editor.project_action(
            project_id, "action_undo", "res.partner", False, "list"
        )
        self.assertFalse(data["changes"])
        with self.assertRaises(UserError):
            self.Editor.project_action(
                project_id, "unlink", "res.partner", False, "list"
            )
        action = self.Editor.action_customize("res.partner", False, "form")
        self.assertEqual(action["tag"], "erplibre_studio.editor")
        self.assertEqual(action["params"]["view_id"], self.form.id)

    def test_unchecking_restores_the_view_condition(self):
        """``function`` is hidden for a company: checking then unchecking
        « hidden » leaves no change and keeps the condition."""
        project = self.make_project()
        target = "//field[@name='function']"
        node = self.draft(project, self.form).xpath(target)[0]
        self.assertEqual(node.get("invisible"), "is_company")
        change = self.op(project, self.form, type="hide", target=target, value=True)
        self.assertEqual(change._payload()["value"], True)
        self.op(project, self.form, type="hide", target=target, value=False)
        self.assertFalse(project.change_ids)
        node = self.draft(project, self.form).xpath(target)[0]
        self.assertEqual(node.get("invisible"), "is_company")
        # Unchecking what the view never set constant: nothing to record.
        self.op(project, self.form, type="required", target=target, value=False)
        self.assertFalse(project.change_ids)
        # A constant True of the view is turned off by an explicit False.
        self.op(
            project, self.list, type="hide", target="//field[@name='city']", value=True
        )
        project.action_apply()
        other = self.make_project("studio_test_other_project")
        self.op(
            other, self.list, type="hide", target="//field[@name='city']", value=False
        )
        self.assertEqual(len(other.change_ids), 1)
        self.assertIn(">False<", other.change_ids.spec)

    def test_positional_toggle_only_replaces_the_last_change(self):
        project = self.make_project()
        sheet = self.draft(project, self.form).xpath("//sheet")[0]
        target = "/form/sheet/div[1]"
        self.assertIsNotNone(sheet.find("div"))
        self.op(project, self.form, type="hide", target=target, value=True)
        self.op(project, self.form, type="hide", target=target, value=False)
        self.assertFalse(project.change_ids)
        self.op(project, self.form, type="hide", target=target, value=True)
        self.op(
            project,
            self.form,
            type="relabel",
            target="//field[@name='email']",
            value="Mail",
        )
        # A later change may have moved what the position names: the
        # toggle is a change of its own.
        self.op(project, self.form, type="hide", target=target, value=False)
        self.assertEqual(
            project.change_ids.mapped("change_type"), ["hide", "relabel", "hide"]
        )

    def test_changes_written_outside_the_editor_make_a_draft(self):
        project = self.make_project()
        self.op(
            project,
            self.list,
            type="relabel",
            target="//field[@name='phone']",
            value="Telephone",
        )
        self.op(
            project,
            self.list,
            type="relabel",
            target="//field[@name='email']",
            value="Mail",
        )
        project.action_apply()
        self.assertEqual(project.state, "applied")
        revision = project.draft_revision
        project.change_ids[-1].write({"sequence": 1})
        self.assertEqual(project.state, "draft")
        self.assertEqual(project.draft_revision, revision + 1)
        project.action_apply()
        project.change_ids[0].unlink()
        self.assertEqual(project.state, "draft")
        # The project form shows the changes read-only.
        arch = etree.fromstring(
            self.env.ref("erplibre_studio.erplibre_studio_project_view_form").arch
        )
        node = arch.xpath("//field[@name='change_ids']")[0]
        self.assertEqual(node.get("readonly"), "1")
        self.assertFalse(node.xpath(".//field[@widget='handle']"))

    def test_managed_fields_are_not_writable(self):
        admin = new_test_user(
            self.env,
            login="erplibre_studio_forger",
            groups="base.group_user,base.group_system",
        )
        project = self.make_project().with_user(admin)
        forged = [
            {"state": "applied"},
            {"draft_revision": 0},
            {"applied_snapshot": "[]"},
            {"field_ids": [(5, 0, 0)]},
        ]
        for vals in forged:
            with self.subTest(vals=vals), self.assertRaises(UserError):
                project.write(vals)
        with self.assertRaises(UserError):
            self.Project.with_user(admin).create(
                {
                    "name": "Forged",
                    "module_name": "studio_test_forged",
                    "state": "applied",
                }
            )
        # The client cannot claim the internal context either.
        with self.assertRaises(UserError):
            project.with_context(erplibre_studio_internal=True).write(
                {"state": "applied"}
            )
        project.write({"name": "Renamed"})
        self.assertEqual(project.name, "Renamed")

    def test_editor_refuses_a_stale_revision(self):
        project = self.make_project()
        data = self.Editor.get_editor_data("res.partner", False, "list", project.id)
        revision = data["project"]["revision"]
        operation = {
            "type": "relabel",
            "target": "//field[@name='email']",
            "value": "Mail",
        }
        data = self.Editor.apply_operation(
            project.id, "res.partner", False, "list", operation, revision
        )
        self.assertEqual(data["project"]["revision"], revision + 1)
        for call in (
            lambda: self.Editor.apply_operation(
                project.id, "res.partner", False, "list", operation, revision
            ),
            lambda: self.Editor.project_action(
                project.id,
                "action_undo",
                "res.partner",
                False,
                "list",
                revision,
            ),
        ):
            with self.assertRaises(UserError):
                call()
        self.assertEqual(len(project.change_ids), 1)

    def test_editor_payload_without_a_project(self):
        project = self.make_project()
        data = self.Editor.get_editor_data("res.partner", False, "list")
        self.assertEqual(data["project"]["id"], project.id)
        data = self.Editor.get_editor_data(
            "res.partner", False, "list", False, pick_project=False
        )
        self.assertFalse(data["project"])
        self.assertFalse(data["changes"])
        self.assertIn(project.id, [p["id"] for p in data["projects"]])

    def test_arch_errors_in_the_user_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env["ir.module.module"].search(
            [("name", "=", "erplibre_studio")]
        )._update_translations(["fr_FR"])
        project = self.make_project().with_context(lang="fr_FR")
        with self.assertRaises(UserError) as caught:
            project._apply_operation(
                self.form,
                {"type": "relabel", "target": "/form/sheet/group[9]", "value": "A"},
            )
        self.assertEqual(
            str(caught.exception.args[0]), "Aucun nœud à /form/sheet/group[9]."
        )
