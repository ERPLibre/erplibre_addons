# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import contextvars
from contextlib import contextmanager

from markupsafe import Markup
from odoo import _, fields, models
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError

# Category of a request for action (LU-F-046).
ACTION_CATEGORY = "action"
# Quick replies the server posts; "Let's propose something else" opens the
# precision form of the client, an ordinary precision.
ACTION_REPLIES = ("agree", "not_now")
# Kinds of reflection whose category, or revealed theme, may be a request
# for action, and the states in which their recipient answers it.
ACTION_KINDS = ("initial", "continue", "self_disclosure", "precision")

_action_reply = contextvars.ContextVar("linkup_action_reply", default=False)


@contextmanager
def action_reply_post():
    """Mark the message posted in the block as a quick reply to a request
    for action: it is not free text and closes no round of points."""
    token = _action_reply.set(True)
    try:
        yield
    finally:
        _action_reply.reset(token)


def in_action_reply():
    """Tell whether a quick reply to a request for action is being posted."""
    return _action_reply.get()


class LinkupReflet(models.Model):
    _inherit = "linkup.reflet"

    linkup_action_reply = fields.Selection(
        [("agree", "Agreed"), ("not_now", "Not for now")],
        string="Answer to the request for action",
        readonly=True,
        copy=False,
    )

    def _linkup_is_action_request(self):
        """Whether the reflection asks for an action: its category is
        ``action``, or, for a precision whose guess is made, one of the
        hidden themes it revealed."""
        self.ensure_one()
        reflet = self.sudo()
        if reflet.kind == "precision":
            if reflet.guess_state not in ("found", "missed"):
                return False
            secret = (
                self.env["linkup.reflet.secret"]
                .sudo()
                .search([("reflet_id", "=", reflet.id)], limit=1)
            )
            return ACTION_CATEGORY in secret.category_ids.mapped("code")
        return (
            reflet.kind in ACTION_KINDS
            and reflet.category_id.code == ACTION_CATEGORY
        )

    def _linkup_action_reply_text(self, reply):
        """The sentence of a quick reply, in the language of the member who
        posts it."""
        env = self.with_context(lang=self.env.user.lang or self.env.lang).env
        if reply == "agree":
            return env._("Agreed.")
        return env._("Not for now.")

    @server_context
    def action_answer_action_request(self, reply):
        """Answer a request for action with a quick reply (LU-F-046).

        The recipient of the reflection posts ``agree`` ("Agreed.") or
        ``not_now`` ("Not for now.") in the conversation of the pair, once
        per reflection: an initial reflection once confirmed, a precision
        once its guess is made. No answer is required and none pays or
        costs points (RM2): the post is no round of free text. The card of
        the reflection then carries ``action_reply``. Return
        ``{"reflet_id", "reply", "message_id"}``.
        """
        if reply not in ACTION_REPLIES:
            raise LinkupError(
                "linkup.validation", _("Unknown answer."), field="reply"
            )
        reflet = self._linkup_begin(
            "recipient_id", ("confirmed", "sent"), ACTION_KINDS
        )
        if reflet.kind == "initial" and reflet.state != "confirmed":
            raise LinkupError(
                "linkup.validation",
                _("Confirm this reflection before answering it."),
                field="state",
            )
        if not reflet._linkup_is_action_request():
            raise LinkupError(
                "linkup.validation",
                _("This reflection asks for no action."),
                field="category_id",
            )
        if reflet.linkup_action_reply:
            raise reflet._linkup_already_answered()
        reflet.linkup_action_reply = reply
        text = reflet._linkup_action_reply_text(reply)
        with action_reply_post():
            message = reflet.channel_id.with_user(self.env.user).message_post(
                body=Markup("<p>%s</p>") % text,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        reflet._linkup_notify()
        return {
            "reflet_id": reflet.id,
            "reply": reply,
            "message_id": message.id,
        }

    def _linkup_card_values(self):
        """Add the quick reply to a request for action to the card, the
        same for both parties: it is posted in their conversation."""
        values = super()._linkup_card_values()
        values["action_reply"] = self.sudo().linkup_action_reply or False
        return values
