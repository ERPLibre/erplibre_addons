/** @odoo-module **/
// Copyright 2026 TechnoLibre - Mathieu Benoit
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

// Pure geometry for the floor plan: no Odoo import, no DOM, no state. Every
// function here takes plain numbers or plain objects and returns plain
// values, which is what lets the floor plan be tested without a browser.

export const SEAT_RADIUS = 11;
export const SEAT_RING = 26;
export const GRID_SIZE = 10;
export const MIN_TABLE_SIZE = 40;
export const NAME_LINE_HEIGHT = 22;
// How far beyond a chair's own radius seatPositions pushes the ring
// chairs actually sit on, outside the table's edge (its `left`, `top`,
// `rx`, `ry`, below, are all built from SEAT_RADIUS + this). Named
// separately from SEAT_RING (26, an unrelated reservation for names
// below a non-visual table) so visualTableSize's own rim term can size
// against the SAME ring seatPositions places chairs on, instead of the
// table's own edge — sizing against the wrong one is exactly what let
// the two functions describe two different circles for one table.
export const CHAIR_RING_GAP = 4;
// Target clear space kept between two adjacent chairs' own pads, the
// promise visualTableSize's packing math keeps for every pair of
// consecutive chairs seatPositions places — including two straddling a
// rectangular table's corner, which CORNER_CHORD_PENALTY is what pays
// for. Chairs never overlap as a result, verified against the real
// chair placements — geometry.test.js places them with seatPositions
// itself, on the size visualTableSize returns, for every seat count
// from 2 to 200 — not stated as a limit to accept.
export const SEAT_GAP = 6;
// visualTableSize's own shape for a rectangular table, width:height.
// Editorial: a banquet table reads as a rectangle, not a square, and
// this is simply a fixed ratio rather than anything derived — a real
// design pass could replace it, this only has to be sane and stated.
export const RECTANGLE_ASPECT_RATIO = 1.5;
// Width visualTableSize reserves for one line of content inside the
// surface — the table number, or the occupancy line. Editorial: not
// measured from real text, wide enough for a short two-word name at the
// backend's default font size. A wide occupancy string ("12 / 12") can
// still overrun it, an accepted limit rather than something this
// constant engineers around.
export const NAME_CHIP_WIDTH = 90;
// The floor that grows with the party: PARTY_BASE_SPAN carries a
// two-seat table, and every chair beyond those two adds
// PARTY_SPAN_PER_SEAT to the table's span. This is the term that makes
// the seat count visible at all — the rim term stays under the content
// term up to 15 chairs, so without it a table of eight and a table of
// two both draw at 100.18 px. Editorial, like RECTANGLE_ASPECT_RATIO:
// nothing here measures a real place setting, the pair only has to be
// sane and stated. It costs a floor plan little: a round table of
// eight draws 160 px across against 100 at two, which widens a
// two-table plan of eight by about 6 %, since the name list beside
// each table and the gap between columns dominate a floor's own width
// either way. event_table.py carries both under the same names, and
// test_visual_table_size_matches_js.py pins them against this file's
// own text.
export const PARTY_BASE_SPAN = 100;
export const PARTY_SPAN_PER_SEAT = 10;

// The three constants the NAME LIST beside each table is built from.
// Each measures a DIFFERENT thing and is chosen separately, rather than
// rolled into one rounded number: a list that overruns its reservation
// then says which of the three was underestimated. event_table.py
// carries all three under the same names, and
// test_visual_table_size_matches_js.py pins that pair against this
// file's own text.

