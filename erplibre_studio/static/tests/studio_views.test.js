// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryOne} from "@odoo/hoot-dom";
import {animationFrame, mockTimeZone} from "@odoo/hoot-mock";
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
import {conditionValue, pivotAxes, pivotLanes, searchColumns} from "@erplibre_studio/editor/studio_editor";

const CARD = "//t[@t-name='card']";
const named = (tag, name) => `//${tag}[@name='${name}']`;

const FIELDS = {
    name: {string: "Name", type: "char", store: true, searchable: true, groupable: true},
    email: {string: "Email", type: "char", store: true, searchable: true, groupable: true},
    phone: {string: "Phone", type: "char", store: true, searchable: true, groupable: true},
    vat: {string: "Tax ID", type: "char", store: true, searchable: true, groupable: true},
    active: {string: "Active", type: "boolean", store: true, searchable: true, groupable: true},
    country_id: {string: "Country", type: "many2one", store: true, searchable: true, groupable: true},
    create_date: {string: "Created on", type: "datetime", store: true, searchable: true, groupable: true},
    color: {string: "Color", type: "integer", store: true, searchable: true, groupable: true, aggregator: "sum"},
    partner_latitude: {string: "Latitude", type: "float", store: true, groupable: false, aggregator: "sum"},
    comment: {string: "Notes", type: "html", store: true, searchable: true, groupable: false},
};

const OPERATIONS = {
    kanban: [
        "add_field",
        "add_existing_field",
        "add_widget",
        "move",
        "remove",
        "hide",
        "set_attribute",
        "update_field",
    ],
    search: ["add_existing_field", "add_filter", "add_group_by", "add_separator", "move", "remove", "hide", "relabel"],
    pivot: ["add_existing_field", "move", "remove", "hide", "relabel", "set_attribute"],
    timeline: ["add_existing_field", "move", "remove", "hide", "set_attribute"],
};

const CHOICES = {
    group_field: [
        ["country_id", "Country"],
        ["name", "Name"],
    ],
    relation_group_field: [["country_id", "Country"]],
    date_field: [["create_date", "Created on"]],
    number_field: [["color", "Color"]],
    search_field: [
        ["active", "Active"],
        ["create_date", "Created on"],
        ["phone", "Phone"],
        ["vat", "Tax ID"],
    ],
    bool: [
        ["True", "True"],
        ["False", "False"],
    ],
    interval: ["day", "week", "month", "quarter", "year"].map((i) => [i, i]),
    timeline_mode: ["day", "week", "month", "fit"].map((m) => [m, m]),
    axis: ["row", "col", "measure"].map((a) => [a, a]),
};

function field(path, name, extra = {}) {
    return {path, tag: "field", kind: "field", name, label: FIELDS[name].string, attrs: {}, movable: true, ...extra};
}

function container(path, tag, children, extra = {}) {
    return {path, tag, kind: "container", label: tag, attrs: {}, movable: true, drop: true, children, ...extra};
}

