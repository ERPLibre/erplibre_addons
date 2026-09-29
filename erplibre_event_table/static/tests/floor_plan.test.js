/** @odoo-module **/
import {describe, expect, test} from "@odoo/hoot";
import {animationFrame, click, drag, queryAll, queryAllTexts, queryOne, select} from "@odoo/hoot-dom";
import {mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {defineMailModels} from "@mail/../tests/mail_test_helpers";
import {EventTableFloorPlan} from "@erplibre_event_table/floor_plan/floor_plan";
import {
    LIST_FULL_NAME_LINE_HEIGHT,
    LIST_FULL_NAME_ONE_LINE_CHARS,
    LIST_WIDTH,
    LIST_WIDTH_FULL,
    floorSize,
    listReservedHeight,
    listWrapsToTwoLines,
} from "@erplibre_event_table/floor_plan/geometry";

// mountWithCleanup raises the backend environment, whose services query the
// mail models. The mock server answers a query for a model nobody declared
// by refusing the whole mount, not just that query, so without this every
// test below ends before its first assertion.
defineMailModels();

const PLAN_ID = 7;
const TABLE_1 = 11;
const TABLE_2 = 22;
const ADA = 101;
const BOB = 102;
const CORA = 103;
const DAN = 104;

// A get_floor_plan_data payload matching the fixture of test_floor_plan_data.py:
// two tables of two seats, four people, two rounds, and the single colleague
// pair sitting at table 1 in round 1.
function makePayload(overrides = {}) {
    return {
        plan: {
            id: PLAN_ID,
            name: "Rotating Tables",
            state: "chosen",
            round_count: 2,
            assign_seats: false,
            participant_count: 4,
            seat_count: 4,
            unseated_count: 0,
            capacity_message: "Participants: 4. Seats: 4. Every seat is taken.",
            sync_message: "",
            can_edit_layout: true,
            can_move_participants: true,
            ...(overrides.plan || {}),
        },
        // An explicit `null` has to survive: folding it into the defaults
        // with `|| {}` would leave no way to describe a plan that carries no
        // combination at all, and the screen state that goes with it.
        combination:
            overrides.combination === null
                ? null
                : {
                      id: 55,
                      name: "Combination 1",
                      rank: 1,
                      is_chosen: true,
                      is_adjusted: false,
                      ...(overrides.combination || {}),
                  },
        tables: overrides.tables || [
            {
                id: TABLE_1,
                number: 1,
                seat_count: 2,
                shape: "round",
                x: 40,
                y: 40,
                width: 140,
                height: 140,
                // How many of this table's chips need a second name
                // line, as the server counts them
                // (_wrapping_label_counts). Zero by default, since the
                // default payload hides whole names; the tests that
                // turn the option on set what their own names give.
                wrapping_label_count: 0,
            },
            {
                id: TABLE_2,
                number: 2,
                seat_count: 2,
                shape: "square",
                x: 360,
                y: 40,
                width: 140,
                height: 140,
                wrapping_label_count: 0,
            },
        ],
        participants: overrides.participants || [
            {id: ADA, name: "Ada Bell", company: "Northwind Tools"},
            {id: BOB, name: "Bob Carr", company: "Northwind Tools"},
            {id: CORA, name: "Cora Dane", company: ""},
            {id: DAN, name: "Dan Evers", company: ""},
        ],
        rounds: overrides.rounds || [
            {
                round: 1,
                seats: [
                    {participant_id: ADA, table_id: TABLE_1, seat: 0},
                    {participant_id: BOB, table_id: TABLE_1, seat: 0},
                    {participant_id: CORA, table_id: TABLE_2, seat: 0},
                    {participant_id: DAN, table_id: TABLE_2, seat: 0},
                ],
                unseated: [],
                conflicts: [
                    {
                        table_id: TABLE_1,
                        company_pairs: 1,
                        repeated_pairs: 0,
                        table_returns: 0,
                    },
                ],
            },
            {
                round: 2,
                seats: [
                    {participant_id: ADA, table_id: TABLE_1, seat: 0},
                    {participant_id: CORA, table_id: TABLE_1, seat: 0},
                    {participant_id: BOB, table_id: TABLE_2, seat: 0},
                    {participant_id: DAN, table_id: TABLE_2, seat: 0},
                ],
                unseated: [],
                conflicts: [],
            },
        ],
        // An explicit `null` survives here too, for the same reason as
        // `combination` above: a plan with nothing measured yet is a state
        // the fixture has to be able to describe.
        indicators:
            overrides.indicators === null
                ? null
                : {
                      company_pairs: 1,
                      repeated_pairs: 0,
                      extra_meetings: 0,
                      max_pair_meetings: 1,
                      table_returns: 2,
                      met_distinct_avg: 2.0,
                      met_distinct_min: 2,
                      lower_bound: 0,
                      is_proven_optimal: false,
                      is_adjusted: false,
                      ...(overrides.indicators || {}),
                  },
    };
}

const PROPS = {resModel: "event.table.plan", resId: PLAN_ID};
// Reads the name, not the whole chip: a chip also holds the "⋮" menu button,
// whose glyph belongs to its textContent and would ride along in every name.
const peopleAt = (tableId) =>
    queryAllTexts(`.o_event_table_block[data-table-id='${tableId}'] .o_event_table_person_name`);

describe("EventTableFloorPlan, reading a plan", () => {
    test("draws one numbered block per table", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(queryAllTexts(".o_event_table_number")).toEqual(["1", "2"]);
    });

    test("lists the people of round 1 beside their table", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(peopleAt(TABLE_1)).toEqual(["1. Ada Bell", "2. Bob Carr"]);
        expect(peopleAt(TABLE_2)).toEqual(["1. Cora Dane", "2. Dan Evers"]);
    });

    test("the round selector redraws without calling the server again", async () => {
        let calls = 0;
        onRpc("event.table.plan", "get_floor_plan_data", () => {
            calls++;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        expect(calls).toBe(1);

        await click(".o_event_table_round_button[data-round='2']");
        await animationFrame();

        // Every round arrives in the same payload: switching is local.
        expect(calls).toBe(1);
        expect(peopleAt(TABLE_1)).toEqual(["1. Ada Bell", "2. Cora Dane"]);
        expect(peopleAt(TABLE_2)).toEqual(["1. Bob Carr", "2. Dan Evers"]);
    });

    test("a conflict badge marks only the table that has one", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_conflict`).toHaveCount(1);
        expect(`.o_event_table_block[data-table-id='${TABLE_2}'] .o_event_table_conflict`).toHaveCount(0);

        await click(".o_event_table_round_button[data-round='2']");
        await animationFrame();
        expect(".o_event_table_conflict").toHaveCount(0);
    });

    test("highlighting a person marks her chip and no other", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await select(String(CORA), {target: ".o_event_table_highlight select"});
        await animationFrame();

        expect(".o_event_table_person.o_event_table_highlighted").toHaveCount(1);
        expect(queryAllTexts(".o_event_table_person.o_event_table_highlighted .o_event_table_person_name")).toEqual([
            "1. Cora Dane",
        ]);

        // The point of the feature: follow one person from round to round.
        // Her number follows the list she is in, so it changes with her
        // place in it — she is second at this table in round 2.
        await click(".o_event_table_round_button[data-round='2']");
        await animationFrame();
        expect(
            queryAllTexts(
                `.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_person.o_event_table_highlighted` +
                    ` .o_event_table_person_name`
            )
        ).toEqual(["2. Cora Dane"]);
    });

    // The test above proves the class is SET; this one proves it PAINTS.
    // floor_plan.scss reaches this browser through web.assets_backend, which
    // web.assets_unit_tests_setup includes, so a rule that stops resolving
    // arrives here as a computed colour and nothing else has to be mocked.
    test("the highlighted chip paints a fill of its own, without resizing", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await select(String(CORA), {target: ".o_event_table_highlight select"});
        await animationFrame();

        // Both people at this table carry no company, so the two chips hold
        // the same number of lines and their boxes are comparable.
        const chipAt = (suffix) =>
            queryOne(`.o_event_table_block[data-table-id='${TABLE_2}'] .o_event_table_person${suffix}`);
        const marked = chipAt(".o_event_table_highlighted");
        const plain = chipAt(":not(.o_event_table_highlighted)");
        const markedStyle = getComputedStyle(marked);
        const plainStyle = getComputedStyle(plain);

        // Read as properties rather than as one pinned colour: the palette
        // belongs to the theme and is recompiled for each colour scheme,
        // while "an opaque fill of its own, and text that answers to it" is
        // what the mark owes the reader whichever scheme is served.
        expect(markedStyle.backgroundColor).not.toBe(plainStyle.backgroundColor);
        // The precise failure this catches: a custom property that resolves
        // to nothing invalidates its whole declaration at computed-value
        // time, and the fill computes to fully transparent — a chip that
        // carries the class and paints nothing. A browser writes an opaque
        // colour as `rgb(…)` and keeps `rgba(…)` only below full alpha.
        expect(markedStyle.backgroundColor).toMatch(/^rgb\(/);
        expect(markedStyle.color).not.toBe(plainStyle.color);
        // The name is a span with a colour of its own, and an explicitly
        // styled descendant never falls back to an ancestor's through
        // inheritance: without the rule handing it `inherit` it keeps that
        // colour on top of the fill.
        expect(getComputedStyle(marked.querySelector(".o_event_table_person_name")).color).toBe(markedStyle.color);

        // The chip is clipped to a fixed width with an ellipsis, and its
        // height is what LIST_LINE_HEIGHT (geometry.js) reserves per line.
        // The mark is drawn with a fill and an outline, neither of which
        // takes part in layout, so neither box may move.
        expect(marked.offsetWidth).toBe(plain.offsetWidth);
        expect(marked.offsetHeight).toBe(plain.offsetHeight);
    });

    test("the reserve carries the same mark as the lists", async () => {
        // Whoever waits in the reserve is the hardest person to find, since
        // no table points at her: the mark has to reach that panel too.
        const EVE = 105;
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {unseated_count: 1, participant_count: 5},
                participants: [
                    {id: ADA, name: "Ada Bell", company: "Northwind Tools"},
                    {id: BOB, name: "Bob Carr", company: "Northwind Tools"},
                    {id: CORA, name: "Cora Dane", company: ""},
                    {id: DAN, name: "Dan Evers", company: ""},
                    {id: EVE, name: "Eve Frank", company: ""},
                ],
                rounds: [
                    {
                        round: 1,
                        seats: [
                            {participant_id: ADA, table_id: TABLE_1, seat: 0},
                            {participant_id: BOB, table_id: TABLE_1, seat: 0},
                            {participant_id: CORA, table_id: TABLE_2, seat: 0},
                            {participant_id: DAN, table_id: TABLE_2, seat: 0},
                        ],
                        unseated: [EVE],
                        conflicts: [],
                    },
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // Someone seated first, to read what the mark looks like at all.
        await select(String(CORA), {target: ".o_event_table_highlight select"});
        await animationFrame();
        const inList = getComputedStyle(
            queryOne(".o_event_table_names .o_event_table_person.o_event_table_highlighted")
        ).backgroundColor;

        // Then the one waiting in the reserve. Nothing about the mark may
        // depend on which of the two panels draws the chip.
        await select(String(EVE), {target: ".o_event_table_highlight select"});
        await animationFrame();
        expect(".o_event_table_names .o_event_table_person.o_event_table_highlighted").toHaveCount(0);
        const inTray = queryOne(".o_event_table_tray .o_event_table_person.o_event_table_highlighted");
        // Both halves are needed: "the same as the list" alone still holds
        // when neither panel paints anything, so the fill is also asked to
        // be an opaque colour of its own.
        expect(getComputedStyle(inTray).backgroundColor).toMatch(/^rgb\(/);
        expect(getComputedStyle(inTray).backgroundColor).toBe(inList);
    });

    test("people without a seat wait in the tray", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {unseated_count: 1, participant_count: 5},
                participants: [
                    {id: ADA, name: "Ada Bell", company: "Northwind Tools"},
                    {id: BOB, name: "Bob Carr", company: "Northwind Tools"},
                    {id: CORA, name: "Cora Dane", company: ""},
                    {id: DAN, name: "Dan Evers", company: ""},
                    {id: 105, name: "Eve Frank", company: ""},
                ],
                rounds: [
                    {
                        round: 1,
                        seats: [
                            {participant_id: ADA, table_id: TABLE_1, seat: 0},
                            {participant_id: BOB, table_id: TABLE_1, seat: 0},
                            {participant_id: CORA, table_id: TABLE_2, seat: 0},
                            {participant_id: DAN, table_id: TABLE_2, seat: 0},
                        ],
                        unseated: [105],
                        conflicts: [],
                    },
                    {
                        round: 2,
                        seats: [],
                        unseated: [105],
                        conflicts: [],
                    },
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(queryAllTexts(".o_event_table_tray .o_event_table_person_name")).toEqual(["Eve Frank"]);
    });

    test("the tray stays on screen when it is empty, so the gesture is findable", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_tray").toHaveCount(1);
        expect(".o_event_table_tray .o_event_table_person").toHaveCount(0);
    });

    test("seats are drawn only when the plan assigns them", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        expect(".o_event_table_seat").toHaveCount(0);
    });

    test("with assigned seats, every seat of every table is drawn", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {assign_seats: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // Two tables of two seats.
        expect(".o_event_table_seat").toHaveCount(4);
    });

    test("every list line is numbered, and without show_company carries nothing else", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // Nobody holds a seat in this payload, so each list numbers its
        // own lines 1..N from its own order. The number is the list's,
        // not show_seat_number's: that option is off here.
        expect(queryAllTexts(".o_event_table_person_name")).toEqual([
            "1. Ada Bell",
            "2. Bob Carr",
            "1. Cora Dane",
            "2. Dan Evers",
        ]);
        expect(".o_event_table_person_company").toHaveCount(0);
    });

    test("with attributed seats the list numbers each line with the seat itself", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {show_seat_number: true, assign_seats: true},
                rounds: [
                    {
                        round: 1,
                        seats: [
                            {participant_id: ADA, table_id: TABLE_1, seat: 1},
                            {participant_id: BOB, table_id: TABLE_1, seat: 2},
                            {participant_id: CORA, table_id: TABLE_2, seat: 1},
                            {participant_id: DAN, table_id: TABLE_2, seat: 2},
                        ],
                        unseated: [],
                        conflicts: [],
                    },
                    {round: 2, seats: [], unseated: [], conflicts: []},
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(queryAllTexts(".o_event_table_person_name")).toEqual([
            "1. Ada Bell",
            "2. Bob Carr",
            "1. Cora Dane",
            "2. Dan Evers",
        ]);
    });

    test("show_company writes the company under the name, only where there is one", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {show_company: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(queryAllTexts(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_person_company`)).toEqual(
            ["Northwind Tools", "Northwind Tools"]
        );
        expect(`.o_event_table_block[data-table-id='${TABLE_2}'] .o_event_table_person_company`).toHaveCount(0);
    });

    test("without show_full_names a list clips its chips to the narrow column", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        const list = queryOne(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_names`);
        // The width namesStyle writes inline IS the one floorSize and
        // _grid_positions reserve: a list drawn wider than the room kept
        // for it runs over the next column's tables.
        expect(list.offsetWidth).toBe(LIST_WIDTH);
        expect(list).not.toHaveClass("o_event_table_names_full");
        // One line, whatever the name's length, and the ellipsis that
        // says it was cut.
        const chip = list.querySelector(".o_event_table_person");
        expect(getComputedStyle(chip).whiteSpace).toBe("nowrap");
        expect(getComputedStyle(chip).textOverflow).toBe("ellipsis");
    });

    test("show_full_names widens the column and lets a chip wrap instead of clipping", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {show_full_names: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        const list = queryOne(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_names`);
        expect(list.offsetWidth).toBe(LIST_WIDTH_FULL);
        expect(list).toHaveClass("o_event_table_names_full");
        const chip = list.querySelector(".o_event_table_person");
        expect(getComputedStyle(chip).whiteSpace).toBe("normal");
        // The clamp rides the NAME, never the chip: a chip carries the
        // company on a block line of its own, and clamping the chip
        // would spend one of the two lines on it.
        // The clamp rides the NAME and needs its own `overflow` to cut
        // anything: the pair is what draws the ellipsis on the second
        // line. The DISPLAY it is written on is deliberately not
        // asserted — an engine is free to report `-webkit-box` under
        // its own normalised name, and the test below reads the
        // rendered outcome instead of the spelling.
        const name = chip.querySelector(".o_event_table_person_name");
        expect(getComputedStyle(name).webkitLineClamp).toBe("2");
        expect(getComputedStyle(name).overflow).toBe("hidden");
    });

    test("the second line a wrapped name takes is the one LIST_FULL_NAME_LINE_HEIGHT reserves", async () => {
        // The measurement this module pays its constants for. A chip is
        // RESERVED at listLinePitch and DRAWN by the browser, and the
        // two agreeing is not something the arithmetic can check: only
        // a rendered chip says what a second name line costs. Read as
        // the DIFFERENCE between a wrapped chip and a chip of one line
        // in the SAME render — the pitch a chip gains by wrapping —
        // rather than as the pitch itself, which also carries the
        // chip's padding, its border and its margin and is
        // LIST_LINE_HEIGHT's own business.
        //
        // The long name needs a second line at the widened column,
        // which holds 41 characters on one, and stays inside the two
        // the clamp allows. The third name is past even those two, and
        // pins that the clamp BOUNDS the chip: a name allowed a third
        // line would draw over the row below, which no reservation
        // covers.
        const LONG = "Cassiopeine Amaryl Fenmarrick-Brentwold Harrowdene";
        const LONGER = LONG + " " + LONG + " " + LONG;
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {show_full_names: true},
                participants: [
                    {id: ADA, name: LONG, company: ""},
                    {id: BOB, name: LONGER, company: ""},
                    {id: CORA, name: "Cora Dane", company: ""},
                    {id: DAN, name: "Dan Evers", company: ""},
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        const pitchOf = (tableId) => {
            const chips = queryAll(`.o_event_table_block[data-table-id='${tableId}'] .o_event_table_person`);
            return chips[1].offsetTop - chips[0].offsetTop;
        };
        // Table 2 carries two names of one line, table 1 a name of two.
        expect(pitchOf(TABLE_1) - pitchOf(TABLE_2)).toBe(LIST_FULL_NAME_LINE_HEIGHT);

        // The clamp stops at two lines whatever the name's length: the
        // name that would take four draws the same height as the one
        // that takes two, and keeps the text it cannot show.
        const names = queryAll(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_person_name`);
        const [two, clamped] = names;
        expect(clamped.offsetHeight).toBe(two.offsetHeight);
        expect(clamped.scrollHeight > clamped.clientHeight).toBe(true);

        // And the reservation reaches the same verdict as the browser
        // did: the predicate answering no on a name the page draws on
        // two lines is the one failure the whole threshold exists to
        // rule out.
        expect(listWrapsToTwoLines(true, `1. ${LONG}`.length)).toBe(true);

        // The bracket embracing a list is drawn at that list's OWN
        // height (listHeight), so it follows the table it is drawn
        // around and not the plan: table 1 wraps its two names and
        // table 2 does not, and the two connectors differ by exactly
        // the two lines that makes.
        const connector = (tableId) =>
            queryOne(`.o_event_table_block[data-table-id='${tableId}'] .o_event_table_connector`).offsetHeight;
        expect(connector(TABLE_1) - connector(TABLE_2)).toBe(2 * LIST_FULL_NAME_LINE_HEIGHT);
    });

    test("a list adds its chips one by one, so one long name among short ones costs one line", async () => {
        // The case the old reservation got wrong, and the only one
        // that tells the two apart: a pitch multiplied by a list
        // charges every chip for the tallest, where a list is a stack
        // of chips each as tall as its own label needs. Table 1
        // carries one wrapping name beside one short, table 2 two
        // short ones, so the drawn lists differ by ONE line and not by
        // two.
        const LONG = "Cassiopeine Amaryl Fenmarrick-Brentwold Harrowdene";
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {show_full_names: true},
                participants: [
                    {id: ADA, name: LONG, company: ""},
                    {id: BOB, name: "Bob Carr", company: ""},
                    {id: CORA, name: "Cora Dane", company: ""},
                    {id: DAN, name: "Dan Evers", company: ""},
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // The bracket is drawn at the list's own height (listHeight),
        // so it is what the drawn sum can be read off.
        const connector = (tableId) =>
            queryOne(`.o_event_table_block[data-table-id='${tableId}'] .o_event_table_connector`).offsetHeight;
        expect(connector(TABLE_1) - connector(TABLE_2)).toBe(LIST_FULL_NAME_LINE_HEIGHT);
        expect(connector(TABLE_1)).toBe(listReservedHeight(2, 1, false));
        expect(connector(TABLE_2)).toBe(listReservedHeight(2, 0, false));
        // The chips themselves say the same: one of the two wrapped.
        const nameHeights = queryAll(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_person_name`).map(
            (name) => name.offsetHeight
        );
        expect(nameHeights[1] - nameHeights[0]).toBe(LIST_FULL_NAME_LINE_HEIGHT);
    });

    test("a label at the threshold draws on ONE line, at the widest glyph the alphabet holds", async () => {
        // What the threshold PROMISES, checked against the browser
        // rather than against the arithmetic that produced it: no label
        // of LIST_FULL_NAME_ONE_LINE_CHARS characters ever reaches a
        // second line, so the reservation that answers "one line" for
        // it is never short.
        //
        // The label tested is the WORST one of that length the app can
        // draw. A list prints "{number}. " before the name, and a
        // one-digit number is the narrowest prefix, so it leaves the
        // most room for wide glyphs; `@` is the widest glyph an ASCII
        // or Latin-1 label can carry. Anything else of the same length
        // is narrower than this.
        const WIDEST = "@";
        const worstName = WIDEST.repeat(LIST_FULL_NAME_ONE_LINE_CHARS - "1. ".length);
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {show_full_names: true},
                participants: [
                    {id: ADA, name: worstName, company: ""},
                    {id: BOB, name: worstName, company: ""},
                    {id: CORA, name: "Cora Dane", company: ""},
                    {id: DAN, name: "Dan Evers", company: ""},
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        const pitchOf = (tableId) => {
            const chips = queryAll(`.o_event_table_block[data-table-id='${tableId}'] .o_event_table_person`);
            return chips[1].offsetTop - chips[0].offsetTop;
        };
        // The label is 18 characters long, so the predicate reserves one
        // line — and the browser draws one, at the very same pitch as
        // the table of short names beside it.
        expect(listWrapsToTwoLines(true, LIST_FULL_NAME_ONE_LINE_CHARS)).toBe(false);
        expect(pitchOf(TABLE_1)).toBe(pitchOf(TABLE_2));
        const [name] = queryAll(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_person_name`);
        expect(name.scrollHeight).toBe(name.clientHeight);
    });

    test("the room reserves each table against its OWN count of wrapping chips", async () => {
        // The wiring the whole reservation rests on: the component has
        // to hand floorSize the counts the server made
        // (_wrapping_label_counts, carried on each table of the
        // payload), or the room and the grid _grid_positions spaces
        // answer one question two ways — the room keeping one line's
        // room for lists the server spaced at two, or the reverse.
        //
        // Eight seats and a table placed far out, so that the figures
        // clear the 600 by 400 floor floorSize never returns less than,
        // which would otherwise swallow the difference.
        const tables = [
            {
                id: TABLE_1,
                number: 1,
                seat_count: 8,
                shape: "round",
                x: 400,
                y: 400,
                width: 140,
                height: 140,
                wrapping_label_count: 1,
            },
            {
                id: TABLE_2,
                number: 2,
                seat_count: 8,
                shape: "square",
                x: 400,
                y: 400,
                width: 140,
                height: 140,
                wrapping_label_count: 0,
            },
        ];
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {show_full_names: true}, tables}));

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(component.roomSize).toEqual(floorSize(tables, 80, false, false, false, true));
        // And the counts are READ, not merely accepted: the same plan
        // with nothing wrapping keeps a shorter room, and the one
        // wrapping chip costs ONE line rather than eight.
        const none = tables.map((table) => ({...table, wrapping_label_count: 0}));
        expect(component.roomSize.height - floorSize(none, 80, false, false, false, true).height).toBe(
            LIST_FULL_NAME_LINE_HEIGHT
        );
    });

    test("visual_tables draws every chair, even without assigned seats", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {visual_tables: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // Two tables of two seats, drawn although assign_seats is false.
        expect(".o_event_table_seat").toHaveCount(4);
        // Without assign_seats a chair carries no seat number, so a drop
        // on it never misreads as a seat request (findDropTarget).
        expect(".o_event_table_seat[data-seat]").toHaveCount(0);
    });

    test("a chair carries no number while the seats are not attributed", async () => {
        // The predicate is visual_tables AND assign_seats. Chairs are
        // drawn in visual mode either way, but numbering one that
        // belongs to nobody would promise a place the plan does not
        // hold.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {visual_tables: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_seat").toHaveCount(4);
        expect(".o_event_table_seat_number").toHaveCount(0);
    });

    test("with the seats attributed every chair shows its own number", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({plan: {visual_tables: true, assign_seats: true}})
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_seat_number").toHaveCount(4);
        expect(queryAllTexts(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_seat_number`)).toEqual([
            "1",
            "2",
        ]);
    });

    test("a chair's number is turned back by exactly its own chair's angle", async () => {
        // seatStyle turns the whole pad, the number included, so every
        // number carries a counter-rotation — and it is the EXACT
        // negation, checked here chair by chair rather than by its sign.
        // A chair on a bottom edge has a negative angle of its own, so
        // its counter-rotation is positive: testing for a minus sign
        // would describe only half the ring, and a threshold on the
        // angle would leave the other half lying on its side.
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({plan: {visual_tables: true, assign_seats: true}})
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        const angleOf = (element) => Number(/rotate\((-?[\d.e-]+)rad\)/.exec(element.getAttribute("style"))[1]);
        const numbers = queryAll(".o_event_table_seat_number");
        expect(numbers.length).toBe(4);
        for (const number of numbers) {
            const chair = number.closest(".o_event_table_seat");
            expect(Math.abs(angleOf(chair) + angleOf(number)) < 1e-9).toBe(true);
        }
    });

    test("the names sit in a list beside the table, in visual mode too", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {visual_tables: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // One list per table, holding the names — never around the
        // table, never inside its surface.
        expect(".o_event_table_names").toHaveCount(2);
        expect(peopleAt(TABLE_1)).toEqual(["1. Ada Bell", "2. Bob Carr"]);
    });

    test("without attributed seats the list reads 1..N in alphabetical order", async () => {
        // This payload hands the table its two people in REVERSE
        // alphabetical order, so a list that merely followed what it
        // was given would read "1. Dan Evers".
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {visual_tables: true},
                rounds: [
                    {
                        round: 1,
                        seats: [
                            {participant_id: DAN, table_id: TABLE_2, seat: 0},
                            {participant_id: CORA, table_id: TABLE_2, seat: 0},
                        ],
                        unseated: [ADA, BOB],
                        conflicts: [],
                    },
                    {round: 2, seats: [], unseated: [], conflicts: []},
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(peopleAt(TABLE_2)).toEqual(["1. Cora Dane", "2. Dan Evers"]);
    });

    test("with attributed seats the list reads in the order the chairs go round", async () => {
        // Seat 2 comes first in the payload: the list has to follow the
        // chairs, not the order it was handed.
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {visual_tables: true, assign_seats: true},
                rounds: [
                    {
                        round: 1,
                        seats: [
                            {participant_id: BOB, table_id: TABLE_1, seat: 2},
                            {participant_id: ADA, table_id: TABLE_1, seat: 1},
                        ],
                        unseated: [CORA, DAN],
                        conflicts: [],
                    },
                    {round: 2, seats: [], unseated: [], conflicts: []},
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(peopleAt(TABLE_1)).toEqual(["1. Ada Bell", "2. Bob Carr"]);
    });

    test("one connector per table, never one per person", async () => {
        // Four people over two tables: a connector drawn per name would
        // give four of them, which is the fan of traits the single
        // grouping trait exists instead of.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {visual_tables: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_person").toHaveCount(4);
        expect(".o_event_table_connector").toHaveCount(2);
        expect(".o_event_table_connector_bracket").toHaveCount(2);
        expect(".o_event_table_connector_trait").toHaveCount(2);
    });

    test("a table nobody sits at draws no connector, having no list to point at", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                rounds: [
                    {
                        round: 1,
                        seats: [{participant_id: ADA, table_id: TABLE_1, seat: 0}],
                        unseated: [BOB, CORA, DAN],
                        conflicts: [],
                    },
                    {round: 2, seats: [], unseated: [], conflicts: []},
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_connector").toHaveCount(1);
    });

    test("every list carries its own table id, so its blank space is a drop target", async () => {
        // Without this attribute a drop on the list's own blank space
        // walks up to the body without meeting a dataset,
        // findDropTarget returns null, and the drop is a silent
        // non-event.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(`.o_event_table_names[data-table-id='${TABLE_1}']`).toHaveCount(1);
        expect(`.o_event_table_names[data-table-id='${TABLE_2}']`).toHaveCount(1);
    });

    test("without visual_tables the list is there just the same", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_names").toHaveCount(2);
        // Chairs are drawn only in visual mode or with assigned seats,
        // so neither a chair nor its number exists here.
        expect(".o_event_table_seat_number").toHaveCount(0);
    });

    test("a plan without tables says what to do next", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {state: "draft", can_move_participants: false},
                tables: [],
                rounds: [],
                combination: null,
                indicators: null,
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_empty").toHaveText("Configure the tables to draw the floor plan.");
        expect(".o_event_table_block").toHaveCount(0);
    });

    test("tables without a combination are drawn, with the panel empty", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {state: "draft", can_move_participants: false},
                rounds: [],
                combination: null,
                indicators: null,
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_block").toHaveCount(2);
        expect(".o_event_table_person").toHaveCount(0);
        expect(".o_event_table_empty").toHaveText("Generate and choose a combination to see who sits where.");
    });

    test("no identifier means no call at all", async () => {
        let calls = 0;
        onRpc("event.table.plan", "get_floor_plan_data", () => {
            calls++;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {
            props: {resModel: "event.table.plan", resId: false},
        });

        expect(calls).toBe(0);
        expect(".o_event_table_empty").toHaveText("Save the record to draw the floor plan.");
    });

    test("a combination form asks the combination, not the plan", async () => {
        let asked = "";
        onRpc("event.table.combination", "get_floor_plan_data", () => {
            asked = "event.table.combination";
            return makePayload({
                plan: {can_move_participants: false},
                combination: {id: 56, rank: 2, is_chosen: false},
            });
        });

        await mountWithCleanup(EventTableFloorPlan, {
            props: {resModel: "event.table.combination", resId: 56},
        });

        expect(asked).toBe("event.table.combination");
        expect(queryAllTexts(".o_event_table_number")).toEqual(["1", "2"]);
    });

    test("a stale reply never overwrites a fresher one", async () => {
        // Without the request counter, an orm call still in flight would put
        // an out-of-date floor back on screen.
        const component = await (async () => {
            onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
            return mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        })();

        const fresh = component.state.requestId;
        component.applyPayload(
            makePayload({tables: []}),
            fresh - 1 // the answer to a request that is no longer the last
        );
        await animationFrame();

        expect(queryAllTexts(".o_event_table_number")).toEqual(["1", "2"]);
    });
});

