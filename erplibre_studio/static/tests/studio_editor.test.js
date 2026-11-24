// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {press, queryAll, queryOne} from "@odoo/hoot-dom";
import {Deferred, animationFrame} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    mountWithCleanup,
    onRpc,
    serverState,
    webModels,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {findBlock, isTrue, selectionToText, textToSelection} from "@erplibre_studio/editor/studio_editor";
import {fieldTypeFits} from "@erplibre_studio/editor/studio_relations";

const NAME = "//field[@name='name']";
const EMAIL = "//field[@name='email']";

function column(name, label, attrs = {}) {
    return {path: `//field[@name='${name}']`, tag: "field", kind: "field", name, label, attrs};
}

/** The editor payload of a contact list with ``columns``. */
function payload(columns, extra = {}) {
    const fields = {
        name: {string: "Name", type: "char"},
        email: {string: "Email", type: "char"},
        ref: {string: "Reference", type: "char"},
    };
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "list",
        view: {id: 7, name: "res.partner.list", xml_id: "base.view_partner_tree"},
        blocks: {
            path: "/list",
            tag: "list",
            kind: "container",
            drop: true,
            label: "list",
            attrs: {},
            children: columns,
        },
        layout: {root: "/list"},
        operations: [
            "add_field",
            "add_existing_field",
            "move",
            "remove",
            "hide",
            "relabel",
            "required",
            "readonly",
            "help",
            "optional",
            "update_field",
        ],
        hide_mode: "column_invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list", "kanban", "search", "pivot"],
        fields,
        palette: [{name: "ref", string: "Reference", type: "char"}],
        field_types: ["char", "integer", "selection"],
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
            change_count: 1,
            item_count: 1,
            app: false,
            models: [],
            access: [],
            rules: [],
            applied: false,
        },
        projects: [{id: 3, name: "Contacts", module_name: "studio_contacts", state: "draft"}],
        // The level that shows the technical bits these tests read.
        display_level: "detailed",
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        ...extra,
    };
}

let answer;
// The answer of get_review.
let review;
// A promise the next apply_operation waits for, when set.
let holdOperation;
// The move changes the server answers, when set: a move adds one, a move
// with ``merge`` folds into the last one, or removes it when the columns
// are back in their first order.
let moveChanges;
// The type of the field an add_field answers with, its label « Text ».
let addedType;

