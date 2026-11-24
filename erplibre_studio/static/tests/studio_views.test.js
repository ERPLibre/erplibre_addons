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
    calendar: ["add_existing_field", "move", "remove", "hide", "relabel", "set_attribute"],
    leaflet_map: ["add_field", "add_existing_field", "remove", "set_attribute"],
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
    calendar_mode: ["day", "week", "month", "year"].map((m) => [m, m]),
    calendar_filter: [["True", "True"]],
    color_field: [
        ["color", "Color"],
        ["country_id", "Country"],
        ["name", "Name"],
    ],
    bool_field: [["active", "Active"]],
    coordinate_field: [["partner_latitude", "Latitude"]],
    text_field: [
        ["email", "Email"],
        ["name", "Name"],
        ["phone", "Phone"],
        ["vat", "Tax ID"],
    ],
    image_field: [],
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
        // The level that shows the technical bits these tests read.
        display_level: "detailed",
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

/**
 * A calendar of the contacts: the root attributes ``attrs``, the fields of
 * ``popover`` as its <field> children, which the popover of an event shows.
 */
function calendarPayload(attrs, popover = ["name"]) {
    const children = popover.map((name) => field(named("field", name), name));
    return payload("calendar", container("/calendar", "calendar", children, {movable: false, attrs}), {
        layout: {
            root: "/calendar",
            popover: children.map((child) => child.path),
            loaded_by_attributes: Object.values(attrs),
        },
        hide_mode: "invisible",
        settable: {
            calendar: {
                date_start: "date_field",
                date_stop: "date_field",
                date_delay: "number_field",
                color: "color_field",
                all_day: "bool_field",
                mode: "calendar_mode",
                quick_create: "bool",
                event_open_popup: "bool",
                create: "bool",
                edit: "bool",
                delete: "bool",
            },
            field: {filters: "calendar_filter"},
        },
        required_attributes: {calendar: ["date_start"]},
    });
}

/**
 * A map of the contacts (web_view_leaflet_map): the root attributes
 * ``attrs``, no children.
 */
