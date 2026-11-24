# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The start rule (T-08, T-09, T-35; LU-F-060 to LU-F-063): a conversation
between two members opens to free text once a reflection is confirmed, and
neither the routes of Discuss nor the ORM go around it.
"""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, JsonRpcException
from odoo.tools import mute_logger

from .common import LinkupRefletCase
from .test_reflet_carrier import INSERT, same_target

PARAM = "linkup.start_rule_mode"


class LinkupStartRuleMixin:
    def _set_mode(self, mode):
        self.env["ir.config_parameter"].sudo().set_param(PARAM, mode)

    def _chat(self, user, other):
        """The direct conversation of two members, opened as the server
        does: a member alone opens it only once their link is active."""
        return (
            self.env["discuss.channel"]
            .with_user(user)
            .sudo()
            .channel_get([other.partner_id.id])
            .sudo(False)
        )

    def _post(self, channel, user, **kwargs):
        values = {
            "body": "Bonjour",
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_comment",
        }
        values.update(kwargs)
        return channel.with_user(user).message_post(**values)

    def _free_messages(self, channel):
        """The messages of ``channel`` that carry no reflection."""
        return (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", channel.id),
                    ("message_type", "!=", "notification"),
                ]
            )
            .filtered(lambda message: not message.linkup_reflet_ids)
        )


class TestLinkupStartRule(LinkupStartRuleMixin, LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")

    # LU-F-060: the mode

    def test_effective_mode(self):
        """A direct conversation follows the global mode, strict when unset;
        a group has none unless an administrator sets one (LU-F-060 CA1)."""
        chat = self._chat(self.sam, self.france)
        self.assertEqual(chat.linkup_effective_start_rule, "strict")
        self.assertEqual(self.workshop.linkup_effective_start_rule, "off")
        for mode in ("incitative", "off", "strict"):
            self._set_mode(mode)
            self.assertEqual(chat._linkup_start_rule(), mode)
            self.assertEqual(self.workshop._linkup_start_rule(), "off")
        self._set_mode("unknown")
        self.assertEqual(chat._linkup_start_rule(), "strict")
        self.workshop.linkup_start_rule = "strict"
        chat.sudo().linkup_start_rule = "off"
        self.assertEqual(self.workshop._linkup_start_rule(), "strict")
        self.assertEqual(chat._linkup_start_rule(), "off")

    def test_member_cannot_change_the_mode(self):
        """Only a LinkUp administrator sets the mode of a conversation
        (LU-F-060 RM5, CA2)."""
        chat = self._chat(self.sam, self.france)
        for channel in (chat, self.workshop):
            with self.subTest(channel=channel.channel_type):
                with self.assertRaises(AccessError):
                    channel.with_user(self.sam).write(
                        {"linkup_start_rule": "off"}
                    )
        self.assertEqual(chat.sudo().linkup_start_rule, "inherit")
        settings = self.env["res.config.settings"].create(
            {"linkup_start_rule_mode": "incitative"}
        )
        settings.execute()
        self.assertEqual(
            self.env["ir.config_parameter"].get_param(PARAM), "incitative"
        )

    # LU-F-061: strict

    def test_strict_refuses_free_text(self):
        """Without a confirmed reflection, a member posts no free text in
        strict mode, whatever its type, with an attachment as well; a
        sent reflection is not enough (LU-F-061 RM1, RM3)."""
        chat = self._chat(self.sam, self.france)
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": "note.txt",
                    "raw": b"note",
                    "res_model": "discuss.channel",
                    "res_id": chat.id,
                }
            )
        )
        attempts = (
            {},
            {"message_type": "user_notification", "partner_ids": []},
            {"message_type": "email"},
            {"body": "", "attachment_ids": attachment.ids},
        )
        for user in (self.sam, self.france):
            for kwargs in attempts:
                with self.subTest(user=user.name, kwargs=kwargs):
                    with self.assertLinkupCode("linkup.start_rule"):
                        self._post(chat, user, **kwargs)
        self._sent()
        with self.assertLinkupCode("linkup.start_rule"):
            self._post(chat, self.france)
        self.assertFalse(self._free_messages(chat))

    def test_confirmed_reflection_opens_the_conversation(self):
        """Once a reflection of the pair is confirmed, both members post
        freely, and the conversation receives its satisfied rule
        (LU-F-061 CA6)."""
        reflet = self._sent()
        chat = reflet.channel_id
        info = chat.with_user(self.sam)._channel_basic_info()
        self.assertEqual(info["linkup_start_rule"], "strict")
        self.assertFalse(info["linkup_start_rule_satisfied"])
        self._bus_reset()
        reflet.with_user(self.france).action_confirm()
        threads = [
            thread
            for target, kind, payload in self._bus_sent()
            if same_target(target, chat) and kind == INSERT
            for thread in payload.get("discuss.channel", [])
        ]
        self.assertIn(
            True, [t.get("linkup_start_rule_satisfied") for t in threads]
        )
        self.assertTrue(
            chat.with_user(self.france)._channel_basic_info()[
                "linkup_start_rule_satisfied"
            ]
        )
        for user in (self.sam, self.france):
            message = self._post(chat, user)
            self.assertEqual(message.message_type, "comment")

    def test_server_notifications_pass(self):
        """A notification the server posts for a member, such as the pin of
        a message, is not free text (LU-F-061 RM2)."""
        reflet = self._sent()
        chat = reflet.channel_id
        chat.with_user(self.sam).set_message_pin(reflet.message_id.id, True)
        self.assertTrue(
            self.env["mail.message"].search_count(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", chat.id),
                    ("message_type", "=", "notification"),
                ]
            )
        )

    def test_reflections_go_through_strict(self):
        """Every reflection of a pair posts its carrier in strict mode,
        before and after the confirmation (LU-F-061 RM6)."""
        reflet = self._confirmed()
        answer = self._child(
            reflet.with_user(self.france).action_answer_exact("Oui.")
        )
        self.assertTrue(reflet.message_id)
        self.assertTrue(answer.message_id)

    def test_strict_in_a_group(self):
        """A group set to strict opens to a member who has an active link
        with another of its members (LU-F-060 RM4)."""
        self.workshop.linkup_start_rule = "strict"
        for user in (self.sam, self.jacques):
            with self.assertLinkupCode("linkup.start_rule"):
                self._post(self.workshop, user)
        self._confirmed()
        self._post(self.workshop, self.sam)
        self._post(self.workshop, self.france)
        with self.assertLinkupCode("linkup.start_rule"):
            self._post(self.workshop, self.jacques)

    def test_outside_linkup_and_off(self):
        """The rule binds two restricted members: a direct conversation with
        a system administrator, or a conversation set to off, is open."""
        chat = (
            self.env["discuss.channel"]
            .with_user(self.admin)
            .channel_get([self.sam.partner_id.id])
        )
        self._post(chat, self.sam)
        chat = self._chat(self.sam, self.france)
        chat.sudo().linkup_start_rule = "off"
        self._post(chat, self.sam)

    # LU-F-062: incentive

    def test_incitative_accepts_free_text(self):
        """In incentive mode the free text goes, and the conversation still
        reads as not opened by a reflection (T-09, LU-F-062 CA1)."""
        self._set_mode("incitative")
        chat = self._chat(self.sam, self.france)
        message = self._post(chat, self.sam)
        self.assertEqual(message.body, "<p>Bonjour</p>")
        info = chat.with_user(self.sam)._channel_basic_info()
        self.assertEqual(info["linkup_start_rule"], "incitative")
        self.assertFalse(info["linkup_start_rule_satisfied"])
        self.assertFalse(self.events)

    # LU-F-061 RM5 and LU-F-063 RM3: the ORM and the calls

    def test_orm_does_not_post(self):
        """A member neither creates the message of a conversation nor
        rewrites one through the ORM, even in an opened conversation
        (LU-F-061 RM5, CA4)."""
        reflet = self._confirmed()
        chat = reflet.channel_id
        Message = self.env["mail.message"].with_user(self.sam)
        with self.assertRaises(AccessError):
            Message.create(
                {
                    "model": "discuss.channel",
                    "res_id": chat.id,
                    "body": "Bonjour",
                    "message_type": "comment",
                }
            )
        message = self._post(chat, self.sam)
        for vals in ({"body": "Autre"}, {"res_id": self.workshop.id}):
            with self.subTest(vals=vals):
                with self.assertRaises(AccessError):
                    message.with_user(self.sam).write(vals)
        other = (
            self.env["mail.message"]
            .sudo()
            .create(
                {
                    "model": "res.partner",
                    "res_id": self.sam.partner_id.id,
                    "body": "Note",
                    "author_id": self.sam.partner_id.id,
                }
            )
        )
        with self.assertRaises(AccessError):
            other.with_user(self.sam).write(
                {"model": "discuss.channel", "res_id": chat.id}
            )

    def test_call_refused_without_link(self):
        """A member neither starts nor joins a call in a strict conversation
        that no reflection opened (LU-F-061 CA5, LU-F-063 RM3). The route
        joins under ``sudo``, as the member."""
        reflet = self._sent()
        chat = reflet.channel_id
        member = chat.sudo().channel_member_ids.filtered(
            lambda m: m.partner_id == self.sam.partner_id
        )
        with self.assertLinkupCode("linkup.start_rule"):
            member.with_user(self.sam).sudo()._rtc_join_call()
        self.assertFalse(chat.sudo().rtc_session_ids)
        reflet.with_user(self.france).action_confirm()
        member.with_user(self.sam).sudo()._rtc_join_call()
        self.assertTrue(chat.sudo().rtc_session_ids)


@tagged("post_install", "-at_install")
class TestLinkupStartRuleRpc(LinkupStartRuleMixin, LinkupRefletCase, HttpCase):
    """What a web client obtains by forcing the routes in strict mode (T-08,
    LU-F-061 CA2 to CA4)."""

    def _as(self, user):
        self.authenticate(user.login, user.login)

    def _post_route(self, channel, post_data, context=None):
        params = {
            "thread_model": "discuss.channel",
            "thread_id": channel.id,
            "post_data": post_data,
        }
        if context is not None:
            params["context"] = context
        return self.make_jsonrpc_request("/mail/message/post", params)

    def _call(self, model, method, args, kwargs=None):
        return self.make_jsonrpc_request(
            f"/web/dataset/call_kw/{model}/{method}",
            {
                "model": model,
                "method": method,
                "args": args,
                "kwargs": kwargs or {},
            },
        )

    @mute_logger("odoo.http")
    def test_routes_refused_in_strict(self):
        """The post route, its context and its message type, a remote
        ``message_post`` and the ORM all fail before a confirmation, and the
        same post route works after it."""
        reflet = self._sent()
        chat = reflet.channel_id
        self._as(self.sam)
        attempts = (
            ({"body": "Bonjour", "message_type": "comment"}, None),
            ({"body": "Bonjour"}, {"linkup_reflet_post": True}),
            (
                {
                    "body": "Bonjour",
                    "message_type": "notification",
                    "subtype_xmlid": "mail.mt_note",
                },
                None,
            ),
        )
        for post_data, context in attempts:
            with self.subTest(post_data=post_data, context=context):
                with self.assertRaises(JsonRpcException):
                    self._post_route(chat, post_data, context)
        with self.assertRaises(JsonRpcException):
            self._call(
                "discuss.channel",
                "message_post",
                [chat.ids],
                {"body": "Bonjour", "message_type": "notification"},
            )
        with self.assertRaises(JsonRpcException):
            self._call(
                "mail.message",
                "create",
                [
                    {
                        "model": "discuss.channel",
                        "res_id": chat.id,
                        "body": "Bonjour",
                        "message_type": "comment",
                    }
                ],
            )
        with self.assertRaises(JsonRpcException):
            self._call(
                "mail.message",
                "write",
                [reflet.message_id.ids, {"body": "<p>Autre chose.</p>"}],
            )
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(
                "/mail/rtc/channel/join_call", {"channel_id": chat.id}
            )
        self.assertFalse(self._free_messages(chat))
        reflet.with_user(self.france).action_confirm()
        posted = self._post_route(
            chat, {"body": "Bonjour", "message_type": "notification"}
        )
        message = self.env["mail.message"].browse(
            posted["mail.message"][0]["id"]
        )
        self.assertEqual(message.message_type, "comment")
        self.assertEqual(message.subtype_id, self.env.ref("mail.mt_comment"))

    def test_incitative_route(self):
        """In incentive mode, the post route takes the free text."""
        self._set_mode("incitative")
        chat = self._chat(self.sam, self.france)
        self._as(self.sam)
        self._post_route(chat, {"body": "Bonjour"})
        self.assertEqual(len(self._free_messages(chat)), 1)

    def test_user_outside_linkup_keeps_the_route(self):
        """An internal user outside LinkUp posts as before."""
        employee = mail_new_test_user(
            self.env,
            login="linkup_sr_employee",
            name="Employee",
            groups="base.group_user",
        )
        chat = (
            self.env["discuss.channel"]
            .with_user(employee)
            .channel_get([self.env.ref("base.user_admin").partner_id.id])
        )
        self._as(employee)
        posted = self._post_route(
            chat, {"body": "Bonjour", "message_type": "comment"}
        )
        self.assertTrue(posted["mail.message"])
