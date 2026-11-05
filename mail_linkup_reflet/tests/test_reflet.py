# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Categories, reflections and links: data, state machine, access rights
(LU-F-011 to 033, LU-F-040 to 043, §9.3, §9.4; T-02, T-04 to T-07, T-31,
T-32, T-51).

Sam, France and Jacques share a group conversation, so each one is in the
scope of the others; Luce shares nothing with them.
"""

from datetime import timedelta

import psycopg2
from odoo import Command, fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError, ValidationError
from odoo.http import serialize_exception
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from ..exceptions import LinkupError
from .common import MEMBER, LinkupRefletCase

FULL_BAND = [
    "observation",
    "emotions",
    "needs",
    "action",
    "inhibition",
    "go_listen",
    "go_speak",
    "goals",
    "vulnerability",
    "reflection",
    "focus",
    "team",
]
REDUCED_BAR = [
    "observation",
    "emotions",
    "needs",
    "team",
    "go_speak",
    "goals",
    "vulnerability",
]


@tagged("post_install", "-at_install")
class TestLinkupCategory(TransactionCase):
    def test_categories_and_orders(self):
        """Twelve categories, the full band and the reduced bar in order."""
        Category = self.env["linkup.category"]
        self.assertEqual(Category.search([]).mapped("code"), FULL_BAND)
        bar = Category.search(
            [("in_reflet_bar", "=", True)], order="reflet_bar_sequence"
        )
        self.assertEqual(bar.mapped("code"), REDUCED_BAR)
        cnv = Category.search([("is_cnv", "=", True)])
        self.assertEqual(
            set(cnv.mapped("code")),
            {"observation", "emotions", "needs", "action", "inhibition"},
        )
        for category in Category.search([]):
            self.assertTrue(category.reflet_title)
            self.assertTrue(category.starter_self)
            self.assertTrue(category.starter_reflect)

    def test_archived_category_leaves_the_bar(self):
        """An archived category is out of the band and of the bar."""
        team = self.env.ref("mail_linkup_reflet.linkup_category_team")
        team.active = False
        codes = self.env["linkup.category"].search([]).mapped("code")
        self.assertNotIn("team", codes)

    def test_category_texts_in_french(self):
        """The texts are translatable, with their French version."""
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            ["mail_linkup_reflet"], ["fr_CA"], overwrite=True
        )
        goals = self.env.ref(
            "mail_linkup_reflet.linkup_category_goals"
        ).with_context(lang="fr_CA")
        self.assertEqual(goals.name, "Buts")
        self.assertEqual(goals.starter_self, "Mon but est :")
        self.assertEqual(goals.reflet_title, "Tu m'as parlé de ton but")
        self.assertIn("lien durable", goals.definition)
        self.assertEqual(goals.with_context(lang="en_US").name, "Goals")

    def test_member_reads_categories_only(self):
        """A member reads the categories; only an administrator edits."""
        member = mail_new_test_user(
            self.env, login="linkup_cat_sam", groups=MEMBER
        )
        Category = self.env["linkup.category"].with_user(member)
        self.assertEqual(len(Category.search([])), 12)
        with self.assertRaises(AccessError):
            Category.search([], limit=1).write({"name": "Autre"})
        with self.assertRaises(AccessError):
            Category.create({"code": "other", "name": "Other"})


@tagged("post_install", "-at_install")
class TestLinkupReflet(LinkupRefletCase):
    # Drafts (T-02)

    def test_draft_single_and_private(self):
        """One draft per author, kept on save, invisible to others."""
        draft = self._draft()
        again = self._draft(you_said="Autre texte", state="sent")
        self.assertEqual(draft, again)
        self.assertEqual(draft.state, "draft")
        self.assertEqual(draft.you_said, "Autre texte")
        self.assertEqual(draft.author_id, self.sam)
        Reflet = self.Reflet.with_user(self.france)
        self.assertFalse(Reflet.search([("id", "=", draft.id)]))
        with self.assertRaises(AccessError):
            draft.with_user(self.france).read(["you_said"])
        self.assertEqual(
            self.Reflet.with_user(self.sam).search([]),
            draft.with_user(self.sam),
        )
        draft.with_user(self.sam).action_discard_draft()
        self.assertFalse(draft.exists())

    def test_member_has_no_orm_write(self):
        """Every change goes through the methods: no create, write, unlink."""
        reflet = self._sent()
        Reflet = self.Reflet.with_user(self.sam)
        with self.assertRaises(AccessError):
            Reflet.create({"author_id": self.sam.id, "state": "confirmed"})
        with self.assertRaises(AccessError):
            reflet.with_user(self.france).write({"state": "confirmed"})
        with self.assertRaises(AccessError):
            reflet.with_user(self.sam).unlink()
        with self.assertRaises(AccessError):
            self._link(self.sam, self.france).with_user(self.sam).write(
                {"state": "active"}
            )

    # Sending (LU-F-013, LU-F-016)

    def test_send_checks_texts_and_attestation(self):
        """Missing texts and an undeclared first exchange are refused."""
        draft = self._draft(understood="  ")
        with self.assertLinkupCode("linkup.validation", "understood"):
            draft.with_user(self.sam).action_send(self.france.id)
        draft = self._draft(understood="Que tu as besoin de calme.")
        draft.with_user(self.sam).action_save_draft(
            {"real_world_declared": False}
        )
        with self.assertLinkupCode("linkup.validation", "real_world_declared"):
            draft.with_user(self.sam).action_send(self.france.id)
        self.assertEqual(draft.state, "draft")
        self.assertFalse(self._link(self.sam, self.france))
        too_long = "x" * 1001
        with self.assertLinkupCode("linkup.validation", "you_said"):
            self._draft(you_said=too_long)

    def test_send(self):
        """Sending creates the pending link and reports reflect_sent."""
        reflet = self._sent()
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(reflet.recipient_id, self.france)
        self.assertTrue(reflet.sent_date)
        self.assertEqual(reflet.real_world_date, fields.Date.today())
        link = self._link(self.sam, self.france)
        self.assertEqual(reflet.link_id, link)
        self.assertEqual(link.state, "pending")
        self.assertLess(link.user_a_id.id, link.user_b_id.id)
        self.assertEqual(
            self.events, [("reflect_sent", frozenset(self.sam.ids))]
        )
        with self.assertLinkupCode("linkup.already_answered"):
            reflet.with_user(self.sam).action_send(self.france.id)

    def test_send_out_of_scope_refused(self):
        """Outsider, self, unknown id: the same generic refusal."""
        draft = self._draft()
        Draft = draft.with_user(self.sam)
        for recipient_id in (self.luce.id, self.sam.id, 999999, "x"):
            with self.assertLinkupCode("linkup.unavailable"):
                Draft.action_send(recipient_id)
        self.assertEqual(draft.state, "draft")

    def test_linked_pair_needs_no_attestation(self):
        """Once linked, a new reflection needs no declaration."""
        self._confirmed()
        reflet = self._sent(real_world_declared=False)
        self.assertEqual(reflet.state, "sent")
        self.assertFalse(reflet.real_world_date)

    # Reception (LU-F-022, 023, 025, 019)

    def test_confirm(self):
        """Confirmation links the pair, once, by the recipient only (T-04)."""
        reflet = self._sent()
        with self.assertRaises(AccessError):
            reflet.with_user(self.sam).action_confirm()
        reflet.with_user(self.france).action_confirm()
        self.assertEqual(reflet.state, "confirmed")
        self.assertTrue(reflet.read_date)
        link = reflet.link_id
        self.assertEqual(link.state, "active")
        self.assertTrue(link.first_link_date)
        self.assertEqual(link.turn_reflet_id, reflet)
        self.assertEqual(link._linkup_turn_user(), self.france)
        self.assertTrue(self.Link._is_active_between(self.france, self.sam))
        with self.assertLinkupCode("linkup.already_answered"):
            reflet.with_user(self.france).action_confirm()
        with self.assertLinkupCode("linkup.already_answered"):
            reflet.with_user(self.france).action_reject()
        both = frozenset((self.sam | self.france).ids)
        self.assertEqual(
            [event for event in self.events if event[0] != "reflect_sent"],
            [("reflect_confirmed", both)],
        )

    def test_reject(self):
        """Rejection reports to the author only and links nothing (T-05)."""
        reflet = self._sent()
        reflet.with_user(self.france).action_reject()
        self.assertEqual(reflet.state, "rejected")
        self.assertEqual(reflet.link_id.state, "closed")
        self.assertEqual(
            self.events[-1], ("reflect_rejected", frozenset(self.sam.ids))
        )

    def test_ignore_hidden_from_author_then_expires(self):
        """Ignoring changes nothing for the author; the cron expires it."""
        reflet = self._sent()
        reflet.with_user(self.france).action_ignore()
        self.assertTrue(reflet.recipient_ignored)
        self.assertEqual(reflet.state, "sent")
        with self.assertRaises(AccessError):
            reflet.with_user(self.sam).read(["recipient_ignored"])
        rows = reflet.with_user(self.sam).read()
        self.assertNotIn("recipient_ignored", rows[0])
        self.assertEqual(len(self.events), 1)
        reflet.sudo().sent_date = fields.Datetime.now() - timedelta(days=31)
        recent = self._sent(author=self.jacques)
        self.Reflet._cron_expire_reflets()
        self.assertEqual(reflet.state, "expired")
        self.assertEqual(recent.state, "sent")
        with self.assertLinkupCode("linkup.expired"):
            reflet.with_user(self.france).action_confirm()

    def test_ignore_leaves_no_trace_for_the_author(self):
        """Ignoring changes nothing the author reads: neither the last
        writer nor the date of the last write, and the flag is neither
        searchable nor groupable by them (LU-F-025 RM1)."""
        reflet = self._sent()
        reflet.flush_recordset()
        self.env.cr.execute(
            "UPDATE linkup_reflet SET write_date = write_date"
            " - interval '1 day' WHERE id = %s",
            [reflet.id],
        )
        reflet.invalidate_recordset()
        as_sam = reflet.with_user(self.sam)
        before = as_sam.read(["write_uid", "write_date"])[0]
        reflet.with_user(self.france).action_ignore()
        reflet.invalidate_recordset()
        self.assertTrue(reflet.recipient_ignored)
        self.assertEqual(as_sam.read(["write_uid", "write_date"])[0], before)
        Reflet = self.Reflet.with_user(self.sam)
        with self.assertRaises(AccessError):
            Reflet.search_count(
                [("id", "=", reflet.id), ("recipient_ignored", "=", True)]
            )
        with self.assertRaises(AccessError):
            Reflet.read_group([], ["id:count"], ["recipient_ignored"])

    def test_inaccurate(self):
        """Inaccurate: a correction for the author, no link, no event."""
        reflet = self._sent()
        reflet.with_user(self.france).action_mark_inaccurate(
            "Je parlais du potager du quartier."
        )
        self.assertEqual(reflet.state, "inaccurate")
        self.assertEqual(
            reflet.body_text, "Je parlais du potager du quartier."
        )
        self.assertEqual(reflet.link_id.state, "pending")
        self.assertEqual(len(self.events), 1)

    def test_withdraw(self):
        """An unread reflection is withdrawn and leaves the recipient."""
        reflet = self._sent()
        reflet.with_user(self.sam).action_withdraw()
        self.assertEqual(reflet.state, "withdrawn")
        self.assertEqual(
            self.events[-1], ("reflect_withdrawn", frozenset(self.sam.ids))
        )
        self.assertFalse(
            self.Reflet.with_user(self.france).search([("id", "=", reflet.id)])
        )
        with self.assertLinkupCode("linkup.expired"):
            reflet.with_user(self.france).action_confirm()

    def test_withdrawn_name_hides_the_category(self):
        """The name of a withdrawn reflection, served under ``sudo`` with
        the carrier message, no longer holds its category (LU-F-019 CA1)."""
        reflet = self._sent()
        message = reflet.message_id.with_user(self.france)
        self.assertEqual(
            message.read(["linkup_reflet_id"])[0]["linkup_reflet_id"][1],
            self.needs.name,
        )
        reflet.with_user(self.sam).action_withdraw()
        message.invalidate_recordset()
        name = message.read(["linkup_reflet_id"])[0]["linkup_reflet_id"][1]
        self.assertNotIn(self.needs.name, name)
        self.assertEqual(name, "Reflection")

    def test_withdraw_refused_once_read(self):
        """A reflection read by its recipient can no longer be withdrawn."""
        reflet = self._sent()
        reflet.with_user(self.france).action_mark_read()
        self.assertTrue(reflet.read_date)
        with self.assertLinkupCode("linkup.already_answered"):
            reflet.with_user(self.sam).action_withdraw()

    # Rights (§9.4)

    def test_member_reads_own_reflections_only(self):
        """A reads their reflections, not those of B and C."""
        sam_france = self._sent()
        france_jacques = self._sent(author=self.france, recipient=self.jacques)
        Reflet = self.Reflet
        self.assertEqual(
            Reflet.with_user(self.sam).search([]).ids, sam_france.ids
        )
        self.assertEqual(
            set(Reflet.with_user(self.france).search([]).ids),
            {sam_france.id, france_jacques.id},
        )
        self.assertEqual(
            Reflet.with_user(self.jacques).search([]).ids, france_jacques.ids
        )
        with self.assertRaises(AccessError):
            sam_france.with_user(self.jacques).read(["you_said"])
        with self.assertRaises(AccessError):
            sam_france.with_user(self.jacques).action_confirm()
        Link = self.Link
        self.assertEqual(
            Link.with_user(self.jacques).search([]),
            self._link(self.france, self.jacques),
        )
        self.assertFalse(Link.with_user(self.luce).search([]))

    def test_link_opens_partner_scope(self):
        """A link opens the two members to each other; blocked closes."""
        Partner = self.env["res.partner"].with_user(self.sam)
        Users = self.env["res.users"].with_user(self.sam)
        self.assertNotIn(self.luce.partner_id, Partner.search([]))
        link = self.Link._get_or_create(self.luce, self.sam)
        self.assertIn(self.luce.partner_id, Partner.search([]))
        self.assertIn(self.luce, Users.search([]))
        self.assertIn(
            self.sam.partner_id,
            self.env["res.partner"].with_user(self.luce).search([]),
        )
        link.state = "active"
        self.assertIn(self.luce, Users.search([]))
        link.state = "blocked"
        self.assertNotIn(self.luce.partner_id, Partner.search([]))
        self.assertNotIn(self.luce, Users.search([]))

    # Links (§9.3)

    def _expire(self, reflet):
        reflet.sudo().sent_date = fields.Datetime.now() - timedelta(days=31)
        self.Reflet._cron_expire_reflets()

    def _closings(self):
        """The three ends of a pending link: rejection, withdrawal and
        expiry, each as a function of the sent reflection."""
        return {
            "rejected": lambda r: r.with_user(r.recipient_id).action_reject(),
            "withdrawn": lambda r: r.with_user(r.author_id).action_withdraw(),
            "expired": self._expire,
        }

    def test_unanswered_link_closes_then_reopens(self):
        """A pending link closes when its reflection is rejected, withdrawn
        or expired; the next sending makes it pending again."""
        for state, close in self._closings().items():
            with self.subTest(state=state):
                reflet = self._sent()
                link = reflet.link_id
                self.assertEqual(link.state, "pending")
                close(reflet)
                self.assertEqual(reflet.state, state)
                self.assertEqual(link.state, "closed")
                self.assertFalse(
                    self.Link._is_active_between(self.sam, self.france)
                )
        again = self._sent()
        self.assertEqual(again.link_id, link)
        self.assertEqual(link.state, "pending")
        again.with_user(self.france).action_confirm()
        self.assertEqual(link.state, "active")

    def test_link_waits_on_every_sent_reflection(self):
        """A pending link stays open while another reflection of the pair
        waits for an answer, in either direction."""
        first = self._sent()
        second = self._sent(author=self.france, recipient=self.sam)
        link = first.link_id
        self.assertEqual(second.link_id, link)
        first.with_user(self.france).action_reject()
        self.assertEqual(link.state, "pending")
        second.with_user(self.france).action_withdraw()
        self.assertEqual(link.state, "closed")

    def test_inaccurate_keeps_the_link_pending(self):
        """An inaccurate reflection does not close the link: the author may
        send a corrected one."""
        reflet = self._sent()
        reflet.with_user(self.france).action_mark_inaccurate()
        self.assertEqual(reflet.link_id.state, "pending")

    def test_active_and_blocked_links_never_close(self):
        """Ending a later reflection changes neither an active link nor a
        blocked one."""
        self._confirmed()
        link = self._link(self.sam, self.france)
        for state, close in self._closings().items():
            with self.subTest(state=state):
                close(self._sent())
                self.assertEqual(link.state, "active")
        self.env["linkup.block"].with_user(self.jacques).action_block(
            self.sam.id
        )
        jacques_link = self._link(self.sam, self.jacques)
        reflet = self._sent(recipient=self.jacques)
        self.assertEqual(jacques_link.state, "blocked")
        reflet.with_user(self.sam).action_withdraw()
        self.assertEqual(jacques_link.state, "blocked")
        reflet = self._sent(recipient=self.jacques)
        self._expire(reflet)
        self.assertEqual(reflet.state, "expired")
        self.assertEqual(jacques_link.state, "blocked")

    def test_closed_pair_no_longer_sees_each_other(self):
        """Once the link of a pair closes, neither member reads the other,
        although the carrier messages left them a direct conversation; the
        conversation still loads for both."""
        Partner = self.env["res.partner"]
        Users = self.env["res.users"]
        for state, close in self._closings().items():
            with self.subTest(state=state):
                # A shared group puts Luce in Sam's scope for the sending
                # only.
                group = self.env["discuss.channel"].create(
                    {
                        "name": "Rencontre",
                        "channel_type": "group",
                        "channel_partner_ids": [
                            Command.link(self.sam.partner_id.id),
                            Command.link(self.luce.partner_id.id),
                        ],
                    }
                )
                reflet = self._sent(recipient=self.luce)
                group.unlink()
                chat = reflet.channel_id
                self.assertEqual(chat.channel_type, "chat")
                for user, other in (
                    (self.sam, self.luce),
                    (self.luce, self.sam),
                ):
                    self.assertTrue(
                        Partner.with_user(user).search(
                            [("id", "=", other.partner_id.id)]
                        )
                    )
                close(reflet)
                self.assertEqual(reflet.link_id.state, "closed")
                self.env.invalidate_all()
                for user, other in (
                    (self.sam, self.luce),
                    (self.luce, self.sam),
                ):
                    self.assertFalse(
                        Partner.with_user(user).search(
                            [("id", "=", other.partner_id.id)]
                        )
                    )
                    self.assertFalse(
                        Users.with_user(user).search([("id", "=", other.id)])
                    )
                    with self.assertRaises(AccessError):
                        other.partner_id.with_user(user).read(["name"])
                    Store(chat.with_user(user)).get_result()
                with self.assertLinkupCode("linkup.unavailable"):
                    self._draft().with_user(self.sam).action_send(self.luce.id)
                self._draft().with_user(self.sam).action_discard_draft()

    def test_link_unique_per_pair(self):
        """One link per unordered pair, stored in increasing id order."""
        link = self.Link._get_or_create(self.sam, self.france)
        self.assertEqual(self.Link._get_or_create(self.france, self.sam), link)
        self.assertEqual(self.Link._get_or_create(self.sam, self.france), link)
        self.assertEqual(
            link.user_a_id | link.user_b_id, self.sam | self.france
        )
        self.assertLess(link.user_a_id.id, link.user_b_id.id)
        with self.assertRaises(ValueError):
            self.Link._get_or_create(self.sam, self.sam)
        with mute_logger("odoo.sql_db"), self.assertRaises(
            psycopg2.errors.UniqueViolation
        ):
            self.Link.create(
                {"user_a_id": self.france.id, "user_b_id": self.sam.id}
            )
            self.Link.flush_model()
        with mute_logger("odoo.sql_db"), self.assertRaises(
            psycopg2.errors.CheckViolation
        ):
            self.env.cr.execute(
                "INSERT INTO linkup_link (user_a_id, user_b_id, state)"
                " VALUES (%s, %s, 'pending')",
                [
                    max(self.sam.id, self.jacques.id),
                    min(self.sam.id, self.jacques.id),
                ],
            )

    # Answers, hidden themes, guess (LU-F-030 to 033, T-06, T-07, T-31)

    def test_answer_exact_once(self):
        """One answer per reflection; the answer takes the turn."""
        reflet = self._confirmed()
        with self.assertRaises(AccessError):
            reflet.with_user(self.sam).action_answer_exact()
        answer = self._child(
            reflet.with_user(self.france).action_answer_exact("Merci !")
        )
        self.assertEqual(answer.kind, "answer_exact")
        self.assertEqual(answer.author_id, self.france)
        self.assertEqual(answer.recipient_id, self.sam)
        self.assertEqual(answer.parent_id, reflet)
        self.assertEqual(answer.round_index, 1)
        self.assertEqual(reflet.response_state, "exact")
        self.assertEqual(reflet.link_id._linkup_turn_user(), self.sam)
        with self.assertLinkupCode("linkup.already_answered"):
            reflet.with_user(self.france).action_answer_precision("Aussi")
        both = frozenset((self.sam | self.france).ids)
        self.assertEqual(self.events[-1], ("answer_exact", both))

    def test_answer_needs_confirmation(self):
        """A sent, unconfirmed reflection takes no answer."""
        reflet = self._sent()
        with self.assertLinkupCode("linkup.validation", "state"):
            reflet.with_user(self.france).action_answer_exact()

    def test_precision_body_has_no_starter(self):
        """A precision keeps its text as written, without the starter of
        its hidden theme (LU-F-032 RM2)."""
        reflet = self._confirmed()
        body = "Je parlais du potager du quartier."
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                body, [self.goals.id]
            )
        )
        self.assertEqual(precision.body_text, body)
        for starter in (self.goals.starter_self, self.goals.starter_reflect):
            self.assertNotIn(starter, precision.body_text)

    def test_hidden_themes_stay_secret(self):
        """The recipient of a precision reaches its themes by no read,
        search, count or grouping; its author sees them (T-06)."""
        reflet = self._confirmed()
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Je voudrais trouver quelqu'un pour le potager.",
                [self.goals.id, self.emotions.id],
            )
        )
        self.assertEqual(precision.guess_state, "pending")
        self.assertFalse(precision.category_id)
        self.env.invalidate_all()
        as_sam = precision.with_user(self.sam)
        self.assertFalse(as_sam.revealed_category_ids)
        values = as_sam.read()[0]
        self.assertFalse(values["revealed_category_ids"])
        self.assertFalse(values["category_id"])
        self.assertEqual(
            precision.with_user(self.france).revealed_category_ids,
            self.goals | self.emotions,
        )
        Secret = self.env["linkup.reflet.secret"]
        for user in (self.sam, self.france):
            with self.assertRaises(AccessError):
                Secret.with_user(user).search_count([])
            with self.assertRaises(AccessError):
                Secret.with_user(user).read_group([], ["reflet_id"], [])
        Reflet = self.Reflet.with_user(self.sam)
        # The field is not searchable: Odoo drops the condition, so the
        # count answers the same whatever theme is asked.
        with mute_logger("odoo.osv.expression"):
            self.assertEqual(
                Reflet.search_count(
                    [("revealed_category_ids", "in", self.goals.ids)]
                ),
                Reflet.search_count([]),
            )
        groups = Reflet.read_group([], ["category_id"], ["category_id"])
        grouped = {
            group["category_id"][0] for group in groups if group["category_id"]
        }
        self.assertNotIn(self.goals.id, grouped)
        self.assertNotIn(self.emotions.id, grouped)
        self.assertEqual(
            self.events[-1],
            ("precision_sent", frozenset((self.sam | self.france).ids)),
        )

    def test_guess_secondary_theme_once(self):
        """A secondary theme counts; one guess only; themes revealed
        (T-07)."""
        reflet = self._confirmed()
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Précision", [self.goals.id, self.emotions.id]
            )
        )
        with self.assertRaises(AccessError):
            precision.with_user(self.france).action_guess(self.goals.id)
        result = precision.with_user(self.sam).action_guess(self.emotions.id)
        self.assertEqual(result, "found")
        self.assertEqual(precision.guessed_category_id, self.emotions)
        self.env.invalidate_all()
        self.assertEqual(
            precision.with_user(self.sam).revealed_category_ids,
            self.goals | self.emotions,
        )
        with self.assertLinkupCode("linkup.already_answered"):
            precision.with_user(self.sam).action_guess(self.goals.id)
        self.assertEqual(
            self.events[-1],
            ("theme_guessed", frozenset((self.sam | self.france).ids)),
        )

    def test_guess_missed(self):
        """A wrong guess is missed and still reveals the themes."""
        reflet = self._confirmed()
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Précision", [self.goals.id]
            )
        )
        result = precision.with_user(self.sam).action_guess(self.needs.id)
        self.assertEqual(result, "missed")
        self.env.invalidate_all()
        self.assertEqual(
            precision.with_user(self.sam).revealed_category_ids, self.goals
        )
        self.assertEqual(self.events[-1][0], "theme_missed")

    def test_precision_theme_limits(self):
        """At most two themes, active ones; none means nothing to guess."""
        reflet = self._confirmed()
        As = reflet.with_user(self.france)
        with self.assertLinkupCode("linkup.validation", "hidden_category_ids"):
            As.action_answer_precision(
                "Précision", [self.goals.id, self.needs.id, self.emotions.id]
            )
        with self.assertLinkupCode("linkup.validation", "body_text"):
            As.action_answer_precision("  ", [self.goals.id])
        precision = self._child(As.action_answer_precision("Sans thème"))
        self.assertEqual(precision.guess_state, "none")
        with self.assertLinkupCode("linkup.validation", "guess_state"):
            precision.with_user(self.sam).action_guess(self.goals.id)
        with self.assertRaises(ValidationError):
            self.env["linkup.reflet.secret"].create(
                {
                    "reflet_id": precision.id,
                    "category_ids": [
                        Command.set(
                            (self.goals | self.needs | self.emotions).ids
                        )
                    ],
                }
            )

    # Turns and follow-up options (LU-F-040 to 043, T-32)

    def test_options_wait_for_the_guess(self):
        """The options open on a precision once its guess is made."""
        reflet = self._confirmed()
        precision = self._child(
            reflet.with_user(self.france).action_answer_precision(
                "Précision", [self.goals.id]
            )
        )
        with self.assertLinkupCode("linkup.validation", "guess_state"):
            precision.with_user(self.sam).action_close()
        precision.with_user(self.sam).action_guess(self.goals.id)
        close = self._child(precision.with_user(self.sam).action_close())
        self.assertEqual(close.kind, "close")
        self.assertFalse(reflet.link_id._linkup_turn_user())

    def test_answered_call_from_the_options(self):
        """T-33, LU-F-044 CA1, CA3 and RM3: the first participant of a call
        reports nothing; the second, while Sam holds the three options,
        reports ``call_answered`` for both once and ends the turn. A call
        outside the options reports nothing."""
        both = frozenset((self.sam | self.france).ids)
        reflet = self._confirmed()
        link = reflet.link_id
        exact = self._child(
            reflet.with_user(self.france).action_answer_exact()
        )
        members = {
            member.partner_id: member
            for member in reflet.channel_id.sudo().channel_member_ids
        }
        sam = members[self.sam.partner_id].with_user(self.sam).sudo()
        france = members[self.france.partner_id].with_user(self.france).sudo()
        self.events.clear()
        sam._rtc_join_call()
        self.assertEqual(self.events, [])
        self.assertEqual(link.turn_reflet_id, exact)
        france._rtc_join_call()
        self.assertEqual(self.events, [("call_answered", both)])
        self.assertFalse(link.turn_reflet_id)
        with self.assertLinkupCode("linkup.already_answered"):
            exact.with_user(self.sam).action_close()
        france._rtc_leave_call()
        france._rtc_join_call()
        self.assertEqual(self.events, [("call_answered", both)])

    def test_turn_chain(self):
        """Each kind of the table of child reflections, in one chain."""
        both = frozenset((self.sam | self.france).ids)
        reflet = self._confirmed()
        link = reflet.link_id
        exact = self._child(
            reflet.with_user(self.france).action_answer_exact()
        )
        # France wrote the exact answer: the options belong to Sam.
        with self.assertRaises(AccessError):
            exact.with_user(self.france).action_close()
        cont = self._child(
            exact.with_user(self.sam).action_continue(
                self.action_cat.id, "Ta demande d'action est que…"
            )
        )
        self.assertEqual(
            (cont.kind, cont.author_id, cont.category_id),
            ("continue", self.sam, self.action_cat),
        )
        self.assertEqual(cont.understood, "Ta demande d'action est que…")
        self.assertEqual(self.events[-1], ("continue_sent", both))
        with self.assertLinkupCode("linkup.already_answered"):
            exact.with_user(self.sam).action_close()
        cont_exact = self._child(
            cont.with_user(self.france).action_answer_exact()
        )
        self.assertEqual(self.events[-1], ("continue_confirmed", both))
        disclosure = self._child(
            cont_exact.with_user(self.sam).action_self_disclosure(
                self.needs.id, "J'ai besoin de : plus de concentration."
            )
        )
        self.assertEqual(disclosure.kind, "self_disclosure")
        self.assertEqual(self.events[-1], ("continue_confirmed", both))
        self.assertEqual(link._linkup_turn_user(), self.france)
        # The disclosure reverses the roles: France reformulates Sam.
        reformulation = self._child(
            disclosure.with_user(self.france).action_continue(
                self.needs.id,
                "Donc si je comprends bien, tu as besoin de calme.",
                you_said="J'ai besoin de concentration.",
            )
        )
        self.assertEqual(reformulation.parent_id, disclosure)
        self.assertEqual(disclosure.response_state, "precision")
        self.assertEqual(reformulation.recipient_id, self.sam)
        precision = self._child(
            reformulation.with_user(self.sam).action_answer_precision(
                "Plutôt de silence."
            )
        )
        self.assertEqual(self.events[-1], ("precision_sent", both))
        self.assertEqual(link._linkup_turn_user(), self.france)
        close = self._child(precision.with_user(self.france).action_close())
        self.assertEqual(self.events[-1], ("close", both))
        self.assertEqual(link.turn_reflet_id, close)
        self.assertFalse(link._linkup_turn_user())
        self.assertEqual(close.round_index, 7)
        with self.assertLinkupCode("linkup.validation", "kind"):
            close.with_user(self.sam).action_close()
        self.assertEqual(
            [code for code, _users in self.events],
            [
                "reflect_sent",
                "reflect_confirmed",
                "answer_exact",
                "continue_sent",
                "continue_confirmed",
                "continue_sent",
                "precision_sent",
                "close",
            ],
        )

    # Error catalogue (LU-F-093)

    def test_error_code_reaches_the_client(self):
        """The code travels in ``error.data.context`` of the RPC error."""
        error = LinkupError("linkup.validation", "Message", field="you_said")
        data = serialize_exception(error)
        self.assertEqual(data["context"]["linkup_code"], "linkup.validation")
        self.assertEqual(data["context"]["linkup_field"], "you_said")

    def test_text_too_long_gives_its_limit(self):
        """A text over the limit is refused with the limit, which the client
        shows instead of a missing field."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.reflet_text_max_length", "10"
        )
        with self.assertRaises(LinkupError) as catcher:
            self._draft(you_said="Court.", understood="Beaucoup trop long.")
        data = serialize_exception(catcher.exception)
        self.assertEqual(
            data["context"],
            {
                "linkup_code": "linkup.validation",
                "linkup_field": "understood",
                "linkup_limit": 10,
            },
        )
