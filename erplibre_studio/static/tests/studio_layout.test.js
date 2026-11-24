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
import {columnName, pairRole} from "@erplibre_studio/editor/studio_editor";

// The form canvas lays a group out as the web client does (rule 1): a
// label cell and the block after it share a line, an address draws its
// parts in the value column, the picture floats at the right of the
// title. Its groups are named by their place, at both levels; the plan
// at Simple lists what the canvas draws.

const SHEET = "/form/sheet";
const WARNING = "/form/div[@name='warning']";
const TITLE = "/form/sheet/div[@name='title']";
const MAIN = "/form/sheet/group";
const LEFT = "/form/sheet/group/group[1]";
const RIGHT = "/form/sheet/group/group[2]";
const LABEL = "//span[@name='address_label']";
const LABEL_TEXT = "//span[@name='address_label']/span";
const ADDRESS = "//div[@name='address_block']";
const named = (name) => `//field[@name='${name}']`;

// An invented grower directory: none of these values exists anywhere else.
const FIELDS = {
    name: {string: "Grower name", type: "char"},
    is_farm: {string: "Is a farm", type: "boolean"},
    kind: {
        string: "Grower kind",
        type: "selection",
        selection: [
            ["person", "Person"],
            ["farm", "Farm"],
        ],
    },
    photo: {string: "Photo", type: "binary"},
    twin_id: {string: "Twin grower", type: "many2one", relation: "x.grower"},
    role: {string: "Role", type: "char"},
    street: {string: "Street", type: "char"},
    city: {string: "City", type: "char"},
    zip: {string: "Zip", type: "char"},
    email: {string: "Email", type: "char"},
    phone: {string: "Phone", type: "char"},
};

function node(path, tag, kind, label, attrs = {}, extra = {}) {
    return {
        path,
        tag,
        kind,
        label,
        attrs,
        movable: true,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
        ...extra,
    };
}

function field(name, attrs = {}, extra = {}) {
    return node(named(name), "field", "field", FIELDS[name].string, attrs, {name, ...extra});
}

function container(path, tag, label, children, attrs = {}, extra = {}) {
    return node(path, tag, "container", label, attrs, {drop: true, children, ...extra});
}

/**
 * A grower form: a warning above the sheet shown for a twin; in the sheet
 * a photo, a radio and a title; two columns, the left one with a label
 * cell (its text for a farm, a role for a person) and an address of three
 * parts, then an email; the right one with a phone.
 */
function formBlocks() {
    const warning = container(WARNING, "div", "warning", [field("twin_id")], {
        name: "warning",
        invisible: "not twin_id",
    });
    const title = container(TITLE, "div", "title", [container(`${TITLE}/h1`, "h1", "h1", [field("name")])], {
        name: "title",
    });
    const label = container(
        LABEL,
        "span",
        "address_label",
        [
            field("role", {invisible: "is_farm"}),
            node(LABEL_TEXT, "span", "other", "Address", {invisible: "not is_farm"}),
        ],
        {name: "address_label", class: "o_form_label o_td_label"}
    );
    const address = container(
        ADDRESS,
        "div",
        "address_block",
        [
            field("street", {class: "o_address_street", placeholder: "Street..."}),
            field("city", {class: "o_address_city", placeholder: "City"}),
            field("zip", {class: "o_address_zip", placeholder: "Zip"}),
        ],
        {name: "address_block", class: "o_address_format"}
    );
    const left = container(LEFT, "group", "group", [label, address, field("email")], {}, {column: 1, columns: 2});
    const right = container(RIGHT, "group", "group", [field("phone")], {}, {column: 2, columns: 2});
    const main = container(MAIN, "group", "group", [left, right]);
    const sheet = container(SHEET, "sheet", "sheet", [
        field("photo", {widget: "image", class: "oe_avatar"}),
        field("kind", {widget: "radio"}),
        title,
        main,
    ]);
    return container("/form", "form", "form", [warning, sheet]);
}

