# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models

# Steps that wait for an answer of the party: a choice among the answers of
# the step, or a typed text.
CHOICE_STEPS = frozenset({"question_selection", "linkup_category"})
TEXT_STEPS = frozenset(
    {
        "question_email",
        "question_phone",
        "free_input_single",
        "free_input_multi",
        "linkup_you_said",
        "linkup_understood",
    }
)
ANSWER_STEPS = CHOICE_STEPS | TEXT_STEPS
# Steps posted at most after one answer, a bound against a script whose
# steps would wait for nothing in a loop.
MAX_CHAINED_STEPS = 50


class DiscussChannel(models.Model):
    """The reflection guide of a member, run in Discuss (LU-F-125 RM5).

    ``linkup.reflet.linkup_start_guide`` opens a conversation of the
    welcome channel between the member and the chatbot, marked
    ``linkup_member_guide``. Discuss has no chatbot of the widget: the
    server runs the script there. Each message the member posts in it
    answers the current step, a choice of the step carrying
    ``selected_answer_id`` as in the widget; ``message_post`` then
    processes the answer, which the checks of the guide may refuse with
    ``linkup.validation``, the post and its step staying as they were, and
    posts the following steps up to the next one that waits for an answer,
    or the end of the script. ``linkup_guide`` gives the web client the
    step to answer: its type, whether it waits for a choice or a text, and
    the answers of a choice.
    """

    _inherit = "discuss.channel"

    linkup_member_guide = fields.Boolean(
        string="Guide of a member",
        readonly=True,
        copy=False,
        help="A conversation of the reflection guide of a member, whose"
        " script the server runs in Discuss.",
    )

    def _linkup_guide_info(self):
        """The step of the guide the member answers: ``step_type``,
        ``expects`` (``choice``, ``text``, or ``False`` once the script
        waits for nothing more) and the ``answers`` of a choice, in the
        language of the context."""
        self.ensure_one()
        step = self.sudo().chatbot_current_step_id
        expects = False
        if step.step_type in CHOICE_STEPS:
            expects = "choice"
        elif step.step_type in TEXT_STEPS:
            expects = "text"
        answers = []
        if expects == "choice":
            answers = [
                {"id": answer.id, "name": answer.name}
                for answer in step.answer_ids
            ]
        return {
            "step_type": step.step_type or False,
            "expects": expects,
            "answers": answers,
        }

    def _channel_basic_info(self):
        data = super()._channel_basic_info()
        if self.sudo().linkup_member_guide:
            data["linkup_guide"] = self._linkup_guide_info()
        return data

    @api.private
    def message_post(self, *, message_type="notification", **kwargs):
        """Answer the current step of the guide of a member with the
        message the member posts in it."""
        message = super().message_post(message_type=message_type, **kwargs)
        if len(self) == 1 and self._linkup_guide_party(message):
            self._linkup_guide_answer(message)
        return message

    def _linkup_guide_party(self, message):
        """Whether ``message`` is a post of the member of this guide."""
        channel = self.sudo()
        if not channel.linkup_member_guide:
            return False
        user = self.env.user
        partner = user.partner_id
        return (
            not user._is_public()
            and message.author_id == partner
            and partner in channel.channel_member_ids.partner_id
        )

    def _linkup_guide_answer(self, message):
        """Process ``message`` as the answer to the current step, then post
        the steps that follow it up to the next one that waits for an
        answer. A plain choice without an answer chosen is a message like
        any other. The steps posted reach the member on the bus, as any new
        message of the conversation; the new step to answer in the response
        of the post too."""
        step = self.sudo().chatbot_current_step_id
        if step.step_type not in ANSWER_STEPS:
            return
        if step.step_type == "question_selection" and not (
            self.env.context.get("selected_answer_id")
        ):
            return
        next_step = step._process_answer(self, message.body)
        for _index in range(MAX_CHAINED_STEPS):
            if not next_step:
                break
            next_step._process_step(self)
            if next_step.step_type in ANSWER_STEPS:
                break
            next_step = next_step._process_answer(self, "")
        info = {"linkup_guide": self._linkup_guide_info()}
        store = self.env.context.get("message_post_store")
        if store is not None:
            store.add(self, info)
        self._bus_send_store(self, info)
