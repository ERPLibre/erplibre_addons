# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The start rule against the other ways of Discuss (T-08, LU-F-061 RM1 to
RM5, LU-F-063): a reply, a notification written by the client, the full
composer, a scheduled message, a reaction, an edition, a group or a channel
of one's own carry no free text into a conversation that the rule keeps
closed.
"""

from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, JsonRpcException
from odoo.tools import mute_logger

from .common import LinkupRefletCase
from .test_start_rule import LinkupStartRuleMixin


class TestLinkupStartRuleBypass(LinkupStartRuleMixin, LinkupRefletCase):
    def _strict_chat(self):
        """A reflection of Sam waits for France: their direct conversation
        exists and the start rule keeps it closed."""
        reflet = self._sent()
        return reflet, reflet.channel_id

    def test_reply_and_client_notification(self):
        """A reply to the carrier of a reflection, and a post that names
        itself a ``notification``, are free text (LU-F-061 RM1)."""
        reflet, chat = self._strict_chat()
        with self.assertLinkupCode("linkup.start_rule"):
            self._post(chat, self.france, parent_id=reflet.message_id.id)
        for user in (self.sam, self.france):
            with self.subTest(user=user.name):
                with self.assertLinkupCode("linkup.start_rule"):
                    self._post(chat, user, message_type="notification")
        self.assertFalse(self._free_messages(chat))

    def test_full_composer(self):
        """The composer of a document posts on the conversation through
        ``message_post``, with the type it carries: refused whatever the
        type."""
        _reflet, chat = self._strict_chat()
        for message_type in ("notification", "comment"):
            with self.subTest(message_type=message_type):
                composer = (
                    self.env["mail.compose.message"]
                    .with_user(self.sam)
                    .with_context(
                        default_model="discuss.channel",
                        default_res_ids=chat.ids,
                        default_composition_mode="comment",
                    )
                    .create({"body": "Bonjour", "message_type": message_type})
                )
                with self.assertLinkupCode("linkup.start_rule"):
                    composer.action_send_mail()
        self.assertFalse(self._free_messages(chat))

    def test_scheduled_message(self):
        """A scheduled message posts as a ``notification`` of its author:
        refused when it is sent."""
        _reflet, chat = self._strict_chat()
        scheduled = (
            self.env["mail.scheduled.message"]
            .with_user(self.sam)
            .create(
                {
                    "model": "discuss.channel",
                    "res_id": chat.id,
                    "body": "Bonjour",
                    "author_id": self.sam.partner_id.id,
                    "scheduled_date": fields.Datetime.now()
                    + timedelta(hours=1),
                }
            )
        )
        with self.assertLinkupCode("linkup.start_rule"):
            scheduled.with_user(self.sam).post_message()
        self.assertFalse(self._free_messages(chat))

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_message_notify(self):
        """``message_notify`` creates the message without ``message_post``:
        the ORM refuses it, called on the conversation or on its model."""
        _reflet, chat = self._strict_chat()
        values = {
            "body": "Bonjour",
            "partner_ids": self.france.partner_id.ids,
        }
        with self.assertRaises(AccessError):
            chat.with_user(self.sam).message_notify(**values)
        with self.assertRaises(AccessError):
            self.env["mail.thread"].with_user(self.sam).message_notify(
                model="discuss.channel", res_id=chat.id, **values
            )
        self.assertFalse(self._free_messages(chat))

    def test_reaction(self):
        """The content of a reaction is a text of the client: none is added
        before the confirmation, one is after it (LU-F-063 RM4)."""
        reflet, chat = self._strict_chat()
        message = reflet.message_id

        def react(user, content):
            message.with_user(user).sudo()._message_reaction(
                content, "add", user.partner_id, self.env["mail.guest"]
            )

        for user in (self.sam, self.france):
            with self.subTest(user=user.name):
                with self.assertLinkupCode("linkup.start_rule"):
                    react(user, "Appelle-moi ce soir")
        self.assertFalse(message.sudo().reaction_ids)
        reflet.with_user(self.france).action_confirm()
        react(self.france, "👍")
        self.assertEqual(message.sudo().reaction_ids.content, "👍")

    def test_edit_once_strict(self):
        """A comment posted in incentive mode takes no new text once the
        conversation turns strict (LU-F-061 RM5)."""
        self._set_mode("incitative")
        chat = self._chat(self.sam, self.france)
        message = self._post(chat, self.sam)
        self._set_mode("strict")
        with self.assertLinkupCode("linkup.start_rule"):
            chat.with_user(self.sam)._message_update_content(
                message, body="Appelle-moi"
            )
        self.assertEqual(message.body, "<p>Bonjour</p>")

    def test_group_needs_a_link(self):
        """A group holds no free exchange that the direct conversation
        refuses: a member adds to a group, new or existing, only the people
        of a confirmed reflection, and never a blocked one (LU-F-063 RM1,
        CA1)."""
        Channel = self.env["discuss.channel"].with_user(self.sam)
        orchard = self.env["discuss.channel"].create(
            {
                "name": "Verger",
                "channel_type": "group",
                "channel_partner_ids": [
                    Command.link(self.sam.partner_id.id),
                    Command.link(self.jacques.partner_id.id),
                ],
            }
        )
        france = self.france.partner_id
        attempts = (
            lambda: Channel.create_group(france.ids),
            lambda: Channel.create(
                {
                    "name": "Verger",
                    "channel_type": "group",
                    "channel_partner_ids": [Command.link(france.id)],
                }
            ),
            lambda: orchard.with_user(self.sam).add_members(
                partner_ids=france.ids
            ),
        )
        for attempt in attempts:
            with self.assertRaises(AccessError):
                attempt()
        reflet = self._confirmed()
        group = Channel.create_group(france.ids)
        self.assertIn(france, group.channel_member_ids.partner_id)
        orchard.with_user(self.sam).add_members(partner_ids=france.ids)
        self.assertIn(france, orchard.channel_member_ids.partner_id)
        reflet.link_id.sudo().state = "blocked"
        with self.assertRaises(AccessError):
            Channel.create_group(france.ids)

    def test_member_creates_no_channel(self):
        """A member creates no channel and changes the type of no
        conversation (LU-F-063 RM2, CA2)."""
        Channel = self.env["discuss.channel"].with_user(self.sam)
        with self.assertRaises(AccessError):
            Channel.channel_create("Place publique", None)
        with self.assertRaises(AccessError):
            Channel.create({"name": "Place", "channel_type": "channel"})
        with self.assertRaises(AccessError):
            Channel.create({"name": "Place"})
        with self.assertRaises(AccessError):
            Channel.sudo().with_context(default_channel_type="channel").create(
                {"name": "Place"}
            )
        with self.assertRaises(AccessError):
            Channel.with_context(default_parent_channel_id=False).create(
                {"name": "Place"}
            )
        self.assertFalse(
            self.env["discuss.channel"].search([("name", "=", "Place")])
        )
        with self.assertRaises(AccessError):
            self.workshop.with_user(self.sam).write(
                {"channel_type": "channel"}
            )
        self.assertEqual(self.workshop.channel_type, "group")

    def test_chat_opened_by_its_member(self):
        """A member opens no direct conversation between two other people,
        even when the creation skips adding its author."""
        with self.assertRaises(AccessError):
            self.env["discuss.channel"].with_user(self.sam).with_context(
                install_mode=True
            ).create(
                {
                    "name": "Rencontre",
                    "channel_type": "chat",
                    "channel_member_ids": [
                        Command.create(
                            {"partner_id": self.france.partner_id.id}
                        ),
                        Command.create(
                            {"partner_id": self.jacques.partner_id.id}
                        ),
                    ],
                }
            )

    def test_thread_follows_its_channel(self):
        """The thread of a strict channel is strict: a member without a link
        neither writes there nor opens one, whose name would be posted in
        the channel."""
        animation = self.env["discuss.channel"].create(
            {
                "name": "Animation",
                "channel_type": "channel",
                "group_public_id": self.env.ref(
                    "mail_linkup_reflet.group_linkup_member"
                ).id,
                "linkup_start_rule": "strict",
                "channel_partner_ids": [
                    Command.link(self.sam.partner_id.id),
                    Command.link(self.france.partner_id.id),
                ],
            }
        )
        thread = animation._create_sub_channel(name="Fil")
        self.assertEqual(thread._linkup_start_rule(), "strict")
        with self.assertLinkupCode("linkup.start_rule"):
            self._post(animation, self.sam)
        with self.assertLinkupCode("linkup.start_rule"):
            animation.with_user(self.sam)._create_sub_channel(
                name="Appelle-moi ce soir"
            )
        self.assertEqual(animation.sub_channel_ids, thread)


@tagged("post_install", "-at_install")
class TestLinkupStartRuleBypassRpc(
    LinkupStartRuleMixin, LinkupRefletCase, HttpCase
):
    """The same ways, forced by a web client (T-08)."""

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

    @mute_logger("odoo.http", "odoo.addons.mail.models.mail_thread")
    def test_routes_refused(self):
        """A reply, a reaction, ``message_notify``, a group and a channel
        all fail before a confirmation; the reaction works after it."""
        reflet = self._sent()
        chat = reflet.channel_id
        message = reflet.message_id
        self.authenticate(self.france.login, self.france.login)
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(
                "/mail/message/post",
                {
                    "thread_model": "discuss.channel",
                    "thread_id": chat.id,
                    "post_data": {"body": "Oui", "parent_id": message.id},
                },
            )
        reaction = {
            "message_id": message.id,
            "content": "Appelle-moi ce soir",
            "action": "add",
        }
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request("/mail/message/reaction", reaction)
        with self.assertRaises(JsonRpcException):
            self._call(
                "discuss.channel",
                "message_notify",
                [chat.ids],
                {"body": "Bonjour", "partner_ids": self.sam.partner_id.ids},
            )
        with self.assertRaises(JsonRpcException):
            self._call(
                "discuss.channel", "create_group", [self.sam.partner_id.ids]
            )
        with self.assertRaises(JsonRpcException):
            self._call("discuss.channel", "channel_create", ["Place", None])
        self.assertFalse(self._free_messages(chat))
        self.assertFalse(message.sudo().reaction_ids)
        reflet.with_user(self.france).action_confirm()
        self.make_jsonrpc_request(
            "/mail/message/reaction", dict(reaction, content="👍")
        )
        self.assertEqual(message.sudo().reaction_ids.content, "👍")
