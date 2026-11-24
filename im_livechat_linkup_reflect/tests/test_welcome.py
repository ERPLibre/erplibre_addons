# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The welcome of the visitors (T-52, LU-F-124): the channel and its
script, the answer about an invitation, the draft of a visitor given to
the account it signs up only once the address is verified."""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import tagged

from .common import MEMBER, LinkupLivechatCase

# The choices of the welcome script (RM2).
WELCOME_CHOICES = (
    "Discover LinkUp",
    "Sign up",
    "I received an invitation",
    "Try a guided reflection",
    "Talk to a member",
    "Need help now",
)
# Step types that wait for a text typed by the visitor.
TYPED_STEPS = {
    "question_email",
    "question_phone",
    "free_input_single",
    "free_input_multi",
}


@tagged("post_install", "-at_install")
class TestLinkupLivechatWelcome(LinkupLivechatCase):
    def test_channels_of_the_data(self):
        """RM1, Q-45: the welcome channel carries the welcome script in its
        rule and is the channel of the website; the distress channel has no
        rule and no operator of its own."""
        rules = self.welcome.rule_ids
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules.chatbot_script_id, self.welcome_script)
        self.assertEqual(rules.action, "display_button")
        self.assertEqual(
            self.env.ref("website.default_website").channel_id, self.welcome
        )
        self.assertEqual(self.welcome.linkup_kind, "welcome")
        self.assertEqual(self.distress.linkup_kind, "distress")
        self.assertFalse(self.distress.rule_ids)
        self.assertFalse(self.distress.user_ids)
        self.assertEqual(self.distress.linkup_start_rule, "off")

    def test_welcome_choices(self):
        """RM2, CA1: the welcome message, then the choices, signup leading
        to ``/web/signup``; a visitor is a ``mail.guest``."""
        channel, guest = self._welcome_session()
        bodies = self._bot_bodies(channel)
        self.assertEqual(len(bodies), 2)
        self.assertIn("reflection", bodies[0])
        choice = self._answer("welcome_step_choice")
        self.assertEqual(channel.chatbot_current_step_id, choice)
        self.assertEqual(
            tuple(choice.answer_ids.sorted("sequence").mapped("name")),
            WELCOME_CHOICES,
        )
        self.assertEqual(
            self._answer("welcome_answer_signup").redirect_link, "/web/signup"
        )
        self.assertEqual(channel.channel_member_ids.guest_id, guest)
        self.assertEqual(channel.channel_type, "livechat")

    def test_invitation_asks_nothing(self):
        """RM3, CA2: no step of the script waits for a typed text, a token
        or an address; the answer about an invitation is the same for
        every visitor, and closes the script."""
        steps = self.welcome_script.script_step_ids
        self.assertFalse(set(steps.mapped("step_type")) & TYPED_STEPS)
        answers = []
        for name in ("Visiteur A", "Visiteur B"):
            channel, guest = self._welcome_session(self._visitor(name))
            next_step = self._chatbot(
                channel,
                "I received an invitation",
                answer=self._answer("welcome_answer_invitation"),
                guest=guest,
            )
            self.assertEqual(
                next_step, self._answer("welcome_step_invitation")
            )
            self.assertTrue(next_step._is_last_step(channel))
            answers.append(self._bot_bodies(channel)[-1])
        self.assertEqual(answers[0], answers[1])
        self.assertNotIn("@", answers[0])

    def test_discover_then_end(self):
        """RM2: "Discover LinkUp" tells how a reflection works in two
        messages, then the script ends."""
        channel, guest = self._welcome_session()
        step = self._chatbot(
            channel,
            "Discover LinkUp",
            answer=self._answer("welcome_answer_discover"),
            guest=guest,
        )
        self.assertEqual(step, self._answer("welcome_step_discover"))
        step = self._trigger(channel, guest=guest)
        self.assertEqual(step, self._answer("welcome_step_discover_next"))
        self.assertTrue(step._is_last_step(channel))

    def test_draft_given_after_verification(self):
        """RM4, CA3: the draft of a visitor stays theirs while the address
        of the account it signed up is not verified, then becomes the
        draft of the member, which the Reflet view restores."""
        channel, guest = self._welcome_session()
        Reflet = self.env["linkup.reflet"]
        Reflet._linkup_guest_save_draft(
            guest,
            {
                "category_id": self.emotions.id,
                "you_said": "Que la pluie te rend calme.",
                "understood": "Que tu aimes le calme.",
            },
        )
        draft = Reflet._linkup_guest_draft(guest)
        camille = mail_new_test_user(
            self.env,
            login="linkup_lc_camille",
            name="Camille",
            email="linkup_lc_camille@example.com",
            groups=MEMBER,
        )
        self._as_public_account(camille)
        camille.sudo().linkup_livechat_guest_id = guest
        self.assertFalse(camille._linkup_livechat_attach())
        self.assertEqual(draft.author_guest_id, guest)
        self.assertFalse(Reflet.with_user(camille)._linkup_draft_info())
        camille.sudo().linkup_email_verified = True
        self.assertTrue(camille._linkup_livechat_attach())
        self.assertEqual(draft.author_id, camille)
        self.assertFalse(draft.author_guest_id)
        self.assertFalse(camille.sudo().linkup_livechat_guest_id)
        info = Reflet.with_user(camille)._linkup_draft_info()
        self.assertEqual(info["id"], draft.id)
        self.assertEqual(info["category_id"], self.emotions.id)
        self.assertEqual(info["understood"], "Que tu aimes le calme.")
        # A second call gives nothing more.
        self.assertFalse(camille._linkup_livechat_attach())

    def test_member_draft_wins(self):
        """RM4: a member who already holds a draft keeps it; the draft of
        the visitor is dropped, a member holding one draft at most."""
        channel, guest = self._welcome_session()
        Reflet = self.env["linkup.reflet"]
        Reflet._linkup_guest_save_draft(guest, {"you_said": "Visiteur"})
        mine = self._draft(self.luce)
        self.luce.sudo().linkup_livechat_guest_id = guest
        self.assertTrue(self.luce._linkup_livechat_attach())
        self.assertFalse(Reflet._linkup_guest_draft(guest))
        self.assertEqual(
            Reflet.sudo().search(
                [("author_id", "=", self.luce.id), ("state", "=", "draft")]
            ),
            mine,
        )
