// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {press, queryAllTexts, queryOne} from "@odoo/hoot-dom";
import {animationFrame, mockTimeZone} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    makeServerError,
    mountWithCleanup,
    onRpc,
    serverState,
    webModels,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {
    conditionValue,
    graphAxes,
    graphLanes,
    pivotAxes,
    pivotLanes,
    searchColumns,
} from "@erplibre_studio/editor/studio_editor";

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
    graph: ["add_existing_field", "move", "remove", "hide", "relabel", "set_attribute"],
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
    graph_axis: ["row", "measure"].map((a) => [a, a]),
    graph_type: ["bar", "line", "pie"].map((t) => [t, t]),
    graph_order: ["asc", "desc"].map((o) => [o, o]),
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
        hide_mode: ["search", "pivot", "graph"].includes(viewType) ? "remove" : "invisible",
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

/** A graph of ``axes`` [[name, axis]], its root of ``rootAttrs``. */
function graphPayload(axes, rootAttrs = {}) {
    const children = [];
    const layout = {root: "/graph", axes: {row: [], measure: []}, others: []};
    for (const [name, axis] of axes) {
        children.push(field(named("field", name), name, {axis, interval: null, attrs: {type: axis}}));
        layout.axes[axis].push(named("field", name));
    }
    const data = payload("graph", container("/graph", "graph", children, {movable: false, attrs: rootAttrs}), {
        layout,
        settable: {
            graph: {
                type: "graph_type",
                stacked: "bool",
                order: "graph_order",
                disable_linking: "bool",
                cumulated: "bool",
            },
            field: {type: "graph_axis", interval: "interval"},
        },
    });
    data.palette = data.palette
        .map((item) => ({...item, axes: graphAxes(FIELDS[item.name])}))
        .filter((item) => item.axes.length);
    return data;
}

