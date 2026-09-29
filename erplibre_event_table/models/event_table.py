# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import math

from odoo import _, api, fields, models

# Grid layout constants (event.table.plan._grid_positions): a table's
# footprint, the gap the grid reserves around and between tables, and the
# space each seat adds to a table's name panel.
TABLE_SIZE = 140.0
GRID_MARGIN = 40.0
GRID_GAP_X = 180.0
NAME_LINE_HEIGHT = 22.0
SEAT_RING = 26.0
# The name list drawn beside each table. geometry.js carries all six
# under the same names, and test_visual_table_size_matches_js.py pins
# them against that file's own text, so a change to one side without
# the other fails a test rather than drifting quietly. Each measures a
# DIFFERENT thing and is chosen separately, rather than rolled into one
# rounded number: a list that overruns its reservation then says which
# of them was underestimated. Every height is MEASURED in a browser,
# never derived from NAME_LINE_HEIGHT, which is the line height of text
# drawn INSIDE the table surface and would fall short by about a fifth
# on every line. LIST_LINE_HEIGHT is the pitch of a chip carrying the
# NAME ALONE (28.2 px between two stacked chips, taken up to the next
# whole pixel). LIST_COMPANY_LINE_HEIGHT is what the company line adds
# when show_company puts one under the name: its own 18 px box, and
# nothing else, a chip's padding and margins being paid once per chip
# rather than once per line. LIST_FULL_NAME_LINE_HEIGHT is what a
# SECOND NAME line adds when show_full_names lets the name wrap instead
# of being clipped, measured the same way and additive for the same
# reason. LIST_WIDTH_FULL is the column that same option widens to, at
# which one line holds 41 characters against 31 at LIST_WIDTH.
# LIST_FULL_NAME_ONE_LINE_CHARS is how many characters that wider line
# holds at the WIDEST glyph of the alphabet rather than at an average
# one — 18, against those same 41 — and it is the threshold that
# decides whether the second line is reserved at all. Counting at the
# average would reserve one line for a label of wide glyphs the browser
# draws on two; counting at the widest only ever reserves a line too
# many, which costs room and hides nothing. Read the widths through
# list_width and the heights through list_line_pitch, never singly.
LIST_WIDTH = 220.0
LIST_WIDTH_FULL = 280.0
LIST_LINE_HEIGHT = 29.0
LIST_COMPANY_LINE_HEIGHT = 18.0
LIST_FULL_NAME_LINE_HEIGHT = 21.0
LIST_FULL_NAME_ONE_LINE_CHARS = 18
CONNECTOR_WIDTH = 34.0


def list_width(show_full_names):
    """Width the name list beside a table takes, the figure every
    horizontal reservation of that list is built from.

    Python twin of listWidth (geometry.js). The width depends on
    show_full_names because that option widens the column so a whole
    name fits: a reader left on LIST_WIDTH alone spaces its columns for
    a 220 px list while the browser draws a 280 px one, which runs one
    column of names over the next column's tables.
    """
    return LIST_WIDTH_FULL if show_full_names else LIST_WIDTH


def list_label_length(list_number, name):
    """Character length of the label a list draws on one chip, which is
    "{number}. {name}".

    Python twin of listLabelLength (geometry.js). The number and its
    ". " are counted because floor_plan.xml numbers every line of a
    list, so they are part of what has to fit. The company is not: it
    is a block line of its own, with its own term in the pitch.
    """
    return len(str(list_number)) + 2 + len(name or "")


def list_wraps_to_two_lines(show_full_names, label_length):
    """Whether the chips of a list take TWO name lines rather than one.

    Python twin of listWrapsToTwoLines (geometry.js). Both conditions
    are needed: without show_full_names a chip is clipped to one line
    whatever it carries, and with it only a label longer than one line
    holds wraps. The question is asked of ONE CHIP'S label: a list
    reserves chip by chip (list_reserved_height), so one long name
    costs its own second line and nothing more.
    """
    return bool(show_full_names) and (
        label_length > LIST_FULL_NAME_ONE_LINE_CHARS
    )


