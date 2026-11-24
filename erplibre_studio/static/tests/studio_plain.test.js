// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryAllTexts, queryOne} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    makeMockEnv,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {changeSentence, hiddenSentence, kindSentence} from "@erplibre_studio/editor/studio_editor";

const MAIN = "//group[@name='main']";
const named = (name) => `//field[@name='${name}']`;

// An invented supplier model: none of these values exists anywhere else.
const FIELDS = {
    name: {string: "Name", type: "char"},
    phone: {string: "Phone", type: "char"},
    mobile: {string: "Mobile", type: "char"},
    email: {string: "Email", type: "char"},
    website: {string: "Website", type: "char"},
    x_tier: {string: "Supplier tier", type: "selection", project: true, pending: true},
};

// The changes of the draft: a new field, a relabel, a required field, a
// hidden one and a move, each with the subject the server reads.
const ADD = 1;
const RELABEL = 2;
const REQUIRED = 3;
const HIDE = 4;
const MOVE = 5;

const subject = (extra) => ({
    label: false,
    tag: "field",
    kind: false,
    anchor: false,
    position: false,
    value: false,
    ...extra,
});

const CHANGES = [
    {
        id: ADD,
        type: "add_field",
        kind: "new",
        summary: "Add a new field: x_tier",
        subject: subject({label: "Supplier tier", anchor: "Email", position: "after"}),
        xpath: named("email"),
        path: named("x_tier"),
        error: false,
    },
    {
        id: RELABEL,
        type: "relabel",
        kind: "renamed",
        summary: `Relabel: ${named("email")} = Work email`,
        subject: subject({label: "Email", value: "Work email"}),
        xpath: named("email"),
        path: named("email"),
        error: false,
    },
    {
        id: REQUIRED,
        type: "required",
        kind: "attribute",
        summary: `Required: ${named("phone")} = True`,
        subject: subject({label: "Phone", value: true}),
        xpath: named("phone"),
        path: named("phone"),
        error: false,
    },
    {
        id: HIDE,
        type: "hide",
        kind: "hidden",
        summary: `Hide or show: ${named("website")} = True`,
        subject: subject({label: "Website", value: true}),
        xpath: named("website"),
        path: named("website"),
        error: false,
    },
    {
        id: MOVE,
        type: "move",
        kind: "moved",
        summary: `Move: ${named("mobile")} → ${named("phone")}`,
        subject: subject({label: "Mobile", anchor: "Phone", position: "after"}),
        xpath: named("phone"),
        path: named("mobile"),
        error: false,
    },
];

function field(name, change = null, extra = {}) {
    return {
        path: named(name),
        tag: "field",
        kind: "field",
        name,
        label: FIELDS[name].string,
        attrs: {},
        movable: true,
        changes: change ? [change.id] : [],
        change_kinds: change ? [change.kind] : [],
        changed: Boolean(change),
        changed_inside: false,
        ...extra,
    };
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
        changed_inside: true,
    };
}

function formBlocks() {
    const [add, relabel, required, hide, move] = CHANGES;
    const main = container(MAIN, "group", [
        field("name"),
        field("phone", required),
        field("mobile", move),
        field("email", relabel, {label: "Work email"}),
        field("x_tier", add),
        field("website", hide, {attrs: {invisible: "True"}}),
    ]);
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
        operations: ["add_field", "add_existing_field", "move", "remove", "hide", "relabel", "required"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: FIELDS,
        palette: [],
        field_types: ["char"],
        changes: CHANGES,
        errors: [],
        project: {
            id: 3,
            name: "Suppliers",
            module_name: "studio_suppliers",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 5,
            item_count: 5,
            app: false,
            models: [],
            access: [],
            rules: [],
            applied: false,
        },
        projects: [{id: 3, name: "Suppliers", module_name: "studio_suppliers", state: "draft"}],
        display_level: "simple",
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        sample_values: {},
        ...extra,
    };
}

