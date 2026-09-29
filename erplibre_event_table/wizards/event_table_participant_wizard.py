# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models


class EventTableParticipantWizard(models.TransientModel):
    _name = "event.table.participant.wizard"
    _description = "Add Rotating Table Participants"

    event_id = fields.Many2one(
        "event.event",
        required=True,
        default=lambda self: self.env.context.get("default_event_id"),
    )
    plan_id = fields.Many2one(
        "event.table.plan",
        compute="_compute_plan_id",
        store=True,
        readonly=False,
        domain="[('event_id', '=', event_id)]",
        help="Leave empty to create a new plan.",
    )
    registration_scope = fields.Selection(
        [
            ("registered", "Registered and attended"),
            ("attended", "Attended only"),
            ("none", "No registration"),
        ],
        default="registered",
        required=True,
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "event_table_participant_wizard_partner_rel",
        "wizard_id",
        "partner_id",
        string="Other Contacts",
    )

    @api.depends("event_id")
    def _compute_plan_id(self):
        for wizard in self:
            wizard.plan_id = wizard.event_id.table_plan_ids[:1]

    def _registration_states(self):
        self.ensure_one()
        if self.registration_scope == "attended":
            return ["done"]
        if self.registration_scope == "registered":
            return ["open", "done"]
        return []

    def action_add(self):
        self.ensure_one()
        plan = self.plan_id
        if not plan:
            plan = self.env["event.table.plan"].create(
                {"event_id": self.event_id.id}
            )
        states = self._registration_states()
        # event.registration orders "id desc": sorting ascending restores
        # booking order, so the earliest registration of a shared booker
        # is the one that wins the merge in _add_registrations.
        registrations = self.event_id.registration_ids.filtered(
            lambda r: r.state in states
        ).sorted("id")
        added, merged = plan._add_registrations(registrations)
        added += plan._add_partners(self.partner_ids)
        plan.message_post(
            body=_(
                "Participants added: %(added)s."
                " Registrations merged with an existing participant:"
                " %(merged)s.",
                added=added,
                merged=merged,
            )
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Rotating Table Plan"),
            "res_model": "event.table.plan",
            "res_id": plan.id,
            "view_mode": "form",
            "target": "current",
        }
