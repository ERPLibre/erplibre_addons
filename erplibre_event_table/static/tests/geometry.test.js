/** @odoo-module **/
import {describe, expect, test} from "@odoo/hoot";
import {
    CHAIR_RING_GAP,
    CONNECTOR_WIDTH,
    GRID_SIZE,
    LIST_COMPANY_LINE_HEIGHT,
    LIST_FULL_NAME_LINE_HEIGHT,
    LIST_FULL_NAME_ONE_LINE_CHARS,
    LIST_LINE_HEIGHT,
    LIST_WIDTH,
    LIST_WIDTH_FULL,
    MIN_TABLE_SIZE,
    NAME_CHIP_WIDTH,
    NAME_LINE_HEIGHT,
    PARTY_BASE_SPAN,
    PARTY_SPAN_PER_SEAT,
    RECTANGLE_ASPECT_RATIO,
    SEAT_GAP,
    SEAT_RADIUS,
    SEAT_RING,
    clampPosition,
    dropPosition,
    findDropTarget,
    floorSize,
    listLabelLength,
    listLinePitch,
    listReservedHeight,
    listWidth,
    listWrapsToTwoLines,
    resizeTable,
    seatPositions,
    snapToGrid,
    visualTableSize,
} from "@erplibre_event_table/floor_plan/geometry";
import {
    LIST_RESERVATION_FIXTURE,
    LIST_RESERVED_HEIGHT_FIXTURE,
    VISUAL_TABLE_SIZE_FIXTURE,
} from "./visual_table_size_fixture.js";

const near = (a, b) => Math.abs(a - b) < 1e-9;

// An eight-seat table placed far enough out that a floor measured from
// it clears the 600 by 400 this module never returns less than, which
// would otherwise swallow the differences these tests are about.
// `wrapping` is what the server counts and the payload carries
// (_wrapping_label_counts): how many of this table's chips need a
// second name line.
const tableWrapping = (wrapping) => ({
    x: 400,
    y: 400,
    width: 140,
    height: 140,
    seat_count: 8,
    wrapping_label_count: wrapping,
});

// Mirrors _grid_positions (event_table_plan.py) closely enough to derive
// a fixture's table positions instead of hardcoding its printed output —
// a copied number is exactly the shape of mistake that let a stale 668
// stand unnoticed here as "the figure on record". Not exported: it
// exists only for the tests that need it. GRID_MARGIN and GRID_GAP_X
// have no JS twin to import (they live only in event_table_plan.py), so
// they are repeated here as literals; SEAT_RING, CONNECTOR_WIDTH,
// listWidth, listLinePitch and visualTableSize are the real,
// imported ones — visual mode's step must use the SAME auto-computed
// size floorSize and surfaceStyle draw, not the fixed TABLE_SIZE
// non-visual mode still uses, or this mirror would reproduce the exact
// overlap bug _grid_positions was fixed for.
//
// The margin is plain GRID_MARGIN on both axes, with no wider case: the
// band a fresh grid used to reserve for labels around a table's rim went
// with the labels themselves, now that every name sits in a column to
// the table's right instead of around it.
function gridPositions(
    count,
    seats,
    visualTables,
    shape = "round",
    assignSeats = false,
    showCompany = false,
    showFullNames = false,
    wrappingLabelCount = 0
) {
    const TABLE_SIZE = 140;
    const GRID_MARGIN = 40;
    const GRID_GAP_X = 180;
    const columns = Math.max(1, Math.ceil(Math.sqrt(count)));
    let tableWidth;
    let tableHeight;
    if (visualTables) {
        const size = visualTableSize(shape, seats, assignSeats, showCompany);
        tableWidth = size.width;
        tableHeight = size.height;
    } else {
        tableWidth = TABLE_SIZE;
        tableHeight = TABLE_SIZE;
    }
    const stepX = tableWidth + SEAT_RING + CONNECTOR_WIDTH + listWidth(showFullNames) + GRID_GAP_X;
    const wrapping = showFullNames ? wrappingLabelCount : 0;
    const stepY = Math.max(tableHeight + SEAT_RING, listReservedHeight(seats, wrapping, showCompany)) + 40;
    return Array.from({length: count}, (_, index) => [
        GRID_MARGIN + (index % columns) * stepX,
        GRID_MARGIN + Math.floor(index / columns) * stepY,
    ]);
}

