# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Reflections between a visitor and a member in the widget (T-55,
LU-F-127, Q-43): the start rule of a live chat conversation, the parties
``mail.guest``, the routes of a visitor, the scoring events held until the
signup of the visitor, and the report of a visitor."""

import json
import re
from datetime import timedelta

import psycopg2
from odoo import fields
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.mail_linkup_community.tests.common import (
    SIGNUP_FORM,
    LinkupAltchaMixin,
)
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import LinkupLivechatCase

DRAFT = {
    "you_said": "Que tu découvres LinkUp aujourd'hui.",
    "understood": "Que tu es curieuse.",
    "real_world_declared": True,
}


class LinkupLivechatRefletMixin:
    def _operator_reflet(self, channel):
        """A reflection of Nicolas to the visitor of ``channel``, sent."""
        Reflet = self.Reflet.with_user(self.nicolas)
        Reflet.action_save_draft(dict(DRAFT, category_id=self.needs.id))
        return self.Reflet.sudo().browse(
            Reflet.action_livechat_send(channel.id)
        )

    def _visitor_reflet(self, channel, guest):
        """A reflection of the visitor of ``channel`` to Nicolas, sent."""
        self.Reflet._linkup_livechat_save_draft(
            channel.id, dict(DRAFT, category_id=self.goals.id), guest=guest
        )
        return self.Reflet.sudo().browse(
            self.Reflet._linkup_livechat_send(channel.id, guest=guest)
        )

    def _held(self, guest):
        return self.GuestEvent.sudo().search([("guest_id", "=", guest.id)])

    def _lines(self, reflet):
        return self.Ledger.sudo().search([("reflet_id", "=", reflet.id)])


@tagged("post_install", "-at_install")
class TestLinkupLivechatReflet(LinkupLivechatRefletMixin, LinkupLivechatCase):
    def test_strict_refuses_free_text(self):
        """CA1, RM3: in ``strict``, once Nicolas joined, the free text of
        the visitor and of Nicolas is refused with ``linkup.start_rule``;
        the answers to the chatbot before passed."""
        channel, guest = self._member_session()
        self.assertEqual(channel._linkup_start_rule(), "strict")
        with self.assertLinkupCode("linkup.start_rule"):
            self._post(channel, "Bonjour !", guest=guest)
        with self.assertLinkupCode("linkup.start_rule"):
            self._post(channel, "Bonjour !", user=self.nicolas)
        info = channel.with_user(self.nicolas)._linkup_start_rule_info()
        self.assertEqual(info["linkup_start_rule"], "strict")
        self.assertFalse(info["linkup_start_rule_satisfied"])

    def test_chatbot_answers_pass(self):
        """RM3: the answers of a visitor to the chatbot, alone with it, are
        never refused."""
        channel, guest = self._welcome_session()
        self.assertTrue(self._post(channel, "Bonjour", guest=guest))

    def test_confirmed_reflection_opens_the_text(self):
        """CA2, RM2: Nicolas sends a reflection to the visitor, whose
        carrier is posted in the conversation; the visitor confirms it, and
        the free text opens to both."""
        channel, guest = self._member_session()
        reflet = self._operator_reflet(channel)
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(reflet.author_id, self.nicolas)
        self.assertEqual(reflet.recipient_guest_id, guest)
        self.assertFalse(reflet.recipient_id)
        self.assertEqual(reflet.channel_id, channel)
        self.assertFalse(reflet.link_id)
        self.assertEqual(reflet.message_id.model, "discuss.channel")
        self.assertEqual(reflet.message_id.res_id, channel.id)
        self.assertEqual(reflet.message_id.author_id, self.nicolas.partner_id)
        self.assertTrue(
            self.Reflet._linkup_livechat_info(channel.id, guest=guest)[
                "reflet_ids"
            ]
        )
        reflet._linkup_livechat_answer("confirmed", guest=guest)
        self.assertEqual(reflet.state, "confirmed")
        self.assertTrue(self._post(channel, "Merci !", guest=guest))
        self.assertTrue(
            self._post(channel, "Avec plaisir.", user=self.nicolas)
        )

    def test_visitor_sends_a_reflection(self):
        """RM2: the visitor is the author, Nicolas the recipient who
        confirms it; the carrier names the visitor."""
        channel, guest = self._member_session()
        reflet = self._visitor_reflet(channel, guest)
        self.assertEqual(reflet.author_guest_id, guest)
        self.assertFalse(reflet.author_id)
        self.assertEqual(reflet.recipient_id, self.nicolas)
        self.assertEqual(reflet.message_id.author_guest_id, guest)
        self.assertFalse(self.Reflet._linkup_guest_draft(guest))
        self.Reflet.with_user(self.nicolas).browse(
            reflet.id
        ).action_livechat_confirm()
        self.assertEqual(reflet.state, "confirmed")
        self.assertTrue(self._post(channel, "Super.", user=self.nicolas))

    def test_party_checks(self):
        """RM2, RM4: only the recipient answers; the author never; a
        visitor of another conversation reads nothing of it."""
        channel, guest = self._member_session()
        reflet = self._operator_reflet(channel)
        with self.assertRaises(AccessError):
            self.Reflet.with_user(self.nicolas).browse(
                reflet.id
            ).action_livechat_confirm()
        other_channel, other = self._welcome_session(self._visitor("Autre"))
        with self.assertLinkupCode("linkup.unavailable"):
            self.Reflet._linkup_livechat_info(channel.id, guest=other)
        with self.assertLinkupCode("linkup.unavailable"):
            reflet._linkup_livechat_answer("confirmed", guest=other)
        with self.assertLinkupCode("linkup.unavailable"):
            self.Reflet._linkup_livechat_info(999999, guest=guest)
        with self.assertLinkupCode("linkup.unavailable"):
            self.Reflet.with_user(self.sam).linkup_livechat_info(channel.id)
        self.assertEqual(reflet.state, "sent")
        # Twice answered: the second one is refused.
        reflet._linkup_livechat_answer("rejected", guest=guest)
        with self.assertLinkupCode("linkup.already_answered"):
            reflet._linkup_livechat_answer("confirmed", guest=guest)

    def test_send_requires_two_parties(self):
        """RM1: without a member in the conversation, the visitor has
        nobody to send to."""
        channel, guest = self._welcome_session()
        self.Reflet._linkup_livechat_save_draft(
            channel.id, dict(DRAFT, category_id=self.goals.id), guest=guest
        )
        with self.assertLinkupCode("linkup.unavailable"):
            self.Reflet._linkup_livechat_send(channel.id, guest=guest)

    def test_send_requires_the_texts(self):
        """RM2: the controls of a first reflection apply: the texts, the
        category and the declaration of the exchange in person."""
        channel, guest = self._member_session()
        self.Reflet._linkup_livechat_save_draft(
            channel.id, {"category_id": self.goals.id}, guest=guest
        )
        with self.assertLinkupCode("linkup.validation"):
            self.Reflet._linkup_livechat_send(channel.id, guest=guest)
        self.Reflet._linkup_livechat_save_draft(
            channel.id,
            {"you_said": DRAFT["you_said"], "understood": "Oui."},
            guest=guest,
        )
        with self.assertLinkupCode(
            "linkup.validation", field="real_world_declared"
        ):
            self.Reflet._linkup_livechat_send(channel.id, guest=guest)

    def test_one_party_each(self):
        """RM2: a party is a member or a visitor, never both."""
        guest = self._visitor()
        with mute_logger("odoo.sql_db"), self.assertRaises(
            psycopg2.IntegrityError
        ), self.env.cr.savepoint():
            self.Reflet.sudo().create(
                {
                    "author_id": self.sam.id,
                    "author_guest_id": guest.id,
                    "kind": "initial",
                    "state": "draft",
                }
            )

    def test_points_held_until_the_signup(self):
        """CA3, RM5, Q-43: once the reflection is confirmed, the ledger
        holds no line, and events wait for the visitor; at the verified
        signup, the lines of both parties are written once."""
        channel, guest = self._member_session()
        reflet = self._operator_reflet(channel)
        reflet._linkup_livechat_answer("confirmed", guest=guest)
        self.assertFalse(self._lines(reflet))
        held = self._held(guest)
        self.assertEqual(
            set(held.mapped("code")), {"reflect_sent", "reflect_confirmed"}
        )
        self.assertEqual(held.counterpart_user_id, self.nicolas)
        pair_key = f"livechat:{guest.id}:{self.nicolas.id}"
        self.assertEqual(
            set(held.mapped("event_key")), {f"reflet:{reflet.id}", pair_key}
        )
        # Held twice, held once.
        self.GuestEvent._linkup_hold(
            guest, "reflect_confirmed", reflet, self.nicolas, key=pair_key
        )
        self.assertEqual(len(self._held(guest)), 2)
        self.luce.sudo().linkup_livechat_guest_id = guest
        self._as_public_account(self.luce)
        self.assertFalse(self.luce._linkup_livechat_attach())
        self.assertFalse(self._lines(reflet))
        self.luce.sudo().linkup_email_verified = True
        self.assertTrue(self.luce._linkup_livechat_attach())
        self.assertEqual(reflet.recipient_id, self.luce)
        self.assertFalse(reflet.recipient_guest_id)
        lines = self._lines(reflet)
        self.assertTrue(lines)
        self.assertEqual(lines.user_id, self.luce | self.nicolas)
        self.assertFalse(self._held(guest))
        # Released again, the same events pay nothing more.
        self.GuestEvent._linkup_hold(
            guest, "reflect_sent", reflet, self.nicolas
        )
        self.GuestEvent._linkup_hold(
            guest, "reflect_confirmed", reflet, self.nicolas, key=pair_key
        )
        self.GuestEvent._linkup_release(guest)
        self.assertEqual(self._lines(reflet), lines)

    def test_pair_confirmation_paid_once(self):
        """RM5: a pair of a visitor and a member has no link to cap; its
        confirmations are held under the key of the pair, so two
        reflections confirmed in the conversation pay the confirmation of
        Nicolas once."""
        channel, guest = self._member_session()
        first = self._operator_reflet(channel)
        first._linkup_livechat_answer("confirmed", guest=guest)
        second = self._operator_reflet(channel)
        second._linkup_livechat_answer("confirmed", guest=guest)
        confirmed = self._held(guest).filtered(
            lambda event: event.code == "reflect_confirmed"
        )
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed.reflet_id, first)
        self.luce.sudo().linkup_livechat_guest_id = guest
        self._as_public_account(self.luce, verified=True)
        self.assertTrue(self.luce._linkup_livechat_attach())
        rule = self.env.ref("mail_linkup_gamification.rule_reflect_confirmed")
        lines = self.Ledger.sudo().search(
            [("user_id", "=", self.nicolas.id), ("rule_id", "=", rule.id)]
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            lines.event_key, f"livechat:{guest.id}:{self.nicolas.id}"
        )

    def test_core_actions_refused(self):
        """A reflection of a live chat has no link: the actions of the
        core, which would lock and move a link and pay the points at once,
        read ``linkup.unavailable``; its recipient still reads it."""
        channel, guest = self._member_session()
        reflet = self._visitor_reflet(channel, guest)
        mine = self.Reflet.with_user(self.nicolas).browse(reflet.id)
        for action in ("action_confirm", "action_reject"):
            with self.assertLinkupCode("linkup.unavailable"):
                getattr(mine, action)()
        self.assertTrue(mine.action_mark_read())
        sent = self._operator_reflet(channel)
        with self.assertLinkupCode("linkup.unavailable"):
            self.Reflet.with_user(self.nicolas).browse(
                sent.id
            ).action_withdraw()
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(sent.state, "sent")
        self.assertFalse(self._lines(reflet) | self._lines(sent))

    def test_attached_reflection_stays(self):
        """RM4: once its visitor signed up, a reflection of the
        conversation has two members as parties, and its answer reads
        ``linkup.unavailable`` instead of paying outside the hold."""
        channel, guest = self._member_session()
        reflet = self._visitor_reflet(channel, guest)
        self.luce.sudo().linkup_livechat_guest_id = guest
        self._as_public_account(self.luce, verified=True)
        self.assertTrue(self.luce._linkup_livechat_attach())
        self.assertEqual(reflet.author_id, self.luce)
        with self.assertLinkupCode("linkup.unavailable"):
            self.Reflet.with_user(self.nicolas).browse(
                reflet.id
            ).action_livechat_confirm()
        self.assertEqual(reflet.state, "sent")

    def test_carrier_names_the_operator_by_pseudonym(self):
        """RM1: the visitor reads the operator by their pseudonym of the
        live chat, in the carrier message too."""
        self.nicolas.sudo().livechat_username = "Nico"
        channel, guest = self._member_session()
        reflet = self._operator_reflet(channel)
        self.assertIn("Nico", reflet.message_id.body)
        self.assertNotIn("Nicolas", reflet.message_id.body)

    def test_held_events_expire(self):
        """RM5, Q-43: an event held longer than
        ``linkup.guest_event_expiry_days`` is deleted without points."""
        channel, guest = self._member_session()
        reflet = self._operator_reflet(channel)
        old = self._held(guest)
        old.date = fields.Datetime.now() - timedelta(days=31)
        reflet._linkup_livechat_answer("confirmed", guest=guest)
        self.GuestEvent._cron_linkup_expire()
        self.assertEqual(
            self._held(guest).mapped("code"), ["reflect_confirmed"]
        )
        self.assertFalse(self._lines(reflet))

    def test_unanswered_reflection_expires(self):
        """A reflection of a live chat, which has no link, expires as a
        reflection of the core does."""
        channel, guest = self._member_session()
        reflet = self._operator_reflet(channel)
        reflet.sent_date = fields.Datetime.now() - timedelta(days=31)
        self.GuestEvent._cron_linkup_expire()
        self.assertEqual(reflet.state, "expired")

    def test_incitative_lets_text_through(self):
        """CA4: in ``incitative``, the free text of the visitor passes and
        the banner stays, no reflection being confirmed."""
        self.welcome.linkup_start_rule = "incitative"
        channel, guest = self._member_session()
        self.assertTrue(self._post(channel, "Bonjour !", guest=guest))
        info = channel.with_user(self.nicolas)._linkup_start_rule_info()
        self.assertEqual(info["linkup_start_rule"], "incitative")
        self.assertFalse(info["linkup_start_rule_satisfied"])

    def test_report_the_visitor(self):
        """RM6: Nicolas reports the visitor; the report carries the
        conversation, the visitor and their last message, and the queue
        names the visitor."""
        self.welcome.linkup_start_rule = "incitative"
        channel, guest = self._member_session()
        message = self._post(channel, "Message déplacé", guest=guest)
        Report = self.env["linkup.report"]
        report = Report.sudo().browse(
            Report.with_user(self.nicolas).action_report_livechat_visitor(
                channel.id, "harassment"
            )
        )
        self.assertEqual(report.reported_guest_id, guest)
        self.assertEqual(report.livechat_conversation_id, channel)
        self.assertEqual(report.message_id, message)
        self.assertEqual(report.reporter_id, self.nicolas)
        self.assertEqual(report._linkup_row()["member"], guest.name)
        again = Report.with_user(self.nicolas).action_report_livechat_visitor(
            channel.id, "harassment"
        )
        self.assertEqual(again, report.id)
        with self.assertLinkupCode("linkup.unavailable"):
            Report.with_user(self.sam).action_report_livechat_visitor(
                channel.id, "harassment"
            )

    def test_card_names_the_visitor(self):
        """RM2: the card of a reflection gives the visitor as a guest
        persona."""
        channel, guest = self._member_session()
        reflet = self._operator_reflet(channel)
        card = Store(reflet).get_result()["linkup.reflet"][0]
        self.assertEqual(card["recipient"], {"id": guest.id, "type": "guest"})
        self.assertEqual(
            card["author"],
            {"id": self.nicolas.partner_id.id, "type": "partner"},
        )
        self.assertTrue(card["livechat"])
        self.assertNotIn("revealed_category_ids", card)


@tagged("post_install", "-at_install")
class TestLinkupLivechatRefletRoutes(
    LinkupAltchaMixin, LinkupLivechatRefletMixin, LinkupLivechatCase, HttpCase
):
    """The routes of a visitor (RM4): the visitor comes from the cookie of
    ``mail.guest`` and acts only in a conversation they belong to."""

    def _rpc(self, route, params):
        response = self.url_open(
            route,
            data=json.dumps(
                {"jsonrpc": "2.0", "method": "call", "id": 1, "params": params}
            ),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _code(self, response):
        return response["error"]["data"]["context"].get("linkup_code")

    def _open_session(self):
        """Open a welcome session through the widget routes; return the
        conversation and its visitor, whose cookie the opener holds."""
        result = self._rpc(
            "/im_livechat/get_session",
            {
                "channel_id": self.welcome.id,
                "anonymous_name": "Visiteur",
                "chatbot_script_id": self.welcome_script.id,
                "persisted": True,
            },
        )["result"]
        channel_id = result["discuss.channel"][0]["id"]
        channel = self.Channel.sudo().browse(channel_id)
        guest = channel.channel_member_ids.guest_id
        self.assertEqual(len(guest), 1)
        self.assertIn("dgid", self.opener.cookies)
        return channel, guest

    def _join(self, channel):
        """Nicolas joins the conversation, as "Talk to a member" does."""
        channel._add_members(users=self.nicolas, post_joined_message=False)

    def test_session_of_a_visitor(self):
        """T-52 CA1: a session of the welcome channel creates a
        ``mail.guest`` and posts the welcome and its choices."""
        channel, guest = self._open_session()
        self.assertEqual(channel.livechat_channel_id, self.welcome)
        self.assertEqual(
            channel.chatbot_current_step_id,
            self._answer("welcome_step_choice"),
        )
        self.assertEqual(len(self._bot_bodies(channel)), 2)

    def test_sessions_per_address(self):
        """A visitor opens at most ``linkup.livechat_sessions_per_ip_hour``
        welcome sessions an hour from one address."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.livechat_sessions_per_ip_hour", "1"
        )
        self._open_session()
        self.opener.cookies.clear()
        result = self._rpc(
            "/im_livechat/get_session",
            {
                "channel_id": self.welcome.id,
                "anonymous_name": "Visiteur",
                "chatbot_script_id": self.welcome_script.id,
                "persisted": True,
            },
        )
        self.assertFalse(result["result"])

    def test_member_sent_to_discuss(self):
        """T-52, RM5, Q-45: a logged-in member is sent to Discuss and gets
        no session of the welcome channel."""
        self.authenticate(self.sam.login, self.sam.login)
        result = self._rpc(
            "/im_livechat/init", {"channel_id": self.welcome.id}
        )["result"]
        self.assertFalse(result["available_for_me"])
        self.assertEqual(result["linkup_redirect"], "/odoo/discuss")
        result = self._rpc(
            "/im_livechat/get_session",
            {
                "channel_id": self.welcome.id,
                "anonymous_name": "Sam",
                "chatbot_script_id": self.welcome_script.id,
            },
        )
        self.assertFalse(result["result"])

    def test_routes_of_a_visitor(self):
        """RM4, CA1, CA2: the visitor saves a draft, sends it to Nicolas,
        posts no free text before the confirmation, and reads the cards."""
        channel, guest = self._open_session()
        self._join(channel)
        params = {"channel_id": channel.id}
        refused = self._rpc(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": channel.id,
                "post_data": {
                    "body": "Bonjour",
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_comment",
                },
            },
        )
        self.assertEqual(self._code(refused), "linkup.start_rule")
        draft_id = self._rpc(
            "/linkup/v1/livechat/reflet/draft",
            dict(params, vals=dict(DRAFT, category_id=self.goals.id)),
        )["result"]
        self.assertEqual(
            self.Reflet.sudo().browse(draft_id).author_guest_id, guest
        )
        reflet_id = self._rpc("/linkup/v1/livechat/reflet/send", params)[
            "result"
        ]
        info = self._rpc("/linkup/v1/livechat/reflet/info", params)["result"]
        self.assertEqual(info["reflet_ids"], [reflet_id])
        self.assertEqual(info["linkup_start_rule"], "strict")
        self.assertFalse(info["linkup_start_rule_satisfied"])
        self.assertNotIn("revealed_category_ids", json.dumps(info["store"]))
        self.Reflet.with_user(self.nicolas).browse(
            reflet_id
        ).action_livechat_confirm()
        posted = self._rpc(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": channel.id,
                "post_data": {
                    "body": "Merci",
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_comment",
                },
            },
        )
        self.assertIn("result", posted)

    def test_visitor_confirms_through_the_route(self):
        """CA2: the visitor confirms the reflection of Nicolas through
        ``/linkup/v1/livechat/reflet/confirm``."""
        channel, guest = self._open_session()
        self._join(channel)
        reflet = self._operator_reflet(channel)
        result = self._rpc(
            "/linkup/v1/livechat/reflet/confirm",
            {"channel_id": channel.id, "reflet_id": reflet.id},
        )
        self.assertTrue(result["result"])
        self.assertEqual(reflet.state, "confirmed")

    def test_foreign_visitor_refused(self):
        """RM4: a visitor of another conversation, or without a cookie, is
        refused on every route with ``linkup.unavailable``."""
        channel, guest = self._open_session()
        self._join(channel)
        reflet = self._operator_reflet(channel)
        self.opener.cookies.clear()
        for route, params in (
            ("/linkup/v1/livechat/reflet/info", {}),
            ("/linkup/v1/livechat/reflet/send", {}),
            ("/linkup/v1/livechat/reflet/draft", {"vals": DRAFT}),
            ("/linkup/v1/livechat/reflet/confirm", {"reflet_id": reflet.id}),
        ):
            response = self._rpc(route, dict(params, channel_id=channel.id))
            self.assertEqual(self._code(response), "linkup.unavailable")
        other_channel, other = self._open_session()
        self.assertNotEqual(other, guest)
        for route, params in (
            ("/linkup/v1/livechat/reflet/info", {}),
            ("/linkup/v1/livechat/reflet/send", {}),
            ("/linkup/v1/livechat/reflet/draft", {"vals": DRAFT}),
            ("/linkup/v1/livechat/reflet/confirm", {"reflet_id": reflet.id}),
            ("/linkup/v1/livechat/reflet/reject", {"reflet_id": reflet.id}),
        ):
            response = self._rpc(route, dict(params, channel_id=channel.id))
            self.assertEqual(self._code(response), "linkup.unavailable")
        # The reflection of another conversation is not reached through
        # the conversation of the visitor either.
        response = self._rpc(
            "/linkup/v1/livechat/reflet/confirm",
            {"channel_id": other_channel.id, "reflet_id": reflet.id},
        )
        self.assertEqual(self._code(response), "linkup.unavailable")
        self.assertEqual(reflet.state, "sent")
        self.assertFalse(self.Reflet._linkup_guest_draft(other))

    def test_signup_from_the_widget(self):
        """T-52 CA3, RM4: a visitor who signs up in the same browser gets
        their draft once the address is verified; before, nothing is
        given."""
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        channel, guest = self._open_session()
        self.Reflet._linkup_guest_save_draft(
            guest, dict(DRAFT, category_id=self.goals.id)
        )
        draft = self.Reflet._linkup_guest_draft(guest)
        page = self.url_open("/web/signup")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        email = "linkup_lc_signup@example.com"
        password = "linkup-Livechat-2026"
        response = self.url_open(
            "/web/signup",
            data=dict(
                SIGNUP_FORM,
                login=email,
                name="Camille",
                password=password,
                confirm_password=password,
                csrf_token=csrf.group(1),
            ),
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (200, 303))
        user = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search([("email", "=", email)])
        )
        self.assertEqual(len(user), 1)
        self.assertEqual(user.linkup_livechat_guest_id, guest)
        self.assertFalse(user.linkup_email_verified)
        self.assertEqual(draft.author_guest_id, guest)
        self.assertFalse(draft.author_id)
        token = self._verify_token(email)
        self.url_open(f"/linkup/verify/{token}")
        self.assertTrue(user.linkup_email_verified)
        self.assertEqual(draft.author_id, user)
        self.assertFalse(draft.author_guest_id)
        info = self.Reflet.with_user(user)._linkup_draft_info()
        self.assertEqual(info["id"], draft.id)

    def _widget_signup(self, email, **extra):
        """Post the form of ``/web/signup`` from the browser of the visitor,
        whose cookie the opener keeps, with the fields of ``extra`` too."""
        page = self.url_open("/web/signup")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        return self.url_open(
            "/web/signup",
            data=dict(
                SIGNUP_FORM,
                login=email,
                name="Camille",
                password="linkup-Livechat-2026",
                confirm_password="linkup-Livechat-2026",
                csrf_token=csrf.group(1),
                **extra,
            ),
            allow_redirects=False,
        )

    @mute_logger(
        "odoo.addons.website_altcha.models.ir_http",
        "odoo.addons.mail_linkup_community.models.ir_http",
    )
    def test_signup_from_the_widget_altcha(self):
        """The "Sign up" answer of the widget leaves it for the page
        ``/web/signup``, whose form asks for the proof of work once the
        website holds an ALTCHA key: without its solution, the refusal of
        the proof and no account; with it, the account remembers the
        visitor."""
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        self.assertEqual(
            self.env.ref(
                "im_livechat_linkup_reflect.welcome_answer_signup"
            ).redirect_link,
            "/web/signup",
        )
        self._linkup_altcha_enable()
        _channel, guest = self._open_session()
        email = "linkup_lc_altcha@example.com"
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        refused = self._widget_signup(email)
        self.assertEqual(refused.status_code, 200)
        self.assertIn(
            "Could not create the account. Please try again.", refused.text
        )
        self.assertFalse(Users.search([("email", "=", email)]))
        accepted = self._widget_signup(
            email, altcha=self._linkup_altcha_solution()
        )
        self.assertNotIn("alert-danger", accepted.text)
        user = Users.search([("email", "=", email)])
        self.assertEqual(len(user), 1)
        self.assertEqual(user.linkup_livechat_guest_id, guest)
