# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, fields, models


class EventRaffleStartWizard(models.TransientModel):
    _name = "event.raffle.start.wizard"
    _description = "Start a Raffle from an Event"

    event_id = fields.Many2one(
        "event.event",
        string="Event",
        required=True,
        default=lambda self: self.env.context.get("active_id"),
    )
    name = fields.Char(string="Raffle Name")
    copy_strategy = fields.Selection(
        [
            ("present_only", "Present only (attended)"),
            ("registered_and_present", "Registered and present"),
        ],
        string="Participants",
        default="present_only",
        required=True,
    )
    context_note = fields.Text(string="Context")
    remove_winner = fields.Boolean(string="Remove Winner", default=True)

    def _registration_domain_states(self):
        self.ensure_one()
        if self.copy_strategy == "present_only":
            return ["done"]
        return ["open", "done"]

    def _copy_participants(self, raffle):
        self.ensure_one()
        states = self._registration_domain_states()
        regs = self.event_id.registration_ids.filtered(
            lambda r: r.state in states
        )
        seen = set()
        Participant = self.env["event.raffle.participant"]
        participant_vals = []
        for reg in regs:
            stripped_email = (reg.email or "").strip().lower()
            stripped_name = (reg.name or "").strip().lower()
            if reg.partner_id:
                key = ("p", reg.partner_id.id)
            elif stripped_email:
                key = ("e", stripped_email)
            elif stripped_name:
                key = ("n", stripped_name)
            else:
                key = ("i", reg.id)
            if key in seen:
                continue
            seen.add(key)
            participant_vals.append(
                {
                    "raffle_id": raffle.id,
                    "name": reg.name
                    or (reg.partner_id.name if reg.partner_id else _("Guest")),
                    "email": reg.email
                    or (reg.partner_id.email if reg.partner_id else False),
                    "partner_id": reg.partner_id.id or False,
                    "registration_id": reg.id,
                    "source": "registration",
                }
            )
        if participant_vals:
            Participant.create(participant_vals)

    def action_start(self):
        self.ensure_one()
        raffle = self.env["event.raffle"].create(
            {
                "name": self.name or _("Tirage - %s") % self.event_id.name,
                "event_id": self.event_id.id,
                "context_note": self.context_note or False,
                "remove_winner": self.remove_winner,
            }
        )
        self._copy_participants(raffle)
        return {
            "type": "ir.actions.act_window",
            "name": _("Raffle"),
            "res_model": "event.raffle",
            "res_id": raffle.id,
            "view_mode": "form",
            "target": "current",
        }