describe("constants", () => {
    test("the drawing constants the styles depend on", () => {
        expect(SEAT_RADIUS).toBe(11);
        expect(SEAT_RING).toBe(26);
        expect(GRID_SIZE).toBe(10);
        expect(MIN_TABLE_SIZE).toBe(40);
        expect(NAME_LINE_HEIGHT).toBe(22);
    });

    test("the seven name-list constants, each measuring its own thing", () => {
        // Pinned here AND against this file's own text by
        // test_visual_table_size_matches_js.py, which is what keeps the
        // Python half of the pair from drifting. Separate numbers
        // rather than one rounded total, so that a list overrunning its
        // reservation names which of them was too small.
        expect(LIST_WIDTH).toBe(220);
        expect(LIST_WIDTH_FULL).toBe(280);
        expect(LIST_LINE_HEIGHT).toBe(29);
        expect(LIST_COMPANY_LINE_HEIGHT).toBe(18);
        expect(LIST_FULL_NAME_LINE_HEIGHT).toBe(21);
        expect(LIST_FULL_NAME_ONE_LINE_CHARS).toBe(18);
        expect(CONNECTOR_WIDTH).toBe(34);
        // The connector has to clear the chairs on the side it crosses,
        // or the trait would be drawn straight through a chair pad.
        expect(CONNECTOR_WIDTH > 0).toBe(true);
        // A list line is TALLER than a line of text inside the table:
        // reserving one with the other is exactly the mistake this
        // separation exists to prevent.
        expect(LIST_LINE_HEIGHT > NAME_LINE_HEIGHT).toBe(true);
        // The company line is the SMALLER of the two: it is a 12 px
        // font on an 18 px line box, and it adds no padding and no
        // margin of its own, both being paid once per chip. A
        // multiplier on LIST_LINE_HEIGHT would pay them a second time
        // and reserve 11 px per chip that no chip ever takes.
        expect(LIST_COMPANY_LINE_HEIGHT < LIST_LINE_HEIGHT).toBe(true);
        // A second NAME line is the smaller of the two as well, and for
        // the same reason: it is the 21 px line box alone, where the
        // one-line pitch also carries the chip's padding, its border
        // and the margin between two chips.
        expect(LIST_FULL_NAME_LINE_HEIGHT < LIST_LINE_HEIGHT).toBe(true);
        // Whole names need a WIDER column, or the second line would be
        // the ordinary case rather than the exception it is reserved
        // as.
        expect(LIST_WIDTH_FULL > LIST_WIDTH).toBe(true);
        // The threshold counts at the WIDEST glyph, never at an average
        // one: the same 265 px of text carry 41 characters of an
        // ordinary name and 18 of the widest the alphabet holds. A
        // threshold at the average would reserve one line for a label
        // the browser draws on two — the silent overrun this whole
        // geometry exists to prevent — so it has to stay well under
        // that figure.
        expect(LIST_FULL_NAME_ONE_LINE_CHARS < 41).toBe(true);
    });

    test("listWidth widens the column, and only where show_full_names asks", () => {
        // The one figure every horizontal reservation of a list reads:
        // the grid's own column step, the floor's width term, and the
        // list the component actually draws. A caller left on the bare
        // constant draws a list wider than the room reserved for it.
        expect(listWidth(false)).toBe(LIST_WIDTH);
        expect(listWidth(true)).toBe(LIST_WIDTH_FULL);
    });

    test("listLabelLength counts the number a list prints, not the bare name", () => {
        // What the browser lays out is "1. Ada Bell", never "Ada Bell":
        // floor_plan.xml numbers every line of a list. A caller
        // measuring the bare name lets a label three characters longer
        // than it thinks past the threshold, on every line of every
        // list, and a list one character over reserves one line and
        // draws two.
        expect(listLabelLength(1, "Ada Bell")).toBe("1. Ada Bell".length);
        // A two-digit number costs one character more than a one-digit
        // one, which is why the number is counted and not assumed.
        expect(listLabelLength(10, "Ada Bell")).toBe(listLabelLength(1, "Ada Bell") + 1);
        // A participant line added and left blank carries no name at
        // all; the number and its separator still do.
        expect(listLabelLength(1, "")).toBe(3);
        expect(listLabelLength(1, undefined)).toBe(3);
    });

    test("listWrapsToTwoLines answers no while the chip is clipped, whatever the name", () => {
        // Without show_full_names the chip is cut to one line
        // (floor_plan.scss), so no length can make it wrap and no
        // reservation may pay for a second one. This is what keeps a
        // plan that never asked for the option from paying 21 px a chip
        // for it.
        expect(listWrapsToTwoLines(false, 0)).toBe(false);
        expect(listWrapsToTwoLines(false, 500)).toBe(false);
    });

    test("listWrapsToTwoLines turns on ONE character past the threshold, not at it", () => {
        // The two lengths that straddle the threshold, which are the
        // only ones an off-by-one can be read off. A label of exactly
        // LIST_FULL_NAME_ONE_LINE_CHARS characters FITS — the constant
        // is a capacity, not a limit already exceeded — and the next
        // one does not.
        expect(listWrapsToTwoLines(true, LIST_FULL_NAME_ONE_LINE_CHARS)).toBe(false);
        expect(listWrapsToTwoLines(true, LIST_FULL_NAME_ONE_LINE_CHARS + 1)).toBe(true);
        // A plan holding nobody reserves nothing extra.
        expect(listWrapsToTwoLines(true, 0)).toBe(false);
    });

    test("listLinePitch adds the company line, and only where show_company asks", () => {
        // The one figure every reservation of a list reads: the grid's
        // own row step, the floor's height term, and the drawn list
        // that gives the connector its bracket. A chip carries the name
        // alone by default, and a second line under it once the option
        // is on.
        expect(listLinePitch(false, false)).toBe(LIST_LINE_HEIGHT);
        expect(listLinePitch(true, false)).toBe(LIST_LINE_HEIGHT + LIST_COMPANY_LINE_HEIGHT);
        expect(listLinePitch(true, false) > listLinePitch(false, false)).toBe(true);
        // Well under twice the one-line pitch, which is what a
        // multiplier would have reserved.
        expect(listLinePitch(true, false) < 2 * LIST_LINE_HEIGHT).toBe(true);
    });

    test("listLinePitch adds the wrapped name's second line, and composes with the company", () => {
        // show_full_names lets a name take a second LINE OF ITS OWN,
        // where show_company adds a block under it. The two are
        // different lines, so a chip wearing both stands three lines
        // tall and the terms ADD: a pitch where one option replaced the
        // other would reserve two lines for a chip that draws three,
        // which is one row of names over the next row's.
        expect(listLinePitch(false, true)).toBe(LIST_LINE_HEIGHT + LIST_FULL_NAME_LINE_HEIGHT);
        expect(listLinePitch(true, true)).toBe(
            LIST_LINE_HEIGHT + LIST_COMPANY_LINE_HEIGHT + LIST_FULL_NAME_LINE_HEIGHT
        );
        expect(listLinePitch(true, true) > listLinePitch(true, false)).toBe(true);
        expect(listLinePitch(true, true) > listLinePitch(false, true)).toBe(true);
        // Still well under twice the one-line pitch for the second name
        // line alone: that line costs its own line box and nothing
        // else, the chip's padding, border and margins being paid once.
        expect(listLinePitch(false, true) < 2 * LIST_LINE_HEIGHT).toBe(true);
    });

    test("the party floor, the one term of visualTableSize that grows with the seat count", () => {
        // Pinned here AND against this file's own text by
        // test_visual_table_size_matches_js.py, same as the three
        // above: both halves compute the footprint, and nothing else
        // would notice one copy being edited alone.
        expect(PARTY_BASE_SPAN).toBe(100);
        expect(PARTY_SPAN_PER_SEAT).toBe(10);
        // A base that already carries two chairs side by side, so the
        // party term subsumes the chair floor at every seat count
        // rather than fighting it.
        expect(PARTY_BASE_SPAN > 2 * (2 * SEAT_RADIUS + SEAT_GAP)).toBe(true);
    });
});

