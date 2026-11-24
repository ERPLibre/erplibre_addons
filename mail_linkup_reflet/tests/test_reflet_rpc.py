# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""What a web client obtains by forcing the RPC calls (LU-F-019 CA1,
LU-F-022 CA3, LU-F-031 RM5 and CA2, §9.4): the actions of a reflection
refused to anybody but the party whose step it is, the carrier messages
kept from edition, and the routes of Discuss that never serve the hidden
themes nor a withdrawn reflection to a reader who may not see them.
"""

import json

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import tagged
from odoo.tests.common import HttpCase, JsonRpcException
from odoo.tools import mute_logger
from requests import HTTPError

from .common import LinkupRefletCase
from .test_reflet_carrier import LinkupCarrierMixin

# What a refused call raises: a JSON-RPC error, or an HTTP error for a route
# that answers "not found".
REFUSED = (JsonRpcException, HTTPError)
# Distinctive texts of the reflection withdrawn in the tests.
WITHDRAWN_YOU_SAID = "zz-withdrawn-you-said"
WITHDRAWN_UNDERSTOOD = "zz-withdrawn-understood"


@tagged("post_install", "-at_install")
class TestLinkupRefletRpc(LinkupCarrierMixin, LinkupRefletCase, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = mail_new_test_user(
            cls.env,
            login="linkup_rpc_employee",
            name="Employee",
            groups="base.group_user",
        )

    # Helpers

    def _as(self, user):
        self.authenticate(user.login, user.login)

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

    def assertCallRefused(self, function, *args):
        """``function(*args)`` fails with a JSON-RPC error, or an HTTP
        error for a route that answers "not found"."""
        try:
            function(*args)
        except REFUSED:
            return
        self.fail(f"The call {args[0]} was not refused.")

    def _snapshot(self):
        """Everything an action may change, for every reflection."""
        self.env.invalidate_all()
        reflets = self.Reflet.sudo().search([], order="id")
        return (
            reflets.read(
                [
                    "state",
                    "response_state",
                    "guess_state",
                    "guessed_category_id",
                    "read_date",
                    "recipient_ignored",
                    "body_text",
                ]
            ),
            self.Link.sudo()
            .search([], order="id")
            .read(["state", "turn_reflet_id"]),
            self.env["linkup.reflet.secret"].sudo().search_count([]),
            self.env["mail.message"].sudo().search_count([]),
        )

    def assertRefused(self, calls):
        """Each ``(user, method, reflet, args)`` call fails and changes
        nothing."""
        before = self._snapshot()
        for user, method, reflet, args in calls:
            with self.subTest(user=user.login, method=method, id=reflet.id):
                self._as(user)
                with self.assertRaises(JsonRpcException):
                    self._call("linkup.reflet", method, [reflet.ids, *args])
                self.assertEqual(self._snapshot(), before)

    # Actions

    def test_actions_refused_to_the_wrong_person(self):
        """At each step of a chain, every action is refused to the other
        party, to a third member who shares a conversation with both, and
        to an internal user outside LinkUp; the right party then acts."""
        jacques, employee = self.jacques, self.employee
        sent = self._sent()
        draft = self._draft()
        outsiders = (jacques, employee)
        recipient_actions = (
            ("action_mark_read", []),
            ("action_confirm", []),
            ("action_reject", []),
            ("action_ignore", []),
            ("action_mark_inaccurate", ["Pas ça."]),
        )
        self.assertRefused(
            [
                (self.sam, method, sent, args)
                for method, args in recipient_actions
            ]
            + [
                (user, method, sent, args)
                for user in outsiders
                for method, args in recipient_actions
            ]
            + [
                (user, "action_withdraw", sent, [])
                for user in (self.france, *outsiders)
            ]
            + [
                (user, method, draft, args)
                for user in (self.france, *outsiders)
                for method, args in (
                    ("action_discard_draft", []),
                    ("action_send", [self.france.id]),
                    ("action_send", [user.id]),
                )
            ]
        )
        sent.with_user(self.france).action_confirm()
        answers = (
            ("action_answer_exact", ["Oui."]),
            ("action_answer_precision", ["Je précise.", [self.goals.id]]),
        )
        self.assertRefused(
            [
                (user, method, sent, args)
                for user in (self.sam, *outsiders)
                for method, args in answers
            ]
        )
        precision = self._precision(sent, codes=("goals",))
        options = (
            ("action_continue", [self.action_cat.id, "Donc tu veux."]),
            ("action_self_disclosure", [self.needs.id, "J'ai besoin."]),
            ("action_close", []),
        )
        self.assertRefused(
            [
                (user, "action_guess", precision, [self.goals.id])
                for user in (self.france, *outsiders)
            ]
            # The theme is not guessed yet: even the member whose turn it
            # will be has no option.
            + [
                (user, method, precision, args)
                for user in (self.sam, self.france, *outsiders)
                for method, args in options
            ]
        )
        precision.with_user(self.sam).action_guess(self.needs.id)
        self.assertRefused(
            [(self.sam, "action_guess", precision, [self.goals.id])]
            + [
                (user, method, precision, args)
                for user in (self.france, *outsiders)
                for method, args in options
            ]
            # The answered reflection takes no second answer.
            + [(self.france, method, sent, args) for method, args in answers]
        )
        self._as(self.sam)
        child_id = self._call("linkup.reflet", "action_close", [precision.ids])
        self.assertEqual(self.Reflet.browse(child_id).kind, "close")

    # Carrier messages

    def test_carrier_message_cannot_be_changed(self):
        """Neither party edits nor deletes a carrier message, through the
        route of Discuss or through the ORM; a plain message of the same
        conversation stays editable."""
        reflet = self._confirmed()
        precision = self._precision(reflet)
        carriers = (
            (self.sam, reflet.message_id),
            (self.france, precision.message_id),
        )
        bodies = {message.id: message.body for _user, message in carriers}
        for user, message in carriers:
            for other in (user, self.france if user == self.sam else self.sam):
                self._as(other)
                for body in ("<p>Autre chose.</p>", ""):
                    with self.subTest(user=other.login, body=body):
                        self.assertCallRefused(
                            self.make_jsonrpc_request,
                            "/mail/message/update_content",
                            {
                                "message_id": message.id,
                                "body": body,
                                "attachment_ids": [],
                            },
                        )
                with self.assertRaises(JsonRpcException):
                    self._call(
                        "mail.message",
                        "write",
                        [message.ids, {"body": "<p>Autre chose.</p>"}],
                    )
                with self.assertRaises(JsonRpcException):
                    self._call("mail.message", "unlink", [message.ids])
        self.env.invalidate_all()
        for message_id, body in bodies.items():
            message = self.env["mail.message"].browse(message_id)
            self.assertTrue(message.exists())
            self.assertEqual(message.body, body)
        self._as(self.sam)
        posted = self.make_jsonrpc_request(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": reflet.channel_id.id,
                "post_data": {"body": "Bonjour", "message_type": "comment"},
            },
        )
        message_id = posted["mail.message"][0]["id"]
        self.make_jsonrpc_request(
            "/mail/message/update_content",
            {
                "message_id": message_id,
                "body": "Bonjour France",
                "attachment_ids": [],
            },
        )
        self.assertIn(
            "Bonjour France",
            self.env["mail.message"].browse(message_id).body,
        )

    # Payloads

    def _payloads(self, user, channel):
        """What the web client of ``user`` reads of a conversation through
        the routes of Discuss and ``linkup_channel_info``."""
        self._as(user)
        return {
            "/mail/data": self.make_jsonrpc_request(
                "/mail/data",
                {"init_messaging": {}, "channels_as_member": True},
            ),
            "/discuss/channel/messages": self.make_jsonrpc_request(
                "/discuss/channel/messages", {"channel_id": channel.id}
            ),
            "/mail/starred/messages": self.make_jsonrpc_request(
                "/mail/starred/messages", {}
            ),
            "linkup_channel_info": self._call(
                "linkup.reflet", "linkup_channel_info", [channel.id]
            ),
        }

    def test_payloads_hide_themes_before_the_guess(self):
        """Before his guess, nothing Sam's client reads holds the hidden
        themes: the routes of Discuss, the LinkUp channel information, the
        starred messages, nor a read, search or grouping of the
        reflections and of their secrets."""
        reflet = self._confirmed()
        precision = self._precision(reflet)
        themes = self.goals | self.emotions
        precision.message_id.with_user(self.sam).toggle_message_starred()
        payloads = self._payloads(self.sam, reflet.channel_id)
        cards = self._cards(
            [
                (
                    None,
                    "mail.record/insert",
                    payloads["/discuss/channel/messages"]["data"],
                )
            ]
        )
        self.assertIn(precision.id, cards)
        for route, payload in payloads.items():
            with self.subTest(route=route):
                self.assertNoHiddenTheme(payload, themes)
        read = self._call(
            "linkup.reflet",
            "web_read",
            [precision.ids],
            {
                "specification": {
                    "display_name": {},
                    "revealed_category_ids": {"fields": {"code": {}}},
                    "category_id": {"fields": {"code": {}}},
                }
            },
        )
        self.assertEqual(read[0]["revealed_category_ids"], [])
        self.assertFalse(read[0]["category_id"])
        text = json.dumps(read)
        for theme in themes:
            self.assertNotIn(f'"{theme.code}"', text)
            self.assertNotIn(theme.name, text)
        # A search on the themes tells nothing: the ORM logs and drops the
        # condition on a field that is not searchable, so every category
        # gives the same count.
        with mute_logger("odoo.osv.expression"):
            counts = {
                self._call(
                    "linkup.reflet",
                    "search_count",
                    [[("revealed_category_ids", "in", category.ids)]],
                )
                for category in self.env["linkup.category"].search([])
            }
        self.assertEqual(len(counts), 1)
        # Grouping by the themes fails, as any grouping by a field that is
        # not stored; the server logs the failed request.
        with mute_logger("odoo.http"), self.assertRaises(JsonRpcException):
            self._call(
                "linkup.reflet",
                "read_group",
                [[], ["id:count"], ["revealed_category_ids"]],
            )
        for method, args in (
            ("search_read", [[], ["category_ids"]]),
            ("search_count", [[]]),
        ):
            with self.subTest(model="secret", method=method):
                with self.assertRaises(JsonRpcException):
                    self._call("linkup.reflet.secret", method, args)
        # France, its author, gets them from the same routes.
        payload = self._payloads(self.france, reflet.channel_id)
        cards = self._cards(
            [
                (
                    None,
                    "mail.record/insert",
                    payload["/discuss/channel/messages"]["data"],
                )
            ]
        )
        self.assertEqual(
            set(cards[precision.id]["revealed_category_ids"]), set(themes.ids)
        )

    def test_payloads_hide_a_withdrawn_reflection(self):
        """Once withdrawn, a reflection reaches its recipient through no
        route: neither its texts nor its category, and a direct read of
        the reflection is refused."""
        reflet = self._sent(
            category_id=self.goals.id,
            you_said=WITHDRAWN_YOU_SAID,
            understood=WITHDRAWN_UNDERSTOOD,
        )
        reflet.with_user(self.sam).action_withdraw()
        payloads = self._payloads(self.france, reflet.channel_id)
        cards = self._cards(
            [
                (
                    None,
                    "mail.record/insert",
                    payloads["/discuss/channel/messages"]["data"],
                )
            ]
        )
        self.assertEqual(cards[reflet.id]["state"], "withdrawn")
        self.assertFalse(cards[reflet.id]["category_id"])
        for route, payload in payloads.items():
            with self.subTest(route=route):
                text = json.dumps(payload)
                self.assertNotIn(WITHDRAWN_YOU_SAID, text)
                self.assertNotIn(WITHDRAWN_UNDERSTOOD, text)
        self._as(self.france)
        with self.assertRaises(JsonRpcException):
            self._call(
                "linkup.reflet",
                "read",
                [reflet.ids, ["you_said", "understood"]],
            )
        message = self._call(
            "mail.message",
            "web_read",
            [reflet.message_id.ids],
            {"specification": {"body": {}, "linkup_reflet_id": {}}},
        )
        text = json.dumps(message)
        self.assertNotIn(WITHDRAWN_YOU_SAID, text)
        self.assertNotIn(self.goals.name, text)