// Width of the list column itself. Taken from the reserve tray, which
// already stacks these exact chips in `flex: 0 0 220px`
// (floor_plan.scss) and holds them without wrapping for an ordinary
// two-word name.
export const LIST_WIDTH = 220;
// Width the column takes instead when `show_full_names` asks for whole
// names: the chip then WRAPS rather than clipping, and the wider column
// is what keeps that second line from being the ordinary case. MEASURED
// in a browser on the rendered font, not derived from LIST_WIDTH: a
// chip's own text box holds 41 characters on ONE line at this width,
// against 31 at 220, so a given name and a composed surname — 40
// characters — never reaches the second line at all. Two lines hold 79
// characters here; past that the name is clipped again, which
// LIST_FULL_NAME_LINE_HEIGHT's own comment states as the limit it is.
// Read both through `listWidth`, never singly.
export const LIST_WIDTH_FULL = 280;
// Vertical pitch from one chip to the next when the chip carries the
// NAME ALONE, MEASURED in a browser on the rendered font rather than
// derived: a chip's own box is 24.2 px (a 21 px line box plus 2 x 1.6
// px of padding), and two stacked chips sit 28.2 px apart once their
// 4 px margins collapse — taken up here to the next whole pixel.
// NAME_LINE_HEIGHT (22) is NOT this number: it is the line height of
// text drawn INSIDE the table surface, and reserving a list with it
// would fall short by about a fifth on every line. The name itself
// never wraps, whatever its length: the list clips it to one line with
// an ellipsis (floor_plan.scss). It is the COMPANY, a block-level line
// of its own, that adds a second line to a chip — hence the second
// constant below, and `listLinePitch`, which is what every reservation
// reads instead of this one.
export const LIST_LINE_HEIGHT = 29;
// What the COMPANY line adds to a chip's pitch when show_company puts
// it under the name (`.o_event_table_person_company` is `display:
// block`, floor_plan.scss, so it starts a line of its own even though
// the chip forbids wrapping). MEASURED the same way LIST_LINE_HEIGHT
// was, on the same rendered font: the company line's own box is 18 px
// (a 12 px font on an 18 px line box), and it is ALL the second line
// adds — a chip's padding and its margins are paid once per chip, not
// once per line. A two-line chip therefore stands 42.2 px against
// 24.2, and two stacked ones sit 46.2 px apart against 28.2, which
// 29 + 18 = 47 covers.
//
// A MULTIPLIER on LIST_LINE_HEIGHT would not: doubling it reserves 58
// px per chip, 11 px more than a chip ever takes, because it pays the
// padding, the margins and the full 21 px name line a second time for
// a line that is none of those things. On a plan of eight-seat tables
// that is 88 px of dead space per row, and it would still be a guess
// rather than a measurement.
export const LIST_COMPANY_LINE_HEIGHT = 18;
// What a SECOND NAME line adds to a chip's pitch when show_full_names
// lets the name wrap instead of being clipped to one line. MEASURED the
// same way LIST_COMPANY_LINE_HEIGHT was, on the same rendered font: a
// name line's own box is 21 px, and it is ALL the second line adds — a
// chip's padding, its border and its margins are paid once per chip,
// not once per line. A chip stands 47 px on two name lines against 26
// on one, and two stacked ones sit 51 px apart against 30.
//
// The wrap stops at TWO lines, which is the LIMIT this constant buys
// and not a full promise: a name longer than two lines hold — 79
// characters at LIST_WIDTH_FULL — is still clipped, now with the
// ellipsis the clamp draws on the second line. Reserving a third line
// would pay 21 px on every chip of every plan to carry a name no
// roster holds, where the two the option reserves already carry twice
// what the clipped column showed.
export const LIST_FULL_NAME_LINE_HEIGHT = 21;
// How many characters of a chip's label fit on ONE line at
// LIST_WIDTH_FULL, counted at the WIDEST glyph of the alphabet rather
// than at an average one. It is the threshold `listWrapsToTwoLines`
// compares a label's length to, so that a list reserves its second
// line only where a name actually needs one.
//
// MEASURED in a browser on the rendered font: the chip offers 265 px of
// text per line at that width, and the widest glyph an ASCII or
// Latin-1 label can carry is `@` at 14.217 px, which fits 18 times —
// verified by layout, 18 staying on one line and 19 taking two, not by
// the division alone. The runners-up bracket it closely: `Œ` and `Æ`
// fit 19 times, `W` 20, `M` 22.
//
// A COUNT AT THE AVERAGE GLYPH WOULD BE WRONG. The same 265 px carry 41
// characters of an ordinary mixed-case name, and a threshold set there
// would reserve one line for a label of 41 wide glyphs that the browser
// then draws on two — the list overrunning its reservation silently,
// one row of names across the next row's. The safe direction is the
// other one: a label of 19 narrow characters reserves two lines and
// draws one, which costs 21 px of empty room and hides nothing.
//
// The LIMIT this states: the alphabet measured is ASCII and Latin-1,
// the two languages this module ships in. Glyphs outside it were spot
// checked and come in narrower — a CJK ideograph at 13 px, an em dash
// at 14 — but the check is a sample, not a proof, and a name made of
// something wider than `@` would still overrun a one-line
// reservation.
export const LIST_FULL_NAME_ONE_LINE_CHARS = 18;
// Horizontal space the connector occupies between the table's seat ring
// and the first character of its list: a 20 px straight trait leaving
// the table, then a 14 px bracket embracing the list. Reserved BEYOND
// SEAT_RING, which stays its own term in every formula here, so the
// connector is drawn clear of the chairs instead of across them.
export const CONNECTOR_WIDTH = 34;