function timelinePayload(attrs, loaded = ["name"], colors = []) {
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
            colors,
            color_operators: ["==", "!=", ">", "<"],
            color_types: ["char", "integer", "boolean", "date"],
        },
        settable: {
            timeline: {
                date_start: "date_field",
                date_stop: "date_field",
                date_delay: "number_field",
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
        // The timeline the canvas renders when web_timeline is loaded.
        "timeline,12": `<timeline date_start="create_date" default_group_by="country_id"/>`,
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
        // In a kanban the widget stays in « In this view »: no « Advanced ».
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_settable[data-attribute=widget]").toHaveCount(1);
        expect(".o_erplibre_studio_field_advanced_toggle").toHaveCount(0);

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
        await contains(".o_erplibre_studio_inspector_tab[data-tab=changes]").click();
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

describe("erplibre_studio editor, graph", () => {
    test("the axes, their captions, a drop on each axis and the chart type", async () => {
        answer = graphPayload([
            ["country_id", "row"],
            ["active", "row"],
            ["color", "measure"],
        ]);
        await openEditor("graph");
        expect(".o_erplibre_studio_axis").toHaveCount(2);
        expect(queryAllTexts(".o_erplibre_studio_axis > .fw-bold")).toEqual(["Group by", "Measures"]);
        expect("[data-axis=row] .o_erplibre_studio_field[data-name=country_id]").toHaveCount(1);
        expect("[data-axis=measure] .o_erplibre_studio_field[data-name=color]").toHaveCount(1);
        // The first group-by makes the X axis, the next one the series; a
        // single measure needs no caption.
        expect(queryAllTexts("[data-axis=row] .o_erplibre_studio_axis_caption")).toEqual(["X axis", "Series"]);
        expect("[data-axis=measure] .o_erplibre_studio_axis_caption").toHaveCount(0);
        expect(".o_erplibre_studio_existing_field[data-name=partner_latitude] .o_erplibre_studio_axis_badge").toHaveText(
            "Measure"
        );
        expect(".o_erplibre_studio_existing_field[data-name=create_date] .o_erplibre_studio_axis_badge").toHaveText(
            "Group by"
        );

        // A number that does not group goes on the measures only.
        const dragging = await contains(".o_erplibre_studio_existing_field[data-name=partner_latitude]").drag();
        expect("[data-axis=row]").toHaveClass("o_erplibre_studio_axis_refused");
        expect("[data-axis=measure]").not.toHaveClass("o_erplibre_studio_axis_refused");
        await dragging.drop(hook(named("field", "color"), "after", "measure"));
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: named("field", "color"),
            position: "after",
            field_name: "partner_latitude",
            axis: "measure",
        });

        // A date groups by the interval of the palette.
        await contains(".o_erplibre_studio_existing_field[data-name=create_date]").dragAndDrop(
            hook(named("field", "active"), "after", "row")
        );
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: named("field", "active"),
            position: "after",
            field_name: "create_date",
            axis: "row",
            interval: "month",
        });

        // Without « type », the graph is a bar chart.
        const type = (value) => `.o_erplibre_studio_graph_types .o_erplibre_studio_graph_type[data-value=${value}]`;
        expect(queryAllTexts(".o_erplibre_studio_graph_type")).toEqual(["Bar", "Line", "Pie"]);
        expect(type("bar")).toHaveAttribute("aria-pressed", "true");
        await contains(type("bar")).click();
        expect.verifySteps([]);
        respond = () =>
            graphPayload(
                [
                    ["country_id", "row"],
                    ["active", "row"],
                    ["color", "measure"],
                ],
                {type: "line"}
            );
        await contains(type("line")).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({type: "set_attribute", target: "/graph", attribute: "type", value: "line"});
        expect(type("line")).toHaveAttribute("aria-pressed", "true");

        // The properties of the view name the chart type and its values.
        await contains(".o_erplibre_studio_canvas").click();
        const settable = (attribute) => `.o_erplibre_studio_settable[data-attribute=${attribute}]`;
        expect(`${settable("type")} label`).toHaveText(/^Chart type/);
        expect(queryAllTexts(`${settable("type")} option`)).toEqual(["Default", "Bar", "Line", "Pie"]);
        expect(`${settable("type")} select`).toHaveValue("line");
        expect(`${settable("stacked")} label`).toHaveText(/^Stacked/);
        expect(`${settable("cumulated")} label`).toHaveText(/^Cumulative/);
        expect(queryAllTexts(`${settable("order")} option`)).toEqual(["Default", "Ascending", "Descending"]);
    });

    test("a pie names its slices, several measures name the one drawn", async () => {
        answer = graphPayload(
            [
                ["country_id", "row"],
                ["color", "measure"],
                ["partner_latitude", "measure"],
            ],
            {type: "pie"}
        );
        await openEditor("graph");
        expect(queryAllTexts("[data-axis=row] .o_erplibre_studio_axis_caption")).toEqual(["Slices"]);
        expect(queryAllTexts("[data-axis=measure] .o_erplibre_studio_axis_caption")).toEqual(["Drawn"]);
        expect(
            "[data-axis=measure] .o_erplibre_studio_axis_caption + .o_erplibre_studio_field[data-name=partner_latitude]"
        ).toHaveCount(1);
        expect(".o_erplibre_studio_axis_empty").toHaveCount(0);
    });

    test("a graph without measure counts the records", async () => {
        answer = graphPayload([["create_date", "row"]]);
        await openEditor("graph");
        expect("[data-axis=measure] .o_erplibre_studio_axis_empty").toHaveText("None: the chart counts the records.");
        // The palette adds on the first axis that takes the field.
        await contains(".o_erplibre_studio_existing_field[data-name=country_id] .o_erplibre_studio_pick").click();
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toMatchObject({field_name: "country_id", axis: "row"});
    });
});