// Turns the participant mode on. Every ⋮ — a table's and a name's alike —
// exists only inside it: outside, the plan is read-only and no menu is drawn
// to click.
async function enterEditParticipants() {
    await click(".o_event_table_edit_participants");
    await animationFrame();
}

describe("EventTableFloorPlan, moving people", () => {
    test("dropping a chip onto another swaps the two, server-side", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        let call = null;
        onRpc("event.table.plan", "action_move_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        const {drop, moveTo} = await drag(`.o_event_table_person[data-participant-id='${ADA}']`);
        await moveTo(`.o_event_table_person[data-participant-id='${CORA}']`);
        // The core throttles its pointermove handler to an animation frame,
        // and that handler is what arms the drag. Dropping within the same
        // frame sends pointerup before the drag ever starts, so onDrop never
        // runs and no call reaches the server.
        await animationFrame();
        await drop();
        await animationFrame();

        // [planId, round, participantId, tableId], then the keyword part.
        expect(call.args).toEqual([PLAN_ID, 1, ADA, TABLE_2]);
        expect(call.kwargs.swap_participant_id).toBe(CORA);
    });

    test("the drop target list is never empty", async () => {
        // The guard against pe-none coming back. During a drag the core puts
        // pointer-events: none on document.body with an !important utility;
        // without restoring hover on the floor container,
        // document.elementsFromPoint returns nothing useful and every drop
        // becomes a silent non-event.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        onRpc("event.table.plan", "action_move_participant", () => makePayload());

        const component = await mountWithCleanup(EventTableFloorPlan, {
            props: PROPS,
        });
        const {drop, moveTo} = await drag(`.o_event_table_person[data-participant-id='${ADA}']`);
        await moveTo(`.o_event_table_person[data-participant-id='${CORA}']`);
        // The drag arms only on the next animation frame.
        await animationFrame();
        await drop();
        await animationFrame();

        expect(component.lastDropCandidates.length > 0).toBe(true);
    });

    test("dropping on a bare surface is a plain move", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        let call = null;
        onRpc("event.table.plan", "action_move_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        const {drop, moveTo} = await drag(`.o_event_table_person[data-participant-id='${ADA}']`);
        await moveTo(`.o_event_table_surface[data-table-id='${TABLE_2}']`);
        // The drag arms only on the next animation frame.
        await animationFrame();
        await drop();
        await animationFrame();

        expect(call.args).toEqual([PLAN_ID, 1, ADA, TABLE_2]);
        expect(call.kwargs.swap_participant_id).toBe(false);
    });

    test("dropping on the tray takes the person out of the round", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        let call = null;
        onRpc("event.table.plan", "action_unseat_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        const {drop, moveTo} = await drag(`.o_event_table_person[data-participant-id='${ADA}']`);
        await moveTo(".o_event_table_tray");
        // The drag arms only on the next animation frame.
        await animationFrame();
        await drop();
        await animationFrame();

        expect(call.args).toEqual([PLAN_ID, 1, ADA]);
    });

    test("Send to table... moves someone without any dragging", async () => {
        // The path that works with a finger, with a keyboard, and when the
        // two tables are far apart in a large room.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        let call = null;
        onRpc("event.table.plan", "action_move_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();
        await click(`.o_event_table_person[data-participant-id='${ADA}'] .o_event_table_person_menu`);
        await animationFrame();
        await click(`.o_event_table_send_to[data-table-id='${TABLE_2}']`);
        await animationFrame();

        expect(call.args).toEqual([PLAN_ID, 1, ADA, TABLE_2]);
        expect(call.kwargs.swap_participant_id).toBe(false);
    });

    test("the menu lists every table with its occupancy", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();
        await click(`.o_event_table_person[data-participant-id='${ADA}'] .o_event_table_person_menu`);
        await animationFrame();

        expect(queryAllTexts(".o_event_table_send_to")).toEqual(["Table 1 (2 / 2)", "Table 2 (2 / 2)"]);
    });

    test("Remove from this round sends the person to the tray", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        let call = null;
        onRpc("event.table.plan", "action_unseat_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();
        await click(`.o_event_table_person[data-participant-id='${ADA}'] .o_event_table_person_menu`);
        await animationFrame();
        await click(".o_event_table_remove_from_round");
        await animationFrame();

        expect(call.args).toEqual([PLAN_ID, 1, ADA]);
    });

    // Opens one chip's menu and chooses "Send to table…" for `tableId`. A
    // chip is drawn inside a people loop, its menu panel only when it
    // opens, one render later: every place that draws a chip therefore has
    // to be measured for whose identity that later render carries.
    async function sendToTableFrom(chipSelector, tableId) {
        await click(`${chipSelector} .o_event_table_person_menu`);
        await animationFrame();
        await click(`.o_event_table_send_to[data-table-id='${tableId}']`);
        await animationFrame();
    }

    test("a drop onto a table's list moves the person to THAT table", async () => {
        // The list is a drop target for its own table, which is what
        // data-table-id on it buys: a drop anywhere in the column — on
        // a chip or in the blank between them — reaches this table.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        let call = null;
        onRpc("event.table.plan", "action_move_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        const {drop, moveTo} = await drag(`.o_event_table_person[data-participant-id='${ADA}']`);
        await moveTo(`.o_event_table_names[data-table-id='${TABLE_2}']`);
        // The drag arms only on the next animation frame.
        await animationFrame();
        await drop();
        await animationFrame();

        // The destination is what this pins; whether the pointer landed
        // on a chip (a swap) or on blank space (a plain move) decides
        // only the keyword part.
        expect(call.args).toEqual([PLAN_ID, 1, ADA, TABLE_2]);
    });

    test("a list chip's menu in visual mode moves its own person", async () => {
        // Visual mode with assigned seats: the list numbers by seat.
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {visual_tables: true, assign_seats: true},
                rounds: [
                    {
                        round: 1,
                        seats: [
                            {participant_id: ADA, table_id: TABLE_1, seat: 1},
                            {participant_id: BOB, table_id: TABLE_1, seat: 2},
                            {participant_id: CORA, table_id: TABLE_2, seat: 1},
                            {participant_id: DAN, table_id: TABLE_2, seat: 2},
                        ],
                        unseated: [],
                        conflicts: [],
                    },
                    {round: 2, seats: [], unseated: [], conflicts: []},
                ],
            })
        );
        let call = null;
        onRpc("event.table.plan", "action_move_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();
        // Ada is first of her table, so the last name of the loop is not hers.
        const chip = `.o_event_table_names .o_event_table_person[data-participant-id='${ADA}']`;
        await sendToTableFrom(chip, TABLE_2);

        expect(call.args).toEqual([PLAN_ID, 1, ADA, TABLE_2]);
    });

    test("a list chip without assigned seats moves its own person", async () => {
        // Visual mode without assigned seats: the list numbers by its
        // own order instead of by seat, and the chips behave the same.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {visual_tables: true}}));
        let call = null;
        onRpc("event.table.plan", "action_move_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();
        const chip = `.o_event_table_names .o_event_table_person[data-participant-id='${ADA}']`;
        await sendToTableFrom(chip, TABLE_2);

        expect(call.args).toEqual([PLAN_ID, 1, ADA, TABLE_2]);
    });

    test("a tray chip's menu seats its own person", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {unseated_count: 2},
                rounds: [
                    {
                        round: 1,
                        seats: [
                            {participant_id: CORA, table_id: TABLE_1, seat: 0},
                            {participant_id: DAN, table_id: TABLE_2, seat: 0},
                        ],
                        unseated: [ADA, BOB],
                        conflicts: [],
                    },
                    {round: 2, seats: [], unseated: [], conflicts: []},
                ],
            })
        );
        let call = null;
        onRpc("event.table.plan", "action_move_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();
        // The tray sorts by name, so Ada is not the last chip it draws.
        const chip = `.o_event_table_tray .o_event_table_person[data-participant-id='${ADA}']`;
        await sendToTableFrom(chip, TABLE_1);

        expect(call.args).toEqual([PLAN_ID, 1, ADA, TABLE_1]);
    });

    test("a read-only payload offers no move at all", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {can_move_participants: false}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // The mode that would draw the menus is not even offered, so there
        // is no gesture left that could promise a move the server refuses.
        expect(".o_event_table_edit_participants").toHaveCount(0);
        expect(".o_event_table_person_menu").toHaveCount(0);
        expect(".o_event_table_table_menu").toHaveCount(0);
    });

    test("without layout rights the Edit Layout button is absent", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {can_edit_layout: false}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_edit_layout").toHaveCount(0);
    });

    test("editing the layout hides the people menus and shows the grid", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        // The participant mode first, or the menus would already be absent
        // and this would prove nothing about the layout one.
        await enterEditParticipants();
        expect(".o_event_table_person_menu").toHaveCount(4);

        await click(".o_event_table_edit_layout");
        await animationFrame();

        expect(".o_event_table_floor.o_event_table_grid").toHaveCount(1);
        expect(".o_event_table_person_menu").toHaveCount(0);
        // A click inside the surface starts a table drag here, so the table's
        // own menu stands down with the names'.
        expect(".o_event_table_table_menu").toHaveCount(0);
        expect(".o_event_table_handle").toHaveCount(2);
    });

    test("toggling the shape writes it and redraws the table", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());
        let written = null;
        onRpc("event.table", "write", (params) => {
            written = params;
            return true;
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await click(".o_event_table_edit_layout");
        await animationFrame();
        await click(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_shape_toggle`);
        await animationFrame();

        expect(written.args).toEqual([[TABLE_1], {shape: "square"}]);
    });
});

describe("EventTableFloorPlan, fitting the room to its pane", () => {
    // One table placed by hand. floorSize measures the room from a table's
    // own corner outwards, so x and y alone decide whether the room overflows
    // its pane and on WHICH axis — which is what lets each test below bind
    // the fit to a single term and read the result unambiguously.
    const oneTableAt = (x, y) => [
        {id: TABLE_1, number: 1, seat_count: 2, shape: "round", x, y, width: 140, height: 140},
    ];
    const EMPTY_ROUNDS = [
        {round: 1, seats: [], unseated: [ADA, BOB, CORA, DAN], conflicts: []},
        {round: 2, seats: [], unseated: [ADA, BOB, CORA, DAN], conflicts: []},
    ];
    // Well past any pane on one axis, while the other stays at floorSize's
    // own 600 x 400 minimum. Written as offsets rather than as measured
    // sizes so the tests hold at whatever size the runner's window happens
    // to open.
    const WIDE = {tables: oneTableAt(3000, 0), rounds: EMPTY_ROUNDS};
    const TALL = {tables: oneTableAt(0, 3000), rounds: EMPTY_ROUNDS};
    const SMALL = {tables: oneTableAt(0, 0), rounds: EMPTY_ROUNDS};
    const floorPane = () => queryAll(".o_event_table_floor")[0];

    test("a room wider than its pane is scaled down at mount, with no click", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(WIDE));

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await animationFrame();

        // The room stands 3500px wide; no pane is. Before the fit ran at
        // mount this sat at 1 and the user had to reach for the button.
        expect(component.state.zoom < 1).toBe(true);
    });

    test("a room taller than its pane is scaled down too", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(TALL));

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await animationFrame();

        // This room is only 600px wide, floorSize's own minimum. Reading the
        // pane's width proves the width term could not be what bound the
        // fit — a ratio of 1 or more contributes nothing to a minimum capped
        // at 1 — so the height is the only term left that can have.
        expect(floorPane().clientWidth >= 600).toBe(true);
        expect(component.state.zoom < 1).toBe(true);
    });

    test("a room that already fits keeps its native scale", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(SMALL));

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await animationFrame();

        // The fit shrinks an oversized room; it never blows a small one up
        // past the size its own geometry asks for.
        expect(component.state.zoom).toBe(1);
    });

    test("a scale chosen by hand survives a reload of the data", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(WIDE));

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await animationFrame();
        expect(component.state.zoom < 1).toBe(true);

        await click(".o_event_table_zoom_100");
        await animationFrame();
        expect(component.state.zoom).toBe(1);

        // A fresh payload, the way a reload or a move applies one. The room
        // is still far too wide, so an unconditional fit would pull the
        // scale straight back off the value just asked for.
        component.applyPayload(makePayload(WIDE), component.state.requestId);
        await animationFrame();

        expect(component.state.zoom).toBe(1);
    });

    test("no fit runs while the layout is being edited", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(SMALL));

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await animationFrame();
        expect(component.state.zoom).toBe(1);

        await click(".o_event_table_edit_layout");
        await animationFrame();

        // A room far wider than the pane: a fit would drop the scale well
        // below 1. While the layout is being edited it has to hold still,
        // because dropPosition and onResizeMove divide by it to undo the
        // room's transform, and the position they land on is written to the
        // database.
        component.applyPayload(makePayload(WIDE), component.state.requestId);
        await animationFrame();
        expect(component.state.zoom).toBe(1);

        // Leaving edit mode fits the room the tables now occupy: that is why
        // editLayout is a dependency of the effect and not a bare guard.
        await click(".o_event_table_edit_layout");
        await animationFrame();
        expect(component.state.zoom < 1).toBe(true);
    });
});

describe("EventTableFloorPlan, the display buttons", () => {
    // Two people waiting for a place, so a table's menu has something to
    // offer. Ada sorts first, so she is never the last name the tray's loop
    // leaves behind.
    const WITH_TRAY = {
        plan: {unseated_count: 2},
        rounds: [
            {
                round: 1,
                seats: [
                    {participant_id: CORA, table_id: TABLE_1, seat: 0},
                    {participant_id: DAN, table_id: TABLE_2, seat: 0},
                ],
                unseated: [ADA, BOB],
                conflicts: [],
            },
            {round: 2, seats: [], unseated: [], conflicts: []},
        ],
    };

    test("the name lists go and come back with the toggle", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        expect(".o_event_table_names").toHaveCount(2);
        expect(".o_event_table_connector").toHaveCount(2);

        await click(".o_event_table_toggle_names");
        await animationFrame();

        // The lists and the rules pointing at them go; the tables, their
        // numbers and their occupancy stay, which is the whole point of the
        // switch.
        expect(".o_event_table_names").toHaveCount(0);
        expect(".o_event_table_connector").toHaveCount(0);
        expect(queryAllTexts(".o_event_table_number")).toEqual(["1", "2"]);
        expect(queryAllTexts(".o_event_table_occupancy")).toEqual(["2 / 2", "2 / 2"]);

        await click(".o_event_table_toggle_names");
        await animationFrame();
        expect(".o_event_table_names").toHaveCount(2);
        expect(peopleAt(TABLE_1)).toEqual(["1. Ada Bell", "2. Bob Carr"]);
    });

    test("the toggle writes nothing and asks the server nothing", async () => {
        // A display switch local to the component, like the zoom: a call to
        // the server here would make it a stored preference, which it is not.
        let calls = 0;
        onRpc("event.table.plan", "get_floor_plan_data", () => {
            calls++;
            return makePayload();
        });

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await click(".o_event_table_toggle_names");
        await animationFrame();

        expect(calls).toBe(1);
        expect(component.state.showNames).toBe(false);
    });

    test("hiding the lists leaves the room its footprint, and its scale with it", async () => {
        // floorSize reserves the list's width beside every table whatever is
        // drawn there, and its Python twin _grid_positions spaces the tables
        // on that same reservation. A local switch that shrank the floor
        // would put the two out of step: the room would close up while the
        // tables stayed spread for lists nobody draws.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await animationFrame();
        const before = component.floorStyle;
        const zoom = component.state.zoom;

        await click(".o_event_table_toggle_names");
        await animationFrame();

        expect(component.floorStyle).toBe(before);
        expect(component.state.zoom).toBe(zoom);
    });

    test("nothing offers a move until the participant mode is on", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(WITH_TRAY));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_person_menu").toHaveCount(0);
        expect(".o_event_table_table_menu").toHaveCount(0);
    });

    test("the participant mode puts a menu on every table and every name", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(WITH_TRAY));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();

        // One per table, plus one per name: the two seated at their table and
        // the two the tray holds.
        expect(".o_event_table_table_menu").toHaveCount(2);
        expect(".o_event_table_person_menu").toHaveCount(4);

        await click(".o_event_table_edit_participants");
        await animationFrame();
        expect(".o_event_table_table_menu").toHaveCount(0);
        expect(".o_event_table_person_menu").toHaveCount(0);
    });

    test("a table's menu lists the tray and seats someone at THAT table", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(WITH_TRAY));
        let call = null;
        onRpc("event.table.plan", "action_move_participant", (params) => {
            call = params;
            return makePayload();
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();
        // Table 1 is the FIRST of the loop drawing the blocks, so the value
        // that loop leaves behind is table 2: a panel rendered at opening
        // time and reading the loop variable then would seat Ada there.
        await click(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_table_menu`);
        await animationFrame();

        expect(queryAllTexts(".o_event_table_seat_here")).toEqual(["Ada Bell", "Bob Carr"]);

        await click(`.o_event_table_seat_here[data-participant-id='${ADA}']`);
        await animationFrame();

        expect(call.args).toEqual([PLAN_ID, 1, ADA, TABLE_1]);
        expect(call.kwargs.swap_participant_id).toBe(false);
    });

    test("a table's menu says so when nobody is waiting", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await enterEditParticipants();
        await click(`.o_event_table_block[data-table-id='${TABLE_1}'] .o_event_table_table_menu`);
        await animationFrame();

        expect(".o_event_table_seat_here").toHaveCount(0);
        expect(".o_event_table_tray_empty").toHaveCount(1);
    });

    test("auto-arrange asks the server, then reads the plan again", async () => {
        // The method answers nothing of its own, so the new positions reach
        // the screen only through a fresh payload.
        const moved = [
            {id: TABLE_1, number: 1, seat_count: 2, shape: "round", x: 10, y: 20, width: 140, height: 140},
            {id: TABLE_2, number: 2, seat_count: 2, shape: "square", x: 30, y: 40, width: 140, height: 140},
        ];
        let reads = 0;
        onRpc("event.table.plan", "get_floor_plan_data", () => {
            reads++;
            return reads === 1 ? makePayload() : makePayload({tables: moved});
        });
        let call = null;
        onRpc("event.table.plan", "action_rearrange_tables", (params) => {
            call = params;
            return false;
        });

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        expect(queryAll(`.o_event_table_block[data-table-id='${TABLE_1}']`)[0].style.left).toBe("40px");

        await click(".o_event_table_rearrange");
        await animationFrame();

        expect(call.args).toEqual([PLAN_ID]);
        expect(reads).toBe(2);
        expect(queryAll(`.o_event_table_block[data-table-id='${TABLE_1}']`)[0].style.left).toBe("10px");
    });

    test("auto-arrange leaves a scale chosen by hand alone", async () => {
        // The payload it brings back is a fresh one, which is what the
        // automatic fit keys on. That fit still has to stand down in front of
        // a scale the user named, exactly as it does after a move.
        const far = {
            tables: [{id: TABLE_1, number: 1, seat_count: 2, shape: "round", x: 3000, y: 0, width: 140, height: 140}],
            rounds: [
                {round: 1, seats: [], unseated: [ADA, BOB, CORA, DAN], conflicts: []},
                {round: 2, seats: [], unseated: [ADA, BOB, CORA, DAN], conflicts: []},
            ],
        };
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload(far));
        onRpc("event.table.plan", "action_rearrange_tables", () => false);

        const component = await mountWithCleanup(EventTableFloorPlan, {props: PROPS});
        await animationFrame();
        expect(component.state.zoom < 1).toBe(true);

        await click(".o_event_table_zoom_100");
        await animationFrame();
        expect(component.state.zoom).toBe(1);

        await click(".o_event_table_rearrange");
        await animationFrame();
        expect(component.state.zoom).toBe(1);
    });

    test("auto-arrange is offered only where the method exists", async () => {
        // It lives on the plan, and it writes the tables: a combination
        // preview holds no plan id to call it with, and a reader without
        // layout rights would only be shown a refusal.
        onRpc("event.table.combination", "get_floor_plan_data", () =>
            makePayload({plan: {can_move_participants: false}})
        );

        await mountWithCleanup(EventTableFloorPlan, {
            props: {resModel: "event.table.combination", resId: 56},
        });

        expect(".o_event_table_rearrange").toHaveCount(0);
        // The switch that costs nothing stays, even here.
        expect(".o_event_table_toggle_names").toHaveCount(1);
    });

    test("auto-arrange is absent without layout rights", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {can_edit_layout: false}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_rearrange").toHaveCount(0);
    });

    test("each button carries its wording, and a toggle says whether it is pressed", async () => {
        // Icons alone name nothing: the wording is what a pointer reads in
        // the tooltip and what is announced to whoever has none. A toggle
        // owes a third thing, its own state.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        const wordings = {
            o_event_table_toggle_names: "Show the name lists",
            o_event_table_rearrange: "Auto-arrange the tables",
            o_event_table_edit_participants: "Edit participants",
        };
        for (const [className, wording] of Object.entries(wordings)) {
            const button = queryAll(`.${className}`)[0];
            expect(button.getAttribute("title")).toBe(wording);
            expect(button.getAttribute("aria-label")).toBe(wording);
            // The glyph is announced through the label, not twice.
            expect(button.querySelector("i.fa").getAttribute("aria-hidden")).toBe("true");
        }

        expect(".o_event_table_toggle_names[aria-pressed='true']").toHaveCount(1);
        expect(".o_event_table_edit_participants[aria-pressed='false']").toHaveCount(1);
        // The button that writes is not a state, so it claims none.
        expect(queryAll(".o_event_table_rearrange")[0].hasAttribute("aria-pressed")).toBe(false);

        await click(".o_event_table_toggle_names");
        await enterEditParticipants();
        expect(".o_event_table_toggle_names[aria-pressed='false'].active").toHaveCount(0);
        expect(".o_event_table_toggle_names[aria-pressed='false']").toHaveCount(1);
        expect(".o_event_table_edit_participants[aria-pressed='true'].active").toHaveCount(1);
    });
});

