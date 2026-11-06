# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The conversation of distress with a moderator (T-54, LU-F-126, Q-44):
opened by the server with an available moderator in no conflict of
interest, the help resources without one, no start rule, the opening in
the audit log, and a distress channel nobody reaches but the server."""

import json

from odoo.addons.im_livechat_linkup_reflect.authorization import (
    distress_operators,
)
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import LinkupLivechatCase


class LinkupDistressMixin:
    def _distress(self, reporter, about=None, **kwargs):
        """A report of distress of ``reporter`` about the member
        ``about``."""
        about = about or self.sam
        Report = self.env["linkup.report"]
        return Report.browse(
            Report.with_user(reporter).action_create_report(
                user_id=about.id, reason="distress", **kwargs
            )
        ).sudo()

    def _distress_conversations(self):
        return self.Channel.sudo().search(
            [("livechat_channel_id", "=", self.distress.id)]
        )


@tagged("post_install", "-at_install")
class TestLinkupLivechatDistress(LinkupDistressMixin, LinkupLivechatCase):
    def setUp(self):
        super().setUp()
        # Joanna shares a link with France; Thomas with Sam.
        self.Link._get_or_create(self.joanna, self.france)

    def test_conflicted_moderator_never_chosen(self):
        """CA1, RM2: Jean, Joanna and Thomas online, Joanna linked to
        France, Thomas linked to Sam; France reports Sam in distress: the
        conversation opens with Jean, the only moderator in no conflict."""
        self._online(self.jean, self.joanna, self.thomas)
        report = self._distress(self.france)
        conversation = report.distress_channel_id
        self.assertTrue(conversation)
        self.assertEqual(conversation.channel_type, "livechat")
        self.assertEqual(conversation.livechat_channel_id, self.distress)
        self.assertEqual(
            conversation.livechat_operator_id, self.jean.partner_id
        )
        self.assertEqual(
            conversation.channel_member_ids.partner_id,
            self.france.partner_id | self.jean.partner_id,
        )
        self.assertTrue(report.urgent)

    def test_excluded_previous_operator_ignored(self):
        """RM2: a ``previous_operator_id`` that names a moderator in
        conflict is ignored; one in no conflict is preferred."""
        self._online(self.jean, self.joanna)
        report = self._distress(
            self.france, previous_operator_id=self.joanna.partner_id.id
        )
        self.assertEqual(
            report.distress_channel_id.livechat_operator_id,
            self.jean.partner_id,
        )

    def test_reporter_and_reported_excluded(self):
        """RM2: a moderator who reports, or who is reported, is no operator
        of that distress."""
        self._online(self.jean, self.joanna)
        report = self._distress(self.jean, about=self.joanna)
        self.assertFalse(report.distress_channel_id)
        self.assertTrue(report.urgent)

    def test_no_moderator_available(self):
        """CA2, RM3, Q-44: without a moderator online, no conversation is
        created; the reporter reads the help resources, and the report
        waits, urgent, in the queue."""
        report = self._distress(self.sam, about=self.france)
        self.assertFalse(report.distress_channel_id)
        self.assertFalse(self._distress_conversations())
        self.assertTrue(report.urgent)
        self.assertEqual(report.state, "new")
        info = (
            self.env["linkup.report"]
            .with_user(self.sam)
            .linkup_distress_info(report.id)
        )
        self.assertTrue(info["queued"])
        self.assertFalse(info["channel_id"])
        self.assertTrue(any("9-8-8" in line for line in info["resources"]))
        self.assertIn(report.id, self._queue_ids(self.jean))

    def test_distress_info_of_the_reporter_only(self):
        """The state of a distress is read by its reporter alone."""
        report = self._distress(self.sam, about=self.france)
        with self.assertLinkupCode("linkup.unavailable"):
            self.env["linkup.report"].with_user(
                self.france
            ).linkup_distress_info(report.id)

    def test_off_and_audited(self):
        """RM4, CA4: the conversation has no start rule, so Sam writes free
        text at once, the global rule being strict; its opening is in the
        audit log of the report; it reminds that LinkUp is not an
        emergency service."""
        self._online(self.jean)
        report = self._distress(self.sam, about=self.france)
        conversation = report.distress_channel_id
        self.assertEqual(conversation._linkup_start_rule(), "off")
        message = self._post(
            conversation, "J'ai besoin d'aide.", user=self.sam
        )
        self.assertTrue(message)
        self._post(conversation, "Je suis là.", user=self.jean)
        audit = self.Audit.sudo().search(
            [("report_id", "=", report.id), ("action", "=", "distress_open")]
        )
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit.res_model, "discuss.channel")
        self.assertEqual(audit.res_id, conversation.id)
        self.assertTrue(
            any(
                "emergency" in body
                for body in conversation.message_ids.mapped("body")
            )
        )

    def test_one_conversation_per_report(self):
        """A report already holding an open conversation keeps it."""
        self._online(self.jean)
        report = self._distress(self.sam, about=self.france)
        again = self._distress(self.sam, about=self.france)
        self.assertEqual(again, report)
        self.assertEqual(len(self._distress_conversations()), 1)

    def test_other_reasons_open_nothing(self):
        """RM1: only a report of distress opens a conversation."""
        self._online(self.jean)
        Report = self.env["linkup.report"]
        Report.with_user(self.sam).action_create_report(
            user_id=self.france.id, reason="harassment"
        )
        self.assertFalse(self._distress_conversations())

    def test_distress_channel_has_no_operator_outside_the_server(self):
        """RM5: outside the opening by the server, the distress channel has
        no operator, a moderator being online or not."""
        self._online(self.jean, self.joanna)
        self.assertIsNone(distress_operators())
        self.assertFalse(self.distress.available_operator_ids)
        self.assertFalse(self.distress._get_operator())
        self.assertFalse(
            self.distress.sudo()._get_livechat_discuss_channel_vals(
                "Visiteur", previous_operator_id=self.jean.partner_id.id
            )
        )

    def test_conversation_readable_by_its_parties_only(self):
        """RM5: a live chat manager, a moderator who does not operate it
        and a visitor of another conversation read neither the distress
        conversation nor its members, by search or by id."""
        self._online(self.jean)
        report = self._distress(self.sam, about=self.france)
        conversation = report.distress_channel_id
        self.luce.sudo().groups_id = [
            (4, self.env.ref("im_livechat.im_livechat_group_manager").id)
        ]
        welcome, _guest = self._welcome_session()
        for user in (self.luce, self.joanna):
            Channel = self.Channel.with_user(user)
            found = Channel.search([("channel_type", "=", "livechat")])
            self.assertNotIn(conversation, found)
            self.assertFalse(
                self.env["discuss.channel.member"]
                .with_user(user)
                .search([("channel_id", "=", conversation.id)])
            )
            with self.assertRaises(AccessError):
                conversation.with_user(user).check_access("read")
            self.assertFalse(
                self.env["mail.message"]
                .with_user(user)
                .search(
                    [
                        ("model", "=", "discuss.channel"),
                        ("res_id", "=", conversation.id),
                    ]
                )
            )
        # The live chat manager still reads the welcome conversation.
        self.assertIn(
            welcome,
            self.Channel.with_user(self.luce).search(
                [("channel_type", "=", "livechat")]
            ),
        )
        other = self._visitor("Autre")
        with self.assertRaises(AccessError):
            self._as_visitor(conversation, other).check_access("read")
        for user in (self.sam, self.jean):
            conversation.with_user(user).check_access("read")
            self.assertEqual(
                len(
                    self.env["discuss.channel.member"]
                    .with_user(user)
                    .search([("channel_id", "=", conversation.id)])
                ),
                2,
            )

    def test_administrator_in_conflict_never_chosen(self):
        """RM2: the administrator of Odoo, a moderator through the LinkUp
        administrator group, is excluded as any moderator in conflict:
        linked to France and alone online, they open nothing; once Jean is
        online too, the report of France opens with Jean, even with the
        administrator named by ``previous_operator_id``."""
        admin = self.env.ref("base.user_admin")
        self.assertIn(admin, self.distress._linkup_moderators())
        self.Link._get_or_create(admin, self.france)
        self._online(admin)
        report = self._distress(
            self.france, previous_operator_id=admin.partner_id.id
        )
        self.assertFalse(report.distress_channel_id)
        self._online(admin, self.jean)
        report = self._distress(
            self.france, previous_operator_id=admin.partner_id.id
        )
        self.assertEqual(
            report.distress_channel_id.livechat_operator_id,
            self.jean.partner_id,
        )

    def test_distress_not_reached_by_bus_nor_attachment(self):
        """RM5: a live chat manager neither subscribes to the bus of a
        distress conversation nor reads its attachments; its parties do."""
        self._online(self.jean)
        report = self._distress(self.sam, about=self.france)
        conversation = report.distress_channel_id
        self.luce.sudo().groups_id = [
            (4, self.env.ref("im_livechat.im_livechat_group_manager").id)
        ]
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": "aide.txt",
                    "raw": b"Aide",
                    "res_model": "discuss.channel",
                    "res_id": conversation.id,
                }
            )
        )
        for user, reached in ((self.luce, False), (self.jean, True)):
            # The search of ``ir.websocket._build_bus_channel_list`` for a
            # subscription to ``discuss.channel_<id>``.
            channels = self.Channel.with_user(user).search(
                ["|", ("is_member", "=", True), ("id", "in", conversation.ids)]
            )
            self.assertEqual(conversation in channels, reached)
            if reached:
                attachment.with_user(user).check("read")
            else:
                with self.assertRaises(AccessError):
                    attachment.with_user(user).check("read")

    def test_help_step_never_moves_a_member_conversation(self):
        """RM1, RM2: once Nicolas operates the welcome conversation, its
        script does not restart, and the step "Need help now", reached
        anyway, leaves the report urgent in the queue and posts the
        resources: no moderator joins a conversation of three people."""
        self._online(self.jean)
        channel, guest = self._member_session()
        with self.assertLinkupCode("linkup.unavailable"):
            self._as_visitor(channel, guest)._chatbot_restart(
                self.welcome_script
            )
        visitor_channel = self._as_visitor(channel, guest).sudo()
        step = self._answer("welcome_step_help").with_env(visitor_channel.env)
        step._linkup_forward_moderator(visitor_channel)
        self.assertEqual(channel.livechat_channel_id, self.welcome)
        self.assertNotIn(
            self.jean.partner_id, channel.channel_member_ids.partner_id
        )
        report = self.Report.sudo().search(
            [("reporter_guest_id", "=", guest.id)]
        )
        self.assertTrue(report.urgent)
        self.assertFalse(report.distress_channel_id)
        self.assertIn("9-8-8", self._bot_bodies(channel)[-1])

    def test_visitor_needs_help(self):
        """RM1, RM4: "Need help now" of a visitor creates the urgent report
        of the visitor, then brings Jean into the conversation, which joins
        the distress channel without start rule; the opening is
        audited."""
        self._online(self.jean)
        channel, guest = self._welcome_session()
        self._chatbot(
            channel,
            "Need help now",
            answer=self._answer("welcome_answer_help"),
            guest=guest,
        )
        report = self.Report.sudo().search(
            [("reporter_guest_id", "=", guest.id)]
        )
        self.assertEqual(len(report), 1)
        self.assertTrue(report.urgent)
        self.assertEqual(report.reason, "distress")
        self.assertFalse(report.reporter_id)
        self.assertEqual(report.distress_channel_id, channel)
        self.assertEqual(channel.livechat_channel_id, self.distress)
        self.assertIn(
            self.jean.partner_id, channel.channel_member_ids.partner_id
        )
        self.assertEqual(channel._linkup_start_rule(), "off")
        self._post(channel, "Je ne vais pas bien.", guest=guest)
        self.assertTrue(
            self.Audit.sudo().search_count(
                [
                    ("report_id", "=", report.id),
                    ("action", "=", "distress_open"),
                ]
            )
        )
        self.assertIn(report.id, self._queue_ids(self.joanna))
        detail = self.Report.with_user(self.joanna).linkup_moderation_detail(
            report.id
        )
        self.assertEqual(detail["reporter"], guest.name)
        self.assertTrue(detail["urgent"])

    def test_visitor_needs_help_without_moderator(self):
        """RM3, Q-44: without a moderator online, the visitor reads the
        help resources at once and the request waits, urgent."""
        channel, guest = self._welcome_session()
        self._chatbot(
            channel,
            "Need help now",
            answer=self._answer("welcome_answer_help"),
            guest=guest,
        )
        report = self.Report.sudo().search(
            [("reporter_guest_id", "=", guest.id)]
        )
        self.assertTrue(report.urgent)
        self.assertFalse(report.distress_channel_id)
        self.assertEqual(channel.livechat_channel_id, self.welcome)
        body = self._bot_bodies(channel)[-1]
        self.assertIn("9-8-8", body)
        self.assertIn("queue", body)
        self.assertEqual(
            channel.channel_member_ids.partner_id.user_ids.filtered(
                lambda user: not user.share
            ),
            self.env["res.users"],
        )

    def test_help_resources_of_the_settings(self):
        """RM3: the resources are those of ``linkup.help_resources`` once
        set, one per line."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.help_resources", "Ligne A\n\nLigne B"
        )
        self.assertEqual(
            self.env["linkup.report"]._linkup_help_resources(),
            ["Ligne A", "Ligne B"],
        )