function leafletPayload(attrs) {
    const settable = {
        field_latitude: "coordinate_field",
        field_longitude: "coordinate_field",
        field_title: "text_field",
        field_address: "text_field",
        field_marker_icon_image: "image_field",
        marker_icon_size_x: "pixels",
        marker_icon_size_y: "pixels",
        marker_popup_anchor_x: "offset",
        marker_popup_anchor_y: "offset",
    };
    const lanes = Object.fromEntries(
        Object.keys(settable)
            .filter((attribute) => attribute.startsWith("field_"))
            .map((attribute) => [attribute, attrs[attribute] || false])
    );
    return payload("leaflet_map", container("/leaflet_map", "leaflet_map", [], {movable: false, attrs}), {
        layout: {
            root: "/leaflet_map",
            lanes,
            loaded_fields: [],
            new_field_types: {
                field_latitude: ["float"],
                field_longitude: ["float"],
                field_title: ["char"],
                field_address: ["char"],
                field_marker_icon_image: [],
            },
        },
        hide_mode: "remove",
        settable: {leaflet_map: settable},
        required_attributes: {leaflet_map: ["field_latitude", "field_longitude"]},
        field_types: ["char", "integer", "float"],
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
            "data-draggable",
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

    test("the geometry types stay out of the palette of a kanban", async () => {
        answer = kanbanPayload([inCard("name")]);
        answer.field_types = ["char", "integer", "geo_point", "geo_line", "geo_polygon"];
        await openEditor("kanban");
        expect(".o_erplibre_studio_new_field").toHaveCount(2);
        expect(".o_erplibre_studio_new_field[data-type^=geo]").toHaveCount(0);
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
        ).toHaveAttribute("data-draggable", "false");

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

describe("erplibre_studio editor, calendar", () => {
    const lane = (key) => `.o_erplibre_studio_calendar_lane[data-lane=${key}]`;

    test("the lanes, a chip removed, a drop on a lane and the scale", async () => {
        answer = calendarPayload({date_start: "create_date", date_stop: "create_date"});
        await openEditor("calendar");
        expect(".o_erplibre_studio_calendar_lane").toHaveCount(6);
        for (const key of ["start", "stop", "color", "all_day", "scale", "popover"]) {
            expect(lane(key)).toHaveCount(1);
        }
        expect(".o_erplibre_studio_timeline_lane").toHaveCount(0);
        expect(".o_erplibre_studio_palette").toHaveText(/a field onto Color, or any field into the popover/);
        // The start date is required: its chip stays.
        expect(`${lane("start")} .o_erplibre_studio_calendar_chip`).toHaveText("Created on · create_date");
        expect(`${lane("start")} .o_erplibre_studio_calendar_chip_remove`).toHaveCount(0);
        expect(lane("color")).toHaveText(/Drop a field here/);
        await contains(`${lane("stop")} .o_erplibre_studio_calendar_chip_remove`).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/calendar",
            attribute: "date_stop",
            value: "",
        });

        // A number does not fit the start date; a date fits the end date.
        const dragging = await contains(".o_erplibre_studio_existing_field[data-name=color]").drag();
        expect(lane("start")).toHaveClass("o_erplibre_studio_calendar_lane_refused");
        expect(lane("color")).not.toHaveClass("o_erplibre_studio_calendar_lane_refused");
        await dragging.drop(lane("start"));
        expect.verifySteps([]);
        await contains(".o_erplibre_studio_existing_field[data-name=create_date]").dragAndDrop(lane("stop"));
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/calendar",
            attribute: "date_stop",
            value: "create_date",
        });
        // The inspector shows the lane of the drop and what it does.
        expect(".o_erplibre_studio_view_properties").toHaveAttribute("data-lane", "stop");
        expect(".o_erplibre_studio_inspector_kind").toHaveText(/Lane of the calendar/);
        expect(".o_erplibre_studio_lane_props").toHaveText(/The end date wins over the duration/);
        expect(lane("stop")).toHaveClass("o_erplibre_studio_calendar_lane_selected");

        // Without « mode », the calendar opens on the scale the browser
        // remembers: no scale is pressed, the week can be written too.
        const scale = `${lane("scale")} .o_erplibre_studio_calendar_scale`;
        expect(queryAllTexts(scale)).toEqual(["Day", "Week", "Month", "Year"]);
        expect(`${scale}[aria-pressed=true]`).toHaveCount(0);
        await contains(`${scale}[data-value=week]`).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({type: "set_attribute", target: "/calendar", attribute: "mode", value: "week"});
        await contains(`${scale}[data-value=month]`).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({type: "set_attribute", target: "/calendar", attribute: "mode", value: "month"});
    });

    test("the popover lane takes any field, the inspector names its fields", async () => {
        answer = calendarPayload({date_start: "create_date"}, ["name", "email"]);
        await openEditor("calendar");
        expect(`${lane("popover")} .o_erplibre_studio_field`).toHaveCount(2);
        await contains(".o_erplibre_studio_existing_field[data-name=phone]").dragAndDrop(
            `${lane("popover")} ${hook(named("field", "email"), "after")}`
        );
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: named("field", "email"),
            position: "after",
            field_name: "phone",
        });

        await contains(`${lane("popover")} .o_erplibre_studio_calendar_lane_pick`).click();
        expect(".o_erplibre_studio_view_properties").toHaveAttribute("data-lane", "popover");
        expect(".o_erplibre_studio_inspector_title").toHaveText("Popover");
        expect(".o_erplibre_studio_lane_fields").toHaveText(/Name, Email/);
        expect(".o_erplibre_studio_lane_props").toHaveText(/The fields the popover of an event shows/);
        // The other attributes of the calendar keep their own section.
        expect(".o_erplibre_studio_view_properties legend").toHaveCount(2);
        expect(".o_erplibre_studio_view_properties legend:last").toHaveText(/options of the calendar/i);
        expect(".o_erplibre_studio_settable[data-attribute=edit]").toHaveText(/Move and resize events/);

        // A field of the popover: the lane leaves the inspector.
        await contains(`${lane("popover")} .o_erplibre_studio_field[data-name=name]`).click();
        expect(".o_erplibre_studio_properties[data-name=name]").toHaveCount(1);
        expect(".o_erplibre_studio_calendar_lane_selected").toHaveCount(0);
        // Its filter in the side panel reads as a yes, not as the raw value.
        expect(queryAllTexts(".o_erplibre_studio_settable[data-attribute=filters] option")).toEqual([
            "Default",
            "Yes",
        ]);
    });

    test("a color field and an all-day boolean drop on their lanes", async () => {
        answer = calendarPayload({date_start: "create_date"});
        await openEditor("calendar");
        // The view itself, no lane chosen: its scale as a group of buttons.
        expect(".o_erplibre_studio_inspector_title").toHaveText("Calendar");
        expect(".o_erplibre_studio_settable[data-attribute=mode] .o_erplibre_studio_mode").toHaveCount(4);
        expect(".o_erplibre_studio_settable[data-attribute=mode]").toHaveText(/opens on the last scale used, else Week/);
        expect(".o_erplibre_studio_settable[data-attribute=mode] .o_erplibre_studio_mode[aria-pressed=true]").toHaveCount(
            0
        );
        await contains(".o_erplibre_studio_existing_field[data-name=country_id]").dragAndDrop(lane("color"));
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/calendar",
            attribute: "color",
            value: "country_id",
        });
        await contains(".o_erplibre_studio_existing_field[data-name=active]").dragAndDrop(lane("all_day"));
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/calendar",
            attribute: "all_day",
            value: "active",
        });
        expect(".o_erplibre_studio_inspector_title").toHaveText("All day");
    });
});

