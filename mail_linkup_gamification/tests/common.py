# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import datetime

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import (
    MEMBER,
    LinkupRefletCase,
)

# Accounts of the tests are dated well before any frozen time, so that they
# are old enough to earn points.
OLD_ACCOUNT_DATE = datetime(2020, 1, 1)


class LinkupPointsCase(LinkupRefletCase):
    """The members of ``LinkupRefletCase``, Sam, France, Jacques and Luce,
    with old accounts in the time zone of Montréal; the scoring events of
    the core run for real."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.members = cls.sam | cls.france | cls.jacques | cls.luce
        cls.members.write({"tz": "America/Toronto"})
        cls._age_accounts(cls.members)
        cls.Ledger = cls.env["linkup.points.ledger"]
        cls.Rule = cls.env["linkup.points.rule"]

    @classmethod
    def _age_accounts(cls, users, date=OLD_ACCOUNT_DATE):
        """Date the creation of ``users`` back to ``date``."""
        users.flush_recordset()
        cls.env.cr.execute(
            "UPDATE res_users SET create_date = %s WHERE id IN %s",
            [date, tuple(users.ids)],
        )
        users.invalidate_recordset(["create_date"])

    @classmethod
    def _new_members(cls, count, prefix, age=True):
        """``count`` new members who share a group conversation with Sam
        and France, so that each one is in their scope."""
        users = cls.env["res.users"]
        for index in range(count):
            login = f"linkup_pt_{prefix}{index}"
            users |= mail_new_test_user(
                cls.env,
                login=login,
                name=f"Membre {prefix}{index}",
                email=f"{login}@example.com",
                groups=MEMBER,
                tz="America/Toronto",
            )
        cls.env["discuss.channel"].create(
            {
                "name": f"Groupe {prefix}",
                "channel_type": "group",
                "channel_partner_ids": [
                    Command.link(partner.id)
                    for partner in (users | cls.sam | cls.france).partner_id
                ],
            }
        )
        if age:
            cls._age_accounts(users)
        return users

    def _record_events(self):
        """Keep the scoring events of the core running: nothing is
        recorded here."""
        self.events = []

    # Ledger

    def _lines(self, user, code=None):
        domain = [("user_id", "=", user.id)]
        if code:
            domain.append(("rule_id.code", "=", code))
        return self.Ledger.sudo().search(domain, order="id")

    def _paid(self, user, code=None):
        """The points of the lines of ``user``, in order."""
        return self._lines(user, code).mapped("points")

    def _rule(self, code):
        return (
            self.Rule.sudo()
            .with_context(active_test=False)
            .search([("code", "=", code)])
        )

    def assertBalanced(self, *users):
        """The karma of each user is the sum of their ledger lines."""
        for user in users:
            user.invalidate_recordset(["karma"])
            self.assertEqual(
                user.sudo().karma,
                sum(self._lines(user).mapped("points")),
                f"karma of {user.name}",
            )

    # Reflections

    def _sent_to(self, author, recipient, **vals):
        return self._sent(author=author, recipient=recipient, **vals)

    def _confirmed_by(self, author, recipient):
        reflet = self._sent_to(author, recipient)
        reflet.with_user(recipient).action_confirm()
        return reflet

    def _exact(self, reflet, user):
        """``user`` answers "that's exactly it" to ``reflet``."""
        return self._child(reflet.with_user(user).action_answer_exact())

    def _continue(self, reflet, user):
        """``user`` continues the reflection from the options of
        ``reflet``."""
        return self._child(
            reflet.with_user(user).action_continue(
                self.action_cat.id, "Ta demande d'action est que…"
            )
        )

    def _post(self, channel, user, body="Bonjour !"):
        """Post free text as ``user`` in ``channel``."""
        return channel.with_user(user).message_post(
            body=body, message_type="comment"
        )

    def _call_members(self, reflet):
        """The members of the conversation of ``reflet`` for Sam and
        France, each acting as their own user."""
        members = {
            member.partner_id: member
            for member in reflet.channel_id.sudo().channel_member_ids
        }
        return (
            members[self.sam.partner_id].with_user(self.sam).sudo(),
            members[self.france.partner_id].with_user(self.france).sudo(),
        )

    def _awarded(self, user):
        """The ``linkup.points/awarded`` payloads sent to ``user``."""
        return [
            payload
            for target, kind, payload in self._bus_sent()
            if kind == "linkup.points/awarded" and target == user.partner_id
        ]
