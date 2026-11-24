// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryAll, queryOne} from "@odoo/hoot-dom";
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
import {contentName, focusBlocks, outlineRows, simpleLabel} from "@erplibre_studio/editor/studio_editor";

// Readable names at the Simple level: the plan, the folded lines of the
// focus, the « Additions go into » hint, the inspector; « More options »
// closed at each new selection unless the account always shows them.

const WARNING = "//div[@name='warning_code']";
const WARNING_SPAN = "//div[@name='warning_code']/span";
const SHEET = "/form/sheet";
const BOX = "//div[@name='button_box']";
const TITLE = "/form/sheet/div[2]";
const TITLE_H1 = "/form/sheet/div[2]/h1";
const MAIN = "/form/sheet/group";
const LEFT = "/form/sheet/group/group[1]";
const RIGHT = "/form/sheet/group/group[2]";
const LINE = "//span[@name='origin_line']";
const ORIGIN = "//span[@name='origin_line']/span";
const ADDRESS = "/form/sheet/group/group[1]/div";
const NOTEBOOK = "/form/sheet/notebook";
const TRADE = "//page[@name='trade']";
const SALE = "//group[@name='sale']";
const ROW = "//group[@name='container_row_9']";
const NOTES = "//page[@name='notes']";
const NOTE_LABEL = "//page[@name='notes']/label";
const SPACER = "//div[@name='spacer_block']";
const named = (name) => `//field[@name='${name}']`;

// An invented seed catalogue: none of these values exists anywhere else.
const FIELDS = {
    duplicate_id: {string: "Same seed code", type: "many2one", relation: "x_seed"},
    name: {string: "Seed name", type: "char"},
    seed_type: {string: "Seed type", type: "selection"},
    street: {string: "Street", type: "char"},
    city: {string: "City", type: "char"},
    phone: {string: "Phone", type: "char"},
    email: {string: "Email", type: "char"},
    grower: {string: "Grower", type: "char"},
    terms: {string: "Terms", type: "char"},
    vendor_terms: {string: "Vendor terms", type: "char"},
    barcode: {string: "Barcode", type: "char"},
    comment: {string: "Notes", type: "text"},
};

function node(path, tag, kind, label, extra = {}) {
    return {
        path,
        tag,
        kind,
        label,
        attrs: {},
        movable: true,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
        ...extra,
    };
}

function field(name, extra = {}) {
    return node(named(name), "field", "field", FIELDS[name].string, {name, ...extra});
}

function container(path, tag, label, children, extra = {}) {
    return node(path, tag, "container", label, {drop: true, children, ...extra});
}

/**
 * A seed form: a warning above the sheet; in the sheet the smart buttons, a
 * title, a main group of two groups (the first one holds a label line and
 * an address block), a notebook whose first page holds a group with a
 * « string » and a row without one, whose second page holds a field, the
 * label of a field and an empty block.
 */
function formBlocks() {
    const warning = container(
        WARNING,
        "div",
        "warning_code",
        [container(WARNING_SPAN, "span", "span", [field("duplicate_id")])],
        {attrs: {name: "warning_code"}}
    );
    const orders = node(`${BOX}/button`, "button", "other", "Orders", {attrs: {string: "Orders"}});
    const box = container(BOX, "div", "button_box", [orders], {attrs: {name: "button_box"}});
    const title = container(TITLE, "div", "div", [container(TITLE_H1, "h1", "h1", [field("name")])]);
    const line = container(LINE, "span", "origin_line", [field("seed_type"), node(ORIGIN, "span", "other", "Origin")], {
        attrs: {name: "origin_line"},
    });
    const address = container(ADDRESS, "div", "div", [field("street"), field("city")]);
    const left = container(LEFT, "group", "group", [line, address]);
    const right = container(RIGHT, "group", "group", [
        field("phone", {attrs: {widget: "phone"}}),
        field("email", {attrs: {widget: "email"}}),
    ]);
    const main = container(MAIN, "group", "group", [left, right]);
    const sale = container(SALE, "group", "Sales", [field("grower")], {attrs: {name: "sale", string: "Sales"}});
    const row = container(ROW, "group", "container_row_9", [field("terms"), field("vendor_terms"), field("barcode")], {
        attrs: {name: "container_row_9"},
    });
    const trade = container(TRADE, "page", "Trade", [sale, row], {attrs: {name: "trade", string: "Trade"}});
    const notes = container(
        NOTES,
        "page",
        "Notes",
        [
            field("comment"),
            node(NOTE_LABEL, "label", "other", "email"),
            node(SPACER, "div", "other", "spacer_block", {attrs: {name: "spacer_block"}}),
        ],
        {attrs: {name: "notes", string: "Notes"}}
    );
    const notebook = container(NOTEBOOK, "notebook", "notebook", [trade, notes]);
    const sheet = container(SHEET, "sheet", "sheet", [box, title, main, notebook]);
    return container("/form", "form", "form", [warning, sheet]);
}

