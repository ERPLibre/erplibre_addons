# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import StudioCase

MODULE = "studio_test_groups"
TICKET = "x_studio_test_ticket"
OWN = "[('create_uid', '=', user.id)]"


@tagged("post_install", "-at_install")
class TestGroups(StudioCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project(MODULE)
        self.app = self.project._studio_save_app({"name": "Studio test desk"})
        self.line = self.make_model(
            self.project,
            "Studio test ticket",
            model=TICKET,
            menu={"mode": "app", "app_id": self.app.id},
        )
        self.internal = self.env.ref("base.group_user")

    def ref(self, name, model):
        data = self.module_records(MODULE, model).filtered(lambda d: d.name == name)
        return self.env[model].browse(data.res_id).exists()

    def group(self, name, app=None, **values):
        return self.project._studio_save_group(
            {"name": name, "app_id": (app or self.app).id, **values}
        )

    def test_apply_creates_the_category_the_groups_and_their_rights(self):
        user = self.group("Studio test agent")
        self.assertEqual(user.xml_name, "group_studio_test_desk_studio_test_agent")
        self.assertEqual(user.implied_group_ids, self.internal)
        admin = self.group("Studio test manager", implied_line_ids=[user.id])
        self.project._studio_set_access(
            [
                {
                    "model": TICKET,
                    "group_id": self.internal.id,
                    "perm_read": True,
                },
                {
                    "model": TICKET,
                    "group_line_id": admin.id,
                    "perm_read": True,
                    "perm_write": True,
                    "perm_create": True,
                    "perm_unlink": True,
                },
            ]
        )
        self.project._studio_save_rule(
            {
                "name": "Studio test own tickets",
                "model": TICKET,
                "domain": OWN,
                "group_line_ids": [user.id],
                "perm_read": True,
            }
        )
        self.project.action_apply()
        category = self.ref("module_category_app", "ir.module.category")
        self.assertEqual(category.name, "Studio test desk")
        agent = self.ref(user.xml_name, "res.groups")
        manager = self.ref(admin.xml_name, "res.groups")
        self.assertEqual((agent.category_id, manager.category_id), (category, category))
        self.assertEqual(agent.implied_ids, self.internal)
        self.assertEqual(manager.implied_ids, agent | self.internal)
        self.assertEqual(self.project.created_group_ids, agent | manager)
        self.assertEqual(self.project.created_category_ids, category)
        access = self.ref(
            f"access_{TICKET}_group_studio_test_desk_studio_test_manager",
            "ir.model.access",
        )
        self.assertEqual((access.group_id, access.perm_unlink), (manager, True))
        rule = self.project.created_rule_ids
        self.assertEqual(rule.groups, agent)
        count = len(self.module_records(MODULE))
        self.project.action_apply()
        self.assertEqual(len(self.module_records(MODULE)), count)
        # A user given the manager group gets the agent group too.
        member = new_test_user(
            self.env, login="studio_test_groups_member", groups="base.group_user"
        )
        member.groups_id = [(4, manager.id)]
        self.assertTrue(member.has_group(f"{MODULE}.{user.xml_name}"))
        # A chain of groups is one selection of the user form.
        fields_info = self.env["res.users"].fields_get()
        selection = (
            f"sel_groups_{'_'.join(str(i) for i in sorted((agent | manager).ids))}"
        )
        self.assertIn(selection, fields_info)
        payload = self.Editor._project_payload(self.project)
        self.assertTrue(payload["apps"][0]["chain"])
        self.assertEqual(payload["groups"][1]["implied"], [[user.id, user.name]])
        self.assertEqual(
            payload["access"][1]["group_line"],
            [admin.id, "Studio test desk / Studio test manager"],
        )
        choices = self.Editor.get_studio_choices(self.project.id)
        own = [g for g in choices["groups"] if g.get("project")]
        self.assertEqual(
            [g["xml_id"] for g in own],
            [f"{MODULE}.{user.xml_name}", f"{MODULE}.{admin.xml_name}"],
        )
        self.assertNotIn(agent.id, [g["id"] for g in choices["groups"]])

    def test_groups_that_do_not_chain_are_checkboxes(self):
        other = self.project._studio_save_app({"name": "Studio test lab"})
        first = self.group("Studio test reader", app=other)
        second = self.group("Studio test writer", app=other)
        self.assertFalse(other._studio_chain())
        self.project.action_apply()
        fields_info = self.env["res.users"].fields_get()
        for line in first | second:
            group = line._studio_group_record()
            self.assertIn(f"in_group_{group.id}", fields_info)
        self.project._studio_save_group(
            {"id": second.id, "implied_line_ids": [first.id]}
        )
        self.assertTrue(other._studio_chain())

    def test_refused_groups(self):
        user = self.group("Studio test agent")
        admin = self.group("Studio test manager", implied_line_ids=[user.id])
        with self.assertRaisesRegex(ValidationError, "imply each other"):
            with self.env.cr.savepoint():
                self.project._studio_save_group(
                    {"id": user.id, "implied_line_ids": [admin.id]}
                )
        for xmlid in (
            "base.group_portal",
            "base.group_system",
            "base.group_erp_manager",
        ):
            with self.subTest(group=xmlid), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.group(
                        "Studio test wide", implied_group_ids=[self.env.ref(xmlid).id]
                    )
        loose = self.env["res.groups"].create({"name": "Studio test loose"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.group("Studio test loose line", implied_group_ids=[loose.id])
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.project._studio_save_group({"name": "Studio test without app"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.group("Studio test agent")
        # An app with groups is not removed.
        with self.assertRaisesRegex(UserError, "Studio test agent"):
            with self.env.cr.savepoint():
                self.project._studio_remove_app(self.app)

    def test_removal(self):
        user = self.group("Studio test agent")
        self.project._studio_set_access(
            [
                {"model": TICKET, "group_id": self.internal.id, "perm_read": True},
                {"model": TICKET, "group_line_id": user.id, "perm_read": True},
            ]
        )
        self.project.action_apply()
        agent = user._studio_group_record()
        foreign = self.env["res.groups"].create(
            {"name": "Studio test foreign", "implied_ids": [(4, agent.id)]}
        )
        self.project._studio_remove_group(user)
        self.assertEqual(len(self.project.access_line_ids), 1)
        with self.assertRaisesRegex(UserError, "Studio test foreign"):
            with self.env.cr.savepoint():
                self.project.action_apply()
        foreign.unlink()
        # The members do not keep the group from leaving; the report counts
        # them.
        member = new_test_user(
            self.env, login="studio_test_groups_member", groups="base.group_user"
        )
        member.groups_id = [(4, agent.id)]
        report = self.project._studio_apply_report()
        self.assertTrue(report["confirm"])
        self.assertEqual(report["report"]["groups"][0]["users"], 1)
        self.assertEqual(len(report["report"]["categories"]), 1)
        self.project.action_apply()
        self.assertFalse(agent.exists())
        self.assertFalse(self.project.created_group_ids)
        self.assertFalse(self.project.created_category_ids)
        self.assertNotIn(agent, member.groups_id)

    def test_discard_restores_the_groups(self):
        user = self.group("Studio test agent")
        self.group("Studio test manager", implied_line_ids=[user.id])
        self.project._studio_save_rule(
            {
                "name": "Studio test own tickets",
                "model": TICKET,
                "domain": OWN,
                "group_line_ids": [user.id],
                "perm_read": True,
            }
        )
        self.project.action_apply()
        snapshot = self.project.applied_snapshot
        xml_name = user.xml_name
        self.project._studio_remove_group(user)
        self.project.action_discard()
        self.assertEqual(self.project._current_snapshot(), snapshot)
        restored = self.project.group_line_ids.filtered(
            lambda g: g.name == "Studio test agent"
        )
        self.assertEqual(restored.xml_name, xml_name)
        manager = self.project.group_line_ids - restored
        self.assertEqual(manager.implied_line_ids, restored)
        self.assertEqual(self.project.rule_line_ids.group_line_ids, restored)
        self.assertEqual(self.project.state, "applied")

    def test_a_group_that_grants_the_settings_is_refused(self):
        """An existing group that implies the Settings, directly or through
        another group, would grant them to the members of the project
        group."""
        system = self.env.ref("base.group_system")
        middle = self.bind_group(
            self.env["res.groups"].create({"name": "Studio test middle"}),
            "studio_test_invented",
            "group_middle",
        )
        back_office = self.bind_group(
            self.env["res.groups"].create(
                {"name": "Studio test back office", "implied_ids": [(4, middle.id)]}
            ),
            "studio_test_invented",
            "group_back_office",
        )
        clerk = self.group("Studio test clerk", implied_group_ids=[back_office.id])
        self.project.action_apply()
        # The intermediate group comes to grant the Settings: Apply refuses.
        middle.implied_ids = [(4, system.id)]
        with self.assertRaisesRegex(ValidationError, "grants"):
            with self.env.cr.savepoint():
                self.project.action_apply()
        with self.assertRaisesRegex(ValidationError, "Studio test back office"):
            with self.env.cr.savepoint():
                self.group("Studio test second", implied_group_ids=[back_office.id])
        self.assertFalse(clerk._studio_group_record().users)

    def test_an_exported_group_is_not_an_existing_group(self):
        """A group with an external id under « __export__ » only names no
        module the generated module can depend on; with another under an
        installed module, that one is the group's."""
        exported = self.env["res.groups"].create({"name": "Studio test exported"})
        self.env["ir.model.data"].create(
            {
                "module": "__export__",
                "name": "res_groups_studio_test_exported",
                "model": "res.groups",
                "res_id": exported.id,
            }
        )
        self.assertEqual(self.Project._studio_group_xmlid(exported), "")
        with self.assertRaisesRegex(ValidationError, "installed module"):
            with self.env.cr.savepoint():
                self.group("Studio test exporter", implied_group_ids=[exported.id])
        self.bind_group(exported, "studio_test_invented", "group_exported")
        self.assertEqual(
            self.Project._studio_group_xmlid(exported),
            "studio_test_invented.group_exported",
        )
        self.group("Studio test exporter", implied_group_ids=[exported.id])

    def test_members_lose_a_group_no_longer_implied(self):
        """Odoo adds the members of a group to the groups it comes to imply,
        never takes them out of those it stops implying: Apply takes a group
        of the project from the members who had it only through the
        implication the draft drops, and asks to confirm it."""
        user = self.group("Studio test agent")
        admin = self.group("Studio test manager", implied_line_ids=[user.id])
        lead = self.group("Studio test lead", implied_line_ids=[user.id])
        self.project._studio_set_access(
            [{"model": TICKET, "group_id": self.internal.id, "perm_read": True}]
        )
        self.project.action_apply()
        agent = user._studio_group_record()
        manager = admin._studio_group_record()
        only_admin = new_test_user(
            self.env, login="studio_test_groups_admin", groups="base.group_user"
        )
        only_admin.groups_id = [(4, manager.id)]
        both = new_test_user(
            self.env, login="studio_test_groups_both", groups="base.group_user"
        )
        both.groups_id = [(4, manager.id), (4, lead._studio_group_record().id)]
        self.assertTrue(only_admin.has_group(f"{MODULE}.{user.xml_name}"))
        self.project._studio_save_group(
            {"id": admin.id, "implied_line_ids": [], "implied_group_ids": []}
        )
        answer = self.project._studio_apply_report()
        self.assertTrue(answer["confirm"])
        self.assertEqual(
            answer["report"]["members"],
            [
                {
                    "name": agent.full_name,
                    "via": manager.full_name,
                    "users": 1,
                }
            ],
        )
        self.project.action_apply()
        self.assertEqual(manager.implied_ids, self.env["res.groups"])
        self.assertNotIn(agent, only_admin.groups_id)
        # Another group of the project still implies it.
        self.assertIn(agent, both.groups_id)
        # An existing group a project group stops implying stays.
        self.assertIn(self.internal, only_admin.groups_id)
        self.assertFalse(self.project._studio_apply_report()["report"]["members"])
