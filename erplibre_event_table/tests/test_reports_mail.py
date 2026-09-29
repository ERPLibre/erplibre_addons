# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import UserError

from .common import EventTableCommon


class TestReportsMailCommon(EventTableCommon):
    """Fixture: a two-round plan whose combination is already chosen.

    Two tables of two seats hold four seated people; a fifth participant is
    created before the choice and stays without a seat, which is the case the
    card and the email counters have to handle.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.event = cls.env["event.event"].create(
            {
                "name": "Spring Forum",
                "date_begin": "2026-04-02 09:00:00",
                "date_end": "2026-04-02 17:00:00",
                "use_rotating_tables": True,
            }
        )
        cls.plan = cls.env["event.table.plan"].create(
            {
                "name": "Spring Forum Tables",
                "event_id": cls.event.id,
                "round_count": 2,
                "assign_seats": True,
            }
        )
        cls.table_1, cls.table_2 = cls.env["event.table"].create(
            [
                {"plan_id": cls.plan.id, "number": 1, "seat_count": 2},
                {"plan_id": cls.plan.id, "number": 2, "seat_count": 2},
            ]
        )
        (
            cls.ana,
            cls.bo,
            cls.cleo,
            cls.dev,
            cls.eve,
        ) = cls.env["event.table.participant"].create(
            [
                {
                    "plan_id": cls.plan.id,
                    "name": "Ana Bloom",
                    "email": "ana.bloom@example.com",
                    "company_label": "Bluecrest",
                },
                {
                    "plan_id": cls.plan.id,
                    "name": "Bo Carver",
                    "email": "bo.carver@example.com",
                    "company_label": "Bluecrest",
                },
                {
                    "plan_id": cls.plan.id,
                    "name": "Cleo Dane",
                    "email": "cleo.dane@example.com",
                    "company_label": "Marlow",
                },
                {
                    "plan_id": cls.plan.id,
                    "name": "Dev Ellis",
                    "email": "dev.ellis@example.com",
                    "company_label": "Marlow",
                },
                {
                    "plan_id": cls.plan.id,
                    "name": "Eve Frost",
                    "company_label": "Marlow",
                },
            ]
        )
        cls.combination = cls.env["event.table.combination"].create(
            {
                "plan_id": cls.plan.id,
                "rank": 1,
                "placement_data": [
                    [1, cls.ana.id, 1, 1],
                    [1, cls.bo.id, 1, 2],
                    [1, cls.cleo.id, 2, 1],
                    [1, cls.dev.id, 2, 2],
                    [2, cls.ana.id, 1, 1],
                    [2, cls.cleo.id, 1, 2],
                    [2, cls.bo.id, 2, 1],
                    [2, cls.dev.id, 2, 2],
                ],
            }
        )
        # action_choose only accepts a proposed or chosen plan; the fixture
        # writes the combinations itself instead of running a search.
        cls.plan.state = "proposed"
        cls.combination.action_choose()


class TestReports(TestReportsMailCommon):
    def test_report_rows_lists_one_row_per_round(self):
        self.assertEqual(
            self.ana._report_rows(),
            [
                {"round": 1, "table_number": 1, "seat_number": 1},
                {"round": 2, "table_number": 1, "seat_number": 1},
            ],
        )
        self.assertEqual(
            self.bo._report_rows(),
            [
                {"round": 1, "table_number": 1, "seat_number": 2},
                {"round": 2, "table_number": 2, "seat_number": 1},
            ],
        )

    def test_report_rows_empty_without_assignment(self):
        self.assertEqual(self.eve._report_rows(), [])

    def test_report_rounds_covers_every_round_of_the_plan(self):
        rounds = self.table_1._report_rounds()
        self.assertEqual([entry["round"] for entry in rounds], [1, 2])
        self.assertEqual(
            rounds[0]["rows"],
            [
                {
                    "seat_number": 1,
                    "name": "Ana Bloom",
                    "company": "Bluecrest",
                },
                {
                    "seat_number": 2,
                    "name": "Bo Carver",
                    "company": "Bluecrest",
                },
            ],
        )
        self.assertEqual(
            rounds[1]["rows"],
            [
                {
                    "seat_number": 1,
                    "name": "Ana Bloom",
                    "company": "Bluecrest",
                },
                {
                    "seat_number": 2,
                    "name": "Cleo Dane",
                    "company": "Marlow",
                },
            ],
        )

    def test_report_rounds_keeps_an_empty_round(self):
        # A table nobody sits at still reports one entry per round. A plan
        # of its own keeps this independent of the chosen fixture: creating
        # a table is a structural change, refused outside draft.
        plan = self.env["event.table.plan"].create(
            {
                "name": "Empty Room",
                "event_id": self.event.id,
                "round_count": 2,
            }
        )
        empty_table = self.env["event.table"].create(
            {"plan_id": plan.id, "number": 1, "seat_count": 2}
        )
        self.assertEqual(
            empty_table._report_rounds(),
            [{"round": 1, "rows": []}, {"round": 2, "rows": []}],
        )

    def _render(self, report_ref, records):
        html, report_type = self.env["ir.actions.report"]._render_qweb_html(
            report_ref, records.ids
        )
        self.assertEqual(report_type, "html")
        return html.decode()

    def test_participant_card_prints_names_tables_and_seats(self):
        html = self._render(
            "erplibre_event_table.report_participant_card",
            self.plan._included_participants(),
        )
        self.assertIn(
            '<h3 class="o_event_table_card_name">Ana Bloom</h3>', html
        )
        self.assertIn(
            '<h3 class="o_event_table_card_name">Eve Frost</h3>', html
        )
        self.assertIn("Spring Forum", html)
        self.assertIn("Bluecrest", html)
        # Four seated people over two rounds: eight table numbers, and no
        # ninth one for the participant who has no seat.
        self.assertEqual(
            html.count('<span class="o_event_table_card_number">'), 8
        )
        self.assertIn('<span class="o_event_table_card_number">2</span>', html)
        self.assertIn('<span class="o_event_table_card_seat">2</span>', html)
        self.assertIn("No table assigned yet.", html)

    def test_participant_card_hides_the_seat_column_without_seats(self):
        # The plan is stripped of its seating by hand, then re-seated
        # from a combination built without seat numbers.
        placements = self.combination.placement_data
        self.plan.assignment_ids.with_context(
            event_table_assignment_write=True
        ).unlink()
        self.plan.chosen_combination_id = False
        self.plan.combination_ids.unlink()
        self.plan.assign_seats = False
        combination = self.env["event.table.combination"].create(
            {
                "plan_id": self.plan.id,
                "rank": 1,
                "placement_data": placements,
            }
        )
        self.plan.state = "proposed"
        combination.action_choose()
        html = self._render(
            "erplibre_event_table.report_participant_card",
            self.plan._included_participants(),
        )
        self.assertEqual(
            html.count('<span class="o_event_table_card_seat">'), 0
        )
        self.assertEqual(
            html.count('<span class="o_event_table_card_number">'), 8
        )

    def test_table_sheet_prints_one_page_per_table(self):
        html = self._render(
            "erplibre_event_table.report_table_sheet", self.plan.table_ids
        )
        self.assertIn('<h1 class="o_event_table_sheet_number">1</h1>', html)
        self.assertIn('<h1 class="o_event_table_sheet_number">2</h1>', html)
        self.assertIn("Spring Forum", html)
        # Two tables, two rounds, two people each.
        self.assertEqual(
            html.count('<span class="o_event_table_sheet_name">'), 8
        )
        self.assertIn(
            '<span class="o_event_table_sheet_name">Ana Bloom</span>', html
        )
        self.assertIn(
            '<span class="o_event_table_sheet_name">Dev Ellis</span>', html
        )
        self.assertIn("Marlow", html)
        self.assertEqual(html.count("page-break-after: always"), 2)

    def test_print_participant_cards_targets_included_participants(self):
        # discard_logo_check keeps report_action from returning the report
        # layout configuration wizard when the company has no external
        # layout.
        action = self.plan.with_context(
            discard_logo_check=True
        ).action_print_participant_cards()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(
            action["report_name"],
            "erplibre_event_table.report_participant_card",
        )
        self.assertEqual(
            action["context"]["active_ids"],
            self.plan._included_participants().ids,
        )

    def test_print_table_sheets_targets_every_table(self):
        action = self.plan.with_context(
            discard_logo_check=True
        ).action_print_table_sheets()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(
            action["report_name"],
            "erplibre_event_table.report_table_sheet",
        )
        self.assertEqual(
            action["context"]["active_ids"], self.plan.table_ids.ids
        )

    def test_printing_refused_before_anyone_is_seated(self):
        # The refusal hangs on the seating, not on a state: a plan whose
        # people were placed by hand prints without ever being "chosen".
        self.plan.assignment_ids.with_context(
            event_table_assignment_write=True
        ).unlink()
        with self.assertRaises(UserError) as error:
            self.plan.action_print_participant_cards()
        self.assertIn("Nobody is seated yet.", str(error.exception))
        with self.assertRaises(UserError) as error:
            self.plan.action_print_table_sheets()
        self.assertIn("Nobody is seated yet.", str(error.exception))


class TestAssignmentEmails(TestReportsMailCommon):
    def _sent_mails(self, action):
        """Mails the action put in the queue, and only those."""
        before = self.env["mail.mail"].search([])
        action()
        return self.env["mail.mail"].search([]) - before

    def test_send_creates_one_mail_per_participant_with_an_email(self):
        mails = self._sent_mails(self.plan.action_send_assignment_emails)
        self.assertEqual(len(mails), 4)
        recipients = sorted(mails.mapped("email_to"))
        self.assertEqual(
            recipients,
            [
                '"Ana Bloom" <ana.bloom@example.com>',
                '"Bo Carver" <bo.carver@example.com>',
                '"Cleo Dane" <cleo.dane@example.com>',
                '"Dev Ellis" <dev.ellis@example.com>',
            ],
        )
        self.assertNotIn("Eve Frost", " ".join(recipients))

    def test_mail_body_holds_the_rounds_of_that_participant(self):
        mails = self._sent_mails(self.plan.action_send_assignment_emails)
        ana_mail = mails.filtered(
            lambda mail: "ana.bloom@example.com" in (mail.email_to or "")
        )
        self.assertEqual(len(ana_mail), 1)
        self.assertEqual(ana_mail.subject, "Your tables for Spring Forum")
        self.assertIn("Ana Bloom", ana_mail.body_html)
        self.assertIn("Spring Forum", ana_mail.body_html)
        # Ana sits at table 1 in both rounds, seat 1 each time.
        self.assertEqual(
            ana_mail.body_html.count(
                '<span class="o_event_table_mail_number">'
            ),
            2,
        )
        self.assertIn(
            '<span class="o_event_table_mail_number">1</span>',
            ana_mail.body_html,
        )
        self.assertIn(
            '<span class="o_event_table_mail_seat">1</span>',
            ana_mail.body_html,
        )
        bo_mail = mails.filtered(
            lambda mail: "bo.carver@example.com" in (mail.email_to or "")
        )
        self.assertIn(
            '<span class="o_event_table_mail_number">2</span>',
            bo_mail.body_html,
        )

    def test_chatter_note_counts_sent_and_skipped(self):
        self.plan.action_send_assignment_emails()
        note = self.plan.message_ids[0].body
        self.assertIn("Tables sent by email.", note)
        self.assertIn("Sent: 4", note)
        self.assertIn("Without email address: 1", note)

    def test_send_refused_before_anyone_is_seated(self):
        self.plan.assignment_ids.with_context(
            event_table_assignment_write=True
        ).unlink()
        with self.assertRaises(UserError) as error:
            self.plan.action_send_assignment_emails()
        self.assertIn("Nobody is seated yet.", str(error.exception))

    def test_sender_falls_back_to_the_company_contact(self):
        organizer = self.env["res.partner"].create({"name": "Forum Desk"})
        self.event.organizer_id = organizer
        company_partner = self.event.company_id.partner_id
        company_partner.email = "tables@example.com"
        template = self.env.ref(
            "erplibre_event_table.mail_template_participant_tables"
        )
        rendered = template._render_field("email_from", self.ana.ids)
        self.assertEqual(
            rendered[self.ana.id], company_partner.email_formatted
        )
        self.assertIn("tables@example.com", rendered[self.ana.id])

    def test_participant_without_a_seat_gets_no_table_promise(self):
        # Added after the choice, so the plan seats them nowhere: this is
        # the case the card already handles with "No table assigned yet.",
        # and unlike Eve Frost this participant HAS an email, so the send
        # actually reaches the body instead of being skipped.
        fay = self.env["event.table.participant"].create(
            {
                "plan_id": self.plan.id,
                "name": "Fay Gable",
                "email": "fay.gable@example.com",
                "company_label": "Marlow",
            }
        )
        mails = self._sent_mails(self.plan.action_send_assignment_emails)
        fay_mail = mails.filtered(
            lambda mail: fay.email in (mail.email_to or "")
        )
        self.assertEqual(len(fay_mail), 1)
        self.assertIn("No table assigned yet.", fay_mail.body_html)
        self.assertNotIn(
            '<span class="o_event_table_mail_number">', fay_mail.body_html
        )