describe("seatPositions", () => {
    test("numbers every seat once, starting at 1", () => {
        const seats = seatPositions("round", 140, 140, 7);
        expect(seats.length).toBe(7);
        expect(seats.map((s) => s.seat)).toEqual([1, 2, 3, 4, 5, 6, 7]);
        const spots = new Set(seats.map((s) => `${s.x.toFixed(6)}:${s.y.toFixed(6)}`));
        expect(spots.size).toBe(7);
    });

    test("a round table starts at the top, centred on the surface", () => {
        const [first] = seatPositions("round", 140, 140, 4);
        expect(first.seat).toBe(1);
        expect(near(first.x, 70)).toBe(true);
        // The ring sits SEAT_RADIUS + 4 outside the surface.
        expect(near(first.y, -15)).toBe(true);
    });

    test("four seats on a round table reach the four compass points", () => {
        const at = seatPositions("round", 140, 140, 4).map((s) => [Math.round(s.x), Math.round(s.y)]);
        expect(at).toEqual([
            [70, -15],
            [155, 70],
            [70, 155],
            [-15, 70],
        ]);
    });

    test("opposite seats of a round table are symmetric", () => {
        const seats = seatPositions("round", 140, 100, 6);
        for (let k = 0; k < 3; k++) {
            expect(near(seats[k].x + seats[k + 3].x, 140)).toBe(true);
            expect(near(seats[k].y + seats[k + 3].y, 100)).toBe(true);
        }
    });

    test("a square table walks its perimeter clockwise from the top", () => {
        const at = seatPositions("square", 140, 140, 4).map((s) => [Math.round(s.x), Math.round(s.y)]);
        expect(at).toEqual([
            [70, -15],
            [155, 70],
            [70, 155],
            [-15, 70],
        ]);
    });

    test("a round table's seats face radially inward, toward the centre", () => {
        // Seat 1 sits straight up (theta = -PI/2, outward); facing the
        // table means facing straight down: -PI/2 + PI = PI/2. Seat 2 of
        // 4 sits at 3 o'clock (theta = 0, outward = right); facing the
        // table means facing left: PI.
        const [seat1, seat2] = seatPositions("round", 140, 140, 4);
        expect(near(seat1.angle, Math.PI / 2)).toBe(true);
        expect(near(seat2.angle, Math.PI)).toBe(true);
    });

    test("a square table's seats face perpendicular to their own edge", () => {
        // The four seats of the perimeter test above sit at the top,
        // right, bottom and left midpoints in that order; each faces
        // straight into the table from its own edge, never diagonally
        // toward a centre that may be far off to one side.
        const [top, right, bottom, left] = seatPositions("square", 140, 140, 4);
        expect(near(top.angle, Math.PI / 2)).toBe(true);
        expect(near(right.angle, Math.PI)).toBe(true);
        expect(near(bottom.angle, -Math.PI / 2)).toBe(true);
        expect(near(left.angle, 0)).toBe(true);
    });

    test("a square table spaces its seats evenly around the perimeter", () => {
        const seats = seatPositions("square", 140, 140, 8);
        expect(seats.length).toBe(8);
        // Dilated square: side 170, perimeter 680, one seat every 85 px.
        expect(seats.map((s) => [Math.round(s.x), Math.round(s.y)])).toEqual([
            [70, -15],
            [155, -15],
            [155, 70],
            [155, 155],
            [70, 155],
            [-15, 155],
            [-15, 70],
            [-15, -15],
        ]);
    });

    test("a table with no seats draws none", () => {
        expect(seatPositions("round", 140, 140, 0)).toEqual([]);
    });
});

describe("snapToGrid", () => {
    test("rounds to the nearest multiple", () => {
        expect(snapToGrid(234)).toBe(230);
        expect(snapToGrid(235)).toBe(240);
        expect(snapToGrid(236)).toBe(240);
        expect(snapToGrid(0)).toBe(0);
    });

    test("honours a grid given by the caller", () => {
        expect(snapToGrid(234, 100)).toBe(200);
        expect(snapToGrid(261, 100)).toBe(300);
    });
});

describe("clampPosition", () => {
    test("never lets a table leave the floor by the top or the left", () => {
        expect(clampPosition(-40, -10)).toEqual({x: 0, y: 0});
        expect(clampPosition(120, -10)).toEqual({x: 120, y: 0});
        expect(clampPosition(120, 80)).toEqual({x: 120, y: 80});
    });
});

describe("resizeTable", () => {
    test("applies the movement and snaps to the grid", () => {
        expect(resizeTable(140, 140, 23, -7)).toEqual({
            width: 160,
            height: 130,
        });
    });

    test("never shrinks a table below the minimum", () => {
        expect(resizeTable(140, 140, -200, -200)).toEqual({
            width: MIN_TABLE_SIZE,
            height: MIN_TABLE_SIZE,
        });
    });

    test("a movement of nothing changes nothing", () => {
        expect(resizeTable(140, 100, 0, 0)).toEqual({
            width: 140,
            height: 100,
        });
    });
});

describe("dropPosition", () => {
    // The drag hook hands over VIEWPORT coordinates, while a table position
    // is measured from the edge of a room that is laid out at its native
    // size and scaled by a transform. `scroll` comes from the pane the
    // transform is NOT applied to (.o_event_table_floor, see floor_plan.js's
    // floorStyle/roomStyle), so it is expressed in the same on-screen,
    // zoomed pixels as `pointer` and `rect` — this conversion is the only
    // place that brings all three back to the room's native coordinates.
    const rect = {left: 100, top: 60};

    test("subtracts the grab offset and the floor origin", () => {
        const at = dropPosition({x: 300, y: 220}, {x: 20, y: 10}, rect, {left: 0, top: 0}, 1);
        expect(at).toEqual({x: 180, y: 150});
    });

    test("adds the scroll of the container", () => {
        const at = dropPosition({x: 300, y: 220}, {x: 20, y: 10}, rect, {left: 50, top: 30}, 1);
        expect(at).toEqual({x: 230, y: 180});
    });

    test("divides the pointer distance and the scroll together by the zoom", () => {
        // Both are on-screen pixels at this zoom: halving it doubles the
        // native distance either one converts to.
        const at = dropPosition({x: 300, y: 220}, {x: 20, y: 10}, rect, {left: 50, top: 30}, 0.5);
        expect(at).toEqual({x: 460, y: 360});
    });

    test("snaps the result and never returns a negative coordinate", () => {
        const at = dropPosition({x: 0, y: 0}, {x: 0, y: 0}, rect, {left: 0, top: 0}, 1);
        expect(at).toEqual({x: 0, y: 0});
        const snapped = dropPosition({x: 304, y: 226}, {x: 0, y: 0}, rect, {left: 0, top: 0}, 1);
        expect(snapped).toEqual({x: 200, y: 170});
    });
});