function payload(extra = {}) {
    return {
        model: "x_seed",
        model_name: "Seed",
        view_type: "form",
        view: {id: 9, name: "x_seed.form", xml_id: "studio_seeds.x_seed_form"},
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "hide", "add_group", "add_page"],
        hide_mode: "invisible",
        settable: {field: {widget: "widget"}},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: FIELDS,
        palette: [],
        field_types: ["char", "integer"],
        changes: [],
        errors: [],
        project: {
            id: 3,
            name: "Seeds",
            module_name: "studio_seeds",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 0,
            item_count: 0,
            app: false,
            models: [],
            access: [],
            rules: [],
            applied: false,
        },
        projects: [{id: 3, name: "Seeds", module_name: "studio_seeds", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        display_level: "simple",
        ...extra,
    };
}

let answer;
let alwaysCalls;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    alwaysCalls = [];
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "set_display_level", (args) => args.args[0]);
    onRpc("erplibre.studio.editor", "set_always_more_options", (args) => {
        alwaysCalls.push(args.args[0]);
        return args.args[0];
    });
    onRpc("erplibre.studio.editor", "get_studio_choices", () => ({
        groups: [],
        menus: [],
        apps: [],
        models: [],
        taken_models: [],
        icons: [],
    }));
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "x_seed", viewType: "form", viewId: 9}));
    await animationFrame();
}

const SIMPLE = ".o_erplibre_studio_level_option[data-level=simple]";
const DETAILED = ".o_erplibre_studio_level_option[data-level=detailed]";
const TOGGLE = ".o_erplibre_studio_field_advanced_toggle";
const ALWAYS = ".o_erplibre_studio_more_always_input";
const row = (path) => `.o_erplibre_studio_outline_row[data-path="${path}"]`;
const folded = (path) => `.o_erplibre_studio_folded[data-focus-path="${path}"]`;
const pick = (name) => `.o_erplibre_studio_field[data-name=${name}] .o_erplibre_studio_pick`;

/** The rows of the plan on screen: [label, depth]. */
function planRows() {
    return queryAll(".o_erplibre_studio_outline_row").map((el) => [
        el.querySelector(".o_erplibre_studio_outline_label").textContent.trim(),
        Number(el.getAttribute("aria-level")) - 1,
    ]);
}