def list_line_pitch(show_company, wraps_to_two_lines):
    """Vertical pitch one chip of a name list takes, the figure every
    reservation of that list multiplies by a chip count.

    Python twin of listLinePitch (geometry.js). The pitch depends on
    the company option and on whether the names wrap, because each adds
    a line of its own to a chip: the company its own block under the
    name, a wrapped name a second name line. They compose, so the two
    terms add rather than one replacing the other. A reader left on
    LIST_LINE_HEIGHT alone reserves a one-line chip's room for a two-
    or three-line chip, which draws one row of names across the next
    row's.

    The second argument is list_wraps_to_two_lines' answer, never
    show_full_names itself: the option only ALLOWS a second line, and a
    plan whose names all fit on one would otherwise reserve 21 px per
    chip that nothing draws.

    This is ONE CHIP'S pitch. Nothing multiplies it by a list's length:
    list_reserved_height below is what every reservation goes through.
    """
    return (
        LIST_LINE_HEIGHT
        + (LIST_COMPANY_LINE_HEIGHT if show_company else 0.0)
        + (LIST_FULL_NAME_LINE_HEIGHT if wraps_to_two_lines else 0.0)
    )


def list_reserved_height(chip_count, wrapping_chip_count, show_company):
    """Height a name list of chip_count chips takes, of which
    wrapping_chip_count wrap onto a second name line.

    Python twin of listReservedHeight (geometry.js). CHIP BY CHIP,
    never one pitch times a count: a list is a stack of chips that each
    stand as tall as their own label needs, and multiplying one pitch
    by a whole list charges every chip for the tallest of them — 168 px
    on a table of eight where a single name wraps, for a 21 px need.

    _grid_positions reserves a table's CAPACITY, chip_count being its
    seat_count, since a list has to still fit once the table fills; an
    EMPTY SEAT carries no name, so it cannot wrap and counts as one
    line. The count is clamped into the list rather than trusted.
    """
    wrapping = min(max(wrapping_chip_count, 0), chip_count)
    return wrapping * list_line_pitch(show_company, True) + (
        chip_count - wrapping
    ) * list_line_pitch(show_company, False)


# visualTableSize's own inputs, mirrored (geometry.js): a chair's own
# radius, how far beyond it seatPositions pushes the ring chairs sit
# on, the gap kept between two adjacent chairs, a rectangular table's
# own width:height ratio, and the width reserved for one line of
# content inside the surface. _grid_positions needs the exact same
# table footprint the browser will actually draw, to space rows and
# columns without overlap — see visual_table_size below, and keep both
# copies identical: this is that same arithmetic a third time now, in a
# third place, which is exactly how such a group drifts apart later.
SEAT_RADIUS = 11.0
CHAIR_RING_GAP = 4.0
SEAT_GAP = 6.0
RECTANGLE_ASPECT_RATIO = 1.5
NAME_CHIP_WIDTH = 90.0
# The floor that grows with the party (geometry.js carries both under
# the same names, pinned by test_visual_table_size_matches_js.py against
# that file's own text): PARTY_BASE_SPAN carries a two-seat table, and
# every chair beyond those two adds PARTY_SPAN_PER_SEAT to the span. It
# is the only term of visual_table_size that grows with the seat count
# at every count — the rim term stays under the fixed content term up to
# 15 chairs.
PARTY_BASE_SPAN = 100.0
PARTY_SPAN_PER_SEAT = 10.0

# How much more ring a RECTANGULAR table's rim term asks for than a
# straight edge alone needs (CORNER_CHORD_PENALTY, geometry.js — see its
# own, fuller comment). Two chairs one walk-step apart on the same edge
# stand exactly that step apart; two straddling a corner stand
# hypot(a, b) apart, where a + b is the same step, shortest at
# step / sqrt(2) when the corner falls halfway between them. Paying
# sqrt(2) up front keeps SEAT_GAP's promise wherever the corners fall,
# in closed form, so the size stays monotone in the seat count by
# construction.
_CORNER_CHORD_PENALTY = math.sqrt(2)