describe("floorSize", () => {
    test("never goes below 600 by 400", () => {
        expect(floorSize([])).toEqual({width: 600, height: 400});
    });

    test("reserves the seat ring, the connector and the list column beside a table", () => {
        // Placed far enough out that neither minimum binds, so what is
        // read below is the reservation itself and not a floor.
        const size = floorSize([{x: 400, y: 400, width: 140, height: 140, seat_count: 8}]);
        // 400 + 140 + 26 + 34 + 220 = 820, plus the 80 px margin.
        expect(size.width).toBe(900);
        // Eight names stand 8 * 29 = 232 px, taller than the table and
        // its own ring (140 + 26 = 166), so the LIST is what the height
        // term clears here: 400 + 232 = 632, plus the margin.
        expect(size.height).toBe(712);
    });

    test("the table drives the height instead, once it is taller than its own list", () => {
        // Two names stand 58 px against a 300 px table plus its 26 px
        // ring: the max goes the other way round here, which is the
        // whole reason for taking one rather than always reading the
        // list — or always reading the table.
        const size = floorSize([{x: 400, y: 400, width: 300, height: 300, seat_count: 2}]);
        // 400 + 300 + 26 = 726, plus the margin.
        expect(size.height).toBe(806);
        // 400 + 300 + 26 + 34 + 220 = 980, plus the margin.
        expect(size.width).toBe(1060);
    });

    test("covers the furthest table of the room", () => {
        const size = floorSize([
            {x: 40, y: 40, width: 140, height: 140, seat_count: 2},
            {x: 900, y: 600, width: 200, height: 160, seat_count: 4},
        ]);
        // 900 + 200 + 26 + 34 + 220 + 80 = 1460
        expect(size.width).toBe(1460);
        // The second table's own table term (160 + 26 = 186) beats its
        // list (4 * 29 = 116): 600 + 186 + 80 = 866.
        expect(size.height).toBe(866);
    });

    test("honours a margin given by the caller", () => {
        const size = floorSize([{x: 900, y: 600, width: 200, height: 160, seat_count: 4}], 0);
        expect(size.width).toBe(1380);
        expect(size.height).toBe(786);
    });

    test("measures the auto-computed size in visual mode, never the stored width/height", () => {
        // An absurd stored size (999) that would obviously dominate if
        // floorSize read it: the height term alone would be
        // 50 + 999 + 26 = 1075. visualTableSize("square", 10) is
        // {width: 180, height: 120} instead — ten seats put the party
        // term at 100 + 8 * 10 = 180, above the rim term's 82.79 — and
        // its list (10 * 29 = 290) beats that height plus the ring
        // (146), so the height is 50 + 290 + 80 = 420. The width is
        // 100 + 180 + 26 + 34 + 220 + 80 = 640. Both clear their own
        // minimum (600 by 400), which is what makes this read the
        // reservation and not a floor.
        const table = {x: 100, y: 50, width: 999, height: 999, seat_count: 10, shape: "square"};
        expect(floorSize([table], 80, true, true)).toEqual({width: 640, height: 420});
    });

    test("the list drives the height in both modes, so only the width tells the two apart", () => {
        // 25 names stand 725 px, far past either table's own height
        // plus its ring — the stored 140 + 26, or visual mode's
        // computed 220 + 26 — so BOTH modes clear the same list and the
        // height is identical. The two differ on the WIDTH alone, and
        // visual mode is the wider of them here: 25 seats put the party
        // term at 100 + 23 * 10 = 330, well past the 140 the stored
        // size carries whatever the seat count.
        const table = {x: 40, y: 300, width: 140, height: 140, seat_count: 25, shape: "square"};
        const stored = floorSize([table]);
        const visual = floorSize([table], 80, true, true);
        // 300 + 25 * 29 + 80 = 1105, on both.
        expect(stored.height).toBe(1105);
        expect(visual.height).toBe(1105);
        // 40 + 140 + 26 + 34 + 220 + 80 = 540, under the 600 minimum.
        expect(stored.width).toBe(600);
        // 40 + 330 + 26 + 34 + 220 + 80 = 730, over it.
        expect(visual.width).toBe(730);
    });

    test("a three-table, eight-seat plan matches the figure on record", () => {
        // Positions DERIVED from a small mirror of _grid_positions
        // (event_table_plan.py, above) rather than copied from its
        // printed output: a copied number is exactly the shape of
        // mistake that let 668 stand here, unnoticed, as "the figure on
        // record" until it was checked against the real function.
        const tables = (positions) => positions.map(([x, y]) => ({x, y, width: 140, height: 140, seat_count: 8}));
        expect(floorSize(tables(gridPositions(3, 8, false)))).toEqual({width: 1140, height: 624});

        // Visual mode: _grid_positions spaces this same grid on
        // visualTableSize's own auto-computed size, not the fixed
        // TABLE_SIZE the non-visual figure above still uses — an
        // 8-seat round table draws at 100 + 6 * 10 = 160 px — so the
        // column step is 160 + 26 + 34 + 220 + 180 = 620 against the
        // fixed size's 600, and the floor is WIDER, not narrower: the
        // rightmost table sits at 40 + 620 = 660, and 660 + 160 + 26 +
        // 34 + 220 + 80 = 1180. The height is identical, both modes
        // being driven by the same 8-name list. Pinning grid positions
        // AND floorSize together in one assertion, both derived from
        // the real visualTableSize the browser draws, is what keeps the
        // two from silently drifting apart again.
        const visualTables = (positions) => positions.map(([x, y]) => ({x, y, seat_count: 8, shape: "round"}));
        const visualSize = floorSize(visualTables(gridPositions(3, 8, true)), 80, true);
        expect(visualSize.width).toBe(1180);
        expect(visualSize.height).toBe(624);
    });

    test("showing companies makes every list taller, and the floor with it", () => {
        // A chip stands two lines with show_company on, so the height
        // term has to clear 8 * 47 where it cleared 8 * 29 — this is
        // the term a plan of eight-seat tables overran, drawing each
        // row of names across the next row's. The width is untouched:
        // the company sits UNDER the name, inside the same column.
        const table = {x: 40, y: 40, width: 140, height: 140, seat_count: 8};
        const plain = floorSize([table], 80, false, false, false);
        const withCompany = floorSize([table], 80, false, false, true);
        // 40 + 8 * 29 + 80 = 352, under the 400 minimum.
        expect(plain.height).toBe(400);
        // 40 + 8 * 47 + 80 = 496, over it.
        expect(withCompany.height).toBe(496);
        expect(withCompany.width).toBe(plain.width);
    });

    test("showing whole names widens every list AND makes the wrapped chips taller", () => {
        // The option is the only one of the display family that reaches
        // BOTH terms: the column widens so a whole name fits, and the
        // chips that wrap gain the second line. A floor that reserved
        // one and not the other would clip on the axis it forgot — the
        // lists running over the next column's tables, or over the next
        // row's names.
        const table = tableWrapping(8);
        const clipped = floorSize([table], 80, false, false, false, false);
        const whole = floorSize([table], 80, false, false, false, true);
        // 400 + 140 + 26 + 34 + 220 + 80 = 900, and 60 px more for the
        // wider column.
        expect(clipped.width).toBe(900);
        expect(whole.width).toBe(900 + (LIST_WIDTH_FULL - LIST_WIDTH));
        // The list is the taller of the two, so the height term is the
        // list alone: 400 + 8 * 29 + 80, against 400 + 8 * 50 + 80.
        expect(clipped.height).toBe(712);
        expect(whole.height).toBe(880);
    });

    test("a table reserves per CHIP, so one long name costs one line and not eight", () => {
        // The whole point of counting chips. A table of eight where a
        // single label wraps stands 21 px taller, where a pitch
        // multiplied by the list charges all eight for that one name —
        // 168 px of room nothing is ever drawn in. Read against both
        // uniform ends, so a formula collapsing to either one fails
        // here.
        const none = floorSize([tableWrapping(0)], 80, false, false, false, true);
        const one = floorSize([tableWrapping(1)], 80, false, false, false, true);
        const every = floorSize([tableWrapping(8)], 80, false, false, false, true);
        expect(one.height - none.height).toBe(LIST_FULL_NAME_LINE_HEIGHT);
        expect(every.height - none.height).toBe(8 * LIST_FULL_NAME_LINE_HEIGHT);
        // 400 + (7 * 29 + 1 * 50) + 80.
        expect(one.height).toBe(733);
        // The column never reads the count: it follows the option.
        expect(one.width).toBe(none.width);
        expect(one.width).toBe(every.width);
    });

    test("an empty seat carries no name, so it reserves one line", () => {
        // A reservation is a table's CAPACITY, not its guests: the list
        // has to still fit once the table fills. A seat nobody sits at
        // holds no label, so it cannot wrap, and a count larger than
        // the table is clamped rather than believed — it reaches this
        // function from a payload.
        expect(floorSize([tableWrapping(3)], 80, false, false, false, true).height).toBe(
            400 + (5 * LIST_LINE_HEIGHT + 3 * (LIST_LINE_HEIGHT + LIST_FULL_NAME_LINE_HEIGHT)) + 80
        );
        expect(floorSize([tableWrapping(99)], 80, false, false, false, true)).toEqual(
            floorSize([tableWrapping(8)], 80, false, false, false, true)
        );
    });

    test("a plan that hides whole names reserves one line however many chips are counted", () => {
        // A clipped chip is one line whatever it carries, so no count
        // may add a pixel here. The gate lives in floorSize rather than
        // at whoever filled the field: a stale payload from a plan that
        // has since turned the option off must not grow the room.
        expect(floorSize([tableWrapping(8)], 80, false, false, false, false)).toEqual(
            floorSize([tableWrapping(0)], 80, false, false, false, false)
        );
    });

    test("the grid spaces its rows per chip too, in step with the floor", () => {
        // The two twins read one plan the same way, or the grid places
        // tables the floor kept no room for. Same option, same tables,
        // one wrapping chip against none.
        const none = gridPositions(4, 8, false, "round", false, false, true, 0);
        const one = gridPositions(4, 8, false, "round", false, false, true, 1);
        const every = gridPositions(4, 8, false, "round", false, false, true, 8);
        // Columns are untouched: the count decides a HEIGHT, and the
        // column follows the option alone.
        expect(one[1][0]).toBe(none[1][0]);
        expect(one[2][1] - none[2][1]).toBe(LIST_FULL_NAME_LINE_HEIGHT);
        expect(every[2][1] - none[2][1]).toBe(8 * LIST_FULL_NAME_LINE_HEIGHT);
    });

    test("showing whole names and companies at once reserves for BOTH lines", () => {
        // A wrapped chip then stands three lines, and the height term
        // has to clear 8 * 68. Reserving for either option alone leaves
        // the list a full line per chip short of what the browser
        // draws.
        const table = {x: 40, y: 40, width: 140, height: 140, seat_count: 8, wrapping_label_count: 8};
        const both = floorSize([table], 80, false, false, true, true);
        expect(both.height).toBe(
            40 + 8 * (LIST_LINE_HEIGHT + LIST_COMPANY_LINE_HEIGHT + LIST_FULL_NAME_LINE_HEIGHT) + 80
        );
        expect(both.height > floorSize([table], 80, false, false, true, false).height).toBe(true);
        expect(both.height > floorSize([table], 80, false, false, false, true).height).toBe(true);
        // The company line is paid by EVERY chip and the name line only
        // by the ones that wrap, so a mixed list under both options
        // still stands between them.
        const mixed = floorSize([{...table, wrapping_label_count: 1}], 80, false, false, true, true);
        expect(mixed.height).toBe(40 + (7 * 47 + 68) + 80);
    });

    test("showing whole names opens the COLUMNS of the grid as well as its rows", () => {
        // Where the company opens rows alone, this one opens both: the
        // grid and the floor read the same two figures, so a plan whose
        // lists grew wider is also spaced further apart sideways.
        // Read as a comparison between the two states rather than
        // against a figure — what must hold is that both steps FOLLOW
        // the option.
        const clipped = gridPositions(4, 8, false, "round", false, false, false, 8);
        const whole = gridPositions(4, 8, false, "round", false, false, true, 8);
        expect(whole[1][0] - clipped[1][0]).toBe(LIST_WIDTH_FULL - LIST_WIDTH);
        expect(whole[2][1] > clipped[2][1]).toBe(true);
        // The second row clears a full list of two-line chips.
        expect(whole[2][1] - whole[0][1] >= 8 * listLinePitch(false, true)).toBe(true);
    });

    test("showing companies opens the rows of the grid it also lengthens the lists of", () => {
        // The grid and the floor read the same pitch, so a plan whose
        // lists grew taller is also spaced further apart: reserving on
        // one side alone is what leaves a row of names on the row
        // below. Read as a comparison between the two states rather
        // than against a figure — what must hold is that the step
        // FOLLOWS the option.
        const plainRows = gridPositions(4, 8, false, "round", false, false);
        const companyRows = gridPositions(4, 8, false, "round", false, true);
        expect(companyRows[2][1] > plainRows[2][1]).toBe(true);
        // The second row clears a full list of two-line chips.
        expect(companyRows[2][1] - companyRows[0][1] >= 8 * listLinePitch(true, false)).toBe(true);
        // Columns are untouched: the company adds no width.
        expect(companyRows[1][0]).toBe(plainRows[1][0]);
    });

    test("assigning seats moves no table of the grid and resizes no floor", () => {
        // The grid's own step no longer reads assign_seats on either
        // axis: the band a fresh grid used to widen its left and top
        // margins by went with the rim labels themselves, and
        // visualTableSize's content term does not read the flag either.
        // Checked as an EQUALITY between the two states rather than
        // against a figure, since what matters is that they cannot
        // diverge.
        expect(gridPositions(3, 8, true, "round", true)).toEqual(gridPositions(3, 8, true, "round", false));
        const tablesOf = (positions) => positions.map(([x, y]) => ({x, y, seat_count: 8, shape: "round"}));
        expect(floorSize(tablesOf(gridPositions(3, 8, true, "round", true)), 80, true, true)).toEqual(
            floorSize(tablesOf(gridPositions(3, 8, true, "round", false)), 80, true, false)
        );
    });
});

