# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Concurrent events of one member, through two database cursors
(LU-F-100 CA2, T-11).

The ledger locks the rows of the beneficiaries with ``FOR NO KEY UPDATE
NOWAIT``. The second transaction fails at once with ``LockNotAvailable``,
which the RPC layer retries (``odoo.service.model.retrying``); the test
replays that retry by hand once the first transaction commits.

The data lives in committed transactions, since a second cursor does not
see the test transaction; it is removed once the class ends.
"""

import psycopg2
from odoo import SUPERUSER_ID, Command, api
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail_linkup_reflet.tests.common import MEMBER, LinkupTestMixin
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from .common import OLD_ACCOUNT_DATE


@tagged("post_install", "-at_install")
class TestLinkupPointsConcurrency(LinkupTestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = env["res.users"]
            for login, name in (
                ("linkup_pc_sam", "Sam"),
                ("linkup_pc_france", "France"),
                ("linkup_pc_jacques", "Jacques"),
            ):
                users |= mail_new_test_user(
                    env,
                    login=login,
                    name=name,
                    email=f"{login}@example.com",
                    groups=MEMBER,
                )
            users.flush_recordset()
            cr.execute(
                "UPDATE res_users SET create_date = %s WHERE id IN %s",
                [OLD_ACCOUNT_DATE, tuple(users.ids)],
            )
            cls.sam_id, cls.france_id, cls.jacques_id = users.ids
            cls.channel_id = (
                env["discuss.channel"]
                .create(
                    {
                        "name": "Atelier",
                        "channel_type": "group",
                        "channel_partner_ids": [
                            Command.link(partner.id)
                            for partner in users.partner_id
                        ],
                    }
                )
                .id
            )
            cr.commit()
        cls.addClassCleanup(cls._remove_committed_data)

    @classmethod
    def _remove_committed_data(cls):
        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            ids = [cls.sam_id, cls.france_id, cls.jacques_id]
            env["linkup.points.ledger"].search(
                [("user_id", "in", ids)]
            ).unlink()
            env["linkup.reflet"].search([("author_id", "in", ids)]).unlink()
            env["linkup.link"].search([("user_a_id", "in", ids)]).unlink()
            users = env["res.users"].browse(ids)
            partners = users.partner_id
            env["discuss.channel"].search(
                [("channel_member_ids.partner_id", "in", partners.ids)]
            ).unlink()
            users.unlink()
            partners.unlink()
            cr.commit()

    def setUp(self):
        super().setUp()
        self.cursors = []
        self.addCleanup(self._close_cursors)

    def _close_cursors(self):
        for cr in self.cursors:
            cr.rollback()
            cr.close()

    def _env(self, user_id):
        """An environment of ``user_id`` in a new transaction."""
        cr = self.registry.cursor()
        self.cursors.append(cr)
        return api.Environment(cr, user_id, {})

    def _sent(self, recipient_id):
        """A reflection of Sam to ``recipient_id``, committed."""
        env = self._env(self.sam_id)
        Reflet = env["linkup.reflet"]
        draft_id = Reflet.action_save_draft(
            {
                "category_id": env.ref(
                    "mail_linkup_reflet.linkup_category_needs"
                ).id,
                "you_said": "Que tu cherches du temps.",
                "understood": "Que tu as besoin de calme.",
                "real_world_declared": True,
            }
        )
        Reflet.browse(draft_id).action_send(recipient_id)
        env.cr.commit()
        return draft_id

    def _final(self):
        env = self._env(SUPERUSER_ID)
        sam = env["res.users"].browse(self.sam_id)
        lines = env["linkup.points.ledger"].search(
            [("user_id", "=", self.sam_id)]
        )
        return sam.karma, lines

    def test_two_confirmations_for_one_member(self):
        """LU-F-100 CA2: France and Jacques confirm Sam's reflections at
        once; the second waits for the first, and the karma of Sam is the
        sum of his lines."""
        to_france = self._sent(self.france_id)
        to_jacques = self._sent(self.jacques_id)
        first = self._env(self.france_id)["linkup.reflet"].browse(to_france)
        second = self._env(self.jacques_id)["linkup.reflet"].browse(to_jacques)
        first.action_confirm()
        with mute_logger("odoo.sql_db"), self.assertRaises(
            psycopg2.errors.LockNotAvailable
        ):
            second.action_confirm()
        second.env.cr.rollback()
        first.env.cr.commit()
        retry = self._env(self.jacques_id)["linkup.reflet"].browse(to_jacques)
        retry.action_confirm()
        retry.env.cr.commit()
        karma, lines = self._final()
        for reflet_id in (to_france, to_jacques):
            codes = lines.filtered(
                lambda line, reflet_id=reflet_id: line.reflet_id.id
                == reflet_id
            ).mapped("rule_id.code")
            self.assertEqual(
                sorted(codes), ["reflect_confirmed", "reflect_sent"]
            )
        self.assertEqual(karma, sum(lines.mapped("points")))

    def test_same_event_reported_twice_at_once(self):
        """LU-F-100 RM1: the same event reported by two transactions at
        once pays once."""
        reflet_id = self._sent(self.france_id)
        env = self._env(self.france_id)
        env["linkup.reflet"].browse(reflet_id).action_confirm()
        env.cr.commit()
        before = self._final()

        def report(env):
            reflet = env["linkup.reflet"].sudo().browse(reflet_id)
            reflet._linkup_event(
                "reflect_confirmed",
                reflet.author_id | reflet.recipient_id,
                link=reflet.link_id,
            )

        first = self._env(SUPERUSER_ID)
        second = self._env(SUPERUSER_ID)
        report(first)
        with mute_logger("odoo.sql_db"), self.assertRaises(
            psycopg2.errors.LockNotAvailable
        ):
            report(second)
        second.cr.rollback()
        first.cr.commit()
        retry = self._env(SUPERUSER_ID)
        report(retry)
        retry.cr.commit()
        karma, lines = self._final()
        self.assertEqual(lines, before[1].with_env(lines.env))
        self.assertEqual(karma, before[0])
        self.assertEqual(karma, sum(lines.mapped("points")))
