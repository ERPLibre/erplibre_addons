// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryAllTexts} from "@odoo/hoot-dom";
import {advanceTime, animationFrame} from "@odoo/hoot-mock";
import {contains, defineWebModels, getService, mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";

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
 * project, a name without « x_ » breaks the rule, any other name is
 * available; the label proposes « x_sponsor ».
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
            rule: RULE,
        };
    }
    if (!value.startsWith("x_")) {
        return {
            name: value,
            proposed,
            status: "invalid",
            message: RULE.text,
            detail: RULE.detail,
            checks: checks("prefix"),
            rule: RULE,
        };
    }
    return {
        name: value,
        proposed,
        status: "available",
        message: "Available",
        detail: `No field ${value} on Contact nor in the other projects.`,
        checks: checks(null),
        rule: RULE,
    };
}

let answer;
let operations;
// The names ``check_field_name`` was asked about, in order.
let nameChecks;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    operations = [];
    nameChecks = [];
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        const operation = args.args[4];
        operations.push(operation);
        if (operation.type === "rename_field") {
            answer = renamed(answer, operation.field_name, operation.new_name || "x_sponsor", operation.auto);
        } else {
            answer = payload();
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

    test("no change in the view", async () => {
        answer = payload({changes: []});
        await openEditor();
        expect(".o_erplibre_studio_changes_count").toHaveCount(0);
        await contains(TAB_CHANGES).click();
        expect(".o_erplibre_studio_no_change").toHaveCount(1);
        expect(".o_erplibre_studio_changes li").toHaveCount(0);
    });
});