/**
 * The width the name list beside a table takes.
 *
 * The width DEPENDS ON THE PLAN'S OWN `show_full_names`, because that
 * option widens the column so a whole name fits: the places that
 * reserve horizontal room for a list therefore all call this rather
 * than reaching for LIST_WIDTH directly — `floorSize` below,
 * `namesStyle` (floor_plan.js), and `_grid_positions`
 * (event_table_plan.py, through the Python twin `list_width`). A
 * reader left on the bare constant draws a 280 px list inside a 220 px
 * reservation, which is one column of names running over the next
 * column's tables.
 */
export function listWidth(showFullNames) {
    return showFullNames ? LIST_WIDTH_FULL : LIST_WIDTH;
}

/**
 * The character length of the label a list draws on one chip, which is
 * `"{number}. {name}"` — floor_plan.xml numbers every line of a list,
 * so the number and its `". "` are part of what has to fit and are
 * counted here. The COMPANY is not: it is a block line of its own,
 * with LIST_COMPANY_LINE_HEIGHT as its own term in the pitch.
 *
 * Written as a function, and used by both languages' callers, so that
 * the thing MEASURED against the threshold is the thing the browser
 * actually lays out. A caller counting the bare name instead lets a
 * label three characters longer than it thinks slip past the
 * threshold, on every line of every list.
 */
export function listLabelLength(listNumber, name) {
    return String(listNumber).length + 2 + (name || "").length;
}

/**
 * Whether the chips of a list take TWO name lines rather than one.
 *
 * Two conditions, and both are needed. Without `show_full_names` a chip
 * is clipped to one line whatever it carries (floor_plan.scss), so no
 * length can make it wrap. With the option on, only a label longer than
 * one line holds does — LIST_FULL_NAME_ONE_LINE_CHARS, counted at the
 * widest glyph so that the answer is never optimistic.
 *
 * The question is asked of ONE CHIP'S label, not of a list's longest:
 * a list reserves chip by chip (`listReservedHeight`), so one long
 * name costs its own second line and nothing more. `listHeight`
 * (floor_plan.js) asks it of each person it draws, at the very number
 * the template prints beside the name; `_wrapping_label_counts`
 * (event_table_plan.py, through the Python twin
 * `list_wraps_to_two_lines`) asks it of each seated participant, at
 * the largest number that participant's list can print, so that a
 * count it hands to a reservation is never short.
 */
export function listWrapsToTwoLines(showFullNames, labelLength) {
    return Boolean(showFullNames) && labelLength > LIST_FULL_NAME_ONE_LINE_CHARS;
}

/**
 * The vertical pitch one chip of a name list takes, which is what
 * every reservation of that list multiplies by a line count.
 *
 * The pitch DEPENDS ON THE PLAN'S OWN `show_company` and on whether its
 * names WRAP, because each of the two adds a line of its own to a chip:
 * the company its own 18 px block under the name, a wrapped name a
 * second 21 px name line. They compose — a chip wearing both stands
 * three lines tall — so the two terms add rather than one replacing the
 * other.
 *
 * The second argument is `listWrapsToTwoLines`'s answer, not
 * `show_full_names` itself: the option only ALLOWS a second line, and
 * a plan whose names all fit on one would otherwise reserve 21 px per
 * chip that nothing ever draws — 168 px per row of eight-seat tables.
 *
 * This is ONE CHIP'S pitch. Nothing multiplies it by a list's length:
 * `listReservedHeight` below is what every reservation goes through,
 * and it adds the chips up one by one at each one's own pitch. A
 * reader left on the bare LIST_LINE_HEIGHT reserves a one-line chip's
 * room for a two- or three-line chip, which is one row of names drawn
 * across the next row's.
 */
export function listLinePitch(showCompany, wrapsToTwoLines) {
    return (
        LIST_LINE_HEIGHT +
        (showCompany ? LIST_COMPANY_LINE_HEIGHT : 0) +
        (wrapsToTwoLines ? LIST_FULL_NAME_LINE_HEIGHT : 0)
    );
}

