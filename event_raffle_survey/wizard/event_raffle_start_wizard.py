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
    survey_question_ids = fields.Many2many(
        "survey.question",
        string="Required Questions",
        domain="[('survey_id', '=', survey_id), ('is_page', '=', False)]",
        help="Optional. When the list holds questions, only the respondents "
        "who answered them enter the raffle: each of them, or at least one, "
        "as Answered says.",
    )
    survey_question_match = fields.Selection(
        [("all", "Each"), ("any", "At least one")],
        string="Answered",
        default="all",
        required=True,
        help="Which of the required questions a respondent must have "
        "answered: each of them, or at least one.",
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

    @api.constrains("survey_id", "survey_question_ids")
    def _check_survey_question_ids(self):
        # A question of another survey, or a section, has no answer in the
        # chosen survey: the raffle would come out empty without a word. An
        # empty list reads no question, so a user without survey rights can
        # still start the other strategies.
        for wizard in self:
            questions = wizard.survey_question_ids
            if questions and questions - wizard.survey_id.question_ids:
                raise ValidationError(
                    _(
                        "The required questions must be questions of the "
                        "chosen survey."
                    )
                )

    @api.onchange("survey_id")
    def _onchange_survey_id(self):
        # The questions of the previous survey have no answer in this one.
        self.survey_question_ids = False

    def _filled_survey_answers(self):
        """The answers that count as filling the survey, oldest first.

        Completed is not enough: ending a live session marks every answer of
        the survey done, even one opened and never answered, so an answer must
        also answer at least one question. Test entries never count. When
        required questions are set, an answer must also answer each of them,
        or at least one, as survey_question_match says; answering means one
        line at least that is not skipped.
        """
        self.ensure_one()
        domain = [
            ("survey_id", "=", self.survey_id.id),
            ("state", "=", "done"),
            ("test_entry", "=", False),
            ("user_input_line_ids", "any", [("skipped", "=", False)]),
        ]
        questions = self.survey_question_ids
        if questions and self.survey_question_match == "any":
            domain.append(
                (
                    "user_input_line_ids",
                    "any",
                    [
                        ("question_id", "in", questions.ids),
                        ("skipped", "=", False),
                    ],
                )
            )
        else:
            for question in questions:
                domain.append(
                    (
                        "user_input_line_ids",
                        "any",
                        [
                            ("question_id", "=", question.id),
                            ("skipped", "=", False),
                        ],
                    )
                )
        return self.env["survey.user_input"].search(
            domain, order="create_date, id"
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
