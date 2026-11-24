// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {press, queryOne} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {contains, defineWebModels, getService, mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {isGhost} from "@erplibre_studio/editor/studio_editor";

const MAIN = "//group[@name='main']";
const named = (name) => `//field[@name='${name}']`;

// An invented supplier model: none of these values exists anywhere else.
const FIELDS = {
    name: {string: "Name", type: "char"},
    email: {string: "Email", type: "char"},
    fax: {string: "Fax", type: "char"},
    is_vendor: {string: "Vendor", type: "boolean"},
};

// The change that removes the fax: a hide, as « Remove from the view »
// makes it in a form or a list.
const HIDE = 4;

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

/** The fax as the draft removes it: hidden by the change HIDE. */
function removedFax(attribute = "invisible") {
    return field("fax", {attrs: {[attribute]: "True"}, changes: [HIDE], change_kinds: ["hidden"], changed: true});
}

function container(path, tag, children) {
    return {
        path,
        tag,
        kind: "container",
        label: tag,
        attrs: {},
        movable: true,
        drop: true,
        children,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: children.some((child) => child.changed || child.changed_inside),
    };
}

/** A form: one group of four fields, the third one removed by the draft. */
function formBlocks(fax = removedFax()) {
    const main = container(MAIN, "group", [field("name"), field("email"), fax, field("is_vendor")]);
    return container("/form", "form", [container("/form/sheet", "sheet", [main])]);
}

function payload(extra = {}) {
    return {
        model: "x_supplier",
        model_name: "Supplier",
        view_type: "form",
        view: {id: 9, name: "x_supplier.form", xml_id: false},
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "hide", "relabel"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: FIELDS,
        palette: [],
        field_types: ["char"],
        changes: [
            {id: HIDE, type: "hide", kind: "hidden", summary: "Hide: fax = True", xpath: named("fax"), path: named("fax")},
        ],
        errors: [],
        project: {
            id: 3,
            name: "Suppliers",
            module_name: "studio_suppliers",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 1,
            item_count: 1,
            app: false,
            models: [],
            access: [],
            rules: [],
            applied: false,
        },
        projects: [{id: 3, name: "Suppliers", module_name: "studio_suppliers", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: 5,
        sample_values: {fax: "+1 555 0199", email: "orders@example.com"},
        ...extra,
    };
}

/** The payload of a list whose « fax » column the draft removes. */
function listPayload() {
    return payload({
        view_type: "list",
        view: {id: 7, name: "x_supplier.list", xml_id: false},
        blocks: container("/list", "list", [field("name"), removedFax("column_invisible"), field("email")]),
        layout: {root: "/list"},
        hide_mode: "column_invisible",
        sample_values: {},
    });
}

let answer;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "set_display_level", (args) => args.args[0]);
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        const operation = args.args.at(-1);
        expect.step(`apply_operation ${operation.type} ${operation.source || ""} ${operation.target} ${operation.position || ""}`);
        return answer;
    });
});

/** ``get_change_removal`` lets the change leave alone; ``remove_change`` gives the fax back. */
function mockRestore() {
    onRpc("erplibre.studio.editor", "get_change_removal", (args) => {
        expect.step(`get_change_removal ${args.args[1]}`);
        return {
            revision: 0,
            change: {id: args.args[1], summary: "Hide: fax = True", view: "x_supplier.form", applied: false},
            refused: false,
            items: [],
            applied: false,
        };
    });
    onRpc("erplibre.studio.editor", "remove_change", (args) => {
        const [, id, expected] = args.args;
        expect.step(`remove_change ${id} ${JSON.stringify(expected)}`);
        answer = payload({blocks: formBlocks(field("fax")), changes: []});
        answer.project = {...answer.project, revision: 1, change_count: 0, item_count: 0};
        return answer;
    });
}

async function openEditor(viewType = "form") {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(
        customizeAction({resModel: "x_supplier", viewType, viewId: viewType === "form" ? 9 : 7})
    );
    await animationFrame();
}