/**
 * The height a name list of `chipCount` chips takes, of which
 * `wrappingChipCount` wrap onto a second name line.
 *
 * CHIP BY CHIP, never one pitch times a count. A list is a stack of
 * chips that each stand as tall as their own label needs: the pitch
 * `listLinePitch` gives is one chip's, and multiplying it by a whole
 * list charges every chip for the tallest of them. On a table of eight
 * where a single name wraps that is 168 px reserved for a 21 px need,
 * and it is the reason this function exists rather than a bare
 * multiplication.
 *
 * All three reservations are this one call, which is what keeps them
 * from drifting: `floorSize` below and `_grid_positions`
 * (event_table_plan.py, through the Python twin `list_reserved_height`)
 * both reserve a table's CAPACITY — `chipCount` is `seat_count`, since
 * a list has to still fit once the table fills — while `listHeight`
 * (floor_plan.js) measures the people actually seated this round, with
 * `chipCount` their own number. An EMPTY SEAT carries no name, so it
 * cannot wrap and counts as one line.
 *
 * The wrapping count is clamped into the list rather than trusted: it
 * reaches `floorSize` from a payload and `_grid_positions` from a
 * placement, and a count larger than the list would reserve room for
 * chips that cannot exist while a negative one would reserve less than
 * a line each.
 */
export function listReservedHeight(chipCount, wrappingChipCount, showCompany) {
    const wrapping = Math.min(Math.max(wrappingChipCount, 0), chipCount);
    return wrapping * listLinePitch(showCompany, true) + (chipCount - wrapping) * listLinePitch(showCompany, false);
}

/**
 * Rounds a value to the nearest multiple of `grid`.
 */
export function snapToGrid(value, grid = GRID_SIZE) {
    return Math.round(value / grid) * grid;
}

/**
 * Forbids a negative coordinate on either axis, keeping a table from
 * leaving the floor by the top or the left.
 */
export function clampPosition(x, y) {
    return {x: Math.max(0, x), y: Math.max(0, y)};
}

/**
 * Places `seatCount` seats around a table surface of `width` by `height`,
 * relative to the table's own top-left corner. A round table distributes
 * seats evenly on an ellipse; a square table walks the perimeter of the
 * rectangle at the same distance. Both rings sit SEAT_RADIUS + 4 outside
 * the surface, and both start at the top centre, going clockwise.
 *
 * Each seat also carries `angle`, in radians, standard math convention
 * (0 along +x, growing clockwise since y grows downward on screen): the
 * direction a chair drawn top-down must face to look toward the table,
 * for `visual_tables` (floor_plan.js/.xml). On a ROUND table that
 * direction is radial: a seat's own placement angle `theta` points
 * OUTWARD from the centre (it is literally how `x, y` are built below),
 * so facing INWARD is `theta + Math.PI`. On a SQUARE table a chair on a
 * long side faces PERPENDICULAR to that side, toward the inside, never
 * toward the table's centre point specifically — a chair on the top
 * edge of a wide, short table still faces straight down, not toward a
 * centre that may be far to one side of it. A seat that lands exactly
 * on a corner keeps the facing angle of whichever edge segment the walk
 * already assigned its `x, y` to (the same branch decides both), rather
 * than some blended diagonal — simplest, and nothing in this project
 * distinguishes the two.
 */
export function seatPositions(shape, width, height, seatCount) {
    if (!seatCount) {
        return [];
    }
    const centerX = width / 2;
    const centerY = height / 2;
    const seats = [];
    if (shape === "square") {
        const left = -SEAT_RADIUS - CHAIR_RING_GAP;
        const top = -SEAT_RADIUS - CHAIR_RING_GAP;
        const right = width + SEAT_RADIUS + CHAIR_RING_GAP;
        const bottom = height + SEAT_RADIUS + CHAIR_RING_GAP;
        const perimeter = 2 * (right - left) + 2 * (bottom - top);
        const step = perimeter / seatCount;
        // Perimeter distance walked clockwise from the top centre, the
        // point the loop below converts back to (x, y) on each side.
        let distance = (right - left) / 2;
        for (let k = 0; k < seatCount; k++) {
            let d = distance % perimeter;
            let x;
            let y;
            let angle;
            const topLen = right - left;
            const rightLen = bottom - top;
            const bottomLen = right - left;
            if (d < topLen) {
                x = left + d;
                y = top;
                angle = Math.PI / 2; // top edge: face down, into the table
            } else if (d < topLen + rightLen) {
                x = right;
                y = top + (d - topLen);
                angle = Math.PI; // right edge: face left
            } else if (d < topLen + rightLen + bottomLen) {
                x = right - (d - topLen - rightLen);
                y = bottom;
                angle = -Math.PI / 2; // bottom edge: face up
            } else {
                x = left;
                y = bottom - (d - topLen - rightLen - bottomLen);
                angle = 0; // left edge: face right
            }
            seats.push({seat: k + 1, x, y, angle});
            distance += step;
        }
        return seats;
    }
    const rx = centerX + SEAT_RADIUS + CHAIR_RING_GAP;
    const ry = centerY + SEAT_RADIUS + CHAIR_RING_GAP;
    for (let k = 0; k < seatCount; k++) {
        const theta = -Math.PI / 2 + (2 * Math.PI * k) / seatCount;
        seats.push({
            seat: k + 1,
            x: centerX + rx * Math.cos(theta),
            y: centerY + ry * Math.sin(theta),
            angle: theta + Math.PI,
        });
    }
    return seats;
}