@tagged("post_install", "-at_install")
class TestLinkupLivechatDistressRoutes(
    LinkupDistressMixin, LinkupLivechatCase, HttpCase
):
    """``/im_livechat/*`` never opens nor offers the distress channel;
    ``/linkup/v1/report`` answers a distress with the conversation or the
    resources."""

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

    def _get_session(self, channel, route="/im_livechat/get_session", **extra):
        params = {
            "channel_id": channel.id,
            "anonymous_name": "Visiteur",
            "persisted": True,
        }
        params.update(extra)
        return self._rpc(route, params)

    def test_get_session_refused_on_distress(self):
        """CA3: ``get_session`` on the distress channel creates no
        conversation, for a visitor, a visitor of a welcome conversation,
        a member, the CORS route and a chatbot script given by the
        client."""
        self._online(self.jean, self.joanna)
        before = self._distress_conversations()
        self.assertFalse(self._get_session(self.distress).get("result"))
        self.assertTrue(
            self._get_session(
                self.welcome, chatbot_script_id=self.welcome_script.id
            ).get("result")
        )
        self.assertFalse(
            self._get_session(
                self.distress,
                previous_operator_id=self.jean.partner_id.id,
                chatbot_script_id=self.welcome_script.id,
            ).get("result")
        )
        self.assertFalse(
            self._get_session(
                self.distress, route="/im_livechat/cors/get_session"
            ).get("result")
        )
        self.authenticate(self.sam.login, self.sam.login)
        self.assertFalse(self._get_session(self.distress).get("result"))
        self.assertEqual(self._distress_conversations(), before)

    def test_init_and_pages_hide_distress(self):
        """RM5: ``init`` offers nothing on the distress channel; its page
        and its loader do not exist."""
        self._online(self.jean)
        result = self._rpc(
            "/im_livechat/init", {"channel_id": self.distress.id}
        )["result"]
        self.assertFalse(result["available_for_me"])
        self.assertFalse(result["rule"])
        with mute_logger("odoo.http"):
            for url in (
                f"/im_livechat/support/{self.distress.id}",
                f"/im_livechat/loader/{self.distress.id}",
            ):
                self.assertEqual(self.url_open(url).status_code, 404)
        self.assertEqual(
            self.url_open(
                f"/im_livechat/support/{self.welcome.id}"
            ).status_code,
            200,
        )

    def test_help_answer_ends_the_script(self):
        """RM1: "Need help now" chosen in the widget brings Jean through
        ``/chatbot/step/trigger``, which ends the script there, so that the
        widget triggers no further step that would close the conversation
        of distress."""
        self._online(self.jean)
        result = self._get_session(
            self.welcome, chatbot_script_id=self.welcome_script.id
        )["result"]
        channel = self.Channel.sudo().browse(
            result["discuss.channel"][0]["id"]
        )
        answer = self._answer("welcome_answer_help")
        posted = self._rpc(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": channel.id,
                "post_data": {
                    "body": answer.name,
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_comment",
                },
            },
        )["result"]
        choice = channel.chatbot_message_ids.filtered(
            lambda message: message.script_step_id
            == self._answer("welcome_step_choice")
            and message.mail_message_id.author_id == self.bot
        )
        self._rpc(
            "/chatbot/answer/save",
            {
                "channel_id": channel.id,
                "message_id": choice.mail_message_id.id,
                "selected_answer_id": answer.id,
            },
        )
        self.assertTrue(posted)
        steps = self._rpc(
            "/chatbot/step/trigger",
            {
                "channel_id": channel.id,
                "chatbot_script_id": self.welcome_script.id,
            },
        )["result"]["ChatbotStep"]
        self.env.invalidate_all()
        self.assertTrue(all(step["operatorFound"] for step in steps))
        self.assertEqual(channel.livechat_channel_id, self.distress)
        self.assertTrue(channel.livechat_active)
        self.assertIn(
            self.jean.partner_id, channel.channel_member_ids.partner_id
        )
        restart = self._rpc(
            "/chatbot/restart",
            {
                "channel_id": channel.id,
                "chatbot_script_id": self.welcome_script.id,
            },
        )
        self.assertIn("error", restart)
        self.env.invalidate_all()
        self.assertEqual(channel.livechat_channel_id, self.distress)

    def test_report_route_answers_distress(self):
        """RM1, RM3: ``/linkup/v1/report`` answers a distress with the
        conversation opened, or with the resources and the queue."""
        self.authenticate(self.sam.login, self.sam.login)
        result = self._rpc(
            "/linkup/v1/report",
            {"reason": "distress", "user_id": self.france.id},
        )["result"]
        self.assertTrue(result["urgent"])
        self.assertTrue(result["distress"]["queued"])
        self.assertTrue(result["distress"]["resources"])
        self._online(self.jean)
        self.authenticate(self.france.login, self.france.login)
        result = self._rpc(
            "/linkup/v1/report",
            {"reason": "distress", "user_id": self.sam.id},
        )["result"]
        self.assertFalse(result["distress"]["queued"])
        conversation = self.Channel.sudo().browse(
            result["distress"]["channel_id"]
        )
        self.assertEqual(conversation.livechat_channel_id, self.distress)
        self.assertEqual(
            conversation.livechat_operator_id, self.jean.partner_id
        )