/** The payload of the editor on a res.partner view of ``viewType``. */
function payload(viewType, blocks, extra = {}) {
    const palette = Object.entries(FIELDS)
        .filter(([name]) => !JSON.stringify(blocks).includes(`"name":"${name}"`))
        .map(([name, info]) => ({name, string: info.string, type: info.type}));
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: viewType,
        view_types: ["form", "list", "kanban", "search", "pivot", "timeline"],
        view: {id: 12, name: `res.partner.${viewType}`, xml_id: `base.partner_${viewType}`},
        blocks,
        layout: {root: blocks.path},
        operations: OPERATIONS[viewType],
        hide_mode: ["search", "pivot"].includes(viewType) ? "remove" : "invisible",
        settable: {},
        required_attributes: {},
        choices: CHOICES,
        fields: FIELDS,
        palette,
        field_types: ["char", "integer"],
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

function kanbanPayload(cardChildren, rootAttrs = {}) {
    const card = {
        path: CARD,
        tag: "t",
        kind: "template",
        label: "card",
        attrs: {"t-name": "card"},
        movable: false,
        drop: true,
        in_template: true,
        chain: null,
        template: "card",
        children: cardChildren,
    };
    const blocks = container(
        "/kanban",
        "kanban",
        [
            field("//field[@name='active']", "active", {movable: false, in_template: false, chain: null}),
            container("/kanban/templates", "templates", [card], {drop: false, movable: false, in_template: false}),
        ],
        {drop: false, movable: false, attrs: rootAttrs}
    );
    return payload("kanban", blocks, {
        layout: {
            root: "/kanban",
            card: CARD,
            templates: {card: CARD},
            loaded_fields: ["active"],
            widgets: {web_ribbon: ["title", "bg_color", "tooltip"]},
        },
        settable: {
            kanban: {default_group_by: "group_field", quick_create: "bool"},
            field: {widget: "widget"},
        },
    });
}

const inCard = (name, extra = {}) => field(named("field", name), name, {in_template: true, chain: null, ...extra});

function searchPayload({fields = ["name", "email"], filters = [], groupBys = []} = {}) {
    const children = fields.map((name) => field(named("field", name), name));
    children.push({
        path: "/search/separator[1]",
        tag: "separator",
        kind: "separator",
        label: "separator",
        attrs: {},
        movable: true,
    });
    for (const [name, label, domain] of filters) {
        children.push({
            path: named("filter", name),
            tag: "filter",
            kind: "filter",
            name,
            label,
            domain,
            attrs: {string: label},
            movable: true,
        });
    }
    const group = groupBys.map(([name, label, groupBy]) => ({
        path: named("filter", name),
        tag: "filter",
        kind: "group_by",
        name,
        label,
        group_by: groupBy,
        attrs: {string: label},
        movable: true,
    }));
    children.push(container(named("group", "group_by"), "group", group));
    return payload("search", container("/search", "search", children, {movable: false}), {
        layout: {
            root: "/search",
            operators: {
                char: ["ilike", "not ilike", "=", "!=", "set", "not set"],
                boolean: ["=", "!="],
                datetime: [">", "<", "set", "not set"],
            },
        },
    });
}

function pivotPayload(axes) {
    const children = [];
    const layout = {root: "/pivot", axes: {row: [], col: [], measure: []}, others: []};
    for (const [name, axis] of axes) {
        children.push(field(named("field", name), name, {axis, interval: null, attrs: {type: axis}}));
        layout.axes[axis].push(named("field", name));
    }
    const data = payload("pivot", container("/pivot", "pivot", children, {movable: false}), {
        layout,
        settable: {pivot: {disable_linking: "bool"}, field: {type: "axis", interval: "interval"}},
    });
    data.palette = data.palette
        .map((item) => ({...item, axes: pivotAxes(FIELDS[item.name])}))
        .filter((item) => item.axes.length);
    return data;
}

function timelinePayload(attrs, loaded = ["name"]) {
    const item = {
        path: "//t[@t-name='timeline-item']",
        tag: "t",
        kind: "template",
        label: "timeline-item",
        attrs: {},
        movable: false,
        drop: true,
        in_template: true,
        chain: null,
        template: "timeline-item",
        children: [inCard("name")],
    };
    const children = loaded.map((name, index) =>
        field(`/timeline/field[${index + 1}]`, name, {movable: false, in_template: false, chain: null})
    );
    children.push(
        container("/timeline/templates", "templates", [item], {drop: false, movable: false, in_template: false})
    );
    return payload("timeline", container("/timeline", "timeline", children, {movable: false, attrs}), {
        layout: {
            root: "/timeline",
            template: item.path,
            loaded_fields: loaded,
            colors: [],
            color_operators: ["==", "!=", ">", "<"],
            color_types: ["char", "integer", "boolean", "date"],
        },
        settable: {
            timeline: {
                date_start: "date_field",
                default_group_by: "relation_group_field",
                mode: "timeline_mode",
                colors: "colors",
            },
        },
        required_attributes: {timeline: ["date_start", "default_group_by"]},
    });
}

// The payload the editor loads, and how an operation answers.
let answer;
let respond;
let operations;

beforeEach(() => {
    serverState.debug = "1";
    webModels.ResPartner._views = {
        "kanban,12": `<kanban><templates><t t-name="card"><field name="name"/></t></templates></kanban>`,
        "search,44": `<search><field name="name"/></search>`,
    };
    defineWebModels();
    operations = [];
    respond = () => answer;
    onRpc("erplibre.studio.editor", "get_editor_data", (args) => {
        expect.step(`get_editor_data ${args.args.slice(0, 4).join(" ")}`);
        return answer;
    });
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        const operation = args.args[4];
        operations.push(operation);
        expect.step(`apply_operation ${operation.type}`);
        answer = respond(operation);
        answer.project = {...answer.project, revision: args.kwargs.revision + 1};
        return answer;
    });
});

