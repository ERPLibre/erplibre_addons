// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {manuallyDispatchProgrammaticEvent, press, queryAll, queryOne} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    mountWithCleanup,
    onRpc,
    patchTranslations,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {focusBlockOf, focusBlocks, focusEndHook} from "@erplibre_studio/editor/studio_editor";

const SHEET = "/form/sheet";
const BOX = "/form/sheet/div";
const TITLE = "/form/sheet/div[2]";
const MAIN = "//group[@name='main']";
const LEFT = "//group[@name='left']";
const RIGHT = "//group[@name='right']";
const NOTEBOOK = "/form/sheet/notebook";
const TRADE = "//page[@name='trade']";
const SALE = "//group[@name='sale']";
const PURCHASE = "//group[@name='purchase']";
const MISC = "//group[@name='misc']";
const NOTES = "//page[@name='notes']";
const CHATTER = "/form/chatter";
const named = (name) => `//field[@name='${name}']`;

// An invented garden supplier model: none of these values exists anywhere else.
const FIELDS = {
    name: {string: "Name", type: "char"},
    street: {string: "Street", type: "char"},
    city: {string: "City", type: "char"},
    phone: {string: "Phone", type: "char"},
    email: {string: "Email", type: "char"},
    seller: {string: "Seller", type: "char"},
    x_sponsor: {string: "Sponsor", type: "char", project: true, pending: true, definition: {}},
    terms: {string: "Terms", type: "char"},
    vendor_terms: {string: "Vendor terms", type: "char"},
    barcode: {string: "Barcode", type: "char"},
    comment: {string: "Notes", type: "text"},
};

const SPONSOR_CHANGE = 1;
const PHONE_CHANGE = 2;

function field(name, extra = {}) {
    return {
        path: named(name),
        tag: "field",
        kind: "field",
        name,
        label: FIELDS[name].string,
        attrs: {},
        movable: true,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
        ...extra,
    };
}

function container(path, tag, label, children, extra = {}) {
    return {
        path,
        tag,
        kind: "container",
        label,
        attrs: {},
        movable: true,
        drop: true,
        children,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
        ...extra,
    };
}

/**
 * A supplier form: the smart buttons, a title, a row of two groups (the
 * phone made required by the draft), a notebook whose first page holds
 * three groups (a new field in « Sales ») and whose second holds the
 * notes; then the chatter.
 */
function formBlocks() {
    const button = {
        path: `${BOX}/button`,
        tag: "button",
        kind: "other",
        label: "Orders",
        attrs: {},
        movable: true,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
    };
    const box = container(BOX, "div", "button_box", [button]);
    const title = container(TITLE, "div", "div", [field("name")]);
    const left = container(LEFT, "group", "left", [field("street"), field("city")]);
    const right = container(RIGHT, "group", "right", [
        field("phone", {changes: [PHONE_CHANGE], change_kinds: ["attribute"], changed: true}),
        field("email"),
    ]);
    const main = container(MAIN, "group", "main", [left, right]);
    const sale = container(
        SALE,
        "group",
        "sale",
        [
            field("seller"),
            field("x_sponsor", {changes: [SPONSOR_CHANGE], change_kinds: ["new"], changed: true}),
            field("terms"),
        ],
        {attrs: {string: "Sales"}}
    );
    const purchase = container(PURCHASE, "group", "purchase", [field("vendor_terms")], {
        attrs: {string: "Purchase"},
    });
    const misc = container(MISC, "group", "misc", [field("barcode")], {attrs: {string: "Misc"}});
    const trade = container(TRADE, "page", "trade", [sale, purchase, misc], {attrs: {string: "Trade"}});
    const notes = container(NOTES, "page", "notes", [field("comment")], {attrs: {string: "Notes"}});
    const notebook = container(NOTEBOOK, "notebook", "notebook", [trade, notes]);
    const sheet = container(SHEET, "sheet", "sheet", [box, title, main, notebook]);
    const chatter = {
        path: CHATTER,
        tag: "chatter",
        kind: "other",
        label: "chatter",
        attrs: {},
        movable: false,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
    };
    return container("/form", "form", "form", [sheet, chatter]);
}