describe("erplibre_studio editor, hierarchy", () => {
    const BOX = "//t[@t-name='hierarchy-box']";
    const HEADER = `${BOX}/div[1]`;
    const BODY = `${BOX}/div[2]`;
    const HIERARCHY_OPERATIONS = [
        "add_field",
        "add_existing_field",
        "move",
        "remove",
        "hide",
        "set_attribute",
        "update_field",
        "rename_field",
    ];

    /**
     * A hierarchy of the contacts: the root attributes ``attrs``, its
     * « hierarchy-box » card with the name in its header and the fields of
     * ``body`` in its body.
     */
    function hierarchyPayload(attrs = {}, body = ["email"]) {
        const div = (path, children) => container(path, "div", children, {in_template: true, chain: null});
        const box = {
            path: BOX,
            tag: "t",
            kind: "template",
            label: "hierarchy-box",
            attrs: {"t-name": "hierarchy-box"},
            movable: false,
            drop: true,
            in_template: true,
            chain: null,
            template: "hierarchy-box",
            children: [div(HEADER, [inCard("name")]), div(BODY, body.map((name) => inCard(name)))],
        };
        const blocks = container(
            "/hierarchy",
            "hierarchy",
            [container("/hierarchy/templates", "templates", [box], {drop: false, movable: false, in_template: false})],
            {drop: false, movable: false, attrs}
        );
        return payload("hierarchy", blocks, {
            operations: HIERARCHY_OPERATIONS,
            layout: {root: "/hierarchy", card: BOX, templates: {"hierarchy-box": BOX}, loaded_fields: [], widgets: {}},
            settable: {
                hierarchy: {
                    parent_field: "parent_field",
                    child_field: "child_field",
                    draggable: "bool",
                    default_order: "order",
                },
                field: {widget: "widget"},
            },
            choices: {
                ...CHOICES,
                parent_field: [["parent_id", "Related Company"]],
                child_field: [["child_ids", "Contact"]],
            },
        });
    }

    test("the card of the nodes shows; the palette adds to it; no ribbon", async () => {
        answer = hierarchyPayload({parent_field: "parent_id"});
        await openEditor("hierarchy");
        expect(".o_erplibre_studio_hierarchy_caption").toHaveText("The card of each node of the hierarchy");
        expect(".o_erplibre_studio_card .o_erplibre_studio_field").toHaveCount(2);
        expect(".o_erplibre_studio_card .o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "name");
        expect(".o_erplibre_studio_template_tab").toHaveCount(0);
        expect(".o_erplibre_studio_palette [data-tab=other]").toHaveCount(0);
        expect(hook(BODY, "inside")).toHaveCount(1);
        // Nothing new goes outside the card.
        expect(hook("/hierarchy", "inside")).toHaveCount(0);

        respond = () => hierarchyPayload({parent_field: "parent_id"}, ["email", "phone"]);
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        await contains(".o_erplibre_studio_existing_field[data-name=phone]").dragAndDrop(hook(BODY, "inside"));
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: BODY,
            position: "inside",
            field_name: "phone",
        });
        expect(".o_erplibre_studio_card .o_erplibre_studio_field[data-name=phone]").toHaveCount(1);
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "phone");
    });

    test("the view properties: parent and children fields, drag, order", async () => {
        answer = hierarchyPayload({parent_field: "parent_id"});
        await openEditor("hierarchy");
        expect(".o_erplibre_studio_view_properties").toHaveAttribute("data-tag", "hierarchy");
        const settable = (attribute) => `.o_erplibre_studio_settable[data-attribute=${attribute}]`;
        expect(`${settable("parent_field")} label`).toHaveText(/Parent field/);
        expect(`${settable("parent_field")} select`).toHaveValue("parent_id");
        expect(queryAllTexts(`${settable("child_field")} option`)).toEqual(["Default", "Contact"]);
        expect(`${settable("draggable")} label`).toHaveText(/Drag the cards to change the parent/);
        expect(`${settable("default_order")} input`).toHaveCount(1);

        respond = (operation) => {
            const data = hierarchyPayload({parent_field: "parent_id", [operation.attribute]: operation.value});
            data.changes = [{id: 1, type: "set_attribute", summary: "Children field", error: false}];
            return data;
        };
        await contains(`${settable("child_field")} select`).select("child_ids");
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/hierarchy",
            attribute: "child_field",
            value: "child_ids",
        });
        expect(`${settable("child_field")} select`).toHaveValue("child_ids");
        await contains(`${settable("draggable")} select`).select("True");
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/hierarchy",
            attribute: "draggable",
            value: "True",
        });
    });
});