async function openEditor(viewType) {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType, viewId: 12}));
    await animationFrame();
    expect.verifySteps([`get_editor_data res.partner 12 ${viewType} false`]);
}

function hook(target, position, zone = "") {
    return `.o_erplibre_studio_hook[data-target="${target}"][data-position=${position}][data-zone="${zone}"]`;
}

describe.current.tags("desktop");
describe("erplibre_studio editor, kanban", () => {
    test("the card shows, a drag reorders it, the palette adds to it", async () => {
        answer = kanbanPayload([inCard("name"), inCard("email")]);
        await openEditor("kanban");
        expect(".o_erplibre_studio_card .o_erplibre_studio_field").toHaveCount(2);
        // The field the view only loads stays where it is.
        expect(".o_erplibre_studio_loaded .o_erplibre_studio_field[data-name=active]").toHaveAttribute(
            "draggable",
            "false"
        );
        expect(".o_erplibre_studio_palette [data-tab=new]").toHaveCount(1);

        respond = () => kanbanPayload([inCard("email"), inCard("name")]);
        await contains(".o_erplibre_studio_card .o_erplibre_studio_field[data-name=email]").dragAndDrop(
            hook(named("field", "name"), "before")
        );
        expect.verifySteps(["apply_operation move"]);
        expect(operations.pop()).toEqual({
            type: "move",
            source: named("field", "email"),
            target: named("field", "name"),
            position: "before",
        });
        expect(".o_erplibre_studio_card .o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "email");
        expect(".o_erplibre_studio_field[data-name=email]").toHaveClass("o_erplibre_studio_selected");

        respond = () => kanbanPayload([inCard("email"), inCard("name"), inCard("phone")]);
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        await contains(".o_erplibre_studio_existing_field[data-name=phone]").dragAndDrop(hook(CARD, "inside"));
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: CARD,
            position: "inside",
            field_name: "phone",
        });
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "phone");
        expect(".o_erplibre_studio_settable[data-attribute=widget]").toHaveCount(1);

        // A ribbon from the « Other » tab.
        await contains(".o_erplibre_studio_palette [data-tab=other]").click();
        await contains(".o_erplibre_studio_ribbon_title").edit("VIP");
        await contains(".o_erplibre_studio_widget[data-widget=web_ribbon]").dragAndDrop(
            hook(named("field", "name"), "before")
        );
        expect.verifySteps(["apply_operation add_widget"]);
        expect(operations.pop()).toEqual({
            type: "add_widget",
            target: named("field", "name"),
            position: "before",
            widget: "web_ribbon",
            attrs: {title: "VIP", bg_color: "text-bg-success"},
        });
    });

    test("no hook inside a t-if chain; the view properties set an attribute", async () => {
        const chain = (path, role, children) =>
            container(path, "t", children, {in_template: true, chain: role, movable: false, label: `t-${role}`});
        answer = kanbanPayload([
            chain(`${CARD}/t[1]`, "if", [inCard("name")]),
            chain(`${CARD}/t[2]`, "else", [inCard("email")]),
        ]);
        await openEditor("kanban");
        expect(hook(`${CARD}/t[1]`, "before")).toHaveCount(1);
        expect(hook(`${CARD}/t[2]`, "before")).toHaveCount(0);
        expect(
            ".o_erplibre_studio_container[data-path=\"//t[@t-name='card']/t[2]\"] > .o_erplibre_studio_container_title"
        ).toHaveAttribute("draggable", "false");

        // Nothing selected: the properties of the view.
        expect(".o_erplibre_studio_view_properties").toHaveAttribute("data-tag", "kanban");
        respond = (operation) => {
            const data = kanbanPayload(answer.blocks.children[1].children[0].children, {
                default_group_by: operation.value,
            });
            data.changes = [{id: 1, type: "set_attribute", summary: "Default grouping", error: false}];
            return data;
        };
        await contains(".o_erplibre_studio_settable[data-attribute=default_group_by] select").select("country_id");
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/kanban",
            attribute: "default_group_by",
            value: "country_id",
        });
        expect(".o_erplibre_studio_settable[data-attribute=default_group_by] select").toHaveValue("country_id");
        expect(".o_erplibre_studio_changes li[data-type=set_attribute]").toHaveCount(1);
    });

    test("the debug menu of a kanban view and its search view open the editor", async () => {
        answer = kanbanPayload([inCard("name")]);
        await mountWithCleanup(WebClient);
        await getService("action").doAction({
            name: "Partners",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[12, "kanban"]],
            search_view_id: [44, "search"],
        });
        await contains(".o_debug_manager button").click();
        await contains(".dropdown-menu .dropdown-item:contains('Customize this view')").click();
        await animationFrame();
        expect.verifySteps(["get_editor_data res.partner 12 kanban false"]);
        expect(".o_erplibre_studio[data-view-type=kanban]").toHaveCount(1);

        answer = searchPayload();
        await contains(".o_erplibre_studio_close").click();
        await contains(".o_debug_manager button").click();
        await contains(".dropdown-menu .dropdown-item:contains('Customize the search view')").click();
        await animationFrame();
        expect.verifySteps(["get_editor_data res.partner 44 search false"]);
        expect(".o_erplibre_studio[data-view-type=search]").toHaveCount(1);
    });
});