describe("erplibre_studio editor, add a view", () => {
    /** An entry of ``view_list``: an editable view unless ``values`` say otherwise. */
    function entry(type, label, values = {}) {
        return {
            type,
            label,
            view_id: false,
            xml_id: false,
            exists: true,
            pending: false,
            added: false,
            editable: true,
            reason: false,
            reason_code: false,
            changes: 0,
            ...values,
        };
    }
    const missing = (type, label, code, reason) =>
        entry(type, label, {exists: false, editable: false, reason_code: code, reason});

    test("the menu adds a view to the draft, opens it, and the banner removes it", async () => {
        const kanbanList = [
            entry("kanban", "Kanban", {view_id: 12, xml_id: "base.partner_kanban"}),
            missing("pivot", "Pivot", "no_view", "Contact has no Pivot view to inherit."),
            missing("timeline", "Timeline", "needs_module", "Install the web_timeline module to edit a timeline view."),
            missing("calendar", "Calendar", "not_editable", "The studio does not edit Calendar views yet."),
        ];
        answer = kanbanPayload([inCard("name")]);
        answer.view_list = kanbanList;
        const added = {
            line_id: 5,
            applied: false,
            name: "res.partner.pivot.studio",
            xml_id: "studio_contacts.res_partner_view_pivot",
        };
        onRpc("erplibre.studio.editor", "add_view", (args) => {
            expect.step(`add_view ${args.args.join(" ")}`);
            expect(args.kwargs.revision).toBe(0);
            const data = pivotPayload([]);
            data.view = {id: false, name: added.name, xml_id: added.xml_id, pending: false, added};
            data.view_list = [
                kanbanList[0],
                entry("pivot", "Pivot", {xml_id: added.xml_id, pending: true, added: true}),
                ...kanbanList.slice(2),
            ];
            data.project = {...data.project, revision: 1, item_count: 1};
            return data;
        });
        onRpc("erplibre.studio.editor", "remove_view", (args) => {
            expect.step(`remove_view ${args.args.slice(0, 5).join(" ")}`);
            expect(args.kwargs.revision).toBe(1);
            expect(args.kwargs.fallback).toEqual(["res.partner", 12, "kanban"]);
            const data = kanbanPayload([inCard("name")]);
            data.view_list = kanbanList;
            data.view_changed = true;
            return data;
        });
        await openEditor("kanban");
        expect(".o_erplibre_studio_added_banner").toHaveCount(0);

        await contains(".o_erplibre_studio_add_view").click();
        expect(".o_erplibre_studio_view_menu_open").toHaveCount(1);
        expect(".o_erplibre_studio_view_menu_open .o_erplibre_studio_view_menu_tag").toHaveAttribute(
            "data-origin",
            "model"
        );
        expect(".o_erplibre_studio_view_menu_add").toHaveCount(1);
        expect(".o_erplibre_studio_view_menu_add[data-view-type=pivot]").toHaveText(
            /Pivot\s*Cross analysis: rows, columns and measures\./
        );
        expect(".o_erplibre_studio_view_menu_unavailable[data-reason=needs_module]").toHaveText(
            /Timeline\s*not installed\s*Install the web_timeline module/
        );
        expect(".o_erplibre_studio_view_menu_unavailable[data-reason=not_editable]").toHaveText(
            /Calendar\s*The studio does not edit Calendar views yet\./
        );
        await contains(".o_erplibre_studio_view_menu_add[data-view-type=pivot]").click();
        expect.verifySteps(["add_view 3 res.partner pivot"]);
        // The view exists in the draft only: the editor shows its canvas.
        expect(".o_erplibre_studio").toHaveAttribute("data-view-type", "pivot");
        expect("[data-axis=row]").toHaveCount(1);
        expect(".o_erplibre_studio_view_tab[data-view-type=pivot]").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_view_tab[data-view-type=pivot] .o_erplibre_studio_view_tab_new").toHaveCount(1);
        expect(".o_erplibre_studio_added_banner").toHaveAttribute("data-applied", "false");
        expect(".o_erplibre_studio_added_banner").toHaveText(/Pivot view added to the project.*Apply creates it/);

        await contains(".o_erplibre_studio_add_view").click();
        expect(".o_erplibre_studio_view_menu_open[data-view-type=pivot] .o_erplibre_studio_view_menu_tag").toHaveAttribute(
            "data-origin",
            "project"
        );
        expect(".o_erplibre_studio_view_menu_add").toHaveCount(0);
        expect(".o_erplibre_studio_view_menu_none").toHaveCount(0);
        await contains(".o_erplibre_studio_add_view").click();

        // Removing it asks first, then shows the view the editor opened on.
        await contains(".o_erplibre_studio_remove_view").click();
        expect.verifySteps([]);
        await contains(".modal .modal-footer .btn-primary").click();
        expect.verifySteps(["remove_view 3 5 res.partner false pivot"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-view-type", "kanban");
        expect(".o_erplibre_studio_added_banner").toHaveCount(0);
        expect(".o_erplibre_studio_view_tab[data-view-type=pivot]").toHaveCount(0);
    });
});

describe("erplibre_studio editor, a view added to the draft and the project menu", () => {
    test("another project, or none, shows the view the editor opened on", async () => {
        answer = kanbanPayload([inCard("name")]);
        const added = {
            line_id: 5,
            applied: false,
            name: "res.partner.pivot.studio",
            xml_id: "studio_contacts.res_partner_view_pivot",
        };
        answer.view_list = [
            {
                type: "kanban",
                label: "Kanban",
                view_id: 12,
                xml_id: "base.partner_kanban",
                exists: true,
                pending: false,
                added: false,
                editable: true,
                reason: false,
                reason_code: false,
                changes: 0,
            },
            {
                type: "pivot",
                label: "Pivot",
                view_id: false,
                xml_id: false,
                exists: false,
                pending: false,
                added: false,
                editable: false,
                reason: "Contact has no Pivot view to inherit.",
                reason_code: "no_view",
                changes: 0,
            },
        ];
        onRpc("erplibre.studio.editor", "add_view", () => {
            const data = pivotPayload([]);
            data.view = {id: false, name: added.name, xml_id: added.xml_id, pending: false, added};
            return data;
        });
        onRpc("erplibre.studio.editor", "get_editor_data", (args) => {
            const [, viewId, viewType] = args.args;
            if (viewId === false && viewType === "pivot") {
                // The view exists in the draft of project 3 only.
                throw makeServerError({message: "Contact has no pivot view to inherit."});
            }
            if (args.kwargs.pick_project === false) {
                expect.step(`get_editor_data ${args.args.slice(0, 4).join(" ")}`);
                return {...answer, project: false};
            }
        });
        await openEditor("kanban");
        await contains(".o_erplibre_studio_add_view").click();
        await contains(".o_erplibre_studio_view_menu_add[data-view-type=pivot]").click();
        expect(".o_erplibre_studio").toHaveAttribute("data-view-type", "pivot");

        await contains(".o_erplibre_studio_project_select").click();
        await contains(".o_erplibre_studio_project_item[data-project='']").click();
        await animationFrame();
        expect.verifySteps(["get_editor_data res.partner 12 kanban false"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-view-type", "kanban");
        expect(".o_erplibre_studio_project_select").toHaveAttribute("data-project", "");
        expect(".o_notification").toHaveCount(0);
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
        expect(".o_erplibre_studio_settable[data-attribute=date_stop] option[value='']").toHaveCount(1);
        // The scale is a group of buttons; without « mode », web_timeline opens on « fit ».
        const scale = ".o_erplibre_studio_settable[data-attribute=mode] .o_erplibre_studio_mode";
        expect(scale).toHaveCount(4);
        expect(`${scale}[data-value=fit]`).toHaveAttribute("aria-pressed", "true");
        await contains(`${scale}[data-value=fit]`).click();
        expect.verifySteps([]);

        await contains(`${scale}[data-value=week]`).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/timeline",
            attribute: "mode",
            value: "week",
        });

        // A view without new field types shows its existing fields unfolded.
        expect(".o_erplibre_studio_palette [data-tab=existing]").toHaveAttribute("aria-expanded", "true");
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
        expect(".o_erplibre_studio_edit_colors").toHaveText("Add a rule");
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

    test("the lanes take the fields of their kind, the scale and the color rules", async () => {
        const rules = [
            {color: "#ec7063", expression: "active == False", field: "active", operator: "==", value: false},
            {color: "green", expression: "color > 3", field: "color", operator: ">", value: 3},
        ];
        answer = timelinePayload({date_start: "create_date", default_group_by: "country_id"}, ["name"], rules);
        answer.changes = [
            {
                id: 5,
                type: "set_attribute",
                kind: "attribute",
                attribute: "date_start",
                summary: "Set date_start",
                xpath: "/timeline",
                path: "/timeline",
                error: false,
            },
        ];
        await openEditor("timeline");
        const lane = (key) => `.o_erplibre_studio_timeline_lane[data-lane=${key}]`;
        expect(".o_erplibre_studio_timeline_lane").toHaveCount(6);
        expect(`${lane("start")} .o_erplibre_studio_timeline_chip .text-truncate`).toHaveText(
            "Created on · create_date"
        );
        // The draft set the start date: its chip and its lane say so, to
        // a screen reader too.
        expect(`${lane("start")} .o_erplibre_studio_timeline_chip`).toHaveClass(
            "o_erplibre_studio_timeline_chip_changed"
        );
        expect(`${lane("start")} .o_erplibre_studio_timeline_chip .visually-hidden`).toHaveText(
            "(changed in this draft)"
        );
        expect(`${lane("group")} .o_erplibre_studio_timeline_chip .visually-hidden`).toHaveCount(0);
        expect(`${lane("start")} .o_erplibre_studio_change_dot`).toHaveCount(1);
        expect(`${lane("group")} .o_erplibre_studio_change_dot`).toHaveCount(0);
        // A required attribute keeps its field; an empty lane says what it takes.
        expect(`${lane("group")} .o_erplibre_studio_timeline_chip_remove`).toHaveCount(0);
        expect(lane("stop")).toHaveText(/Drop a field here/);
        expect(`${lane("template")} .o_erplibre_studio_card .o_erplibre_studio_field[data-name=name]`).toHaveCount(1);
        expect(".o_erplibre_studio_frise").toHaveCount(1);

        // A field that does not fit a lane is refused, one that fits sets its attribute.
        await contains(".o_erplibre_studio_existing_field[data-name=active]").dragAndDrop(lane("start"));
        expect.verifySteps([]);
        await contains(".o_erplibre_studio_existing_field[data-name=color]").dragAndDrop(lane("stop"));
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/timeline",
            attribute: "date_delay",
            value: "color",
        });
        // The inspector shows the lane of the drop.
        expect(".o_erplibre_studio_view_properties").toHaveAttribute("data-lane", "stop");
        expect(".o_erplibre_studio_lane_props .o_erplibre_studio_settable[data-attribute=date_stop]").toHaveCount(1);
        expect(".o_erplibre_studio_lane_props .o_erplibre_studio_settable[data-attribute=date_delay]").toHaveCount(1);

        // The scale of the canvas.
        expect(`${lane("scale")} .o_erplibre_studio_timeline_scale[data-value=fit]`).toHaveAttribute(
            "aria-pressed",
            "true"
        );
        await contains(`${lane("scale")} .o_erplibre_studio_timeline_scale[data-value=month]`).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({type: "set_attribute", target: "/timeline", attribute: "mode", value: "month"});

        // A color rule leaves; the others are written again as they are.
        expect(`${lane("colors")} .o_erplibre_studio_timeline_chip`).toHaveCount(2);
        await contains(`${lane("colors")} .o_erplibre_studio_timeline_chip[data-index='0'] button`).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/timeline",
            attribute: "colors",
            value: [{color: "green", field: "color", operator: ">", value: 3}],
        });

        // « Add a rule » opens the rules of the colors lane with a new one.
        await contains(`${lane("colors")} .o_erplibre_studio_timeline_add_rule`).click();
        expect(lane("colors")).toHaveClass("o_erplibre_studio_timeline_lane_selected");
        expect(".o_erplibre_studio_view_properties").toHaveAttribute("data-lane", "colors");
        expect(".o_erplibre_studio_color_rule").toHaveCount(3);
        expect(".o_erplibre_studio_color_rule:eq(1) .o_erplibre_studio_color_value").toHaveValue("3");
        await contains(".o_erplibre_studio_colors_form .btn-secondary").click();

        // A lane chosen on the canvas: its attribute shows once, in « Lane ».
        await contains(`${lane("group")} .o_erplibre_studio_timeline_lane_pick`).click();
        expect(`${lane("group")} .o_erplibre_studio_timeline_lane_pick`).toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_studio_settable[data-attribute=default_group_by]").toHaveCount(1);
        expect(".o_erplibre_studio_lane_props .o_erplibre_studio_settable[data-attribute=default_group_by]").toHaveCount(
            1
        );
        // The attributes the view gets from the draft.
        await contains(".o_erplibre_studio_generated_toggle").click();
        expect(".o_erplibre_studio_generated").toHaveText(/<timeline date_start="create_date"/);
        expect(".o_erplibre_studio_generated").toHaveText(/default_group_by="country_id">/);

        // A field of the item template: the lane leaves the inspector.
        await contains(`${lane("template")} .o_erplibre_studio_field[data-name=name]`).click();
        expect(".o_erplibre_studio_properties[data-name=name]").toHaveCount(1);
        expect(".o_erplibre_studio_timeline_lane_selected").toHaveCount(0);
    });

    test("a color rule the editor does not write keeps every rule", async () => {
        const rules = [
            {color: "red", expression: "state in ('a', 'b')"},
            {color: "green", expression: "color > 3", field: "color", operator: ">", value: 3},
        ];
        answer = timelinePayload({date_start: "create_date", default_group_by: "country_id"}, ["name"], rules);
        await openEditor("timeline");
        expect(".o_erplibre_studio_timeline_chip_remove").toHaveCount(0);
        expect(".o_erplibre_studio_color_remove").toHaveCount(0);
        await contains(".o_erplibre_studio_edit_colors").click();
        // Saving replaces the rules: the form starts with a new one only.
        expect(".o_erplibre_studio_color_rule").toHaveCount(1);
        expect(".o_erplibre_studio_colors_form").toHaveText(/Saving replaces the rules above/);
    });
});

