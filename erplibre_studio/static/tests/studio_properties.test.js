// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {advanceTime, animationFrame} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    mountWithCleanup,
    onRpc,
    serverState,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {propertiesField} from "@erplibre_studio/editor/studio_properties";
import {fieldTypeFits} from "@erplibre_studio/editor/studio_relations";

const LEFT = "//group[@name='studio_left']";
const COMMON = ["char", "integer", "float", "boolean", "date", "datetime", "selection", "many2one"];
// The name the server proposes for the definition field it would create.
const PROPOSED = {name: "x_contact_properties", label: "Contact properties"};

function container(path, tag, children, extra = {}) {
    return {path, tag, kind: "container", label: tag, attrs: {}, movable: false, drop: true, children, ...extra};
}

function fieldBlock(name, label) {
    return {path: `//field[@name='${name}']`, tag: "field", kind: "field", name, label, attrs: {}, movable: true};
}

/** The blocks of a contact form, the blocks ``extra`` in its left column. */
function formBlocks(extra = []) {
    return container(
        "/form",
        "form",
        [
            container("/form/sheet", "sheet", [
                container("//group[@name='studio_main']", "group", [
                    container(LEFT, "group", extra),
                    container("//group[@name='studio_right']", "group", []),
                ]),
            ]),
        ],
        {drop: false}
    );
}

/** The editor payload of a contact view of ``viewType`` (form by default). */
function payload({viewType = "form", blocks = formBlocks(), fields = {}, revision = 0} = {}) {
    const list = viewType === "list";
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: viewType,
        view_types: ["form", "list"],
        view: {id: 7, name: `res.partner.${viewType}`, xml_id: false},
        blocks: list ? container("/list", "list", []) : blocks,
        layout: {root: list ? "/list" : "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "hide", "update_field"],
        hide_mode: list ? "column_invisible" : "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        // The view shows no country yet; the model has it.
        fields: {
            name: {string: "Name", type: "char"},
            country_id: {string: "Country", type: "many2one", relation: "res.country"},
            ...fields,
        },
        palette: [],
        field_types: [...COMMON, "text", "json", "properties"],
        changes: [],
        errors: [],
        project: {
            id: 3,
            name: "Contacts",
            module_name: "studio_contacts",
            state: "draft",
            state_label: "Draft",
            revision,
            preview_value: `3:${revision}`,
            change_count: 0,
            item_count: 0,
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
    };
}

/** The containers ``get_properties_choices`` answers: a country, and a new region with a definition field. */
function twoContainers() {
    return [
        {
            name: "country_id",
            label: "Country",
            comodel: "res.country",
            comodel_label: "Country",
            pending: false,
            definitions: [],
            proposed: PROPOSED,
        },
        {
            name: "x_region_id",
            label: "Region",
            comodel: "x_region",
            comodel_label: "Region",
            pending: true,
            definitions: [{name: "x_region_definition", label: "Region properties"}],
            proposed: PROPOSED,
        },
    ];
}

let answer;
let containers;
// The technical names ``check_field_name`` answers « taken » for.
let taken;
let calls;

beforeEach(() => {
    serverState.debug = "1";
    defineWebModels();
    answer = payload();
    containers = twoContainers();
    taken = [];
    calls = [];
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "get_properties_choices", (args) => {
        calls.push({method: "get_properties_choices", args: args.args});
        return {containers};
    });
    onRpc("erplibre.studio.editor", "check_field_name", (args) => {
        const [, model, name] = args.args;
        calls.push({method: "check_field_name", args: [model, name]});
        const isTaken = taken.includes(name);
        return {
            name,
            proposed: false,
            status: isTaken ? "taken" : "available",
            message: isTaken ? `The field ${name} already exists on Country` : "Available",
            detail: "",
            checks: [],
        };
    });
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        const operation = args.args[4];
        calls.push({method: "apply_operation", args: [operation]});
        const field = operation.field;
        const definition = {
            ...field,
            relation: "res.country",
            definition_record_field:
                field.definition_record_field || (field.definition_new && field.definition_new.name),
            help: "",
            readonly: false,
        };
        // The many2one lands before the properties field, in the same change.
        answer = payload({
            revision: 1,
            blocks: formBlocks([fieldBlock("country_id", "Country"), fieldBlock("x_properties", "Properties")]),
            fields: {
                x_properties: {
                    string: "Properties",
                    type: "properties",
                    project: true,
                    pending: true,
                    definition,
                },
            },
        });
        return answer;
    });
});

