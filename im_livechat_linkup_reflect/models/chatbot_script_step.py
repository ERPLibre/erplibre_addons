# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.addons.mail_linkup_reflet.models.linkup_reflet import (
    DEFAULT_TEXT_MAX_LENGTH,
)
from odoo.exceptions import AccessError
from odoo.tools import html2plaintext, is_html_empty, plaintext2html

# The steps of the reflection guide (LU-F-125 RM1), and the field of the
# draft each answer writes.
GUIDE_STEPS = {
    "linkup_category": "category_id",
    "linkup_you_said": "you_said",
    "linkup_understood": "understood",
    "linkup_reflet_review": None,
}
FORWARD_MODERATOR = "linkup_forward_moderator"
LINKUP_STEPS = frozenset(GUIDE_STEPS) | {FORWARD_MODERATOR}


class ChatbotScriptStep(models.Model):
    """The steps of the chatbots of LinkUp.

    The guide of a reflection (LU-F-125) asks for the category, then "You
    told me", then "I understood that", and shows the draft for review.
    ``_process_step`` posts each question with what helps answering it,
    from the category chosen; ``_process_answer`` writes each answer into
    the single draft of the party: ``action_save_draft`` for a member, the
    draft of the ``mail.guest`` for a visitor, with the checks of the core
    on the server. A text left empty is refused with ``linkup.validation``
    and the step stays the current one. The chatbot never sends: the
    sending stays ``action_send``, or the reflection of a live chat
    conversation (LU-F-127).

    The answers of ``linkup_category`` are the active categories, kept in
    step by ``_linkup_sync_category_answers``: a chosen answer gives its
    ``linkup_category_id``.

    ``linkup_forward_moderator`` answers "Need help now" (LU-F-126): it
    creates the urgent report of distress of the party, then brings into the
    conversation an available moderator in no conflict of interest with
    it, the conversation joining the distress channel without start rule;
    without one, it posts the help resources and tells that the request
    waits in the queue. Beyond ``linkup.livechat_help_now_per_hour``
    reports an hour (3), for the party or for the address, it posts the
    resources and that the request is already with the moderation team,
    without a new report or a moderator.
    """

    _inherit = "chatbot.script.step"

    step_type = fields.Selection(
        selection_add=[
            ("linkup_category", "LinkUp: category of the reflection"),
            ("linkup_you_said", "LinkUp: You told me"),
            ("linkup_understood", "LinkUp: I understood that"),
            ("linkup_reflet_review", "LinkUp: review of the reflection"),
            (FORWARD_MODERATOR, "LinkUp: forward to a moderator"),
        ],
        ondelete={
            "linkup_category": "cascade",
            "linkup_you_said": "cascade",
            "linkup_understood": "cascade",
            "linkup_reflet_review": "cascade",
            FORWARD_MODERATOR: "cascade",
        },
    )

    # ------------------------------------------------------------------
    # Answers of the category step
    # ------------------------------------------------------------------

    @api.model
    def _linkup_sync_category_answers(self):
        """Give each ``linkup_category`` step one answer per active
        category, named as the category in every installed language and
        ordered as the full band; the answers of a category no longer
        active are deleted."""
        steps = self.sudo().search([("step_type", "=", "linkup_category")])
        if not steps:
            return True
        categories = self.env["linkup.category"].sudo().search([])
        langs = [code for code, _name in self.env["res.lang"].get_installed()]
        Answer = self.env["chatbot.script.answer"].sudo()
        for step in steps:
            answers = step.answer_ids
            answers.filtered(
                lambda answer: answer.linkup_category_id not in categories
            ).unlink()
            by_category = {
                answer.linkup_category_id: answer
                for answer in answers.exists()
            }
            for category in categories:
                answer = by_category.get(category)
                if not answer:
                    answer = Answer.create(
                        {
                            "script_step_id": step.id,
                            "linkup_category_id": category.id,
                            "name": category.name,
                            "sequence": category.sequence,
                        }
                    )
                elif answer.sequence != category.sequence:
                    answer.sequence = category.sequence
                for lang in langs:
                    name = category.with_context(lang=lang).name
                    if answer.with_context(lang=lang).name != name:
                        answer.with_context(lang=lang).name = name
        return True

    # ------------------------------------------------------------------
    # Party of the conversation
    # ------------------------------------------------------------------

    def _linkup_party(self, discuss_channel):
        """The party who talks with the chatbot in ``discuss_channel``:
        ``(user, guest)``, one of them empty. The visitor comes from the
        context the request of ``mail`` sets, the member from the session;
        each must be a member of the conversation."""
        members = discuss_channel.sudo().channel_member_ids
        guest = self.env["mail.guest"]._get_guest_from_context()
        if guest and guest in members.guest_id:
            return self.env["res.users"], guest.sudo()
        user = self.env.user
        if not user._is_public() and user.partner_id in members.partner_id:
            return user, self.env["mail.guest"].sudo()
        raise AccessError(_("This conversation is not yours."))

    def _linkup_draft(self, user, guest):
        """The draft of the party, under ``sudo``, or an empty
        recordset."""
        Reflet = self.env["linkup.reflet"].sudo()
        if guest:
            return Reflet._linkup_guest_draft(guest)
        return Reflet.search(
            [("author_id", "=", user.id), ("state", "=", "draft")], limit=1
        )

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _process_step(self, discuss_channel):
        """Post a step of LinkUp with what helps answering it; the other
        steps are those of ``im_livechat``."""
        self.ensure_one()
        if self.step_type not in LINKUP_STEPS:
            return super()._process_step(discuss_channel)
        # sudo: discuss.channel - updating current step on the channel is allowed
        discuss_channel.sudo().chatbot_current_step_id = self.id
        if self.step_type == FORWARD_MODERATOR:
            return self._linkup_forward_moderator(discuss_channel)
        return discuss_channel._chatbot_post_message(
            self.chatbot_script_id, self._linkup_step_body(discuss_channel)
        )

    def _linkup_step_body(self, discuss_channel):
        """The body of a step of the guide: its message, then the
        categories with their definition, the examples of the category
        chosen, its starter, or the review of the draft."""
        self.ensure_one()
        parts = []
        if not is_html_empty(self.message):
            parts.append(plaintext2html(self.message))
        user, guest = self._linkup_party(discuss_channel)
        draft = self._linkup_draft(user, guest)
        lang = self.env.context.get("lang") or self.env.lang
        category = draft.category_id.with_context(lang=lang)
        if self.step_type == "linkup_category":
            categories = (
                self.env["linkup.category"].sudo().with_context(lang=lang)
            ).search([])
            items = Markup("").join(
                Markup("<li><b>%s</b>: %s</li>")
                % (
                    item.name,
                    html2plaintext(item.definition or "").strip(),
                )
                for item in categories
            )
            parts.append(Markup("<ul>%s</ul>") % items)
        elif self.step_type == "linkup_you_said" and category:
            parts.append(
                Markup("<p>%s</p>")
                % _("Category: %(name)s", name=category.name)
            )
            if category.example_do:
                parts.append(
                    Markup("<p>%s</p>")
                    % _("To say: %(text)s", text=category.example_do)
                )
            if category.example_dont:
                parts.append(
                    Markup("<p>%s</p>")
                    % _("Not to say: %(text)s", text=category.example_dont)
                )
        elif self.step_type == "linkup_understood" and category:
            if category.starter_reflect:
                parts.append(
                    Markup("<p>%s</p>")
                    % _(
                        "You may start with: %(text)s",
                        text=category.starter_reflect,
                    )
                )
        elif self.step_type == "linkup_reflet_review":
            parts.append(self._linkup_review(draft, category, guest))
        return Markup("").join(parts)

    def _linkup_review(self, draft, category, guest):
        """The draft as the guide shows it for review, and how it is sent:
        from the Reflet view for a member, in the conversation with a
        member for a visitor. Nothing is sent from here."""
        lines = [
            _("Category: %(name)s", name=category.name or "-"),
            _("You told me: %(text)s", text=draft.you_said or "-"),
            _("I understood that: %(text)s", text=draft.understood or "-"),
        ]
        if guest:
            lines.append(
                _(
                    "Nothing is sent: choose “Talk to a member” to send it in"
                    " this window, or sign up to keep it."
                )
            )
        else:
            lines.append(
                _(
                    "Nothing is sent: your draft waits in the Reflet view,"
                    " where you choose who receives it."
                )
            )
        return Markup("").join(Markup("<p>%s</p>") % line for line in lines)

    def _process_answer(self, discuss_channel, message_body):
        """Write the answer to a step of the guide into the draft of the
        party before the next step is fetched; an answer the core refuses
        raises its ``LinkupError``, and the step stays the current one."""
        self.ensure_one()
        field = GUIDE_STEPS.get(self.step_type)
        if field:
            self._linkup_save_answer(discuss_channel, message_body, field)
        return super()._process_answer(discuss_channel, message_body)

    def _linkup_save_answer(self, discuss_channel, message_body, field):
        user, guest = self._linkup_party(discuss_channel)
        Reflet = self.env["linkup.reflet"].sudo()
        if field == "category_id":
            # sudo: chatbot.message - the answer chosen by the party
            chosen = (
                discuss_channel.sudo()
                .chatbot_message_ids.filtered(
                    lambda message: message.script_step_id == self
                    and message.user_script_answer_id
                )
                .sorted("id")[-1:]
                .user_script_answer_id
            )
            category = chosen.linkup_category_id
            if not category.active:
                raise LinkupError(
                    "linkup.validation",
                    _("Choose a category."),
                    field="category_id",
                )
            vals = {"category_id": category.id}
        else:
            max_length = Reflet._linkup_param(
                "linkup.reflet_text_max_length", DEFAULT_TEXT_MAX_LENGTH
            )
            vals = {
                field: Reflet._linkup_clean_text(
                    html2plaintext(message_body or ""),
                    field,
                    max_length,
                    required=True,
                )
            }
        if guest:
            return Reflet._linkup_guest_save_draft(guest, vals)
        return (
            self.env["linkup.reflet"].with_user(user).action_save_draft(vals)
        )

    def _linkup_forward_moderator(self, discuss_channel):
        """Answer "Need help now" (LU-F-126 RM1 to RM3, Q-44).

        The urgent report of the party is created first, so it waits in the
        queue whatever follows. An available moderator in no conflict of
        interest with it then joins the conversation, which moves to the
        distress channel, without start rule, and the opening is written to
        the audit log. Without a moderator, the chatbot posts the help
        resources and the delay of the queue at once.

        A moderator joins a welcome conversation that the party holds alone
        with the chatbot only: in a conversation a member already operates,
        or one of distress, which a restarted script would reach again, the
        report waits in the queue and the resources are posted. The row of
        the conversation is locked first, so two presses at once bring a
        single moderator. Beyond the limit of "Need help now", no report is
        created and no moderator is brought: the chatbot posts the
        resources and that the request is already with the moderation team.
        """
        user, guest = self._linkup_party(discuss_channel)
        channel = discuss_channel.sudo()
        channel.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM discuss_channel WHERE id = %s"
            " FOR NO KEY UPDATE NOWAIT",
            [channel.id],
        )
        channel.invalidate_recordset()
        Report = self.env["linkup.report"].sudo()
        if Report._linkup_help_now_limited(channel, user, guest):
            return channel._chatbot_post_message(
                self.chatbot_script_id,
                self._linkup_resources_body(limited=True),
            )
        report = Report._linkup_livechat_distress(channel, user, guest)
        Livechat = self.env["im_livechat.channel"].sudo()
        operator = self.env["res.users"]
        if (
            channel._linkup_livechat_kind() == "welcome"
            and channel._linkup_livechat_people() < 2
        ):
            operator = Livechat._linkup_distress_operator(
                report,
                lang=self.env.context.get("lang"),
                country_id=channel.country_id.id,
            )
        script = self.chatbot_script_id
        posted = self.env["mail.message"]
        if not operator or operator == self.env.user:
            return channel._chatbot_post_message(
                script, self._linkup_resources_body()
            )
        if not is_html_empty(self.message):
            posted = channel._chatbot_post_message(
                script, plaintext2html(self.message)
            )
        distress = Livechat._linkup_get("distress")
        channel._add_members(
            users=operator,
            inviting_partner=script.operator_partner_id,
            open_chat_window=True,
        )
        channel.write(
            {
                "livechat_channel_id": distress.id,
                "livechat_operator_id": operator.partner_id.id,
                "livechat_active": True,
                "linkup_start_rule": "off",
                "name": distress._linkup_conversation_name(
                    channel.anonymous_name
                    or (guest.name if guest else user.name),
                    operator,
                ),
            }
        )
        report.distress_channel_id = channel
        channel._linkup_send_start_rule()
        self.env["linkup.audit.log"]._linkup_log(
            report,
            "distress_open",
            _("Conversation of distress opened by the server"),
            record=channel,
        )
        discuss_channel._bus_send_store(
            Store(
                "ChatbotStep",
                {
                    "id": (self.id, posted.id),
                    "scriptStep": self.id,
                    "message": posted.id,
                    "operatorFound": True,
                },
            )
        )
        channel._broadcast(operator.partner_id.ids)
        return posted

    def _process_step_forward_operator(self, discuss_channel):
        """Tell both parties the start rule of the conversation once a
        member joined it: from then on, the rule binds them."""
        posted = super()._process_step_forward_operator(discuss_channel)
        if discuss_channel.sudo().livechat_channel_id.linkup_kind:
            discuss_channel._linkup_send_start_rule()
        return posted

    @api.model
    def _linkup_help_step(self):
        """The step "Need help now" of the welcome script, under
        ``sudo``."""
        step = self.sudo().env.ref(
            "im_livechat_linkup_reflect.welcome_step_help",
            raise_if_not_found=False,
        )
        if step and step.step_type == FORWARD_MODERATOR:
            return step
        return self.sudo().search(
            [("step_type", "=", FORWARD_MODERATOR)], order="id", limit=1
        )

    @api.model
    def _linkup_help_now(self, channel_id, guest=None):
        """ "Need help now", pressed in the widget at any moment of a
        welcome conversation (LU-F-126 RM1, RM3, Q-44).

        While the chatbot alone answers the party, the button does what
        the step "Need help now" does: the urgent report, then an
        available moderator in no conflict of interest, or the help
        resources posted at once; the script ends when a moderator joins.
        Once a member operates the conversation, the urgent report waits
        in the queue and the conversation stays theirs: no moderator joins
        a conversation that holds a third person. The party is the one of
        ``linkup.reflet._linkup_livechat_party``; any other case reads
        ``linkup.unavailable``.

        Beyond ``linkup.livechat_help_now_per_hour`` urgent reports an hour
        (3), for the party or for the address, the press creates no report
        and brings no moderator: the resources still show, and the chatbot
        says that the request is already with the moderation team
        (``limited``).

        Return whether a moderator joined, whether the limit held the press
        back, the step and the message posted, the help resources, the
        hours of the moderation and the delay of an urgent report, with the
        Store data of the message.
        """
        Reflet = self.env["linkup.reflet"]
        Report = self.env["linkup.report"].sudo()
        channel, user, guest = Reflet._linkup_livechat_party(channel_id, guest)
        step = self._linkup_help_step()
        if not step:
            raise Reflet._linkup_livechat_unavailable()
        posted = self.env["mail.message"]
        limited = Report._linkup_help_now_limited(channel, user, guest)
        if limited:
            posted = channel._chatbot_post_message(
                step.chatbot_script_id,
                step._linkup_resources_body(limited=True),
            )
        elif channel._linkup_livechat_people() < 2:
            posted = step._linkup_forward_moderator(channel)
        else:
            Report._linkup_livechat_distress(channel, user, guest)
        found = channel.livechat_channel_id.linkup_kind == "distress"
        if found:
            channel.chatbot_current_step_id = step
        return {
            "operator_found": found,
            "limited": limited,
            "step_id": step.id,
            "message_id": posted.id,
            **Report._linkup_help_info(),
            "store": Store(posted, for_current_user=True).get_result(),
        }

    def _linkup_resources_body(self, limited=False):
        """The help resources, and that the request waits in the queue of
        the moderation, processed within the delay of an urgent report;
        with ``limited``, that it is already with the moderation team, a
        line that tells neither the limit nor the reports counted."""
        Report = self.env["linkup.report"]
        if limited:
            lines = [
                _(
                    "LinkUp is not an emergency service: reach one of these"
                    " resources."
                )
            ]
        else:
            lines = [
                _(
                    "No person of the moderation is available right now."
                    " LinkUp is not an emergency service: reach one of these"
                    " resources."
                )
            ]
        lines += Report._linkup_help_resources()
        if limited:
            lines.append(
                _("Your request is already with the moderation team.")
            )
        else:
            lines.append(
                _(
                    "Your request waits in the queue of the moderation, which"
                    " processes it within %(hours)s hours.",
                    hours=Report._linkup_hours(True),
                )
            )
        return Markup("").join(Markup("<p>%s</p>") % line for line in lines)