beforeEach(() => {
    serverState.debug = "1";
    webModels.ResPartner._views.list = `<list><field name="name"/><field name="email"/></list>`;
    defineWebModels();
    answer = payload([column("name", "Name"), column("email", "Email")]);
    holdOperation = null;
    moveChanges = null;
    addedType = "char";
    onRpc("erplibre.studio.editor", "get_editor_data", (args) => {
        expect.step(`get_editor_data ${args.args.slice(0, 4).join(" ")}`);
        if (args.kwargs.pick_project === false) {
            return payload(answer.blocks.children, {project: false});
        }
        return answer;
    });
    onRpc("erplibre.studio.editor", "apply_operation", async (args) => {
        const operation = args.args[4];
        const parts = [operation.type, operation.source || operation.field_name, operation.position];
        parts.push(operation.target, operation.value, operation.merge && "merge");
        expect.step(["apply_operation", ...parts.filter(Boolean)].join(" "));
        expect(args.kwargs.revision).toBe(answer.project.revision);
        if (holdOperation) {
            await holdOperation;
        }
        if (operation.type === "add_field") {
            expect(operation.field.ttype).toBe(addedType);
            answer = payload([column("name", "Name"), column("email", "Email"), column("x_text", "Text")]);
            answer.fields.x_text = {
                string: "Text",
                type: addedType,
                project: true,
                pending: true,
                definition: {ttype: addedType, field_description: "Text", help: "", readonly: false},
            };
        } else if (operation.type === "move") {
            // The columns in their new order: the source before the target,
            // or at the end for « inside ».
            const columns = answer.blocks.children;
            const moved = columns.find((c) => c.path === operation.source);
            const rest = columns.filter((c) => c !== moved);
            const index = rest.findIndex((c) => c.path === operation.target);
            rest.splice(operation.position === "before" && index >= 0 ? index : rest.length, 0, moved);
            answer = payload(rest);
            if (moveChanges) {
                const back = rest.map((c) => c.name).join() === moveChanges.first;
                if (!operation.merge) {
                    const id = moveChanges.items.length + 1;
                    moveChanges.items.push({id, type: "move", kind: "moved", path: operation.source});
                } else if (back) {
                    moveChanges.items.pop();
                }
                answer.changes = [...moveChanges.items];
            }
        } else if (operation.type === "remove") {
            answer = payload(answer.blocks.children.filter((c) => c.path !== operation.target));
        } else if (operation.type === "relabel") {
            answer = payload([column("name", "Name"), column("email", operation.value, {string: operation.value})]);
        }
        answer.project.revision = args.kwargs.revision + 1;
        return answer;
    });
    onRpc("erplibre.studio.editor", "get_review", (args) => {
        expect.step(`get_review ${args.args[0]}`);
        return review;
    });
    review = {
        revision: 0,
        state: "draft",
        groups: [],
        removal: {report: {}, digest: "n0thing", confirm: false},
        blocked: false,
    };
    onRpc("erplibre.studio.editor", "project_action", (args) => {
        expect.step(`project_action ${args.args[1]}`);
        answer = payload(answer.blocks.children, {
            project: {...answer.project, state: "applied", state_label: "Applied", applied: true},
        });
        return answer;
    });
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "list", viewId: 7}));
    await animationFrame();
    expect.verifySteps(["get_editor_data res.partner 7 list false"]);
}

/** Choose ``value`` in the project menu of the top bar: an id, « new » or « » for none. */
async function chooseProject(value) {
    await contains(".o_erplibre_studio_project_select").click();
    await contains(`.o_erplibre_studio_project_item[data-project='${value}']`).click();
}

function hook(target, position) {
    return `.o_erplibre_studio_hook[data-target="${target}"][data-position=${position}]`;
}