describe("visualTableSize", () => {
    // The content term is FIXED at two header lines — the table number
    // and the occupancy count — for every seat count and both
    // assign_seats states, so it is what a growing rim term has to
    // clear before that growth becomes visible on the table itself:
    // hypot(NAME_CHIP_WIDTH, 2 * NAME_LINE_HEIGHT).
    const fixedContentDiameter = Math.hypot(NAME_CHIP_WIDTH, 2 * NAME_LINE_HEIGHT);

    test("a round table's diameter grows with the seat count, one party share at a time", () => {
        // The party term is the only one that grows at every seat
        // count, and on a round table it is the one that binds: 8 seats
        // give 100 + 6 * 10 = 160, 16 give 100 + 14 * 10 = 240. Neither
        // of the two terms that could have driven this comes close —
        // the fixed content diameter is 100.18 at both, and the rim
        // term, which sizes the RING seatPositions places chairs on
        // (circumference rimRequirement) then shrinks back to the
        // table's own diameter by 2 * (SEAT_RADIUS + CHAIR_RING_GAP),
        // asks 224 / PI - 30 =~ 41.30 at 8 seats and 448 / PI - 30 =~
        // 112.60 at 16. Both are read here rather than left implicit: a
        // term that never binds is invisible in the result, and the
        // party term overtaking the rim is exactly what makes a round
        // table keep SEAT_GAP's promise without a corner solver.
        const eight = visualTableSize("round", 8, true);
        const sixteen = visualTableSize("round", 16, true);
        const ringGap = SEAT_RADIUS + CHAIR_RING_GAP;
        const rimDiameter = (seatCount) => (seatCount * (2 * SEAT_RADIUS + SEAT_GAP)) / Math.PI - 2 * ringGap;
        expect(eight.width).toBe(PARTY_BASE_SPAN + 6 * PARTY_SPAN_PER_SEAT);
        expect(sixteen.width).toBe(PARTY_BASE_SPAN + 14 * PARTY_SPAN_PER_SEAT);
        expect(sixteen.width > eight.width).toBe(true);
        expect(rimDiameter(16) < sixteen.width && fixedContentDiameter < sixteen.width).toBe(true);
    });

    test("neither seating mode nor showCompany changes the size, at any seat count", () => {
        // The content term reserves the table's header and nothing else,
        // so neither flag selects anything in the result. Checked as a
        // PROPERTY over every seat count from 2 to 200 and both shapes
        // rather than at one point: this is the whole of what freezing
        // the term at two lines means, and a per-seat term reintroduced
        // on either flag would show up here first.
        for (const shape of ["round", "square"]) {
            for (let seatCount = 2; seatCount <= 200; seatCount++) {
                const assigned = visualTableSize(shape, seatCount, true, false);
                const unassigned = visualTableSize(shape, seatCount, false, false);
                const withCompany = visualTableSize(shape, seatCount, false, true);
                expect(near(assigned.width, unassigned.width) && near(assigned.height, unassigned.height)).toBe(true);
                expect(near(assigned.width, withCompany.width) && near(assigned.height, withCompany.height)).toBe(true);
            }
        }
        // At 8 seats that leaves the party term winning outright, on
        // either flag: the content term would give only 100.18 and the
        // rim term only 41.30.
        expect(visualTableSize("round", 8, false).height).toBe(PARTY_BASE_SPAN + 6 * PARTY_SPAN_PER_SEAT);
    });

    test("a rectangular table keeps RECTANGLE_ASPECT_RATIO between its sides, whichever term binds", () => {
        // Read on BOTH sides of the one crossover a rectangle has, so
        // the ratio is checked against each of the two terms that can
        // drive it rather than against whichever happens to win today.
        // 20 seats: the party term (100 + 18 * 10 = 280 wide, 280 / 1.5
        // tall) is above the rim term's 201.59. 100 seats: the rim
        // term, which asks CORNER_CHORD_PENALTY times the straight-edge
        // span — 100 * 28 * sqrt(2) of ring perimeter, less the ring's
        // own 8 * 15, spread over 2 * (1.5 + 1) — gives 767.96 tall and
        // 1151.94 wide, above the party term's 1080. They cross at 62
        // seats, where 11.879 * seatCount - 36 overtakes
        // 10 * seatCount + 80.
        const party = visualTableSize("square", 20, true);
        expect(party.width).toBe(PARTY_BASE_SPAN + 18 * PARTY_SPAN_PER_SEAT);
        expect(party.height).toBe((PARTY_BASE_SPAN + 18 * PARTY_SPAN_PER_SEAT) / RECTANGLE_ASPECT_RATIO);
        expect(near(party.width / party.height, RECTANGLE_ASPECT_RATIO)).toBe(true);

        const rim = visualTableSize("square", 100, true);
        const rimHeight =
            (100 * (2 * SEAT_RADIUS + SEAT_GAP) * Math.SQRT2 - 8 * (SEAT_RADIUS + CHAIR_RING_GAP)) /
            (2 * (RECTANGLE_ASPECT_RATIO + 1));
        expect(near(rim.height, rimHeight)).toBe(true);
        expect(near(rim.width, RECTANGLE_ASPECT_RATIO * rimHeight)).toBe(true);
        expect(near(rim.width / rim.height, RECTANGLE_ASPECT_RATIO)).toBe(true);
        expect(rim.width > PARTY_BASE_SPAN + 98 * PARTY_SPAN_PER_SEAT).toBe(true);
    });

    test("never shrinks below two chairs' own footprint, on either axis", () => {
        // A reasoning check on the floor itself, not a scenario where it
        // is the one binding term: NAME_CHIP_WIDTH (90) already exceeds
        // it (56) for every shape and seat count with today's constants,
        // so in practice the content term already guarantees this — the
        // floor is a safety net against a future change to that
        // constant, not today's active constraint, and is checked here
        // as its own property for exactly that reason.
        const chairFloor = 2 * (2 * SEAT_RADIUS + SEAT_GAP);
        const round = visualTableSize("round", 2, true);
        const square = visualTableSize("square", 2, true);
        expect(round.width >= chairFloor).toBe(true);
        expect(square.width >= chairFloor && square.height >= chairFloor).toBe(true);
    });

    test("SEAT_GAP is a positive, modest addition to a chair's own span", () => {
        // A sanity check on the constant itself, not the formula: a
        // negative or zero gap would let chairs touch or overlap, and a
        // gap larger than a chair's own span would waste more room on
        // spacing than the chairs themselves need.
        expect(SEAT_GAP > 0 && SEAT_GAP < 2 * SEAT_RADIUS).toBe(true);
    });

    test("CHAIR_RING_GAP is the same offset seatPositions places chairs at", () => {
        // Not a formula check, a WIRING check: this constant only does
        // its job (sizing the ring seatPositions actually uses) if the
        // two never drift apart, which is exactly the mistake this
        // constant replaced — visualTableSize hard-coded a "4" that
        // matched seatPositions' own only by looking at both at once.
        const [seat] = seatPositions("round", 0, 0, 1);
        expect(near(seat.y, -(SEAT_RADIUS + CHAIR_RING_GAP))).toBe(true);
        expect(CHAIR_RING_GAP > 0).toBe(true);
    });

    test("a rectangular table never lets two consecutive chairs, corner included, fall under SEAT_GAP's target", () => {
        // The property widenUntilChairsClearTheCorners exists for,
        // pinned by an assertion rather than left to its own comment:
        // place the REAL chairs seatPositions would draw on the size
        // visualTableSize actually returns, for every seat count from
        // 2 to 200 and both assignSeats states, and check the minimum
        // gap between any two of them — corner pairs included — never
        // falls under the same target the rim term already keeps
        // exactly on a straight edge. 200 covers every crossover this
        // file measures elsewhere and the solver's own worst case (17
        // seats); it is not exhaustive over every seat count a plan
        // could configure, but a table seating more than 200 is not a
        // scenario this module's own indicators (03 §8) target either.
        const target = 2 * SEAT_RADIUS + SEAT_GAP;
        for (const assignSeats of [true, false]) {
            for (let seatCount = 2; seatCount <= 200; seatCount++) {
                const size = visualTableSize("square", seatCount, assignSeats, false);
                const seats = seatPositions("square", size.width, size.height, seatCount);
                let minGap = Infinity;
                for (let k = 0; k < seats.length; k++) {
                    const a = seats[k];
                    const b = seats[(k + 1) % seats.length];
                    const gap = Math.hypot(a.x - b.x, a.y - b.y);
                    if (gap < minGap) {
                        minGap = gap;
                    }
                }
                expect(minGap >= target - 1e-6).toBe(true);
            }
        }
    });

    test("a round table keeps SEAT_GAP's promise too, at every seat count, with no solver of its own", () => {
        // The round branch pays no CORNER_CHORD_PENALTY: a chord is
        // always shorter than its own arc, on any polygon inscribed in
        // a circle, but that shortfall is spread over the whole rim
        // instead of concentrated at four points, and it shrinks toward
        // zero as the ring grows with the seat count. What closes it is
        // the party term: it gives the ring 10 px of diameter per seat
        // — PI * 10 =~ 31.4 px of circumference — against the
        // 2 * SEAT_RADIUS + SEAT_GAP = 28 the rim term asks for, and
        // starts higher besides, so the rim term never binds and every
        // pair clears the target with room to spare. Checked for every
        // seat count from 2 to 200, both assignSeats states, against
        // the chairs seatPositions actually places on the size
        // visualTableSize actually returns. The closest pair over that
        // sweep stands 33.14 px apart, at 200 seats; over 2 to 2000 it
        // is 31.59, at 2000.
        const target = 2 * SEAT_RADIUS + SEAT_GAP;
        for (const assignSeats of [true, false]) {
            for (let seatCount = 2; seatCount <= 200; seatCount++) {
                const size = visualTableSize("round", seatCount, assignSeats, false);
                const seats = seatPositions("round", size.width, size.height, seatCount);
                let minGap = Infinity;
                for (let k = 0; k < seats.length; k++) {
                    const a = seats[k];
                    const b = seats[(k + 1) % seats.length];
                    const gap = Math.hypot(a.x - b.x, a.y - b.y);
                    if (gap < minGap) {
                        minGap = gap;
                    }
                }
                expect(minGap >= target - 1e-6).toBe(true);
            }
        }
    });

    test("neither shape ever draws a smaller table for one more seat", () => {
        // The fixture's own rows carry this property too, on both
        // sides of the twin — but the fixture samples 22 seat counts,
        // and a size that shrinks between two of them it does not
        // sample would go unseen. Swept here over every seat count
        // from 2 to 200 instead, both shapes, both assignSeats states.
        // Every term of visualTableSize is monotone in the seat count,
        // so this holds by construction; it is pinned because the
        // closed form it rests on replaced a solver that grew the
        // table by whole multiplicative passes, whose crossings were
        // not monotone and which therefore drew a rectangular table
        // SMALLER for one more seat, at 46 of the 118 steps below.
        const shrinks = [];
        for (const shape of ["round", "square"]) {
            for (const assignSeats of [true, false]) {
                for (let seatCount = 3; seatCount <= 200; seatCount++) {
                    const smaller = visualTableSize(shape, seatCount - 1, assignSeats, false);
                    const bigger = visualTableSize(shape, seatCount, assignSeats, false);
                    if (bigger.width < smaller.width - 1e-9 || bigger.height < smaller.height - 1e-9) {
                        shrinks.push(`${shape}, assignSeats=${assignSeats}: ${seatCount - 1} -> ${seatCount} seats`);
                    }
                }
            }
        }
        expect(shrinks).toEqual([]);
    });
});