function payload(extra = {}) {
    return {
        model: "x_supplier",
        model_name: "Supplier",
        view_type: "form",
        view: {id: 9, name: "x_supplier.form", xml_id: "studio_garden.x_supplier_form"},
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: [
            "add_field",
            "add_existing_field",
            "move",
            "remove",
            "hide",
            "add_group",
            "add_page",
            "add_separator",
        ],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: FIELDS,
        palette: [{name: "website", string: "Website", type: "char"}],
        field_types: ["char", "integer", "selection", "date"],
        changes: [
            {id: SPONSOR_CHANGE, type: "add_field", kind: "new", path: named("x_sponsor"), summary: "Add Sponsor"},
            {
                id: PHONE_CHANGE,
                type: "set_attribute",
                kind: "attribute",
                path: named("phone"),
                summary: "Phone required",
            },
        ],
        errors: [],
        project: {
            id: 3,
            name: "Garden",
            module_name: "studio_garden",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 2,
            item_count: 2,
            app: false,
            models: [],
            access: [],
            rules: [],
            applied: false,
        },
        projects: [{id: 3, name: "Garden", module_name: "studio_garden", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        ...extra,
    };
}

let answer;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "set_display_level", (args) => args.args[0]);
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        const operation = args.args.at(-1);
        expect.step(`${operation.type} ${operation.target} ${operation.position}`);
        return answer;
    });
});

async function openEditor(viewType = "form") {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(
        customizeAction({resModel: "x_supplier", viewType, viewId: viewType === "form" ? 9 : 7})
    );
    await animationFrame();
}

const FOCUS_BTN = ".o_erplibre_studio_focus_btn";
const FOLDED = ".o_erplibre_studio_folded";
const OPEN = ".o_erplibre_studio_focus_open";
const BAR = ".o_erplibre_studio_focus_bar";
const focusBtn = (path) => `${FOCUS_BTN}[data-focus-path="${path}"]`;
const folded = (path) => `${FOLDED}[data-focus-path="${path}"]`;
// The « Focus » button stays transparent until its block is hovered: a click reaches it all the same.
const clickFocus = (path) => contains(focusBtn(path), {visible: false}).click();
const fieldEl = (name) => `.o_erplibre_studio_field[data-name=${name}]`;
const pick = (name) => `${fieldEl(name)} .o_erplibre_studio_pick`;