/**
 * The table size visual_tables draws instead of the table's own stored
 * `width`/`height`, which stay exactly as the operator left them in the
 * database — auto-size is a RENDERING choice, never written back, so
 * leaving visual mode restores the manual size untouched (the same
 * toggle-safety contract already binding for the rim margins).
 *
 * Derived from FOUR needs, never tuned by eye, the table's size being
 * whichever asks for the most room:
 *
 * 1. THE PARTY: a table reads as seating its guests only if it grows
 *    with them — PARTY_BASE_SPAN for the first two chairs, then
 *    PARTY_SPAN_PER_SEAT for each one after them. Without this term
 *    the content term below, which is fixed, hides the rim term's own
 *    growth up to 15 chairs, and a table of eight draws at exactly a
 *    table of two's size.
 * 2. THE RIM: a chair's own footprint is `2 * SEAT_RADIUS` across, so
 *    `seatCount` of them need at least that many times
 *    `2 * SEAT_RADIUS + SEAT_GAP` of room around the ring `seatPositions`
 *    actually places them on — the circumference of a round table's
 *    ring, the perimeter of a rectangular one's — NOT the table's own
 *    edge: that ring sits `SEAT_RADIUS + CHAIR_RING_GAP` further out on
 *    every side (`seatPositions`' own `left`/`top`/`right`/`bottom`,
 *    `rx`/`ry`), so sizing against the edge would size against a
 *    smaller circle than chairs are actually placed on — the same twin
 *    divergence as elsewhere in this file, only both twins live in this
 *    one. The table's own width/height is therefore the RING size this
 *    term first solves for, shrunk back by that same offset on every
 *    side. A RECTANGULAR table asks CORNER_CHORD_PENALTY times that
 *    span, which is what covers two chairs straddling a corner: they
 *    stand closer, in a straight line, than the same walk-distance
 *    along one edge.
 * 3. THE CONTENT: the surface shows two lines — the table number and the
 *    occupancy count — which `.o_event_table_surface` draws
 *    unconditionally (floor_plan.xml), on a surface carrying no
 *    `overflow` rule to hide what does not fit. The term is FIXED at
 *    those two lines whatever `assignSeats` and `showCompany` say: it
 *    reserves a header, not a guest list, so it never grows with the
 *    seat count. NAME_CHIP_WIDTH stands in for one line's own width,
 *    since neither a number nor a name is measured for real.
 * 4. THE CHAIRS THEMSELVES: a table must never read as smaller than the
 *    chairs standing around it — two of them side by side, at minimum,
 *    however few seats there are — or the table itself all but
 *    disappears behind its own furniture.
 *
 * WHICH TERM BINDS, with today's constants: on a round table, the party
 * term at every seat count but two, where the content term's own
 * diagonal (100.18) is 0.18 px wider than PARTY_BASE_SPAN. On a
 * rectangular table, the party term up to 61 seats and the rim term
 * from 62 up, where `11.879 * seatCount - 36` overtakes
 * `10 * seatCount + 80`. The rim term never binds on a ROUND table: the
 * party term already gives its ring 10 px of diameter per seat against
 * the `(2 * SEAT_RADIUS + SEAT_GAP) / PI = 8.91` that term asks for,
 * and starts higher besides. It is kept because it STATES the promise
 * in the code, which a floor chosen for how a table reads does not, and
 * because a change to either constant can put it back in charge.
 *
 * Every term is monotone in the seat count and none of them shrinks, so
 * adding a chair never draws a smaller table — the property the
 * fixture's own rows are checked for on both sides
 * (geometry.test.js, test_visual_table_size_matches_js.py).
 *
 * A round table returns equal width and height, since anything else
 * would draw an ellipse, not a circle, once `border-radius: 50%`
 * applies; fitting the content rectangle inside that circle uses its
 * DIAGONAL (Pythagoras) as the required diameter, since the smallest
 * circle around an axis-aligned rectangle always touches its four
 * corners — a disc wastes its own corners compared to a square holding
 * the same text, which is exactly why the round branch needs this term
 * and the square one does not. A round table has no corners, and pays
 * no CORNER_CHORD_PENALTY either: two chairs on a ring are also
 * slightly closer, in a straight line, than the same arc-length apart
 * (a chord is always shorter than its own arc), but that shortfall
 * shrinks toward zero as the ring grows with the seat count, unlike a
 * rectangle's, which stays concentrated at just four points. Measured
 * over every seat count from 2 to 2000, both `assignSeats` states —
 * which return the same size, the content term no longer reading that
 * flag — the closest two chairs ever stand on a round table is 31.59
 * px, clear of the 28 px target the rim term names and well clear of
 * the 22 px at which two pads would actually touch.
 *
 * A rectangular table's CONTENT term is derived from AREA, not from
 * stacking every line in one column: `seatCount` lines of
 * `NAME_CHIP_WIDTH` each, stacked one under the other, grow ever
 * TALLER while staying exactly `NAME_CHIP_WIDTH` wide, which drove a
 * "rectangular" table portrait — narrower than tall — for any
 * reasonably full, unassigned table, the opposite of what
 * RECTANGLE_ASPECT_RATIO names. Instead, the total area those lines
 * need is reshaped into a rectangle that already keeps
 * RECTANGLE_ASPECT_RATIO between its own sides — the browser is left to
 * wrap the actual name chips within that shape (`.o_event_table_person`
 * is `display: inline-block`, `floor_plan.scss`), which this still does
 * not measure for real, same as NAME_CHIP_WIDTH itself never did. The
 * rim and party terms already keep the same ratio by construction
 * (`rimWidth = RATIO * rimHeight`, and the party span is read as a
 * width against `partySpan / RATIO` as a height), so whichever of the
 * three asks for more room wins on BOTH sides at once, and the ratio
 * survives either way. The chair floor is the one term that does not
 * keep it, and it never binds: two seats already ask 100 by 66.67, both
 * above its 56.
 */

