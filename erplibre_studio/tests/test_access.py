# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import StudioCase

MODEL = "x_studio_test_ticket"


@tagged("post_install", "-at_install")
class TestAccess(StudioCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_access")
        self.line = self.make_model(self.project, "Studio test ticket", model=MODEL)
        self.user_group = self.env.ref("base.group_user")
        self.system = self.env.ref("base.group_system")

    def row(self, model=MODEL, group=None, **perms):
        return {"model": model, "group_id": (group or self.user_group).id, **perms}

    def access(self, name):
        data = self.module_records("studio_test_access", "ir.model.access").filtered(
            lambda d: d.name == name
        )
        return self.env["ir.model.access"].browse(data.res_id).exists()

    def test_set_access_replaces_the_rows(self):
        self.assertEqual(
            [
                (a.model, a.group_id, a.perm_unlink)
                for a in self.project.access_line_ids
            ],
            [(MODEL, self.user_group, True)],
        )
        self.project._studio_set_access(
            [
                self.row(perm_read=True),
                self.row(group=self.system, perm_read=True, perm_write=True),
                self.row(
                    model="res.partner.category", perm_read=True, perm_create=True
                ),
                # No right: left out.
                self.row(model="res.partner"),
            ]
        )
        lines = self.project.access_line_ids
        self.assertEqual(len(lines), 3)
        own = lines.filtered(
            lambda a: a.model == MODEL and a.group_id == self.user_group
        )
        self.assertEqual(
            (own.perm_read, own.perm_write, own.perm_create, own.perm_unlink),
            (True, False, False, False),
        )
        self.assertEqual(own.xml_name, f"access_{MODEL}_base_group_user")
        self.assertEqual(
            lines.filtered(lambda a: a.model == "res.partner.category").xml_name,
            "access_res_partner_category_base_group_user",
        )
        self.project._studio_set_access([self.row(perm_read=True)])
        self.assertEqual(self.project.access_line_ids, own)

    def test_refused_rows(self):
        loose = self.env["res.groups"].create({"name": "Studio test loose group"})
        for row in (
            self.row(group=loose, perm_read=True),
            self.row(model="base.module.update", perm_read=True),
            self.row(model="ir.rule", perm_read=True),
            self.row(model="res.groups", perm_read=True),
            self.row(model="mail.thread", perm_read=True),
            self.row(model="x_studio_test_nowhere", perm_read=True),
        ):
            with self.subTest(row=row), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.project._studio_set_access([row])
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["erplibre.studio.access"].create(
                {
                    "project_id": self.project.id,
                    "model": "res.partner",
                    "group_id": self.system.id,
                }
            )

    def test_protected_models_and_share_groups(self):
        """The rights, the users, the companies, the settings and the
        technical records of the database take no row; a group of users
        outside the company (portal, public) only reads an existing model,
        and gets every right on a model of the project."""
        portal = self.env.ref("base.group_portal")
        public = self.env.ref("base.group_public")
        for model in (
            "res.users",
            "res.users.log",
            "res.company",
            "res.config.settings",
            "ir.config_parameter",
            "ir.ui.view",
            "ir.actions.server",
            "ir.model.data",
            "ir.module.module",
            "ir.cron",
        ):
            for group in (portal, public, self.user_group):
                row = self.row(model=model, group=group, perm_read=True)
                with self.subTest(model=model, group=group.name):
                    with self.assertRaises(ValidationError), self.env.cr.savepoint():
                        self.project._studio_set_access([row])
        for perm in ("perm_write", "perm_create", "perm_unlink"):
            for group in (portal, public):
                row = self.row(
                    model="res.partner", group=group, perm_read=True, **{perm: True}
                )
                with self.subTest(perm=perm, group=group.name):
                    with self.assertRaises(ValidationError), self.env.cr.savepoint():
                        self.project._studio_set_access([row])
        self.project._studio_set_access(
            [
                self.row(model="res.partner", group=portal, perm_read=True),
                self.row(
                    group=portal,
                    perm_read=True,
                    perm_write=True,
                    perm_create=True,
                    perm_unlink=True,
                ),
            ]
        )
        self.assertEqual(len(self.project.access_line_ids), 2)
        choices = self.Editor.get_studio_choices(self.project.id)["models"]
        names = [model for model, _name in choices]
        self.assertIn("res.partner", names)
        self.assertFalse(
            [n for n in names if n.startswith(("ir.", "res.users", "res.groups"))]
        )

    def test_apply_creates_updates_and_removes_the_rights(self):
        self.project._studio_set_access(
            [
                self.row(
                    perm_read=True, perm_write=True, perm_create=True, perm_unlink=True
                ),
                self.row(
                    model="res.partner.category",
                    group=self.system,
                    perm_read=True,
                    perm_write=True,
                ),
            ]
        )
        self.project.action_apply()
        own = self.access(f"access_{MODEL}_base_group_user")
        extended = self.access("access_res_partner_category_base_group_system")
        self.assertEqual(
            (own.model_id.model, own.group_id, own.name),
            (MODEL, self.user_group, f"access_{MODEL}_base_group_user"),
        )
        self.assertEqual(
            (
                extended.model_id.model,
                extended.group_id,
                extended.perm_write,
                extended.perm_create,
            ),
            ("res.partner.category", self.system, True, False),
        )
        self.assertEqual(self.project.created_access_ids, own | extended)
        # An internal user works on the records, a portal user does not.
        employee = new_test_user(
            self.env, login="studio_test_employee", groups="base.group_user"
        )
        portal = new_test_user(
            self.env, login="studio_test_portal", groups="base.group_portal"
        )
        record = self.env[MODEL].with_user(employee).create({"x_name": "Ticket"})
        self.assertEqual(record.with_user(employee).x_name, "Ticket")
        with self.assertRaises(AccessError):
            self.env[MODEL].with_user(portal).create({"x_name": "Refused"})
        # New rights: the same record, updated.
        self.project._studio_set_access(
            [
                self.row(perm_read=True),
                self.row(
                    model="res.partner.category",
                    group=self.system,
                    perm_read=True,
                    perm_write=True,
                ),
            ]
        )
        self.project.action_apply()
        self.assertEqual(self.access(f"access_{MODEL}_base_group_user"), own)
        self.assertEqual((own.perm_read, own.perm_create), (True, False))
        with self.assertRaises(AccessError):
            self.env[MODEL].with_user(employee).create({"x_name": "Refused"})
        # A removed row leaves the database.
        self.project._studio_set_access([self.row(perm_read=True)])
        self.project.action_apply()
        self.assertFalse(extended.exists())
        self.assertEqual(self.project.created_access_ids, own)
        self.project.action_revert()
        self.assertFalse(own.exists())
        self.assertFalse(self.module_records("studio_test_access"))

    def test_rights_on_an_existing_model_only(self):
        """A project that only gives rights on an existing model."""
        self.line.unlink()
        self.assertFalse(self.project.access_line_ids)
        self.project._studio_set_access(
            [self.row(model="res.partner.category", group=self.system, perm_read=True)]
        )
        self.assertEqual(self.project.item_count, 1)
        self.project.action_apply()
        self.assertEqual(self.project.state, "applied")
        self.assertTrue(self.access("access_res_partner_category_base_group_system"))
        self.assertFalse(self.project.created_model_ids)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.project.unlink()
        self.project.action_revert()
        self.assertFalse(self.module_records("studio_test_access"))
