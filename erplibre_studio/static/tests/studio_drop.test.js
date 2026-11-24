// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {
    hover,
    manuallyDispatchProgrammaticEvent,
    pointerDown,
    press,
    queryAll,
    queryOne,
    scroll,
} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {contains, defineWebModels, getService, mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";

const SHEET = "/form/sheet";
const MAIN = "//group[@name='main']";
const LEFT = "//group[@name='left']";
const RIGHT = "//group[@name='right']";
const named = (name) => `//field[@name='${name}']`;

// An invented contact model: none of these values exists anywhere else.
const FIELDS = {
    name: {string: "Name", type: "char"},
    street: {string: "Street", type: "char"},
    code: {string: "Internal code", type: "char"},
    email: {string: "Email", type: "char"},
    phone: {string: "Phone", type: "char"},
    birthday: {string: "Birthday", type: "date"},
};

function field(name) {
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
    };
}

function container(path, tag, label, children) {
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
    };
}

/** A contact form: a title, then a row of two groups of fields. */
function formBlocks() {
    const title = container("/form/sheet/div/h1", "h1", "h1", [field("name")]);
    const left = container(LEFT, "group", "left", [field("street"), field("code")]);
    const right = container(RIGHT, "group", "right", [field("email"), field("phone"), field("birthday")]);
    const main = container(MAIN, "group", "main", [left, right]);
    return container("/form", "form", "form", [container(SHEET, "sheet", "sheet", [title, main])]);
}

function payload(extra = {}) {
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "form",
        view: {id: 9, name: "res.partner.form", xml_id: "base.view_partner_form"},
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "add_page", "add_group", "add_separator"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: FIELDS,
        palette: [],
        field_types: ["char", "integer", "date", "selection"],
        changes: [],
        errors: [],
        project: {
            id: 3,
            name: "Contacts",
            module_name: "studio_contacts",
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
        projects: [{id: 3, name: "Contacts", module_name: "studio_contacts", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        ...extra,
    };
}

/**
 * A form whose right group holds twenty-four more lines, taller than the canvas
 * the tests of the scroll give it.
 */
function tallPayload() {
    const fields = {...FIELDS};
    const lines = [];
    for (let index = 1; index <= 24; index++) {
        const name = `x_line_${index}`;
        fields[name] = {string: `Line ${index}`, type: "char"};
        lines.push({...field("email"), path: named(name), name, label: `Line ${index}`});
    }
    const title = container("/form/sheet/div/h1", "h1", "h1", [field("name")]);
    const left = container(LEFT, "group", "left", [field("street"), field("code")]);
    const right = container(RIGHT, "group", "right", [field("email"), ...lines]);
    const main = container(MAIN, "group", "main", [left, right]);
    const blocks = container("/form", "form", "form", [container(SHEET, "sheet", "sheet", [title, main])]);
    return payload({blocks, fields});
}

/** The payload of a list of three columns. */
function listPayload() {
    return payload({
        view_type: "list",
        view: {id: 7, name: "res.partner.list", xml_id: "base.view_partner_tree"},
        blocks: container("/list", "list", "list", [field("name"), field("email"), field("phone")]),
        layout: {root: "/list"},
        hide_mode: "column_invisible",
    });
}

let answer;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        const operation = args.args[4];
        expect.step(`${operation.type} ${operation.position} ${operation.target}`);
        return answer;
    });
});

async function openEditor(viewType = "form") {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(
        customizeAction({resModel: "res.partner", viewType, viewId: viewType === "form" ? 9 : 7})
    );
    await animationFrame();
}

/** The children of the container ``path``: the drop scope of its hooks. */
const scopeOf = (path) => `.o_erplibre_studio_container[data-path="${path}"] > .o_erplibre_studio_children`;
const ACTIVE = ".o_erplibre_studio_hook_active";
const SCOPE = ".o_erplibre_studio_drop_scope";
const NEAR = ".o_erplibre_studio_hook_near";

/** The own hooks of the scope ``scope``, in their order. */
function hooksOf(scope) {
    return queryAll(`${scope} > .o_erplibre_studio_hook`);
}

/** The centre of ``element`` on screen: {clientX, clientY}. */
function centreOf(element) {
    const rect = element.getBoundingClientRect();
    return {clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2};
}