async function openEditor(viewType = "form") {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType, viewId: 7}));
    await animationFrame();
}

/** Drop the Properties item of the palette into the left column of the form. */
async function dropProperties() {
    await contains(".o_erplibre_studio_more_types").click();
    await contains(".o_erplibre_studio_new_field[data-type=properties]").dragAndDrop(
        `.o_erplibre_studio_hook[data-target="${LEFT}"][data-position=inside]`
    );
    await animationFrame();
}

const methods = () => calls.map((c) => c.method);
const lastCall = (method) => calls.filter((c) => c.method === method).pop();

describe.current.tags("desktop");
describe("erplibre_studio properties field", () => {
    test("Properties: among the other types of a form, never in a list", async () => {
        await openEditor();
        // Not among the common types: under « Show the other types ».
        expect(".o_erplibre_studio_new_field[data-type=properties]").toHaveCount(0);
        await contains(".o_erplibre_studio_more_types").click();
        expect(".o_erplibre_studio_new_field[data-type=properties]").toHaveCount(1);
        expect(".o_erplibre_studio_new_field[data-type=properties]").toHaveText(/Properties/);
        expect(["form", "list", "kanban", "search", "pivot"].filter((t) => fieldTypeFits("properties", t))).toEqual([
            "form",
        ]);
    });

    test("a list leaves Properties out of its palette", async () => {
        answer = payload({viewType: "list"});
        await openEditor("list");
        await contains(".o_erplibre_studio_more_types").click();
        expect(".o_erplibre_studio_new_field[data-type=json]").toHaveCount(1);
        expect(".o_erplibre_studio_new_field[data-type=properties]").toHaveCount(0);
    });

    test("a drop opens the dialog; Create makes the definition field on the comodel", async () => {
        await openEditor();
        await dropProperties();
        expect(".o_erplibre_studio_properties_dialog").toHaveCount(1);
        expect(lastCall("get_properties_choices").args).toEqual([3, "res.partner"]);
        expect(".o_erplibre_studio_properties_container").toHaveCount(2);
        expect("label[for=o_erplibre_studio_container_x_region_id]").toHaveText(
            /Region \(Region\)\s*x_region_id\s*new/
        );
        expect("label[for=o_erplibre_studio_container_country_id]").toHaveText(/Country \(Country\)\s*country_id/);
        expect("label[for=o_erplibre_studio_container_country_id] .badge").toHaveCount(0);
        // The first container is chosen; its comodel has no definition field yet.
        expect("#o_erplibre_studio_container_country_id").toBeChecked();
        expect(".o_erplibre_studio_properties_definition legend").toHaveText(
            "Where the properties are defined on Country"
        );
        expect("#o_erplibre_studio_definition_create").toBeChecked();
        expect("label[for=o_erplibre_studio_definition_create]").toHaveText("Create Contact properties");
        expect(".o_erplibre_studio_properties_new_name").toHaveValue(PROPOSED.name);
        expect(lastCall("check_field_name").args).toEqual(["res.country", PROPOSED.name]);
        expect(".o_erplibre_studio_properties_name_status").toHaveAttribute("data-status", "available");
        expect(".o_erplibre_studio_properties_label").toHaveValue("Properties");
        expect(".o_erplibre_studio_properties_save").toBeEnabled();
        await contains(".o_erplibre_studio_properties_save").click();
        expect(methods()).toEqual(["get_properties_choices", "check_field_name", "apply_operation"]);
        expect(lastCall("apply_operation").args[0]).toEqual({
            type: "add_field",
            target: LEFT,
            position: "inside",
            field: {
                ttype: "properties",
                field_description: "Properties",
                definition_record: "country_id",
                definition_new: {name: PROPOSED.name, field_description: PROPOSED.label},
            },
        });
        expect(".o_erplibre_studio_properties_dialog").toHaveCount(0);
        // The many2one shows as an ordinary block; the new field is selected.
        expect(".o_erplibre_studio_field[data-name=country_id]").toHaveCount(1);
        expect(".o_erplibre_studio_field[data-name=x_properties]").toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_properties_source").toHaveText(
            `Defined on res.country.${PROPOSED.name} through country_id`
        );
    });

    test("an existing definition field: sent by name, no definition_new", async () => {
        await openEditor();
        await dropProperties();
        await contains("#o_erplibre_studio_container_x_region_id").click();
        expect("#o_erplibre_studio_definition_x_region_definition").toBeChecked();
        expect(".o_erplibre_studio_properties_new_name").toHaveCount(0);
        // Create, then back to the existing definition field.
        await contains("#o_erplibre_studio_definition_create").click();
        expect(".o_erplibre_studio_properties_new_name").toHaveValue(PROPOSED.name);
        await contains("#o_erplibre_studio_definition_x_region_definition").click();
        expect("#o_erplibre_studio_definition_x_region_definition").toBeChecked();
        expect(".o_erplibre_studio_properties_new_name").toHaveCount(0);
        await contains(".o_erplibre_studio_properties_label").edit("Region data");
        await contains(".o_erplibre_studio_properties_save").click();
        expect(lastCall("apply_operation").args[0].field).toEqual({
            ttype: "properties",
            field_description: "Region data",
            definition_record: "x_region_id",
            definition_record_field: "x_region_definition",
        });
        expect(
            propertiesField(
                {label: " Notes ", container: "x_region_id", mode: "existing", definition: "x_region_definition"},
                twoContainers()[1]
            )
        ).toEqual({
            ttype: "properties",
            field_description: "Notes",
            definition_record: "x_region_id",
            definition_record_field: "x_region_definition",
        });
    });

    test("no many2one: one sentence, Create disabled", async () => {
        containers = [];
        await openEditor();
        await dropProperties();
        expect(".o_erplibre_studio_properties_empty").toHaveText(
            "Add a many2one field first: the properties are defined on the record it points to."
        );
        expect(".o_erplibre_studio_properties_container").toHaveCount(0);
        expect(".o_erplibre_studio_properties_save").not.toBeEnabled();
    });

    test("a taken name of the definition field disables Create", async () => {
        taken = [PROPOSED.name];
        await openEditor();
        await dropProperties();
        expect(".o_erplibre_studio_properties_name_status").toHaveAttribute("data-status", "taken");
        expect(".o_erplibre_studio_properties_name_status").toHaveText(
            `The field ${PROPOSED.name} already exists on Country`
        );
        expect(".o_erplibre_studio_properties_new_name").toHaveClass("is-invalid");
        expect(".o_erplibre_studio_properties_save").not.toBeEnabled();
        // Another name: checked once the typing pauses, then Create applies.
        await contains(".o_erplibre_studio_properties_new_name").edit("x_contact_fields", {confirm: false});
        expect(".o_erplibre_studio_properties_save").not.toBeEnabled();
        await advanceTime(300);
        await animationFrame();
        expect(lastCall("check_field_name").args).toEqual(["res.country", "x_contact_fields"]);
        expect(".o_erplibre_studio_properties_save").toBeEnabled();
        expect(methods()).not.toInclude("apply_operation");
        // An empty name: the status says what is missing, not « Checking… ».
        await contains(".o_erplibre_studio_properties_new_name").clear({confirm: false});
        await advanceTime(300);
        await animationFrame();
        expect(".o_erplibre_studio_properties_name_status").toHaveAttribute("data-status", "empty");
        expect(".o_erplibre_studio_properties_name_status").toHaveText("Type a technical name.");
        expect(".o_erplibre_studio_properties_save").not.toBeEnabled();
    });
});