describe("erplibre_studio editor, activity", () => {
    const BOX = "//div[@t-name='activity-box']";
    const ACTIVITY_OPERATIONS = [
        "add_field",
        "add_existing_field",
        "move",
        "remove",
        "hide",
        "set_attribute",
        "update_field",
        "rename_field",
    ];

    /**
     * An activity view of the contacts: the id it loads, its
     * « activity-box » template, a <div>, showing the fields ``names``;
     * ``attrs`` gives a field its attributes.
     */
    function activityPayload(names = ["name"], attrs = {}) {
        const box = {
            path: BOX,
            tag: "div",
            kind: "template",
            label: "activity-box",
            attrs: {"t-name": "activity-box"},
            movable: false,
            drop: true,
            in_template: true,
            chain: null,
            template: "activity-box",
            children: names.map((name) => inCard(name, {attrs: attrs[name] || {}})),
        };
        const blocks = container(
            "/activity",
            "activity",
            [container("/activity/templates", "templates", [box], {drop: false, movable: false, in_template: false})],
            {drop: false, movable: false}
        );
        return payload("activity", blocks, {
            operations: ACTIVITY_OPERATIONS,
            layout: {root: "/activity", card: BOX, templates: {"activity-box": BOX}, loaded_fields: [], widgets: {}},
            settable: {field: {widget: "widget", display: "activity_display"}},
            choices: {...CHOICES, activity_display: ["full", "right"].map((d) => [d, d])},
        });
    }

    test("the activity box shows as a card; the palette adds to it; the width of a field", async () => {
        answer = activityPayload();
        await openEditor("activity");
        expect(".o_erplibre_studio_activity_caption").toHaveText("The record cell of each row of the activity view");
        expect(".o_erplibre_studio_card .o_erplibre_studio_field").toHaveCount(1);
        expect(".o_erplibre_studio_card .o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "name");
        expect(".o_erplibre_studio_palette [data-tab=other]").toHaveCount(0);
        expect(hook(BOX, "inside")).toHaveCount(1);
        // Nothing new goes outside the box.
        expect(hook("/activity", "inside")).toHaveCount(0);

        respond = () => activityPayload(["name", "phone"]);
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        await contains(".o_erplibre_studio_existing_field[data-name=phone]").dragAndDrop(hook(BOX, "inside"));
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: BOX,
            position: "inside",
            field_name: "phone",
        });
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "phone");

        const display = ".o_erplibre_studio_settable[data-attribute=display]";
        expect(`${display} label`).toHaveText(/Width/);
        expect(queryAllTexts(`${display} option`)).toEqual(["Default", "Whole line", "Right-aligned"]);
        respond = () => activityPayload(["name", "phone"], {phone: {display: "right"}});
        await contains(`${display} select`).select("right");
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: named("field", "phone"),
            attribute: "display",
            value: "right",
        });
        expect(`${display} select`).toHaveValue("right");
    });

    test("a model without activities: the menu lists the activity view, not addable", async () => {
        answer = kanbanPayload([inCard("name")]);
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
                type: "activity",
                label: "Activity",
                view_id: false,
                xml_id: false,
                exists: false,
                pending: false,
                added: false,
                editable: false,
                reason: "res.partner has no activities: an activity view needs the model to inherit mail.activity.mixin (a chatter).",
                reason_code: "needs_activity",
                changes: 0,
            },
        ];
        await openEditor("kanban");
        await contains(".o_erplibre_studio_add_view").click();
        expect(".o_erplibre_studio_view_menu_add").toHaveCount(0);
        const unavailable = ".o_erplibre_studio_view_menu_unavailable[data-reason=needs_activity]";
        expect(unavailable).toHaveAttribute("data-view-type", "activity");
        expect(unavailable).toHaveAttribute("aria-disabled", "true");
        expect(unavailable).toHaveText(/Activity\s*res\.partner has no activities: .*mail\.activity\.mixin/);
        expect(`${unavailable} .badge`).toHaveCount(0);
    });
});