describe("visualTableSize matches its own generated fixture", () => {
    test("every row of visual_table_size_fixture.js is exactly what visualTableSize returns today", () => {
        // The fixture (generate_visual_table_size_fixture.mjs) is
        // frozen output from this very function, read here AND by
        // test_visual_table_size_matches_js.py (Python) — this half
        // of the pair catches an ACCIDENTAL change to visualTableSize
        // itself that nobody regenerated the fixture for; the Python
        // half catches visual_table_size (event_table.py) drifting
        // from the same frozen rows. Neither half alone would notice
        // the two Python and JS functions drifting from EACH OTHER if
        // the fixture were regenerated from the wrong side, which is
        // exactly why it is regenerated from JS only (see its own
        // header) and both sides are checked against it, not against
        // each other directly.
        for (const row of VISUAL_TABLE_SIZE_FIXTURE) {
            const size = visualTableSize(row.shape, row.seatCount, row.assignSeats, row.showCompany);
            expect(near(size.width, row.width)).toBe(true);
            expect(near(size.height, row.height)).toBe(true);
        }
    });

    test("the fixture still covers the whole sweep it was generated for", () => {
        // The row-by-row check above passes just as well on a fixture
        // narrowed to a single seat count: every remaining row still
        // matches, while the crossovers, the corner solver's active
        // range and the large-seat-count tail go unchecked without one
        // test going red. Pinning the fixture's REACH, not only its
        // values, is what makes such a narrowing fail. The twin
        // assertion on the Python side pins the same two figures.
        expect(VISUAL_TABLE_SIZE_FIXTURE.length).toBe(92);
        expect([...new Set(VISUAL_TABLE_SIZE_FIXTURE.map((row) => row.seatCount))].sort((a, b) => a - b)).toEqual([
            2, 4, 8, 10, 11, 12, 14, 15, 16, 17, 20, 25, 30, 45, 50, 51, 52, 60, 100, 200, 500, 1000,
        ]);
    });

    test("no row of the fixture draws a smaller table than the row one seat below it", () => {
        // The two checks above pin AGREEMENT — this half against the
        // other half, and both against frozen rows — never JUSTNESS:
        // a size that shrinks when a seat is added matches just as
        // exactly on both sides, and was certified conforming by both
        // for as long as it stood. This is the missing property, and it
        // is read off the SAME rows: group them by everything that is
        // not the seat count, sort each group by seat count, and check
        // that neither side of the table ever gets shorter from one row
        // to the next. Collected into a list and compared to an empty
        // one rather than asserted pair by pair, so a failure names
        // every offending pair at once instead of stopping at the
        // first. The Python twin runs the same grouping over the same
        // file.
        const series = new Map();
        for (const row of VISUAL_TABLE_SIZE_FIXTURE) {
            const key = `${row.shape}, assignSeats=${row.assignSeats}, showCompany=${row.showCompany}`;
            if (!series.has(key)) {
                series.set(key, []);
            }
            series.get(key).push(row);
        }
        const shrinks = [];
        for (const [key, rows] of series) {
            const sorted = [...rows].sort((a, b) => a.seatCount - b.seatCount);
            for (let k = 1; k < sorted.length; k++) {
                const smaller = sorted[k - 1];
                const bigger = sorted[k];
                if (bigger.width < smaller.width - 1e-9 || bigger.height < smaller.height - 1e-9) {
                    shrinks.push(
                        `${key}: ${smaller.seatCount} seats draw` +
                            ` ${smaller.width.toFixed(2)}x${smaller.height.toFixed(2)}, ${bigger.seatCount} draw` +
                            ` ${bigger.width.toFixed(2)}x${bigger.height.toFixed(2)}`
                    );
                }
            }
        }
        expect(shrinks).toEqual([]);
    });

    test("every reservation row is what listWidth, listWrapsToTwoLines and listLinePitch return", () => {
        // The JavaScript half of the pair the Python twin reads from
        // the same file. Pinning it HERE too is what makes a change to
        // either function fail on its own side: a regenerated fixture
        // that nobody checked against this side would simply record
        // whatever the new formula returns.
        expect(LIST_RESERVATION_FIXTURE.length).toBe(20);
        for (const row of LIST_RESERVATION_FIXTURE) {
            expect(listWidth(row.showFullNames)).toBe(row.width);
            expect(listWrapsToTwoLines(row.showFullNames, row.labelLength)).toBe(row.wrapsToTwoLines);
            expect(listLinePitch(row.showCompany, row.wrapsToTwoLines)).toBe(row.linePitch);
        }
        // The whole input space of the two booleans, so the combination
        // where they COMPOSE cannot be the one left out.
        const pairs = LIST_RESERVATION_FIXTURE.map((row) => `${row.showCompany}/${row.showFullNames}`);
        expect([...new Set(pairs)].sort()).toEqual(["false/false", "false/true", "true/false", "true/true"]);
        // And both label lengths that STRADDLE the threshold, which are
        // the only rows an off-by-one shows up in.
        const labels = new Set(LIST_RESERVATION_FIXTURE.map((row) => row.labelLength));
        expect(labels.has(LIST_FULL_NAME_ONE_LINE_CHARS)).toBe(true);
        expect(labels.has(LIST_FULL_NAME_ONE_LINE_CHARS + 1)).toBe(true);
    });

    test("every reserved-height row is what listReservedHeight returns", () => {
        // The formula a list's whole height comes from, pinned on this
        // side as the Python twin pins it on its own. The rows that
        // matter are the MIXED ones: a formula multiplying one pitch by
        // a whole list matches every unmixed row exactly and gets those
        // wrong by a line per chip.
        expect(LIST_RESERVED_HEIGHT_FIXTURE.length).toBe(18);
        for (const row of LIST_RESERVED_HEIGHT_FIXTURE) {
            expect(listReservedHeight(row.chipCount, row.wrappingChipCount, row.showCompany)).toBe(row.height);
        }
        const mixed = LIST_RESERVED_HEIGHT_FIXTURE.filter(
            (row) => row.wrappingChipCount > 0 && row.wrappingChipCount < row.chipCount
        );
        expect(mixed.length > 0).toBe(true);
        // A mixed list stands strictly between the two uniform ones, so
        // a formula collapsing to either end fails here too.
        for (const row of mixed) {
            expect(listReservedHeight(row.chipCount, 0, row.showCompany) < row.height).toBe(true);
            expect(row.height < listReservedHeight(row.chipCount, row.chipCount, row.showCompany)).toBe(true);
        }
    });
});