/** A dragover on the scope ``scope`` at the centre of its hook ``index``. */
async function overNear(scope, index) {
    await manuallyDispatchProgrammaticEvent(queryOne(scope), "dragover", centreOf(hooksOf(scope)[index]));
    await animationFrame();
}

/**
 * What the blocks look like: the border of a field, the outline of a
 * group, the drag handle of a field. A drag changes none of it.
 */
function blockLook() {
    const field = getComputedStyle(queryOne(".o_erplibre_studio_field[data-name=birthday]"));
    const group = getComputedStyle(queryOne(`.o_erplibre_studio_container[data-path="${RIGHT}"]`));
    const handle = getComputedStyle(queryOne(".o_erplibre_studio_field[data-name=birthday] .o_erplibre_studio_handle"));
    return [field.borderTopColor, group.outlineStyle, handle.opacity];
}

/**
 * Press ``selector`` and move the pointer a few pixels: the drag starts
 * there, over the item itself.
 */
async function startDrag(selector) {
    await pointerDown(selector);
    await hover(selector, {position: {x: 2, y: 2}, relative: true});
    await animationFrame();
}

const GHOST = ".o_erplibre_studio_drag_ghost";

/** The canvas, made lower than the form so that it scrolls. */
async function lowCanvas() {
    const canvas = queryOne(".o_erplibre_studio_canvas");
    canvas.style.maxHeight = "400px";
    await animationFrame();
    return canvas;
}

