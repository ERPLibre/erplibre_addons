# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.tests.common import TransactionCase, new_test_user


class EventTableCommon(TransactionCase):
    """Fixtures shared by every ORM test of the module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.event_type_on = cls.env["event.type"].create(
            {"name": "Rotating Template", "use_rotating_tables": True}
        )
        cls.event_type_off = cls.env["event.type"].create(
            {"name": "Plain Template"}
        )
        cls.event = cls.env["event.event"].create(
            {
                "name": "Networking Evening",
                "date_begin": "2026-03-01 17:00:00",
                "date_end": "2026-03-01 22:00:00",
            }
        )
        cls.desk_user = new_test_user(
            cls.env,
            login="desk_user",
            groups="event.group_event_registration_desk",
        )

    def _make_plan(self, **kw):
        vals = {"event_id": self.event.id}
        vals.update(kw)
        return self.env["event.table.plan"].create(vals)

    def _configure_tables(
        self, plan, table_count, seats_per_table, mode="replace"
    ):
        wizard = self.env["event.table.configure.wizard"].create(
            {
                "plan_id": plan.id,
                "mode": mode,
                "table_count": table_count,
                "seats_per_table": seats_per_table,
            }
        )
        wizard.action_apply()
        return plan.table_ids

    def _add_participant(self, plan, name, **kw):
        vals = {"plan_id": plan.id, "name": name}
        vals.update(kw)
        return self.env["event.table.participant"].create(vals)
