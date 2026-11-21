# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import StudioCase

MODULE = "studio_test_confirm"
ORDER = "x_studio_test_order"
LEFT = "//group[@name='studio_left']"


@tagged("post_install", "-at_install")
class TestConfirm(StudioCase):
    """What Revert, and an Apply that removes data, take out of the
    database: a report the user confirms by its digest."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.order = self.make_model(self.project, "Studio test order", model=ORDER)
        self.admin = self.env.ref("base.user_admin")

    def as_admin(self):
        """The project as a Settings administrator edits it: not the
        superuser, who is not asked to confirm."""
        return self.project.with_user(self.admin)

    def fill(self):
        """An applied project with records, values and a group member."""
        app = self.project.app_ids[:1]
        group = self.project._studio_save_group(
            {"name": "Studio test clerk", "app_id": app.id}
        )
        self.project.action_apply()
        form = self.order._studio_views()["form"]
        for view, target, position, field in (
            (form, LEFT, "inside", {"ttype": "char", "field_description": "Code"}),
            (
                self.form,
                "//field[@name='vat']",
                "after",
                {"ttype": "char", "field_description": "Studio nickname"},
            ),
            (
                form,
                LEFT,
                "inside",
                {
                    "ttype": "many2many",
                    "field_description": "Contacts",
                    "relation": "res.partner",
                },
            ),
        ):
            self.op(
                self.project,
                view,
                type="add_field",
                target=target,
                position=position,
                field=field,
            )
        self.project.action_apply()
        partner = self.env["res.partner"].create(
            {"name": "Studio test", "x_studio_nickname": "Nick"}
        )
        Order = self.env[ORDER]
        Order.create(
            {"x_name": "First", "x_code": "A", "x_contacts": [(4, partner.id)]}
        )
        Order.create({"x_name": "Second"})
        member = new_test_user(
            self.env, login="studio_test_confirm_member", groups="base.group_user"
        )
        member.groups_id = [(4, group._studio_group_record().id)]
        return group

    def test_revert_report(self):
        self.fill()
        answer = self.project._studio_revert_report()
        report = answer["report"]
        self.assertFalse(answer["refused"])
        self.assertEqual(
            report["models"],
            [{"model": ORDER, "name": "Studio test order", "count": 2}],
        )
        fields_info = {(f["model"], f["name"]): f["filled"] for f in report["fields"]}
        self.assertEqual(fields_info[("res.partner", "x_studio_nickname")], 1)
        # The fields of a removed model go with it.
        self.assertNotIn((ORDER, "x_code"), fields_info)
        self.assertEqual(report["groups"][0]["users"], 1)
        self.assertEqual(len(report["categories"]), 1)
        self.assertEqual(
            report["tables"], [f"x_{MODULE}_studio_test_order_contacts_rel"]
        )
        self.assertEqual(
            sorted(v["kind"] for v in report["views"]),
            ["default", "default", "default", "inherited", "inherited"],
        )
        self.assertEqual(report["changes_removed"], 2)
        self.assertEqual(
            self.Editor.get_revert_report(self.project.id)["digest"], answer["digest"]
        )
        # A Settings administrator confirms what it removes.
        project = self.as_admin()
        with self.assertRaisesRegex(UserError, "review it again"):
            with self.env.cr.savepoint():
                project.action_revert()
        with self.assertRaisesRegex(UserError, "review it again"):
            with self.env.cr.savepoint():
                project.action_revert(digest="0" * 64)
        self.env["x_studio_test_order"].create({"x_name": "Third"})
        with self.assertRaisesRegex(UserError, "review it again"):
            with self.env.cr.savepoint():
                project.action_revert(digest=answer["digest"])
        digest = self.project._studio_revert_report()["digest"]
        project.action_revert(digest=digest)
        self.assertNotIn(ORDER, self.env)
        self.assertFalse(self.project.created_group_ids)

    def test_revert_from_the_project_form(self):
        self.fill()
        action = self.as_admin().action_revert_wizard()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual((wizard.mode, wizard.refused), ("revert", False))
        html = str(wizard.report_html)
        for text in (ORDER, "x_studio_nickname", "Studio test clerk"):
            self.assertIn(text, html)
        wizard.with_user(self.admin).action_confirm()
        self.assertNotIn(ORDER, self.env)
        self.assertFalse(self.module_records(MODULE))

    def test_revert_refused_while_the_module_owns_a_model(self):
        self.project.action_apply()
        self.env.cr.execute(
            "UPDATE ir_model SET state = 'base' WHERE model = %s", [ORDER]
        )
        self.env["ir.model"].invalidate_model(["state"])
        answer = self.project._studio_revert_report()
        self.assertIn(MODULE, answer["refused"])
        action = self.project.action_revert_wizard()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertIn(MODULE, wizard.refused)
        self.env.cr.execute(
            "UPDATE ir_model SET state = 'manual' WHERE model = %s", [ORDER]
        )
        self.env["ir.model"].invalidate_model(["state"])

    def test_apply_report(self):
        self.project.action_apply()
        # Nothing with data leaves: Apply is not asked to confirm.
        self.project._studio_save_app({"name": "Studio test spare"})
        answer = self.project._studio_apply_report()
        self.assertFalse(answer["confirm"])
        self.assertIs(self.as_admin().action_apply_wizard(), True)
        group = self.fill()
        # The model and the group leave with their records and member.
        self.project._studio_remove_group(group)
        self.project._studio_remove_model(self.order)
        answer = self.project._studio_apply_report()
        self.assertTrue(answer["confirm"])
        report = answer["report"]
        self.assertEqual(report["models"][0]["count"], 2)
        self.assertEqual(report["groups"][0]["users"], 1)
        self.assertEqual(
            self.Editor.get_apply_report(self.project.id)["digest"], answer["digest"]
        )
        project = self.as_admin()
        with self.assertRaisesRegex(UserError, "confirm"):
            with self.env.cr.savepoint():
                project.action_apply()
        action = project.action_apply_wizard()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(wizard.mode, "apply")
        self.assertEqual(wizard.digest, answer["digest"])
        # The editor of the administrator opens the project first.
        editor = self.Editor.with_user(self.admin)
        editor.get_editor_data("res.partner", False, "form", self.project.id)
        data = editor.project_action(
            self.project.id,
            "action_apply",
            "res.partner",
            False,
            "form",
            self.project.draft_revision,
            digest=answer["digest"],
        )
        self.assertEqual(data["project"]["state"], "applied")
        self.assertNotIn(ORDER, self.env)

    def test_revert_refused_while_the_module_is_installed(self):
        """Installed, the generated module owns what the project applied,
        models or not (groups, categories, access rights): only its
        uninstall removes it. Revert refuses, its report and its call
        alike."""
        project = self.make_project("studio_test_confirm_groups")
        app = project._studio_save_app({"name": "Studio test groups app"})
        group = project._studio_save_group(
            {"name": "Studio test reader", "app_id": app.id}
        )
        project._studio_set_access(
            [
                {
                    "model": "res.partner.category",
                    "group_line_id": group.id,
                    "perm_read": True,
                }
            ]
        )
        project.action_apply()
        self.assertFalse(project._studio_revert_report()["refused"])
        self.env["ir.module.module"].create(
            {"name": "studio_test_confirm_groups", "state": "installed"}
        )
        answer = project._studio_revert_report()
        self.assertIn("studio_test_confirm_groups", answer["refused"])
        with self.assertRaisesRegex(UserError, "Uninstall the module"):
            with self.env.cr.savepoint():
                project.with_user(self.admin).action_revert(digest=answer["digest"])
        self.assertTrue(project.created_group_ids.exists())

    def test_revert_refused_by_records_made_by_hand(self):
        """The database deletes in cascade with a model the server actions,
        the scheduled actions, the default values... on it: made by hand,
        they refuse Revert, named; its filters go with it."""
        self.project.action_apply()
        model = self.env["ir.model"]._get(ORDER)
        action = self.env["ir.actions.server"].create(
            {
                "name": "Studio test action",
                "model_id": model.id,
                "state": "code",
                "code": "pass",
            }
        )
        cron = self.env["ir.cron"].create(
            {
                "name": "Studio test cron",
                "model_id": model.id,
                "state": "code",
                "code": "pass",
                "interval_type": "days",
            }
        )
        default = self.env["ir.default"].set(ORDER, "x_name", "Studio default")
        self.assertTrue(default)
        self.env["ir.filters"].create(
            {"name": "Studio test filter", "model_id": ORDER, "domain": "[]"}
        )
        answer = self.project._studio_revert_report()
        for text in ("Studio test action", "Studio test cron", "Default Values"):
            self.assertIn(text, answer["refused"])
        names = [item["name"] for item in answer["report"]["others"]]
        self.assertTrue(any("Studio test filter" in name for name in names))
        with self.assertRaisesRegex(UserError, "Studio test cron"):
            with self.env.cr.savepoint():
                self.project.action_revert()
        # A scheduled action is a server action too, which stays behind it.
        server = cron.ir_actions_server_id
        cron.unlink()
        (server | action).unlink()
        self.env["ir.default"].search([("field_id.model", "=", ORDER)]).unlink()
        self.assertFalse(self.project._studio_revert_report()["refused"])
        self.project.action_revert()
        self.assertNotIn(ORDER, self.env)
        self.assertFalse(self.env["ir.filters"].search([("model_id", "=", ORDER)]))

    def test_apply_and_revert_withdraw_the_approval(self):
        """The approval of a real preview is for the models not created yet:
        Apply creates them, a Revert puts them back as a draft, which needs
        a new approval."""
        self.project.action_approve()
        self.assertTrue(self.project.approved)
        self.project.action_apply()
        self.assertFalse(self.project.approved_snapshot or self.project.approved_uid)
        self.project.action_revert()
        self.assertFalse(self.project.approved)
        self.assertFalse(self.project.approved_date)

    def test_revert_leaves_no_external_id_of_the_inheritance(self):
        """A custom model with a chatter gets from Odoo the external ids
        « False.model_inherit__<model>__mail_thread »...: Revert removes them
        with the model."""
        if not self.mail_available():
            self.skipTest("mail is not installed")
        self.project._studio_remove_model(self.order)
        self.make_model(self.project, "Studio test chat", model=ORDER, chatter=True)
        self.project.action_apply()
        Data = self.env["ir.model.data"]
        domain = [
            ("module", "=", "False"),
            ("model", "=", "ir.model.inherit"),
            ("name", "=like", f"model_inherit__{ORDER}__%"),
        ]
        self.assertTrue(Data.search(domain))
        self.project.action_revert()
        self.assertFalse(Data.search(domain))
