# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import StudioCase

MODEL = "x_studio_test_note"
OWN = "[('create_uid', '=', user.id)]"


@tagged("post_install", "-at_install")
class TestRules(StudioCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("studio_test_rules")
        self.line = self.make_model(self.project, "Studio test note", model=MODEL)
        self.user_group = self.env.ref("base.group_user")

    def rule(self, **values):
        return self.project._studio_save_rule(
            {
                "name": "Studio test rule",
                "model": "res.partner",
                "domain": "[]",
                "group_ids": [self.user_group.id],
                "perm_read": True,
                **values,
            }
        )

    def test_refused_domains(self):
        for domain in (
            "[('name', '=',",
            "[('studio_test_nowhere', '=', 1)]",
            "[('name', 'studio_op', 1)]",
            "__import__('os').getcwd()",
            "[(''.__class__, '=', 1)]",
            "{'name': 1}",
            "[%s]" % ", ".join(["('id', '!=', 0)"] * 200),
        ):
            with self.subTest(domain=domain), self.assertRaises(UserError):
                with self.env.cr.savepoint():
                    self.rule(domain=domain)
        with self.assertRaisesRegex(UserError, "Studio test rule"):
            with self.env.cr.savepoint():
                self.rule(domain="[('studio_test_nowhere', '=', 1)]")
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.rule(perm_read=False)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.rule(name=" ")
        loose = self.env["res.groups"].create({"name": "Studio test loose group"})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.rule(group_ids=[loose.id])
        # A model not created yet: the shape of the terms only.
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.rule(model=MODEL, domain="['&', ('x_name', '=', 1)]")
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.rule(model=MODEL, domain="[('x_name', '=')]")

    def test_share_group_rules(self):
        """A rule of a group of users outside the company widens what they
        reach: refused on an existing model, accepted on a model of the
        project."""
        portal = self.env.ref("base.group_portal")
        with self.assertRaisesRegex(UserError, "outside"):
            with self.env.cr.savepoint():
                self.rule(domain="[(1, '=', 1)]", group_ids=[portal.id])
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.rule(group_ids=[portal.id, self.user_group.id])
        self.assertTrue(self.rule(model=MODEL, domain=OWN, group_ids=[portal.id]))
        self.assertTrue(self.rule(domain=OWN))

    def test_accepted_domain_and_external_id(self):
        rule = self.rule(domain=OWN)
        self.assertEqual(rule.xml_name, "rule_res_partner_1")
        second = self.rule(
            name="Second", domain="['|', ('active', '=', True), ('id', '<', 10)]"
        )
        self.assertEqual(second.xml_name, "rule_res_partner_2")
        rule.unlink()
        self.assertEqual(self.rule(name="Third").xml_name, "rule_res_partner_1")
        # Moved to another model: the external id of a new rule.
        second = self.project._studio_save_rule(
            {
                "id": second.id,
                "name": "Second",
                "model": MODEL,
                "domain": OWN,
                "perm_read": True,
            }
        )
        self.assertEqual(second.xml_name, f"rule_{MODEL}_1")
        result = self.Editor.check_rule_domain(self.project.id, "res.partner", OWN)
        self.assertTrue(result["ok"])
        self.assertIsInstance(result["count"], int)
        result = self.Editor.check_rule_domain(self.project.id, MODEL, OWN)
        self.assertEqual(result, {"ok": True, "count": False})
        result = self.Editor.check_rule_domain(
            self.project.id, "res.partner", "[('studio_test_nowhere', '=', 1)]"
        )
        self.assertFalse(result["ok"])
        self.assertIn("studio_test_nowhere", result["error"])

    def test_pending_model_rule_checked_at_apply(self):
        self.rule(
            name="Bad rule", model=MODEL, domain="[('x_studio_test_nowhere', '=', 1)]"
        )
        with self.assertRaisesRegex(UserError, "Bad rule"):
            with self.env.cr.savepoint():
                self.project.action_apply()
        self.env.cr.execute("SELECT count(*) FROM ir_model WHERE model = %s", [MODEL])
        self.assertEqual(self.env.cr.fetchone()[0], 0)
        self.assertFalse(self.module_records("studio_test_rules"))

    def test_apply_creates_the_rule_and_it_applies(self):
        rule = self.rule(name="Own notes", model=MODEL, domain=OWN)
        self.project.action_apply()
        data = self.module_records("studio_test_rules", "ir.rule")
        self.assertEqual(data.name, rule.xml_name)
        record = self.env["ir.rule"].browse(data.res_id)
        self.assertEqual(
            (record.name, record.model_id.model, record.domain_force, record.groups),
            ("Own notes", MODEL, OWN, self.user_group),
        )
        self.assertEqual(
            (record.perm_read, record.perm_write),
            (True, False),
        )
        self.assertEqual(self.project.created_rule_ids, record)
        first = new_test_user(
            self.env, login="studio_test_first", groups="base.group_user"
        )
        second = new_test_user(
            self.env, login="studio_test_second", groups="base.group_user"
        )
        Note = self.env[MODEL]
        mine = Note.with_user(first).create({"x_name": "First"})
        theirs = Note.with_user(second).create({"x_name": "Second"})
        self.assertEqual(Note.with_user(first).search([]), mine)
        self.assertEqual(Note.with_user(second).search([]), theirs)
        # Updated in place, then removed.
        self.project._studio_save_rule(
            {
                "id": rule.id,
                "name": "Own notes",
                "model": MODEL,
                "domain": OWN,
                "perm_read": True,
                "perm_write": True,
            }
        )
        self.project.action_apply()
        self.assertEqual(self.project.created_rule_ids, record)
        self.assertTrue(record.perm_write)
        self.assertFalse(record.groups)
        self.project._studio_remove_rule(rule)
        self.project.action_apply()
        self.assertFalse(record.exists())
        self.assertFalse(self.module_records("studio_test_rules", "ir.rule"))
        self.assertEqual(len(Note.with_user(first).search([])), 2)