describe.current.tags("desktop");
describe("erplibre_studio readable names at the Simple level", () => {
    test("simpleLabel and contentName: what a reader sees, never a technical name", () => {
        patchTranslations();
        const root = formBlocks();
        const find = (path) => {
            const walk = (block) =>
                block.path === path ? block : (block.children || []).map(walk).find(Boolean) || null;
            return walk(root);
        };
        const label = (path) => String(simpleLabel(find(path), FIELDS));
        expect(label(MAIN)).toBe("Group: Seed type, Street…");
        expect(label(RIGHT)).toBe("Group: Phone, Email");
        expect(label(ROW)).toBe("Group: Terms, Vendor terms…");
        expect(label(SALE)).toBe("Group « Sales »");
        expect(label(BOX)).toBe("Smart buttons");
        expect(label(`${BOX}/button`)).toBe("Orders");
        expect(label(ORIGIN)).toBe("Origin");
        // A label without « string » shows the label of its field.
        expect(label(NOTE_LABEL)).toBe("Email");
        // An element whose only text is its technical name has none.
        expect(label(SPACER)).toBe("");
        expect(label(LINE)).toBe("Block: Seed type");
        expect(String(contentName(container("/x", "group", "g", [])))).toBe("Group");
        expect(String(contentName(find(NOTES)))).toBe("Tab: Notes");
    });

    test("outlineRows: Simple flattens the layout-only elements of a form, Detailed keeps them", () => {
        patchTranslations();
        const root = formBlocks();
        const simple = outlineRows(root, {simple: true, flatten: true, fields: FIELDS});
        const shown = simple.rows.map((r) => [String(simpleLabel(r.block, FIELDS)), r.depth]);
        expect(shown).toEqual([
            ["Same seed code", 0],
            ["Sheet", 0],
            ["Smart buttons", 1],
            ["Orders", 2],
            ["Seed name", 1],
            ["Group: Seed type, Street…", 1],
            ["Group: Seed type, Street…", 2],
            ["Seed type", 3],
            ["Origin", 3],
            ["Street", 3],
            ["City", 3],
            ["Group: Phone, Email", 2],
            ["Phone", 3],
            ["Email", 3],
            ["Tabs", 1],
            ["Trade", 2],
            ["Group « Sales »", 3],
            ["Grower", 4],
            ["Group: Terms, Vendor terms…", 3],
            ["Terms", 4],
            ["Vendor terms", 4],
            ["Barcode", 4],
            ["Notes", 2],
            ["Notes", 3],
            ["Email", 3],
        ]);
        expect(simple.total).toBe(shown.length);
        // A filter finds a field through the elements that have no row.
        const city = outlineRows(root, {simple: true, flatten: true, fields: FIELDS, filter: "city"});
        expect(city.rows.map((r) => r.block.path)).toEqual([SHEET, MAIN, LEFT, named("city")]);
        expect(city.matches).toBe(1);
        // A technical name still finds its block.
        expect(outlineRows(root, {simple: true, flatten: true, filter: "vendor_terms"}).matches).toBe(1);
        // A layout element the draft changes keeps its row.
        const changed = formBlocks();
        changed.children[1].children[1].changed = true;
        const kept = outlineRows(changed, {simple: true, flatten: true, fields: FIELDS});
        expect(kept.rows.map((r) => r.block.path)).toInclude(TITLE);
        // Detailed: every element, the technical names.
        const detailed = outlineRows(root);
        expect(detailed.rows.map((r) => r.block.path)).toInclude(WARNING_SPAN);
        expect(detailed.rows.map((r) => r.block.path)).toInclude(SPACER);
        expect(detailed.total).toBe(32);
    });

    test("focusBlocks: a group without « string » named from its fields at Simple", () => {
        patchTranslations();
        const labels = (simple) => focusBlocks(formBlocks(), {simple}).map((e) => String(e.label));
        expect(labels(true)).toEqual(["General information", "Sales", "Group: Terms, Vendor terms…", "Notes"]);
        expect(labels(false)).toEqual(["General information", "Sales", "Group « container_row_9 »", "Notes"]);
    });

    test("the plan at Simple: what a user sees; Detailed gives the technical names back", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        const rows = planRows();
        const labels = rows.map(([label]) => label);
        for (const technical of ["warning_code", "button_box", "container_row_9", "origin_line", "spacer_block"]) {
            expect(labels.some((label) => label.includes(technical))).toBe(false, {message: technical});
        }
        expect(labels).not.toInclude("div");
        expect(labels).not.toInclude("h1");
        expect(labels).not.toInclude("span");
        expect(rows).toInclude(["Same seed code", 0]);
        expect(rows).toInclude(["Seed name", 1]);
        expect(rows).toInclude(["Smart buttons", 1]);
        expect(rows).toInclude(["Group: Terms, Vendor terms…", 3]);
        expect(".o_erplibre_studio_outline_count").toHaveText("25 item(s)");
        expect(`${row(ROW)} .o_erplibre_studio_outline_toggle`).toHaveAttribute(
            "aria-label",
            "Collapse Group: Terms, Vendor terms…"
        );
        // Detailed: the layout elements and their technical names.
        await contains(DETAILED).click();
        expect(row(TITLE_H1)).toHaveCount(1);
        expect(`${row(ROW)} .o_erplibre_studio_outline_label`).toHaveText("Group « container_row_9 »");
        expect(`${row(BOX)} .o_erplibre_studio_outline_label`).toHaveText("button_box");
        expect(".o_erplibre_studio_outline_count").toHaveText("32 item(s)");
        // The path of the selection: the technical names at Detailed, the
        // readable names without the layout elements at Simple.
        await contains(pick("street")).click();
        const crumbs = () => queryAll(".o_erplibre_studio_crumb").map((el) => el.textContent.trim());
        expect(crumbs()).toEqual(["Sheet", "Group", "Group", "div", "Street"]);
        await contains(SIMPLE).click();
        expect(crumbs()).toEqual(["Sheet", "Group: Seed type, Street…", "Group: Seed type, Street…", "Street"]);
    });

    test("the folded lines of the focus and the « Additions go into » hint name a group from its fields", async () => {
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${TRADE}"]`).click();
        await contains(`.o_erplibre_studio_focus_btn[data-focus-path="${SALE}"]`, {visible: false}).click();
        expect(`${folded(ROW)} .o_erplibre_studio_folded_label`).toHaveText("Group: Terms, Vendor terms…");
        expect(folded(ROW)).toHaveAttribute("aria-label", /^Focus on Group: Terms, Vendor terms…, 3 field\(s\)/);
        await contains(folded(ROW)).click();
        expect(".o_erplibre_studio_palette_target_block").toHaveText("Group: Terms, Vendor terms…");
        expect(".o_erplibre_studio_status_focus").toHaveText("Focus: Trade › Group: Terms, Vendor terms…");
        await contains(pick("terms")).click();
        expect(".o_erplibre_studio_palette_target_where").toHaveText("after « Terms »");
        // Detailed: the technical name of the group.
        await contains(DETAILED).click();
        expect(".o_erplibre_studio_palette_target_block").toHaveText("Group « container_row_9 »");
        expect(`${folded(SALE)} .o_erplibre_studio_folded_label`).toHaveText("Sales");
        await contains(SIMPLE).click();
        expect(".o_erplibre_studio_palette_target_block").toHaveText("Group: Terms, Vendor terms…");
    });

    test("More options start closed at each new selection, unless always shown for the account", async () => {
        await openEditor();
        // A field with a widget: closed all the same.
        await contains(pick("phone")).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "false");
        expect(".o_erplibre_studio_field_advanced").toHaveCount(0);
        expect(ALWAYS).toHaveCount(0);
        await contains(TOGGLE).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "true");
        expect(ALWAYS).not.toBeChecked();
        expect(".o_erplibre_studio_more_always").toHaveText("Always show these options");
        // Another selection, then the first one again: closed each time.
        await contains(pick("email")).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "false");
        await contains(pick("phone")).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "false");
        // The choice of the account: open on every selection.
        await contains(TOGGLE).click();
        await contains(ALWAYS).check();
        expect(alwaysCalls).toEqual([true]);
        expect(TOGGLE).toHaveAttribute("aria-expanded", "true");
        await contains(pick("email")).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "true");
        expect(ALWAYS).toBeChecked();
        // Folded by hand on that field only.
        await contains(TOGGLE).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "false");
        await contains(pick("street")).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "true");
        // Unticked: the field on screen stays open, the next one is closed.
        await contains(ALWAYS).uncheck();
        expect(alwaysCalls).toEqual([true, false]);
        expect(TOGGLE).toHaveAttribute("aria-expanded", "true");
        await contains(pick("city")).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "false");
    });

    test("the payload gives the choice of the account; the checkbox is keyboard reachable", async () => {
        answer = payload({always_more_options: true});
        await openEditor();
        await contains(pick("phone")).click();
        expect(TOGGLE).toHaveAttribute("aria-expanded", "true");
        expect(ALWAYS).toBeChecked();
        expect(queryOne(ALWAYS).tagName).toBe("INPUT");
        expect(ALWAYS).not.toHaveAttribute("tabindex");
        // The Detailed level always shows them: neither toggle nor choice.
        await contains(DETAILED).click();
        expect(TOGGLE).toHaveCount(0);
        expect(ALWAYS).toHaveCount(0);
    });
});