describe("erplibre_studio editor, search", () => {
    test("three columns; the palette adds a field and a grouping", async () => {
        answer = searchPayload({
            filters: [["type_company", "Companies", "[('is_company', '=', True)]"]],
            groupBys: [["salesperson", "Salesperson", "user_id"]],
        });
        await openEditor("search");
        expect("[data-column=fields] .o_erplibre_studio_field").toHaveCount(2);
        expect("[data-column=filters] .o_erplibre_studio_field").toHaveCount(2);
        expect("[data-column=filters] .o_erplibre_studio_field[data-kind=separator]").toHaveCount(1);
        expect("[data-column=group_bys] .o_erplibre_studio_field[data-kind=group_by]").toHaveCount(1);
        expect(".o_erplibre_studio_palette [data-tab=new]").toHaveCount(0);
        expect(".o_erplibre_studio_interval").toHaveValue("month");

        await contains(".o_erplibre_studio_existing_field[data-name=phone]").dragAndDrop(
            hook(named("field", "email"), "after", "fields")
        );
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: named("field", "email"),
            position: "after",
            field_name: "phone",
        });

        await contains(".o_erplibre_studio_interval").select("year");
        await contains(".o_erplibre_studio_existing_field[data-name=create_date]").dragAndDrop(
            hook(named("filter", "salesperson"), "after", "group_bys")
        );
        expect.verifySteps(["apply_operation add_group_by"]);
        expect(operations.pop()).toEqual({
            type: "add_group_by",
            target: named("filter", "salesperson"),
            position: "after",
            field_name: "create_date",
            interval: "year",
        });
        // A field the records cannot be grouped by does not drop there.
        await contains(".o_erplibre_studio_existing_field[data-name=comment]").dragAndDrop(
            hook(named("filter", "salesperson"), "after", "group_bys")
        );
        expect.verifySteps([]);
    });

    test("a new filter from its form", async () => {
        answer = searchPayload({filters: [["type_company", "Companies", "[('is_company', '=', True)]"]]});
        await openEditor("search");
        respond = () =>
            searchPayload({
                filters: [
                    ["type_company", "Companies", "[('is_company', '=', True)]"],
                    ["studio_filter_has_a_tax_id", "Has a tax ID", "[('vat', '!=', False)]"],
                ],
            });
        await contains(".o_erplibre_studio_new_filter").click();
        expect(".o_erplibre_studio_filter_form").toHaveCount(1);
        await contains(".o_erplibre_studio_filter_label").edit("Has a tax ID");
        await contains(".o_erplibre_studio_condition_field").select("vat");
        await contains(".o_erplibre_studio_condition_operator").select("set");
        expect(".o_erplibre_studio_condition_value").toHaveCount(0);
        await contains(".o_erplibre_studio_add_condition").click();
        await contains(".o_erplibre_studio_condition:eq(1) .o_erplibre_studio_condition_field").select("active");
        expect(".o_erplibre_studio_condition:eq(1) .o_erplibre_studio_condition_value").toHaveValue("True");
        await contains(".o_erplibre_studio_create_filter").click();
        expect.verifySteps(["apply_operation add_filter"]);
        expect(operations.pop()).toEqual({
            type: "add_filter",
            target: named("filter", "type_company"),
            position: "after",
            label: "Has a tax ID",
            conditions: [
                {field: "vat", operator: "set", value: ""},
                {field: "active", operator: "=", value: "True"},
            ],
        });
        expect(".o_erplibre_studio_filter_form").toHaveCount(0);
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "studio_filter_has_a_tax_id");
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-kind", "filter");

        // A field dropped among the filters opens the form on it.
        await contains(".o_erplibre_studio_existing_field[data-name=phone]").dragAndDrop(
            hook(named("filter", "type_company"), "before", "filters")
        );
        expect.verifySteps([]);
        expect(".o_erplibre_studio_filter_label").toHaveValue("Phone");
        expect(".o_erplibre_studio_condition_field").toHaveValue("phone");
        expect(".o_erplibre_studio_condition_operator").toHaveValue("ilike");
    });

    test("a datetime condition is sent in UTC", async () => {
        mockTimeZone(-4);
        answer = searchPayload();
        await openEditor("search");
        respond = () => searchPayload({filters: [["studio_filter_recent", "Recent", "[]"]]});
        await contains(".o_erplibre_studio_new_filter").click();
        await contains(".o_erplibre_studio_condition_field").select("create_date");
        // A datetime-local input takes its value whole, as a picker sets it.
        const input = queryOne(".o_erplibre_studio_condition_value");
        input.value = "2026-10-16T08:00";
        input.dispatchEvent(new Event("input", {bubbles: true}));
        await animationFrame();
        await contains(".o_erplibre_studio_create_filter").click();
        expect.verifySteps(["apply_operation add_filter"]);
        expect(operations.pop().conditions).toEqual([
            {field: "create_date", operator: ">", value: "2026-10-16 12:00:00"},
        ]);
    });

    test("the filter form closes when the draft changes under it", async () => {
        answer = searchPayload();
        await openEditor("search");
        await contains(".o_erplibre_studio_existing_field[data-name=vat]").dragAndDrop(
            hook("/search/separator[1]", "after", "filters")
        );
        expect(".o_erplibre_studio_filter_form").toHaveCount(1);
        // Another drop moves the paths: the form located its target in the
        // revision before it.
        respond = () => searchPayload({fields: ["name", "email", "phone"]});
        await contains(".o_erplibre_studio_existing_field[data-name=phone]").dragAndDrop(
            hook(named("field", "email"), "after", "fields")
        );
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(".o_erplibre_studio_filter_form").toHaveCount(0);
    });
});