// How much more ring a RECTANGULAR table's rim term asks for than a
// straight edge alone needs. Two chairs one walk-step apart on the
// same edge stand exactly that step apart; two straddling a corner
// stand `hypot(a, b)` apart, where `a + b` is the same step — shortest
// when the corner falls halfway between them, at `step / sqrt(2)`.
// Paying sqrt(2) up front therefore keeps SEAT_GAP's promise wherever
// the corners happen to fall, without predicting WHICH chairs straddle
// one, and it is a closed form: the size stays monotone in the seat
// count by construction, where a solver growing the table by whole
// multiplicative passes crosses a number of passes that is NOT
// monotone in it, and so draws a SMALLER table for one more seat. The
// bound is loose by construction, since a corner rarely falls exactly
// halfway: the closest two chairs ever stand on a rectangular table is
// 28.03 px, measured over every seat count from 2 to 2000, against the
// 28 px target.
const CORNER_CHORD_PENALTY = Math.SQRT2;

export function visualTableSize(shape, seatCount, assignSeats, showCompany) {
    const seatSpan = 2 * SEAT_RADIUS + SEAT_GAP;
    // seatPositions places every chair this far outside the table's own
    // edge — the rim term below sizes the RING chairs actually occupy,
    // then shrinks back to the table's own edge by this same offset.
    const ringGap = SEAT_RADIUS + CHAIR_RING_GAP;
    // Never smaller than two chairs side by side, whatever the party,
    // the rim or the content would otherwise allow.
    const chairFloor = 2 * seatSpan;
    // Grows with the party, and is the only term that does: read as a
    // WIDTH on a rectangular table, whose height follows from the same
    // ratio the rim term keeps, and as a DIAMETER on a round one.
    const partySpan = PARTY_BASE_SPAN + PARTY_SPAN_PER_SEAT * Math.max(seatCount - 2, 0);
    // The content term reserves the table's own HEADER and nothing more:
    // the table number and the occupancy count, the two lines
    // `.o_event_table_surface` draws unconditionally (floor_plan.xml), on
    // a surface carrying no `overflow` rule to clip what does not fit. It
    // never grows with the seat count, which is what the party term is
    // for. `assignSeats` and `showCompany` select nothing here any more;
    // they stay in the signature because this footprint is computed in two
    // languages (visual_table_size, event_table.py) against one generated
    // fixture that pins both as columns, so dropping them would move every
    // call site and reshape the fixture without changing a single result.
    const contentLines = 2;
    const contentHeight = contentLines * NAME_LINE_HEIGHT;
    const contentWidth = NAME_CHIP_WIDTH;

    if (shape === "square") {
        // The ring's own perimeter is 2 * (width + height) + 8 * ringGap
        // (seatPositions: each of the 4 sides of the dilated rectangle
        // is ringGap longer, twice, than the table's own side). Solving
        // that, not the table's own 2 * (width + height), for
        // rimRequirement is what makes this the same ring seatPositions
        // walks. width = RATIO * height:
        // rimRequirement = 2 * height * (RATIO + 1) + 8 * ringGap
        const rimRequirement = seatCount * seatSpan * CORNER_CHORD_PENALTY;
        const rimHeight = (rimRequirement - 8 * ringGap) / (2 * (RECTANGLE_ASPECT_RATIO + 1));
        const rimWidth = RECTANGLE_ASPECT_RATIO * rimHeight;
        // area = width * height = RATIO * height^2 => height = sqrt(area / RATIO)
        const contentArea = contentLines * NAME_LINE_HEIGHT * NAME_CHIP_WIDTH;
        const contentAreaHeight = Math.sqrt(contentArea / RECTANGLE_ASPECT_RATIO);
        const contentAreaWidth = RECTANGLE_ASPECT_RATIO * contentAreaHeight;
        return {
            width: Math.max(chairFloor, rimWidth, contentAreaWidth, partySpan),
            height: Math.max(chairFloor, rimHeight, contentAreaHeight, partySpan / RECTANGLE_ASPECT_RATIO),
        };
    }
    // The ring's own circumference is PI * (diameter + 2 * ringGap)
    // (seatPositions: rx and ry both add ringGap to the table's own
    // radius). Solving THAT for rimRequirement, then subtracting the
    // ring's own diameter back out, is what sizes the table so its
    // chairs — placed on the dilated ring, not the table's own edge —
    // get rimRequirement of room.
    const rimDiameter = (seatCount * seatSpan) / Math.PI - 2 * ringGap;
    const contentDiameter = Math.hypot(contentWidth, contentHeight);
    const diameter = Math.max(chairFloor, rimDiameter, contentDiameter, partySpan);
    return {width: diameter, height: diameter};
}