describe("erplibre_studio editor, leaflet map", () => {
    const lane = (key) => `.o_erplibre_studio_timeline_lane[data-lane=${key}]`;

    test("five lanes; a field of its kind or a new field drops on a lane", async () => {
        answer = leafletPayload({field_longitude: "partner_latitude", field_title: "name"});
        await openEditor("leaflet_map");
        expect(".o_erplibre_studio_leaflet_lanes .o_erplibre_studio_timeline_lane").toHaveCount(5);
        for (const key of ["latitude", "longitude", "title", "address", "marker"]) {
            expect(lane(key)).toHaveCount(1);
        }
        expect(".o_erplibre_studio_palette").toHaveText(/onto Latitude or Longitude/);
        // A coordinate is required: its chip stays; the title can leave.
        expect(`${lane("longitude")} .o_erplibre_studio_timeline_chip`).toHaveText(
            "Latitude · partner_latitude"
        );
        expect(`${lane("longitude")} .o_erplibre_studio_timeline_chip_remove`).toHaveCount(0);
        expect(`${lane("title")} .o_erplibre_studio_timeline_chip_remove`).toHaveCount(1);
        // The palette offers the new types a lane creates only.
        expect(".o_erplibre_studio_new_field").toHaveCount(2);
        expect(".o_erplibre_studio_new_field[data-type=integer]").toHaveCount(0);

        // A text does not fit a coordinate: refused, no call.
        const dragging = await contains(".o_erplibre_studio_existing_field[data-name=email]").drag();
        expect(lane("latitude")).toHaveClass("o_erplibre_studio_timeline_lane_refused");
        expect(lane("title")).not.toHaveClass("o_erplibre_studio_timeline_lane_refused");
        await dragging.drop(lane("latitude"));
        expect.verifySteps([]);

        await contains(".o_erplibre_studio_existing_field[data-name=partner_latitude]").dragAndDrop(
            lane("latitude")
        );
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/leaflet_map",
            attribute: "field_latitude",
            value: "partner_latitude",
        });
        expect(".o_erplibre_studio_view_properties").toHaveAttribute("data-lane", "latitude");
        expect(".o_erplibre_studio_inspector_kind").toHaveText(/Lane of the map/);
        expect(".o_erplibre_studio_lane_props").toHaveText(/A stored decimal field/);

        // A new Decimal field dropped on Longitude is created for it.
        await contains(".o_erplibre_studio_new_field[data-type=float]").dragAndDrop(lane("longitude"));
        expect.verifySteps(["apply_operation add_field"]);
        expect(operations.pop()).toEqual({
            type: "add_field",
            target: "/leaflet_map",
            position: "inside",
            attribute: "field_longitude",
            field: {ttype: "float", field_description: "Longitude"},
        });
        // A new Text field fits no coordinate.
        const text = await contains(".o_erplibre_studio_new_field[data-type=char]").drag();
        expect(lane("latitude")).toHaveClass("o_erplibre_studio_timeline_lane_refused");
        expect(lane("address")).not.toHaveClass("o_erplibre_studio_timeline_lane_refused");
        expect(lane("marker")).toHaveClass("o_erplibre_studio_timeline_lane_refused");
        await text.drop(lane("latitude"));
        expect.verifySteps([]);
    });

    test("the marker numbers fold under Advanced; no zoom setting", async () => {
        answer = leafletPayload({field_latitude: "partner_latitude", field_longitude: "partner_latitude"});
        await openEditor("leaflet_map");
        expect(".o_erplibre_studio_inspector_title").toHaveText("Map");
        expect(".o_erplibre_studio_settable[data-attribute=default_zoom]").toHaveCount(0);
        expect(".o_erplibre_studio_settable[data-attribute=marker_icon_size_x]").toHaveCount(0);
        await contains(".o_erplibre_studio_lane_advanced_toggle").click();
        const width = ".o_erplibre_studio_settable[data-attribute=marker_icon_size_x] input[type=number]";
        expect(width).toHaveCount(1);
        expect(width).toHaveAttribute("placeholder", "64");
        expect(".o_erplibre_studio_settable[data-attribute=marker_popup_anchor_y] input").toHaveAttribute(
            "placeholder",
            "-32"
        );
        respond = () =>
            leafletPayload({
                field_latitude: "partner_latitude",
                field_longitude: "partner_latitude",
                marker_icon_size_x: "48",
            });
        await contains(width).edit("48");
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/leaflet_map",
            attribute: "marker_icon_size_x",
            value: "48",
        });
        // A value the server refuses: the input shows the value of the view again.
        respond = () => {
            throw makeServerError({message: "The marker width is not a whole number from 1 to 512."});
        };
        await contains(width).edit("600");
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(".o_notification").toHaveText(/from 1 to 512/);
        expect(width).toHaveValue(48);
    });

    test("the menu of views describes the map, and why it is missing", async () => {
        answer = kanbanPayload([inCard("name")]);
        const base = {view_id: false, xml_id: false, exists: false, pending: false, added: false, changes: 0};
        answer.view_list = [
            {
                ...base,
                type: "kanban",
                label: "Kanban",
                view_id: 12,
                exists: true,
                editable: true,
                reason: false,
                reason_code: false,
            },
            {
                ...base,
                type: "leaflet_map",
                label: "Map (Leaflet)",
                editable: false,
                reason: "Install the web_view_leaflet_map module to edit a map (leaflet) view.",
                reason_code: "needs_module",
            },
        ];
        await openEditor("kanban");
        await contains(".o_erplibre_studio_add_view").click();
        const entry = ".o_erplibre_studio_view_menu_unavailable[data-view-type=leaflet_map]";
        expect(entry).toHaveAttribute("data-reason", "needs_module");
        expect(entry).toHaveText(
            /Map \(Leaflet\)\s*not installed\s*Install the web_view_leaflet_map module.*view\.\s*Markers on a map, provided by web_view_leaflet_map/
        );
    });

    test("the entry of a map that creates its date field says so", async () => {
        answer = kanbanPayload([inCard("name")]);
        const base = {view_id: false, xml_id: false, exists: false, pending: false, added: false, changes: 0};
        answer.view_list = [
            {...base, type: "kanban", label: "Kanban", view_id: 12, exists: true, editable: true},
            {
                ...base,
                type: "leaflet_map",
                label: "Map (Leaflet)",
                editable: false,
                reason: "Contact has no Map (Leaflet) view to inherit.",
                reason_code: "no_view",
                description: "The map also creates the date_localization field it reads.",
            },
            {...base, type: "pivot", label: "Pivot", editable: false, reason: "-", reason_code: "no_view"},
        ];
        await openEditor("kanban");
        await contains(".o_erplibre_studio_add_view").click();
        expect(".o_erplibre_studio_view_menu_add[data-view-type=leaflet_map]").toHaveText(
            /Map \(Leaflet\).*Adding creates the default view.*The map also creates the date_localization field it reads\./s
        );
        expect(".o_erplibre_studio_view_menu_creates").toHaveCount(1);
    });
});

