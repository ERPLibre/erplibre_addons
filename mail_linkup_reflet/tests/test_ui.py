# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Web client of the reflections: the tours of a sending (T-03, T-28,
LU-F-012 to LU-F-017), of the strict start rule (T-08, LU-F-061), of the
validation and the exact answer (T-18, LU-F-021 to LU-F-030), of a precision
and its guess (LU-F-031 to LU-F-042), of the Reflet view (T-24, LU-F-010 to
LU-F-016), of NewLink (T-29, LU-F-020), of the first-use tour (T-25,
LU-F-083), of a sending with the keyboard only (T-18, LU-NF-020), of the
three options (P4, LU-F-040 to LU-F-044), of "You add to my happiness" (P5,
LU-F-050, LU-F-051), and the Hoot unit tests of the module (§12.1).
"""

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.web.tests import test_js
from odoo.tests import HttpCase, tagged

from .common import MEMBER

# Suite of the Hoot tests of the module, as the Hoot runner names it.
HOOT_SUITE = "@mail_linkup_reflet"


@tagged("post_install", "-at_install")
class TestLinkupRefletUi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_CA")
        cls.env["ir.module.module"].search(
            [("name", "=", "mail_linkup_reflet")]
        )._update_translations(["fr_CA"])

        def member(login, name):
            return mail_new_test_user(
                cls.env,
                login=login,
                password=login,
                name=name,
                email=f"{login}@example.com",
                groups=MEMBER,
                lang="fr_CA",
            )

        cls.sam = member("linkup_ui_sam", "Sam")
        cls.france = member("linkup_ui_france", "France")
        # The first-use tour would cover the screens the other tours use.
        (cls.sam | cls.france).write({"linkup_tour_done": True})
        # A shared group conversation puts each one in the other's scope.
        cls.env["discuss.channel"].create(
            {
                "name": "Atelier",
                "channel_type": "group",
                "channel_member_ids": [
                    Command.create({"partner_id": user.partner_id.id})
                    for user in (cls.sam, cls.france)
                ],
            }
        )
        # Opened as the server does: a member alone opens it only once
        # their link is active.
        cls.chat = (
            cls.env["discuss.channel"]
            .with_user(cls.sam)
            .sudo()
            .channel_get([cls.france.partner_id.id])
            .sudo(False)
        )

    @property
    def chat_url(self):
        return f"/odoo/discuss?active_id=discuss.channel_{self.chat.id}"

    def _send(self, understood, category="needs"):
        """A reflection of Sam sent to France, as the web client sends it."""
        Reflet = self.env["linkup.reflet"].with_user(self.sam)
        draft_id = Reflet.action_save_draft(
            {
                "category_id": self.env["linkup.category"]
                .search([("code", "=", category)])
                .id,
                "you_said": "Que tu as passé la journée sans pause.",
                "understood": understood,
                "real_world_declared": True,
            }
        )
        reflet = Reflet.browse(draft_id)
        reflet.action_send(self.france.id)
        return reflet.sudo()

    def test_reflet_send_tour(self):
        """Sam opens the conversation of France, chooses Emotions, fills
        the form and sends: the card shows the reflection waiting."""
        self.start_tour(
            f"/odoo/discuss?active_id=discuss.channel_{self.chat.id}",
            "linkup_reflet_send_tour",
            login=self.sam.login,
        )
        reflet = self.env["linkup.reflet"].search(
            [("author_id", "=", self.sam.id)]
        )
        self.assertEqual(len(reflet), 1)
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(reflet.recipient_id, self.france)
        self.assertEqual(reflet.category_id.code, "emotions")
        self.assertEqual(reflet.understood, "tu es épuisée.")
        self.assertTrue(reflet.real_world_declared)
        self.assertEqual(reflet.channel_id, self.chat)
        self.assertEqual(reflet.message_id.linkup_reflet_id, reflet)

    def test_reflet_view_tour(self):
        """Sam lands in the Reflet view, drops Emotions on France, fills
        the form and sends, then opens the conversation of France."""
        self.start_tour(
            "/odoo", "linkup_reflet_view_tour", login=self.sam.login
        )
        reflet = self.env["linkup.reflet"].search(
            [("author_id", "=", self.sam.id)]
        )
        self.assertEqual(len(reflet), 1)
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(reflet.recipient_id, self.france)
        self.assertEqual(reflet.category_id.code, "emotions")
        self.assertEqual(reflet.understood, "tu es épuisée.")
        self.assertEqual(reflet.channel_id, self.chat)

    def test_newlink_tour(self):
        """Sam invites a person who is not a member from the Reflet view:
        the reflection waits for the invitation, and the email leaves its
        texts out (T-29, LU-F-020 CA1)."""
        self.start_tour("/odoo", "linkup_newlink_tour", login=self.sam.login)
        invitation = self.env["linkup.invitation"].search(
            [("inviter_id", "=", self.sam.id)]
        )
        self.assertEqual(len(invitation), 1)
        self.assertEqual(invitation.email, "camille.nouvelle@example.com")
        self.assertEqual(invitation.name, "Camille")
        reflet = invitation.reflet_id
        self.assertEqual(reflet.state, "pending_invite")
        self.assertEqual(reflet.category_id.code, "emotions")
        self.assertEqual(reflet.understood, "tu es épuisée.")
        self.assertFalse(reflet.recipient_id)
        mail = self.env["mail.mail"].search(
            [("email_to", "=", "camille.nouvelle@example.com")]
        )
        self.assertEqual(len(mail), 1)
        self.assertIn("/linkup/invite/", mail.body_html)
        self.assertNotIn("tu es épuisée", mail.body_html)

    def test_strict_mode_tour(self):
        """In strict mode, Sam finds the banner of the start rule in place
        of the text field of a conversation no reflection opened yet, and
        its button leads to the Help bar."""
        self.env["ir.config_parameter"].set_param(
            "linkup.start_rule_mode", "strict"
        )
        self.start_tour(
            self.chat_url, "linkup_strict_mode_tour", login=self.sam.login
        )
        self.assertFalse(
            self.env["mail.message"].search_count(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "=", self.chat.id),
                    ("message_type", "=", "comment"),
                ]
            )
        )

    def test_first_use_tour(self):
        """France, who never saw the tour, opens Discuss: the tour starts at
        step 1 of 5 and follows its five elements; once finished, it is
        recorded on her user and does not start again (T-25, LU-F-083)."""
        self.france.linkup_tour_done = False
        self.start_tour(
            self.chat_url,
            "linkup_first_use_driver_tour",
            login=self.france.login,
        )
        self.assertTrue(self.france.linkup_tour_done)

    def test_reflet_confirm_tour(self):
        """France rejects a first reflection with the arrow key and its
        confirmation, confirms a second one with the other arrow, then
        answers that it is exactly it, with a word."""
        rejected = self._send("tu veux manger")
        confirmed = self._send("tu es épuisée.")
        self.start_tour(
            self.chat_url,
            "linkup_reflet_confirm_tour",
            login=self.france.login,
        )
        self.env.invalidate_all()
        self.assertEqual(rejected.state, "rejected")
        self.assertEqual(confirmed.state, "confirmed")
        self.assertEqual(confirmed.link_id.state, "active")
        self.assertEqual(confirmed.response_state, "exact")
        answer = confirmed.child_ids
        self.assertEqual(answer.kind, "answer_exact")
        self.assertEqual(answer.author_id, self.france)
        self.assertEqual(answer.body_text, "C'est bien ça.")
        self.assertEqual(answer.message_id.linkup_reflet_id, answer)
        self.assertEqual(confirmed.link_id.turn_reflet_id, answer)

    def test_precision_guess_tour(self):
        """France hides Buts and Émotions in a precision whose text she
        writes from an empty field; Sam, whose client never holds the
        themes before guessing, finds Buts, then continues the reflection
        with the starter of Demande d'action."""
        reflet = self._send("tu es épuisée.", "emotions")
        reflet.with_user(self.france).action_confirm()
        self.start_tour(
            self.chat_url,
            "linkup_precision_send_tour",
            login=self.france.login,
        )
        self.env.invalidate_all()
        precision = reflet.child_ids
        self.assertEqual(precision.kind, "precision")
        self.assertEqual(precision.guess_state, "pending")
        self.assertEqual(
            precision.body_text,
            "Mon but est vraiment de trouver une personne pour faire avancer"
            " cette situation…",
        )
        secret = self.env["linkup.reflet.secret"].search(
            [("reflet_id", "=", precision.id)]
        )
        self.assertEqual(
            set(secret.category_ids.mapped("code")), {"emotions", "goals"}
        )
        self.assertEqual(secret.primary_category_id.code, "goals")
        self.start_tour(
            self.chat_url, "linkup_precision_guess_tour", login=self.sam.login
        )
        self.env.invalidate_all()
        self.assertEqual(precision.guess_state, "found")
        self.assertEqual(precision.guessed_category_id.code, "goals")
        follow = precision.child_ids
        self.assertEqual(follow.kind, "continue")
        self.assertEqual(follow.author_id, self.sam)
        self.assertEqual(follow.category_id.code, "action")
        self.assertEqual(
            follow.understood,
            "Ta demande d'action est que : tu trouves quelqu'un pour avancer.",
        )

    def test_keyboard_only_tour(self):
        """Sam writes and sends a reflection from the Reflet view with the
        keyboard only (T-18, P1)."""
        self.start_tour(
            "/odoo", "linkup_keyboard_only_tour", login=self.sam.login
        )
        reflet = self.env["linkup.reflet"].search(
            [("author_id", "=", self.sam.id)]
        )
        self.assertEqual(len(reflet), 1)
        self.assertEqual(reflet.state, "sent")
        self.assertEqual(reflet.recipient_id, self.france)
        self.assertEqual(reflet.category_id.code, "emotions")
        self.assertEqual(reflet.understood, "tu es épuisée.")
        self.assertTrue(reflet.real_world_declared)

    def test_next_options_tour(self):
        """After the exact answer of France, Sam talks about himself; once
        France reformulated him and he answered that it is exactly it,
        France ends the exchange with the keyboard (P4)."""
        Reflet = self.env["linkup.reflet"]
        reflet = self._send("tu es épuisée.")
        reflet.with_user(self.france).action_confirm()
        exact = Reflet.browse(
            reflet.with_user(self.france).action_answer_exact()
        )
        self.start_tour(
            self.chat_url,
            "linkup_talk_about_oneself_tour",
            login=self.sam.login,
        )
        self.env.invalidate_all()
        disclosure = exact.child_ids
        self.assertEqual(disclosure.kind, "self_disclosure")
        self.assertEqual(disclosure.author_id, self.sam)
        self.assertEqual(disclosure.category_id.code, "needs")
        self.assertEqual(
            disclosure.body_text, "J'ai besoin de : plus de concentration."
        )
        self.assertEqual(disclosure.link_id.turn_reflet_id, disclosure)
        reformulation = Reflet.browse(
            disclosure.with_user(self.france).action_continue(
                disclosure.category_id.id,
                "Donc si je comprends bien, tu as besoin de calme.",
            )
        )
        answer = Reflet.browse(
            reformulation.with_user(self.sam).action_answer_exact()
        )
        self.start_tour(
            self.chat_url, "linkup_end_it_here_tour", login=self.france.login
        )
        self.env.invalidate_all()
        close = answer.child_ids
        self.assertEqual(close.kind, "close")
        self.assertEqual(close.author_id, self.france)
        self.assertFalse(close.body_text)
        self.assertFalse(close.link_id._linkup_turn_user())

    def test_happiness_tour(self):
        """France puts Sam in the light from their conversation with the
        mouse; Sam sees it in the Reflet view and puts France in the light
        in turn with the keyboard (P5)."""
        Highlight = self.env["linkup.highlight"]
        self.start_tour(
            self.chat_url,
            "linkup_happiness_send_tour",
            login=self.france.login,
        )
        received = Highlight.search(
            [("sender_id", "=", self.france.id), ("active", "=", True)]
        )
        self.assertEqual(received.recipient_id, self.sam)
        self.assertEqual(received.context, "thread")
        self.assertEqual(received.channel_id, self.chat)
        self.start_tour(
            "/odoo", "linkup_happiness_receive_tour", login=self.sam.login
        )
        sent = Highlight.search(
            [("sender_id", "=", self.sam.id), ("active", "=", True)]
        )
        self.assertEqual(sent.recipient_id, self.france)
        self.assertEqual(sent.context, "drag")


@tagged("post_install", "-at_install")
class TestLinkupRefletHoot(HttpCase):
    def test_hoot_suite(self):
        """The Hoot tests of the module, in a desktop browser."""
        # The module is imported rather than its classes: a test class
        # imported here would be collected and run with this module.
        suite_id = test_js.HOOTCommon._generate_hash(self, HOOT_SUITE)
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000"
            f"&id={suite_id}",
            "",
            "",
            login="admin",
            timeout=1800,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=test_js.unit_test_error_checker,
        )
