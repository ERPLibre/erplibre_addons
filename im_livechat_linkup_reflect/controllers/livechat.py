# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import http
from odoo.addons.im_livechat.controllers.cors.chatbot import (
    CorsLivechatChatbotScriptController,
)
from odoo.addons.mail.models.discuss.mail_guest import add_guest_to_context
from odoo.addons.mail_linkup_community.controllers.signup import (
    LinkupCommunityController,
)
from odoo.addons.website_livechat.controllers.main import WebsiteLivechat
from odoo.http import request

from ..models.chatbot_script_step import FORWARD_MODERATOR

# Sessions a visitor opens on the welcome channel from one address within
# an hour (LU-NF-006).
SESSION_RATE_PARAM = "linkup.livechat_sessions_per_ip_hour"
DEFAULT_SESSION_RATE = 20
DISCUSS_URL = "/odoo/discuss"


def _linkup_kind(channel_id):
    """The LinkUp role of the live chat channel ``channel_id``, or
    ``False``."""
    try:
        channel_id = int(channel_id)
    except (TypeError, ValueError):
        return False
    channel = request.env["im_livechat.channel"].sudo().browse(channel_id)
    return channel.exists().linkup_kind


class LinkupLivechatController(WebsiteLivechat):
    """The routes of ``im_livechat`` for the channels of LinkUp (§9.11).

    The distress channel is opened by the server only (LU-F-126 RM5): its
    page, its loader and its rating page answer "not found", ``init``
    offers nothing and ``get_session`` opens nothing, whatever
    ``channel_id``, ``previous_operator_id`` or ``chatbot_script_id`` the
    client sends. A logged-in user holds Discuss: the welcome widget sends
    them there (``linkup_redirect``) and opens no session for them (Q-45).
    ``init`` also gives the LinkUp role of the channel (``linkup_kind``),
    which the widget reads before a conversation exists.
    A visitor opens at most ``linkup.livechat_sessions_per_ip_hour`` (20)
    sessions of the welcome channel an hour from one address. The
    conversations of LinkUp take no rating of their operator, a measure of
    ego (LU-NF-032).
    """

    @http.route()
    def support_page(self, channel_id, **kwargs):
        if _linkup_kind(channel_id) == "distress":
            raise request.not_found()
        return super().support_page(channel_id, **kwargs)

    @http.route()
    def loader(self, channel_id, **kwargs):
        if _linkup_kind(channel_id) == "distress":
            raise request.not_found()
        return super().loader(channel_id, **kwargs)

    @http.route()
    def channel_rating(self, channel, **kw):
        if channel.sudo().linkup_kind:
            raise request.not_found()
        return super().channel_rating(channel, **kw)

    @http.route()
    def livechat_init(self, channel_id):
        result = super().livechat_init(channel_id)
        kind = _linkup_kind(channel_id)
        result["linkup_kind"] = kind
        if kind == "distress":
            result.update(available_for_me=False, rule={})
        elif kind == "welcome" and not request.env.user._is_public():
            result.update(
                available_for_me=False, rule={}, linkup_redirect=DISCUSS_URL
            )
        return result

    @http.route()
    def get_session(
        self,
        channel_id,
        anonymous_name,
        previous_operator_id=None,
        chatbot_script_id=None,
        persisted=True,
        **kwargs,
    ):
        kind = _linkup_kind(channel_id)
        if kind == "distress":
            return False
        if kind == "welcome":
            if not request.env.user._is_public():
                return False
            if persisted and not self._linkup_count_session():
                return False
        return super().get_session(
            channel_id,
            anonymous_name,
            previous_operator_id=previous_operator_id,
            chatbot_script_id=chatbot_script_id,
            persisted=persisted,
            **kwargs,
        )

    def _linkup_count_session(self):
        """Count a session of the welcome channel from the address of the
        request; ``False`` once the limit of the hour is reached."""
        Rate = request.env["linkup.rate.event"].sudo()
        address = request.env["res.users"]._linkup_request_address()
        limit = request.env["linkup.reflet"]._linkup_param(
            SESSION_RATE_PARAM, DEFAULT_SESSION_RATE
        )
        if Rate._linkup_exceeded(
            "livechat_session", address, limit, timedelta(hours=1)
        ):
            return False
        Rate._linkup_hit("livechat_session", address)
        return True

    @http.route()
    def feedback(self, channel_id, rate, reason=None, **kwargs):
        try:
            conversation = (
                request.env["discuss.channel"].sudo().browse(int(channel_id))
            )
        except (TypeError, ValueError):
            return False
        if conversation.exists().livechat_channel_id.linkup_kind:
            return False
        return super().feedback(channel_id, rate, reason=reason, **kwargs)


