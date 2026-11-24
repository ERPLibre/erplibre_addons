// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {manuallyDispatchProgrammaticEvent, press, queryAll, queryOne} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {contains, defineWebModels, getService, mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";

const SHEET = "/form/sheet";
const INFO = "//group[@name='info']";
const NOTEBOOK = "/form/sheet/notebook";
const NOTES = "//page[@name='notes']";
const named = (name) => `//field[@name='${name}']`;

// An invented club member model: none of these values exists anywhere else.
const FIELDS = {
    name: {string: "Name", type: "char"},
    email: {string: "Email", type: "char"},
    phone: {string: "Phone", type: "char"},
    fax: {string: "Fax", type: "char"},
    website: {string: "Website", type: "char"},
    birthday: {string: "Birthday", type: "date"},
    comment: {string: "Notes", type: "text"},
};

// The id of the change an insertion makes.
const NEW_CHANGE = 11;

function field(name, extra = {}) {
    return {
        path: named(name),
        tag: "field",
        kind: "field",
        name,
        label: (FIELDS[name] || {string: name}).string,
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
 * A member form: a group « Contact » (name, email, phone), then a
 * notebook whose first page holds the notes. ``added``: a field block
 * the draft adds before ``before`` (a path of the group), else at its end.
 */
function formBlocks(added = null, before = null) {
    const fields = [field("name"), field("email"), field("phone")];
    if (added) {
        const index = before ? fields.findIndex((f) => f.path === before) : fields.length;
        fields.splice(index, 0, added);
    }
    const info = container(INFO, "group", "Contact", fields);
    const notes = container(NOTES, "page", "Notes", [field("comment")]);
    const notebook = container(NOTEBOOK, "notebook", "notebook", [notes]);
    const sheet = container(SHEET, "sheet", "sheet", [info, notebook]);
    return container("/form", "form", "form", [sheet]);
}

function payload(extra = {}) {
    return {
        model: "x_member",
        model_name: "Member",
        view_type: "form",
        view: {id: 9, name: "x_member.form", xml_id: "studio_club.x_member_form"},
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
        palette: [
            {name: "fax", string: "Fax", type: "char"},
            {name: "website", string: "Website", type: "char"},
            {name: "birthday", string: "Birthday", type: "date"},
        ],
        field_types: ["char", "integer", "selection", "date"],
        changes: [],
        errors: [],
        project: {
            id: 3,
            name: "Club",
            module_name: "studio_club",
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
        projects: [{id: 3, name: "Club", module_name: "studio_club", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        ...extra,
    };
}

/** The payload once an operation added the field ``name`` before ``before``, as the change NEW_CHANGE. */
function inserted(name, label, before) {
    const fields = {...FIELDS};
    if (!fields[name]) {
        fields[name] = {string: label, type: "char", project: true, pending: true, definition: {}};
    }
    const block = field(name, {
        label,
        changes: [NEW_CHANGE],
        change_kinds: ["new"],
        changed: true,
    });
    return payload({
        fields,
        blocks: formBlocks(block, before),
        palette: payload().palette.filter((item) => item.name !== name),
        changes: [{id: NEW_CHANGE, kind: "new", path: named(name), summary: `Add ${label}`}],
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
        const name = operation.field_name || "x_loyalty";
        const label = operation.field ? operation.field.field_description : FIELDS[name].string;
        expect.step(`${operation.type} ${name} ${label} ${operation.target} ${operation.position}`);
        answer = inserted(name, label, operation.position === "before" ? operation.target : null);
        return answer;
    });
});

async function openEditor(viewType = "form") {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(
        customizeAction({resModel: "x_member", viewType, viewId: viewType === "form" ? 9 : 7})
    );
    await animationFrame();
}

const PLUS = ".o_erplibre_studio_insert";
const LIST = ".o_erplibre_studio_insert_list";
const INPUT = ".o_erplibre_studio_insert_input";
const OPTION = ".o_erplibre_studio_insert_option";
const plusOf = (target, position) => `${PLUS}[data-hook="${`:${position}:${target}`.replace(/"/g, '\\"')}"]`;
// A « + » stays transparent until hovered or focused: a click reaches it all the same.
const clickHidden = (selector) => contains(selector, {visible: false}).click();
const pick = (name) => `.o_erplibre_studio_field[data-name=${name}] .o_erplibre_studio_pick`;

describe.current.tags("desktop");
describe("erplibre_studio insert without dragging", () => {
    test("a « + » per hook of a form, named by its neighbours; the one after the selection is a tab stop", async () => {
        await openEditor();
        // The group: before each field and at its end.
        expect(`.o_erplibre_studio_container[data-path="${INFO}"] > .o_erplibre_studio_children ${PLUS}`).toHaveCount(
            4
        );
        expect(plusOf(named("email"), "before")).toHaveAttribute("aria-label", "Insert here, between Name and Email");
        expect(plusOf(named("name"), "before")).toHaveAttribute("aria-label", "Insert here, before Name");
        expect(plusOf(INFO, "inside")).toHaveAttribute("aria-label", "Insert here, after Phone");
        expect(plusOf(named("email"), "before")).toHaveAttribute("title", "Insert here");
        expect(plusOf(named("email"), "before")).toHaveAttribute("aria-haspopup", "dialog");
        expect(plusOf(named("email"), "before")).toHaveAttribute("aria-expanded", "false");
        // None in the tab order at rest.
        expect(`${PLUS}[tabindex="0"]`).toHaveCount(0);
        expect(".o_erplibre_studio_insert_line").toHaveCount(queryAll(PLUS).length);
        // The notebook holds no « + » between its tabs.
        expect(`.o_erplibre_studio_page_hook ${PLUS}`).toHaveCount(0);
        // Selected, a block gives the « + » right after it the tab stop.
        await contains(".o_erplibre_studio_field[data-name=email]").click();
        expect(`${PLUS}[tabindex="0"]`).toHaveCount(1);
        expect(plusOf(named("phone"), "before")).toHaveAttribute("tabindex", "0");
        await contains(".o_erplibre_studio_field[data-name=phone]").click();
        expect(plusOf(INFO, "inside")).toHaveAttribute("tabindex", "0");
        // The palette of a form says so.
        expect(".o_erplibre_studio_palette_hint").toHaveText(
            "Dragging still works. Shorter: hover the space between two fields and click the +."
        );
    });

    test("the list: open at its hook, filtered by the search, Enter inserts the active option there", async () => {
        await openEditor();
        await clickHidden(plusOf(named("email"), "before"));
        expect(LIST).toHaveCount(1);
        expect(LIST).toHaveAttribute("role", "dialog");
        expect(LIST).toHaveAttribute("aria-label", "Insert in Group « Contact », between Name and Email");
        expect(plusOf(named("email"), "before")).toHaveAttribute("aria-expanded", "true");
        expect(plusOf(named("email"), "before")).toHaveAttribute("tabindex", "0");
        expect(INPUT).toBeFocused();
        expect(INPUT).toHaveAttribute("role", "combobox");
        expect(INPUT).toHaveAttribute("placeholder", "Search a field or create…");
        // The inspector shows the insertion point.
        expect(".o_erplibre_studio_insert_point").toHaveCount(1);
        expect(".o_erplibre_studio_insert_point .o_erplibre_studio_inspector_title").toHaveText("Insertion point");
        expect(".o_erplibre_studio_insert_point_where").toHaveText("Group « Contact », between Name and Email");
        // The groups: the existing fields, the new field types, the layout.
        expect(".o_erplibre_studio_insert_group").toHaveCount(3);
        expect(".o_erplibre_studio_insert_group:eq(0) .o_erplibre_studio_insert_group_title").toHaveText(
            /existing fields/i
        );
        expect(".o_erplibre_studio_insert_group:eq(1) .o_erplibre_studio_insert_group_title").toHaveText(/new field…/i);
        // A tab goes in a sheet or a tab only: a group takes a group and a separator.
        expect(".o_erplibre_studio_insert_group[data-group=layout] [role=option]").toHaveCount(2);
        expect(`${OPTION}[data-key="layout:page"]`).toHaveCount(0);
        expect(`${OPTION}[data-key="existing:fax"]`).toHaveAttribute("aria-selected", "true");
        expect(INPUT).toHaveAttribute("aria-activedescendant", queryOne(`${OPTION}[data-key="existing:fax"]`).id);
        // The search filters the existing fields, accents and case aside.
        await contains(INPUT).edit("WÉB", {confirm: false});
        expect(`.o_erplibre_studio_insert_group[data-group=existing] ${OPTION}`).toHaveCount(1);
        expect(`${OPTION}[data-key="existing:website"]`).toHaveCount(1);
        await contains(INPUT).edit("", {confirm: false});
        // Down, then Enter: the second existing field, at the hook.
        await press("ArrowDown");
        await animationFrame();
        expect(`${OPTION}[data-key="existing:website"]`).toHaveAttribute("aria-selected", "true");
        await press("Enter");
        await animationFrame();
        await animationFrame();
        await animationFrame();
        expect.verifySteps([`add_existing_field website Website ${named("email")} before`]);
        expect(LIST).toHaveCount(0);
        expect(".o_erplibre_studio_insert_point").toHaveCount(0);
        expect(".o_erplibre_studio_field[data-name=website]").toHaveClass("o_erplibre_studio_selected");
        expect(pick("website")).toBeFocused();
        expect(".o_erplibre_studio_live").toHaveText("Website inserted between Name and Email.");
    });

    test("create « text » as…: the new field takes the text as its label; Cancel this insertion removes it", async () => {
        onRpc("erplibre.studio.editor", "get_change_removal", (args) => {
            expect.step(`get_change_removal ${args.args[1]}`);
            return {
                revision: 0,
                change: {id: args.args[1], summary: "Add Loyalty", view: "x_member.form", applied: false},
                refused: false,
                items: [],
                applied: false,
            };
        });
        onRpc("erplibre.studio.editor", "remove_change", (args) => {
            expect.step(`remove_change ${args.args[1]}`);
            answer = payload();
            return answer;
        });
        await openEditor();
        await clickHidden(plusOf(named("email"), "before"));
        await contains(INPUT).edit("Loyalty", {confirm: false});
        expect(".o_erplibre_studio_insert_empty").toHaveText("No existing field matches.");
        expect(".o_erplibre_studio_insert_group[data-group=new] .o_erplibre_studio_insert_group_title").toHaveText(
            /create « loyalty » as…/i
        );
        // The title shows in capitals; the text typed keeps its case.
        const typed = queryOne(".o_erplibre_studio_insert_group[data-group=new] .o_erplibre_studio_insert_typed");
        expect(typed).toHaveText("Loyalty");
        expect(getComputedStyle(typed).textTransform).toBe("none");
        expect(getComputedStyle(typed.parentElement).textTransform).toBe("uppercase");
        await contains(`${OPTION}[data-key="new:char"]`).click();
        await animationFrame();
        expect.verifySteps([`add_field x_loyalty Loyalty ${named("email")} before`]);
        expect(".o_erplibre_studio_field[data-name=x_loyalty]").toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_inspector_changed").toHaveText(
            /Inserted between Name and Email in Group « Contact »\./
        );
        expect(".o_erplibre_studio_undo_block_change").toHaveCount(0);
        await contains(".o_erplibre_studio_cancel_insert").click();
        await animationFrame();
        expect.verifySteps([`get_change_removal ${NEW_CHANGE}`, `remove_change ${NEW_CHANGE}`]);
        expect(".o_erplibre_studio_field[data-name=x_loyalty]").toHaveCount(0);
        expect(".o_erplibre_studio_selected").toHaveCount(0);
    });

    test("Escape closes the list and gives the focus back to its « + »; a click outside closes it", async () => {
        await openEditor();
        await clickHidden(plusOf(INFO, "inside"));
        expect(INPUT).toBeFocused();
        await press("Escape");
        await animationFrame();
        await animationFrame();
        expect(LIST).toHaveCount(0);
        expect(plusOf(INFO, "inside")).toBeFocused();
        expect(plusOf(INFO, "inside")).toHaveAttribute("aria-expanded", "false");
        expect.verifySteps([]);
        // A click on the canvas outside the list closes it.
        await clickHidden(plusOf(INFO, "inside"));
        expect(LIST).toHaveCount(1);
        await contains(".o_erplibre_studio_crumbs").click();
        expect(LIST).toHaveCount(0);
    });

    test("Escape on the « + » after the selection unselects; a click on the block selects it again", async () => {
        await openEditor();
        const email = ".o_erplibre_studio_field[data-name=email]";
        await contains(email).click();
        expect(email).toHaveClass("o_erplibre_studio_selected");
        // Tab from the block reaches the « + » right after it.
        queryOne(pick("email")).focus();
        await press("Tab");
        expect(plusOf(named("phone"), "before")).toBeFocused();
        await press("Escape");
        await animationFrame();
        expect(".o_erplibre_studio_selected").toHaveCount(0);
        expect(LIST).toHaveCount(0);
        // The click selects: a block still selected would toggle off.
        await contains(email).click();
        expect(email).toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_inspector_title").toHaveText("Email");
    });

    test("Escape on the Close button of the list closes it too", async () => {
        await openEditor();
        await clickHidden(plusOf(INFO, "inside"));
        queryOne(".o_erplibre_studio_insert_close").focus();
        await press("Escape");
        await animationFrame();
        await animationFrame();
        expect(LIST).toHaveCount(0);
        expect(plusOf(INFO, "inside")).toBeFocused();
    });

    test("a list opened from the plan gives the focus back to its row", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        const emailRow = `.o_erplibre_studio_outline_row[data-path="${named("email")}"]`;
        await contains(`${emailRow} .o_erplibre_studio_outline_pick`).click();
        queryOne(emailRow).focus();
        await press("Insert");
        await animationFrame();
        expect(INPUT).toBeFocused();
        await press("Escape");
        await animationFrame();
        await animationFrame();
        expect(LIST).toHaveCount(0);
        expect(emailRow).toBeFocused();
        // Its Close button too.
        await press("Insert");
        await animationFrame();
        expect(INPUT).toBeFocused();
        await contains(".o_erplibre_studio_insert_close").click();
        await animationFrame();
        await animationFrame();
        expect(emailRow).toBeFocused();
    });

    test("the « + » of an empty tab is a tab stop", async () => {
        const blocks = formBlocks();
        const notebook = blocks.children[0].children.find((b) => b.tag === "notebook");
        notebook.children[0].children = [];
        answer = payload({blocks});
        await openEditor();
        expect(".o_erplibre_studio_empty_hint").toHaveText("Empty tab. The + above inserts a first field.");
        expect(plusOf(NOTES, "inside")).toHaveAttribute("tabindex", "0");
        expect(plusOf(NOTES, "inside")).toHaveAttribute("aria-label", "Insert here, in Notes");
        // The group, which holds fields, keeps none at rest.
        expect(`.o_erplibre_studio_container[data-path="${INFO}"] ${PLUS}[tabindex="0"]`).toHaveCount(0);
    });

    test("the plan: the « + » of the selected row and of a container open the list on the canvas", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        // A container that takes drops: « Add in ».
        const groupRow = `.o_erplibre_studio_outline_row[data-path="${INFO}"]`;
        expect(`${groupRow} .o_erplibre_studio_outline_add`).toHaveAttribute("aria-label", "Add in Group « Contact »");
        expect(`${groupRow} .o_erplibre_studio_outline_add`).toHaveAttribute("tabindex", "-1");
        expect(
            `.o_erplibre_studio_outline_row[data-path="${NOTEBOOK}"] .o_erplibre_studio_outline_add`
        ).toHaveAttribute("aria-label", "Add a tab");
        await clickHidden(`${groupRow} .o_erplibre_studio_outline_add`);
        await animationFrame();
        expect(LIST).toHaveCount(1);
        expect(plusOf(INFO, "inside")).toHaveAttribute("aria-expanded", "true");
        expect(INPUT).toBeFocused();
        expect(`${groupRow} .o_erplibre_studio_outline_add`).toHaveAttribute("aria-expanded", "true");
        // The selected row: « Insert after ».
        await contains(
            `.o_erplibre_studio_outline_row[data-path="${named("name")}"] .o_erplibre_studio_outline_pick`
        ).click();
        expect(LIST).toHaveCount(0);
        const nameAdd = `.o_erplibre_studio_outline_row[data-path="${named("name")}"] .o_erplibre_studio_outline_add`;
        expect(nameAdd).toHaveAttribute("aria-label", "Insert after Name");
        await contains(nameAdd).click();
        await animationFrame();
        expect(plusOf(named("email"), "before")).toHaveAttribute("aria-expanded", "true");
        // Insert on a row opens the list after its block.
        await contains(
            `.o_erplibre_studio_outline_row[data-path="${named("email")}"] .o_erplibre_studio_outline_pick`
        ).click();
        queryOne(`.o_erplibre_studio_outline_row[data-path="${named("email")}"]`).focus();
        await press("Insert");
        await animationFrame();
        expect(plusOf(named("phone"), "before")).toHaveAttribute("aria-expanded", "true");
        expect(INPUT).toBeFocused();
    });

    test("no « + » in a list, during a drag or in the preview", async () => {
        await openEditor();
        expect(PLUS).not.toHaveCount(0);
        await manuallyDispatchProgrammaticEvent(queryOne(".o_erplibre_studio_new_field[data-type=date]"), "dragstart");
        await animationFrame();
        expect(PLUS).toHaveCount(0);
        await manuallyDispatchProgrammaticEvent(queryOne(".o_erplibre_studio_new_field[data-type=date]"), "dragend");
        await animationFrame();
        expect(PLUS).not.toHaveCount(0);
    });

    test("no « + » in a list view", async () => {
        answer = payload({
            view_type: "list",
            view: {id: 7, name: "x_member.list", xml_id: "studio_club.x_member_list"},
            blocks: container("/list", "list", "list", [field("name"), field("email")]),
            layout: {root: "/list"},
            hide_mode: "column_invisible",
        });
        await openEditor("list");
        expect(".o_erplibre_studio_hook").not.toHaveCount(0);
        expect(PLUS).toHaveCount(0);
        expect(".o_erplibre_studio_palette_hint").toHaveCount(0);
    });
});
