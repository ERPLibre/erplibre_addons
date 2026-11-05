# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import json
from contextlib import contextmanager

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.tests.common import TransactionCase

MEMBER = "mail_linkup_reflet.group_linkup_member"


class LinkupTestMixin:
    """Helpers shared by the LinkUp test classes.

    ``_record_events`` replaces ``linkup.reflet._linkup_event`` with a
    recorder: each call appends ``(code, user ids)`` to ``self.events``.
    """

    def _record_events(self):
        self.events = []
        events = self.events

        def record(reflet, code, users, link=None):
            events.append((code, frozenset(users.ids)))

        self.patch(type(self.env["linkup.reflet"]), "_linkup_event", record)

    @contextmanager
    def assertLinkupCode(self, code, field=None):
        """Expect a ``LinkupError`` carrying ``code`` (and ``field``)."""
        with self.assertRaises(LinkupError) as catcher:
            yield
        self.assertEqual(catcher.exception.context["linkup_code"], code)
        if field:
            self.assertEqual(
                catcher.exception.context.get("linkup_field"), field
            )

    # Bus

    def _bus_reset(self):
        """Forget the bus notifications sent so far in the test."""
        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()

    def _bus_sent(self):
        """The bus notifications sent since the last reset, in order.

        Each one is ``(target, type, payload)``; ``target`` is the record
        notified, a channel or a partner, and the subchannel when there is
        one. The bus writes them at commit time; running the precommit
        hooks writes them now.
        """
        self.env.cr.precommit.run()
        sent = []
        for notif in self.env["bus.bus"].sudo().search([], order="id"):
            channel = json.loads(notif.channel)
            model, res_id = channel[1], channel[2]
            target = self.env[model].browse(res_id)
            if len(channel) > 3:
                target = (target, channel[3])
            message = json.loads(notif.message)
            sent.append((target, message["type"], message["payload"]))
        return sent


class LinkupRefletCase(LinkupTestMixin, TransactionCase):
    """Sam, France and Jacques share a group conversation, so each one is in
    the scope of the others; Luce shares nothing with them. Each test
    records the scoring events in ``self.events``."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def member(login, name):
            return mail_new_test_user(
                cls.env,
                login=login,
                name=name,
                email=f"{login}@example.com",
                groups=MEMBER,
            )

        cls.sam = member("linkup_rf_sam", "Sam")
        cls.france = member("linkup_rf_france", "France")
        cls.jacques = member("linkup_rf_jacques", "Jacques")
        cls.luce = member("linkup_rf_luce", "Luce")
        cls.workshop = cls.env["discuss.channel"].create(
            {
                "name": "Atelier",
                "channel_type": "group",
                "channel_partner_ids": [
                    Command.link(user.partner_id.id)
                    for user in (cls.sam, cls.france, cls.jacques)
                ],
            }
        )
        Category = cls.env["linkup.category"]
        cls.needs = Category.search([("code", "=", "needs")])
        cls.goals = Category.search([("code", "=", "goals")])
        cls.emotions = Category.search([("code", "=", "emotions")])
        cls.action_cat = Category.search([("code", "=", "action")])
        cls.Reflet = cls.env["linkup.reflet"]
        cls.Link = cls.env["linkup.link"]

    def setUp(self):
        super().setUp()
        self._record_events()

    def _draft(self, author=None, **vals):
        author = author or self.sam
        values = {
            "category_id": self.needs.id,
            "you_said": "Que tu cherches du temps pour ton jardin.",
            "understood": "Que tu as besoin de calme.",
            "real_world_declared": True,
        }
        values.update(vals)
        draft_id = self.Reflet.with_user(author).action_save_draft(values)
        return self.Reflet.browse(draft_id)

    def _sent(self, author=None, recipient=None, **vals):
        author = author or self.sam
        recipient = recipient or self.france
        reflet = self._draft(author, **vals)
        reflet.with_user(author).action_send(recipient.id)
        return reflet

    def _confirmed(self):
        reflet = self._sent()
        reflet.with_user(self.france).action_confirm()
        return reflet

    def _child(self, reflet_id):
        return self.Reflet.browse(reflet_id)

    def _link(self, user1, user2):
        return self.Link._get_between(user1, user2)