describe.current.tags("desktop");
describe("erplibre_studio drop zones", () => {
    test("no zone at rest; a drag shows the hooks of the scope under the pointer", async () => {
        await openEditor();
        // At rest: every hook is there, none is open, no scope shows.
        expect(hooksOf(scopeOf(RIGHT))).toHaveLength(4);
        expect(ACTIVE).toHaveCount(0);
        expect(SCOPE).toHaveCount(0);
        expect(".o_erplibre_studio_drop_label").toHaveCount(0);
        const look = blockLook();

        await startDrag(".o_erplibre_studio_new_field[data-type=date]");
        expect(document.body).toHaveClass("o_erplibre_studio_dragging");
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging_page");
        // The drag alone opens no zone: the pointer is over no scope yet.
        expect(ACTIVE).toHaveCount(0);

        await overNear(scopeOf(RIGHT), 1);
        expect(SCOPE).toHaveCount(1);
        expect(queryOne(SCOPE)).toBe(queryOne(scopeOf(RIGHT)));
        expect(hooksOf(scopeOf(RIGHT))[1]).toHaveClass("o_erplibre_studio_hook_active");
        expect(ACTIVE).toHaveCount(1);
        expect(`${ACTIVE} .o_erplibre_studio_drop_here`).toHaveText("Drop here");
        expect(`${ACTIVE} .o_erplibre_studio_drop_glyph`).toHaveText("D");
        expect(`${ACTIVE} .o_erplibre_studio_drop_item`).toHaveText(/Date · new field/);
        expect(".o_erplibre_studio_drop_label").toHaveCount(1);
        // Only the hooks right before and after it draw a line, not every
        // hook of the group.
        expect(NEAR).toHaveCount(2);
        // The form keeps its calm look: no border, outline nor handle shows.
        expect(blockLook()).toEqual(look);
        expect(hooksOf(scopeOf(RIGHT))[0]).toHaveClass("o_erplibre_studio_hook_near");
        expect(hooksOf(scopeOf(RIGHT))[2]).toHaveClass("o_erplibre_studio_hook_near");
        expect(hooksOf(scopeOf(RIGHT))[3]).not.toHaveClass("o_erplibre_studio_hook_near");

        // Nearer the end of the group: the slot moves there.
        await overNear(scopeOf(RIGHT), 3);
        expect(hooksOf(scopeOf(RIGHT))[3]).toHaveClass("o_erplibre_studio_hook_active");
        expect(ACTIVE).toHaveCount(1);
        expect(NEAR).toHaveCount(1);
        expect(hooksOf(scopeOf(RIGHT))[2]).toHaveClass("o_erplibre_studio_hook_near");

        // Over the other group: its scope shows, the first one no longer.
        await overNear(scopeOf(LEFT), 0);
        expect(queryOne(SCOPE)).toBe(queryOne(scopeOf(LEFT)));
        expect(hooksOf(scopeOf(LEFT))[0]).toHaveClass("o_erplibre_studio_hook_active");
        expect(`${scopeOf(RIGHT)} > ${ACTIVE}`).toHaveCount(0);

        // A drop anywhere in the scope lands on the hook it shows.
        await manuallyDispatchProgrammaticEvent(queryOne(scopeOf(LEFT)), "drop");
        await animationFrame();
        expect.verifySteps([`add_field before ${named("street")}`]);
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging");
        expect(ACTIVE).toHaveCount(0);
        expect(SCOPE).toHaveCount(0);
        expect(NEAR).toHaveCount(0);
    });

    test("a node dragged from the canvas: its label, then Escape clears", async () => {
        await openEditor();
        await startDrag(".o_erplibre_studio_field[data-name=birthday]");
        await overNear(scopeOf(RIGHT), 0);
        expect(`${ACTIVE} .o_erplibre_studio_drop_item`).toHaveText(/Birthday/);
        expect(`${ACTIVE} .o_erplibre_studio_drop_glyph`).toHaveText("D");

        await press("Escape");
        await animationFrame();
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging");
        expect(ACTIVE).toHaveCount(0);
        expect(SCOPE).toHaveCount(0);
        expect.verifySteps([]);
    });

    test("a hook that refuses the item is never chosen", async () => {
        await openEditor();
        // A tab goes in a sheet or a tab only: the hooks of a group refuse
        // it, so the dragover passes to the scope of the sheet.
        await startDrag(".o_erplibre_studio_layout_page");
        expect(document.body).toHaveClass("o_erplibre_studio_dragging_page");
        await overNear(scopeOf(RIGHT), 1);
        expect(`${scopeOf(RIGHT)} > ${ACTIVE}`).toHaveCount(0);
        expect(queryOne(SCOPE)).toBe(queryOne(scopeOf(SHEET)));
        expect(`${scopeOf(SHEET)} > ${ACTIVE}`).toHaveCount(1);
        expect(`${ACTIVE} .o_erplibre_studio_drop_item`).toHaveText(/Tab/);
        // Right on a hook that refuses it: that hook wins, and shows nothing.
        await manuallyDispatchProgrammaticEvent(hooksOf(scopeOf(RIGHT))[0], "dragover");
        await animationFrame();
        expect(ACTIVE).toHaveCount(0);
        expect(SCOPE).toHaveCount(0);

        await press("Escape");
        await animationFrame();
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging_page");
        expect(ACTIVE).toHaveCount(0);
    });

    test("a dragover on the canvas outside any scope clears the slot", async () => {
        await openEditor();
        await startDrag(".o_erplibre_studio_new_field[data-type=char]");
        await overNear(scopeOf(RIGHT), 2);
        expect(ACTIVE).toHaveCount(1);
        await manuallyDispatchProgrammaticEvent(queryOne(".o_erplibre_studio_canvas"), "dragover");
        await animationFrame();
        expect(ACTIVE).toHaveCount(0);
        expect(SCOPE).toHaveCount(0);
        // A drop on a hook right under the pointer keeps working.
        await manuallyDispatchProgrammaticEvent(hooksOf(scopeOf(RIGHT))[2], "dragover");
        await animationFrame();
        expect(hooksOf(scopeOf(RIGHT))[2]).toHaveClass("o_erplibre_studio_hook_active");
        await manuallyDispatchProgrammaticEvent(hooksOf(scopeOf(RIGHT))[2], "drop");
        await animationFrame();
        expect.verifySteps([`add_field before ${named("birthday")}`]);
    });

    test("in a list, the abscissa picks the column hook", async () => {
        answer = listPayload();
        await openEditor("list");
        const scope = scopeOf("/list");
        expect(hooksOf(scope)).toHaveLength(4);
        await startDrag(".o_erplibre_studio_new_field[data-type=char]");
        await overNear(scope, 2);
        expect(hooksOf(scope)[2]).toHaveClass("o_erplibre_studio_hook_active");
        expect(hooksOf(scope)[2]).toHaveAttribute("data-target", named("phone"));
        expect(`${ACTIVE} .o_erplibre_studio_drop_item`).toHaveText(/Text · new field/);
        await manuallyDispatchProgrammaticEvent(queryOne(scope), "drop");
        await animationFrame();
        expect.verifySteps([`add_field before ${named("phone")}`]);
    });

    test("a drag runs on pointer events: a ghost, the slot under the pointer, a release drops", async () => {
        await openEditor();
        // No native drag source: the wheel scrolls during a drag.
        expect("[draggable=true]").toHaveCount(0);
        const scope = scopeOf(RIGHT);
        const dragging = await contains(".o_erplibre_studio_new_field[data-type=char]").drag();
        expect(document.body).toHaveClass("o_erplibre_studio_dragging");
        expect(GHOST).toHaveCount(1);
        expect(GHOST).toHaveText(/Text · new field/);
        expect(GHOST).toHaveAttribute("aria-hidden", "true");
        await dragging.moveTo(hooksOf(scope)[2]);
        expect(hooksOf(scope)[2]).toHaveClass("o_erplibre_studio_hook_active");
        expect(ACTIVE).toHaveCount(1);
        await dragging.drop();
        expect.verifySteps([`add_field before ${named("birthday")}`]);
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging");
        expect(GHOST).toHaveCount(0);
        // The drag is over: a later move places nothing.
        await hover(hooksOf(scope)[1]);
        await animationFrame();
        expect(ACTIVE).toHaveCount(0);
    });

    test("a press without a move stays a click: no drag starts", async () => {
        await openEditor();
        const item = ".o_erplibre_studio_new_field[data-type=char]";
        const {width, height} = queryOne(item).getBoundingClientRect();
        await pointerDown(item);
        // Two pixels from where it was pressed: under the threshold.
        await hover(item, {position: {x: width / 2 + 2, y: height / 2 + 1}, relative: true});
        await animationFrame();
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging");
        expect(GHOST).toHaveCount(0);
        await press("Escape");
    });

    test("the wheel scrolls the canvas during a drag; the slot follows the pointer", async () => {
        answer = tallPayload();
        await openEditor();
        const canvas = await lowCanvas();
        expect(canvas.scrollHeight).toBeGreaterThan(canvas.clientHeight + 200);
        const scope = scopeOf(RIGHT);
        const dragging = await contains(".o_erplibre_studio_new_field[data-type=char]").drag();
        await dragging.moveTo(hooksOf(scope)[2]);
        expect(hooksOf(scope)[2]).toHaveClass("o_erplibre_studio_hook_active");

        // The wheel over the canvas, the pointer still: the content moves
        // up under it, and the slot goes to a hook further down.
        await scroll(canvas, {y: 150});
        await animationFrame();
        expect(canvas.scrollTop).toBe(150);
        expect(ACTIVE).toHaveCount(1);
        expect(hooksOf(scope).indexOf(queryOne(ACTIVE))).toBeGreaterThan(2);

        // Escape cancels: nothing drops, a later scroll places nothing.
        await dragging.cancel();
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging");
        expect(ACTIVE).toHaveCount(0);
        expect(GHOST).toHaveCount(0);
        await scroll(canvas, {y: 0});
        await animationFrame();
        expect(ACTIVE).toHaveCount(0);
        expect.verifySteps([]);
    });

    test("the edge of the canvas scrolls it during a drag, faster nearer the border", async () => {
        answer = tallPayload();
        await openEditor();
        const canvas = await lowCanvas();
        const {height, width} = canvas.getBoundingClientRect();
        const dragging = await contains(".o_erplibre_studio_new_field[data-type=char]").drag();

        // Out of the bands: no scroll.
        await dragging.moveTo(canvas, {position: {x: width / 2, y: height / 2}, relative: true});
        let before = canvas.scrollTop;
        await animationFrame();
        expect(canvas.scrollTop).toBe(before);

        // In the bottom band, 50 pixels from the border: a slow scroll.
        await dragging.moveTo(canvas, {position: {x: width / 2, y: height - 50}, relative: true});
        before = canvas.scrollTop;
        await animationFrame();
        const slow = canvas.scrollTop - before;
        expect(slow).toBeGreaterThan(0);

        // 5 pixels from it: faster.
        await dragging.moveTo(canvas, {position: {x: width / 2, y: height - 5}, relative: true});
        before = canvas.scrollTop;
        await animationFrame();
        expect(canvas.scrollTop - before).toBeGreaterThan(slow);

        // The end of the drag stops the scroll.
        await dragging.cancel();
        before = canvas.scrollTop;
        await animationFrame();
        await animationFrame();
        expect(canvas.scrollTop).toBe(before);
    });
});