describe("erplibre_studio editor, pivot", () => {
    test("axis lanes: a field moves to another axis, the palette adds on an axis", async () => {
        answer = pivotPayload([
            ["country_id", "row"],
            ["partner_latitude", "measure"],
        ]);
        await openEditor("pivot");
        expect("[data-axis=row] .o_erplibre_studio_field[data-name=country_id]").toHaveCount(1);
        expect("[data-axis=measure] .o_erplibre_studio_field[data-name=partner_latitude]").toHaveCount(1);
        expect("[data-axis=col] .o_erplibre_studio_field").toHaveCount(0);

        respond = () =>
            pivotPayload([
                ["country_id", "col"],
                ["partner_latitude", "measure"],
            ]);
        await contains("[data-axis=row] .o_erplibre_studio_field[data-name=country_id]").dragAndDrop(
            hook("/pivot", "inside", "col")
        );
        expect.verifySteps(["apply_operation move"]);
        expect(operations.pop()).toEqual({
            type: "move",
            source: named("field", "country_id"),
            target: "/pivot",
            position: "inside",
            axis: "col",
        });
        expect("[data-axis=col] .o_erplibre_studio_field[data-name=country_id]").toHaveCount(1);
        expect(".o_erplibre_studio_settable[data-attribute=type] select").toHaveValue("col");

        // A field that cannot be a measure does not drop on the measures.
        await contains(".o_erplibre_studio_existing_field[data-name=create_date]").dragAndDrop(
            hook(named("field", "partner_latitude"), "after", "measure")
        );
        expect.verifySteps([]);
        await contains(".o_erplibre_studio_existing_field[data-name=create_date]").dragAndDrop(
            hook("/pivot", "inside", "row")
        );
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: "/pivot",
            position: "inside",
            field_name: "create_date",
            axis: "row",
            interval: "month",
        });
    });
});

