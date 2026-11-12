# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models
from odoo.tools import is_html_empty, plaintext2html

from .chatbot_script_step import LINKUP_STEPS
from .discuss_channel_guide import GUIDE_SCRIPT


class ChatbotScript(models.Model):
    _inherit = "chatbot.script"

    def _linkup_is_linkup_script(self):
        """Whether the script is one of LinkUp: it holds a step of LinkUp,
        or a rule of a live chat channel of LinkUp runs it, or it is the
        script of the guide."""
        self.ensure_one()
        script = self.sudo()
        if script == self.env.ref(GUIDE_SCRIPT, raise_if_not_found=False):
            return True
        if any(
            step.step_type in LINKUP_STEPS for step in script.script_step_ids
        ):
            return True
        return bool(
            self.env["im_livechat.channel.rule"]
            .sudo()
            .search_count(
                [
                    ("chatbot_script_id", "=", script.id),
                    ("channel_id.linkup_kind", "!=", False),
                ],
                limit=1,
            )
        )

    @api.onchange("script_step_ids")
    def _onchange_script_step_ids(self):
        """Keep the answers of a ``linkup_category`` step, the categories,
        which the form of ``im_livechat`` clears for any step other than a
        question."""
        kept = {
            step: step.answer_ids
            for step in self.script_step_ids
            if step.step_type == "linkup_category"
        }
        super()._onchange_script_step_ids()
        for step, answers in kept.items():
            step.answer_ids = answers

    def _post_welcome_steps(self, discuss_channel):
        """Post the welcome steps, a step of LinkUp with the body that
        ``chatbot.script.step._linkup_step_body`` gives it, such as the
        categories with their definition."""
        self.ensure_one()
        welcome_steps = self._get_welcome_steps()
        if not any(step.step_type in LINKUP_STEPS for step in welcome_steps):
            return super()._post_welcome_steps(discuss_channel)
        posted = self.env["mail.message"]
        for step in welcome_steps:
            discuss_channel.chatbot_current_step_id = step.id
            if step.step_type in LINKUP_STEPS:
                body = step._linkup_step_body(discuss_channel)
            elif not is_html_empty(step.message):
                body = plaintext2html(step.message)
            else:
                continue
            posted += discuss_channel.with_context(
                mail_create_nosubscribe=True
            ).message_post(
                author_id=self.operator_partner_id.id,
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        return posted
