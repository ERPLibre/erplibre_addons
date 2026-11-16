# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from lxml import etree
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user

DEFAULT_EN = "You won a prize, come and claim it!"
DEFAULT_FR = "Vous avez reçu un prix, venez le réclamer!"


class TestRaffleDrawNotify(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                mail_create_nolog=True,
                mail_notrack=True,
                no_reset_password=True,
            )
        )
        cls.odoobot = cls.env.ref("base.partner_root")
        cls.organizer = new_test_user(
            cls.env,
            login="raffle_organizer",
            groups="base.group_user,event.group_event_user",
            email="organizer@example.com",
            name="Raffle Organizer",
        )
        cls.portal_winner = new_test_user(
            cls.env,
            login="raffle_portal_winner",
            groups="base.group_portal",
            email="portal.winner@example.com",
            name="Portal Winner",
        )
        cls.internal_winner = new_test_user(
            cls.env,
            login="raffle_internal_winner",
            groups="base.group_user",
            email="internal.winner@example.com",
            name="Internal Winner",
        )
        cls.contact = cls.env["res.partner"].create(
            {"name": "Mail Winner", "email": "mail.winner@example.com"}
        )
        cls.raffle = cls.env["event.raffle"].create({"name": "R"})

    def _draw(self, partner=None, **kw):
        vals = {"raffle_id": self.raffle.id, "winner_name": "W"}
        if partner:
            participant = self.env["event.raffle.participant"].create(
                {
                    "raffle_id": self.raffle.id,
                    "name": partner.name,
                    "partner_id": partner.id,
                }
            )
            vals["winner_participant_id"] = participant.id
        vals.update(kw)
        return self.env["event.raffle.draw"].create(vals)

    def _wizard(self, draw, user=None, **vals):
        user = user or self.organizer
        vals["draw_id"] = draw.id
        Wizard = self.env["event.raffle.draw.notify.wizard"].with_user(user)
        return Wizard.create(vals)

    def _send(self, draw, user=None, **vals):
        wizard = self._wizard(draw, user=user, **vals)
        wizard.action_send()
        return draw.notification_ids.sorted("id")[-1]

    def _member(self, channel, partner):
        return channel.channel_member_ids.filtered(
            lambda m: m.partner_id == partner
        )

    # Wizard defaults

    def test_defaults_are_odoobot_and_the_english_message(self):
        wizard = self._wizard(self._draw(self.portal_winner.partner_id))
        self.assertEqual(wizard.sender, "odoobot")
        self.assertEqual(wizard.body, DEFAULT_EN)
        self.assertEqual(wizard.delivery, "chat")

    def test_default_message_is_translated(self):
        self.env["res.lang"]._activate_lang("fr_CA")
        draw = self._draw(self.portal_winner.partner_id)
        Wizard = self.env["event.raffle.draw.notify.wizard"].with_context(
            lang="fr_CA"
        )
        wizard = Wizard.with_user(self.organizer).create({"draw_id": draw.id})
        self.assertEqual(wizard.body, DEFAULT_FR)

    # Chat path

    def _assert_chat_path(self, winner_user, sender, author):
        winner = winner_user.partner_id
        draw = self._draw(winner)
        self.assertFalse(draw.notified)
        notif = self._send(draw, sender=sender, body="Come to the desk")
        channel = notif.discuss_channel_id
        self.assertEqual(notif.channel, "chat")
        self.assertEqual(channel.channel_type, "chat")
        self.assertEqual(
            channel.channel_member_ids.partner_id, author | winner
        )
        self.assertEqual(notif.message_id.author_id, author)
        self.assertEqual(notif.message_id.model, "discuss.channel")
        self.assertEqual(notif.message_id.res_id, channel.id)
        self.assertIn("Come to the desk", notif.message_id.body)
        self.assertEqual(notif.author_id, author)
        self.assertEqual(draw.notification_count, 1)
        self.assertTrue(draw.notified)
        self.assertFalse(draw.notification_read)
        self.assertIn(
            f"Notification sent by chat by {author.name}.",
            draw.message_ids.mapped("body")[0],
        )
        # A second send reuses the conversation and counts again.
        second = self._send(draw, sender=sender)
        self.assertEqual(second.discuss_channel_id, channel)
        self.assertEqual(draw.notification_count, 2)
        self.assertFalse(draw.notification_read)
        # Seeing the first message only is not reading the latest one.
        member = self._member(channel, winner).with_user(winner_user)
        member._mark_as_read(notif.message_id.id)
        self.assertFalse(draw.notification_read)
        member._mark_as_read(second.message_id.id)
        self.assertTrue(second.is_read)
        self.assertTrue(draw.notification_read)

    def test_chat_to_a_portal_winner_as_odoobot(self):
        self._assert_chat_path(self.portal_winner, "odoobot", self.odoobot)

    def test_chat_to_an_internal_winner_as_odoobot(self):
        self._assert_chat_path(self.internal_winner, "odoobot", self.odoobot)

    def test_chat_to_a_portal_winner_as_self(self):
        self._assert_chat_path(
            self.portal_winner, "me", self.organizer.partner_id
        )

    def test_chat_to_an_internal_winner_as_self(self):
        self._assert_chat_path(
            self.internal_winner, "me", self.organizer.partner_id
        )

    def test_archived_user_falls_back_to_email(self):
        self.internal_winner.active = False
        wizard = self._wizard(self._draw(self.internal_winner.partner_id))
        self.assertEqual(wizard.delivery, "email")
        self.internal_winner.active = True

    def test_self_cannot_chat_with_itself(self):
        draw = self._draw(self.organizer.partner_id)
        with self.assertRaises(UserError):
            self._send(draw, sender="me")

    # Email path

    def test_email_to_a_contact_without_user(self):
        draw = self._draw(self.contact)
        wizard = self._wizard(draw)
        self.assertEqual(wizard.delivery, "email")
        wizard.action_send()
        notif = draw.notification_ids
        mail = notif.mail_id
        self.assertEqual(notif.channel, "email")
        self.assertEqual(mail.recipient_ids, self.contact)
        self.assertIn(DEFAULT_EN, mail.body_html)
        self.assertIn("OdooBot", mail.email_from)
        self.assertEqual(mail.author_id, self.odoobot)
        self.assertEqual(notif.message_id, mail.mail_message_id)
        self.assertEqual(draw.notification_count, 1)
        self.assertTrue(draw.notified)
        self.assertFalse(draw.notification_read)
        self.assertIn(
            "Notification sent by email by OdooBot.",
            draw.message_ids.mapped("body")[0],
        )

    def test_email_to_the_draw_address_without_contact(self):
        draw = self._draw(winner_email="guest.winner@example.com")
        notif = self._send(draw, sender="me", body="See you there")
        mail = notif.mail_id
        self.assertEqual(mail.email_to, "guest.winner@example.com")
        self.assertFalse(mail.recipient_ids)
        self.assertIn("See you there", mail.body_html)
        self.assertIn("organizer@example.com", mail.email_from)
        self.assertEqual(mail.author_id, self.organizer.partner_id)
        self.assertFalse(draw.notification_read)

    def test_no_user_and_no_email_cannot_be_notified(self):
        draw = self._draw(self.env["res.partner"].create({"name": "Nobody"}))
        wizard = self._wizard(draw)
        self.assertEqual(wizard.delivery, "none")
        self.assertIn(
            "neither a user account nor an email", wizard.delivery_info
        )
        with self.assertRaises(UserError):
            wizard.action_send()
        self.assertFalse(draw.notification_ids)

    def test_an_absent_winner_can_be_notified(self):
        draw = self._draw(self.portal_winner.partner_id)
        draw.action_mark_absent()
        self._send(draw)
        self.assertTrue(draw.is_absent)
        self.assertEqual(draw.notification_count, 1)

    # Access

    def test_a_user_without_draw_write_access_cannot_notify(self):
        plain = new_test_user(
            self.env, login="raffle_plain", groups="base.group_user"
        )
        draw = self._draw(self.portal_winner.partner_id)
        with self.assertRaises(AccessError):
            self._send(draw, user=plain)
        with self.assertRaises(AccessError):
            draw.with_user(plain).action_open_notify_wizard()
        self.assertFalse(draw.notification_ids)

    def test_the_sender_is_odoobot_or_self_only(self):
        draw = self._draw(self.portal_winner.partner_id)
        with self.assertRaises(ValueError):
            self._wizard(draw, sender="other")
        # The author follows the selection, whatever the context says.
        wizard = self._wizard(draw, sender="me").with_context(
            default_author_id=self.internal_winner.partner_id.id
        )
        wizard.action_send()
        notif = draw.notification_ids
        self.assertEqual(notif.message_id.author_id, self.organizer.partner_id)

    def test_open_wizard_action(self):
        draw = self._draw(self.portal_winner.partner_id)
        action = draw.with_user(self.organizer).action_open_notify_wizard()
        self.assertEqual(
            action["res_model"], "event.raffle.draw.notify.wizard"
        )
        self.assertEqual(action["context"]["default_draw_id"], draw.id)

    # Views

    def _list_columns(self, arch):
        return [
            (f.get("name"), f.get("optional")) for f in arch.xpath("./field")
        ]

    def _assert_columns_after_date(self, list_node):
        columns = self._list_columns(list_node)
        names = [name for name, _optional in columns]
        start = names.index("date") + 1
        self.assertEqual(
            columns[start : start + 3],
            [
                ("notified", "show"),
                ("notification_read", "show"),
                ("notification_count", "show"),
            ],
        )

    def test_list_views_show_the_notification_columns_after_date(self):
        Draw = self.env["event.raffle.draw"]
        view = self.env.ref("event_raffle.event_raffle_draw_view_list")
        arch = Draw.get_view(view.id, "list")["arch"]
        self._assert_columns_after_date(etree.fromstring(arch))
        form = self.env.ref("event_raffle.event_raffle_view_form")
        arch = etree.fromstring(form.arch)
        tab = arch.xpath("//field[@name='draw_ids']/list")[0]
        self._assert_columns_after_date(tab)

    def test_notify_button_follows_the_absence_buttons(self):
        form = self.env.ref("event_raffle.event_raffle_draw_view_form")
        arch = etree.fromstring(form.arch)
        names = arch.xpath("//header/button/@name")
        self.assertEqual(
            names,
            [
                "action_mark_absent",
                "action_mark_present",
                "action_open_notify_wizard",
            ],
        )