describe("erplibre_studio editor, timeline", () => {
    test("the attributes of the view, the loaded fields and the colors", async () => {
        answer = timelinePayload({date_start: "create_date", default_group_by: "country_id"});
        await openEditor("timeline");
        expect(".o_erplibre_studio_timeline_summary [data-attribute=date_start]").toHaveCount(1);
        expect(".o_erplibre_studio_card .o_erplibre_studio_field[data-name=name]").toHaveCount(1);
        // A required attribute offers no « Default ».
        expect(".o_erplibre_studio_settable[data-attribute=date_start] option[value='']").toHaveCount(0);
        expect(".o_erplibre_studio_settable[data-attribute=mode] option[value='']").toHaveCount(1);

        await contains(".o_erplibre_studio_settable[data-attribute=mode] select").select("week");
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/timeline",
            attribute: "mode",
            value: "week",
        });

        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        await contains(".o_erplibre_studio_existing_field[data-name=active]").dragAndDrop(
            hook("/timeline", "inside", "loaded")
        );
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: "/timeline",
            position: "inside",
            field_name: "active",
        });

        await contains(".o_erplibre_studio_canvas").click();
        await contains(".o_erplibre_studio_edit_colors").click();
        await contains(".o_erplibre_studio_color_field").select("active");
        await contains(".o_erplibre_studio_color_value").edit("False");
        await contains(".o_erplibre_studio_save_colors").click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/timeline",
            attribute: "colors",
            value: [{color: "#ec7063", field: "active", operator: "==", value: "False"}],
        });
    });
});

test("helpers of the view types", () => {
    const search = searchPayload({
        filters: [["a", "A", "[]"]],
        groupBys: [["g", "G", "user_id"]],
    }).blocks;
    const columns = searchColumns(search);
    expect(columns.fields.map((b) => b.name)).toEqual(["name", "email"]);
    expect(columns.filters.map((b) => b.kind)).toEqual(["separator", "filter"]);
    expect(columns.group_bys.map((b) => b.name)).toEqual(["g"]);
    const lanes = pivotLanes(pivotPayload([["country_id", "row"]]));
    expect(lanes.row.map((b) => b.name)).toEqual(["country_id"]);
    expect(lanes.measure).toEqual([]);
    expect(pivotAxes(FIELDS.color)).toEqual(["row", "col", "measure"]);
    expect(pivotAxes(FIELDS.partner_latitude)).toEqual(["measure"]);
    expect(pivotAxes(FIELDS.comment)).toEqual([]);
    mockTimeZone(+2);
    expect(conditionValue("datetime", "2026-01-01T08:00")).toBe("2026-01-01 06:00:00");
    expect(conditionValue("date", "2026-01-01")).toBe("2026-01-01");
});