class LinkupChatbotController(CorsLivechatChatbotScriptController):
    """``/chatbot/step/trigger`` (and its CORS route) ends the script of
    the widget once "Need help now" brought a moderator: ``im_livechat``
    marks a step as having found an operator for ``forward_operator`` only,
    so the widget would trigger the next step, and the end of the script
    would close the conversation of distress."""

    @http.route()
    def chatbot_trigger_step(self, channel_id, chatbot_script_id=None):
        result = super().chatbot_trigger_step(
            channel_id, chatbot_script_id=chatbot_script_id
        )
        if not isinstance(result, dict) or not result.get("ChatbotStep"):
            return result
        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            return result
        # sudo: discuss.channel - the step and the role of the conversation
        # the trigger just processed
        channel = request.env["discuss.channel"].sudo().browse(channel_id)
        if (
            channel.exists()
            and channel.chatbot_current_step_id.step_type == FORWARD_MODERATOR
            and channel._linkup_livechat_kind() == "distress"
        ):
            for step in result["ChatbotStep"]:
                step["operatorFound"] = True
        return result


class LinkupLivechatReportController(LinkupCommunityController):
    """``/linkup/v1/report`` answers a report of distress with the
    conversation opened with a moderator, or the help resources and the
    queue (LU-F-126 RM3)."""

    @http.route()
    def linkup_report(
        self,
        reason=None,
        description=None,
        message_id=None,
        reflet_id=None,
        user_id=None,
        partner_id=None,
        previous_operator_id=None,
    ):
        Report = request.env["linkup.report"]
        report_id = Report.action_create_report(
            reflet_id=reflet_id,
            message_id=message_id,
            user_id=user_id,
            partner_id=partner_id,
            reason=reason,
            description=description,
            previous_operator_id=previous_operator_id,
        )
        report = Report.browse(report_id)
        result = {
            "id": report.id,
            "urgent": report.urgent,
            "urgent_hours": Report._linkup_hours(True),
        }
        if reason == "distress":
            result["distress"] = Report.linkup_distress_info(report.id)
        return result


