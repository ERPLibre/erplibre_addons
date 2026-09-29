# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from lxml import etree
from odoo.tests.common import new_test_user

from .common import EventTableCommon


class TestPlanMenus(EventTableCommon):
    def test_the_plan_action_lists_and_opens_plans(self):
        action = self.env.ref("erplibre_event_table.action_event_table_plan")
        self.assertEqual(action.res_model, "event.table.plan")
        self.assertEqual(action.view_mode, "list,form")

    def test_the_menu_sits_under_the_events_menu(self):
        menu = self.env.ref("erplibre_event_table.menu_event_table_plan")
        self.assertEqual(menu.parent_id, self.env.ref("event.event_main_menu"))
        self.assertIn(
            self.env.ref("event.group_event_registration_desk"),
            menu.groups_id,
        )

    def test_the_fullscreen_action_targets_the_plan(self):
        plan = self._make_plan()
        action = plan.action_open_floor_plan_fullscreen()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "erplibre_event_table.floor_plan")
        self.assertEqual(action["target"], "fullscreen")
        self.assertEqual(action["params"], {"plan_id": plan.id})


class TestPlanDuplication(EventTableCommon):
    """Odoo's own Duplicate is the only way in, so it is held to it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.event_user = new_test_user(
            cls.env, login="plan_user", groups="event.group_event_user"
        )

    def _plan_form_arch(self, user):
        view = self.env.ref("erplibre_event_table.event_table_plan_view_form")
        return etree.fromstring(
            self.env["event.table.plan"]
            .with_user(user)
            .get_view(view.id, "form")["arch"]
        )

    def test_the_form_offers_the_standard_duplicate(self):
        # The Actions menu shows Duplicate when the arch the client
        # receives forbids neither create nor duplicate; get_view sets
        # create="False" itself for a user without the create right. No
        # button duplicates a plan any more, so this arch is the whole
        # of the function: it is read here rather than assumed.
        root = self._plan_form_arch(self.event_user)
        self.assertEqual(root.tag, "form")
        self.assertIsNone(root.get("create"))
        self.assertIsNone(root.get("duplicate"))

    def test_a_read_only_user_gets_a_form_that_forbids_creating(self):
        # The counterpart: the same arch, read by a user who may not
        # create, comes back marked. Without it the assertions above
        # would pass on a form that offers nothing.
        root = self._plan_form_arch(self.desk_user)
        self.assertEqual(root.get("create"), "False")

    def _duplicate(self, plan):
        """Duplicate the way the Actions menu does: copy() as the user."""
        return plan.with_user(self.event_user).copy()

    def test_duplicating_a_plan_copies_its_tables_and_its_people(self):
        plan = self._make_plan(name="Evening Plan", round_count=4)
        self._configure_tables(plan, 3, 6)
        self._add_participant(plan, "Ada Brightwood")
        self._add_participant(plan, "Milo Fernsby")
        copy = self._duplicate(plan)
        self.assertNotEqual(copy, plan)
        self.assertEqual(copy.state, "draft")
        self.assertEqual(copy.event_id, plan.event_id)
        self.assertEqual(copy.round_count, 4)
        self.assertEqual(copy.table_ids.mapped("number"), [1, 2, 3])
        self.assertEqual(copy.seat_count, 18)
        self.assertEqual(
            sorted(copy.participant_ids.mapped("name")),
            ["Ada Brightwood", "Milo Fernsby"],
        )

    def test_duplicating_a_plan_leaves_the_original_untouched(self):
        plan = self._make_plan()
        self._configure_tables(plan, 2, 8)
        self._add_participant(plan, "Ada Brightwood")
        self._duplicate(plan)
        self.assertEqual(plan.table_count, 2)
        self.assertEqual(plan.participant_count, 1)
        self.assertEqual(plan.state, "draft")
        self.assertEqual(self.event.table_plan_count, 2)

    def test_the_duplicate_says_which_plan_it_comes_from(self):
        plan = self._make_plan(name="Evening Plan")
        copy = self._duplicate(plan)
        bodies = "".join(str(body) for body in copy.message_ids.mapped("body"))
        self.assertIn("Evening Plan", bodies)

    def test_the_duplicate_carries_the_reserved_seats(self):
        plan = self._make_plan(round_count=3)
        self._configure_tables(plan, 2, 4)
        person = self._add_participant(plan, "Ada Brightwood")
        self._add_participant(plan, "Milo Fernsby")
        self.env["event.table.pin"].create(
            {
                "plan_id": plan.id,
                "round_number": 2,
                "table_id": plan.table_ids[0].id,
                "participant_id": person.id,
                "seat_number": 3,
            }
        )
        copy = self._duplicate(plan)
        self.assertEqual(len(copy.pin_ids), 1)
        self.assertEqual(copy.pin_ids.plan_id, copy)
        self.assertEqual(copy.pin_ids.participant_id.name, person.name)
        self.assertEqual(copy.pin_ids.participant_id.plan_id, copy)
        self.assertEqual(copy.pin_ids.table_id.plan_id, copy)
        self.assertEqual(copy.pin_ids.round_number, 2)
        self.assertEqual(copy.pin_ids.seat_number, 3)

    def test_duplicating_a_chosen_plan_does_not_copy_the_choice(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "1"
        )
        plan = self._make_plan(round_count=3)
        self._configure_tables(plan, 4, 3)
        for index in range(1, 13):
            self._add_participant(plan, "Person %02d" % index)
        plan.combination_count = 1
        plan.action_generate_combinations()
        plan.combination_ids.action_choose()
        copy = self._duplicate(plan)
        self.assertFalse(copy.combination_ids)
        self.assertFalse(copy.assignment_ids)
        self.assertFalse(copy.chosen_combination_id)
        self.assertEqual(copy.state, "draft")
