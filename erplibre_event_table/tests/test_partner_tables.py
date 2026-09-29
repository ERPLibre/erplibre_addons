# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.tests.common import new_test_user

from .common import EventTableCommon


class TestPartnerTables(EventTableCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Ada Brightwood", "email": "ada@example.com"}
        )
        cls.plan = cls.env["event.table.plan"].create(
            {"event_id": cls.event.id, "round_count": 2}
        )

    def _seat_everyone(self):
        self._configure_tables(self.plan, 2, 4)
        self._add_participant(
            self.plan, "Ada Brightwood", partner_id=self.partner.id
        )
        for index in range(5):
            self._add_participant(self.plan, "Guest %s" % index)
        self.plan.action_generate_combinations()
        self.plan.combination_ids[0].action_choose()

    def test_a_contact_without_a_table_shows_no_button(self):
        self.assertEqual(self.partner.table_plan_count, 0)

    def test_a_seated_contact_counts_one_plan_for_every_round(self):
        self._seat_everyone()
        self.partner.invalidate_recordset(["table_plan_count"])
        # two rounds in one plan: the count is of PLANS, not of rounds
        self.assertEqual(self.partner.table_plan_count, 1)
        self.assertEqual(len(self.partner.table_assignment_ids), 2)

    def test_a_user_without_event_rights_sees_a_zero_count(self):
        self._seat_everyone()
        plain_user = new_test_user(
            self.env, login="plain_user", groups="base.group_user"
        )
        partner = self.partner.with_user(plain_user)
        partner.invalidate_recordset(["table_plan_count"])
        self.assertEqual(partner.table_plan_count, 0)

    def test_the_contact_action_filters_on_the_contact(self):
        action = self.partner.action_view_table_assignments()
        self.assertEqual(action["res_model"], "event.table.assignment")
        self.assertEqual(
            action["domain"], [("partner_id", "=", self.partner.id)]
        )
