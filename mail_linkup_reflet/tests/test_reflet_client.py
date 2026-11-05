# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Server side of the web client: the member flag of the Store and
``linkup.reflet.linkup_channel_info`` (LU-F-016 RM3, LU-F-017, §9.6).
"""

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import LinkupRefletCase
from .test_reflet_carrier import LinkupCarrierMixin


@tagged("post_install", "-at_install")
class TestLinkupRefletClient(LinkupCarrierMixin, LinkupRefletCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = mail_new_test_user(
            cls.env,
            login="linkup_rf_employee",
            name="Employee",
            groups="base.group_user",
        )

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

    def _info(self, channel, user=None):
        return self.Reflet.with_user(user or self.sam).linkup_channel_info(
            channel.id
        )

    def test_store_member_flag(self):
        """The Store of a member says so; another internal user's does
        not. Both get the maximum of hidden themes of a precision."""
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.max_hidden_themes", "3"
        )
        for user, expected in ((self.sam, True), (self.employee, False)):
            store = Store()
            self.env["res.users"].with_user(user)._init_store_data(store)
            result = store.get_result()["Store"]
            self.assertIs(result["linkup_is_member"], expected)
            self.assertEqual(result["linkup_max_hidden_themes"], 3)

    def test_channel_info_follows_the_pair(self):
        """The answer gives the recipient, the link, the draft and the
        recent cards of the pair as the reflection goes on."""
        chat = self._chat(self.sam, self.france)
        info = self._info(chat)
        self.assertEqual(
            {
                key: info[key]
                for key in (
                    "available",
                    "can_send",
                    "recipient_id",
                    "link_state",
                    "needs_real_world",
                    "reflet_count",
                    "reflet_ids",
                    "draft",
                )
            },
            {
                "available": True,
                "can_send": True,
                "recipient_id": self.france.id,
                "link_state": "none",
                "needs_real_world": True,
                "reflet_count": 0,
                "reflet_ids": [],
                "draft": False,
            },
        )
        draft = self._draft(you_said="Brouillon", understood="")
        draft_info = self._info(chat)["draft"]
        self.assertEqual(draft_info["id"], draft.id)
        self.assertEqual(draft_info["category_id"], self.needs.id)
        self.assertEqual(draft_info["you_said"], "Brouillon")
        self.assertEqual(draft_info["understood"], "")
        draft.with_user(self.sam).action_save_draft(
            {"understood": "Que tu as besoin de calme."}
        )
        draft.with_user(self.sam).action_send(self.france.id)
        info = self._info(chat)
        self.assertEqual(info["link_state"], "pending")
        self.assertEqual(info["reflet_ids"], draft.ids)
        self.assertEqual(info["reflet_count"], 1)
        self.assertFalse(info["draft"])
        cards = info["store"]["linkup.reflet"]
        self.assertEqual([card["id"] for card in cards], draft.ids)
        self.assertEqual(cards[0]["state"], "sent")
        # France reads the same pair from her side, and confirms.
        info = self._info(chat, self.france)
        self.assertEqual(info["recipient_id"], self.sam.id)
        self.assertEqual(info["reflet_ids"], draft.ids)
        draft.with_user(self.france).action_confirm()
        info = self._info(chat)
        self.assertEqual(info["link_state"], "active")
        self.assertFalse(info["needs_real_world"])
        self.assertTrue(info["first_link_date"])

    def test_channel_info_most_recent_first(self):
        """The cards are the most recent reflections of the pair, at most
        five, and the count covers all of them."""
        first = self._confirmed()
        for _index in range(5):
            self._sent(category_id=self.goals.id)
        info = self._info(first.channel_id)
        self.assertEqual(info["reflet_count"], 6)
        self.assertEqual(len(info["reflet_ids"]), 5)
        self.assertNotIn(first.id, info["reflet_ids"])
        self.assertEqual(info["reflet_ids"], sorted(info["reflet_ids"])[::-1])

    def test_channel_info_private_part(self):
        """The hidden themes of a precision reach its author only."""
        reflet = self._confirmed()
        precision = self._precision(reflet)
        themes = self.goals | self.emotions
        for user, sees in ((self.france, True), (self.sam, False)):
            info = self._info(reflet.channel_id, user)
            self.assertIn(precision.id, info["reflet_ids"])
            if sees:
                card = next(
                    card
                    for card in info["store"]["linkup.reflet"]
                    if card["id"] == precision.id
                    and "revealed_category_ids" in card
                )
                self.assertEqual(
                    sorted(card["revealed_category_ids"]), sorted(themes.ids)
                )
            else:
                self.assertNoHiddenTheme(info["store"], themes)

    def test_channel_info_closed_and_blocked(self):
        """A rejected first reflection closes the link; a blocked link
        reads closed, and the other member is out of reach."""
        reflet = self._sent()
        reflet.with_user(self.france).action_reject()
        self.workshop.channel_member_ids.filtered(
            lambda member: member.partner_id == self.france.partner_id
        ).unlink()
        info = self._info(reflet.channel_id)
        self.assertEqual(info["link_state"], "closed")
        self.assertFalse(info["can_send"])
        reflet.link_id.sudo().state = "blocked"
        self.assertEqual(self._info(reflet.channel_id)["link_state"], "closed")

    def test_channel_info_unavailable(self):
        """Any other conversation gets the same refusal."""
        unavailable = {"available": False}
        france_jacques = self._chat(self.france, self.jacques)
        # The employee, outside LinkUp, opens the chat with Sam.
        sam_employee = self._chat(self.employee, self.sam)
        for channel_id in (
            self.workshop.id,
            france_jacques.id,
            sam_employee.id,
            0,
            "not an id",
        ):
            with self.subTest(channel_id=channel_id):
                self.assertEqual(
                    self.Reflet.with_user(self.sam).linkup_channel_info(
                        channel_id
                    ),
                    unavailable,
                )
        with self.assertRaises(AccessError):
            self.Reflet.with_user(self.employee).linkup_channel_info(
                self.workshop.id
            )

    def _history(self, channel, user=None, **filters):
        return self.Reflet.with_user(user or self.sam).linkup_history(
            channel.id, **filters
        )

    def test_history_filters(self):
        """The history of a pair lists the reflections sent and received,
        filtered by visible category and by state (LU-F-018 CA1)."""
        emotions = self._confirmed()
        emotions.write({"category_id": self.emotions.id})
        goals = self._sent(category_id=self.goals.id)
        needs = self._sent(author=self.france, recipient=self.sam)
        chat = emotions.channel_id
        history = self._history(chat)
        self.assertEqual(history["count"], 3)
        self.assertEqual(
            history["reflet_ids"], [needs.id, goals.id, emotions.id]
        )
        history = self._history(chat, category_id=self.goals.id)
        self.assertEqual(history["reflet_ids"], [goals.id])
        self.assertEqual(
            [card["id"] for card in history["store"]["linkup.reflet"]],
            [goals.id],
        )
        history = self._history(chat, state="confirmed")
        self.assertEqual(history["reflet_ids"], [emotions.id])
        for state in ("draft", "zz-unknown"):
            with self.subTest(state=state), self.assertLinkupCode(
                "linkup.validation", field="state"
            ):
                self._history(chat, state=state)
        self.assertEqual(self._history(self.workshop), {"available": False})

    def test_history_keeps_the_hidden_theme(self):
        """A precision whose theme is still to guess matches none of its
        hidden themes as a category, and its card hides them from its
        recipient (LU-F-018 RM2)."""
        reflet = self._confirmed()
        precision = self._precision(reflet)
        themes = self.goals | self.emotions
        for theme in themes:
            history = self._history(reflet.channel_id, category_id=theme.id)
            self.assertNotIn(precision.id, history["reflet_ids"])
        history = self._history(reflet.channel_id)
        self.assertIn(precision.id, history["reflet_ids"])
        self.assertNoHiddenTheme(history["store"], themes)
