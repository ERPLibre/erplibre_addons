// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryAll, queryAllTexts, queryOne} from "@odoo/hoot-dom";
import {advanceTime, animationFrame} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    makeServerError,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {choiceValue, parseOptions, widgetOptionSpecs} from "@erplibre_studio/editor/studio_widget_options";

const SHEET = "/form/sheet";
const ADDRESS = "//group[@name='address']";
const NOTEBOOK = "/form/sheet/notebook";
const NOTES = "//page[@name='notes']";
const SALES = "//page[@name='sales']";
const named = (name) => `//field[@name='${name}']`;

// The rule of the database (field_name_rule of the payload).
const RULE = {
    prefix_required: true,
    mode: "production",
    label: "Production · x_ required",
    text: "Prefix x_ required on this database",
    detail: "Fields created outside the code carry x_ on a production database.",
};
// The rule of a database with code_generator: a name without « x_ » applies.
const DEVELOPMENT_RULE = {
    prefix_required: false,
    mode: "development",
    label: "Development · x_ optional",
    text: "Without x_ allowed: development database (code_generator)",
    detail: "The generated module defines its fields in its code.",
};

const FIELDS = {
    street: {string: "Street", type: "char"},
    city: {string: "City", type: "char"},
    comment: {string: "Internal notes", type: "html"},
    user_id: {string: "Salesperson", type: "many2one", relation: "res.users"},
    x_sponsor: {
        string: "Sponsor",
        type: "many2one",
        relation: "res.users",
        project: true,
        pending: true,
        name_auto: true,
        definition: {field_description: "Sponsor", relation: "res.users", help: "", readonly: false},
    },
    x_level: {
        string: "Level",
        type: "selection",
        project: true,
        pending: false,
        selection: [["gold", "Gold"]],
        definition: {field_description: "Level", selection: [["gold", "Gold"]], help: "", readonly: false},
    },
};

/** A field block; ``kinds``: the kinds of the draft changes that touch it. */
function field(name, kinds = [], extra = {}) {
    return {
        path: named(name),
        tag: "field",
        kind: "field",
        name,
        label: FIELDS[name].string,
        attrs: {},
        movable: true,
        changes: kinds.length ? [1] : [],
        change_kinds: kinds,
        changed: kinds.length > 0,
        changed_inside: false,
        ...extra,
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
        changed_inside: children.some((child) => child.changed || child.changed_inside),
    };
}

/**
 * A partner form: an address group (the city relabelled) and a notebook
 * whose second page holds a new field of the project.
 */
function formBlocks() {
    const address = container(ADDRESS, "group", "Address", [
        field("street"),
        field("city", ["renamed"], {label: "Town", attrs: {string: "Town"}}),
        field("x_level", ["new"]),
    ]);
    const notes = container(NOTES, "page", "Notes", [field("comment")]);
    const sales = container(SALES, "page", "Sales", [field("user_id"), field("x_sponsor", ["new"])]);
    const notebook = container(NOTEBOOK, "notebook", "notebook", [notes, sales]);
    const sheet = container(SHEET, "sheet", "sheet", [address, notebook]);
    return container("/form", "form", "form", [sheet]);
}

const CHANGES = [
    {id: 1, type: "relabel", kind: "renamed", summary: "Rename City to Town", path: named("city"), error: false},
    {id: 2, type: "add_field", kind: "new", summary: "Add Sponsor", path: named("x_sponsor"), error: false},
    {id: 3, type: "move", kind: "moved", summary: "Move Phone", path: false, error: "No node matches the xpath."},
    {id: 4, type: "remove", kind: "hidden", summary: "Remove Fax", path: false, error: false},
];

function payload(extra = {}) {
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "form",
        view: {id: 9, name: "res.partner.form", xml_id: "base.view_partner_form"},
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: [
            "add_field",
            "add_existing_field",
            "move",
            "remove",
            "hide",
            "relabel",
            "help",
            "readonly",
            "required",
            "update_field",
            "rename_field",
        ],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: JSON.parse(JSON.stringify(FIELDS)),
        field_name_rule: RULE,
        palette: [],
        field_types: ["char"],
        changes: CHANGES,
        errors: [],
        project: {
            id: 3,
            name: "Contacts",
            module_name: "studio_contacts",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 4,
            item_count: 4,
            counts: {fields: 2, views: 2, total: 4, name_blockers: 0},
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

/**
 * ``data`` with its field ``old`` named ``name``: its entry (``name_auto``
 * = ``auto``) and its block.
 */
function renamed(data, old, name, auto) {
    const fields = {};
    for (const [key, info] of Object.entries(data.fields)) {
        fields[key === old ? name : key] = key === old ? {...info, name_auto: auto} : info;
    }
    const rename = (block) => ({
        ...block,
        ...(block.name === old ? {name, path: named(name)} : {}),
        ...(block.children ? {children: block.children.map(rename)} : {}),
    });
    return {...data, fields, blocks: rename(data.blocks)};
}

const NAME_CHECKS = {
    format: "Lower case letters, digits and _",
    reserved: "Not a reserved word of the ORM",
    prefix: "Prefix that fits the rule of the database",
    unique: "Unique on Contact and in the projects",
};

/**
 * The answer of ``check_field_name``: « x_level » is taken by the
 * project, a name without « x_ » breaks the rule when ``rule`` requires
 * the prefix, any other name is available; the label proposes
 * « x_sponsor ».
 */
function checkName(name) {
    const proposed = "x_sponsor";
    const value = name || proposed;
    const checks = (bad) => Object.entries(NAME_CHECKS).map(([key, text]) => ({key, ok: key !== bad, text}));
    if (value === "x_level") {
        return {
            name: value,
            proposed,
            status: "taken",
            message: "x_level is already created by this project",
            detail: "Each new field of the project needs its own name.",
            checks: checks("unique"),
            rule,
        };
    }
    if (rule.prefix_required && !value.startsWith("x_")) {
        return {
            name: value,
            proposed,
            status: "invalid",
            message: rule.text,
            detail: rule.detail,
            checks: checks("prefix"),
            rule,
        };
    }
    return {
        name: value,
        proposed,
        status: "available",
        message: "Available",
        detail: `No field ${value} on Contact nor in the other projects.`,
        checks: checks(null),
        rule,
    };
}

let answer;
// The rule ``check_field_name`` answers with.
let rule;
// ``afterOperation(operation)``: the payload an operation other than a
// rename answers, instead of the initial one; null keeps the initial one.
let afterOperation;
let operations;
// The names ``check_field_name`` was asked about, in order.
let nameChecks;
// ``refuse(operation)``: the message of the error the server answers the
// operation with, or a falsy value to apply it.
let refuse;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    rule = RULE;
    afterOperation = null;
    operations = [];
    nameChecks = [];
    refuse = () => false;
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        const operation = args.args[4];
        operations.push(operation);
        const refused = refuse(operation);
        if (refused) {
            throw makeServerError({message: refused});
        }
        if (operation.type === "rename_field") {
            answer = renamed(answer, operation.field_name, operation.new_name || "x_sponsor", operation.auto);
        } else {
            answer = afterOperation ? afterOperation(operation) : payload();
        }
        answer.project = {...answer.project, revision: args.kwargs.revision + 1};
        return answer;
    });
    onRpc("erplibre.studio.editor", "check_field_name", (args) => {
        expect(args.args[1]).toBe("res.partner");
        nameChecks.push([args.args[2], args.kwargs.field_name]);
        return checkName(args.args[2]);
    });
});

/**
 * ``get_change_removal`` answers ``removal`` (the change asked about plus
 * these values); ``remove_change`` drops the changes it removes from the
 * payload, with the block of « x_sponsor » when « Add Sponsor » goes, and
 * pushes their ids to ``removed``. Both calls are steps.
 */
function mockRemoval(removal, removed) {
    onRpc("erplibre.studio.editor", "get_change_removal", (args) => {
        const id = args.args[1];
        expect.step(`get_change_removal ${id}`);
        const change = CHANGES.find((c) => c.id === id);
        return {
            revision: 0,
            change: {id, summary: change.summary, view: "res.partner.form", view_type: "form", applied: false},
            refused: false,
            ...removal,
        };
    });
    onRpc("erplibre.studio.editor", "remove_change", (args) => {
        const [, id, expected] = args.args;
        expect.step(`remove_change ${id} ${JSON.stringify(expected)} ${args.kwargs.revision}`);
        removed.push(...expected);
        const drop = (block) => ({
            ...block,
            ...(block.children
                ? {
                      children: block.children
                          .filter((child) => !(expected.includes(2) && child.name === "x_sponsor"))
                          .map(drop),
                  }
                : {}),
        });
        answer = payload({changes: CHANGES.filter((c) => !expected.includes(c.id))});
        answer.blocks = drop(answer.blocks);
        answer.project = {...answer.project, revision: args.kwargs.revision + 1};
        return {...answer, removed: expected};
    });
}

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 9}));
    await animationFrame();
}