describe.current.tags("desktop");
describe("erplibre_studio focus on a block", () => {
    test("focusBlocks: groups of the sheet and of a page, a row as one block, a page of fields", () => {
        // The labels are translated terms: read them in English.
        patchTranslations();
        const root = formBlocks();
        const entries = focusBlocks(root);
        expect(entries.map((e) => [e.path, e.kind, String(e.label), e.pageLabel])).toEqual([
            [MAIN, "group", "General information", ""],
            [SALE, "group", "Sales", "Trade"],
            [PURCHASE, "group", "Purchase", "Trade"],
            [MISC, "group", "Misc", "Trade"],
            [NOTES, "page", "Notes", ""],
        ]);
        // A field finds the focus block that holds it; the chatter, a page of
        // groups and the sheet have none.
        expect(focusBlockOf(root, named("city")).path).toBe(MAIN);
        expect(focusBlockOf(root, named("terms")).path).toBe(SALE);
        expect(focusBlockOf(root, CHATTER)).toBe(null);
        expect(focusBlockOf(root, TRADE)).toBe(null);
        expect(focusBlockOf(root, SHEET)).toBe(null);
        // The end of a row of groups is the end of its last group.
        expect(focusEndHook(entries[0])).toEqual({target: RIGHT, position: "inside"});
        expect(focusEndHook(entries[1])).toEqual({target: SALE, position: "inside"});
        // A second group of the sheet without a string is a « Group ».
        const sheet = root.children[0];
        sheet.children.push(container("//group[@name='extra']", "group", "extra", [], {}));
        expect(String(focusBlocks(root).at(-1).label)).toBe("Group « extra »");
    });

    test("the « Focus » button sits on the title lines of the focus blocks only", async () => {
        await openEditor();
        // The first tab shows: it holds groups only, whose titles carry the button.
        expect(FOCUS_BTN).toHaveCount(4);
        expect(focusBtn(SALE)).toHaveCount(1);
        expect(focusBtn(MISC)).toHaveCount(1);
        expect(focusBtn(TRADE)).toHaveCount(0);
        expect(focusBtn(MAIN)).toHaveCount(1);
        expect(focusBtn(MAIN)).toHaveAttribute("aria-label", "Focus on General information");
        expect(focusBtn(MAIN)).toHaveAttribute("title", "Isolate this block to work in it");
        expect(focusBtn(MAIN)).toHaveText("Focus");
        expect(
            `.o_erplibre_studio_container[data-path="${MAIN}"] > .o_erplibre_studio_container_title > ${FOCUS_BTN}`
        ).toHaveCount(1);
        // The groups of a row are not focus blocks.
        expect(focusBtn(LEFT)).toHaveCount(0);
        // The tab of fields carries it on the head of the notebook once shown.
        await contains(`.o_erplibre_studio_page_tab[data-path="${NOTES}"]`).click();
        expect(FOCUS_BTN).toHaveCount(2);
        expect(`.o_erplibre_studio_notebook_head > ${focusBtn(NOTES)}`).toHaveCount(1);
        expect(focusBtn(NOTES)).toHaveAttribute("aria-label", "Focus on Notes");
        // Never during a drag.
        await manuallyDispatchProgrammaticEvent(queryOne(".o_erplibre_studio_new_field[data-type=date]"), "dragstart");
        await animationFrame();
        expect(FOCUS_BTN).toHaveCount(0);
        await manuallyDispatchProgrammaticEvent(queryOne(".o_erplibre_studio_new_field[data-type=date]"), "dragend");
        await animationFrame();
        expect(FOCUS_BTN).not.toHaveCount(0);
    });

    test("focus: one block open, the others folded to a line, a ring where changes are", async () => {
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${TRADE}"]`).click();
        await clickFocus(PURCHASE);
        // The block in focus, as the full form draws it.
        expect(OPEN).toHaveCount(1);
        expect(OPEN).toHaveAttribute("data-focus-path", PURCHASE);
        expect(`${OPEN} .o_erplibre_studio_field[data-name=vendor_terms]`).toHaveCount(1);
        expect(`${OPEN} .o_erplibre_studio_hook`).not.toHaveCount(0);
        // The others: one line each, a ring and a count where changes are.
        expect(FOLDED).toHaveCount(4);
        expect(folded(MAIN)).toHaveText(/General information\s*· 4 field\(s\)\s*1 change\(s\)/);
        expect(`${folded(MAIN)} .o_erplibre_studio_folded_ring`).toHaveCount(1);
        expect(`${folded(SALE)} .o_erplibre_studio_folded_ring`).toHaveCount(1);
        expect(`${folded(MISC)} .o_erplibre_studio_folded_ring`).toHaveCount(0);
        expect(folded(MISC)).toHaveText(/Misc\s*· 1 field\(s\)/);
        expect(folded(NOTES)).toHaveText(/Tab Notes/);
        expect(folded(MISC)).toHaveAttribute("aria-label", "Focus on Misc, 1 field(s)");
        expect(folded(SALE)).toHaveClass("o_erplibre_studio_focus_indent");
        // The summaries: the smart buttons, the header, the chatter; the page
        // of groups as a context line; no tab drawn.
        expect(".o_erplibre_studio_folded_static").toHaveCount(3);
        expect(`.o_erplibre_studio_folded_static[data-key="${BOX}"]`).toHaveText(/Smart buttons\s*· 1 button\(s\)/);
        expect('.o_erplibre_studio_folded_static[data-key="header"]').toHaveText("Header");
        expect(`.o_erplibre_studio_folded_static[data-key="${CHATTER}"]`).toHaveText(/Chatter\s*· collapsed/);
        // An upper-case caption: innerText follows the CSS.
        expect(".o_erplibre_studio_focus_context").toHaveText(/^tab trade$/i);
        expect(".o_erplibre_studio_page_tab").toHaveCount(0);
        expect(`.o_erplibre_studio_field[data-name=street]`).toHaveCount(0);
        // The bar of the focus, the status bar, no « Focus » button.
        expect(BAR).toHaveCount(1);
        expect(`${BAR} nav`).toHaveAttribute("aria-label", "Path of the block in focus");
        expect(".o_erplibre_studio_focus_crumb").toHaveCount(2);
        expect(".o_erplibre_studio_focus_crumb:eq(1)").toHaveText("Purchase");
        expect(".o_erplibre_studio_focus_crumb:eq(1)").toHaveAttribute("aria-current", "location");
        expect(".o_erplibre_studio_status_focus").toHaveText("Focus: Trade › Purchase");
        expect(FOCUS_BTN).toHaveCount(0);
        // A click on a folded line moves the focus there.
        await contains(folded(MAIN)).click();
        expect(OPEN).toHaveAttribute("data-focus-path", MAIN);
        expect(`${OPEN} .o_erplibre_studio_focus_open_title`).toHaveText("General information");
        expect(`${OPEN} .o_erplibre_studio_container[data-path="${RIGHT}"]`).toHaveCount(1);
        expect(folded(PURCHASE)).toHaveCount(1);
        expect(".o_erplibre_studio_status_focus").toHaveText("Focus: General information");
    });

    test("Escape unselects, then leaves; the full form goes back to the focus", async () => {
        await openEditor();
        await clickFocus(MAIN);
        await contains(fieldEl("city")).click();
        expect(fieldEl("city")).toHaveClass("o_erplibre_studio_selected");
        queryOne(pick("city")).focus();
        await press("Escape");
        await animationFrame();
        expect(fieldEl("city")).not.toHaveClass("o_erplibre_studio_selected");
        expect(BAR).toHaveCount(1);
        await press("Escape");
        await animationFrame();
        expect(BAR).toHaveCount(0);
        expect(FOLDED).toHaveCount(0);
        expect(".o_erplibre_studio_full_bar").toHaveCount(1);
        expect(".o_erplibre_studio_full_back").toHaveText("Back to focus « General information »");
        expect(".o_erplibre_studio_status_focus").toHaveCount(0);
        // Back to the focus, then out through « Leave focus » and the « Form » crumb.
        await contains(".o_erplibre_studio_full_back").click();
        expect(OPEN).toHaveAttribute("data-focus-path", MAIN);
        await contains(".o_erplibre_studio_focus_leave").click();
        expect(BAR).toHaveCount(0);
        await contains(".o_erplibre_studio_full_back").click();
        await contains(".o_erplibre_studio_focus_form").click();
        expect(BAR).toHaveCount(0);
        expect(".o_erplibre_studio_full_bar").toHaveCount(1);
    });

    test("the palette adds after the selected field of the block in focus, else at its end", async () => {
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${TRADE}"]`).click();
        await clickFocus(SALE);
        expect(".o_erplibre_studio_palette_target").toHaveCount(1);
        expect(".o_erplibre_studio_palette_target_block").toHaveText("Sales");
        expect(".o_erplibre_studio_palette_target_where").toHaveText("at the end of the block");
        expect(".o_erplibre_studio_palette_hint").toHaveText(
            "To target another block, click its folded line or use the Plan."
        );
        await contains(".o_erplibre_studio_new_field[data-type=char]").click();
        expect.verifySteps([`add_field ${SALE} inside`]);
        await contains(fieldEl("seller")).click();
        expect(".o_erplibre_studio_palette_target_where").toHaveText("after « Seller »");
        await contains(".o_erplibre_studio_new_field[data-type=char]").click();
        expect.verifySteps([`add_field ${named("x_sponsor")} before`]);
        // A row of groups ends in its last group.
        await contains(folded(MAIN)).click();
        await contains(".o_erplibre_studio_new_field[data-type=integer]").click();
        expect.verifySteps([`add_field ${RIGHT} inside`]);
    });

    test("the Changes list splits around the block in focus; a change elsewhere moves the focus", async () => {
        await openEditor();
        const changesTab = ".o_erplibre_studio_inspector_tab[data-tab=changes]";
        await contains(changesTab).click();
        expect(".o_erplibre_studio_changes_section").toHaveCount(0);
        await clickFocus(MAIN);
        expect(".o_erplibre_studio_changes_section").toHaveCount(2);
        // The titles are upper-case captions: innerText follows the CSS.
        expect('.o_erplibre_studio_changes_section[data-section="in"] h3').toHaveText(
            /^in « general information » · 1$/i
        );
        expect('.o_erplibre_studio_changes_section[data-section="in"] li').toHaveAttribute("data-path", named("phone"));
        expect('.o_erplibre_studio_changes_section[data-section="elsewhere"] h3').toHaveText(
            /^elsewhere in the form · 1$/i
        );
        await contains(
            '.o_erplibre_studio_changes_section[data-section="elsewhere"] .o_erplibre_studio_change_pick'
        ).click();
        expect(OPEN).toHaveAttribute("data-focus-path", SALE);
        expect(fieldEl("x_sponsor")).toHaveClass("o_erplibre_studio_selected");
        await contains(changesTab).click();
        expect('.o_erplibre_studio_changes_section[data-section="in"] h3').toHaveText(/^in « sales » · 1$/i);
    });

    test("the Plan: a row of another block moves the focus; Escape leaves", async () => {
        await openEditor();
        await clickFocus(MAIN);
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        expect(`.o_erplibre_studio_outline_row[data-path="${MAIN}"]`).toHaveClass("o_erplibre_studio_outline_focus");
        await contains(`.o_erplibre_studio_outline_row[data-path="${NOTES}"] .o_erplibre_studio_outline_pick`).click();
        expect(OPEN).toHaveAttribute("data-focus-path", NOTES);
        expect(`${OPEN} .o_erplibre_studio_focus_open_title`).toHaveText("Notes");
        // A reveal of a block no focus block holds turns the focus off.
        const chatterRow = `.o_erplibre_studio_outline_row[data-path="${CHATTER}"] .o_erplibre_studio_outline_pick`;
        await contains(chatterRow).click();
        expect(BAR).toHaveCount(0);
        expect(".o_erplibre_studio_other[data-tag=chatter]").toHaveClass("o_erplibre_studio_selected");
        // From the plan, Escape with nothing selected leaves the focus.
        await contains(".o_erplibre_studio_full_back").click();
        expect(BAR).toHaveCount(1);
        const row = `.o_erplibre_studio_outline_row[data-path="${MAIN}"]`;
        queryOne(row).focus();
        await press("Escape");
        await animationFrame();
        expect(BAR).toHaveCount(0);
    });

    test("the « Focus » button, the folded lines and the bar are tab stops with a name", async () => {
        await openEditor();
        expect(queryOne(focusBtn(MAIN)).tagName).toBe("BUTTON");
        await clickFocus(MAIN);
        for (const el of queryAll(`${FOLDED}, .o_erplibre_studio_focus_leave, .o_erplibre_studio_focus_form`)) {
            expect(el.tagName).toBe("BUTTON");
            expect(el.tabIndex).toBe(0);
        }
        expect(".o_erplibre_studio_focus_leave").toHaveText("Leave focus");
        expect(".o_erplibre_studio_focus_form").toHaveText("Form");
        // The first button of the block in focus takes the keyboard focus.
        await animationFrame();
        await animationFrame();
        expect(`${OPEN} .o_erplibre_studio_pick:first`).toBeFocused();
    });

    test("no focus in a list view", async () => {
        answer = payload({
            view_type: "list",
            view: {id: 7, name: "x_supplier.list", xml_id: "studio_garden.x_supplier_list"},
            blocks: container("/list", "list", "list", [field("name"), field("email")]),
            layout: {root: "/list"},
            hide_mode: "column_invisible",
            changes: [],
        });
        await openEditor("list");
        expect(".o_erplibre_studio_field").not.toHaveCount(0);
        expect(FOCUS_BTN).toHaveCount(0);
        expect(BAR).toHaveCount(0);
        expect(".o_erplibre_studio_full_bar").toHaveCount(0);
        expect(".o_erplibre_studio_palette_target").toHaveCount(0);
    });
});