describe("erplibre_studio editor, geoengine", () => {
    const BOX = "//t[@t-name='info_box']";
    const GEO_FIELDS = {
        ...FIELDS,
        x_site: {string: "Site", type: "geo_point", store: true},
        x_spot: {string: "Spot", type: "geo_point", store: true},
    };

    /**
     * A GeoEngine view the project adds to the contacts, before Apply: it
     * loads the name and the geo field x_site, its « info_box » shows the
     * fields ``names``; two layers.
     */
    function geoPayload(names = ["name"], rootAttrs = {}, extraLayers = []) {
        const box = {
            path: BOX,
            tag: "t",
            kind: "template",
            label: "info_box",
            attrs: {"t-name": "info_box"},
            movable: false,
            drop: true,
            in_template: true,
            chain: null,
            template: "info_box",
            children: names.map((name) => inCard(name)),
        };
        const loaded = ["name", "x_site"].map((name, index) => ({
            path: `/geoengine/field[${index + 1}]`,
            tag: "field",
            kind: "field",
            name,
            label: GEO_FIELDS[name].string,
            attrs: {},
            movable: false,
            in_template: false,
            chain: null,
        }));
        const blocks = container(
            "/geoengine",
            "geoengine",
            [
                ...loaded,
                container("/geoengine/templates", "templates", [box], {
                    drop: false,
                    movable: false,
                    in_template: false,
                }),
            ],
            {movable: false, attrs: rootAttrs}
        );
        return payload("geoengine", blocks, {
            view: {
                id: false,
                name: "res.partner.geoengine.studio",
                xml_id: "studio_contacts.res_partner_view_geoengine",
                added: {
                    line_id: 7,
                    applied: false,
                    name: "res.partner.geoengine.studio",
                    xml_id: "studio_contacts.res_partner_view_geoengine",
                    layers: [
                        {
                            id: 1,
                            kind: "raster",
                            name: "OpenStreetMap",
                            geo_field: false,
                            geo_repr: "basic",
                            active_on_startup: false,
                        },
                        {
                            id: 2,
                            kind: "vector",
                            sequence: 10,
                            name: "Site",
                            geo_field: "x_site",
                            geo_repr: "basic",
                            active_on_startup: true,
                        },
                        ...extraLayers,
                    ],
                    geo_fields: [
                        ["x_site", "Site"],
                        ["x_spot", "Spot"],
                    ],
                    attribute_fields: [
                        ["color", "Color", true],
                        ["name", "Name", false],
                    ],
                },
            },
            operations: ["add_existing_field", "move", "remove", "hide", "set_attribute"],
            layout: {
                root: "/geoengine",
                card: BOX,
                templates: {info_box: BOX},
                loaded_fields: ["name", "x_site"],
                widgets: {},
            },
            settable: {geoengine: {editable: "bool_number"}},
            fields: GEO_FIELDS,
            palette: ["email", "phone", "x_spot"].map((name) => ({
                name,
                string: GEO_FIELDS[name].string,
                type: GEO_FIELDS[name].type,
            })),
        });
    }

    test("the info box, the loaded fields and the layers; a geo field goes among the loaded ones", async () => {
        answer = geoPayload();
        await openEditor("geoengine");
        expect(".o_erplibre_studio_geoengine_caption").toHaveText("The popup of a record on the map");
        expect(".o_erplibre_studio_card .o_erplibre_studio_field").toHaveCount(1);
        expect(".o_erplibre_studio_loaded .o_erplibre_studio_field").toHaveCount(2);
        expect(".o_erplibre_studio_loaded .o_erplibre_studio_field[data-name=x_site]").toHaveCount(1);
        expect(queryAllTexts(".o_erplibre_studio_geo_layer")).toEqual([
            "OpenStreetMap · Background",
            "Site · Site (x_site), drawn as is",
        ]);
        expect(".o_erplibre_studio_geo_layers .badge").toHaveCount(0);
        expect(".o_erplibre_studio_geo_pending").toHaveText(
            "The map shows once Apply creates the view and its layers."
        );

        // The view takes no new field: the existing ones show unfolded.
        expect(".o_erplibre_studio_palette [data-tab=new]").toHaveCount(0);
        // A geo field never goes in the info box.
        const dragging = await contains(".o_erplibre_studio_existing_field[data-name=x_spot]").drag();
        await dragging.moveTo(hook(BOX, "inside"));
        expect(hook(BOX, "inside")).not.toHaveClass("o_erplibre_studio_hook_active");
        await dragging.moveTo(hook("/geoengine", "inside", "loaded"));
        expect(hook("/geoengine", "inside", "loaded")).toHaveClass("o_erplibre_studio_hook_active");
        await dragging.drop(hook(BOX, "inside"));
        expect.verifySteps([]);

        respond = () => geoPayload();
        await contains(".o_erplibre_studio_existing_field[data-name=x_spot]").dragAndDrop(
            hook("/geoengine", "inside", "loaded")
        );
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: "/geoengine",
            position: "inside",
            field_name: "x_spot",
        });

        // Another field goes in the info box.
        respond = () => geoPayload(["name", "email"]);
        await contains(".o_erplibre_studio_existing_field[data-name=email]").dragAndDrop(hook(BOX, "inside"));
        expect.verifySteps(["apply_operation add_existing_field"]);
        expect(operations.pop()).toEqual({
            type: "add_existing_field",
            target: BOX,
            position: "inside",
            field_name: "email",
        });
    });

    test("Draw on the map is a toggle that writes 1; the preview waits for Apply", async () => {
        answer = geoPayload();
        await openEditor("geoengine");
        const toggle = ".o_erplibre_studio_settable[data-attribute=editable] input[type=checkbox]";
        expect(toggle).toHaveCount(1);
        expect(toggle).not.toBeChecked();
        expect(".o_erplibre_studio_settable[data-attribute=editable] label").toHaveText("Draw on the map");
        respond = () => geoPayload(["name"], {editable: "1"});
        await contains(toggle).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(operations.pop()).toEqual({
            type: "set_attribute",
            target: "/geoengine",
            attribute: "editable",
            value: "1",
        });
        expect(toggle).toBeChecked();

        await contains(".o_erplibre_studio_preview_toggle").click();
        expect(".o_notification").toHaveText(/The map shows once Apply creates the view and its layers/);
        expect(".o_erplibre_studio_view_preview").toHaveCount(0);

        // Refused: the toggle shows the value of the view again.
        respond = () => {
            throw makeServerError({message: "The view cannot change now."});
        };
        await contains(toggle).click();
        expect.verifySteps(["apply_operation set_attribute"]);
        expect(toggle).toBeChecked();
    });
    // A second vector layer, on the geo field x_spot.
    const SPOTS = {
        id: 3,
        kind: "vector",
        sequence: 20,
        name: "Spots",
        geo_field: "x_spot",
        geo_repr: "basic",
        active_on_startup: false,
    };

    test("a layer row opens its form; the range shows for a colored layer; Save sends it", async () => {
        const saved = [];
        onRpc("erplibre.studio.editor", "save_geo_layer", (args) => {
            expect.step("save_geo_layer");
            saved.push(args.args[1]);
            return {...geoPayload(["name"], {}, [SPOTS]), saved_geo_layer: args.args[1].id || 3};
        });
        answer = geoPayload();
        await openEditor("geoengine");
        // The background shows read only.
        await contains(".o_erplibre_studio_geo_layer[data-kind=raster] .o_erplibre_studio_geo_layer_pick").click();
        expect(".o_erplibre_studio_geo_background_note").toHaveCount(1);
        expect(".o_erplibre_studio_geo_layer_form").toHaveCount(0);

        await contains(".o_erplibre_studio_geo_layer[data-id='2'] .o_erplibre_studio_geo_layer_pick").click();
        expect(".o_erplibre_studio_geo_layer[data-id='2']").toHaveClass("o_erplibre_studio_geo_layer_selected");
        expect(".o_erplibre_studio_geo_layer_name").toHaveValue("Site");
        expect(".o_erplibre_studio_geo_layer_field").toHaveValue("x_site");
        expect(".o_erplibre_studio_geo_layer_repr").toHaveValue("basic");
        expect(".o_erplibre_studio_geo_layer_range").toHaveCount(0);
        expect(".o_erplibre_studio_geo_layer_load").toHaveCount(0);
        // A single vector layer stays: no Remove.
        expect(".o_erplibre_studio_geo_layer_remove").toHaveCount(0);

        await contains(".o_erplibre_studio_geo_layer_repr").select("colored");
        expect(".o_erplibre_studio_geo_layer_range").toHaveCount(1);
        expect(".o_erplibre_studio_geo_layer_classification option[value=interval]").toHaveAttribute("disabled");
        await contains(".o_erplibre_studio_geo_layer_attribute").select("name");
        expect(".o_erplibre_studio_geo_layer_classification option[value=quantile]").toHaveAttribute("disabled");
        // The view loads the name already.
        expect(".o_erplibre_studio_geo_layer_load").toHaveCount(0);
        await contains(".o_erplibre_studio_geo_layer_attribute").select("color");
        expect(".o_erplibre_studio_geo_layer_classification option[value=interval]").not.toHaveAttribute("disabled");
        expect(".o_erplibre_studio_geo_layer_load").toHaveText(
            "Save also loads color in the view: the map reads them from the records."
        );
        await contains(".o_erplibre_studio_geo_layer_classification").select("interval");
        await contains(".o_erplibre_studio_geo_layer_classes").edit("4");
        await contains(".o_erplibre_studio_geo_layer_save").click();
        expect.verifySteps(["save_geo_layer"]);
        expect(saved.pop()).toEqual({
            id: 2,
            name: "Site",
            geo_field: "x_site",
            geo_repr: "colored",
            active_on_startup: true,
            attribute_field: "color",
            classification: "interval",
            nb_class: 4,
            begin_color: "#ffffff",
            end_color: "#ff680a",
        });

        // Add layer: a basic layer of the first geo field, then its own.
        await contains(".o_erplibre_studio_geo_layer_add").click();
        expect(".o_erplibre_studio_inspector_title").toHaveText("New layer");
        expect(".o_erplibre_studio_geo_layer_name").toHaveValue("Site");
        await contains(".o_erplibre_studio_geo_layer_field").select("x_spot");
        await contains(".o_erplibre_studio_geo_layer_name").edit(" Spots ");
        expect(".o_erplibre_studio_geo_layer_load").toHaveText(
            "Save also loads x_spot in the view: the map reads them from the records."
        );
        await contains(".o_erplibre_studio_geo_layer_save").click();
        expect.verifySteps(["save_geo_layer"]);
        expect(saved.pop()).toEqual({
            name: "Spots",
            geo_field: "x_spot",
            geo_repr: "basic",
            active_on_startup: true,
        });
        // The inspector shows the layer saved, its row selected.
        expect(".o_erplibre_studio_geo_layer[data-id='3']").toHaveClass("o_erplibre_studio_geo_layer_selected");
        expect(".o_erplibre_studio_inspector_title").toHaveText("Spots");

        // Its place: up swaps it with the layer before.
        expect(".o_erplibre_studio_geo_layer_down").toHaveAttribute("disabled");
        await contains(".o_erplibre_studio_geo_layer_up").click();
        expect.verifySteps(["save_geo_layer"]);
        expect(saved.pop()).toMatchObject({id: 3, geo_field: "x_spot", sequence: 10});
    });

    test("Discard closes the form of a layer: its layers come back under new ids", async () => {
        onRpc("erplibre.studio.editor", "project_action", (args) => {
            expect.step(`project_action ${args.args[1]}`);
            const data = geoPayload();
            data.view.added.layers = data.view.added.layers.map((layer) => ({...layer, id: layer.id + 10}));
            return data;
        });
        answer = geoPayload(["name"], {}, [SPOTS]);
        await openEditor("geoengine");
        await contains(".o_erplibre_studio_geo_layer[data-id='3'] .o_erplibre_studio_geo_layer_pick").click();
        expect(".o_erplibre_studio_geo_layer_form").toHaveCount(1);
        await contains(".o_erplibre_studio_apply_menu").click();
        await contains(".o_erplibre_studio_discard").click();
        expect.verifySteps(["project_action action_discard"]);
        // The inspector of the layer closed: no form, no « no longer in the view ».
        expect(".o_erplibre_studio_geo_layer_form").toHaveCount(0);
        expect(".o_erplibre_studio_geo_layer_gone").toHaveCount(0);
        expect(".o_erplibre_studio_geo_layer_selected").toHaveCount(0);
        expect(queryAllTexts(".o_erplibre_studio_geo_layer").length).toBe(2);
    });

    test("a layer that leaves the view under its open form: no form to save", async () => {
        answer = geoPayload(["name"], {}, [SPOTS]);
        await openEditor("geoengine");
        await contains(".o_erplibre_studio_geo_layer[data-id='3'] .o_erplibre_studio_geo_layer_pick").click();
        expect(".o_erplibre_studio_geo_layer_name").toHaveValue("Spots");
        // The server answers with a payload without the layer.
        onRpc("erplibre.studio.editor", "save_geo_layer", () => {
            expect.step("save_geo_layer");
            return {...geoPayload(), saved_geo_layer: 3};
        });
        await contains(".o_erplibre_studio_geo_layer_name").edit("Spot list");
        await contains(".o_erplibre_studio_geo_layer_save").click();
        expect.verifySteps(["save_geo_layer"]);
        expect(".o_erplibre_studio_geo_layer_form").toHaveCount(0);
        expect(".o_erplibre_studio_geo_layer_gone").toHaveText("This layer is no longer in the view.");
    });

    test("a map the project does not add: its layers are not listed as none", async () => {
        answer = geoPayload();
        delete answer.view.added;
        await openEditor("geoengine");
        expect(".o_erplibre_studio_geo_layers_elsewhere").toHaveCount(1);
        expect(".o_erplibre_studio_geo_layer").toHaveCount(0);
        expect(".o_erplibre_studio_geo_layers").not.toHaveText(/No layer/);
        expect(".o_erplibre_studio_geo_layer_add").toHaveCount(0);
    });

    test("Remove asks for a confirmation, then sends remove_geo_layer", async () => {
        onRpc("erplibre.studio.editor", "remove_geo_layer", (args) => {
            expect.step(`remove_geo_layer ${args.args[1]}`);
            return geoPayload();
        });
        answer = geoPayload(["name"], {}, [SPOTS]);
        await openEditor("geoengine");
        await contains(".o_erplibre_studio_geo_layer[data-id='3'] .o_erplibre_studio_geo_layer_pick").click();
        await contains(".o_erplibre_studio_geo_layer_remove").click();
        expect(".modal-body").toHaveText("The layer Spots leaves the draft.");
        await contains(".modal-footer .btn-secondary").click();
        expect.verifySteps([]);
        expect(".o_erplibre_studio_geo_layer_form").toHaveCount(1);

        await contains(".o_erplibre_studio_geo_layer_remove").click();
        await contains(".modal-footer .btn-primary").click();
        expect.verifySteps(["remove_geo_layer 3"]);
        expect(".o_erplibre_studio_geo_layer_form").toHaveCount(0);
        expect(".o_erplibre_studio_geo_layer").toHaveCount(2);
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