describe("erplibre_studio editor, form layout", () => {
    const FORM_OPERATIONS = [
        "add_field",
        "add_existing_field",
        "add_group",
        "add_page",
        "add_separator",
        "move",
        "remove",
        "hide",
        "relabel",
    ];
    const SHEET = "/form/sheet";
    const NOTEBOOK = "/form/sheet/notebook[1]";
    const NEW_GROUP = named("group", "studio_group_new_group");

    /** A form: a group, then a notebook of one tab; ``extra`` blocks after them. */
    function formPayload(extra = [], changes = []) {
        const page = container(named("page", "notes"), "page", [field(named("field", "email"), "email")], {
            label: "Notes",
            attrs: {name: "notes", string: "Notes"},
        });
        const notebook = container(NOTEBOOK, "notebook", [page], {drop: false, movable: false});
        const group = container(named("group", "g"), "group", [field(named("field", "name"), "name")]);
        const sheet = container(SHEET, "sheet", [group, notebook, ...extra], {movable: false});
        return payload("form", container("/form", "form", [sheet], {drop: false, movable: false}), {
            operations: FORM_OPERATIONS,
            changes,
        });
    }

    test("the layout items drop onto the sheet and the tabs", async () => {
        answer = formPayload();
        await openEditor("form");
        expect(".o_erplibre_studio_palette [data-tab=layout]").toHaveCount(1);
        expect(".o_erplibre_studio_layout_item").toHaveCount(3);
        expect(".o_erplibre_studio_palette [data-tab=other]").toHaveCount(0);
        // The notebook ends its tabs with the hook of a new tab.
        expect(`.o_erplibre_studio_page_hook ${hook(NOTEBOOK, "inside", "pages")}`).toHaveCount(1);

        // A group onto the sheet: the new group is selected.
        const added = container(NEW_GROUP, "group", [], {
            label: "New group",
            attrs: {name: "studio_group_new_group", string: "New group"},
            change_kinds: ["new"],
            changed: true,
        });
        const change = {id: 9, type: "add_node", kind: "new", summary: "group", path: NEW_GROUP, error: false};
        respond = () => formPayload([added], [change]);
        await contains(".o_erplibre_studio_layout_group").dragAndDrop(hook(SHEET, "inside"));
        expect.verifySteps(["apply_operation add_group"]);
        expect(operations.pop()).toEqual({type: "add_group", target: SHEET, position: "inside"});
        expect(`.o_erplibre_studio_container[data-path="${NEW_GROUP}"]`).toHaveClass("o_erplibre_studio_selected");

        // A tab onto the hook of the tabs.
        respond = () => formPayload();
        await contains(".o_erplibre_studio_layout_page").dragAndDrop(hook(NOTEBOOK, "inside", "pages"));
        expect.verifySteps(["apply_operation add_page"]);
        expect(operations.pop()).toEqual({type: "add_page", target: NOTEBOOK, position: "inside"});

        // A field never drops there.
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        await contains(".o_erplibre_studio_existing_field[data-name=phone]").dragAndDrop(
            hook(NOTEBOOK, "inside", "pages")
        );
        expect.verifySteps([]);

        // A click on a tab selects its page.
        await contains(`.o_erplibre_studio_page_tab[data-path="${named("page", "notes")}"]`).click();
        expect(`.o_erplibre_studio_container[data-path="${named("page", "notes")}"]`).toHaveClass(
            "o_erplibre_studio_selected"
        );
        expect(".o_erplibre_studio_in_view .o_erplibre_studio_prop_label").toHaveCount(1);
    });

    test("a tab from the palette goes with the tabs of the notebook", async () => {
        answer = formPayload();
        respond = () => formPayload();
        await openEditor("form");
        await contains(".o_erplibre_studio_palette [data-tab=layout]").click();
        const tab = ".o_erplibre_studio_layout_page";
        const expected = {type: "add_page", target: NOTEBOOK, position: "inside"};
        // Nothing selected, a field of a group selected, a tab selected:
        // each time at the end of the tabs.
        await contains(tab).click();
        await animationFrame();
        expect.verifySteps(["apply_operation add_page"]);
        expect(operations.pop()).toEqual(expected);
        await contains(".o_erplibre_studio_field[data-name=name]").click();
        queryOne(`${tab} > .o_erplibre_studio_palette_add`).focus();
        await press("Enter");
        await animationFrame();
        expect.verifySteps(["apply_operation add_page"]);
        expect(operations.pop()).toEqual(expected);
        await contains(`.o_erplibre_studio_page_tab[data-path="${named("page", "notes")}"]`).click();
        await contains(tab).click();
        await animationFrame();
        expect.verifySteps(["apply_operation add_page"]);
        expect(operations.pop()).toEqual(expected);
        // A drag of a tab: not into a group, where no notebook goes.
        await contains(tab).dragAndDrop(hook(named("field", "name"), "before"));
        expect.verifySteps([]);
        await contains(tab).dragAndDrop(hook(SHEET, "inside"));
        expect.verifySteps(["apply_operation add_page"]);
        expect(operations.pop()).toEqual({type: "add_page", target: SHEET, position: "inside"});
    });

    test("a tab from the palette starts a notebook in a form without one", async () => {
        const group = container(named("group", "g"), "group", [field(named("field", "name"), "name")]);
        const sheet = container(SHEET, "sheet", [group], {movable: false});
        answer = payload("form", container("/form", "form", [sheet], {drop: false, movable: false}), {
            operations: FORM_OPERATIONS,
        });
        respond = () => answer;
        await openEditor("form");
        await contains(".o_erplibre_studio_palette [data-tab=layout]").click();
        await contains(".o_erplibre_studio_field[data-name=name]").click();
        await contains(".o_erplibre_studio_layout_page").click();
        await animationFrame();
        expect.verifySteps(["apply_operation add_page"]);
        expect(operations.pop()).toEqual({type: "add_page", target: SHEET, position: "inside"});
    });

    test("no layout item in a list", async () => {
        const blocks = container("/list", "list", [field(named("field", "name"), "name")], {movable: false});
        answer = payload("list", blocks, {
            operations: ["add_field", "add_existing_field", "move", "remove", "hide", "relabel"],
        });
        await openEditor("list");
        expect(".o_erplibre_studio_palette [data-tab=layout]").toHaveCount(0);
        expect(".o_erplibre_studio_layout_item").toHaveCount(0);
    });

    test("the separator of a search view is a layout item", async () => {
        answer = searchPayload();
        await openEditor("search");
        expect(".o_erplibre_studio_palette [data-tab=layout]").toHaveCount(1);
        expect(".o_erplibre_studio_layout .o_erplibre_studio_separator").toHaveCount(1);
        expect(".o_erplibre_studio_layout_item").toHaveCount(1);
        expect(".o_erplibre_studio_palette [data-tab=other]").toHaveCount(0);
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
    const graph = graphLanes(
        graphPayload([
            ["country_id", "row"],
            ["color", "measure"],
        ])
    );
    expect(graph.row.map((b) => b.name)).toEqual(["country_id"]);
    expect(graph.measure.map((b) => b.name)).toEqual(["color"]);
    expect(graph.others).toEqual([]);
    expect("col" in graph).toBe(false);
    expect(graphAxes(FIELDS.color)).toEqual(["row", "measure"]);
    expect(graphAxes(FIELDS.partner_latitude)).toEqual(["measure"]);
    expect(graphAxes(FIELDS.create_date)).toEqual(["row"]);
    expect(graphAxes(FIELDS.comment)).toEqual([]);
    mockTimeZone(+2);
    expect(conditionValue("datetime", "2026-01-01T08:00")).toBe("2026-01-01 06:00:00");
    expect(conditionValue("date", "2026-01-01")).toBe("2026-01-01");
});