let answer;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "set_display_level", (args) => args.args[0]);
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "x_supplier", viewType: "form", viewId: 9}));
    await animationFrame();
}

const DETAILED = ".o_erplibre_studio_level_option[data-level=detailed]";
const TAB_CHANGES = ".o_erplibre_studio_inspector_tab[data-tab=changes]";
const SUMMARIES = ".o_erplibre_studio_changes .o_erplibre_studio_change_summary";
const planRow = (name) => `.o_erplibre_studio_outline_row[data-name=${name}]`;

describe("changeSentence", () => {
    // The translations load with the environment: the sentences are then
    // plain strings.
    beforeEach(() => makeMockEnv());

    const sentence = (change, options = {}) => String(changeSentence(change, {viewType: "form", ...options}));

    test("each type of change in plain words, from the label of its element", () => {
        const of = (type, extra = {}, more = {}) => sentence({type, subject: subject(extra), ...more});
        expect(of("add_field", {label: "Supplier tier"})).toBe("New field Supplier tier");
        expect(of("add_field")).toBe("New field");
        expect(of("add_existing_field", {label: "Phone"})).toBe("Field Phone added");
        expect(of("add_node", {label: "Loyalty", tag: "page", kind: "page"})).toBe("New tab Loyalty");
        expect(of("add_node", {label: "Loyalty", tag: "notebook", kind: "notebook"})).toBe("New tab Loyalty");
        expect(of("add_node", {tag: "group", kind: "group"})).toBe("New group");
        expect(of("add_node", {label: "Terms", tag: "group", kind: "group"})).toBe("New group Terms");
        expect(of("add_node", {tag: "separator", kind: "separator"})).toBe("New separator");
        expect(of("add_node", {label: "Archived", tag: "widget", kind: "widget"})).toBe("New ribbon Archived");
        expect(of("add_node", {label: "Late", tag: "filter", kind: "filter"})).toBe("New filter Late");
        expect(of("add_node", {label: "Tier", tag: "filter", kind: "group_by"})).toBe("New grouping Tier");
        expect(of("add_node", {label: "Odd", tag: "div", kind: "other"})).toBe("New element Odd");
        expect(of("move", {label: "Mobile", anchor: "Phone", position: "after"})).toBe("Mobile moved after Phone");
        expect(of("move", {label: "Mobile", anchor: "Phone", position: "before"})).toBe("Mobile moved before Phone");
        expect(of("move", {label: "Mobile", anchor: "Contact", position: "inside"})).toBe("Mobile moved into Contact");
        expect(of("move", {label: "Mobile", position: "inside"})).toBe("Mobile moved");
        expect(of("hide", {label: "Website", value: true})).toBe("Website hidden in this form");
        expect(of("hide", {label: "Website", value: false})).toBe("Website shown again");
        expect(of("remove", {label: "Late", tag: "filter"})).toBe("Late removed from this view");
        expect(of("relabel", {label: "Email", value: "Work email"})).toBe("Email renamed Work email");
        expect(of("relabel", {label: "Email", value: ""})).toBe("Email takes back its original label");
        expect(of("required", {label: "Phone", value: true})).toBe("Phone becomes required");
        expect(of("required", {label: "Phone", value: false})).toBe("Phone is no longer required");
        expect(of("readonly", {label: "Phone", value: true})).toBe("Phone becomes read-only");
        expect(of("readonly", {label: "Phone", value: false})).toBe("Phone is no longer read-only");
        expect(of("help", {label: "Phone", value: "Dial the area code"})).toBe("New tooltip on Phone");
        expect(of("help", {label: "Phone", value: ""})).toBe("Tooltip of Phone cleared");
        expect(of("optional", {label: "Phone", value: "show"})).toBe("Phone optional, shown by default");
        expect(of("optional", {label: "Phone", value: "hide"})).toBe("Phone optional, hidden by default");
        expect(of("optional", {label: "Phone", value: ""})).toBe("Phone is no longer optional");
        // A set_attribute names the attribute by its label, never by its
        // technical name; the label of the view itself is the view.
        expect(of("set_attribute", {label: "Phone", value: "Call"}, {attribute: "string"})).toBe("Phone renamed Call");
        expect(of("set_attribute", {label: "Phone", value: "phone"}, {attribute: "widget"})).toBe(
            "Phone: setting « Widget » changed"
        );
        expect(of("set_attribute", {tag: "kanban", value: "x_tier"}, {attribute: "default_group_by"})).toBe(
            "View setting « Default grouping » changed"
        );
        expect(of("set_attribute", {label: "Phone", value: "1"}, {attribute: "x_unknown"})).toBe(
            "Phone: a setting changed"
        );
        // The kind of an attribute names it where its name means another
        // thing elsewhere (the type of a graph).
        expect(
            sentence(
                {type: "set_attribute", attribute: "type", subject: subject({tag: "graph", value: "pie"})},
                {settable: {graph: {type: "graph_type"}}}
            )
        ).toBe("View setting « Chart type » changed");
    });

    test("a fallback: the label of the block, the kind, an unknown type", () => {
        // No label in the subject: the block on the canvas names it.
        expect(sentence({type: "required", subject: subject({value: true})}, {label: "Phone"})).toBe(
            "Phone becomes required"
        );
        expect(sentence({type: "required", subject: subject({value: true})})).toBe("An element becomes required");
        // No subject: the kind of the change.
        expect(sentence({type: "hide", kind: "hidden"}, {label: "Website"})).toBe("Website hidden in this form");
        expect(sentence({type: "relabel", kind: "renamed"}, {label: "Town"})).toBe("Town renamed");
        expect(sentence({type: "move", kind: "moved"}, {label: "Mobile"})).toBe("Mobile moved");
        expect(sentence({type: "add_node", kind: "new"}, {label: "Loyalty"})).toBe("New element Loyalty");
        expect(sentence({type: "set_attribute", kind: "attribute"}, {label: "Phone"})).toBe("Phone changed");
        expect(sentence({type: "set_attribute", kind: "attribute"})).toBe("A change of this view");
        // A type of change it does not know names the element only.
        expect(sentence({type: "frobnicate", subject: subject({label: "Phone"})})).toBe("Phone changed");
        expect(sentence({type: "frobnicate", subject: subject()})).toBe("A change of this view");
        expect(String(kindSentence("other", "", "form"))).toBe("A change of this view");
    });

    test("hidden, by the type of the view", () => {
        expect(String(hiddenSentence("Website", "form"))).toBe("Website hidden in this form");
        expect(String(hiddenSentence("Website", "list"))).toBe("Website hidden in this list");
        expect(String(hiddenSentence("Website", "kanban"))).toBe("Website hidden in this view");
    });
});