function payload(extra = {}) {
    return {
        model: "x.grower",
        model_name: "Grower",
        view_type: "form",
        view: {id: 9, name: "x.grower.form", xml_id: "studio_growers.x_grower_form"},
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "hide", "relabel", "add_page"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: FIELDS,
        palette: [],
        field_types: ["char", "integer", "selection"],
        changes: [],
        errors: [],
        project: {
            id: 3,
            name: "Growers",
            module_name: "studio_growers",
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
        projects: [{id: 3, name: "Growers", module_name: "studio_growers", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: 4,
        sample_values: {
            name: "Quillfern Acres",
            kind: "Farm",
            street: "8 Lantern Furrow",
            city: "Brindlemoor",
            zip: "Q7Z 0X0",
            email: "barn.office@quillfern.example",
            phone: "+1 555 0142",
            is_farm: true,
        },
        sample_record: {is_farm: true, twin_id: false, kind: "farm"},
        display_level: "simple",
        ...extra,
    };
}

beforeEach(() => {
    defineWebModels();
    onRpc("erplibre.studio.editor", "get_editor_data", () => payload());
    onRpc("erplibre.studio.editor", "set_display_level", (args) => args.args[0]);
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "x.grower", viewType: "form", viewId: 9}));
    await animationFrame();
}

const DETAILED = ".o_erplibre_studio_level_option[data-level=detailed]";
const at = (path) => `.o_erplibre_studio_canvas [data-path="${path}"]`;
const line = (name) => `.o_erplibre_studio_canvas .o_erplibre_studio_field[data-name=${name}]`;
const box = (selector) => queryOne(selector).getBoundingClientRect();
const row = (path) => `.o_erplibre_studio_outline_row[data-path="${path}"]`;
const PLUS = ".o_erplibre_studio_insert";
const plusOf = (target, position) => `${PLUS}[data-hook="${`:${position}:${target}`.replace(/"/g, '\\"')}"]`;

/** The rows of the plan on screen: [label, depth]. */
function planRows() {
    return queryAll(".o_erplibre_studio_outline_row").map((el) => [
        el.querySelector(".o_erplibre_studio_outline_label").textContent.trim(),
        Number(el.getAttribute("aria-level")) - 1,
    ]);
}

describe.current.tags("desktop");
describe("erplibre_studio form layout and names by place", () => {
    test("pairRole and columnName: the line of a label cell, the name of a column", () => {
        patchTranslations();
        const root = formBlocks();
        const left = root.children[1].children[3].children[0];
        const [label, address, email] = left.children;
        expect(pairRole(left, label)).toBe("label");
        expect(pairRole(left, address)).toBe("value");
        expect(pairRole(left, email)).toBe("");
        // A field with its own label starts a line; without, it is the value.
        const after = {...email, path: "/x"};
        const group = {...left, children: [label, after]};
        expect(pairRole(group, after)).toBe("");
        after.attrs = {nolabel: "1"};
        expect(pairRole(group, after)).toBe("value");
        // A group of groups lays out no line.
        expect(pairRole(root.children[1].children[3], left)).toBe("");
        expect(String(columnName(left))).toBe("Left column");
        expect(String(columnName({tag: "group", column: 2, columns: 2}))).toBe("Right column");
        expect(String(columnName({tag: "group", column: 3, columns: 3}))).toBe("Column 3");
        expect(columnName({tag: "group"})).toBe("");
    });

    test("the address shares the line of its label, its parts in the value column", async () => {
        await openEditor();
        // The label cell draws its text for a farm, not the role.
        expect(at(LABEL)).toHaveClass("o_erplibre_studio_pair_label");
        expect(at(ADDRESS)).toHaveClass(["o_erplibre_studio_pair_value", "o_erplibre_studio_address"]);
        expect(line("role")).toHaveCount(0);
        expect(`${at(LABEL_TEXT)}`).toHaveText("Address");
        // No hook between the label cell and its value.
        expect(`.o_erplibre_studio_hook[data-target="${ADDRESS}"][data-position=before]`).toHaveCount(0);
        const label = box(at(LABEL_TEXT));
        const street = box(`${line("street")} .o_erplibre_studio_sample_value`);
        const email = box(`${line("email")} .o_erplibre_studio_line_value`);
        // On one line: the label at the left, the street in the value column.
        expect(Math.abs(label.top - street.top)).toBeLessThan(8);
        expect(label.right).toBeLessThan(street.left);
        expect(Math.abs(street.left - email.left)).toBeLessThan(4);
        // City and zip follow on one line under the street, their whole
        // text kept: a narrow column wraps them, its text lined up.
        expect(line("city")).toHaveClass("o_erplibre_studio_address_inline");
        const city = box(`${line("city")} .o_erplibre_studio_sample_value`);
        const zip = box(`${line("zip")} .o_erplibre_studio_sample_value`);
        expect(city.top).toBeGreaterThan(street.top);
        expect(Math.abs(city.left - street.left)).toBeLessThan(2);
        if (Math.abs(zip.top - city.top) < 1) {
            expect(zip.left).toBeGreaterThan(city.right);
        } else {
            expect(Math.abs(zip.left - street.left)).toBeLessThan(2);
        }
        for (const name of ["city", "zip"]) {
            const value = queryOne(`${line(name)} .o_erplibre_studio_sample_value`);
            expect(value.scrollWidth).toBeLessThan(value.clientWidth + 1);
        }
        // The email starts a line of its own, under the address.
        expect(box(line("email")).top).toBeGreaterThan(box(line("zip")).bottom - 1);
    });

    test("the picture floats at the right of the title", async () => {
        await openEditor();
        expect(line("photo")).toHaveClass("o_erplibre_studio_avatar");
        const photo = box(line("photo"));
        const radio = box(line("kind"));
        expect(photo.left).toBeGreaterThan(radio.left + 100);
        // The radio sits beside the picture, not under it.
        expect(radio.top).toBeLessThan(photo.bottom);
        // The columns start under it.
        expect(box(at(MAIN)).top).toBeGreaterThan(photo.bottom - 1);
    });

    test("the plan at Simple lists what the canvas draws; the columns named by their place", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        // The warning and the role are hidden on the sample record; the
        // group of the two columns only lays them out.
        expect(row(WARNING)).toHaveCount(0);
        expect(row(named("twin_id"))).toHaveCount(0);
        expect(row(named("role"))).toHaveCount(0);
        expect(row(MAIN)).toHaveCount(0);
        expect(planRows()).toEqual([
            ["Sheet", 0],
            ["Photo", 1],
            ["Grower kind", 1],
            ["Grower name", 1],
            ["Left column", 1],
            ["Address", 2],
            ["Street", 2],
            ["City", 2],
            ["Zip", 2],
            ["Email", 2],
            ["Right column", 1],
            ["Phone", 2],
        ]);
        expect(".o_erplibre_studio_outline_count").toHaveText("12 items");
        // An open container shows no count; a closed one does.
        expect(`${row(LEFT)} .o_erplibre_studio_outline_size`).toHaveCount(0);
        await contains(`${row(LEFT)} .o_erplibre_studio_outline_toggle`).click();
        expect(`${row(LEFT)} .o_erplibre_studio_outline_size`).toHaveText("4");
        await contains(`${row(LEFT)} .o_erplibre_studio_outline_toggle`).click();
        // The path of the selection names the column.
        await contains(`${line("phone")} .o_erplibre_studio_pick`).click();
        const crumbs = () => queryAll(".o_erplibre_studio_crumb").map((el) => el.textContent.trim());
        expect(crumbs()).toEqual(["Sheet", "Right column", "Phone"]);
        // Detailed: every node, the columns keep their names, with the tag.
        await contains(DETAILED).click();
        expect(row(WARNING)).toHaveCount(1);
        expect(row(named("role"))).toHaveCount(1);
        expect(`${row(MAIN)} .o_erplibre_studio_outline_label`).toHaveText("Columns");
        expect(`${row(LEFT)} .o_erplibre_studio_outline_label`).toHaveText("Left column");
        expect(`${row(LEFT)} .o_erplibre_studio_outline_tech`).toHaveText("group");
        expect(crumbs()).toEqual(["Sheet", "Columns", "Right column", "Phone"]);
    });

    test("the « + » and its list name their place at the level shown", async () => {
        await openEditor();
        const labels = () => queryAll(PLUS).map((el) => el.getAttribute("aria-label"));
        for (const label of labels()) {
            expect(label).not.toMatch(/\b(div|h1|span|group)\b/);
        }
        expect(plusOf(RIGHT, "inside")).toHaveAttribute("aria-label", "Insert here, after Phone");
        await contains(plusOf(RIGHT, "inside"), {visible: false}).click();
        expect(".o_erplibre_studio_insert_list").toHaveAttribute("aria-label", "Insert in Right column, after Phone");
    });
});
