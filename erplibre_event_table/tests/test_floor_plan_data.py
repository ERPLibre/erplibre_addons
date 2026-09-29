# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.tests.common import TransactionCase, new_test_user


class TestFloorPlanData(TransactionCase):
    """Cover the payload the floor plan component reads.

    The fixture is built so that the only conflict in the whole plan is a
    single colleague pair, at table 1 of round 1. Every pair of people meets
    exactly once, and returning to a table does not count because
    avoid_repeat_table is off. Every asserted conflict number is therefore
    derivable from the seating alone.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.event = cls.env["event.event"].create(
            {
                "name": "Networking Night",
                "date_begin": "2026-04-01 17:00:00",
                "date_end": "2026-04-01 21:00:00",
                "use_rotating_tables": True,
            }
        )
        cls.plan = cls.env["event.table.plan"].create(
            {
                "name": "Rotating Tables",
                "event_id": cls.event.id,
                "round_count": 2,
                "separate_companies": True,
                "avoid_repeat_neighbors": True,
                "avoid_repeat_table": False,
                "assign_seats": False,
            }
        )
        cls.table_1, cls.table_2 = cls.env["event.table"].create(
            [
                {
                    "plan_id": cls.plan.id,
                    "number": 1,
                    "seat_count": 2,
                    "shape": "round",
                    "position_h": 40.0,
                    "position_v": 40.0,
                },
                {
                    "plan_id": cls.plan.id,
                    "number": 2,
                    "seat_count": 2,
                    "shape": "square",
                    "position_h": 360.0,
                    "position_v": 40.0,
                },
            ]
        )
        cls.ada, cls.bob, cls.cora, cls.dan = cls.env[
            "event.table.participant"
        ].create(
            [
                {
                    "plan_id": cls.plan.id,
                    "name": "Ada Bell",
                    "company_label": "Northwind Tools",
                },
                {
                    "plan_id": cls.plan.id,
                    "name": "Bob Carr",
                    "company_label": "Northwind Tools",
                },
                {"plan_id": cls.plan.id, "name": "Cora Dane"},
                {"plan_id": cls.plan.id, "name": "Dan Evers"},
            ]
        )
        # Round 1: table 1 holds the two colleagues, table 2 the two others.
        # Round 2: everyone changes neighbour, so no pair ever meets twice.
        cls.combination = cls.env["event.table.combination"].create(
            {
                "plan_id": cls.plan.id,
                "rank": 1,
                "placement_data": [
                    [1, cls.ada.id, 1, 0],
                    [1, cls.bob.id, 1, 0],
                    [1, cls.cora.id, 2, 0],
                    [1, cls.dan.id, 2, 0],
                    [2, cls.ada.id, 1, 0],
                    [2, cls.cora.id, 1, 0],
                    [2, cls.bob.id, 2, 0],
                    [2, cls.dan.id, 2, 0],
                ],
            }
        )
        # A second combination, never chosen: it exists only to be previewed.
        cls.preview = cls.env["event.table.combination"].create(
            {
                "plan_id": cls.plan.id,
                "rank": 2,
                "placement_data": [
                    [1, cls.ada.id, 1, 0],
                    [1, cls.cora.id, 1, 0],
                    [1, cls.bob.id, 2, 0],
                    [1, cls.dan.id, 2, 0],
                    [2, cls.ada.id, 1, 0],
                    [2, cls.dan.id, 1, 0],
                    [2, cls.bob.id, 2, 0],
                    [2, cls.cora.id, 2, 0],
                ],
            }
        )
        cls.plan.write({"state": "proposed"})
        cls.combination.action_choose()

    def test_payload_describes_the_chosen_plan(self):
        data = self.plan.get_floor_plan_data()

        self.assertEqual(data["plan"]["id"], self.plan.id)
        self.assertEqual(data["plan"]["state"], "chosen")
        self.assertEqual(data["plan"]["round_count"], 2)
        self.assertFalse(data["plan"]["assign_seats"])
        self.assertFalse(data["plan"]["show_seat_number"])
        self.assertFalse(data["plan"]["show_company"])
        self.assertFalse(data["plan"]["visual_tables"])
        self.assertEqual(data["plan"]["participant_count"], 4)
        self.assertEqual(data["plan"]["seat_count"], 4)
        self.assertEqual(data["plan"]["unseated_count"], 0)

        self.assertEqual(data["combination"]["id"], self.combination.id)
        self.assertEqual(data["combination"]["rank"], 1)
        self.assertTrue(data["combination"]["is_chosen"])
        self.assertFalse(data["combination"]["is_adjusted"])

        self.assertEqual([t["number"] for t in data["tables"]], [1, 2])
        self.assertEqual(
            [t["id"] for t in data["tables"]],
            [self.table_1.id, self.table_2.id],
        )
        self.assertEqual(data["tables"][0]["shape"], "round")
        self.assertEqual(data["tables"][0]["seat_count"], 2)
        self.assertEqual(data["tables"][0]["x"], 40.0)
        self.assertEqual(data["tables"][0]["y"], 40.0)
        self.assertEqual(data["tables"][1]["shape"], "square")
        self.assertEqual(data["tables"][1]["x"], 360.0)

        self.assertEqual(
            [p["name"] for p in data["participants"]],
            ["Ada Bell", "Bob Carr", "Cora Dane", "Dan Evers"],
        )
        self.assertEqual(data["participants"][0]["company"], "Northwind Tools")
        self.assertEqual(data["participants"][2]["company"], "")

        self.assertEqual([r["round"] for r in data["rounds"]], [1, 2])
        seats = {
            (s["participant_id"], s["table_id"])
            for s in data["rounds"][0]["seats"]
        }
        self.assertEqual(
            seats,
            {
                (self.ada.id, self.table_1.id),
                (self.bob.id, self.table_1.id),
                (self.cora.id, self.table_2.id),
                (self.dan.id, self.table_2.id),
            },
        )
        self.assertTrue(
            all(s["seat"] == 0 for s in data["rounds"][0]["seats"])
        )
        self.assertEqual(data["rounds"][0]["unseated"], [])
        self.assertEqual(data["rounds"][1]["unseated"], [])

    def test_indicators_come_from_the_chosen_combination(self):
        data = self.plan.get_floor_plan_data()
        indicators = data["indicators"]

        self.assertEqual(
            indicators["company_pairs"], self.combination.company_pair_count
        )
        self.assertEqual(
            indicators["extra_meetings"], self.combination.extra_meeting_count
        )
        self.assertEqual(
            indicators["table_returns"], self.combination.table_return_count
        )
        self.assertEqual(
            indicators["lower_bound"], self.combination.lower_bound
        )
        self.assertFalse(indicators["is_adjusted"])

    def test_conflicts_are_listed_table_by_table(self):
        data = self.plan.get_floor_plan_data()
        round_1, round_2 = data["rounds"]

        # Only table 1 of round 1 seats two colleagues together.
        self.assertEqual(len(round_1["conflicts"]), 1)
        conflict = round_1["conflicts"][0]
        self.assertEqual(conflict["table_id"], self.table_1.id)
        self.assertEqual(conflict["company_pairs"], 1)
        self.assertEqual(conflict["repeated_pairs"], 0)
        self.assertEqual(conflict["table_returns"], 0)

        # Round 2 mixes everyone: nothing to report.
        self.assertEqual(round_2["conflicts"], [])

    def test_repeated_pairs_are_read_on_the_displayed_round(self):
        """A conflict is read on the round shown, not on the whole plan.

        Ed and Fay are colleagues seated together in both rounds. Round 1
        is their first meeting: repeated_pairs is 0 there, even though the
        pair does repeat later. Round 2 is where the repeat shows, because
        by then they already share round 1. Both rounds report the same
        company_pairs, since a company overlap carries no such history.
        """
        plan = self.env["event.table.plan"].create(
            {
                "name": "Repeat Check",
                "event_id": self.event.id,
                "round_count": 2,
                "separate_companies": True,
                "avoid_repeat_neighbors": True,
                "avoid_repeat_table": False,
                "assign_seats": False,
            }
        )
        table = self.env["event.table"].create(
            {"plan_id": plan.id, "number": 1, "seat_count": 2}
        )
        ed, fay = self.env["event.table.participant"].create(
            [
                {
                    "plan_id": plan.id,
                    "name": "Ed Farr",
                    "company_label": "Acme",
                },
                {
                    "plan_id": plan.id,
                    "name": "Fay Grant",
                    "company_label": "Acme",
                },
            ]
        )
        combination = self.env["event.table.combination"].create(
            {
                "plan_id": plan.id,
                "rank": 1,
                "placement_data": [
                    [1, ed.id, 1, 0],
                    [1, fay.id, 1, 0],
                    [2, ed.id, 1, 0],
                    [2, fay.id, 1, 0],
                ],
            }
        )
        plan.write({"state": "proposed"})
        combination.action_choose()

        data = plan.get_floor_plan_data()
        round_1, round_2 = data["rounds"]
        self.assertEqual(
            round_1["conflicts"],
            [
                {
                    "table_id": table.id,
                    "company_pairs": 1,
                    "repeated_pairs": 0,
                    "table_returns": 0,
                }
            ],
        )
        self.assertEqual(
            round_2["conflicts"],
            [
                {
                    "table_id": table.id,
                    "company_pairs": 1,
                    "repeated_pairs": 1,
                    "table_returns": 0,
                }
            ],
        )

    def test_a_table_with_no_conflict_yet_is_absent_from_the_round(self):
        """A table the library flags for a global repeat can still be
        missing from a round's conflicts entirely: nothing else conflicts
        at that table, and the repeat has not happened yet at round 1.
        """
        plan = self.env["event.table.plan"].create(
            {
                "name": "Absence Check",
                "event_id": self.event.id,
                "round_count": 2,
                "separate_companies": True,
                "avoid_repeat_neighbors": True,
                "avoid_repeat_table": False,
                "assign_seats": False,
            }
        )
        table = self.env["event.table"].create(
            {"plan_id": plan.id, "number": 1, "seat_count": 2}
        )
        gus, hana = self.env["event.table.participant"].create(
            [
                {"plan_id": plan.id, "name": "Gus Ito"},
                {"plan_id": plan.id, "name": "Hana Ivy"},
            ]
        )
        combination = self.env["event.table.combination"].create(
            {
                "plan_id": plan.id,
                "rank": 1,
                "placement_data": [
                    [1, gus.id, 1, 0],
                    [1, hana.id, 1, 0],
                    [2, gus.id, 1, 0],
                    [2, hana.id, 1, 0],
                ],
            }
        )
        plan.write({"state": "proposed"})
        combination.action_choose()

        data = plan.get_floor_plan_data()
        round_1, round_2 = data["rounds"]

        self.assertNotIn(
            table.id, [c["table_id"] for c in round_1["conflicts"]]
        )
        self.assertEqual(
            round_2["conflicts"],
            [
                {
                    "table_id": table.id,
                    "company_pairs": 0,
                    "repeated_pairs": 1,
                    "table_returns": 0,
                }
            ],
        )

    def test_a_table_return_is_absent_until_it_happens(self):
        """avoid_repeat_table derives table_returns separately from
        repeated pairs: a table absent from round 1's conflicts, since no
        one has sat anywhere yet, can appear later once one person comes
        back to it, even while every neighbour pairing stays fresh.
        """
        plan = self.env["event.table.plan"].create(
            {
                "name": "Return Check",
                "event_id": self.event.id,
                "round_count": 2,
                "separate_companies": False,
                "avoid_repeat_neighbors": False,
                "avoid_repeat_table": True,
                "assign_seats": False,
            }
        )
        table_1, table_2, table_3 = self.env["event.table"].create(
            [
                {"plan_id": plan.id, "number": number, "seat_count": 2}
                for number in (1, 2, 3)
            ]
        )
        ida, jon, kira, leo, mina, noel = self.env[
            "event.table.participant"
        ].create(
            [
                {"plan_id": plan.id, "name": name}
                for name in (
                    "Ida Lund",
                    "Jon Marsh",
                    "Kira Nash",
                    "Leo Osei",
                    "Mina Park",
                    "Noel Quinn",
                )
            ]
        )
        combination = self.env["event.table.combination"].create(
            {
                "plan_id": plan.id,
                "rank": 1,
                "placement_data": [
                    [1, ida.id, 1, 0],
                    [1, jon.id, 1, 0],
                    [1, kira.id, 2, 0],
                    [1, leo.id, 2, 0],
                    [1, mina.id, 3, 0],
                    [1, noel.id, 3, 0],
                    # Round 2: Ida is the only one back at her round 1
                    # table; everybody else sits somewhere new.
                    [2, ida.id, 1, 0],
                    [2, kira.id, 1, 0],
                    [2, mina.id, 2, 0],
                    [2, noel.id, 2, 0],
                    [2, leo.id, 3, 0],
                    [2, jon.id, 3, 0],
                ],
            }
        )
        plan.write({"state": "proposed"})
        combination.action_choose()

        data = plan.get_floor_plan_data()
        round_1, round_2 = data["rounds"]

        self.assertEqual(round_1["conflicts"], [])
        self.assertEqual(
            round_2["conflicts"],
            [
                {
                    "table_id": table_1.id,
                    "company_pairs": 0,
                    "repeated_pairs": 0,
                    "table_returns": 1,
                }
            ],
        )

    def test_preview_of_another_combination_reads_its_json(self):
        data = self.preview.get_floor_plan_data()

        self.assertEqual(data["combination"]["id"], self.preview.id)
        self.assertEqual(data["combination"]["rank"], 2)
        self.assertFalse(data["combination"]["is_chosen"])
        seats = {
            (s["participant_id"], s["table_id"])
            for s in data["rounds"][0]["seats"]
        }
        self.assertEqual(
            seats,
            {
                (self.ada.id, self.table_1.id),
                (self.cora.id, self.table_1.id),
                (self.bob.id, self.table_2.id),
                (self.dan.id, self.table_2.id),
            },
        )

        # The assignment lines are untouched: the plan still seats Bob with
        # Ada in round 1. One record is never shown two different ways.
        chosen = self.plan.get_floor_plan_data()
        chosen_seats = {
            (s["participant_id"], s["table_id"])
            for s in chosen["rounds"][0]["seats"]
        }
        self.assertIn((self.bob.id, self.table_1.id), chosen_seats)

    def test_the_display_options_reach_the_payload(self):
        """Appearance options, unlike assign_seats, need no state change."""
        self.plan.write(
            {
                "show_seat_number": True,
                "show_company": True,
                "visual_tables": True,
            }
        )

        data = self.plan.get_floor_plan_data()

        self.assertTrue(data["plan"]["show_seat_number"])
        self.assertTrue(data["plan"]["show_company"])
        self.assertTrue(data["plan"]["visual_tables"])

    def test_an_excluded_participant_leaves_the_payload(self):
        self.bob.excluded = True

        data = self.plan.get_floor_plan_data()

        self.assertNotIn(self.bob.id, [p["id"] for p in data["participants"]])
        self.assertNotIn(
            self.bob.id,
            [s["participant_id"] for s in data["rounds"][0]["seats"]],
        )
        self.assertNotIn(self.bob.id, data["rounds"][0]["unseated"])

    def test_the_registration_desk_may_look_but_not_touch(self):
        desk = new_test_user(
            self.env,
            login="desk_tables",
            groups="event.group_event_registration_desk",
        )

        data = self.plan.with_user(desk).get_floor_plan_data()

        self.assertFalse(data["plan"]["can_edit_layout"])
        self.assertFalse(data["plan"]["can_move_participants"])

    def test_an_event_user_may_edit_the_plan_but_not_a_preview(self):
        manager = new_test_user(
            self.env, login="events_tables", groups="event.group_event_user"
        )
        plan = self.plan.with_user(manager)

        data = plan.get_floor_plan_data()
        self.assertTrue(data["plan"]["can_edit_layout"])
        self.assertTrue(data["plan"]["can_move_participants"])

        # Asking for a combination by name makes the payload a preview, even
        # when that combination is the chosen one.
        preview = plan.get_floor_plan_data(combination_id=self.combination.id)
        self.assertFalse(preview["plan"]["can_move_participants"])
        self.assertTrue(preview["plan"]["can_edit_layout"])

    def test_a_draft_plan_draws_its_tables_and_its_empty_rounds(self):
        """A draft carries no combination, so nobody is seated — but the
        rounds are described all the same, each one empty. The screen reads
        its people out of the CURRENT round: reporting no rounds at all
        left it unable to name anyone, and the tray announced nobody was
        waiting while everybody was.
        """
        draft = self.env["event.table.plan"].create(
            {"name": "Second Room", "event_id": self.event.id}
        )
        self.env["event.table"].create(
            {"plan_id": draft.id, "number": 1, "seat_count": 4}
        )

        data = draft.get_floor_plan_data()

        self.assertEqual(data["plan"]["state"], "draft")
        self.assertIsNone(data["combination"])
        self.assertIsNone(data["indicators"])
        self.assertEqual(len(data["tables"]), 1)
        self.assertEqual(
            [r["round"] for r in data["rounds"]],
            list(range(1, draft.round_count + 1)),
        )
        self.assertTrue(all(not r["seats"] for r in data["rounds"]))
        # A draft plan takes hand placement: only a locked plan, and a
        # preview of a combination, refuse it.
        self.assertTrue(data["plan"]["can_move_participants"])

    def test_a_plan_without_a_combination_lists_everyone_as_waiting(self):
        """The count and the names have to agree, in every state. Both are
        read from the same record: unseated_count feeds the capacity line
        and each round's `unseated` feeds the tray, so a plan that had
        generated nothing said "nobody waiting" twice over while holding
        four participants and no seating at all.
        """
        draft = self.env["event.table.plan"].create(
            {"name": "Third Room", "event_id": self.event.id, "round_count": 2}
        )
        self.env["event.table"].create(
            {"plan_id": draft.id, "number": 1, "seat_count": 4}
        )
        waiting = self.env["event.table.participant"].create(
            [
                {"plan_id": draft.id, "name": name}
                for name in ("Ines Aubry", "Jonas Berger", "Kira Nowak")
            ]
        )

        data = draft.get_floor_plan_data()

        self.assertEqual(data["plan"]["participant_count"], 3)
        self.assertEqual(data["plan"]["unseated_count"], 3)
        self.assertEqual(len(data["rounds"]), 2)
        for round_data in data["rounds"]:
            self.assertEqual(round_data["unseated"], sorted(waiting.ids))
            self.assertEqual(round_data["seats"], [])