describe.current.tags("desktop");
describe("plain changes at the Simple level", () => {
    test("the Changes list: sentences at Simple, summary and XPath at Detailed", async () => {
        await openEditor();
        await contains(TAB_CHANGES).click();
        expect(queryAllTexts(SUMMARIES)).toEqual([
            "New field Supplier tier",
            "Email renamed Work email",
            "Phone becomes required",
            "Website hidden in this form",
            "Mobile moved after Phone",
        ]);
        // No XPath, no technical name at the Simple level.
        const panel = queryOne(".o_erplibre_studio_changes").textContent;
        expect(panel).not.toMatch(/\/\/|x_tier|@name/);
        expect(".o_erplibre_studio_change_xpath").toHaveCount(0);
        expect(`.o_erplibre_studio_changes li[data-type=required] .o_erplibre_studio_change_remove`).toHaveAttribute(
            "aria-label",
            "Undo this change: Phone becomes required"
        );
        await contains(DETAILED).click();
        expect(queryAllTexts(SUMMARIES)).toEqual(CHANGES.map((change) => change.summary));
        // The XPath on a line of its own only when the summary does not
        // already hold it: the new field names its anchor, no other.
        expect(".o_erplibre_studio_change_xpath").toHaveCount(1);
        expect(`.o_erplibre_studio_changes li[data-type=add_field] .o_erplibre_studio_change_xpath`).toHaveText(
            named("email")
        );
        expect(`.o_erplibre_studio_changes li[data-type=required] .o_erplibre_studio_change_remove`).toHaveAttribute(
            "aria-label",
            `Undo this change: Required: ${named("phone")} = True`
        );
    });

    test("the note of the selected element in the inspector", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=phone]").click();
        expect(".o_erplibre_studio_inspector_changed").toHaveText(/^Phone becomes required/);
        await contains(".o_erplibre_studio_field[data-name=mobile]").click();
        expect(".o_erplibre_studio_inspector_changed").toHaveText(/^Mobile moved after Phone/);
        await contains(DETAILED).click();
        expect(".o_erplibre_studio_inspector_changed").toHaveText(/^Move: \/\/field\[@name='mobile'\]/);
    });

    test("the Plan: the sentences of a row as its tooltip and for a screen reader", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        const pick = (name) => `${planRow(name)} .o_erplibre_studio_outline_pick`;
        expect(pick("phone")).toHaveAttribute("title", "Phone becomes required");
        expect(`${planRow("phone")} .o_erplibre_studio_outline_dot_text`).toHaveText("Phone becomes required");
        expect(pick("email")).toHaveAttribute("title", "Email renamed Work email");
        expect(pick("website")).toHaveAttribute("title", "Website hidden in this form");
        expect(pick("x_tier")).toHaveAttribute("title", "New field Supplier tier");
        // An unchanged row has no tooltip at the Simple level.
        expect(pick("name")).not.toHaveAttribute("title");
        // The legend calls the ring « hidden » in a form.
        expect(".o_erplibre_studio_outline_legend").toHaveText(
            "Filled dot: added or modified. Ring: hidden. Number: changes folded inside the block."
        );
        // The Detailed level: the technical name, the kind for a reader.
        await contains(DETAILED).click();
        expect(pick("phone")).toHaveAttribute("title", "phone");
        expect(`${planRow("phone")} .o_erplibre_studio_outline_dot_text`).toHaveText("edited");
    });

    test("a view that hides by removing calls the ring « removed »", async () => {
        answer = payload({hide_mode: "remove"});
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        expect(".o_erplibre_studio_outline_legend").toHaveText(
            "Filled dot: added or modified. Ring: removed. Number: changes folded inside the block."
        );
    });

    test("the dialog that undoes a change names it in plain words", async () => {
        onRpc("erplibre.studio.editor", "get_change_removal", (args) => ({
            revision: 0,
            change: {
                id: args.args[1],
                summary: `Required: ${named("phone")} = True`,
                view: "x_supplier.form",
                applied: true,
            },
            refused: false,
            items: [
                {id: MOVE, summary: CHANGES[4].summary, view: "x_supplier.form", view_type: "form", applied: false},
                {
                    id: 99,
                    summary: "Relabel: //field[@name='phone'] = Tel",
                    view: "x_supplier.list",
                    view_type: "list",
                    applied: false,
                },
            ],
            applied: true,
        }));
        await openEditor();
        await contains(TAB_CHANGES).click();
        await contains(`.o_erplibre_studio_changes li[data-type=required] .o_erplibre_studio_change_remove`).click();
        expect(".o_erplibre_studio_change_removal_dialog p:first").toHaveText(
            "Undoing « Phone becomes required » also removes the changes that depend on it:"
        );
        // A change of this view gets its sentence; one of another view
        // keeps its summary.
        expect(queryAllTexts(".o_erplibre_studio_change_removal_item")).toEqual([
            "Mobile moved after Phone · x_supplier.form",
            "Relabel: //field[@name='phone'] = Tel · x_supplier.list",
        ]);
    });
});