const DETAILED = ".o_erplibre_studio_level_option[data-level=detailed]";
const GHOST = ".o_erplibre_studio_ghost[data-name=fax]";
const PICK = `${GHOST} > .o_erplibre_studio_pick`;
const line = (name) => `.o_erplibre_studio_field[data-name=${name}]`;

describe("isGhost", () => {
    test("an element the draft hides in a form or a list", () => {
        expect(isGhost(removedFax(), "form")).toBe(true);
        expect(isGhost(removedFax(), "list")).toBe(true);
        // A kanban or a search view keeps its own way.
        expect(isGhost(removedFax(), "kanban")).toBe(false);
        expect(isGhost(removedFax(), "search")).toBe(false);
        expect(isGhost(field("email"), "form")).toBe(false);
        expect(isGhost(null, "form")).toBe(false);
    });
});

describe.current.tags("desktop");
describe("an element the draft hides", () => {
    test("Simple: one muted line that shows its row, then folds it", async () => {
        await openEditor();
        expect(GHOST).toHaveClass(["o_erplibre_studio_muted_line", "o_erplibre_studio_field"]);
        expect(GHOST).not.toHaveClass("o_erplibre_studio_ghost_open");
        expect(GHOST).toHaveAttribute("draggable", "false");
        // A hide: the line says « hidden », never « removed ».
        expect(PICK).toHaveText("Fax hidden — show");
        expect(PICK).toHaveAttribute("aria-label", "Fax hidden in this form, show the line");
        expect(PICK).toHaveAttribute("aria-expanded", "false");
        // Neither moves nor leaves again: Escape is its only key.
        expect(PICK).toHaveAttribute("aria-keyshortcuts", "Escape");
        // Hidden, not removed: its label is muted, not struck.
        expect(`${PICK} .o_erplibre_studio_ghost_label`).toHaveText("Fax");
        expect(`${PICK} s`).toHaveCount(0);
        expect(getComputedStyle(queryOne(`${PICK} .o_erplibre_studio_ghost_label`)).textDecorationLine).toBe("none");
        expect(`${GHOST} .o_erplibre_studio_margin_dot[data-dot=ring]`).toHaveCount(1);
        expect(`${GHOST} .o_erplibre_studio_ghost_restore`).toHaveCount(0);
        // The drops beside it target its node, which stays in the arch.
        expect(`.o_erplibre_studio_hook[data-target="${named("is_vendor")}"]`).toHaveCount(1);
        // « show »: the row, its value muted, Restore, the fold button.
        await contains(GHOST).click();
        expect(GHOST).toHaveClass(["o_erplibre_studio_ghost_open", "o_erplibre_studio_selected"]);
        expect(PICK).toHaveAttribute("aria-expanded", "true");
        expect(PICK).toHaveAttribute("aria-label", "Fax hidden in this form");
        expect(PICK).toHaveText("Fax");
        expect(`${GHOST} .o_erplibre_studio_ghost_value`).toHaveText("+1 555 0199");
        expect(`${GHOST} s`).toHaveCount(0);
        expect(`${GHOST} .o_erplibre_studio_ghost_restore`).toHaveText("Restore");
        expect(`${GHOST} .o_erplibre_studio_ghost_fold`).toHaveAttribute("aria-label", "Fold the line Fax");
        // The fold button folds the line; its button keeps the focus.
        await contains(`${GHOST} .o_erplibre_studio_ghost_fold`).click();
        expect(GHOST).not.toHaveClass("o_erplibre_studio_ghost_open");
        expect(PICK).toHaveAttribute("aria-expanded", "false");
        expect(PICK).toBeFocused();
        // Enter on its button shows it again, as a click does.
        await press("Enter");
        await animationFrame();
        expect(GHOST).toHaveClass("o_erplibre_studio_ghost_open");
        expect(PICK).toBeFocused();
    });

    test("Detailed: the row always shows, dashed, with its tag and no fold", async () => {
        await openEditor();
        await contains(DETAILED).click();
        expect(GHOST).toHaveClass(["o_erplibre_studio_ghost_open", "o_erplibre_studio_changed_hidden"]);
        expect(GHOST).not.toHaveClass("o_erplibre_studio_muted_line");
        expect(PICK).not.toHaveAttribute("aria-expanded");
        expect(`${GHOST} .o_erplibre_studio_change_tag[data-kind=hidden]`).toHaveCount(1);
        expect(`${GHOST} .o_erplibre_studio_ghost_restore`).toHaveCount(1);
        expect(`${GHOST} .o_erplibre_studio_ghost_fold`).toHaveCount(0);
        // Its muted value takes the value column of the lines around it,
        // on one line cut by an ellipsis; its tag and Restore go under it.
        const value = queryOne(`${GHOST} .o_erplibre_studio_ghost_value`);
        const valueBox = value.getBoundingClientRect();
        const emailBox = queryOne(`${line("email")} .o_erplibre_studio_line_value`).getBoundingClientRect();
        expect(Math.abs(valueBox.left - emailBox.left)).toBeLessThan(1);
        expect(valueBox.width).toBeGreaterThan(emailBox.width - 1);
        expect(getComputedStyle(value).whiteSpace).toBe("nowrap");
        expect(getComputedStyle(value).textOverflow).toBe("ellipsis");
        expect(value).toHaveAttribute("title", "+1 555 0199");
        const actions = queryOne(`${GHOST} .o_erplibre_studio_ghost_actions`).getBoundingClientRect();
        expect(actions.top).toBeGreaterThan(valueBox.bottom - 1);
        expect(Math.abs(actions.left - valueBox.left)).toBeLessThan(1);
    });

    test("Restore undoes the change that removes it, announces and focuses the field", async () => {
        mockRestore();
        await openEditor();
        await contains(GHOST).click();
        await contains(`${GHOST} .o_erplibre_studio_ghost_restore`).click();
        for (let frame = 0; frame < 4; frame++) {
            await animationFrame();
        }
        expect.verifySteps([`get_change_removal ${HIDE}`, `remove_change ${HIDE} [${HIDE}]`]);
        expect(GHOST).toHaveCount(0);
        expect(line("fax")).toHaveClass(["o_erplibre_studio_line", "o_erplibre_studio_selected"]);
        expect(".o_erplibre_studio_live").toHaveText("Fax restored.");
        expect(`${line("fax")} > .o_erplibre_studio_pick`).toBeFocused();
    });

    test("Delete and Alt+Down do nothing on it; Escape unselects", async () => {
        await openEditor();
        await contains(GHOST).click();
        queryOne(PICK).focus();
        await press("Delete");
        await animationFrame();
        await press(["Alt", "ArrowDown"]);
        await animationFrame();
        expect.verifySteps([]);
        expect(GHOST).toHaveCount(1);
        await press("Escape");
        await animationFrame();
        expect(".o_erplibre_studio_selected").toHaveCount(0);
    });

    test("a keyboard move reads past it", async () => {
        await openEditor();
        // Email, right above the removed fax: down goes past the vendor.
        queryOne(`${line("email")} > .o_erplibre_studio_pick`).focus();
        await press(["Alt", "ArrowDown"]);
        await animationFrame();
        expect.verifySteps([`apply_operation move ${named("email")} ${MAIN} inside`]);
        // The vendor, right under it: up goes before the email, the line
        // the view shows above it.
        queryOne(`${line("is_vendor")} > .o_erplibre_studio_pick`).focus();
        await press(["Alt", "ArrowUp"]);
        await animationFrame();
        expect.verifySteps([`apply_operation move ${named("is_vendor")} ${named("email")} before`]);
    });

    test("the inspector: what it is, Restore, the node at the Detailed level", async () => {
        mockRestore();
        await openEditor();
        await contains(GHOST).click();
        const props = ".o_erplibre_studio_ghost_props";
        expect(props).toHaveCount(1);
        expect(`${props} .o_erplibre_studio_inspector_title`).toHaveText("Fax");
        expect(`${props} .o_erplibre_studio_inspector_kind`).toHaveText("Hidden in this view");
        expect(`${props} .o_erplibre_studio_ghost_note`).toHaveText(
            "The field stays in the database; Restore puts it back where it was."
        );
        expect(`${props} .o_erplibre_studio_ghost_node`).toHaveCount(0);
        // No other property, nor « Remove from the view ».
        expect(".o_erplibre_studio_remove").toHaveCount(0);
        expect(".o_erplibre_studio_prop_hidden").toHaveCount(0);
        await contains(DETAILED).click();
        expect(`${props} .o_erplibre_studio_ghost_node`).toHaveText('<field name="fax" invisible="True"/>');
        await contains(`${props} .o_erplibre_studio_ghost_restore`).click();
        await animationFrame();
        await animationFrame();
        expect.verifySteps([`get_change_removal ${HIDE}`, `remove_change ${HIDE} [${HIDE}]`]);
        expect(".o_erplibre_studio_live").toHaveText("Fax restored.");
        expect(props).toHaveCount(0);
    });

    test("the plan: a muted row with a ring, not draggable, out of the count", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        const row = `.o_erplibre_studio_outline_row[data-name=fax]`;
        expect(row).toHaveClass("o_erplibre_studio_outline_hidden");
        expect(`${row} .o_erplibre_studio_margin_dot[data-dot=ring]`).toHaveCount(1);
        expect(`${row} .o_erplibre_studio_change_dot`).toHaveCount(0);
        // The Simple level shows the ring alone; the sentence of its
        // change stays for a screen reader and as the tooltip of the row,
        // and the Detailed level writes its kind out.
        expect(`${row} .o_erplibre_studio_outline_tag`).toHaveCount(0);
        expect(`${row} .o_erplibre_studio_outline_dot_text`).toHaveText("Fax hidden in this form");
        expect(`${row} .o_erplibre_studio_outline_pick`).toHaveAttribute("title", "Fax hidden in this form");
        await contains(DETAILED).click();
        expect(`${row} .o_erplibre_studio_outline_tag`).toHaveText("hidden");
        expect(`${row} .o_erplibre_studio_outline_dot_text`).toHaveText("hidden");
        expect(`${row} .o_erplibre_studio_outline_pick`).toHaveAttribute("data-draggable", "false");
        expect(getComputedStyle(queryOne(`${row} .o_erplibre_studio_outline_label`)).textDecorationLine).toBe("none");
        // The group, closed, counts the three fields left.
        const main = `.o_erplibre_studio_outline_row[data-path="${MAIN}"]`;
        expect(`${main} .o_erplibre_studio_outline_size`).toHaveCount(0);
        await contains(`${main} .o_erplibre_studio_outline_toggle`).click();
        expect(`${main} .o_erplibre_studio_outline_size`).toHaveText("3");
        await contains(`${main} .o_erplibre_studio_outline_toggle`).click();
        // A click on the row selects the removed line.
        await contains(`${row} .o_erplibre_studio_outline_pick`).click();
        expect(GHOST).toHaveClass("o_erplibre_studio_selected");
    });

    test("the change that removes it finds it on the canvas", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_inspector_tab[data-tab=changes]").click();
        expect(".o_erplibre_studio_change_unplaced").toHaveCount(0);
        await contains(".o_erplibre_studio_changes li[data-type=hide] .o_erplibre_studio_change_pick").click();
        expect(GHOST).toHaveClass("o_erplibre_studio_selected");
    });

    test("a list: a narrow column header with show and Restore", async () => {
        answer = listPayload();
        await openEditor("list");
        expect(GHOST).toHaveAttribute("data-layout", "column");
        expect(PICK).toHaveText("Fax hidden — show");
        expect(PICK).toHaveAttribute("aria-label", "Fax hidden in this list, show the line");
        await contains(GHOST).click();
        expect(`${GHOST} .o_erplibre_studio_ghost_restore`).toHaveCount(1);
        expect(`${GHOST} .o_erplibre_studio_ghost_value`).toHaveCount(0);
    });
});
