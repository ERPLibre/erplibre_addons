# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import StudioCase

MODULE = "studio_test_integrity"
BOX = "x_studio_test_box"
JAR = "x_studio_test_jar"


@tagged("post_install", "-at_install")
class TestIntegrity(StudioCase):
    """What leaves the database with a project leaves it consistent: the
    record rules and the changes that name a removed field, the rights of
    another project on a removed model, the external ids after a rename,
    Discard once a line of the snapshot is gone."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.other = self.make_project(
            "studio_test_integrity_other", name="Studio test other"
        )
        self.user_group = self.env.ref("base.group_user")
        self.system = self.env.ref("base.group_system")
        self.employee = new_test_user(
            self.env, login="studio_test_integrity_user", groups="base.group_user"
        )

    def add_field(self, project, label, view=None, **field):
        """A new field on the partner form, or in the left group of the
        default form ``view``; its name."""
        target = ("//field[@name='vat']", "after")
        if view:
            target = ("//group[@name='studio_left']", "inside")
        change = self.op(
            project,
            view or self.form,
            type="add_field",
            target=target[0],
            position=target[1],
            field={"ttype": "char", "field_description": label, **field},
        )
        return change.field_name

    def show_in_list(self, project, name):
        return self.op(
            project,
            self.list,
            type="add_existing_field",
            target="//field[@name='email']",
            position="after",
            field_name=name,
        )

    def save_rule(self, project, domain, groups=None, model="res.partner"):
        return project._studio_save_rule(
            {
                "name": "Studio test rule",
                "model": model,
                "domain": domain,
                "group_ids": (groups if groups is not None else self.user_group).ids,
                "perm_read": True,
            }
        )

    def partner_count(self):
        return self.env["res.partner"].with_user(self.employee).search_count([])

    # ── fields named by a rule or a change ──────────────────────────────

    def test_a_rule_naming_a_removed_field_refuses_apply(self):
        name = self.add_field(self.project, "Studio code")
        self.project.action_apply()
        rule = self.save_rule(
            self.project,
            f"['|', ('{name}', '=', False), ('{name}', '!=', 'secret')]",
        )
        self.project.action_apply()
        self.op(
            self.project,
            self.form,
            type="remove",
            target=f"//field[@name='{name}']",
        )
        with self.assertRaisesRegex(UserError, "record rule Studio test rule"):
            with self.env.cr.savepoint():
                self.project.action_apply()
        self.assertIn(name, self.env["res.partner"]._fields)
        self.project._studio_remove_rule(rule)
        self.project.action_apply()
        self.assertNotIn(name, self.env["res.partner"]._fields)
        self.assertTrue(self.partner_count())

    def test_a_rule_through_a_relation_is_seen(self):
        """A rule of another model reaches the field through a many2one."""
        name = self.add_field(self.project, "Studio code")
        self.project.action_apply()
        user_model = self.env["ir.model"]._get("res.users")
        self.env["ir.rule"].create(
            {
                "name": "Studio test hand-made rule",
                "model_id": user_model.id,
                "domain_force": f"[('partner_id.{name}', '!=', 'secret')]",
            }
        )
        with self.assertRaisesRegex(UserError, "Studio test hand-made rule"):
            with self.env.cr.savepoint():
                self.project.action_revert()

    def test_a_global_rule_of_another_project_refuses_revert(self):
        name = self.add_field(self.project, "Studio shared")
        self.project.action_apply()
        self.save_rule(
            self.other, f"[('{name}', '!=', 'secret')]", groups=self.env["res.groups"]
        )
        self.other.action_apply()
        with self.assertRaisesRegex(
            UserError, r"Studio test rule \(Studio test other\)"
        ):
            with self.env.cr.savepoint():
                self.project.action_revert()
        self.assertTrue(self.partner_count())
        self.other.action_revert()
        self.project.action_revert()
        self.assertNotIn(name, self.env["res.partner"]._fields)

    def test_the_draft_of_another_project_refuses_revert(self):
        self.make_model(self.project, "Studio test box", model=BOX)
        self.project.action_apply()
        name = self.add_field(
            self.project, "Studio box", ttype="many2one", relation=BOX
        )
        self.project.action_apply()
        self.show_in_list(self.other, name)
        with self.assertRaisesRegex(UserError, "project Studio test other"):
            with self.env.cr.savepoint():
                self.project.action_revert()
        self.other.change_ids.unlink()
        self.project.action_revert()
        self.assertNotIn(BOX, self.env)

    def test_removing_a_model_takes_the_changes_of_its_fields(self):
        line = self.make_model(self.project, "Studio test box", model=BOX)
        self.project.action_apply()
        name = self.add_field(
            self.project, "Studio box", ttype="many2one", relation=BOX
        )
        self.project.action_apply()
        self.show_in_list(self.project, name)
        kept = self.op(
            self.project,
            self.list,
            type="relabel",
            target="//field[@name='phone']",
            value="Studio phone",
        )
        self.project.action_apply()
        self.project._studio_remove_model(line)
        self.assertEqual(self.project.change_ids, kept)
        arch, errors = self.project._draft_arch(self.list)
        self.assertFalse(errors)
        self.assertFalse(arch.xpath(f"//field[@name='{name}']"))
        self.project.action_apply()
        self.assertNotIn(BOX, self.env)
        self.assertNotIn(name, self.env["res.partner"]._fields)

    # ── rights of another project on a removed model ────────────────────

    def test_rights_another_project_applied_refuse_the_removal(self):
        self.make_model(self.project, "Studio test jar", model=JAR)
        self.project.action_apply()
        self.other._studio_set_access(
            [{"model": JAR, "group_id": self.system.id, "perm_read": True}]
        )
        self.save_rule(self.other, "[]", groups=self.system, model=JAR)
        self.other.action_apply()
        self.assertEqual(
            (len(self.other.created_access_ids), len(self.other.created_rule_ids)),
            (1, 1),
        )
        # Out of its draft, still in the database.
        self.other._studio_set_access([])
        self.other.rule_line_ids.unlink()
        with self.assertRaisesRegex(UserError, r"\(Studio test other\)"):
            with self.env.cr.savepoint():
                self.project.action_revert()
        self.assertEqual(len(self.other.created_access_ids), 1)
        self.other.action_apply()
        self.assertFalse(self.other.created_access_ids)
        self.assertFalse(self.other.created_rule_ids)
        self.project.action_revert()
        self.assertNotIn(JAR, self.env)
        self.assertFalse(self.module_records("studio_test_integrity_other"))

    # ── Discard ─────────────────────────────────────────────────────────

    def test_discard_leaves_out_what_left_the_database(self):
        hand = self.env["ir.model"].create(
            {"name": "Studio test hand", "model": "x_studio_test_hand"}
        )
        group = self.env["res.groups"].create({"name": "Studio test group"})
        self.env["ir.model.data"].create(
            {
                "module": "studio_test_data",
                "name": "group_studio_test",
                "model": "res.groups",
                "res_id": group.id,
            }
        )
        view = self.make_view(
            "list",
            "<list><field name='name'/><field name='email'/></list>",
            xml_id="studio_test_data.view_partner_list",
        )
        self.op(
            self.project,
            view,
            type="relabel",
            target="//field[@name='email']",
            value="Studio mail",
        )
        self.project._studio_set_access(
            [
                {
                    "model": "x_studio_test_hand",
                    "group_id": self.system.id,
                    "perm_read": True,
                }
            ]
        )
        self.save_rule(self.project, "[]", groups=group)
        self.project.action_apply()
        # Gone since the Apply: the view, the model and the group (once no
        # rule of the database names it).
        view.with_context(_force_unlink=True).unlink()
        hand.unlink()
        self.project.created_rule_ids.unlink()
        group.unlink()
        self.project.app_name = "Studio test draft"
        result = self.project.action_discard()
        message = result["params"]["message"]
        for text in ("x_studio_test_hand", "Studio test rule", "res.partner"):
            self.assertIn(text, message)
        self.assertFalse(self.project.change_ids)
        self.assertFalse(self.project.access_line_ids)
        self.assertFalse(self.project.rule_line_ids)
        self.assertFalse(self.project.app_name)

    # ── external ids ────────────────────────────────────────────────────

    def test_rename_keeps_the_inherited_views_of_the_new_models(self):
        line = self.make_model(self.project, "Studio test jar", model=JAR)
        self.project.action_apply()
        self.add_field(self.project, "Studio size", view=line._studio_views()["form"])
        self.project.action_apply()
        studio_view = self.project.studio_view_ids
        self.assertEqual(len(studio_view), 1)
        self.project.module_name = "studio_test_integrity_renamed"
        name = f"studio_test_integrity_renamed_view_{JAR}_form_studio"
        self.assertEqual(
            self.module_records("studio_test_integrity_renamed", "ir.ui.view")
            .filtered(lambda d: d.res_id == studio_view.id)
            .name,
            name,
        )
        self.assertEqual(studio_view.name, f"studio_test_integrity_renamed.{name}")
        self.env.invalidate_all()
        self.project.action_apply()
        self.assertEqual(self.project.studio_view_ids, studio_view)

    def test_apply_marks_its_external_ids_noupdate(self):
        """An upgrade of the generated module keeps what Apply made since
        its last generation."""
        self.make_model(self.project, "Studio test jar", model=JAR)
        self.add_field(self.project, "Studio code")
        self.project.action_apply()
        data = self.module_records(MODULE)
        self.assertTrue(data)
        self.assertEqual(set(data.mapped("noupdate")), {True})

    def test_external_id_names_come_from_the_server(self):
        Rule = self.env["erplibre.studio.rule"]
        rule = Rule.create(
            {
                "project_id": self.project.id,
                "name": "Studio test rule",
                "model": "res.partner",
                "domain_force": "[]",
                "xml_name": 'rule_a"b',
            }
        )
        self.assertEqual(rule.xml_name, "rule_res_partner_1")
        rule.write({"xml_name": "rule_c'd"})
        self.assertEqual(rule.xml_name, "rule_res_partner_1")
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            rule._server_writing().write({"xml_name": 'rule_a"b'})
        access = self.env["erplibre.studio.access"].create(
            {
                "project_id": self.project.id,
                "model": "res.partner.category",
                "group_id": self.system.id,
                "perm_read": True,
                "xml_name": "access_forged",
            }
        )
        self.assertEqual(
            access.xml_name, "access_res_partner_category_base_group_system"
        )
        access.write({"xml_name": "access_forged"})
        self.assertEqual(
            access.xml_name, "access_res_partner_category_base_group_system"
        )

    def test_a_new_model_needs_an_access_right(self):
        self.make_model(self.project, "Studio test jar", model=JAR)
        self.project._studio_set_access([])
        with self.assertRaisesRegex(UserError, JAR):
            with self.env.cr.savepoint():
                self.project.action_apply()
        self.assertNotIn(JAR, self.env)

    # ── uninstall ───────────────────────────────────────────────────────

    def test_uninstall_refused_while_a_project_is_applied(self):
        self.make_model(self.project, "Studio test jar", model=JAR)
        self.project.action_apply()
        module = self.env["ir.module.module"].search([("name", "=", "erplibre_studio")])
        self.assertEqual(self.Project._studio_applied(), self.project)
        with self.assertRaisesRegex(UserError, "Studio test"):
            with self.env.cr.savepoint():
                module.button_uninstall()
        self.assertEqual(module.state, "installed")
        self.project.action_revert()
        self.assertFalse(self.Project._studio_applied())
