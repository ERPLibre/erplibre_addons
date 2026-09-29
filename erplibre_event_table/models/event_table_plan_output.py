# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, models
from odoo.exceptions import UserError


class EventTablePlanOutput(models.Model):
    """What a finished plan hands out: screens, documents and mail.

    Split from event_table_plan.py, which holds the model itself. These
    methods read the plan and produce something outside it — a client
    action, a report, a queued message — and write nothing back except
    the chatter line that records a send. They are the only ones a
    locked plan still runs, since locking freezes the record and not
    its use.
    """

    _inherit = "event.table.plan"

    def action_open_floor_plan_fullscreen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "erplibre_event_table.floor_plan",
            "target": "fullscreen",
            "params": {"plan_id": self.id},
        }

    def action_open_configure_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "event.table.configure.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_plan_id": self.id},
        }

    def action_open_participant_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "event.table.participant.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_event_id": self.event_id.id,
                "default_plan_id": self.id,
            },
        }

    def action_print_participant_cards(self):
        self.ensure_one()
        if not self.assignment_ids:
            raise UserError(
                _("Nobody is seated yet. Choose a combination first.")
            )
        return self.env.ref(
            "erplibre_event_table.action_report_participant_card"
        ).report_action(self._included_participants())

    def action_print_table_sheets(self):
        self.ensure_one()
        if not self.assignment_ids:
            raise UserError(
                _("Nobody is seated yet. Choose a combination first.")
            )
        return self.env.ref(
            "erplibre_event_table.action_report_table_sheet"
        ).report_action(self.table_ids)

    def action_send_assignment_emails(self):
        """Queue one email per included participant who has an address.

        send_mail only queues; the mail cron delivers. No PDF is attached: the
        body already carries the tables, and rendering one document per person
        at send time costs much for little.
        """
        self.ensure_one()
        if not self.assignment_ids:
            raise UserError(
                _("Nobody is seated yet. Choose a combination first.")
            )
        template = self.env.ref(
            "erplibre_event_table.mail_template_participant_tables"
        )
        sent = 0
        skipped = 0
        for participant in self._included_participants():
            if not participant.email:
                skipped += 1
                continue
            template.send_mail(participant.id)
            sent += 1
        self.message_post(
            body=_(
                "Tables sent by email. Sent: %(sent)s. Without email address:"
                " %(skipped)s.",
                sent=sent,
                skipped=skipped,
            )
        )
