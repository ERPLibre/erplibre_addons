# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Concurrent actions on one reflection, through two database cursors
(RS-4, LU-F-019 CA2, LU-F-022 RM5, LU-F-033 CA4; T-44).

Each action locks the row of the reflection with ``FOR UPDATE NOWAIT``.
The second transaction fails at once with ``LockNotAvailable``, which the
RPC layer retries (``odoo.service.model.retrying``); the test replays that
retry by hand, after the first transaction commits, and expects the
LinkUp code of an action already done.

The data lives in committed transactions, since a second cursor does not
see the test transaction; it is removed once the class ends.
"""

import psycopg2
from odoo import SUPERUSER_ID, api
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from .common import MEMBER, LinkupTestMixin


@tagged("post_install", "-at_install")
class TestLinkupRefletConcurrency(LinkupTestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = env["res.users"]
            for login, name in (
                ("linkup_cc_sam", "Sam"),
                ("linkup_cc_france", "France"),
            ):
                users |= mail_new_test_user(
                    env,
                    login=login,
                    name=name,
                    email=f"{login}@example.com",
                    groups=MEMBER,
                )
            cls.sam_id, cls.france_id = users.ids
            cls.link_id = (
                env["linkup.link"]._get_or_create(users[0], users[1]).id
            )
            cr.commit()
        cls.addClassCleanup(cls._remove_committed_data)

    @classmethod
    def _remove_committed_data(cls):
        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env["linkup.reflet"].search(
                [
                    "|",
                    ("link_id", "=", cls.link_id),
                    ("author_id", "in", [cls.sam_id, cls.france_id]),
                ]
            ).unlink()
            env["linkup.link"].browse(cls.link_id).unlink()
            users = env["res.users"].browse([cls.sam_id, cls.france_id])
            partners = users.partner_id
            env["discuss.channel"].search(
                [("channel_member_ids.partner_id", "in", partners.ids)]
            ).unlink()
            users.unlink()
            partners.unlink()
            cr.commit()

    def setUp(self):
        super().setUp()
        self._record_events()
        self.cursors = []
        self.addCleanup(self._close_cursors)
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            self.reflet_id = (
                env["linkup.reflet"]
                .create(
                    {
                        "author_id": self.sam_id,
                        "recipient_id": self.france_id,
                        "link_id": self.link_id,
                        "category_id": env.ref(
                            "mail_linkup_reflet.linkup_category_needs"
                        ).id,
                        "you_said": "Que tu cherches du temps.",
                        "understood": "Que tu as besoin de calme.",
                        "real_world_declared": True,
                        "state": "sent",
                    }
                )
                .id
            )
            cr.commit()
        self.events.clear()

    def _close_cursors(self):
        for cr in self.cursors:
            cr.rollback()
            cr.close()

    def _reflet(self, user_id):
        """The reflection as ``user_id`` sees it, in a new transaction."""
        cr = self.registry.cursor()
        self.cursors.append(cr)
        env = api.Environment(cr, user_id, {})
        return env["linkup.reflet"].browse(self.reflet_id)

    def _second_fails_then_retry(self, first, second, retry_code):
        """Run ``first`` without committing, check that ``second`` fails on
        the lock, commit ``first``, then expect ``retry_code`` from a retry
        of ``second`` in a new transaction."""
        first_reflet = first[0]
        first[1](first_reflet)
        second_reflet = second[0]
        with mute_logger("odoo.sql_db"), self.assertRaises(
            psycopg2.errors.LockNotAvailable
        ):
            second[1](second_reflet)
        second_reflet.env.cr.rollback()
        first_reflet.env.cr.commit()
        retry = self._reflet(second_reflet.env.uid).browse(second_reflet.id)
        with self.assertLinkupCode(retry_code):
            second[1](retry)

    def test_two_confirmations_one_succeeds(self):
        """Two concurrent confirmations: one effect, one already answered."""
        self._second_fails_then_retry(
            (self._reflet(self.france_id), lambda r: r.action_confirm()),
            (self._reflet(self.france_id), lambda r: r.action_confirm()),
            "linkup.already_answered",
        )
        final = self._reflet(SUPERUSER_ID)
        self.assertEqual(final.state, "confirmed")
        self.assertEqual(final.link_id.state, "active")
        self.assertEqual(
            [code for code, _users in self.events], ["reflect_confirmed"]
        )

    def test_withdraw_against_confirmation(self):
        """Withdrawal and confirmation at once: one of the two only (T-44)."""
        self._second_fails_then_retry(
            (self._reflet(self.sam_id), lambda r: r.action_withdraw()),
            (self._reflet(self.france_id), lambda r: r.action_confirm()),
            "linkup.expired",
        )
        final = self._reflet(SUPERUSER_ID)
        self.assertEqual(final.state, "withdrawn")
        self.assertEqual(
            [code for code, _users in self.events], ["reflect_withdrawn"]
        )

    def test_two_guesses_one_counts(self):
        """Two concurrent guesses on one precision: the first counts."""
        reflet = self._reflet(self.france_id)
        reflet.action_confirm()
        precision_id = reflet.action_answer_precision(
            "Précision",
            [reflet.env.ref("mail_linkup_reflet.linkup_category_goals").id],
        )
        reflet.env.cr.commit()
        goals_id = reflet.env.ref(
            "mail_linkup_reflet.linkup_category_goals"
        ).id
        needs_id = reflet.env.ref(
            "mail_linkup_reflet.linkup_category_needs"
        ).id
        self.events.clear()

        def precision():
            return self._reflet(self.sam_id).browse(precision_id)

        self._second_fails_then_retry(
            (precision(), lambda r: r.action_guess(goals_id)),
            (precision(), lambda r: r.action_guess(needs_id)),
            "linkup.already_answered",
        )
        final = self._reflet(SUPERUSER_ID).browse(precision_id)
        self.assertEqual(final.guess_state, "found")
        self.assertEqual(
            [code for code, _users in self.events], ["theme_guessed"]
        )

    def test_two_first_saves_keep_one_draft(self):
        """Two first saves of a draft at once: the second fails on the
        lock, and its retry updates the draft of the first (LU-F-012
        RM4)."""
        first = self._reflet(self.sam_id)
        second = self._reflet(self.sam_id)
        # An insert that collides with the uncommitted draft waits for the
        # first transaction; the timeout makes that wait fail the test
        # instead of blocking it.
        second.env.cr.execute("SET LOCAL statement_timeout = '5s'")
        draft_id = first.action_save_draft({"you_said": "Premier onglet."})
        with mute_logger("odoo.sql_db"), self.assertRaises(
            psycopg2.errors.LockNotAvailable
        ):
            second.action_save_draft({"you_said": "Second onglet."})
        second.env.cr.rollback()
        first.env.cr.commit()
        retry = self._reflet(self.sam_id)
        self.assertEqual(
            retry.action_save_draft({"you_said": "Second onglet."}), draft_id
        )
        retry.env.cr.commit()
        final = self._reflet(SUPERUSER_ID)
        drafts = final.search(
            [("author_id", "=", self.sam_id), ("state", "=", "draft")]
        )
        self.assertEqual(drafts.ids, [draft_id])
        self.assertEqual(drafts.you_said, "Second onglet.")