/**
 * Converts a drag's viewport coordinates into a floor position: subtracts
 * where the pointer grabbed the table and the floor's own offset, adds the
 * scrolling pane's own scroll, then divides the lot by the zoom to undo the
 * room's scale, and finally snaps to the grid and forbids a negative
 * coordinate. `scroll` is read off the SCROLLING PANE (.o_event_table_floor),
 * which is not the element the zoom transform is applied to (see
 * floor_plan.js's floorStyle/roomStyle): its scrollLeft/scrollTop are
 * therefore already expressed in the same on-screen, zoomed pixels as
 * `pointer` and `rect`, not in the room's native ones — hence the single
 * division applying to the pointer distance AND the scroll together, rather
 * than to the pointer distance alone.
 */
export function dropPosition(pointer, grab, rect, scroll, zoom) {
    const x = (pointer.x - grab.x - rect.left + scroll.left) / zoom;
    const y = (pointer.y - grab.y - rect.top + scroll.top) / zoom;
    return clampPosition(snapToGrid(x), snapToGrid(y));
}

/**
 * Applies a resize movement to a table's dimensions, snaps the result to
 * the grid, and never lets either dimension go below MIN_TABLE_SIZE.
 */
export function resizeTable(width, height, dx, dy) {
    return {
        width: Math.max(MIN_TABLE_SIZE, snapToGrid(width + dx)),
        height: Math.max(MIN_TABLE_SIZE, snapToGrid(height + dy)),
    };
}

