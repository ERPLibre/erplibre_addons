# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, fields, models
from odoo.exceptions import UserError

# Odoo puts a Name, an Email and a Phone question on every event by default,
# and the registration form answers those by itself. An answer to one proves
# nothing about the survey, so only the question types an attendee actually
# fills in count as "survey answered".
SURVEY_QUESTION_TYPES = ("simple_choice", "text_box")


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
            ("survey_only", "Survey filled only"),
            ("survey_and_present", "Survey filled and present"),
        ],
        string="Participants",
        default="present_only",
        required=True,
        help="Qui entre dans le tirage. Les deux choix « sondage » ne "
        "gardent que les inscrits ayant répondu au questionnaire "
        "d'inscription de l'événement.",
    )
    context_note = fields.Text(string="Context")
    remove_winner = fields.Boolean(string="Remove Winner", default=True)

    def _registration_domain_states(self):
        self.ensure_one()
        if self.copy_strategy in ("present_only", "survey_and_present"):
            return ["done"]
        return ["open", "done"]

    def _requires_survey(self):
        self.ensure_one()
        return self.copy_strategy in ("survey_only", "survey_and_present")

    def _survey_questions(self):
        """The event's real survey questions, identity fields excluded."""
        self.ensure_one()
        return self.event_id.question_ids.filtered(
            lambda q: q.question_type in SURVEY_QUESTION_TYPES
        )

    def _filter_survey_answered(self, regs):
        """Keep the registrations carrying at least one survey answer.

        One query for the whole set, and the order of `regs` is preserved so
        the de-duplication in _copy_participants keeps behaving the same way.
        """
        self.ensure_one()
        questions = self._survey_questions()
        if not questions:
            raise UserError(
                _(
                    "L'événement « %s » n'a pas de question de "
                    "questionnaire : aucun inscrit ne peut avoir rempli le "
                    "sondage. Ajoutez une question, ou choisissez un autre "
                    "type de participants."
                )
                % self.event_id.name
            )
        answers = self.env["event.registration.answer"].search(
            [
                ("registration_id", "in", regs.ids),
                ("question_id", "in", questions.ids),
            ]
        )
        answered_ids = set(answers.registration_id.ids)
        return regs.filtered(lambda r: r.id in answered_ids)

    def _copy_participants(self, raffle):
        self.ensure_one()
        states = self._registration_domain_states()
        regs = self.event_id.registration_ids.filtered(
            lambda r: r.state in states
        )
        if self._requires_survey():
            regs = self._filter_survey_answered(regs)
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
