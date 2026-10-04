# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize

# The survey groups read the answers of these survey types only, which the
# survey module's own record rules call the non-specialised surveys. A
# specialised survey, such as a recruitment one, keeps its answers to its own
# application, and a raffle drawn from it would come out empty without a word.
NON_SPECIALISED_SURVEY_TYPES = [
    "survey",
    "live_session",
    "assessment",
    "custom",
]


class EventRaffleStartWizard(models.TransientModel):
    _inherit = "event.raffle.start.wizard"

    copy_strategy = fields.Selection(
        selection_add=[("survey_only", "Survey filled only")],
        ondelete={"survey_only": "set default"},
    )
    survey_id = fields.Many2one(
        "survey.survey",
        string="Survey",
        domain=[("survey_type", "in", NON_SPECIALISED_SURVEY_TYPES)],
        help="Its respondents enter the raffle instead of the registrations: "
        "every completed answer that is not a test and answers at least one "
        "question.",
    )

    @api.constrains("copy_strategy", "survey_id")
    def _check_survey_id(self):
        # The form requires the survey too, but a record created through RPC
        # skips the form.
        for wizard in self:
            if wizard.copy_strategy == "survey_only" and not wizard.survey_id:
                raise ValidationError(
                    _("Choose the survey whose respondents enter the raffle.")
                )

    def _filled_survey_answers(self):
        """The answers that count as filling the survey, oldest first.

        Completed is not enough: ending a live session marks every answer of
        the survey done, even one opened and never answered, so an answer must
        also answer at least one question. Test entries never count.
        """
        self.ensure_one()
        return self.env["survey.user_input"].search(
            [
                ("survey_id", "=", self.survey_id.id),
                ("state", "=", "done"),
                ("test_entry", "=", False),
                ("user_input_line_ids", "any", [("skipped", "=", False)]),
            ],
            order="create_date, id",
        )

    def _copy_participants(self, raffle):
        self.ensure_one()
        if self.copy_strategy != "survey_only":
            return super()._copy_participants(raffle)
        # The answers are read as the current user, never sudo: without read
        # access to them, the raffle gets Odoo's access error, not the
        # respondents.
        seen = set()
        participant_vals = []
        for answer in self._filled_survey_answers():
            # An invitation can store '"Name" <address>': the bare address
            # identifies the person.
            key = self._participant_key(
                answer.partner_id,
                email_normalize(answer.email) or answer.email,
                answer.nickname,
                ("u", answer.id),
            )
            if key in seen:
                continue
            seen.add(key)
            # The contact's name is read as superuser, as Odoo shows the
            # contact of an answer: the record rules hide a contact whose
            # company is not active for the user. Its email stays unread, the
            # answer carries the one the respondent used.
            participant_vals.append(
                {
                    "raffle_id": raffle.id,
                    "name": answer.partner_id.sudo().name
                    or answer.nickname
                    or answer.email
                    or _("Guest"),
                    "email": answer.email or False,
                    "partner_id": answer.partner_id.id or False,
                    "source": "survey",
                }
            )
        if participant_vals:
            self.env["event.raffle.participant"].create(participant_vals)
