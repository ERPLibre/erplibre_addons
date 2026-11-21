// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryAllTexts} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {contains, defineWebModels, getService, mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";

const SHEET = "/form/sheet";
const ADDRESS = "//group[@name='address']";
const NOTEBOOK = "/form/sheet/notebook";
const NOTES = "//page[@name='notes']";
const SALES = "//page[@name='sales']";
const named = (name) => `//field[@name='${name}']`;

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
        ],
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
            name: "Contacts",
            module_name: "studio_contacts",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 4,
            item_count: 4,
            counts: {fields: 2, views: 2, total: 4},
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

let answer;
let operations;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    operations = [];
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        operations.push(args.args[4]);
        answer = payload();
        answer.project.revision = args.kwargs.revision + 1;
        return answer;
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
        expect(".o_erplibre_studio_name_help").toHaveText(/created under this name at Apply/);
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
