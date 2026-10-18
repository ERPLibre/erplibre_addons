# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.addons.base.models.ir_module import Module
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import StudioCase

MODULE = "studio_test_uninstalled"
GADGET = "x_studio_test_gadget"


@tagged("post_install", "-at_install")
class TestUninstall(StudioCase):
    """The uninstall wizard of a module a project generated: the report of
    what it deletes, and « I understand » before it uninstalls; then the
    project is a draft again."""

    def bind(self, record, name, module=MODULE):
        self.env["ir.model.data"].create(
            {"module": module, "name": name, "model": record._name, "res_id": record.id}
        )
        return record

    def make_module(self):
        """An installed module made for the test, owning a model with two
        records, a field with a value on the contacts, a menu and a group
        with a member."""
        module = self.env["ir.module.module"].create(
            {"name": MODULE, "state": "installed", "shortdesc": "Studio test module"}
        )
        model = self.env["ir.model"].create(
            {"name": "Studio test gadget", "model": GADGET}
        )
        self.bind(model, f"model_{GADGET}")
        self.env[GADGET].create([{"x_name": "First"}, {"x_name": "Second"}])
        field = self.env["ir.model.fields"].create(
            {
                "name": "x_studio_test_gadget_code",
                "model": "res.partner",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "ttype": "char",
                "field_description": "Studio test gadget code",
                "state": "manual",
            }
        )
        self.bind(field, "field_res_partner_x_studio_test_gadget_code")
        self.env["res.partner"].create(
            {"name": "Studio test", "x_studio_test_gadget_code": "G"}
        )
        self.bind(
            self.env["ir.ui.menu"].create({"name": "Studio test gadgets"}), "menu"
        )
        group = self.bind(
            self.env["res.groups"].create({"name": "Studio test gadget users"}),
            "group_gadget",
        )
        member = new_test_user(
            self.env, login="studio_test_uninstall_member", groups="base.group_user"
        )
        member.groups_id = [(4, group.id)]
        return module

    def test_the_wizard_reports_and_asks(self):
        project = self.make_project(MODULE)
        module = self.make_module()
        report = module._studio_uninstall_report({MODULE})
        self.assertEqual(
            report["models"],
            [{"model": GADGET, "name": "Studio test gadget", "count": 2}],
        )
        self.assertEqual(
            [(f["name"], f["filled"]) for f in report["fields"]],
            [("x_studio_test_gadget_code", 1)],
        )
        self.assertEqual(report["menus"], [{"name": "Studio test gadgets"}])
        self.assertEqual(report["groups"][0]["users"], 1)
        wizard = self.env["base.module.uninstall"].create({"module_id": module.id})
        self.assertEqual(wizard.studio_module_ids, module)
        html = str(wizard.studio_report)
        for text in (GADGET, "x_studio_test_gadget_code", "Studio test gadget users"):
            self.assertIn(text, html)
        with patch.object(Module, "button_immediate_uninstall", lambda self: "done"):
            with self.assertRaisesRegex(UserError, "I understand"):
                wizard.action_uninstall()
            wizard.studio_understood = True
            self.assertEqual(wizard.action_uninstall(), "done")
            # Another module: Odoo's wizard as it is.
            other = self.env.ref("base.module_erplibre_studio")
            plain = self.env["base.module.uninstall"].create({"module_id": other.id})
            self.assertFalse(plain.studio_module_ids)
            self.assertEqual(plain.action_uninstall(), "done")
        self.assertTrue(project.exists())

    def test_the_project_is_a_draft_again(self):
        project = self.make_project("studio_test_reset")
        line = self.make_model(
            project, "Studio test widget", model="x_studio_test_widget"
        )
        project.action_apply()
        self.assertEqual(project.state, "applied")
        module = self.env["ir.module.module"].create(
            {"name": "studio_test_reset", "state": "installed"}
        )
        with patch.object(Module, "module_uninstall", lambda self: True):
            module.module_uninstall()
        self.assertEqual(project.state, "draft")
        self.assertFalse(project.applied_snapshot or project.created_model_ids)
        self.assertEqual(project.new_model_ids, line)
        self.assertEqual(len(project.access_line_ids), 1)

    def test_the_wizard_names_what_other_projects_lose(self):
        """The models of the module take with them what other projects
        applied on them: the report lists it, and the wizard refuses while
        another project applied it."""
        self.make_project(MODULE)
        module = self.make_module()
        other = self.make_project(
            "studio_test_uninstall_other", name="Studio test other"
        )
        change = self.op(
            other,
            self.form,
            type="add_field",
            target="//field[@name='vat']",
            position="after",
            field={
                "ttype": "many2one",
                "field_description": "Studio gadget",
                "relation": GADGET,
            },
        )
        other._studio_set_access(
            [
                {
                    "model": GADGET,
                    "group_id": self.env.ref("base.group_system").id,
                    "perm_read": True,
                }
            ]
        )
        other.action_apply()
        name = change.field_name
        report = module._studio_uninstall_report({MODULE})
        self.assertIn(name, [f["name"] for f in report["fields"]])
        self.assertIn(
            other.created_access_ids.name, [a["name"] for a in report["access"]]
        )
        refusal = module._studio_uninstall_refusal({MODULE})
        self.assertIn("Studio test other", refusal)
        self.assertIn(f"res.partner.{name}", refusal)
        wizard = self.env["base.module.uninstall"].create({"module_id": module.id})
        self.assertEqual(wizard.studio_refused, refusal)
        wizard.studio_understood = True
        with patch.object(Module, "button_immediate_uninstall", lambda self: "done"):
            with self.assertRaisesRegex(UserError, "Studio test other"):
                wizard.action_uninstall()
        other.action_revert()
        self.assertFalse(module._studio_uninstall_refusal({MODULE}))

    def test_the_uninstall_leaves_nothing_behind(self):
        """What Odoo keeps once the models of a generated module are gone:
        their filters, the external ids of the inheritance of a custom
        model, the rows of the constraints the uninstall dropped with the
        columns. The uninstall of a generated module removes them."""
        self.make_project(MODULE)
        module = self.make_module()
        self.env["ir.filters"].create(
            {"name": "Studio test gadget filter", "model_id": GADGET, "domain": "[]"}
        )
        Data = self.env["ir.model.data"]
        dangling = Data.create(
            {
                "module": "False",
                "name": f"model_inherit__{GADGET}__mail_thread",
                "model": "ir.model.inherit",
                "res_id": 2147483000,
            }
        )
        # The rows as Odoo writes them when it reflects a constraint (SQL).
        self.env.cr.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'res_partner'::regclass "
            "AND contype = 'f' LIMIT 1"
        )
        existing = self.env.cr.fetchone()[0]
        ids = []
        for name in ("res_partner_x_studio_test_gone_fkey", existing):
            self.env.cr.execute(
                "INSERT INTO ir_model_constraint (name, model, module, type) "
                "VALUES (%s, %s, %s, 'f') RETURNING id",
                [name, self.env["ir.model"]._get_id("res.partner"), module.id],
            )
            ids.append(self.env.cr.fetchone()[0])
        Constraint = self.env["ir.model.constraint"]
        gone, kept = Constraint.browse(ids[0]), Constraint.browse(ids[1])
        with patch.object(Module, "module_uninstall", lambda self: True):
            module.module_uninstall()
        self.assertFalse(self.env["ir.filters"].search([("model_id", "=", GADGET)]))
        self.assertFalse(dangling.exists())
        self.assertFalse(gone.exists())
        self.assertTrue(kept.exists())