describe("findDropTarget", () => {
    // The component feeds this document.elementsFromPoint(); the test feeds
    // it plain objects. Both only ever carry a dataset.
    const chip = (participantId, tableId) => ({
        dataset: {participantId: String(participantId), tableId: String(tableId)},
    });
    const seat = (tableId, number) => ({
        dataset: {seat: String(number), tableId: String(tableId)},
    });
    const surface = (tableId) => ({dataset: {tableId: String(tableId)}});
    const tray = () => ({dataset: {tray: "1"}});
    const nothing = () => ({dataset: {}});

    test("a name chip means a swap", () => {
        expect(findDropTarget([chip(103, 22), surface(22)], 101)).toEqual({
            kind: "participant",
            tableId: 22,
            seat: 0,
            participantId: 103,
        });
    });

    test("the dragged person's own chip is ignored, not treated as a table", () => {
        // Without this, dropping on yourself would read as a move to the
        // table you are already at, and the server call would be pointless.
        expect(findDropTarget([chip(101, 22), surface(22)], 101)).toEqual({
            kind: "table",
            tableId: 22,
            seat: 0,
            participantId: 0,
        });
    });

    test("a seat means a seat number", () => {
        expect(findDropTarget([seat(22, 3), surface(22)], 101)).toEqual({
            kind: "seat",
            tableId: 22,
            seat: 3,
            participantId: 0,
        });
    });

    test("a bare surface means a plain move", () => {
        expect(findDropTarget([surface(22)], 101)).toEqual({
            kind: "table",
            tableId: 22,
            seat: 0,
            participantId: 0,
        });
    });

    test("the tray means leaving the round", () => {
        expect(findDropTarget([tray()], 101)).toEqual({
            kind: "tray",
            tableId: 0,
            seat: 0,
            participantId: 0,
        });
    });

    test("a chip already in the tray still means the tray", () => {
        // Tray chips carry no table: swapping with someone who has no seat
        // would mean nothing.
        expect(findDropTarget([{dataset: {participantId: "104", tray: "1"}}], 101)).toEqual({
            kind: "tray",
            tableId: 0,
            seat: 0,
            participantId: 0,
        });
    });

    test("the first useful candidate wins, the others are skipped", () => {
        expect(findDropTarget([nothing(), nothing(), seat(22, 5), surface(22)], 101)).toEqual({
            kind: "seat",
            tableId: 22,
            seat: 5,
            participantId: 0,
        });
    });

    test("dropping on nothing useful returns null", () => {
        expect(findDropTarget([nothing(), nothing()], 101)).toBe(null);
        expect(findDropTarget([], 101)).toBe(null);
    });
});
