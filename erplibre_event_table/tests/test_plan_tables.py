# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.addons.erplibre_event_table.models.event_table import (
    CONNECTOR_WIDTH,
    GRID_GAP_X,
    LIST_FULL_NAME_ONE_LINE_CHARS,
    LIST_WIDTH,
    LIST_WIDTH_FULL,
    SEAT_RING,
    TABLE_SIZE,
    list_label_length,
    list_line_pitch,
    list_reserved_height,
    list_width,
    visual_table_size,
)
from odoo.exceptions import UserError
from odoo.tests import Form
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import EventTableCommon


class TestPlanTables(EventTableCommon):
    def _assert_no_overlap(self, tables, plan=None):
        """Two tables overlap if their boxes intersect on both axes.
        `plan` measures each box against visual_table_size's own
        footprint when `plan.visual_tables` is on, instead of the
        table's own stored width/height — visual mode never draws that
        stored size either (surfaceStyle, floor_plan.js), and
        _grid_positions does not space rows and columns for it. Without
        `plan` (or with a non-visual one), the boxes stay the stored
        size, since that IS what a non-visual floor draws. Passing the
        stored size for a visual-mode plan would check real tables
        against a box nothing on screen ever matches — exactly the gap
        that let the pre-4478a47 overlap pass this same check silently.
        """

        def box(table):
            if plan is not None and plan.visual_tables:
                width, height = visual_table_size(
                    table.shape,
                    table.seat_count,
                    plan.assign_seats,
                    plan.show_company,
                )
            else:
                width, height = table.width, table.height
            # A table is not only its surface: it also carries the seat
            # ring, the connector, and the name list beside it. Two
            # tables whose SURFACES clear each other can still have one
            # sitting squarely on the other's names, which is what this
            # check could not see while it measured the surface alone.
            # The list is measured at seat_count CHIPS, the most it can
            # ever hold and the same bound _grid_positions reserves
            # against, each one list_line_pitch tall — two lines' worth
            # where the plan shows companies, three where it also shows
            # whole names to the chips whose label needs the room —
            # chip by chip, the very sum the reservations use — so that
            # this check reads the same list height the browser draws.
            # The option also widens the column, so the width term reads
            # it too: a check left on LIST_WIDTH would clear two lists
            # that in fact overlap by 60 px.
            show_company = plan is not None and plan.show_company
            show_full_names = plan is not None and plan.show_full_names
            wrapping = (
                plan._wrapping_label_counts().get(table.number, 0)
                if plan is not None
                else 0
            )
            width += SEAT_RING + CONNECTOR_WIDTH + list_width(show_full_names)
            height = max(
                height + SEAT_RING,
                list_reserved_height(table.seat_count, wrapping, show_company),
            )
            return table.position_h, table.position_v, width, height

        boxes = [box(t) for t in tables]
        for index, (x1, y1, w1, h1) in enumerate(boxes):
            for x2, y2, w2, h2 in boxes[index + 1 :]:
                self.assertTrue(
                    x1 + w1 <= x2
                    or x2 + w2 <= x1
                    or y1 + h1 <= y2
                    or y2 + h2 <= y1,
                    "two tables overlap on the floor plan",
                )

    def test_a_new_plan_is_a_draft_with_the_default_options(self):
        plan = self._make_plan()
        self.assertEqual(plan.state, "draft")
        self.assertEqual(plan.round_count, 3)
        self.assertEqual(plan.combination_count, 3)
        self.assertTrue(plan.separate_companies)
        self.assertTrue(plan.avoid_repeat_neighbors)
        self.assertFalse(plan.avoid_repeat_table)
        self.assertFalse(plan.assign_seats)
        self.assertFalse(plan.show_seat_number)
        self.assertFalse(plan.show_company)
        self.assertFalse(plan.visual_tables)
        self.assertEqual(plan.company_id, self.event.company_id)

    def test_the_event_counts_and_lists_its_plans(self):
        self.assertEqual(self.event.table_plan_count, 0)
        plan = self._make_plan()
        self.assertEqual(self.event.table_plan_count, 1)
        self.assertEqual(self.event.table_plan_ids, plan)

    def test_the_event_opens_a_single_plan_on_its_form(self):
        plan = self._make_plan()
        action = self.event.action_view_table_plans()
        self.assertEqual(action["res_model"], "event.table.plan")
        self.assertEqual(action["res_id"], plan.id)
        self.assertEqual(action["view_mode"], "form")

    def test_the_event_lists_its_plans_when_there_are_several(self):
        self._make_plan()
        self._make_plan()
        action = self.event.action_view_table_plans()
        self.assertEqual(action["view_mode"], "list,form")
        self.assertEqual(action["domain"], [("event_id", "=", self.event.id)])
        self.assertEqual(action["context"]["default_event_id"], self.event.id)

    def test_the_event_creates_a_plan_when_it_has_none(self):
        self.assertFalse(self.event.use_rotating_tables)
        action = self.event.action_view_table_plans()
        self.assertEqual(action["view_mode"], "form")
        plan = self.env["event.table.plan"].browse(action["res_id"])
        self.assertEqual(plan.event_id, self.event)
        # Otherwise the button that just created the plan would vanish
        # from under it, since it is hidden behind this very option.
        self.assertTrue(self.event.use_rotating_tables)
        self.assertEqual(self.event.table_plan_count, 1)

    def test_the_table_buttons_stay_visible_with_a_plan_and_the_option_off(
        self,
    ):
        self._make_plan()
        self.event.use_rotating_tables = False
        arch = self.env["event.event"].get_view(False, "form")["arch"]
        self.assertEqual(
            arch.count(
                'invisible="not use_rotating_tables and not'
                ' table_plan_count"'
            ),
            2,
        )

    def test_the_wizard_numbers_the_first_tables_from_one(self):
        plan = self._make_plan()
        tables = self._configure_tables(plan, 4, 8)
        self.assertEqual(tables.mapped("number"), [1, 2, 3, 4])
        self.assertEqual(set(tables.mapped("seat_count")), {8})
        self.assertEqual(plan.table_count, 4)
        self.assertEqual(plan.seat_count, 32)

    def test_the_wizard_lays_the_first_tables_out_on_a_grid(self):
        plan = self._make_plan()
        tables = self._configure_tables(plan, 4, 8)
        # columns = ceil(sqrt(4)) = 2,
        # step_x = 140 + 26 + 34 + 220 + 180 = 600,
        # step_y = max(140 + 26, 8 * 29) + 40 = 272 — the list of eight
        # names, not the table, is what a row has to clear here.
        self.assertEqual(
            [(t.position_h, t.position_v) for t in tables],
            [(40.0, 40.0), (640.0, 40.0), (40.0, 312.0), (640.0, 312.0)],
        )
        self._assert_no_overlap(tables, plan)

    def test_visual_tables_lays_out_a_tighter_grid(self):
        """In visual mode the grid spaces columns on the table's own
        drawn footprint (visual_table_size), not on the fixed
        TABLE_SIZE: an 8-seat round table draws at 100 + 6 * 10 = 160 px
        across, the party floor's own figure, so the step is WIDER than
        the legacy 140 px one this grid used to assume. The ROW step is
        the same as the non-visual one, both being driven by the same
        list of eight names rather than by either table's own height."""
        plan = self._make_plan(visual_tables=True)
        tables = self._configure_tables(plan, 3, 8)
        # columns = ceil(sqrt(3)) = 2,
        # step_x = 160 + 26 + 34 + 220 + 180 = 620,
        # step_y = max(160 + 26, 8 * 29) + 40 = 272.
        self.assertEqual(
            [(t.position_h, t.position_v) for t in tables],
            [
                (40.0, 40.0),
                (660.0, 40.0),
                (40.0, 312.0),
            ],
        )
        self._assert_no_overlap(tables, plan)

    def test_showing_companies_reserves_a_taller_row_than_hiding_them(self):
        """show_company adds a company line under every name, so a chip
        of the list stands two lines instead of one. The row step has to
        grow with it: it is the only term of the grid that clears a
        list, and a step spaced on the one-line pitch leaves each row of
        names drawn across the next row's — which is exactly what an
        eight-seat plan showed, the lists being far taller than their
        tables. Read as a comparison between the two states, plus the
        height a list of two-line chips actually takes, rather than
        against a single figure: what must hold is that the reserve
        FOLLOWS the option, not that it lands on one number.
        """
        plain = self._make_plan()
        self._configure_tables(plain, 4, 8)
        with_company = self._make_plan(show_company=True)
        self._configure_tables(with_company, 4, 8)

        def row_step(plan):
            positions = plan._grid_positions(0, 4)
            # columns = ceil(sqrt(4)) = 2, so index 2 opens the second row.
            return positions[2][1] - positions[0][1]

        plain_step = row_step(plain)
        company_step = row_step(with_company)
        self.assertGreater(company_step, plain_step)
        # The eight chips themselves, at the pitch each state gives
        # them: the step has to clear them in both, and it is the
        # two-line list that the one-line reserve fell short of.
        self.assertGreaterEqual(company_step, 8 * list_line_pitch(True, False))
        self.assertGreater(8 * list_line_pitch(True, False), plain_step)
        self._assert_no_overlap(with_company.table_ids, with_company)

    def _name_of_length(self, length):
        """An invented name of exactly `length` characters.

        Built from a repeated token rather than picked from a roster:
        what matters here is the LENGTH the threshold reads, and a name
        taken from real data would fix a person in a test forever for
        no gain.
        """
        token = "Amaryl Brentwold "
        return (token * (length // len(token) + 1))[:length]

    def _label_of_length(self, plan, length):
        """A name whose drawn LABEL is `length` characters.

        The label a list draws is "{number}. {name}", and the counting
        numbers it at the table's own seat count, so the name is
        shorter than the label by those digits and their separator.
        Going through the label keeps a test aimed at the threshold
        instead of at the arithmetic around it.
        """
        seats = max(plan.table_ids.mapped("seat_count") or [8])
        return self._name_of_length(length - len(str(seats)) - 2)

    def _seat_labels(self, plan, lengths):
        """Adds one participant per label length, then generates a
        seating and chooses it.

        The counting reads PLACEMENTS, never the participant list: a
        plan with names and no seating draws no chip and reserves one
        line per seat. So a test about the reservation has to seat
        people the way the screen does, which is what choosing a
        generated combination is.
        """
        for length in lengths:
            self._add_participant(plan, self._label_of_length(plan, length))
        plan.action_generate_combinations()
        plan.combination_ids.filtered(lambda c: c.rank == 1).action_choose()

    def _row_step(self, plan, count=4):
        positions = plan._grid_positions(0, count)
        # columns = ceil(sqrt(4)) = 2, so index 2 opens the second row.
        return positions[2][1] - positions[0][1]

    def _column_step(self, plan, count=4):
        positions = plan._grid_positions(0, count)
        return positions[1][0] - positions[0][0]

    def test_a_table_reserves_per_chip_so_one_long_name_costs_one_line(self):
        """The whole point of counting chips rather than multiplying a
        pitch. A table of eight where a SINGLE label wraps stands 21 px
        taller; a reservation that multiplied the tallest chip's pitch
        by the list would charge all eight for that one name, 168 px of
        room nothing is ever drawn in.
        """
        plan = self._make_plan(show_full_names=True, round_count=1)
        self._configure_tables(plan, 4, 8)
        over = LIST_FULL_NAME_ONE_LINE_CHARS + 1
        under = LIST_FULL_NAME_ONE_LINE_CHARS
        self._seat_labels(plan, [over] + [under] * 31)

        counts = plan._wrapping_label_counts()
        # One long name, one round: exactly one table carries it, and
        # it carries it once.
        self.assertEqual(sorted(counts.values()), [1])
        # 7 chips of one line and 1 of two, not 8 of two.
        self.assertEqual(
            self._row_step(plan),
            list_reserved_height(8, 1, False) + 40.0,
        )
        self.assertEqual(
            self._row_step(plan),
            7 * list_line_pitch(False, False)
            + list_line_pitch(False, True)
            + 40.0,
        )
        # Strictly between the two uniform states, and nearer the
        # short one: that gap is what this change buys.
        every = list_reserved_height(8, 8, False) + 40.0
        none = list_reserved_height(8, 0, False) + 40.0
        self.assertLess(none, self._row_step(plan))
        self.assertLess(self._row_step(plan), every)
        self.assertEqual(every - self._row_step(plan), 7 * 21.0)
        plan.action_rearrange_tables()
        self._assert_no_overlap(plan.table_ids, plan)

    def test_a_plan_whose_names_all_fit_reserves_one_line_everywhere(self):
        """show_full_names WIDENS the column whatever the names are,
        but a plan none of whose labels reach a second line reserves
        none: the row step is the one-line step, exactly as if the
        option were off.
        """
        whole = self._make_plan(show_full_names=True, round_count=1)
        self._configure_tables(whole, 4, 8)
        self._seat_labels(whole, [LIST_FULL_NAME_ONE_LINE_CHARS] * 32)
        clipped = self._make_plan(round_count=1)
        self._configure_tables(clipped, 4, 8)
        self._seat_labels(clipped, [LIST_FULL_NAME_ONE_LINE_CHARS] * 32)

        self.assertEqual(whole._wrapping_label_counts(), {})
        self.assertEqual(self._row_step(whole), self._row_step(clipped))
        self.assertEqual(
            self._row_step(whole), list_reserved_height(8, 0, False) + 40.0
        )
        # The COLUMN still follows the option and nothing else.
        self.assertEqual(
            self._column_step(whole) - self._column_step(clipped),
            LIST_WIDTH_FULL - LIST_WIDTH,
        )

    def test_every_name_long_reserves_a_second_line_on_every_chip(self):
        """The other end, where the old all-or-nothing reservation and
        this one agree: a table all of whose labels wrap stands at the
        two-line pitch throughout.
        """
        plan = self._make_plan(show_full_names=True, round_count=1)
        self._configure_tables(plan, 4, 8)
        self._seat_labels(plan, [LIST_FULL_NAME_ONE_LINE_CHARS + 1] * 32)

        self.assertEqual(
            sorted(plan._wrapping_label_counts().values()), [8] * 4
        )
        self.assertEqual(
            self._row_step(plan), list_reserved_height(8, 8, False) + 40.0
        )
        plan.action_rearrange_tables()
        self._assert_no_overlap(plan.table_ids, plan)

    def test_the_count_a_table_keeps_is_its_WORST_round(self):
        """People rotate and a floor holds every round, so a table
        reserves for the round that seats the most long names, not for
        the first or the last. A count taken from one round leaves the
        others drawing over the row below.
        """
        plan = self._make_plan(show_full_names=True, round_count=3)
        self._configure_tables(plan, 4, 8)
        over = LIST_FULL_NAME_ONE_LINE_CHARS + 1
        self._seat_labels(
            plan, [over] * 8 + [LIST_FULL_NAME_ONE_LINE_CHARS] * 24
        )
        counts = plan._wrapping_label_counts()

        placements = plan._assignment_placements()
        names = {
            participant.id: participant.name
            for participant in plan._included_participants()
        }
        seats_by_number = {
            table.number: table.seat_count for table in plan.table_ids
        }
        per_round = {}
        for placement in placements:
            label = list_label_length(
                seats_by_number[placement.table], names[placement.person]
            )
            if label > LIST_FULL_NAME_ONE_LINE_CHARS:
                key = (placement.table, placement.round)
                per_round[key] = per_round.get(key, 0) + 1
        for (number, _round), count in per_round.items():
            self.assertGreaterEqual(counts.get(number, 0), count)
        for number, count in counts.items():
            self.assertEqual(
                count,
                max(
                    value
                    for (table, _round), value in per_round.items()
                    if table == number
                ),
            )

    def test_the_count_measures_the_label_a_list_prints(self):
        """The threshold is compared to "{number}. {name}", not to the
        bare name: floor_plan.xml numbers every line of a list. A count
        measuring the name alone lets a label three characters longer
        than it believes slip under the threshold, on every line.
        """
        plan = self._make_plan(show_full_names=True, round_count=1)
        self._configure_tables(plan, 1, 2)
        # Two seats, so a list numbers its lines with one digit: the
        # label is the name plus ". " plus that digit.
        fits = self._name_of_length(LIST_FULL_NAME_ONE_LINE_CHARS - 3)
        self.assertEqual(
            list_label_length(2, fits), LIST_FULL_NAME_ONE_LINE_CHARS
        )
        self._add_participant(plan, fits)
        self._add_participant(plan, fits + "x")
        plan.action_generate_combinations()
        plan.combination_ids.filtered(lambda c: c.rank == 1).action_choose()

        # One of the two is one character past the threshold.
        self.assertEqual(sorted(plan._wrapping_label_counts().values()), [1])

    def test_a_plan_that_hides_whole_names_counts_nothing(self):
        """A clipped chip is one line whatever it carries, so no name
        may add a pixel to a plan that never turned the option on.
        """
        plain = self._make_plan(round_count=1)
        self._configure_tables(plain, 4, 8)
        self._seat_labels(plain, [200] * 32)
        self.assertEqual(plain._wrapping_label_counts(), {})
        self.assertEqual(
            self._row_step(plain), list_reserved_height(8, 0, False) + 40.0
        )

    def test_a_plan_with_nobody_seated_reserves_no_second_line(self):
        """Tables are configured before anyone is seated, and a count
        with no placement to read must answer that nothing wraps rather
        than reserve for chips it cannot describe. The room follows the
        names at the next rearrangement, as it does after any other
        change to what a list draws.
        """
        plan = self._make_plan(show_full_names=True, round_count=1)
        self._configure_tables(plan, 4, 8)
        for _ in range(32):
            self._add_participant(
                plan,
                self._label_of_length(plan, LIST_FULL_NAME_ONE_LINE_CHARS + 1),
            )
        self.assertEqual(plan._wrapping_label_counts(), {})
        self.assertEqual(
            self._row_step(plan), list_reserved_height(8, 0, False) + 40.0
        )

    def test_the_overlap_check_measures_the_widened_column_too(self):
        """The spacing a plan WITHOUT the option gets puts one table
        squarely on its neighbour's widened list. The check has to fail
        on it, or it is not measuring the wider column at all and would
        pass the very overlap the reservation exists to prevent."""
        plan = self._make_plan(show_full_names=True, round_count=1)
        tables = self._configure_tables(plan, 2, 8)
        self._seat_labels(plan, [LIST_FULL_NAME_ONE_LINE_CHARS + 1] * 16)
        first, second = tables[0], tables[1]
        second.position_v = first.position_v

        second.position_h = first.position_h + (
            TABLE_SIZE + SEAT_RING + CONNECTOR_WIDTH + LIST_WIDTH
        )
        with self.assertRaises(AssertionError):
            self._assert_no_overlap(tables, plan)

        second.position_h = first.position_h + (
            TABLE_SIZE + SEAT_RING + CONNECTOR_WIDTH + LIST_WIDTH_FULL
        )
        self._assert_no_overlap(tables, plan)

    def test_the_overlap_check_measures_the_name_list_and_not_only_the_surface(
        self,
    ):
        """The spacing this grid used BEFORE the list existed — the
        table plus GRID_GAP_X, nothing for the names — puts one table
        squarely on its neighbour's list. The check has to fail on it,
        or it is not measuring the list at all and would pass the very
        overlap it exists to catch."""
        plan = self._make_plan()
        tables = self._configure_tables(plan, 2, 8)
        first, second = tables[0], tables[1]
        second.position_v = first.position_v

        second.position_h = first.position_h + TABLE_SIZE + GRID_GAP_X
        with self.assertRaises(AssertionError):
            self._assert_no_overlap(tables, plan)

        second.position_h = first.position_h + (
            TABLE_SIZE + SEAT_RING + CONNECTOR_WIDTH + LIST_WIDTH + GRID_GAP_X
        )
        self._assert_no_overlap(tables, plan)

    def test_toggling_visual_tables_moves_no_existing_table(self):
        """The tighter grid only ever applies where positions are
        actually computed (the configurator, Rearrange Tables): turning
        the option on or off by itself must never move a table already
        placed, by the configurator or by hand."""
        plan = self._make_plan()
        tables = self._configure_tables(plan, 3, 8)
        before = {t.id: (t.position_h, t.position_v) for t in tables}

        plan.visual_tables = True
        after_on = {t.id: (t.position_h, t.position_v) for t in plan.table_ids}
        self.assertEqual(before, after_on)

        plan.visual_tables = False
        after_off = {
            t.id: (t.position_h, t.position_v) for t in plan.table_ids
        }
        self.assertEqual(before, after_off)

    def test_assigning_seats_no_longer_widens_the_grid_margin(self):
        """A fresh grid used to give its leftmost column and its top row
        a wider margin, so that a name anchored beside a chair on those
        sides did not land at a negative, unreachable coordinate. Names
        no longer sit around a table at all — each list stands to the
        table's right — so that band would now reserve 80 px for an
        empty rim, and the ordinary margin applies in every
        combination."""
        plan = self._make_plan(visual_tables=True, assign_seats=True)
        tables = self._configure_tables(plan, 3, 8)
        self.assertEqual(
            [(t.position_h, t.position_v) for t in tables],
            [
                (40.0, 40.0),
                (660.0, 40.0),
                (40.0, 312.0),
            ],
        )
        self._assert_no_overlap(tables, plan)

    def test_visual_tables_without_assigned_seats_keeps_the_ordinary_margin(
        self,
    ):
        """The ordinary margin applies whether or not seats are
        assigned: this is the same figure as the assigned case above,
        asserted from the other side of the flag."""
        plan = self._make_plan(visual_tables=True, assign_seats=False)
        table = self._configure_tables(plan, 1, 8)
        self.assertEqual(table.position_h, 40.0)

    def test_toggling_visual_tables_and_assigned_seats_moves_no_table(self):
        """Same guarantee as the visual-only case, for the two options
        together: turning on visual_tables with assign_seats must not
        retroactively nudge a table already placed."""
        plan = self._make_plan()
        tables = self._configure_tables(plan, 3, 8)
        before = {t.id: (t.position_h, t.position_v) for t in tables}

        plan.write({"visual_tables": True, "assign_seats": True})

        after = {t.id: (t.position_h, t.position_v) for t in plan.table_ids}
        self.assertEqual(before, after)

    def test_the_wizard_appends_after_the_highest_number(self):
        plan = self._make_plan()
        self._configure_tables(plan, 4, 8)
        tables = self._configure_tables(plan, 2, 6, mode="append")
        self.assertEqual(tables.mapped("number"), [1, 2, 3, 4, 5, 6])
        self.assertEqual(
            tables.filtered(lambda t: t.number > 4).mapped("seat_count"),
            [6, 6],
        )
        self.assertEqual(plan.seat_count, 44)

    def test_appending_tables_does_not_superimpose_them_on_existing_ones(
        self,
    ):
        plan = self._make_plan()
        self._configure_tables(plan, 4, 8)
        self._configure_tables(plan, 2, 8, mode="append")
        self._assert_no_overlap(plan.table_ids, plan)

    def test_replacing_deletes_the_previous_tables(self):
        plan = self._make_plan()
        first = self._configure_tables(plan, 4, 8)
        first_ids = first.ids
        tables = self._configure_tables(plan, 2, 10)
        self.assertEqual(tables.mapped("number"), [1, 2])
        self.assertFalse(
            self.env["event.table"].search([("id", "in", first_ids)])
        )

    def test_rearranging_puts_every_table_back_on_one_grid(self):
        plan = self._make_plan()
        self._configure_tables(plan, 4, 8)
        self._configure_tables(plan, 2, 8, mode="append")
        plan.action_rearrange_tables()
        tables = plan.table_ids.sorted("number")
        # columns = ceil(sqrt(6)) = 3, step_x = 600, step_y = 272.
        self.assertEqual(
            [(t.position_h, t.position_v) for t in tables],
            [
                (40.0, 40.0),
                (640.0, 40.0),
                (1240.0, 40.0),
                (40.0, 312.0),
                (640.0, 312.0),
                (1240.0, 312.0),
            ],
        )
        self._assert_no_overlap(tables, plan)

    def test_rearranging_works_on_a_plan_already_chosen(self):
        """A chosen plan is exactly the one that cannot be configured
        afresh — the wizard replaces tables, and replacing them on a plan
        with a combination is refused. Rearranging writes nothing but
        position_h and position_v, which
        event.table.write lets through in every state (event_table.py):
        the button is therefore offered outside draft too, and a plan
        laid out under an earlier spacing has this as its only remedy.
        """
        plan = self._make_plan(round_count=1, combination_count=1)
        self._configure_tables(plan, 2, 2)
        for name in ("Ada Bell", "Bob Carr", "Cora Dane", "Dan Evers"):
            self._add_participant(plan, name)
        plan.action_generate_combinations()
        plan.combination_ids.filtered(lambda c: c.rank == 1).action_choose()
        self.assertEqual(plan.state, "chosen")

        # Positions an older spacing could have left behind: close enough
        # that each table's name list would run across its neighbour.
        plan.table_ids.write({"position_h": 0.0, "position_v": 0.0})

        plan.action_rearrange_tables()

        tables = plan.table_ids.sorted("number")
        self.assertEqual(
            [(t.position_h, t.position_v) for t in tables],
            list(plan._grid_positions(0, len(tables))),
        )
        self.assertEqual(plan.state, "chosen")
        self._assert_no_overlap(tables, plan)

    def test_the_wizard_defaults_to_appending_on_a_plan_with_tables(self):
        plan = self._make_plan()
        self._configure_tables(plan, 2, 8)
        wizard = self.env["event.table.configure.wizard"].create(
            {"plan_id": plan.id}
        )
        self.assertEqual(wizard.mode, "append")
        self.assertEqual(wizard.existing_table_count, 2)

    def test_the_wizard_defaults_to_replacing_on_an_empty_plan(self):
        wizard = self.env["event.table.configure.wizard"].create(
            {"plan_id": self._make_plan().id}
        )
        self.assertEqual(wizard.mode, "replace")

    def test_the_existing_table_warning_matches_the_count(self):
        plan = self._make_plan()
        wizard = self.env["event.table.configure.wizard"].create(
            {"plan_id": plan.id}
        )
        self.assertFalse(wizard.existing_table_warning)

        self._configure_tables(plan, 1, 8)
        wizard = self.env["event.table.configure.wizard"].create(
            {"plan_id": plan.id}
        )
        self.assertEqual(
            wizard.existing_table_warning,
            "The existing table will be deleted.",
        )

        self._configure_tables(plan, 2, 8)
        wizard = self.env["event.table.configure.wizard"].create(
            {"plan_id": plan.id}
        )
        self.assertEqual(
            wizard.existing_table_warning,
            "The 2 existing tables will be deleted.",
        )

    def test_the_wizard_refuses_a_plan_without_a_table(self):
        wizard = self.env["event.table.configure.wizard"].create(
            {"plan_id": self._make_plan().id, "table_count": 0}
        )
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_the_wizard_refuses_a_table_with_a_single_seat(self):
        wizard = self.env["event.table.configure.wizard"].create(
            {
                "plan_id": self._make_plan().id,
                "table_count": 2,
                "seats_per_table": 1,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_a_locked_plan_refuses_a_new_round_count(self):
        plan = self._make_plan()
        plan.action_lock()
        with self.assertRaises(UserError):
            plan.round_count = 5

    def test_a_locked_plan_refuses_a_new_option(self):
        plan = self._make_plan()
        plan.action_lock()
        with self.assertRaises(UserError):
            plan.assign_seats = True

    def test_a_locked_plan_refuses_a_new_table(self):
        plan = self._make_plan()
        plan.action_lock()
        with self.assertRaises(UserError):
            self.env["event.table"].create(
                {"plan_id": plan.id, "number": 1, "seat_count": 8}
            )

    def test_a_locked_plan_refuses_a_seat_change(self):
        plan = self._make_plan()
        table = self._configure_tables(plan, 1, 8)
        plan.action_lock()
        with self.assertRaises(UserError):
            table.seat_count = 10

    def test_a_locked_plan_refuses_to_lose_a_table(self):
        plan = self._make_plan()
        table = self._configure_tables(plan, 1, 8)
        plan.action_lock()
        with self.assertRaises(UserError):
            table.unlink()

    def test_a_locked_plan_refuses_even_a_display_option(self):
        """Locking is literal: the three display options change nothing
        but the drawing, and a locked plan refuses them too."""
        plan = self._make_plan()
        plan.action_lock()
        with self.assertRaises(UserError):
            plan.show_seat_number = True

    def test_a_proposed_plan_still_accepts_a_display_option(self):
        """Only locking forbids a write, so a proposed plan takes these
        as it takes any other change."""
        plan = self._make_plan()
        plan.state = "proposed"
        plan.write(
            {
                "show_seat_number": True,
                "show_company": True,
                "visual_tables": True,
            }
        )
        self.assertTrue(plan.show_seat_number)
        self.assertTrue(plan.show_company)
        self.assertTrue(plan.visual_tables)

    def test_a_proposed_plan_still_accepts_a_layout_change(self):
        plan = self._make_plan()
        table = self._configure_tables(plan, 1, 8)
        plan.state = "proposed"
        table.write(
            {"position_h": 500.0, "position_v": 250.0, "shape": "square"}
        )
        self.assertEqual(table.position_h, 500.0)
        self.assertEqual(table.shape, "square")

    def test_the_configure_wizard_refuses_a_locked_plan(self):
        plan = self._make_plan()
        self._configure_tables(plan, 2, 8)
        wizard = self.env["event.table.configure.wizard"].create(
            {"plan_id": plan.id, "table_count": 1, "seats_per_table": 8}
        )
        plan.action_lock()
        with self.assertRaises(UserError):
            wizard.action_apply()

    @mute_logger("odoo.sql_db")
    def test_two_tables_of_a_plan_never_share_a_number(self):
        plan = self._make_plan()
        self._configure_tables(plan, 1, 8)
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["event.table"].create(
                {"plan_id": plan.id, "number": 1, "seat_count": 8}
            )

    @mute_logger("odoo.sql_db")
    def test_a_table_number_starts_at_one(self):
        plan = self._make_plan()
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["event.table"].create(
                {"plan_id": plan.id, "number": 0, "seat_count": 8}
            )

    @mute_logger("odoo.sql_db")
    def test_a_table_has_at_least_two_seats(self):
        plan = self._make_plan()
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["event.table"].create(
                {"plan_id": plan.id, "number": 1, "seat_count": 1}
            )

    @mute_logger("odoo.sql_db")
    def test_a_table_is_at_least_forty_pixels_wide(self):
        plan = self._make_plan()
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["event.table"].create(
                {
                    "plan_id": plan.id,
                    "number": 1,
                    "seat_count": 8,
                    "width": 10.0,
                }
            )

    @mute_logger("odoo.sql_db")
    def test_a_plan_has_between_one_and_fifty_rounds(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self._make_plan(round_count=0)

    @mute_logger("odoo.sql_db")
    def test_a_plan_proposes_between_one_and_ten_combinations(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self._make_plan(combination_count=11)

    def test_a_table_shows_its_number_as_its_name(self):
        plan = self._make_plan()
        table = self._configure_tables(plan, 3, 8)[2]
        self.assertEqual(table.display_name, "Table 3")

    def test_an_empty_plan_says_every_seat_is_taken(self):
        plan = self._make_plan()
        self.assertEqual(plan.seat_balance, 0)
        self.assertEqual(
            plan.capacity_message,
            "Participants: 0. Seats: 0. Every seat is taken.",
        )

    def test_a_plan_with_tables_and_no_one_counts_its_free_seats(self):
        plan = self._make_plan()
        self._configure_tables(plan, 2, 8)
        self.assertEqual(plan.participant_count, 0)
        self.assertEqual(plan.seat_balance, 16)
        self.assertEqual(
            plan.capacity_message, "Participants: 0. Seats: 16. Free: 16."
        )

    def test_the_search_budget_defaults_to_ten_seconds(self):
        self.assertEqual(self._make_plan()._search_time_budget(), 10.0)

    def test_the_search_budget_never_exceeds_forty_five_seconds(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "600"
        )
        self.assertEqual(self._make_plan()._search_time_budget(), 45.0)

    def test_the_search_budget_is_at_least_one_second(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "erplibre_event_table.search_time_budget", "0"
        )
        self.assertEqual(self._make_plan()._search_time_budget(), 1.0)

    def test_locking_a_plan_leaves_it_readable(self):
        plan = self._make_plan()
        plan._lock()
        self.assertEqual(plan.state, "draft")

    def test_adding_a_table_survives_unsaved_participants(self):
        """Regression: capacity used to crash before the plan was saved.

        During an onchange the o2m lines hold NewId keys, which Python
        cannot compare, so sorting participant_ids on "id" raised
        TypeError as soon as a SECOND unsaved line existed: participant_ids
        is itself one of _compute_capacity's @api.depends, and one NewId
        alone gives sorted() nothing to compare. Form drives the onchange
        the way the web client does, unlike every other test in this file,
        which only ever calls create().
        """
        plan_form = Form(self.env["event.table.plan"])
        plan_form.event_id = self.event
        with plan_form.participant_ids.new() as participant:
            participant.name = "Ana"
        with plan_form.participant_ids.new() as participant:
            participant.name = "Beto"
        with plan_form.table_ids.new() as table:
            table.number = 1
            table.seat_count = 8
        plan = plan_form.save()
        self.assertEqual(plan.participant_count, 2)
        self.assertEqual(plan.table_count, 1)

    def test_the_configure_wizard_opens_on_its_plan(self):
        plan = self._make_plan()
        action = plan.action_open_configure_wizard()
        self.assertEqual(action["res_model"], "event.table.configure.wizard")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"]["default_plan_id"], plan.id)