describe.current.tags("desktop");
describe("erplibre_studio editor", () => {
    test("renders the columns and the palette", async () => {
        await openEditor();
        expect(".o_erplibre_studio_field").toHaveCount(2);
        expect(".o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "name");
        // A hook before each column and one at the end.
        expect(".o_erplibre_studio_hook").toHaveCount(3);
        expect(".o_erplibre_studio_new_field").toHaveCount(3);
        expect(".o_erplibre_studio_state").toHaveText("Draft");
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        expect(".o_erplibre_studio_existing_field").toHaveCount(1);
        await contains(".o_erplibre_studio_palette_filter").edit("zzz");
        expect(".o_erplibre_studio_existing_field").toHaveCount(0);
    });

    test("Enter on a palette item adds it without a drag", async () => {
        await openEditor();
        const item = ".o_erplibre_studio_new_field[data-type=char]";
        const add = `${item} > button.o_erplibre_studio_palette_add`;
        // The draggable div is no tab stop: the button inside it is.
        expect(item).toHaveAttribute("draggable", "true");
        expect(item).not.toHaveAttribute("role");
        expect(item).not.toHaveAttribute("tabindex");
        expect(add).toHaveCount(1);
        expect(add).toHaveAttribute("type", "button");
        expect(add).toHaveAttribute("aria-label", `Add ${queryOne(item).title}`);
        // The mouse goes through the button to the draggable div.
        expect(getComputedStyle(queryOne(add)).pointerEvents).toBe("none");
        // Nothing selected: at the last hook of the canvas.
        const last = queryAll(".o_erplibre_studio_hook").at(-1);
        queryOne(add).focus();
        await press("Enter");
        await animationFrame();
        expect.verifySteps([`apply_operation add_field ${last.dataset.position} ${last.dataset.target}`]);
        // A selected block: at the first hook after it.
        await contains(".o_erplibre_studio_field[data-name=name]").click();
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        const ref = ".o_erplibre_studio_existing_field[data-name=ref]";
        expect(ref).not.toHaveAttribute("tabindex");
        expect(`${ref} > .o_erplibre_studio_palette_add`).toHaveAttribute("aria-label", "Add Reference (ref)");
        queryOne(`${ref} > .o_erplibre_studio_palette_add`).focus();
        await press("Enter");
        await animationFrame();
        expect.verifySteps([`apply_operation add_existing_field ref before ${EMAIL}`]);
    });

    test("a click on a palette item adds it once", async () => {
        await openEditor();
        const item = ".o_erplibre_studio_new_field[data-type=char]";
        const last = queryAll(".o_erplibre_studio_hook").at(-1);
        // The click lands on the div: its handler runs once, the button
        // has none of its own. (Space on the button is the browser's own
        // click of a button, which hoot does not simulate.)
        await contains(item).click();
        await animationFrame();
        expect.verifySteps([`apply_operation add_field ${last.dataset.position} ${last.dataset.target}`]);
        expect(".o_erplibre_studio_field[data-name=x_text]").toHaveClass("o_erplibre_studio_selected");
    });

    test("a canvas block is a button the keyboard selects", async () => {
        await openEditor();
        const block = ".o_erplibre_studio_field[data-name=name]";
        const pick = `${block} .o_erplibre_studio_pick`;
        expect(pick).toHaveCount(1);
        expect(queryOne(pick).tagName).toBe("BUTTON");
        expect(pick).toHaveAttribute("type", "button");
        expect(pick).toHaveAttribute("aria-label", "Field Name (name)");
        expect(pick).toHaveAttribute("aria-pressed", "false");
        // The mouse goes through the button to the draggable div.
        expect(getComputedStyle(queryOne(pick)).pointerEvents).toBe("none");
        expect(block).toHaveAttribute("draggable", "true");
        queryOne(pick).focus();
        await press("Enter");
        await animationFrame();
        expect(block).toHaveClass("o_erplibre_studio_selected");
        expect(pick).toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "name");
        // A second press unselects, as a second click does.
        await press("Enter");
        await animationFrame();
        expect(block).not.toHaveClass("o_erplibre_studio_selected");
        expect(pick).toHaveAttribute("aria-pressed", "false");
        // A click on the block still selects it once.
        await contains(block).click();
        expect(block).toHaveClass("o_erplibre_studio_selected");
    });

    test("arrow keys walk the canvas blocks", async () => {
        answer = payload([column("name", "Name"), column("email", "Email"), column("ref", "Reference")]);
        await openEditor();
        const pick = (name) => `.o_erplibre_studio_field[data-name=${name}] .o_erplibre_studio_pick`;
        queryOne(pick("name")).focus();
        await press("ArrowDown");
        expect(pick("email")).toBeFocused();
        await press("ArrowRight");
        expect(pick("ref")).toBeFocused();
        // Down on the last block stays there.
        await press("ArrowDown");
        expect(pick("ref")).toBeFocused();
        await press("Home");
        expect(pick("name")).toBeFocused();
        await press("ArrowUp");
        expect(pick("name")).toBeFocused();
        await press("End");
        expect(pick("ref")).toBeFocused();
        await press("ArrowLeft");
        expect(pick("email")).toBeFocused();
        // Walking selects nothing.
        expect(".o_erplibre_studio_selected").toHaveCount(0);
    });

    test("Alt+Arrow moves a canvas block, Delete removes it, Escape unselects", async () => {
        answer = payload([column("name", "Name"), column("email", "Email"), column("ref", "Reference")]);
        await openEditor();
        const pick = (name) => `.o_erplibre_studio_field[data-name=${name}] .o_erplibre_studio_pick`;
        const REF = "//field[@name='ref']";
        expect(pick("email")).toHaveAttribute("aria-keyshortcuts", "Alt+ArrowUp Alt+ArrowDown Delete Escape");
        expect(".o_erplibre_studio_live").toHaveAttribute("aria-live", "polite");
        queryOne(pick("email")).focus();
        await press(["Alt", "ArrowUp"]);
        await animationFrame();
        await animationFrame();
        expect.verifySteps([`apply_operation move ${EMAIL} before ${NAME}`]);
        expect(".o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "email");
        expect(pick("email")).toBeFocused();
        expect(".o_erplibre_studio_field[data-name=email]").toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_live").toHaveText(/Email moved: position 1 of 3/);
        // The first block goes no higher; the last one no lower.
        await press(["Alt", "ArrowUp"]);
        await animationFrame();
        expect.verifySteps([]);
        expect(".o_erplibre_studio_live").toHaveText(/Email cannot move further/);
        queryOne(pick("ref")).focus();
        await press(["Alt", "ArrowDown"]);
        await animationFrame();
        expect.verifySteps([]);
        expect(".o_erplibre_studio_live").toHaveText(/Reference cannot move further/);
        // Down from the first block: past the hook right after it, to the
        // place after the next one.
        queryOne(pick("email")).focus();
        await press(["Alt", "ArrowDown"]);
        await animationFrame();
        await animationFrame();
        expect.verifySteps([`apply_operation move ${EMAIL} before ${REF}`]);
        expect(queryAll(".o_erplibre_studio_field").map((e) => e.dataset.name)).toEqual(["name", "email", "ref"]);
        // The selection shows its crumbs, which carry its path too.
        expect(`.o_erplibre_studio_crumb[data-path="${EMAIL}"]`).toHaveCount(1);
        expect(pick("email")).toBeFocused();
        // Escape unselects; the focus stays.
        expect(".o_erplibre_studio_selected").toHaveCount(1);
        await press("Escape");
        await animationFrame();
        expect(".o_erplibre_studio_selected").toHaveCount(0);
        expect(pick("email")).toBeFocused();
        // Delete removes the block; the focus goes to the block in its place.
        queryOne(pick("ref")).focus();
        await press("Delete");
        await animationFrame();
        await animationFrame();
        expect.verifySteps([`apply_operation remove ${REF}`]);
        expect(".o_erplibre_studio_field").toHaveCount(2);
        expect(pick("email")).toBeFocused();
        // A column of the view itself stays in the arch, hidden: the live
        // region says « hidden », not « removed ».
        expect(".o_erplibre_studio_live").toHaveText(/Reference hidden in this list\. Ctrl\+Z undoes it\./);
        // The plain arrows still walk.
        await press("ArrowUp");
        expect(pick("name")).toBeFocused();
        expect.verifySteps([]);
    });

    test("Delete on a block that asks first announces and moves the focus once confirmed", async () => {
        // A column the draft adds, with changes inside: its removal asks.
        const added = {...column("ref", "Reference"), change_kinds: ["new"], changed_inside: true};
        answer = payload([column("name", "Name"), column("email", "Email"), added]);
        await openEditor();
        const pick = (name) => `.o_erplibre_studio_field[data-name=${name}] .o_erplibre_studio_pick`;
        queryOne(pick("ref")).focus();
        await press("Delete");
        await animationFrame();
        expect.verifySteps([]);
        expect(".modal").toHaveCount(1);
        await contains(".modal .btn-primary").click();
        await animationFrame();
        await animationFrame();
        expect.verifySteps(["apply_operation remove //field[@name='ref']"]);
        expect(".o_erplibre_studio_field").toHaveCount(2);
        // A column the draft adds leaves the draft: it is removed.
        expect(".o_erplibre_studio_live").toHaveText(/Reference removed\. Ctrl\+Z undoes it\./);
        expect(pick("email")).toBeFocused();
    });

    test("consecutive Alt+Arrow moves of one block ask to merge into one change", async () => {
        answer = payload([column("name", "Name"), column("email", "Email"), column("ref", "Reference")]);
        moveChanges = {first: "name,email,ref", items: []};
        await openEditor();
        const pick = (name) => `.o_erplibre_studio_field[data-name=${name}] .o_erplibre_studio_pick`;
        const REF = "//field[@name='ref']";
        const order = () => queryAll(".o_erplibre_studio_field").map((e) => e.dataset.name);
        const moveKey = async (key) => {
            await press(["Alt", key]);
            await animationFrame();
            await animationFrame();
        };
        // The first move of the series adds a change; the next ones of the
        // same block carry « merge ».
        queryOne(pick("name")).focus();
        await moveKey("ArrowDown");
        expect.verifySteps([`apply_operation move ${NAME} before ${REF}`]);
        await moveKey("ArrowDown");
        expect.verifySteps([`apply_operation move ${NAME} inside /list merge`]);
        expect(order()).toEqual(["email", "ref", "name"]);
        expect(".o_erplibre_studio_field[data-name=name]").toHaveClass("o_erplibre_studio_selected");
        expect(pick("name")).toBeFocused();
        // Back where it stood: the change leaves, the block stays selected.
        await moveKey("ArrowUp");
        expect.verifySteps([`apply_operation move ${NAME} before ${REF} merge`]);
        await moveKey("ArrowUp");
        expect.verifySteps([`apply_operation move ${NAME} before ${EMAIL} merge`]);
        expect(order()).toEqual(["name", "email", "ref"]);
        expect(".o_erplibre_studio_field[data-name=name]").toHaveClass("o_erplibre_studio_selected");
        expect(pick("name")).toBeFocused();
        // The series ended with its change: the next move starts a new one.
        await moveKey("ArrowDown");
        expect.verifySteps([`apply_operation move ${NAME} before ${REF}`]);
        // Another block starts its own series.
        queryOne(pick("ref")).focus();
        await moveKey("ArrowUp");
        expect.verifySteps([`apply_operation move ${REF} before ${NAME}`]);
        await moveKey("ArrowUp");
        expect.verifySteps([`apply_operation move ${REF} before ${EMAIL} merge`]);
    });

    test("Ctrl+Z removes the last change of the view; a text field keeps its own undo", async () => {
        answer.changes = [{id: 1, type: "relabel", kind: "renamed", summary: "Rename Email", path: EMAIL, error: false}];
        await openEditor();
        expect(".o_erplibre_studio_undo").toHaveAttribute("aria-keyshortcuts", "Control+Z");
        queryOne(".o_erplibre_studio_palette_filter").focus();
        await press("control+z");
        await animationFrame();
        expect.verifySteps([]);
        queryOne(".o_erplibre_studio_palette_filter").blur();
        await press("control+z");
        await animationFrame();
        expect.verifySteps(["project_action action_undo"]);
        // The answer has no change left: Ctrl+Z does nothing more.
        await press("control+z");
        await animationFrame();
        expect.verifySteps([]);
    });

    test("the preview of a view: a banner, the palette paused, how it renders", async () => {
        webModels.ResPartner._views["list,7"] = `<list><field name="name"/><field name="email"/></list>`;
        await openEditor();
        await contains(".o_erplibre_studio_preview_toggle").click();
        expect(".o_erplibre_studio_preview_toggle").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_studio_preview_banner[data-kind=view]").toHaveText(/The view with the draft/);
        expect(".o_erplibre_studio_preview .o_list_view").toHaveCount(1);
        expect(".o_erplibre_studio_preview_type").toHaveCount(5);
        expect(".o_erplibre_studio_preview_type[data-view-type=list]").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_palette_paused").toHaveText(/Palette paused/);
        expect(".o_erplibre_studio_new_field").toHaveCount(0);
        expect(".o_erplibre_studio_preview_info[data-kind=view] .o_erplibre_studio_render").toHaveText(
            /Those of the database/
        );
        expect(".o_erplibre_studio_approval").toHaveCount(0);
        expect(".o_erplibre_studio_status_preview").toHaveText("Preview: the view with the draft");
        // The changes of the view stay one tab away.
        await contains(".o_erplibre_studio_inspector_tab[data-tab=changes]").click();
        expect(".o_erplibre_studio_no_change").toHaveCount(1);
        await contains(".o_erplibre_studio_inspector_tab[data-tab=properties]").click();
        await contains(".o_erplibre_studio_preview_leave").click();
        expect(".o_erplibre_studio_preview_banner").toHaveCount(0);
        expect(".o_erplibre_studio_canvas .o_erplibre_studio_field").toHaveCount(2);
        expect(".o_erplibre_studio_new_field").toHaveCount(3);
        expect(".o_erplibre_studio_preview_toggle").toHaveAttribute("aria-pressed", "false");
    });

    test("dragging a column onto a hook moves it", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=email]").dragAndDrop(hook(NAME, "before"));
        expect.verifySteps([`apply_operation move ${EMAIL} before ${NAME}`]);
        expect(".o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "email");
        expect(".o_erplibre_studio_field[data-name=email]").toHaveClass("o_erplibre_studio_selected");
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging");
    });

    test("dropping a new field type adds a field and selects it", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_new_field[data-type=char]").dragAndDrop(hook("/list", "inside"));
        expect.verifySteps(["apply_operation add_field inside /list"]);
        expect(".o_erplibre_studio_field[data-name=x_text]").toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_field[data-name=x_text] .o_erplibre_studio_flag[data-flag=pending]").toHaveCount(1);
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "x_text");
        expect(".o_erplibre_studio_prop_label").toHaveValue("Text");
    });

    test("a JSON field: among the other types of a form or a list, read-only", async () => {
        const types = ["char", "integer", "float", "boolean", "date", "datetime", "selection", "many2one"];
        answer = payload(answer.blocks.children, {field_types: [...types, "text", "html", "json", "monetary"]});
        await openEditor();
        // Not among the common types: under « Show the other types ».
        expect(".o_erplibre_studio_new_field").toHaveCount(8);
        expect(".o_erplibre_studio_new_field[data-type=json]").toHaveCount(0);
        await contains(".o_erplibre_studio_more_types").click();
        expect(".o_erplibre_studio_new_field[data-type=json]").toHaveCount(1);
        expect(".o_erplibre_studio_new_field[data-type=json]").toHaveText(/JSON/);
        // A form or a list only: a kanban, a search or a pivot leaves it out.
        expect(["form", "list", "kanban", "search", "pivot"].filter((t) => fieldTypeFits("json", t))).toEqual([
            "form",
            "list",
        ]);
        addedType = "json";
        await contains(".o_erplibre_studio_new_field[data-type=json]").dragAndDrop(hook("/list", "inside"));
        expect.verifySteps(["apply_operation add_field inside /list"]);
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "x_text");
        expect(".o_erplibre_studio_json_help").toHaveText(
            "Shown read-only: its value comes from code, an import or the API."
        );
    });

    test("the properties relabel a column; apply", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=email]").click();
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "email");
        await contains(".o_erplibre_studio_prop_label").edit("Mail");
        expect.verifySteps([`apply_operation relabel ${EMAIL} Mail`]);
        expect(".o_erplibre_studio_field[data-name=email] .o_erplibre_studio_label").toHaveText("Mail");
        // Apply of the top bar opens the review; its last button applies.
        await contains(".o_erplibre_studio_apply_bar").click();
        expect.verifySteps(["get_review 3"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "review");
        await contains(".o_erplibre_studio_apply").click();
        expect.verifySteps(["project_action action_apply"]);
        expect(".o_erplibre_studio_state").toHaveText("Applied");
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "view");
    });

    test("the debug menu of a form or a list opens the editor", async () => {
        await mountWithCleanup(WebClient);
        await getService("action").doAction({
            name: "Partners",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "list"]],
        });
        await contains(".o_debug_manager button").click();
        await contains(".dropdown-menu .dropdown-item:contains('Customize this view')").click();
        await animationFrame();
        expect.verifySteps(["get_editor_data res.partner false list false"]);
        expect(".o_erplibre_studio").toHaveCount(1);
    });

    test("'New project…' and 'Choose a project…' leave the project", async () => {
        await openEditor();
        for (const value of ["new", ""]) {
            await chooseProject(value);
            await animationFrame();
            expect.verifySteps(["get_editor_data res.partner 7 list false"]);
            expect(".o_erplibre_studio_state").toHaveCount(0);
            expect(".o_erplibre_studio_apply_bar").toHaveCount(0);
            expect(".o_erplibre_studio_new_project").toHaveCount(value === "new" ? 1 : 0);
            expect(".o_erplibre_studio_project_select").toHaveAttribute("data-project", value);
            // Without a project, only the view space opens.
            expect(".o_erplibre_studio_rail_item[data-space=models]").not.toBeEnabled();
            // No edit reaches the former project.
            await contains(".o_erplibre_studio_field[data-name=email]").dragAndDrop(hook(NAME, "before"));
            expect.verifySteps([]);
        }
        await chooseProject("3");
        await animationFrame();
        expect.verifySteps(["get_editor_data res.partner 7 list 3"]);
        expect(".o_erplibre_studio_state").toHaveText("Draft");
    });

    test("the shell: view tabs, the menu of views, Apply and its menu, the rail, the status bar", async () => {
        const entry = (type, label, values = {}) => ({
            type,
            label,
            view_id: false,
            xml_id: false,
            exists: true,
            pending: false,
            editable: true,
            reason: false,
            reason_code: false,
            changes: 0,
            ...values,
        });
        answer = payload([column("name", "Name"), column("email", "Email")], {
            view_list: [
                entry("form", "Form", {view_id: 6, xml_id: "base.view_partner_form"}),
                entry("list", "List", {view_id: 7, xml_id: "base.view_partner_tree", changes: 1}),
                entry("calendar", "Calendar", {
                    exists: false,
                    editable: false,
                    reason: "The studio does not edit Calendar views yet.",
                    reason_code: "not_editable",
                }),
            ],
        });
        answer.project.counts = {
            fields: 0,
            views: 1,
            models: 2,
            access: 3,
            rules: 1,
            groups: 1,
            apps: 0,
            total: 8,
            edited_views: 1,
        };
        await openEditor();
        expect(".o_erplibre_studio_title").toHaveText(/^Contact\s*List$/);
        expect(".o_erplibre_studio_crumbs .o_erplibre_studio_xml_id").toHaveText("base.view_partner_tree");
        expect(".o_erplibre_studio_view_tab").toHaveCount(2);
        expect(".o_erplibre_studio_view_tab[data-view-type=list]").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_view_tab[data-view-type=form]").toHaveAttribute("aria-selected", "false");
        expect(".o_erplibre_studio_view_tab[data-view-type=list] .o_erplibre_studio_view_tab_changes").toHaveText("1");
        expect(".o_erplibre_studio_apply_count").toHaveText("8");
        expect(".o_erplibre_studio_rail_item[data-space=view]").toHaveAttribute("aria-current", "page");
        expect(".o_erplibre_studio_rail_item[data-space=models] .o_erplibre_studio_rail_count").toHaveText("2");
        expect(".o_erplibre_studio_rail_item[data-space=security] .o_erplibre_studio_rail_count").toHaveText("5");
        expect(".o_erplibre_studio_rail_item[data-space=review] .o_erplibre_studio_rail_count").toHaveText("8");
        expect(".o_erplibre_studio_status_state").toHaveText("Draft · 8 unapplied change(s)");
        expect(".o_erplibre_studio_status_applied").toHaveText("Never applied");
        expect(".o_erplibre_studio_undo").toHaveAttribute("aria-label");
        expect(".o_erplibre_studio_preview_toggle").toHaveAttribute("aria-pressed", "false");

        // The menu of the views: those the editor opens, the others with why not.
        await contains(".o_erplibre_studio_add_view").click();
        expect(".o_erplibre_studio_view_menu_open").toHaveCount(2);
        expect(".o_erplibre_studio_view_menu_unavailable[data-reason=not_editable]").toHaveText(
            /Calendar\s*The studio does not edit Calendar views yet\./
        );
        await contains(".o_erplibre_studio_view_menu_open[data-view-type=form]").click();
        expect.verifySteps(["get_editor_data res.partner false form 3"]);

        // The rail: the models, the review, back to the view.
        await contains(".o_erplibre_studio_rail_item[data-space=models]").click();
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "models");
        expect(".o_erplibre_studio_palette").toHaveCount(0);
        expect(".o_erplibre_studio_no_model").toHaveCount(1);
        expect(".o_erplibre_studio_new_model").toHaveCount(1);
        await contains(".o_erplibre_studio_rail_item[data-space=review]").click();
        expect(".o_erplibre_studio_rail_item[data-space=review]").toHaveAttribute("aria-current", "page");
        expect.verifySteps(["get_review 3"]);
        expect(".o_erplibre_studio_review_intro").toHaveText(/0 change\(s\) to apply/);
        await contains(".o_erplibre_studio_rail_item[data-space=view]").click();
        expect(".o_erplibre_studio_palette").toHaveCount(1);

        // The menu of Apply: Revert needs something applied; Discard.
        await contains(".o_erplibre_studio_apply_menu").click();
        expect(".o_erplibre_studio_revert").not.toBeEnabled();
        await contains(".o_erplibre_studio_discard").click();
        expect.verifySteps(["project_action action_discard"]);
        expect(".o_erplibre_studio_discard").toHaveCount(0);
        expect(".o_erplibre_studio_status_state").toHaveText(/Applied/);
    });

    test("an operation waits for the answer of the previous one", async () => {
        await openEditor();
        const hold = new Deferred();
        holdOperation = hold;
        await contains(".o_erplibre_studio_field[data-name=email]").dragAndDrop(hook(NAME, "before"));
        expect.verifySteps([`apply_operation move ${EMAIL} before ${NAME}`]);
        expect(".o_erplibre_studio_canvas").toHaveClass("o_erplibre_studio_busy");
        expect(".o_erplibre_studio_project_select").toHaveAttribute("disabled");
        // A second drop while the first one runs is ignored.
        await contains(".o_erplibre_studio_field[data-name=name]").dragAndDrop(hook("/list", "inside"));
        expect.verifySteps([]);
        holdOperation = null;
        hold.resolve();
        await animationFrame();
        expect(".o_erplibre_studio_canvas").not.toHaveClass("o_erplibre_studio_busy");
        expect(".o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "email");
        // The next operation names the revision of the last answer.
        await contains(".o_erplibre_studio_prop_label").edit("Mail");
        expect.verifySteps([`apply_operation relabel ${EMAIL} Mail`]);
    });

    test("helpers", () => {
        expect(isTrue("True")).toBe(true);
        expect(isTrue("not is_company")).toBe(false);
        expect(textToSelection("a:A\n b \n\nc: C")).toEqual([
            ["a", "A"],
            ["b", "b"],
            ["c", "C"],
        ]);
        expect(selectionToText([["a", "A"]])).toBe("a:A");
        const tree = payload([column("name", "Name")]).blocks;
        expect(findBlock(tree, (b) => b.name === "name").path).toBe(NAME);
        expect(findBlock(tree, (b) => b.name === "none")).toBe(null);
    });
});