/**
 * Sizes the floor to cover every table, its seat ring, and the name list
 * drawn beside it, never smaller than 600 by 400.
 *
 * EVERY table carries a list on its RIGHT, in both seating modes and
 * whether or not `visualTables` is on: floor_plan.xml draws one
 * `.o_event_table_names` per table unconditionally. So both terms below
 * apply to every table, with no flag selecting them — where the panel
 * this replaced was reserved only when the names sat under the table.
 *
 * The width term reserves, beyond the table itself, the seat ring, the
 * connector, and the list column. The height term takes whichever of the
 * TABLE and its OWN LIST is taller, rather than adding them: they sit
 * side by side, so the row below has to clear the taller of the two. A
 * list is routinely the taller one — eight names stand 232 px where
 * their table stands 100 — which is why this is a max and not the
 * table's height alone.
 *
 * A list is measured at `seat_count` CHIPS, not at however many people
 * happen to be seated this round: that is the upper bound the list can
 * ever reach, and it is also all _grid_positions knows, since it places
 * tables before anyone is seated at all. Each chip is `listLinePitch`
 * tall, which is one line without `showCompany` and two with it — a
 * height term left on LIST_LINE_HEIGHT alone reserves a one-line chip's
 * room for a two-line chip.
 *
 * _grid_positions (event_table_plan.py) builds its own step_x and step_y
 * from these same terms; keep the two in step, since this is that same
 * arithmetic written a second time, in a second language, and that
 * duplication is exactly how such a pair drifts apart later.
 *
 * The margin is added once, at the end, since clampPosition already
 * forbids a table at a negative position and a leading margin would only
 * be dead space.
 *
 * `assignSeats` is passed straight through to `visualTableSize`, whose
 * result no longer varies on it — see that function's own comment — and
 * is kept in this signature so every caller and the generated fixture
 * keep the one they already use. `showCompany` is forwarded the same
 * way, but it ALSO drives the height term directly, through
 * `listLinePitch`: it is the flag that turns each chip of the list into
 * two lines. `showFullNames` reaches BOTH terms and no table: it widens
 * the column the width term reserves, through `listWidth`, and it is
 * what lets the height term carry a second name line at all. The
 * table's own surface never reads it — a name list is drawn beside a
 * table, never inside it — which is why `visualTableSize` below takes
 * no such argument.
 *
 * The height term reserves each table's list CHIP BY CHIP
 * (`listReservedHeight`), reading `wrapping_label_count` off the table
 * itself: the number of its chips whose label needs a second name
 * line, which the server counts and the payload carries
 * (`_wrapping_label_counts`, event_table_plan.py). A table absent that
 * field reserves one line per seat, which is what a plan hiding whole
 * names takes and what a table nobody sits at takes. `showFullNames`
 * gates the count rather than trusting it: a plan with the option off
 * clips every chip to one line whatever the payload says, and the
 * invariant belongs here rather than at whoever filled the field.
 */
export function floorSize(
    tables,
    margin = 80,
    visualTables = false,
    assignSeats = false,
    showCompany = false,
    showFullNames = false
) {
    let width = 0;
    let height = 0;
    for (const table of tables) {
        // Visual mode never reads the table's own stored width/height —
        // it draws visualTableSize's own computed size instead
        // (floor_plan.js's surfaceStyle does the same) — so measuring
        // the floor from the stored size here would be exactly the twin
        // divergence already fixed twice on this file: the screen
        // drawing one size, the container reserving another. assignSeats
        // and showCompany are plan-wide, like visualTables, and are
        // forwarded unchanged even though visualTableSize's content term
        // no longer reads either.
        const size = visualTables ? visualTableSize(table.shape, table.seat_count, assignSeats, showCompany) : table;
        width = Math.max(width, table.x + size.width + SEAT_RING + CONNECTOR_WIDTH + listWidth(showFullNames));
        const wrapping = showFullNames ? table.wrapping_label_count || 0 : 0;
        const listHeight = listReservedHeight(table.seat_count, wrapping, showCompany);
        height = Math.max(height, table.y + Math.max(size.height + SEAT_RING, listHeight));
    }
    return {
        width: Math.max(600, width + margin),
        height: Math.max(400, height + margin),
    };
}

/**
 * Reads a candidate's numeric dataset field, or 0 when it is absent.
 */
function datasetNumber(dataset, key) {
    return key in dataset ? Number(dataset[key]) : 0;
}

/**
 * Picks the drop target under the pointer from a list of candidates
 * ordered nearest first, such as document.elementsFromPoint(x, y) or a
 * test's plain stand-ins. The dragged person's own chip is skipped
 * entirely, since dropping on yourself would mean a pointless move to the
 * table you are already at. Within a candidate, a name chip beats a seat,
 * a seat beats the tray, and the tray beats a bare table surface — a tray
 * chip carries no table, so it never reads as a swap.
 */
export function findDropTarget(candidates, draggedParticipantId) {
    for (const candidate of candidates) {
        const dataset = candidate.dataset;
        const participantId = datasetNumber(dataset, "participantId");
        if (participantId && participantId === draggedParticipantId) {
            continue;
        }
        const tableId = datasetNumber(dataset, "tableId");
        if (participantId && tableId) {
            return {
                kind: "participant",
                tableId,
                seat: 0,
                participantId,
            };
        }
        const seat = datasetNumber(dataset, "seat");
        if (seat && tableId) {
            return {kind: "seat", tableId, seat, participantId: 0};
        }
        if ("tray" in dataset) {
            return {kind: "tray", tableId: 0, seat: 0, participantId: 0};
        }
        if (tableId) {
            return {kind: "table", tableId, seat: 0, participantId: 0};
        }
    }
    return null;
}