def visual_table_size(shape, seat_count, assign_seats, show_company):
    """Python twin of visualTableSize (geometry.js) — see its own,
    fuller comment for the reasoning behind each term. Needed here
    because _grid_positions must space rows and columns for the SAME
    footprint the browser draws in visual mode, not the table's own
    stored width/height, which visual mode never reads for rendering
    either.
    """
    seat_span = 2 * SEAT_RADIUS + SEAT_GAP
    # Chairs sit this far outside the table's own edge (seatPositions,
    # geometry.js): the rim term below sizes the RING they actually
    # occupy, then shrinks back to the table's own edge by this offset.
    ring_gap = SEAT_RADIUS + CHAIR_RING_GAP
    chair_floor = 2 * seat_span
    # Grows with the party, and is the only term that does: read as a
    # WIDTH on a rectangular table, whose height follows from the same
    # ratio the rim term keeps, and as a DIAMETER on a round one.
    party_span = PARTY_BASE_SPAN + PARTY_SPAN_PER_SEAT * max(seat_count - 2, 0)
    # Reserves the table's own HEADER and nothing more: the table number
    # and the occupancy count, the two lines .o_event_table_surface draws
    # unconditionally (floor_plan.xml), on a surface carrying no overflow
    # rule to clip what does not fit. It never grows with the seat count,
    # which is what party_span is for. assign_seats and show_company
    # select nothing here any more; they stay in the signature because
    # this footprint is computed in two languages against one generated
    # fixture that pins both as columns, and because _grid_positions
    # (event_table_plan.py) passes them.
    content_lines = 2
    content_height = content_lines * NAME_LINE_HEIGHT
    content_width = NAME_CHIP_WIDTH

    if shape == "square":
        rim_requirement = seat_count * seat_span * _CORNER_CHORD_PENALTY
        rim_height = (rim_requirement - 8 * ring_gap) / (
            2 * (RECTANGLE_ASPECT_RATIO + 1)
        )
        rim_width = RECTANGLE_ASPECT_RATIO * rim_height
        content_area = content_lines * NAME_LINE_HEIGHT * NAME_CHIP_WIDTH
        content_area_height = math.sqrt(content_area / RECTANGLE_ASPECT_RATIO)
        content_area_width = RECTANGLE_ASPECT_RATIO * content_area_height
        return (
            max(chair_floor, rim_width, content_area_width, party_span),
            max(
                chair_floor,
                rim_height,
                content_area_height,
                party_span / RECTANGLE_ASPECT_RATIO,
            ),
        )
    rim_diameter = (seat_count * seat_span) / math.pi - 2 * ring_gap
    content_diameter = math.hypot(content_width, content_height)
    diameter = max(chair_floor, rim_diameter, content_diameter, party_span)
    return diameter, diameter


class EventTable(models.Model):
    _name = "event.table"
    _description = "Event Table"
    _order = "plan_id, number"

    plan_id = fields.Many2one(
        "event.table.plan", required=True, ondelete="cascade", index=True
    )
    event_id = fields.Many2one(
        related="plan_id.event_id", store=True, index=True
    )
    number = fields.Integer(string="Table Number", required=True)
    seat_count = fields.Integer(string="Seats", required=True, default=8)
    shape = fields.Selection(
        [("round", "Circular"), ("square", "Rectangular")],
        default="round",
        required=True,
    )
    position_h = fields.Float(default=0.0)
    position_v = fields.Float(default=0.0)
    width = fields.Float(default=TABLE_SIZE)
    height = fields.Float(default=TABLE_SIZE)
    assignment_ids = fields.One2many(
        "event.table.assignment", "table_id", string="Assignments"
    )

    _sql_constraints = [
        (
            "number_unique",
            "UNIQUE(plan_id, number)",
            "Each table number is used once per plan.",
        ),
        ("number_positive", "CHECK(number >= 1)", "Table numbers start at 1."),
        (
            "seat_count_min",
            "CHECK(seat_count >= 2)",
            "A table has at least 2 seats.",
        ),
        (
            "size_min",
            "CHECK(width >= 40 AND height >= 40)",
            "A table is at least 40 pixels wide and high.",
        ),
    ]

    @api.depends("number")
    def _compute_display_name(self):
        for table in self:
            table.display_name = _("Table %(number)s", number=table.number)

    @api.model_create_multi
    def create(self, vals_list):
        plans = self.env["event.table.plan"].browse(
            [vals["plan_id"] for vals in vals_list if vals.get("plan_id")]
        )
        plans._check_not_locked()
        return super().create(vals_list)

    def write(self, vals):
        # Position and shape used to be let through in every state, the
        # rest refused outside draft. One rule replaces both: a locked
        # plan accepts nothing, an unlocked one accepts everything.
        self.plan_id._check_not_locked()
        return super().write(vals)

    def unlink(self):
        self.plan_id._check_not_locked()
        return super().unlink()

    def _report_rounds(self):
        """Occupancy of this table round by round, for the table sheet."""
        self.ensure_one()
        rounds = []
        for round_number in range(1, self.plan_id.round_count + 1):
            lines = self.assignment_ids.filtered(
                lambda line, number=round_number: line.round_number == number
            )
            rounds.append(
                {
                    "round": round_number,
                    "rows": [
                        {
                            "seat_number": line.seat_number,
                            "name": line.participant_id.name,
                            "company": line.participant_id.company_label or "",
                        }
                        for line in lines.sorted(
                            key=lambda line: (
                                line.seat_number,
                                line.participant_id.name,
                            )
                        )
                    ],
                }
            )
        return rounds