const TAB_PROPERTIES = ".o_erplibre_studio_inspector_tab[data-tab=properties]";
const TAB_CHANGES = ".o_erplibre_studio_inspector_tab[data-tab=changes]";

describe.current.tags("desktop");
describe("erplibre_studio editor, inspector", () => {
    test("a field: its definition apart from what the view sets", async () => {
        await openEditor();
        expect(TAB_PROPERTIES).toHaveAttribute("aria-selected", "true");
        expect(TAB_CHANGES).toHaveAttribute("aria-selected", "false");
        expect(".o_erplibre_studio_help").toHaveCount(1);

        // A field of an installed module, relabelled by the draft.
        await contains(".o_erplibre_studio_field[data-name=city]").click();
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "city");
        expect(".o_erplibre_studio_inspector_title").toHaveText("Town");
        expect(".o_erplibre_studio_inspector_kind").toHaveText("Existing field · Text");
        expect(".o_erplibre_studio_inspector_changed").toHaveText(/renamed/);
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_label").toHaveValue("Town");
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_name").toHaveValue("city");
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_name").toHaveAttribute("readonly");
        expect(".o_erplibre_studio_name_help").toHaveText(/installed module/);
        // What the view sets on the node: tooltip, required, read-only, hidden.
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_prop_help").toHaveCount(1);
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_prop_required").toHaveCount(1);
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_prop_readonly").toHaveCount(1);
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_prop_hidden").toHaveCount(1);
        expect(".o_erplibre_studio_remove").toHaveCount(1);
        // The label of a field the project does not define relabels the node.
        await contains(".o_erplibre_studio_field_props .o_erplibre_studio_prop_label").edit("City or town");
        expect(operations.pop()).toEqual({type: "relabel", target: named("city"), value: "City or town"});
        // A real label: a click on its text checks the box.
        await contains(".o_erplibre_studio_check:has(.o_erplibre_studio_prop_required)").click();
        expect(operations.pop()).toEqual({type: "required", target: named("city"), value: true});

        // A new field of the project: its definition goes in « Field ».
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        expect(".o_erplibre_studio_inspector_kind").toHaveText("New field · Many2one to res.users");
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_label").toHaveValue("Sponsor");
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_help").toHaveCount(1);
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_readonly").toHaveCount(1);
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_relation").toHaveValue("res.users");
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_relation").toBeEnabled();
        expect(".o_erplibre_studio_name_help").toHaveText(/Frozen at Apply/);
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_prop_help").toHaveCount(0);
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_prop_required").toHaveCount(1);
        await contains(".o_erplibre_studio_field_props .o_erplibre_studio_prop_label").edit("Godparent");
        expect(operations.pop()).toEqual({
            type: "update_field",
            field_name: "x_sponsor",
            field: {field_description: "Godparent"},
        });

        // An applied field of the project: its values, its name in the database.
        await contains(".o_erplibre_studio_field[data-name=x_level]").click();
        expect(".o_erplibre_studio_inspector_kind").toHaveText("New field · Selection");
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_selection").toHaveValue("gold:Gold");
        expect(".o_erplibre_studio_name_help").toHaveText(/in the database/);
    });

    test("a new field of an existing model names its future owner module", async () => {
        const NOTE = ".o_erplibre_studio_owner_note";
        const project = (extra) => ({...payload().project, module_name: "studio_example", ...extra});
        const sponsor = {...FIELDS.x_sponsor, string: "Example", name_auto: false};
        const fields = {...FIELDS, x_studio_example: sponsor};
        const blocks = formBlocks();
        const example = {name: "x_studio_example", path: named("x_studio_example"), label: "Example"};
        // The address group of the sheet holds the new field.
        blocks.children[0].children[0].children.push(field("street", [], example));
        answer = payload({fields, blocks, project: project({module_state: false})});
        await openEditor();
        // A field of an installed module: no note.
        await contains(".o_erplibre_studio_field[data-name=street]").click();
        expect(NOTE).toHaveCount(0);
        // A new field of the project not created yet: its future module.
        await contains(".o_erplibre_studio_field[data-name=x_studio_example]").click();
        expect(NOTE).toHaveAttribute("data-state", "future");
        expect(`${NOTE} .o_erplibre_studio_owner_module`).toHaveText("studio_example");
        expect(NOTE).toHaveText(/^Future owner module\s*studio_example\s*Apply creates it/);
        // An applied field of the project, the module not installed yet.
        await contains(".o_erplibre_studio_field[data-name=x_level]").click();
        expect(NOTE).toHaveAttribute("data-state", "future");
        expect(NOTE).toHaveText(/Apply created it/);

        // The module of the project installed: it holds the field.
        answer = payload({fields, blocks, project: project({module_state: "installed"})});
        await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 9}));
        await animationFrame();
        await contains(".o_erplibre_studio_field[data-name=x_studio_example]").click();
        expect(NOTE).toHaveAttribute("data-state", "owned");
        expect(NOTE).toHaveText(/^Owner module\s*studio_example\s*The module generated/);

        // A view of a model the project creates, not created yet: no note.
        answer = payload({
            fields,
            blocks,
            view: {id: 9, name: "res.partner.form", xml_id: false, pending: true},
            project: project({module_state: false}),
        });
        await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 9}));
        await animationFrame();
        await contains(".o_erplibre_studio_field[data-name=x_studio_example]").click();
        expect(NOTE).toHaveCount(0);
    });

    test("a new field: its technical name, checked live", async () => {
        const NAME = ".o_erplibre_studio_field_props .o_erplibre_studio_prop_name";
        const STATUS = ".o_erplibre_studio_name_status";
        const BLOCKED = "1 technical name(s) block Apply";
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        await animationFrame();
        // A new field not created yet: its name is edited, checked at once.
        expect(nameChecks).toEqual([["x_sponsor", "x_sponsor"]]);
        expect(NAME).toHaveValue("x_sponsor");
        expect(NAME).not.toHaveAttribute("readonly");
        expect(NAME).toHaveAttribute("aria-invalid", "false");
        expect(".o_erplibre_studio_name_tag").toHaveText("auto");
        expect(".o_erplibre_studio_name_rule").toHaveText("Prefix x_ required on this database");
        expect(".o_erplibre_studio_name_rule").toHaveAttribute("data-mode", "production");
        expect(".o_erplibre_studio_name_rule .fa-lock").toHaveCount(1);
        expect(STATUS).toHaveAttribute("role", "status");
        expect(STATUS).toHaveText(/^Available\s*No field x_sponsor on Contact/);
        expect(queryAllTexts(".o_erplibre_studio_name_check_text")).toEqual(Object.values(NAME_CHECKS));
        expect(queryAllTexts(".o_erplibre_studio_name_check_glyph")).toEqual(["✓", "✓", "✓", "✓"]);
        expect(".o_erplibre_studio_name_use").toHaveCount(0);
        expect(".o_erplibre_studio_name_back").toHaveCount(0);
        expect(".o_erplibre_studio_name_help").toHaveText(/^Proposed from the label while it is not edited\./);
        expect(".o_erplibre_studio_apply_bar").toBeEnabled();
        expect(".o_erplibre_studio_name_blockers").toHaveCount(0);

        // Typed: checked once the typing pauses.
        await contains(NAME).edit("sponsor", {confirm: false});
        expect(STATUS).toHaveText("Checking…");
        await advanceTime(300);
        await animationFrame();
        expect(nameChecks.pop()).toEqual(["sponsor", "x_sponsor"]);
        expect(STATUS).toHaveText(/^Prefix x_ required on this database\s*Fields created outside the code/);
        expect(NAME).toHaveAttribute("aria-invalid", "true");
        expect(".o_erplibre_studio_name_check_bad").toHaveAttribute("data-check", "prefix");
        expect(".o_erplibre_studio_name_use").toHaveText("Use x_sponsor");
        // The value that does not apply blocks Apply until it is fixed.
        expect(".o_erplibre_studio_apply_bar").not.toBeEnabled();
        expect(".o_erplibre_studio_apply_bar").toHaveAttribute("title", BLOCKED);
        expect(".o_erplibre_studio_name_blockers").toHaveText(BLOCKED);

        // A name another new field of the project takes: refused on change.
        await contains(NAME).edit("x_level");
        await animationFrame();
        expect(STATUS).toHaveText(/x_level is already created by this project/);
        expect(".o_erplibre_studio_name_check_bad").toHaveAttribute("data-check", "unique");
        expect(operations).toEqual([]);

        // « Use » takes the name the label proposes, which it follows again.
        await contains(".o_erplibre_studio_name_use").click();
        await animationFrame();
        expect(operations.pop()).toEqual({type: "rename_field", field_name: "x_sponsor", new_name: null, auto: true});
        expect(NAME).toHaveValue("x_sponsor");
        expect(STATUS).toHaveText(/^Available/);
        expect(".o_erplibre_studio_apply_bar").toBeEnabled();
        expect(".o_erplibre_studio_name_blockers").toHaveCount(0);

        // A name that applies renames the field on change; it stays selected.
        await contains(NAME).edit("x_godparent");
        await animationFrame();
        expect(operations.pop()).toEqual({
            type: "rename_field",
            field_name: "x_sponsor",
            new_name: "x_godparent",
            auto: false,
        });
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "x_godparent");
        expect(NAME).toHaveValue("x_godparent");
        expect(".o_erplibre_studio_name_tag").toHaveText("edited");
        expect(STATUS).toHaveText(/^Available\s*No field x_godparent/);

        // Back to the name the label proposes.
        expect(".o_erplibre_studio_name_back").toHaveText("Back to the proposed name (x_sponsor)");
        await contains(".o_erplibre_studio_name_back").click();
        await animationFrame();
        expect(operations.pop()).toEqual({type: "rename_field", field_name: "x_godparent", new_name: null, auto: true});
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "x_sponsor");
        expect(NAME).toHaveValue("x_sponsor");
        expect(".o_erplibre_studio_name_tag").toHaveText("auto");
        expect(".o_erplibre_studio_name_back").toHaveCount(0);

        // An applied field of the project and a field of a module: locked.
        const checked = nameChecks.length;
        for (const name of ["x_level", "city"]) {
            await contains(`.o_erplibre_studio_field[data-name=${name}]`).click();
            expect(NAME).toHaveValue(name);
            expect(NAME).toHaveAttribute("readonly");
            expect(".o_erplibre_studio_field_props .input-group-text").toHaveText("locked");
            expect(STATUS).toHaveCount(0);
        }
        expect(nameChecks.length).toBe(checked);
    });

    test("a typed name blocks Apply until the field is renamed to it", async () => {
        const NAME = ".o_erplibre_studio_field_props .o_erplibre_studio_prop_name";
        const STATUS = ".o_erplibre_studio_name_status";
        const BLOCKED = "1 technical name(s) block Apply";
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        await animationFrame();
        // Available, but not the name of the field yet: Apply would write
        // the current one.
        await contains(NAME).edit("x_godparent", {confirm: false});
        await advanceTime(300);
        await animationFrame();
        expect(STATUS).toHaveText(/^Available/);
        expect(".o_erplibre_studio_apply_bar").not.toBeEnabled();
        expect(".o_erplibre_studio_name_blockers").toHaveText(BLOCKED);
        // The server refuses the rename: the input shows the current name.
        refuse = (operation) => operation.type === "rename_field" && "The draft changed meanwhile.";
        await contains(NAME).edit("x_godparent");
        await animationFrame();
        expect(operations.pop()).toEqual({
            type: "rename_field",
            field_name: "x_sponsor",
            new_name: "x_godparent",
            auto: false,
        });
        expect(NAME).toHaveValue("x_sponsor");
        expect(STATUS).toHaveText(/^Available\s*No field x_sponsor/);
        expect(".o_erplibre_studio_apply_bar").toBeEnabled();
        expect(".o_erplibre_studio_name_blockers").toHaveCount(0);
    });

    test("a refused field option shows the value of the draft again", async () => {
        const OPTIONS = ".o_erplibre_studio_field_props .o_erplibre_studio_field_options";
        const withCode = (definition = {}) => {
            const data = payload();
            data.fields.x_code = {
                string: "Code",
                type: "char",
                project: true,
                pending: true,
                name_auto: true,
                definition: {field_description: "Code", help: "", readonly: false, ...definition},
            };
            const address = data.blocks.children[0].children[0];
            address.children.push(field("street", ["new"], {name: "x_code", path: named("x_code"), label: "Code"}));
            return data;
        };
        answer = withCode({size: 30});
        afterOperation = () => withCode({size: 30});
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=x_code]").click();
        const size = `${OPTIONS} .o_erplibre_studio_prop_size`;
        expect(size).toHaveAttribute("max", "10000");
        refuse = () => "The maximum size is a whole number from 1 to 10000.";
        await contains(size).edit("20000");
        await animationFrame();
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_code", field: {size: 20000}});
        expect(size).toHaveValue(30);
        await contains(`${OPTIONS} .o_erplibre_studio_prop_translate`).click();
        await animationFrame();
        expect(`${OPTIONS} .o_erplibre_studio_prop_translate`).not.toBeChecked();
        await contains(`${OPTIONS} .o_erplibre_studio_prop_index`).click();
        await animationFrame();
        expect(`${OPTIONS} .o_erplibre_studio_prop_index`).not.toBeChecked();
        // 0 is no limit: an empty box.
        refuse = () => false;
        afterOperation = () => withCode();
        await contains(size).edit("0");
        await animationFrame();
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_code", field: {size: 0}});
        expect(queryOne(size).value).toBe("");
    });

    test("a development database: a name without x_ applies", async () => {
        const NAME = ".o_erplibre_studio_field_props .o_erplibre_studio_prop_name";
        const STATUS = ".o_erplibre_studio_name_status";
        rule = DEVELOPMENT_RULE;
        answer = payload({field_name_rule: DEVELOPMENT_RULE});
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        await animationFrame();
        expect(".o_erplibre_studio_name_rule").toHaveText(DEVELOPMENT_RULE.text);
        expect(".o_erplibre_studio_name_rule").toHaveAttribute("data-mode", "development");
        expect(".o_erplibre_studio_name_rule .fa-code").toHaveCount(1);
        expect(".o_erplibre_studio_name_rule .fa-lock").toHaveCount(0);

        // A name without « x_ »: available, it renames the field.
        await contains(NAME).edit("texte");
        await animationFrame();
        // Checked as typed, then as the name of the renamed field.
        expect(nameChecks).toEqual([
            ["x_sponsor", "x_sponsor"],
            ["texte", "x_sponsor"],
            ["texte", "texte"],
        ]);
        expect(operations.pop()).toEqual({
            type: "rename_field",
            field_name: "x_sponsor",
            new_name: "texte",
            auto: false,
        });
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "texte");
        expect(NAME).toHaveValue("texte");
        expect(NAME).toHaveAttribute("aria-invalid", "false");
        expect(STATUS).toHaveText(/^Available\s*No field texte on Contact/);
        expect(queryAllTexts(".o_erplibre_studio_name_check_glyph")).toEqual(["✓", "✓", "✓", "✓"]);
        expect(".o_erplibre_studio_apply_bar").toBeEnabled();
        expect(".o_erplibre_studio_name_blockers").toHaveCount(0);
    });

    test("a new many2one: its inverse one2many, what a deletion does", async () => {
        const INVERSE = ".o_erplibre_studio_m2o_inverse";
        // x_sponsor points to the contacts themselves: its inverse is on res.partner.
        const sponsor = (inverse, extra = {}) => {
            const data = payload();
            const info = data.fields.x_sponsor;
            const definition = {...info.definition, relation: "res.partner", on_delete: "set null"};
            if (inverse) {
                definition.inverse_o2m = {name: inverse, field_description: "Contact", relation_field: "x_sponsor"};
            }
            data.fields.x_sponsor = {...info, relation: "res.partner", inverse_protected: false, definition, ...extra};
            return data;
        };
        answer = sponsor(null);
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        await animationFrame();
        expect(`${INVERSE} legend`).toHaveText("Inverse field on res.partner (optional)");
        expect(".o_erplibre_studio_inverse_toggle").not.toBeChecked();
        expect(".o_erplibre_studio_inverse_toggle").toBeEnabled();
        expect(".o_erplibre_studio_inverse_label").toHaveCount(0);
        expect(`${INVERSE} .o_erplibre_studio_prop_name`).toHaveCount(0);
        // What a deletion of the linked record does, « set null » by default.
        expect(".o_erplibre_studio_prop_on_delete legend").toHaveText("On deletion of the linked record");
        expect(".o_erplibre_studio_on_delete").toHaveCount(3);
        expect(".o_erplibre_studio_on_delete[value='set null']").toBeChecked();
        expect(queryAllTexts(".o_erplibre_studio_prop_on_delete label .fw-bold")).toEqual([
            "Empty the field",
            "Block the deletion",
            "Delete as well",
        ]);
        // Refused by the server: the choice and the toggle of the draft.
        refuse = () => "The draft changed meanwhile.";
        await contains(".o_erplibre_studio_on_delete[value=restrict]").click();
        await animationFrame();
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_sponsor", field: {on_delete: "restrict"}});
        expect(".o_erplibre_studio_on_delete[value='set null']").toBeChecked();
        expect(".o_erplibre_studio_on_delete[value=restrict]").not.toBeChecked();
        await contains(".o_erplibre_studio_inverse_toggle").click();
        await animationFrame();
        operations.pop();
        expect(".o_erplibre_studio_inverse_toggle").not.toBeChecked();
        refuse = () => false;
        await contains(".o_erplibre_studio_on_delete[value=restrict]").click();
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_sponsor", field: {on_delete: "restrict"}});

        // Checked: the server names and labels the one2many.
        afterOperation = () => sponsor("x_contact_ids");
        await contains(".o_erplibre_studio_inverse_toggle").click();
        await animationFrame();
        expect(operations.pop()).toEqual({
            type: "update_field",
            field_name: "x_sponsor",
            field: {inverse_o2m: {create: true}},
        });
        expect(".o_erplibre_studio_inverse_toggle").toBeChecked();
        expect(".o_erplibre_studio_inverse_label").toHaveValue("Contact");
        expect(`${INVERSE} .o_erplibre_studio_prop_name`).toHaveValue("x_contact_ids");
        expect(`${INVERSE} .o_erplibre_studio_name_tag`).toHaveCount(0);
        expect(`${INVERSE} .o_erplibre_studio_name_help`).toHaveText("Creates a one2many « Contact »: same prefix rule.");
        expect(nameChecks.map((item) => item.join(" "))).toInclude("x_contact_ids x_contact_ids");

        // Its label and its name go through the definition of the many2one.
        await contains(".o_erplibre_studio_inverse_label").edit("Godchildren");
        expect(operations.pop()).toEqual({
            type: "update_field",
            field_name: "x_sponsor",
            field: {inverse_o2m: {name: "x_contact_ids", field_description: "Godchildren"}},
        });
        await contains(`${INVERSE} .o_erplibre_studio_prop_name`).edit("x_godchildren_ids");
        await animationFrame();
        expect(nameChecks.pop()).toEqual(["x_godchildren_ids", "x_contact_ids"]);
        expect(operations.pop()).toEqual({
            type: "update_field",
            field_name: "x_sponsor",
            field: {inverse_o2m: {name: "x_godchildren_ids", field_description: "Contact"}},
        });
        // A name that does not apply is not sent.
        await contains(`${INVERSE} .o_erplibre_studio_prop_name`).edit("godchildren");
        await animationFrame();
        expect(`${INVERSE} .o_erplibre_studio_prop_name`).toHaveAttribute("aria-invalid", "true");
        expect(operations).toEqual([]);

        // Unchecked: the one2many leaves the draft.
        afterOperation = () => sponsor(null);
        await contains(".o_erplibre_studio_inverse_toggle").click();
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_sponsor", field: {inverse_o2m: false}});
        expect(".o_erplibre_studio_inverse_label").toHaveCount(0);
    });

    test("a many2one to a model the studio adds no field to: no inverse", async () => {
        answer = payload();
        answer.fields.x_sponsor.inverse_protected = true;
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        expect(".o_erplibre_studio_m2o_inverse legend").toHaveText("Inverse field on res.users (optional)");
        expect(".o_erplibre_studio_inverse_toggle").not.toBeEnabled();
        expect(".o_erplibre_studio_inverse_protected").toHaveText("The studio does not add fields to this model.");
        expect(".o_erplibre_studio_prop_on_delete").toHaveCount(1);
    });

    test("a new field: translatable, indexed, maximum size until Apply", async () => {
        const OPTIONS = ".o_erplibre_studio_field_props .o_erplibre_studio_field_options";
        // x_code: a new char of the project in the address group, not created yet.
        const withCode = (definition = {}) => {
            const data = payload();
            data.fields.x_code = {
                string: "Code",
                type: "char",
                project: true,
                pending: true,
                name_auto: true,
                definition: {field_description: "Code", help: "", readonly: false, ...definition},
            };
            const address = data.blocks.children[0].children[0];
            address.children.push(field("street", ["new"], {name: "x_code", path: named("x_code"), label: "Code"}));
            return data;
        };
        answer = withCode();
        afterOperation = () => withCode({translate: true});
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=x_code]").click();
        expect(`${OPTIONS} .o_erplibre_studio_prop_translate`).toBeEnabled();
        expect(`${OPTIONS} .o_erplibre_studio_prop_index`).toBeEnabled();
        expect(`${OPTIONS} .o_erplibre_studio_prop_size`).toBeEnabled();
        expect(queryOne(`${OPTIONS} .o_erplibre_studio_prop_size`).value).toBe("");
        expect(".o_erplibre_studio_options_help").toHaveCount(0);
        await contains(`${OPTIONS} .o_erplibre_studio_prop_translate`).click();
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_code", field: {translate: true}});
        // A translatable field takes no index.
        expect(`${OPTIONS} .o_erplibre_studio_prop_translate`).toBeChecked();
        expect(`${OPTIONS} .o_erplibre_studio_prop_index`).not.toBeEnabled();
        afterOperation = () => withCode({translate: true, size: 30});
        await contains(`${OPTIONS} .o_erplibre_studio_prop_size`).edit("30");
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_code", field: {size: 30}});
        expect(`${OPTIONS} .o_erplibre_studio_prop_size`).toHaveValue(30);
        await contains(`${OPTIONS} .o_erplibre_studio_prop_size`).clear();
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_code", field: {size: 0}});

        // Indexed, then translatable: the index goes.
        afterOperation = () => withCode({index: true});
        await contains(`${OPTIONS} .o_erplibre_studio_prop_translate`).click();
        operations.pop();
        expect(`${OPTIONS} .o_erplibre_studio_prop_index`).toBeChecked();
        await contains(`${OPTIONS} .o_erplibre_studio_prop_translate`).click();
        expect(operations.pop()).toEqual({
            type: "update_field",
            field_name: "x_code",
            field: {translate: true, index: false},
        });

        // A many2one takes an index only.
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        expect(`${OPTIONS} .o_erplibre_studio_prop_index`).toBeEnabled();
        expect(`${OPTIONS} .o_erplibre_studio_prop_translate`).toHaveCount(0);
        expect(`${OPTIONS} .o_erplibre_studio_prop_size`).toHaveCount(0);

        // A field created by Apply: the column exists, its options are frozen.
        await contains(".o_erplibre_studio_field[data-name=x_level]").click();
        expect(`${OPTIONS} .o_erplibre_studio_prop_index`).not.toBeEnabled();
        expect(".o_erplibre_studio_options_help").toHaveText("Set before Apply only: the column exists.");
    });

    test("a geometry field: one palette item, its shape until Apply, a note", async () => {
        const GEO = ["geo_point", "geo_multi_point", "geo_line", "geo_multi_line", "geo_polygon", "geo_multi_polygon"];
        // x_area: a new point of the project in the address group.
        const withArea = ({ttype = "geo_point", pending = true, missing = true} = {}) => {
            const data = payload({field_types: ["char", ...GEO], geo_view_missing: missing});
            data.fields.x_area = {
                string: "Area",
                type: ttype,
                project: true,
                pending,
                name_auto: true,
                definition: {ttype, field_description: "Area", help: "", readonly: false},
            };
            const address = data.blocks.children[0].children[0];
            address.children.push(field("street", ["new"], {name: "x_area", path: named("x_area"), label: "Area"}));
            return data;
        };
        answer = withArea();
        afterOperation = () => withArea();
        await openEditor();
        // The six types are one item that drops a point.
        expect(".o_erplibre_studio_new_field").toHaveCount(2);
        expect(".o_erplibre_studio_new_field[data-type=geo_point]").toHaveAttribute("title", "Geometry");
        await contains(".o_erplibre_studio_new_field[data-type=geo_point]").click();
        expect(operations.pop()).toMatchObject({
            type: "add_field",
            field: {ttype: "geo_point", field_description: "Geometry"},
        });

        await contains(".o_erplibre_studio_field[data-name=x_area]").click();
        expect(".o_erplibre_studio_inspector_kind").toHaveText("New field · Point");
        expect(".o_erplibre_studio_field_options").toHaveCount(0);
        expect(queryAllTexts(".o_erplibre_studio_prop_shape option")).toEqual([
            "Point",
            "Multi-point",
            "Polyline",
            "Multi-polyline",
            "Polygon",
            "Multi-polygon",
        ]);
        expect(".o_erplibre_studio_prop_shape").toHaveValue("geo_point");
        expect(".o_erplibre_studio_geo_note").toHaveText(
            "The map of Area needs a GeoEngine view with a raster layer on Contact: add one (Add a view) once the field is applied."
        );
        afterOperation = () => withArea({ttype: "geo_polygon"});
        await contains(".o_erplibre_studio_prop_shape").select("geo_polygon");
        expect(operations.pop()).toEqual({type: "update_field", field_name: "x_area", field: {ttype: "geo_polygon"}});
        expect(".o_erplibre_studio_prop_shape").toHaveValue("geo_polygon");
        expect(".o_erplibre_studio_inspector_kind").toHaveText("New field · Polygon");

        // Applied, with a GeoEngine view: the shape is frozen, no note.
        afterOperation = () => withArea({ttype: "geo_polygon", pending: false, missing: false});
        await contains(".o_erplibre_studio_prop_help").edit("Where it is");
        operations.pop();
        expect(".o_erplibre_studio_prop_shape").not.toBeEnabled();
        expect(".o_erplibre_studio_shape_help").toHaveText("Set before Apply only: the column exists.");
        expect(".o_erplibre_studio_geo_note").toHaveCount(0);
    });

    test("the documents tree of dms_field: palette item, Display, template note", async () => {
        const DMS = "dms_directory_ids";
        // The DMS directories of the contacts, in the Notes tab once
        // dropped (``dropped``); ``template``: dms_template of the layout.
        const withDms = ({dropped = false, mode = "dms_list", template = false} = {}) => {
            const data = payload({
                operations: [...payload().operations, "set_attribute"],
                settable: {field: {widget: "widget", mode: "x2many_mode"}},
                layout: {
                    root: "/form",
                    dms_template: template,
                    dms_template_action: "dms_field.action_dms_field_template",
                },
                palette: dropped
                    ? []
                    : [{name: DMS, string: "Documents (DMS)", type: "one2many", special: "dms_list"}],
            });
            data.fields[DMS] = {string: "DMS Directories", type: "one2many", relation: "dms.directory"};
            if (dropped) {
                const notes = data.blocks.children[0].children[1].children[0];
                notes.children.push({
                    ...field("comment"),
                    name: DMS,
                    path: named(DMS),
                    label: "DMS Directories",
                    attrs: mode ? {mode, nolabel: "1"} : {nolabel: "1"},
                });
            }
            return data;
        };
        answer = withDms();
        afterOperation = () => withDms({dropped: true});
        await openEditor();

        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        const item = `.o_erplibre_studio_existing_field[data-name=${DMS}]`;
        expect(item).toHaveText(/Documents \(DMS\)/);
        await contains(item).click();
        const drop = operations.pop();
        expect(drop).toMatchObject({type: "add_existing_field", field_name: DMS, special: "dms_list"});
        // Right in a tab or in the sheet, never in a group.
        const parents = {
            [named("comment")]: NOTES,
            [named("user_id")]: SALES,
            [named("x_sponsor")]: SALES,
            [ADDRESS]: SHEET,
            [NOTEBOOK]: SHEET,
        };
        const container = drop.position === "inside" ? drop.target : parents[drop.target];
        expect([NOTES, SALES, SHEET]).toInclude(container);

        // The drop selects the field: List or Documents tree, and the
        // missing template.
        expect(`.o_erplibre_studio_field[data-name=${DMS}]`).toHaveClass("o_erplibre_studio_selected");
        const display = ".o_erplibre_studio_settable[data-attribute=mode]";
        expect(`${display} label`).toHaveText(/^Display/);
        expect(queryAllTexts(".o_erplibre_studio_prop_x2many_mode option")).toEqual(["List", "Documents tree"]);
        expect(".o_erplibre_studio_prop_x2many_mode").toHaveValue("dms_list");
        expect(".o_erplibre_studio_dms_template_note").toHaveText(
            "No embedded DMS template for this model: the tree stays empty until one exists. Open the DMS templates"
        );
        afterOperation = () => withDms({dropped: true, mode: ""});
        await contains(".o_erplibre_studio_prop_x2many_mode").select("");
        expect(operations.pop()).toEqual({type: "set_attribute", target: named(DMS), attribute: "mode", value: ""});
        expect(".o_erplibre_studio_prop_x2many_mode").toHaveValue("");

        patchWithCleanup(getService("action"), {
            async doAction(action) {
                expect.step(`doAction ${action}`);
            },
        });
        await contains(".o_erplibre_studio_dms_template_open").click();
        expect.verifySteps(["doAction dms_field.action_dms_field_template"]);

        // With a template, no note; another field has no Display.
        afterOperation = () => withDms({dropped: true, template: true});
        await contains(".o_erplibre_studio_prop_x2many_mode").select("dms_list");
        operations.pop();
        expect(".o_erplibre_studio_prop_x2many_mode").toHaveValue("dms_list");
        expect(".o_erplibre_studio_dms_template_note").toHaveCount(0);
        await contains(".o_erplibre_studio_field[data-name=comment]").click();
        expect(".o_erplibre_studio_prop_x2many_mode").toHaveCount(0);
    });

    test("the names the server counts block Apply", async () => {
        answer = payload();
        answer.project.counts.name_blockers = 2;
        await openEditor();
        expect(".o_erplibre_studio_name_blockers").toHaveText("2 technical name(s) block Apply");
        expect(".o_erplibre_studio_apply_bar").not.toBeEnabled();
        expect(".o_erplibre_studio_apply_bar").toHaveAttribute("title", "2 technical name(s) block Apply");
    });

    test("a container: what it holds, read-only", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        await contains(`.o_erplibre_studio_outline_row[data-path="${ADDRESS}"] .o_erplibre_studio_outline_pick`).click();
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-kind", "container");
        expect(".o_erplibre_studio_inspector_title").toHaveText("Group « Address »");
        expect(".o_erplibre_studio_inspector_kind").toHaveText("Group · 3 field(s)");
        expect(".o_erplibre_studio_contents").toHaveText("Contents · Street, Town, Level");
        expect(".o_erplibre_studio_field_props").toHaveCount(0);
        // Nothing to edit in it but its visibility.
        expect(".o_erplibre_studio_container_props input").toHaveCount(0);

        await contains(`.o_erplibre_studio_outline_row[data-path="${NOTEBOOK}"] .o_erplibre_studio_outline_pick`).click();
        expect(".o_erplibre_studio_inspector_kind").toHaveText("Tabs · 2 tab(s)");
        expect(".o_erplibre_studio_contents").toHaveText("Contents · Notes, Sales");
    });

    test("the changes of the view: a count, the errors, a click reveals the block", async () => {
        await openEditor();
        expect(".o_erplibre_studio_changes_count").toHaveText("4");
        expect(".o_erplibre_studio_changes").toHaveCount(0);
        await contains(TAB_CHANGES).click();
        expect(TAB_CHANGES).toHaveAttribute("aria-selected", "true");
        expect(TAB_PROPERTIES).toHaveAttribute("aria-selected", "false");
        expect(".o_erplibre_studio_changes li").toHaveCount(4);
        expect(".o_erplibre_studio_changes li[data-type=add_field]").toHaveAttribute("data-kind", "new");
        expect(queryAllTexts(".o_erplibre_studio_change_kind")).toEqual([
            "View · renamed",
            "Field · new",
            "View · moved",
            "View · hidden",
        ]);
        expect(queryAllTexts(".o_erplibre_studio_change_number")).toEqual(["1", "2", "3", "4"]);
        // A change in error says why, and the canvas has no block for it.
        expect(".o_erplibre_studio_changes li[data-type=move]").toHaveClass("o_erplibre_studio_change_failed");
        expect(".o_erplibre_studio_changes li[data-type=move] .o_erplibre_studio_change_error").toHaveText(
            "No node matches the xpath."
        );
        expect(".o_erplibre_studio_change_pick").toHaveCount(2);
        expect(".o_erplibre_studio_changes li[data-type=remove] .o_erplibre_studio_change_unplaced").toHaveCount(1);

        // A click selects the block, shows its page, and the properties.
        await contains(".o_erplibre_studio_changes li[data-type=add_field] .o_erplibre_studio_change_pick").click();
        expect(TAB_PROPERTIES).toHaveAttribute("aria-selected", "true");
        expect(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).toHaveClass("active");
        expect(".o_erplibre_studio_field[data-name=x_sponsor]").toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "x_sponsor");
        // The note of a changed block leads back to the list.
        await contains(".o_erplibre_studio_show_changes").click();
        expect(TAB_CHANGES).toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_changes li[data-type=add_field] .o_erplibre_studio_change_pick").toHaveClass(
            "o_erplibre_studio_change_selected"
        );
        // A click on the canvas shows the properties again.
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        expect(TAB_PROPERTIES).toHaveAttribute("aria-selected", "true");

        // The review of the whole project is one click away.
        await contains(TAB_CHANGES).click();
        await contains(".o_erplibre_studio_open_review").click();
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "review");
    });

    test("a field of a form: widget, domain and groups under Advanced", async () => {
        const advanced = (extra = {}) => {
            const data = payload({
                settable: {
                    field: {widget: "widget", options: "field_options", domain: "field_domain", groups: "groups"},
                },
                operations: [...payload().operations, "set_attribute"],
                // « More options » folds at the Simple level.
                display_level: "simple",
                ...extra,
            });
            return data;
        };
        /** ``data`` with the attributes ``attrs`` on the block of the field ``name``. */
        const withAttrs = (data, name, attrs) => {
            const set = (block) => ({
                ...block,
                ...(block.name === name ? {attrs: {...block.attrs, ...attrs}} : {}),
                ...(block.children ? {children: block.children.map(set)} : {}),
            });
            return {...data, blocks: set(data.blocks)};
        };
        const choiceCalls = [];
        onRpc("erplibre.studio.editor", "get_studio_choices", (args) => {
            choiceCalls.push(args.args[0]);
            return {
                groups: [
                    {id: 2, name: "Settings / Administration", xml_id: "base.group_system", category: false},
                    {
                        id: false,
                        line_id: 5,
                        name: "Desk / Agent",
                        xml_id: "studio_contacts.group_desk_agent",
                        project: true,
                        applied: false,
                    },
                ],
                menus: [],
                apps: [],
                models: [],
                taken_models: [],
                icons: [],
            };
        });
        answer = advanced();
        afterOperation = () => advanced();
        await openEditor();

        // A selection field: the widget goes under « Advanced », closed.
        await contains(".o_erplibre_studio_field[data-name=x_level]").click();
        expect(".o_erplibre_studio_field_advanced_toggle").toHaveAttribute("aria-expanded", "false");
        expect(".o_erplibre_studio_field_advanced").toHaveCount(0);
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_settable").toHaveCount(0);
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        expect(".o_erplibre_studio_field_advanced_toggle").toHaveAttribute("aria-expanded", "true");
        expect(choiceCalls).toEqual([3]);
        const widget = ".o_erplibre_studio_field_advanced .o_erplibre_studio_settable[data-attribute=widget] select";
        expect(`${widget} option[value=radio]`).toHaveCount(1);
        expect(`${widget} option[value=many2many_tags]`).toHaveCount(0);
        // No domain on a field that is not relational.
        expect(".o_erplibre_studio_prop_domain").toHaveCount(0);
        await contains(widget).select("radio");
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("x_level"),
            attribute: "widget",
            value: "radio",
        });
        // Still open on the same field after the operation.
        expect(".o_erplibre_studio_field_advanced").toHaveCount(1);

        // A many2one: its domain, the groups it shows for.
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        expect(".o_erplibre_studio_field_advanced").toHaveCount(0);
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        expect(".o_erplibre_studio_prop_domain").toHaveCount(1);
        expect(".o_erplibre_studio_prop_domain").toHaveAttribute("placeholder", "[('active', '=', True)]");
        await contains(".o_erplibre_studio_prop_domain").edit("[('share', '=', False)]");
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "domain",
            value: "[('share', '=', False)]",
        });
        expect(".o_erplibre_studio_group_chip").toHaveCount(0);
        expect("#o_erplibre_studio_group_list option").toHaveCount(1);
        expect(".o_erplibre_studio_groups_pending").toHaveText(/Desk \/ Agent/);
        // A group of the project not applied yet is not sent.
        await contains(".o_erplibre_studio_prop_groups").edit("Desk / Agent");
        expect(operations).toEqual([]);
        expect(".o_notification").toHaveCount(1);

        afterOperation = () => withAttrs(advanced(), "user_id", {groups: "base.group_system"});
        await contains(".o_erplibre_studio_prop_groups").edit("Settings / Administration");
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "groups",
            value: ["base.group_system"],
        });
        expect(".o_erplibre_studio_group_chip").toHaveCount(1);
        expect(".o_erplibre_studio_group_chip").toHaveText("Settings / Administration");
        // The canvas flags the restriction at the Detailed level only.
        expect(".o_erplibre_studio_field[data-name=user_id] [data-flag=groups]").toHaveCount(0);
        afterOperation = () => advanced();
        await contains(".o_erplibre_studio_group_remove").click();
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "groups",
            value: [],
        });
        expect(".o_erplibre_studio_group_chip").toHaveCount(0);
    });

    test("the domain of a field in the visual editor", async () => {
        const advanced = () =>
            payload({
                settable: {
                    field: {widget: "widget", options: "field_options", domain: "field_domain", groups: "groups"},
                },
                operations: [...payload().operations, "set_attribute"],
                // « More options » folds at the Simple level.
                display_level: "simple",
            });
        onRpc("erplibre.studio.editor", "get_studio_choices", () => ({
            groups: [],
            menus: [],
            apps: [],
            models: [],
            taken_models: [],
            icons: [],
        }));
        answer = advanced();
        afterOperation = () => advanced();
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        // The text mode stays beside the button.
        expect(".o_erplibre_studio_prop_domain").toHaveCount(1);
        expect(".o_erplibre_studio_domain_visual").toBeEnabled();
        await contains(".o_erplibre_studio_domain_visual").click();
        expect(".o_dialog .o_domain_selector").toHaveCount(1);
        expect(".o_dialog .o_erplibre_studio_domain_hint").toHaveCount(1);
        await contains(".o_dialog .o_domain_selector_debug_container textarea").edit('[("share", "=", False)]');
        await contains(".o_erplibre_studio_domain_confirm").click();
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "domain",
            value: '[("share", "=", False)]',
        });
        expect(".o_dialog").toHaveCount(0);

        // A refusal shows in the dialog, which stays open. The field stays
        // selected after the operation.
        refuse = () => "The domain does not apply: x";
        await contains(".o_erplibre_studio_domain_visual").click();
        await contains(".o_dialog .o_domain_selector_debug_container textarea").edit('[("login", "=", "a")]');
        await contains(".o_erplibre_studio_domain_confirm").click();
        expect(operations.pop().value).toBe('[("login", "=", "a")]');
        expect(".o_erplibre_studio_domain_error").toHaveText("The domain does not apply: x");
        expect(".o_dialog").toHaveCount(1);
        // An empty domain removes the attribute.
        refuse = () => false;
        await contains(".o_dialog .o_domain_selector_debug_container textarea").edit("[]");
        expect(".o_erplibre_studio_domain_error").toHaveCount(0);
        await contains(".o_erplibre_studio_domain_confirm").click();
        expect(operations.pop().value).toBe("");
        expect(".o_dialog").toHaveCount(0);
    });

    test("the visual domain editor waits for the comodel of the project", async () => {
        const data = payload({
            settable: {
                field: {widget: "widget", options: "field_options", domain: "field_domain", groups: "groups"},
            },
            operations: [...payload().operations, "set_attribute"],
            // « More options » folds at the Simple level.
            display_level: "simple",
        });
        data.fields.x_sponsor.relation = "x_desk";
        data.fields.x_sponsor.definition.relation = "x_desk";
        data.project.models = [{id: 8, model: "x_desk", name: "Desk", applied: false, views: {}}];
        onRpc("erplibre.studio.editor", "get_studio_choices", () => ({
            groups: [],
            menus: [],
            apps: [],
            models: [],
            taken_models: [],
            icons: [],
        }));
        answer = data;
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        expect(".o_erplibre_studio_prop_domain").toHaveCount(1);
        expect(".o_erplibre_studio_domain_visual").not.toBeEnabled();
        expect(".o_erplibre_studio_domain_visual").toHaveAttribute(
            "title",
            "Apply the model first: the visual editor reads its fields."
        );
    });

    test("raw options under Advanced", async () => {
        const advanced = () =>
            payload({
                settable: {
                    field: {widget: "widget", options: "field_options", domain: "field_domain", groups: "groups"},
                },
                operations: [...payload().operations, "set_attribute"],
                // « More options » folds at the Simple level.
                display_level: "simple",
            });
        /** ``data`` with the options ``text`` on the field user_id. */
        const withOptions = (data, text) => {
            const set = (block) => ({
                ...block,
                ...(block.name === "user_id" ? {attrs: {...block.attrs, options: text}} : {}),
                ...(block.children ? {children: block.children.map(set)} : {}),
            });
            return {...data, blocks: set(data.blocks)};
        };
        onRpc("erplibre.studio.editor", "get_studio_choices", () => ({
            groups: [],
            menus: [],
            apps: [],
            models: [],
            taken_models: [],
            icons: [],
        }));
        answer = advanced();
        afterOperation = () => withOptions(advanced(), "{'no_create': True}");
        await openEditor();
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        const OPTIONS = ".o_erplibre_studio_field_advanced .o_erplibre_studio_prop_options";
        // The form of the options first, the text on demand.
        expect(OPTIONS).toHaveCount(0);
        expect(".o_erplibre_studio_options_raw_toggle").toHaveAttribute("aria-pressed", "false");
        await contains(".o_erplibre_studio_options_raw_toggle").click();
        expect(".o_erplibre_studio_options_raw_toggle").toHaveAttribute("aria-pressed", "true");
        expect(OPTIONS).toHaveCount(1);
        expect(OPTIONS).toHaveAttribute("placeholder", '{"no_create": true}');
        // Right under the widget.
        expect(
            queryAll(".o_erplibre_studio_field_advanced .o_erplibre_studio_settable").map((el) => el.dataset.attribute)
        ).toEqual(["widget", "options", "domain", "groups"]);
        await contains(OPTIONS).edit('{"no_create": true}');
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "options",
            value: '{"no_create": true}',
        });
        // The draft writes the Python form of the options.
        expect(OPTIONS).toHaveValue("{'no_create': True}");
        // A refused text: the textarea shows the draft again.
        refuse = () => "uid is not a set of options: a dictionary of fixed values is needed.";
        await contains(OPTIONS).edit("{'domain': uid}");
        await animationFrame();
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "options",
            value: "{'domain': uid}",
        });
        expect(OPTIONS).toHaveValue("{'no_create': True}");
    });

    test("widget options: the metadata of the registry", () => {
        const tags = widgetOptionSpecs("many2many_tags", "many2many", "form");
        expect(tags.find((spec) => spec.name === "color_field").scope).toBe("comodel");
        expect(tags.find((spec) => spec.name === "no_create").scope).toBe(null);
        const money = widgetOptionSpecs(false, "monetary", "list");
        expect(money.find((spec) => spec.name === "currency_field").scope).toBe("record");
        // A field option of the comodel without relatedFields.
        const status = widgetOptionSpecs("statusbar", "many2one", "form");
        expect(status.find((spec) => spec.name === "fold_field").scope).toBe("comodel");
        // An unknown widget falls back to the widget of the type.
        expect(widgetOptionSpecs("x_unknown_widget", "many2one", "form").map((spec) => spec.name)).toInclude(
            "no_open"
        );
        expect(choiceValue("[0,90]")).toEqual([0, 90]);
        expect(choiceValue("md")).toBe("md");
        expect(parseOptions("")).toEqual({ok: true, options: {}});
        expect(parseOptions('{"no_create": true}')).toEqual({ok: true, options: {no_create: true}});
        expect(parseOptions("{'size': [0, 90], 'zoom_delay': -5}")).toEqual({
            ok: true,
            options: {size: [0, 90], zoom_delay: -5},
        });
        expect(parseOptions("{'no_create': context.get('x')}").ok).toBe(false);
        expect(parseOptions("{'domain': uid}").ok).toBe(false);
        expect(parseOptions("[1, 2]").ok).toBe(false);
    });

    test("widget options: a form from the widget metadata", async () => {
        const SETTABLE = {
            field: {widget: "widget", options: "field_options", domain: "field_domain", groups: "groups"},
        };
        const AMOUNT = {...field("street"), name: "x_amount", path: named("x_amount"), label: "Amount"};
        /**
         * The payload with a monetary field « x_amount » in the address
         * group, and ``attrs``: field name -> attributes of its block.
         */
        const advanced = (attrs = {}) => {
            const set = (block) => {
                let next = attrs[block.name] ? {...block, attrs: {...block.attrs, ...attrs[block.name]}} : block;
                if (next.children) {
                    const children = next.path === ADDRESS ? [...next.children, AMOUNT] : next.children;
                    next = {...next, children: children.map(set)};
                }
                return next;
            };
            const data = payload({
                settable: SETTABLE,
                operations: [...payload().operations, "set_attribute"],
                // « More options » folds at the Simple level.
                display_level: "simple",
            });
            data.fields.x_amount = {string: "Amount", type: "monetary"};
            data.fields.currency_id = {string: "Currency", type: "many2one", relation: "res.currency"};
            return {...data, blocks: set(data.blocks)};
        };
        onRpc("erplibre.studio.editor", "get_studio_choices", () => ({
            groups: [],
            menus: [],
            apps: [],
            models: [],
            taken_models: [],
            icons: [],
        }));
        const OPTION = (name) => `.o_erplibre_studio_field_advanced .o_erplibre_studio_option[data-option=${name}]`;
        let attrs = {x_level: {widget: "radio"}, city: {options: "{'no_create': context.get('x')}"}};
        answer = advanced(attrs);
        afterOperation = () => advanced(attrs);
        await openEditor();

        // A selection shown as radio buttons: the options of radio.
        await contains(".o_erplibre_studio_field[data-name=x_level]").click();
        expect(".o_erplibre_studio_field_advanced").toHaveCount(1);
        expect(`${OPTION("horizontal")} input[type=checkbox]`).toHaveCount(1);
        expect(`${OPTION("horizontal")} input`).not.toBeChecked();
        expect(".o_erplibre_studio_prop_options").toHaveCount(0);
        await contains(`${OPTION("horizontal")} input`).check();
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("x_level"),
            attribute: "options",
            value: {horizontal: true},
            option_fields: {},
        });

        // A many2one without a widget: the options of many2one.
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        expect(OPTION("no_open")).toHaveCount(1);
        attrs = {...attrs, user_id: {options: "{'no_open': True, 'x_custom': 1}"}};
        await contains(`${OPTION("no_open")} input`).check();
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "options",
            value: {no_open: true},
            option_fields: {},
        });
        expect(`${OPTION("no_open")} input`).toBeChecked();
        // A key the widget does not list shows apart; its button removes it.
        expect(".o_erplibre_studio_option_unknown").toHaveCount(1);
        expect(".o_erplibre_studio_option_unknown").toHaveText("x_custom");
        attrs = {...attrs, user_id: {options: "{'no_open': True}"}};
        await contains(".o_erplibre_studio_option_unknown_remove").click();
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "options",
            value: {no_open: true},
            option_fields: {},
        });
        expect(".o_erplibre_studio_option_unknown").toHaveCount(0);
        // Unchecked: the last option leaves, the attribute goes.
        attrs = {...attrs, user_id: {}};
        await contains(`${OPTION("no_open")} input`).uncheck();
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("user_id"),
            attribute: "options",
            value: "",
            option_fields: {},
        });

        // A monetary: its currency field, a many2one of the record.
        await contains(".o_erplibre_studio_field[data-name=x_amount]").click();
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        const currency = `${OPTION("currency_field")} select`;
        expect(`${currency} option[value=currency_id]`).toHaveCount(1);
        expect(`${currency} option[value=user_id]`).toHaveCount(1);
        // Neither a field not created yet nor a field of another type.
        expect(`${currency} option[value=x_sponsor]`).toHaveCount(0);
        expect(`${currency} option[value=city]`).toHaveCount(0);
        attrs = {...attrs, x_amount: {options: "{'currency_field': 'currency_id'}"}};
        await contains(currency).select("currency_id");
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("x_amount"),
            attribute: "options",
            value: {currency_field: "currency_id"},
            option_fields: {currency_field: "record"},
        });
        expect(currency).toHaveValue("currency_id");
        // The currency is not in the view: the record would not load it.
        expect(`${OPTION("currency_field")} .o_erplibre_studio_option_missing`).toHaveCount(1);

        // Options that hold an expression: the text only.
        await contains(".o_erplibre_studio_field[data-name=city]").click();
        expect(".o_erplibre_studio_field_advanced").toHaveCount(1);
        expect(".o_erplibre_studio_prop_options").toHaveValue("{'no_create': context.get('x')}");
        expect(".o_erplibre_studio_options_raw_toggle").toHaveCount(0);
        expect(".o_erplibre_studio_options_note").toHaveText("These options hold expressions: edit them as text.");
        expect(".o_erplibre_studio_option").toHaveCount(0);
    });

    test("widget options: switch, number, text and list choices of an image", async () => {
        const PHOTO = {...field("street"), name: "x_photo", path: named("x_photo"), label: "Photo"};
        let options = "";
        /** The payload with an image field « x_photo » holding ``options``. */
        const withPhoto = () => {
            const attrs = {widget: "image", ...(options ? {options} : {})};
            const set = (block) => {
                if (block.path === ADDRESS) {
                    return {...block, children: [...block.children, {...PHOTO, attrs}]};
                }
                return block.children ? {...block, children: block.children.map(set)} : block;
            };
            const data = payload({
                settable: {field: {widget: "widget", options: "field_options"}},
                operations: [...payload().operations, "set_attribute"],
            });
            data.fields.x_photo = {string: "Photo", type: "binary"};
            return {...data, blocks: set(data.blocks)};
        };
        answer = withPhoto();
        afterOperation = () => withPhoto();
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=x_photo]").click();
        const OPTION = (name) => `.o_erplibre_studio_field_advanced .o_erplibre_studio_option[data-option=${name}]`;
        const sent = () => operations.pop().value;
        // A switch whose default is on shows on while the key is absent.
        expect(`${OPTION("reload")} input`).toBeChecked();
        options = "{'reload': False}";
        await contains(`${OPTION("reload")} input`).uncheck();
        expect(sent()).toEqual({reload: false});
        expect(`${OPTION("reload")} input`).not.toBeChecked();
        // Back to its default: the key leaves.
        options = "";
        await contains(`${OPTION("reload")} input`).check();
        expect(sent()).toBe("");
        // A number.
        options = "{'zoom_delay': 300}";
        await contains(`${OPTION("zoom_delay")} input[type=number]`).edit("300");
        expect(sent()).toEqual({zoom_delay: 300});
        expect(`${OPTION("zoom_delay")} input`).toHaveValue(300);
        // A text, kept next to the number.
        options = "{'accepted_file_extensions': '.png', 'zoom_delay': 300}";
        await contains(`${OPTION("accepted_file_extensions")} input`).edit(".png");
        expect(sent()).toEqual({zoom_delay: 300, accepted_file_extensions: ".png"});
        // A choice written as a list is sent as a list, and shows chosen.
        options = "{'accepted_file_extensions': '.png', 'size': [0, 90], 'zoom_delay': 300}";
        await contains(`${OPTION("size")} select`).select("[0,90]");
        expect(sent()).toEqual({zoom_delay: 300, accepted_file_extensions: ".png", size: [0, 90]});
        expect(`${OPTION("size")} select`).toHaveValue("[0,90]");
        // « Default » removes the key.
        options = "{'accepted_file_extensions': '.png', 'zoom_delay': 300}";
        await contains(`${OPTION("size")} select`).select("");
        expect(sent()).toEqual({zoom_delay: 300, accepted_file_extensions: ".png"});
        // The help of an option is its title, not a line of text.
        expect(OPTION("zoom_delay")).toHaveAttribute("title", /milliseconds/);
    });

    test("a change of the Changes tab is undone on its own", async () => {
        const removed = [];
        mockRemoval({items: [], applied: false}, removed);
        await openEditor();
        // The new field is selected: its block leaves with the change.
        await contains(TAB_CHANGES).click();
        await contains(".o_erplibre_studio_changes li[data-type=add_field] .o_erplibre_studio_change_pick").click();
        expect(".o_erplibre_studio_field[data-name=x_sponsor]").toHaveClass("o_erplibre_studio_selected");
        await contains(TAB_CHANGES).click();
        expect(".o_erplibre_studio_change_remove").toHaveCount(4);
        // No button inside a button: each one sits beside its change.
        expect(".o_erplibre_studio_change_item .o_erplibre_studio_change_remove").toHaveCount(0);
        expect(".o_erplibre_studio_changes li[data-type=add_field] .o_erplibre_studio_change_remove").toHaveAttribute(
            "aria-label",
            "Undo this change: Add Sponsor"
        );
        await contains(".o_erplibre_studio_changes li[data-type=add_field] .o_erplibre_studio_change_remove").click();
        // A change that leaves alone and that no Apply wrote goes at once.
        expect.verifySteps(["get_change_removal 2", "remove_change 2 [2] 0"]);
        expect(".o_erplibre_studio_change_removal_dialog").toHaveCount(0);
        expect(removed).toEqual([2]);
        expect(".o_erplibre_studio_changes li").toHaveCount(3);
        expect(".o_erplibre_studio_field[data-name=x_sponsor]").toHaveCount(0);
        // The selection left with its block.
        await contains(TAB_PROPERTIES).click();
        expect(".o_erplibre_studio_properties").toHaveCount(0);
        expect(".o_erplibre_studio_help").toHaveCount(1);
    });

    test("undoing a change with dependents asks first and lists them", async () => {
        const removed = [];
        mockRemoval(
            {
                items: [
                    {id: 2, summary: "Add Sponsor", view: "res.partner.form", view_type: "form", applied: false},
                    {id: 4, summary: "Remove Fax", view: "res.partner.list", view_type: "list", applied: true},
                ],
                applied: true,
            },
            removed
        );
        await openEditor();
        await contains(TAB_CHANGES).click();
        await contains(".o_erplibre_studio_changes li[data-type=relabel] .o_erplibre_studio_change_remove").click();
        expect.verifySteps(["get_change_removal 1"]);
        expect(".o_erplibre_studio_change_removal_dialog").toHaveCount(1);
        expect(".o_erplibre_studio_change_removal_dialog p").toHaveText(
            "Undoing « Rename City to Town » also removes the changes that depend on it:"
        );
        expect(queryAllTexts(".o_erplibre_studio_change_removal_item")).toEqual([
            "Add Sponsor · res.partner.form",
            "Remove Fax · res.partner.list · applied",
        ]);
        expect(".o_erplibre_studio_change_removal_applied").toHaveCount(1);
        expect(".o_erplibre_studio_change_removal_confirm").toHaveText("Undo 3 changes");
        // « Cancel » would read « Annuler » in French, as the action does.
        expect(".o_erplibre_studio_change_removal_cancel").toHaveText("Change nothing");
        await contains(".o_erplibre_studio_change_removal_cancel").click();
        expect(".o_erplibre_studio_change_removal_dialog").toHaveCount(0);
        expect.verifySteps([]);

        await contains(".o_erplibre_studio_changes li[data-type=relabel] .o_erplibre_studio_change_remove").click();
        await contains(".o_erplibre_studio_change_removal_confirm").click();
        // The server checks the list the user saw.
        expect.verifySteps(["get_change_removal 1", "remove_change 1 [1,2,4] 0"]);
        expect(".o_erplibre_studio_change_removal_dialog").toHaveCount(0);
        expect(removed).toEqual([1, 2, 4]);
    });

    test("an applied change that leaves alone asks first", async () => {
        mockRemoval({items: [], applied: true}, []);
        await openEditor();
        await contains(TAB_CHANGES).click();
        await contains(".o_erplibre_studio_changes li[data-type=remove] .o_erplibre_studio_change_remove").click();
        expect.verifySteps(["get_change_removal 4"]);
        expect(".o_erplibre_studio_change_removal_item").toHaveCount(0);
        expect(".o_erplibre_studio_change_removal_applied").toHaveText(
            "This change is applied: Apply then removes it from the database."
        );
        expect(".o_erplibre_studio_change_removal_confirm").toHaveText("Undo the change");
        await contains(".o_erplibre_studio_change_removal_confirm").click();
        expect.verifySteps(["remove_change 4 [4] 0"]);
    });

    test("a refused undo notifies and removes nothing", async () => {
        mockRemoval({items: [], applied: false, refused: "Another one2many takes the inverse of this one."}, []);
        await openEditor();
        await contains(TAB_CHANGES).click();
        await contains(".o_erplibre_studio_changes li[data-type=add_field] .o_erplibre_studio_change_remove").click();
        expect.verifySteps(["get_change_removal 2"]);
        expect(".o_notification").toHaveText(/Another one2many takes the inverse of this one\./);
        expect(".o_erplibre_studio_change_removal_dialog").toHaveCount(0);
        expect(".o_erplibre_studio_changes li").toHaveCount(4);
    });

    test("the changed note of a block undoes its single change", async () => {
        mockRemoval({items: [], applied: false}, []);
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=city]").click();
        expect(".o_erplibre_studio_inspector_changed .o_erplibre_studio_show_changes").toHaveCount(1);
        expect(".o_erplibre_studio_undo_block_change").toHaveText("Undo this change");
        await contains(".o_erplibre_studio_undo_block_change").click();
        expect.verifySteps(["get_change_removal 1", "remove_change 1 [1] 0"]);
        expect(".o_erplibre_studio_changes_count").toHaveText("3");
    });

    test("the changed note of a block with two changes undoes none", async () => {
        // The note does not guess which change to undo.
        const twice = (block) => ({
            ...block,
            ...(block.name === "city" ? {changes: [1, 2]} : {}),
            ...(block.children ? {children: block.children.map(twice)} : {}),
        });
        answer = {...payload(), blocks: twice(payload().blocks)};
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=city]").click();
        expect(".o_erplibre_studio_inspector_changed").toHaveCount(1);
        expect(".o_erplibre_studio_undo_block_change").toHaveCount(0);
    });

    test("no change in the view", async () => {
        answer = payload({changes: []});
        await openEditor();
        expect(".o_erplibre_studio_changes_count").toHaveCount(0);
        await contains(TAB_CHANGES).click();
        expect(".o_erplibre_studio_no_change").toHaveCount(1);
        expect(".o_erplibre_studio_changes li").toHaveCount(0);
    });
});
