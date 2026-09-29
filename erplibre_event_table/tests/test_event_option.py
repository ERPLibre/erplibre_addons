# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import AccessError
from odoo.tests import Form

from .common import EventTableCommon


class TestEventOption(EventTableCommon):
    def test_an_event_without_a_template_keeps_the_option_off(self):
        self.assertFalse(self.event.use_rotating_tables)

    def test_the_option_comes_from_the_template_when_it_changes(self):
        with Form(self.event) as form:
            form.event_type_id = self.event_type_on
        self.assertTrue(self.event.use_rotating_tables)

    def test_a_template_without_the_option_turns_it_off(self):
        self.event.use_rotating_tables = True
        with Form(self.event) as form:
            form.event_type_id = self.event_type_off
        self.assertFalse(self.event.use_rotating_tables)

    def test_an_event_created_from_a_template_starts_with_the_option(self):
        event = self.env["event.event"].create(
            {
                "name": "Templated Evening",
                "date_begin": "2026-04-01 17:00:00",
                "date_end": "2026-04-01 22:00:00",
                "event_type_id": self.event_type_on.id,
            }
        )
        self.assertTrue(event.use_rotating_tables)

    def test_a_manual_value_survives_a_later_write(self):
        with Form(self.event) as form:
            form.event_type_id = self.event_type_off
            form.use_rotating_tables = True
        self.assertTrue(self.event.use_rotating_tables)
        self.event.write({"name": "Renamed Evening"})
        self.assertTrue(self.event.use_rotating_tables)

    def test_a_manual_value_survives_a_write_on_the_template_itself(self):
        with Form(self.event) as form:
            form.event_type_id = self.event_type_off
            form.use_rotating_tables = True
        self.event_type_off.write({"name": "Plain Template Renamed"})
        self.event.invalidate_recordset(["use_rotating_tables"])
        self.assertTrue(self.event.use_rotating_tables)

    def test_the_participant_wizard_opens_in_a_dialog_on_the_event(self):
        action = self.event.action_add_table_participants()
        self.assertEqual(action["res_model"], "event.table.participant.wizard")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"]["default_event_id"], self.event.id)

    def test_the_registration_desk_reads_the_option(self):
        event = self.event.with_user(self.desk_user)
        self.assertFalse(event.use_rotating_tables)

    def test_the_registration_desk_does_not_write_the_option(self):
        event = self.event.with_user(self.desk_user)
        with self.assertRaises(AccessError):
            event.write({"use_rotating_tables": True})