class LinkupLivechatRefletController(http.Controller):
    """The routes of a visitor of the welcome widget (LU-F-127 RM4).

    Each one takes the visitor from the cookie of ``mail.guest``, never
    from a parameter, and acts in the conversation ``channel_id`` only when
    the visitor is a member of it; a logged-in member acts as themself.
    Any other case gets ``linkup.unavailable``. A card never holds a hidden
    theme: a reflection of a live chat has none.
    """

    def _linkup_guest(self):
        if not request.env.user._is_public():
            return request.env["mail.guest"]
        return request.env["mail.guest"]._get_guest_from_context()

    def _linkup_reflets(self):
        return request.env["linkup.reflet"]

    def _linkup_refused(self):
        return self._linkup_reflets()._linkup_livechat_unavailable()

    def _linkup_actor(self):
        """The visitor of the request, or an empty recordset for a
        logged-in user; a public request without a visitor is refused."""
        guest = self._linkup_guest()
        if request.env.user._is_public() and not guest:
            raise self._linkup_refused()
        return guest

    def _linkup_lang_env(self):
        """The environment of the request in the language of the chatbot,
        the language of the visitor."""
        lang = request.env["chatbot.script"]._get_chatbot_language()
        return request.env(context=dict(request.env.context, lang=lang))

    @http.route(
        "/linkup/v1/livechat/categories",
        type="json",
        auth="public",
        methods=["POST"],
    )
    def linkup_livechat_categories(self):
        """The active categories, with the texts of the Help bar."""
        return self._linkup_lang_env()[
            "linkup.category"
        ]._linkup_public_categories()

    @http.route(
        "/linkup/v1/livechat/help",
        type="json",
        auth="public",
        methods=["POST"],
    )
    def linkup_livechat_help(self):
        """The help resources, the hours of the moderation and the delay
        of an urgent report; nothing is recorded."""
        return self._linkup_lang_env()["linkup.report"]._linkup_help_info()

    @http.route(
        "/linkup/v1/livechat/help_now",
        type="json",
        auth="public",
        methods=["POST"],
    )
    @add_guest_to_context
    def linkup_livechat_help_now(self, channel_id):
        """ "Need help now" in the welcome conversation ``channel_id``; see
        ``chatbot.script.step._linkup_help_now``."""
        guest = self._linkup_actor()
        return self._linkup_lang_env()["chatbot.script.step"]._linkup_help_now(
            channel_id, guest=guest
        )

    @http.route(
        "/linkup/v1/livechat/reflet/info",
        type="json",
        auth="public",
        methods=["POST"],
    )
    @add_guest_to_context
    def linkup_livechat_info(self, channel_id):
        """The cards, the draft and the start rule of the conversation."""
        return self._linkup_reflets()._linkup_livechat_info(
            channel_id, guest=self._linkup_actor()
        )

    @http.route(
        "/linkup/v1/livechat/reflet/draft",
        type="json",
        auth="public",
        methods=["POST"],
    )
    @add_guest_to_context
    def linkup_livechat_draft(self, channel_id, vals=None):
        """Save the draft of the party; return its id."""
        return self._linkup_reflets()._linkup_livechat_save_draft(
            channel_id, vals or {}, guest=self._linkup_actor()
        )

    @http.route(
        "/linkup/v1/livechat/reflet/send",
        type="json",
        auth="public",
        methods=["POST"],
    )
    @add_guest_to_context
    def linkup_livechat_send(self, channel_id):
        """Send the draft of the party to the other party; return the id
        of the reflection."""
        return self._linkup_reflets()._linkup_livechat_send(
            channel_id, guest=self._linkup_actor()
        )

    def _linkup_answer(self, channel_id, reflet_id, state):
        guest = self._linkup_actor()
        try:
            reflet_id = int(reflet_id)
        except (TypeError, ValueError):
            raise self._linkup_refused() from None
        reflet = self._linkup_reflets().sudo().browse(reflet_id).exists()
        if not reflet or str(reflet.channel_id.id) != str(channel_id):
            raise self._linkup_refused()
        return reflet._linkup_livechat_answer(state, guest=guest)

    @http.route(
        "/linkup/v1/livechat/reflet/confirm",
        type="json",
        auth="public",
        methods=["POST"],
    )
    @add_guest_to_context
    def linkup_livechat_confirm(self, channel_id, reflet_id):
        """Confirm, as its recipient, a reflection of the conversation."""
        return self._linkup_answer(channel_id, reflet_id, "confirmed")

    @http.route(
        "/linkup/v1/livechat/reflet/reject",
        type="json",
        auth="public",
        methods=["POST"],
    )
    @add_guest_to_context
    def linkup_livechat_reject(self, channel_id, reflet_id):
        """Reject, as its recipient, a reflection of the conversation."""
        return self._linkup_answer(channel_id, reflet_id, "rejected")