// What the plan PAINTS, read from the computed style rather than from the
// classes the tests above check. The two are independent: a rule whose
// colour comes from a custom property the backend never defines is invalid
// at computed-value time and is dropped whole, so the class lands, the
// geometry holds, and the element paints nothing. The exact shape of that
// failure is a background computing to `rgba(0, 0, 0, 0)` and a border
// shorthand to `0px none`, which is what every assertion below refuses.
// A browser writes an opaque colour as `rgb(…)` and keeps `rgba(…)` only
// below full alpha, so the opening of the string is the whole test.
//
// Colours are never pinned to a value here: the palette belongs to the
// colour scheme and is recompiled for each one. What is pinned is what a
// reader is owed either way — an opaque fill, a border with a width, two
// states that differ, and ink that holds its contrast against its own
// ground.
describe("EventTableFloorPlan, what the plan paints", () => {
    // One seat taken and one free at each table, so both states are on
    // screen in the same render and can be compared to each other.
    const seatedPayload = (plan = {}) =>
        makePayload({
            plan: {assign_seats: true, unseated_count: 2, ...plan},
            rounds: [
                {
                    round: 1,
                    seats: [
                        {participant_id: ADA, table_id: TABLE_1, seat: 1},
                        {participant_id: CORA, table_id: TABLE_2, seat: 1},
                    ],
                    unseated: [BOB, DAN],
                    conflicts: [],
                },
            ],
        });

    // The first match, not the only one: the plan draws two tables and
    // four seats, and what is read here is the RULE behind them, which is
    // the same for every element the selector reaches. An absent element
    // is named rather than left to fail as "undefined has no style".
    const styleOf = (selector) => {
        const element = queryAll(selector)[0];
        if (!element) {
            throw new Error(`Nothing matches ${selector} in the rendered plan.`);
        }
        return getComputedStyle(element);
    };
    const FREE_SEAT = ".o_event_table_seat:not(.o_event_table_seat_taken)";
    const TAKEN_SEAT = ".o_event_table_seat.o_event_table_seat_taken";

    // WCAG's relative luminance, then its contrast ratio. Written here
    // rather than taken from the palette: what has to hold is the ratio
    // BETWEEN what the browser finally computed, whichever scheme it
    // computed it from.
    function contrastRatio(first, second) {
        const channels = (colour) =>
            colour
                .match(/[\d.]+/g)
                .slice(0, 3)
                .map(Number);
        const luminance = (colour) => {
            const [r, g, b] = channels(colour).map((value) => {
                const ratio = value / 255;
                return ratio <= 0.03928 ? ratio / 12.92 : ((ratio + 0.055) / 1.055) ** 2.4;
            });
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        const [high, low] = [luminance(first), luminance(second)].sort((a, b) => b - a);
        return (high + 0.05) / (low + 0.05);
    }

    test("the floor, a table, a seat and a chip each paint an opaque fill", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => seatedPayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // Compared as a LIST rather than one assertion per element: a
        // failure then names every selector that paints nothing, instead
        // of stopping at the first and hiding the extent.
        const filled = [
            ".o_event_table_floor",
            ".o_event_table_surface",
            FREE_SEAT,
            TAKEN_SEAT,
            ".o_event_table_names .o_event_table_person",
            ".o_event_table_tray .o_event_table_person",
        ];
        expect(filled.filter((selector) => !styleOf(selector).backgroundColor.startsWith("rgb("))).toEqual([]);

        // The other half of the same failure: a border shorthand carrying
        // an unresolved colour computes to `0px none`, a border that
        // vanishes while the border-radius beside it still applies.
        const bordered = [".o_event_table_floor", ".o_event_table_surface", FREE_SEAT];
        expect(
            bordered.filter((selector) => {
                const style = styleOf(selector);
                return (
                    style.borderTopStyle !== "solid" ||
                    parseFloat(style.borderTopWidth) === 0 ||
                    !style.borderTopColor.startsWith("rgb(")
                );
            })
        ).toEqual([]);

        // A taken seat has to be told apart from a free one at a glance,
        // which is the whole point of drawing it differently.
        expect(styleOf(TAKEN_SEAT).backgroundColor).not.toBe(styleOf(FREE_SEAT).backgroundColor);
        // Each seat state also carries the ink its own number inherits,
        // read here from the seat itself: the number is only ever drawn
        // in visual mode (floor_plan.xml), while the fill under it
        // changes in both modes, so the contrast is checked where it is
        // decided rather than only where it happens to show.
        for (const selector of [FREE_SEAT, TAKEN_SEAT]) {
            const seat = styleOf(selector);
            expect(contrastRatio(seat.color, seat.backgroundColor) >= 4.5).toBe(true);
        }
    });

    test("visual mode lays a grain over the table and fabric over the chairs", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => seatedPayload({visual_tables: true}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        // The wood is a gradient, and a gradient is exactly what an
        // invalid declaration takes away: `background-image` falls back
        // to `none` and the table is left flat.
        const wood = styleOf(".o_event_table_surface.o_event_table_surface_wood");
        expect(wood.backgroundImage).not.toBe("none");
        expect(wood.backgroundImage).toMatch(/gradient/);
        expect(wood.backgroundColor).toMatch(/^rgb\(/);
        expect(wood.borderTopColor).toMatch(/^rgb\(/);
        // The table number is written straight onto that fill, so the
        // surface owes it the contrast WCAG AA asks for body text.
        expect(contrastRatio(wood.color, wood.backgroundColor) >= 4.5).toBe(true);
        expect(styleOf(".o_event_table_surface_wood .o_event_table_number").color).toBe(wood.color);
        expect(styleOf(".o_event_table_surface_wood .o_event_table_occupancy").color).toBe(wood.color);

        const freeChair = styleOf(`.o_event_table_seat_chair:not(.o_event_table_seat_taken)`);
        const takenChair = styleOf(`.o_event_table_seat_chair.o_event_table_seat_taken`);
        expect(freeChair.backgroundColor).toMatch(/^rgb\(/);
        expect(takenChair.backgroundColor).toMatch(/^rgb\(/);
        expect(takenChair.backgroundColor).not.toBe(freeChair.backgroundColor);
        // The pad must also stand apart from the table top it is drawn
        // over, or a chair reads as a hole in the wood.
        expect(freeChair.backgroundColor).not.toBe(wood.backgroundColor);

        // Each pad picks its own ink, and the number takes it by
        // inheritance rather than naming a tone that would answer to
        // only one of the two states.
        for (const [pad, selector] of [
            [freeChair, ".o_event_table_seat_chair:not(.o_event_table_seat_taken)"],
            [takenChair, ".o_event_table_seat_chair.o_event_table_seat_taken"],
        ]) {
            const number = styleOf(`${selector} .o_event_table_seat_number`);
            expect(number.color).toBe(pad.color);
            expect(contrastRatio(number.color, pad.backgroundColor) >= 4.5).toBe(true);
        }
    });

    test("a name reads as ink on its chip, not as a fill borrowed from a button", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => seatedPayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        const chip = styleOf(".o_event_table_names .o_event_table_person");
        const name = styleOf(".o_event_table_names .o_event_table_person_name");
        expect(name.color).toMatch(/^rgb\(/);
        expect(name.color).not.toBe(chip.backgroundColor);
        // $primary is chosen to CARRY white text, so as ink on a pale
        // chip it falls under the 4.5:1 WCAG AA asks for body text in at
        // least one colour scheme. The link colour is chosen as ink.
        expect(contrastRatio(name.color, chip.backgroundColor) >= 4.5).toBe(true);
    });
});

// The badge that tells the two placement modes apart. They look alike on
// screen — people sit at tables in both — so the only thing distinguishing
// a reservation being drafted from a seating already in force is this mark
// and the buttons on the form beside it.
describe("EventTableFloorPlan, the reservation mode", () => {
    test("the badge names the mode and says what a drag will write", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {draws_pins: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_pin_mode").toHaveCount(1);
        // The title is what a reader gets on hover, and it is the only
        // place the consequence of the gesture is spelled out. Odoo
        // extracts `title` for translation on its own, so it carries no
        // _t() and must still be there to be extracted.
        expect(queryOne(".o_event_table_pin_mode").title).toMatch(/reserves/);
    });

    test("a plan running on a seating shows no such badge", async () => {
        // The counter-test: without it the assertion above would pass on a
        // badge that is simply always drawn, which would tell a reader
        // nothing at all.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(".o_event_table_pin_mode").toHaveCount(0);
    });
});

// A list clips every chip to its width and marks the cut with an ellipsis,
// so a long name is the one thing the plan can show a reader without
// letting them read it. The tooltip is what closes that gap, and it has to
// reach BOTH places a chip is drawn — the lists and the reserve — which are
// two call sites of one sub-template and two chances to forget one.
describe("EventTableFloorPlan, reading a name the list had to cut", () => {
    const chipTitle = (selector) => queryOne(selector).title;

    test("a chip in a list carries its whole name as a tooltip", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload());

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(chipTitle(`.o_event_table_names .o_event_table_person[data-participant-id='${ADA}']`)).toBe("Ada Bell");
    });

    test("the tooltip carries the company when the plan shows one", async () => {
        // The company line is clipped by the same width as the name, so it
        // belongs in the tooltip too — but only when it is on screen at
        // all, or the tooltip would state what the plan deliberately hides.
        onRpc("event.table.plan", "get_floor_plan_data", () => makePayload({plan: {show_company: true}}));

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(chipTitle(`.o_event_table_names .o_event_table_person[data-participant-id='${ADA}']`)).toBe(
            "Ada Bell — Northwind Tools"
        );
    });

    test("a chip waiting in the reserve carries one too", async () => {
        onRpc("event.table.plan", "get_floor_plan_data", () =>
            makePayload({
                plan: {unseated_count: 1},
                rounds: [
                    {
                        round: 1,
                        seats: [
                            {participant_id: BOB, table_id: TABLE_1, seat: 0},
                            {participant_id: CORA, table_id: TABLE_2, seat: 0},
                            {participant_id: DAN, table_id: TABLE_2, seat: 0},
                        ],
                        unseated: [ADA],
                        conflicts: [],
                    },
                ],
            })
        );

        await mountWithCleanup(EventTableFloorPlan, {props: PROPS});

        expect(chipTitle(`.o_event_table_tray .o_event_table_person[data-participant-id='${ADA}']`)).toBe("Ada Bell");
    });
});
