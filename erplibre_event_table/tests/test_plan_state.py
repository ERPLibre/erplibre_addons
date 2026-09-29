# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from lxml import etree
from odoo.exceptions import UserError

from .common import EventTableCommon


class TestPlanState(EventTableCommon):
    """Draft, proposed and chosen order the work; only locked restricts it."""

    def _seated_plan(self):
        plan = self._make_plan(round_count=2)
        self._configure_tables(plan, 2, 4)
        for name in (
            "Ada Brightwood",
            "Milo Fernsby",
            "Cora Danewick",
            "Petra Loombridge",
        ):
            self._add_participant(plan, name)
        plan.action_generate_combinations()
        plan.combination_ids.filtered(lambda c: c.rank == 1).action_choose()
        return plan

    def test_locking_freezes_every_kind_of_write(self):
        # "Lock everything" is literal, and the layout is inside it: a
        # table's position on the screen moves nobody, but a locked plan
        # is a document that has been handed out, so the cure for a bad
        # layout is to unlock rather than an exemption.
        plan = self._seated_plan()
        plan.action_lock()
        self.assertEqual(plan.state, "locked")
        with self.assertRaises(UserError):
            plan.name = "Another name"
        with self.assertRaises(UserError):
            plan.show_company = True
        with self.assertRaises(UserError):
            plan.table_ids[0].position_h = 42.0
        with self.assertRaises(UserError):
            self._add_participant(plan, "Late Arrival")
        with self.assertRaises(UserError):
            plan.participant_ids[0].excluded = True
        with self.assertRaises(UserError):
            plan.unlink()

    def test_a_locked_plan_still_prints_and_mails(self):
        # Locking freezes the record, never its use: handing the plan
        # out is the reason to lock it in the first place.
        plan = self._seated_plan()
        plan.action_lock()
        self.assertTrue(plan.action_print_participant_cards())
        self.assertTrue(plan.action_print_table_sheets())
        plan.action_send_assignment_emails()

    def test_a_locked_plan_still_takes_a_chatter_note(self):
        # The discussion attached to a record is not the record's data,
        # or a locked plan could not even be commented on.
        plan = self._seated_plan()
        plan.action_lock()
        plan.message_post(body="A note on the locked plan.")
        self.assertIn(
            "A note on the locked plan.", str(plan.message_ids[0].body)
        )

    def test_unlocking_restores_the_state_that_fits_the_data(self):
        # The label comes back from what the plan holds rather than from
        # what it wore before: nothing has to be remembered across the
        # lock, and a plan that gained a combination while locked — it
        # cannot — would still come back coherent.
        plan = self._seated_plan()
        plan.action_lock()
        plan.action_unlock()
        self.assertEqual(plan.state, "chosen")

        draft = self._make_plan()
        draft.action_lock()
        draft.action_unlock()
        self.assertEqual(draft.state, "draft")

        proposed = self._make_plan(round_count=2)
        self._configure_tables(proposed, 2, 4)
        self._add_participant(proposed, "Ada Brightwood")
        self._add_participant(proposed, "Milo Fernsby")
        proposed.action_generate_combinations()
        proposed.action_lock()
        proposed.action_unlock()
        self.assertEqual(proposed.state, "proposed")

    def test_the_status_bar_sets_the_state_and_keeps_locked_out_of_it(self):
        view = self.env.ref("erplibre_event_table.event_table_plan_view_form")
        arch = etree.fromstring(
            self.env["event.table.plan"].get_view(view.id, "form")["arch"]
        )
        field = arch.xpath("//field[@name='state']")[0]
        self.assertEqual(field.get("widget"), "statusbar")
        # locked is absent from the always-visible list, so it shows up
        # only while it IS the state, and the bar is readonly then: the
        # two buttons are the only way in and out of it.
        self.assertEqual(
            field.get("statusbar_visible"), "draft,proposed,chosen"
        )
        self.assertIn("clickable", field.get("options"))
        self.assertEqual(field.get("readonly"), "state == 'locked'")
        self.assertFalse(arch.xpath("//button[@name='action_back_to_draft']"))
        self.assertTrue(arch.xpath("//button[@name='action_lock']"))
        self.assertTrue(arch.xpath("//button[@name='action_unlock']"))

    def test_the_form_locks_every_field_a_user_could_type_into(self):
        """No field on the form offers a change a locked plan refuses.

        The model refuses every write to a locked plan, so a field left
        editable turns that rule into an error dialog after the fact:
        the operator types, saves, and is told no. This walks the arch
        rather than naming fields one by one, so a field added later is
        covered without anyone having to remember this rule exists.

        Only the plan's OWN fields are read — `not(ancestor::field)`
        skips the ones inside the embedded lists, which belong to other
        models and answer to their own guards. Computed and related
        fields are skipped too: nothing can be typed into them.
        """
        view = self.env.ref("erplibre_event_table.event_table_plan_view_form")
        arch = etree.fromstring(
            self.env["event.table.plan"].get_view(view.id, "form")["arch"]
        )
        nodes = arch.xpath("//field[not(ancestor::field)]")
        # A form that suddenly exposes almost nothing would pass every
        # assertion below while proving nothing at all.
        self.assertGreater(len(nodes), 10)
        fields = self.env["event.table.plan"]._fields
        unguarded = []
        for node in nodes:
            field = fields.get(node.get("name"))
            if (
                field is None
                or field.compute
                or field.related
                or field.readonly
            ):
                continue
            if "locked" not in (node.get("readonly") or ""):
                unguarded.append(node.get("name"))
        self.assertFalse(
            unguarded,
            "These fields stay editable on a locked plan, which refuses"
            " every write: %s" % ", ".join(sorted(unguarded)),
        )

    def test_the_placement_message_counts_who_has_no_seat(self):
        plan = self._make_plan(round_count=2)
        self._configure_tables(plan, 2, 4)
        for name in ("Ada Brightwood", "Milo Fernsby", "Cora Danewick"):
            self._add_participant(plan, name)
        self.assertEqual(plan.unplaced_count, 3)
        self.assertIn("3", plan.placement_message)
        # A pin places someone as surely as an assignment does: the
        # figure is what the operator reads before turning hand work
        # into a combination.
        self.env["event.table.pin"].create(
            {
                "plan_id": plan.id,
                "round_number": 1,
                "table_id": plan.table_ids[0].id,
                "participant_id": plan.participant_ids[0].id,
            }
        )
        self.assertEqual(plan.unplaced_count, 2)

    def test_the_placement_message_goes_quiet_once_everyone_sits(self):
        plan = self._seated_plan()
        self.assertEqual(plan.unplaced_count, 0)
        self.assertFalse(plan.placement_message)
