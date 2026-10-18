// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {animationFrame, runAllTimers} from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    defineWebModels,
    fields,
    getService,
    makeServerError,
    models,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    serverState,
} from "@web/../tests/web_test_helpers";
import {ORM} from "@web/core/orm_service";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {chainWarning, groupValue, parseGroupValue} from "@erplibre_studio/editor/studio_groups";
import {accessRows} from "@erplibre_studio/editor/studio_models";
import {
    PreviewWriteError,
    StudioModelPreview,
    pendingViews,
    previewOrm,
    previewViewProps,
    previewWriteErrorHandler,
} from "@erplibre_studio/editor/studio_preview";
import {fieldTypeFits, relationField, sortComodels} from "@erplibre_studio/editor/studio_relations";

const ORDER = "x_j4_order";
const LINE = "x_j4_line";
const STUDIO_ICON = "erplibre_studio,static/description/icon.png";
const BASE_ICON = "base,static/description/icon.png";
const ALL_PERMS = {perm_read: true, perm_write: true, perm_create: true, perm_unlink: true};
const LEFT = "//group[@name='studio_left']";

function info(name, type, string, extra = {}) {
    return {
        name,
        type,
        string,
        required: false,
        readonly: false,
        store: true,
        searchable: true,
        sortable: true,
        groupable: false,
        relation: false,
        selection: [],
        ...extra,
    };
}

function baseFields() {
    return {
        id: info("id", "integer", "ID", {readonly: true}),
        display_name: info("display_name", "char", "Display Name", {readonly: true, store: false}),
        x_name: info("x_name", "char", "Name", {required: true}),
    };
}

/** The answer of get_model_preview for the order, in the shape of get_views. */
function simulation(mode = "simulation") {
    const order = {
        ...baseFields(),
        x_lines: info("x_lines", "one2many", "Lines", {relation: LINE, relation_field: "x_j4_order_id"}),
    };
    const line = {
        ...baseFields(),
        x_j4_order_id: info("x_j4_order_id", "many2one", "J4 order", {relation: ORDER}),
    };
    return {
        mode,
        model: ORDER,
        views: {
            form: {
                arch:
                    `<form string="J4 order"><sheet><div class="oe_title"><h1><field name="x_name"/></h1></div>` +
                    `<group name="studio_main"><group name="studio_left"><field name="x_lines">` +
                    `<list editable="bottom"><field name="x_name"/></list></field></group>` +
                    `<group name="studio_right"/></group></sheet></form>`,
                id: false,
            },
            list: {arch: `<list string="J4 order"><field name="x_name"/></list>`, id: false},
            search: {arch: `<search string="J4 order"><field name="x_name"/></search>`, id: false},
        },
        models: {[ORDER]: {fields: order}, [LINE]: {fields: line}},
        defaults: {x_name: false, x_lines: []},
        model_defaults: {[ORDER]: {x_name: false, x_lines: []}, [LINE]: {x_name: false, x_j4_order_id: false}},
        pending_models: [ORDER, LINE],
        approved: mode === "real",
    };
}

const SHOP = {
    id: 1,
    name: "J4 shop",
    icon: false,
    xml_name: "menu_app",
    menu_sequence: 50,
    sequence: 10,
    applied: false,
    models: [7],
    groups: [3, 4],
    chain: false,
};

const GROUPS = [
    {
        id: 3,
        app_id: 1,
        name: "J4 user",
        xml_name: "group_j4_shop_j4_user",
        comment: "",
        implied: [],
        implied_groups: [[1, "Role / User"]],
        missing_implied: [],
        applied: false,
    },
    {
        id: 4,
        app_id: 1,
        name: "J4 admin",
        xml_name: "group_j4_shop_j4_admin",
        comment: "",
        implied: [],
        implied_groups: [[1, "Role / User"]],
        missing_implied: ["studio_j4.group_gone"],
        applied: false,
    },
];

function orderLine(extra = {}) {
    return {
        id: 7,
        model: ORDER,
        name: "J4 order",
        chatter: false,
        menu_mode: "app",
        app_id: 1,
        menu_parent: false,
        menu_name: "",
        applied: false,
        views: {},
        pending_views: {form: false, list: false, search: false},
        ...extra,
    };
}

function container(path, tag, children, extra = {}) {
    return {path, tag, kind: "container", label: tag, attrs: {}, movable: false, drop: true, children, ...extra};
}

/** The blocks of the default form of the order, the field ``extra`` in its left column. */
function formBlocks(extra = []) {
    const name = {path: "//field[@name='x_name']", tag: "field", kind: "field", name: "x_name", label: "Name"};
    return container(
        "/form",
        "form",
        [
            container("/form/sheet", "sheet", [
                container("/form/sheet/div", "div", [{...name, attrs: {}, movable: true}]),
                container("//group[@name='studio_main']", "group", [
                    container(LEFT, "group", extra),
                    container("//group[@name='studio_right']", "group", []),
                ]),
            ]),
        ],
        {drop: false}
    );
}

/** The editor payload of the pending form of the order; ``project`` completes the project. */
function payload(project = {}, {blocks = formBlocks(), fields = {}} = {}) {
    return {
        model: ORDER,
        model_name: "J4 order",
        view_type: "form",
        view_types: ["form", "list", "search"],
        view: {id: false, name: `${ORDER}.form`, xml_id: false, pending: true, model_line_id: 7},
        blocks,
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "hide"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        fields: {x_name: {string: "Name", type: "char"}, ...fields},
        palette: [],
        field_types: ["char", "one2many", "many2many"],
        changes: [],
        errors: [],
        project: {
            id: 3,
            name: "J4",
            module_name: "studio_j4",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 0,
            item_count: 3,
            applied: false,
            app: false,
            apps: [SHOP],
            groups: GROUPS,
            models: [orderLine()],
            access: [],
            rules: [],
            approved: false,
            approved_by: false,
            approved_date: false,
            real_preview_available: false,
            ...project,
        },
        projects: [{id: 3, name: "J4", module_name: "studio_j4", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        mail_available: false,
    };
}

const CHOICES = {
    mail_available: false,
    icons: [
        {value: STUDIO_ICON, label: "ERPLibre studio", url: "/erplibre_studio/static/description/icon.png"},
        {value: BASE_ICON, label: "Base", url: "/base/static/description/icon.png"},
    ],
    menus: [],
    groups: [
        {id: 1, name: "Role / User", xml_id: "base.group_user"},
        {id: 4, name: "Administration / Settings", xml_id: "base.group_system"},
        {id: false, line_id: 3, name: "J4 shop / J4 user", xml_id: "studio_j4.group_j4_shop_j4_user", project: true},
    ],
    apps: [{id: 1, name: "J4 shop", icon: false, xml_name: "menu_app"}],
    models: [
        ["res.partner", "Contact"],
        [ORDER, "J4 order"],
    ],
    taken_models: [],
};

const REPORT = {
    models: [{model: ORDER, name: "J4 order", count: 2}],
    fields: [{model: "res.partner", name: "x_j4_level", label: "Level", filled: 0}],
    views: [{name: `${ORDER}.form`, kind: "default"}],
    changes_removed: 1,
    menus: [{name: "J4 shop"}],
    actions: [],
    access: [{name: "access_x_j4_order_user", group: "Role / User"}],
    rules: [],
    groups: [{name: "J4 shop / J4 user", users: 0}],
    categories: [{name: "J4 shop"}],
    tables: ["x_studio_j4_j4_order_tags_rel"],
};

const TAG = "x_j4_tag";

/** A model of the database the preview points at. */
class PreviewPartner extends models.Model {
    _name = "j4.partner";
    name = fields.Char();
    _records = [{id: 1, name: "Existing"}];
    _views = {
        form: `<form><field name="name"/></form>`,
        list: `<list><field name="name"/></list>`,
        search: `<search><field name="name"/></search>`,
    };
}

/** A simulation answer: a many2one to a model of the database, a many2many sub-list to a pending model. */
function richSimulation() {
    const order = {
        ...baseFields(),
        x_partner_id: info("x_partner_id", "many2one", "Partner", {relation: "j4.partner"}),
        x_tags: info("x_tags", "many2many", "Tags", {relation: TAG}),
    };
    return {
        mode: "simulation",
        model: ORDER,
        views: {
            form: {
                arch:
                    `<form><sheet><group><field name="x_name"/><field name="x_partner_id"/>` +
                    `<field name="x_tags"><list><field name="x_name"/></list></field></group></sheet></form>`,
                id: false,
            },
            list: {arch: `<list><field name="x_name"/></list>`, id: false},
            search: {arch: `<search><field name="x_name"/></search>`, id: false},
        },
        models: {
            [ORDER]: {fields: order},
            [TAG]: {fields: baseFields()},
            "j4.partner": {fields: {id: info("id", "integer", "ID"), display_name: info("display_name", "char", "Name")}},
        },
        defaults: {x_name: false, x_partner_id: false, x_tags: []},
        model_defaults: {[ORDER]: {x_name: false, x_partner_id: false, x_tags: []}, [TAG]: {x_name: false}},
        pending_models: [ORDER, TAG],
        approved: false,
    };
}

async function mountPreview(data) {
    await mountWithCleanup(StudioModelPreview, {
        props: {
            data,
            viewType: "form",
            mode: "simulation",
            line: orderLine(),
            project: payload().project,
            onView: () => {},
            onApprove: () => {},
            onUnapprove: () => {},
            onClose: () => {},
        },
    });
    await animationFrame();
}

let answer;
let respond;
let calls;

function editorRpc(method) {
    onRpc("erplibre.studio.editor", method, (args) => {
        calls.push({method, args: args.args, kwargs: args.kwargs});
        const result = respond[method] ? respond[method](args) : answer;
        if (result && result.project) {
            answer = result;
        }
        return result;
    });
}

const lastCall = (method) => calls.filter((c) => c.method === method).pop();

beforeEach(() => {
    serverState.debug = "1";
    defineWebModels();
    calls = [];
    respond = {};
    for (const method of [
        "get_editor_data",
        "get_studio_choices",
        "get_comodels",
        "get_relation_choices",
        "get_model_preview",
        "get_revert_report",
        "get_apply_report",
        "apply_operation",
        "project_action",
        "save_rule",
        "save_app",
        "remove_app",
        "save_group",
        "remove_group",
        "set_access",
    ]) {
        editorRpc(method);
    }
    respond.get_studio_choices = () => JSON.parse(JSON.stringify(CHOICES));
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    patchWithCleanup(getService("menu"), {
        async reload() {
            expect.step("menu reload");
        },
    });
    await getService("action").doAction(customizeAction({resModel: ORDER, viewType: "form", viewId: false}));
    await animationFrame();
}

describe.current.tags("desktop");
describe("erplibre_studio j4", () => {
    test("the helpers: group values, access rows, comodels, relation fields", () => {
        expect(groupValue({id: 4})).toBe("4");
        expect(groupValue({id: false, line_id: 3, project: true})).toBe("line:3");
        expect(parseGroupValue("line:3")).toEqual({group_line_id: 3});
        expect(parseGroupValue("4")).toEqual({group_id: 4});
        expect(parseGroupValue("")).toBe(null);
        expect(
            accessRows([
                {id: 1, model: ORDER, group: false, group_line: [3, "J4 shop / J4 user"], ...ALL_PERMS},
                {id: 2, model: ORDER, group: [1, "Role / User"], ...ALL_PERMS, perm_unlink: false},
            ])
        ).toEqual([
            {model: ORDER, group_line_id: 3, ...ALL_PERMS},
            {model: ORDER, group_id: 1, ...ALL_PERMS, perm_unlink: false},
        ]);
        expect(fieldTypeFits("one2many", "form")).toBe(true);
        expect(fieldTypeFits("one2many", "list")).toBe(false);
        expect(fieldTypeFits("many2many", "kanban")).toBe(true);
        expect(fieldTypeFits("many2many", "search")).toBe(false);
        expect(fieldTypeFits("char", "search")).toBe(true);
        const comodels = [
            ["res.partner", "Contact"],
            [LINE, "J4 line"],
            ["res.partner.category", "Contact Tag"],
        ];
        expect(sortComodels(comodels, [LINE]).map((c) => c[0])).toEqual([LINE, "res.partner", "res.partner.category"]);
        expect(sortComodels(comodels, [LINE], "tag").map((c) => c[0])).toEqual(["res.partner.category"]);
        const state = {
            label: " Lines ",
            comodel: LINE,
            inverseMode: "create",
            inverseName: "",
            inverseLabel: "J4 order",
            choices: {inverse_name: "x_j4_order_id"},
        };
        expect(relationField("one2many", state)).toEqual({
            ttype: "one2many",
            field_description: "Lines",
            relation: LINE,
            inverse: {create: true, name: "x_j4_order_id", field_description: "J4 order"},
        });
        expect(relationField("one2many", {...state, inverseMode: "existing", inverseName: "x_order_id"})).toEqual({
            ttype: "one2many",
            field_description: "Lines",
            relation: LINE,
            relation_field: "x_order_id",
        });
        expect(relationField("many2many", state)).toEqual({
            ttype: "many2many",
            field_description: "Lines",
            relation: LINE,
        });
        expect(chainWarning({groups: GROUPS}, SHOP)).toBe(true);
        expect(chainWarning({groups: GROUPS}, {...SHOP, chain: true})).toBe(false);
    });

    test("the orm of a preview answers the pending models and never writes", async () => {
        const data = simulation();
        const real = new ORM();
        real.rpc = async (url, params) => {
            expect.step(`${params.model}.${params.method}`);
            return [{id: 1, display_name: "Gold"}];
        };
        const orm = previewOrm(real, data);
        expect(await orm.call(ORDER, "onchange", [[], {}, [], {}])).toEqual({value: {x_name: false, x_lines: []}});
        expect(await orm.call(LINE, "onchange", [[], {}, [], {}])).toEqual({
            value: {x_name: false, x_j4_order_id: false},
        });
        expect(await orm.webSearchRead(ORDER, [], {specification: {}})).toEqual({length: 0, records: []});
        expect(await orm.webReadGroup(ORDER, [], ["x_name"], ["x_name"])).toEqual({groups: [], length: 0});
        expect(await orm.searchCount(ORDER, [])).toBe(0);
        expect(await orm.call(ORDER, "web_name_search", [])).toEqual([]);
        expect(Object.keys(await orm.call(ORDER, "fields_get", []))).toInclude("x_lines");
        expect.verifySteps([]);
        // A model of the database: its reads reach the server.
        expect(await orm.read("res.partner.category", [1], ["display_name"])).toEqual([{id: 1, display_name: "Gold"}]);
        expect(await orm.silent.searchRead("res.partner", [], ["display_name"])).toHaveLength(1);
        expect.verifySteps(["res.partner.category.read", "res.partner.search_read"]);
        // Nothing that writes, on any model.
        await expect(orm.webSave(ORDER, [], {x_name: "A"})).rejects.toThrow(PreviewWriteError);
        await expect(orm.create("res.partner", [{name: "A"}])).rejects.toThrow(PreviewWriteError);
        await expect(orm.unlink("res.partner", [1])).rejects.toThrow(PreviewWriteError);
        expect.verifySteps([]);
        // The onchange of a model of the database, a comodel of a sub-list:
        // answered without the server, which does not know a pending inverse.
        data.models["res.partner"] = {fields: {name: info("name", "char", "Name"), x_tags: info("x_tags", "many2many", "Tags")}};
        expect(await orm.call("res.partner", "onchange", [[], {}, [], {name: {}, x_tags: {}, x_j4_order_id: {}}])).toEqual({
            value: {name: false, x_tags: []},
        });
        expect.verifySteps([]);
        // The views of a pending comodel the answer does not hold: its name.
        expect(pendingViews(data, LINE, [[false, "list"], [false, "search"]])).toEqual({
            list: {arch: `<list><field name="x_name"/></list>`, id: false},
            search: {arch: `<search><field name="x_name"/></search>`, id: false},
        });
        // The user sees a notification, not an error dialog.
        const env = {
            services: {notification: {add: (message, options) => expect.step(`notification ${options.type}`)}},
        };
        expect(previewWriteErrorHandler(env, new Error("x"), new PreviewWriteError(ORDER, "web_save"))).toBe(true);
        expect(previewWriteErrorHandler(env, new Error("x"), new Error("other"))).toBe(false);
        expect.verifySteps(["notification warning"]);
        // The View loads nothing: arch and fields are given; a search shows above the list.
        const props = previewViewProps(data, "search");
        expect([props.type, props.arch, props.useSampleModel, props.loadIrFilters]).toEqual([
            "list",
            data.views.list.arch,
            true,
            false,
        ]);
        expect(previewViewProps(data, "form").resId).toBe(false);
    });

    test("the simulation renders the form with its sub-list, the list with samples; real once approved", async () => {
        answer = payload({}, {fields: {x_lines: {string: "Lines", type: "one2many", relation: LINE, project: true}}});
        respond.get_model_preview = (args) => {
            expect.step(`get_model_preview ${args.args.slice(1).join(" ")}`);
            return {...simulation(args.args[3]), view_type: args.args[2]};
        };
        await openEditor();
        // The pending model: Form, List and Search open its default views.
        expect(".o_erplibre_studio_open_pending").toHaveCount(3);
        await contains(".o_erplibre_studio_preview_toggle").click();
        expect.verifySteps(["get_model_preview 7 form simulation"]);
        expect(".o_erplibre_studio_preview_mode").toHaveText("Simulation");
        expect(".o_erplibre_studio_preview_note").toHaveText("Nothing is saved: the model does not exist yet.");
        expect(".o_erplibre_studio_model_preview .o_form_view .o_field_widget[name=x_name] input").toHaveCount(1);
        expect(".o_erplibre_studio_model_preview .o_field_one2many .o_list_renderer").toHaveCount(1);
        // A line of the sub-list: the defaults of the pending comodel.
        await contains(".o_field_one2many .o_field_x2many_list_row_add a").click();
        expect(".o_field_one2many .o_data_row").toHaveCount(1);
        // The real mode needs the approval.
        expect(".o_erplibre_studio_preview_real").not.toBeEnabled();

        await contains(".o_erplibre_studio_preview_type[data-view-type=list]").click();
        expect.verifySteps(["get_model_preview 7 list simulation"]);
        expect(".o_erplibre_studio_model_preview .o_list_view .o_view_sample_data").toHaveCount(1);
        expect(".o_erplibre_studio_model_preview .o_data_row").not.toHaveCount(0);

        respond.project_action = (args) => {
            expect.step(`project_action ${args.args[1]}`);
            return payload({
                revision: 1,
                approved: true,
                approved_by: [2, "Mitchell Admin"],
                approved_date: "2026-01-02 03:04:05",
                real_preview_available: true,
            });
        };
        await contains(".o_erplibre_studio_approve").click();
        // The preview follows the draft: shown again once approved.
        expect.verifySteps(["project_action action_approve", "get_model_preview 7 list simulation"]);
        expect(".o_erplibre_studio_approved").toHaveText(/Approved by Mitchell Admin/);
        expect(".o_erplibre_studio_preview_real").toBeEnabled();
        await contains(".o_erplibre_studio_preview_real").click();
        expect.verifySteps(["get_model_preview 7 list real"]);
        expect(".o_erplibre_studio_preview_mode").toHaveAttribute("data-mode", "real");
        expect(".o_erplibre_studio_preview_mode").toHaveText("Real (rolled back)");

        // A view that does not render answers its error.
        respond.get_model_preview = () => ({mode: "real", model: ORDER, error: "Field x_nope does not exist"});
        await contains(".o_erplibre_studio_preview_type[data-view-type=form]").click();
        expect(".o_erplibre_studio_preview_error").toHaveText("Field x_nope does not exist");
        expect(".o_erplibre_studio_preview_error").toHaveAttribute("role", "alert");

        // Withdrawing the approval goes back to the simulation.
        respond.get_model_preview = (args) => ({...simulation(args.args[3]), view_type: args.args[2]});
        respond.project_action = () => payload({revision: 2, approved: false, approved_by: false});
        await contains(".o_erplibre_studio_unapprove").click();
        expect(".o_erplibre_studio_preview_mode").toHaveAttribute("data-mode", "simulation");
        await contains(".o_erplibre_studio_preview_close").click();
        expect(".o_erplibre_studio_model_preview").toHaveCount(0);
        expect(".o_erplibre_studio_field[data-name=x_name]").toHaveCount(1);
    });

    test("a one2many dropped into the form: its inverse, chosen or created", async () => {
        answer = payload({models: [orderLine(), orderLine({id: 8, model: LINE, name: "J4 line", app_id: 2})]});
        respond.get_comodels = () => [
            ["res.partner", "Contact"],
            [LINE, "J4 line"],
        ];
        respond.get_relation_choices = (args) => {
            expect.step(`get_relation_choices ${args.args.slice(1).join(" ")}`);
            if (args.args[2] === "res.partner") {
                return {
                    inverses: [{name: "x_order_id", label: "Order", pending: false}],
                    inverse_name: "x_j4_order_id",
                    inverse_label: "J4 order",
                    on_delete: "set null",
                    protected: false,
                };
            }
            return {inverses: [], inverse_name: "x_j4_order_id", inverse_label: "J4 order", on_delete: "cascade"};
        };
        await openEditor();
        // A one2many shows in a form only; the palette offers both relations here.
        expect(".o_erplibre_studio_new_field[data-type=one2many]").toHaveCount(1);
        expect(".o_erplibre_studio_new_field[data-type=many2many]").toHaveCount(1);
        await contains(".o_erplibre_studio_new_field[data-type=one2many]").dragAndDrop(
            `.o_erplibre_studio_hook[data-target="${LEFT}"][data-position=inside]`
        );
        expect(".o_erplibre_studio_relation_dialog").toHaveCount(1);
        expect(".o_erplibre_studio_relation_save").not.toBeEnabled();
        // The models of the project come first.
        expect(".o_erplibre_studio_relation_comodel option:eq(1)").toHaveValue(LINE);

        await contains(".o_erplibre_studio_relation_comodel").select("res.partner");
        expect.verifySteps(["get_relation_choices x_j4_order res.partner one2many"]);
        expect(".o_erplibre_studio_relation_label").toHaveValue("Contact");
        expect("#o_erplibre_studio_inverse_existing").toBeChecked();
        expect(".o_erplibre_studio_relation_inverse_name").toHaveValue("x_order_id");

        // The pending line has no inverse yet: the studio creates it.
        await contains(".o_erplibre_studio_relation_comodel").select(LINE);
        expect.verifySteps([`get_relation_choices x_j4_order ${LINE} one2many`]);
        expect(".o_erplibre_studio_relation_label").toHaveValue("J4 line");
        expect("#o_erplibre_studio_inverse_existing").not.toBeEnabled();
        expect("#o_erplibre_studio_inverse_create").toBeChecked();
        expect("label[for=o_erplibre_studio_inverse_create]").toHaveText("Create the field x_j4_order_id on J4 line");
        await contains(".o_erplibre_studio_relation_label").edit("Lines");
        await contains(".o_erplibre_studio_inverse_label").edit("Order");

        const field = {string: "Lines", type: "one2many", relation: LINE, project: true, pending: true};
        respond.apply_operation = () =>
            payload(
                {revision: 1},
                {
                    blocks: formBlocks([
                        {
                            path: "//field[@name='x_lines']",
                            tag: "field",
                            kind: "field",
                            name: "x_lines",
                            label: "Lines",
                            attrs: {},
                            movable: true,
                        },
                    ]),
                    fields: {x_lines: field},
                }
            );
        await contains(".o_erplibre_studio_relation_save").click();
        expect(lastCall("apply_operation").args[4]).toEqual({
            type: "add_field",
            target: LEFT,
            position: "inside",
            field: {
                ttype: "one2many",
                field_description: "Lines",
                relation: LINE,
                inverse: {create: true, name: "x_j4_order_id", field_description: "Order"},
            },
        });
        expect(".o_erplibre_studio_relation_dialog").toHaveCount(0);
        // The form shows its sub-list, selected.
        expect(".o_erplibre_studio_field[data-name=x_lines] .o_erplibre_studio_sublist").toHaveAttribute(
            "data-comodel",
            LINE
        );
        expect(".o_erplibre_studio_field[data-name=x_lines]").toHaveClass("o_erplibre_studio_selected");
    });

    test("a many2many shows its relation table, named by the server", async () => {
        answer = payload();
        respond.get_comodels = () => [["res.partner.category", "Contact Tag"]];
        respond.get_relation_choices = (args) => {
            expect.step(`get_relation_choices ${args.args[2]} ${args.args[3]} ${args.kwargs.label}`);
            const field = args.kwargs.label === "Tags" ? "tags" : "contact_tag";
            return {
                relation_table: `x_studio_j4_j4_order_${field}_rel`,
                column1: "x_j4_order_id",
                column2: "res_partner_category_id",
            };
        };
        await openEditor();
        await contains(".o_erplibre_studio_new_field[data-type=many2many]").dragAndDrop(
            `.o_erplibre_studio_hook[data-target="${LEFT}"][data-position=inside]`
        );
        await contains(".o_erplibre_studio_relation_comodel").select("res.partner.category");
        expect.verifySteps(["get_relation_choices res.partner.category many2many Contact Tag"]);
        expect(".o_erplibre_studio_relation_inverse").toHaveCount(0);
        expect(".o_erplibre_studio_relation_table_name").toHaveText("x_studio_j4_j4_order_contact_tag_rel");
        expect(".o_erplibre_studio_relation_columns").toHaveText("x_j4_order_id, res_partner_category_id");
        // The table follows the label; it is never typed in.
        expect("input.o_erplibre_studio_relation_table_name").toHaveCount(0);
        await contains(".o_erplibre_studio_relation_label").edit("Tags");
        expect.verifySteps(["get_relation_choices res.partner.category many2many Tags"]);
        expect(".o_erplibre_studio_relation_table_name").toHaveText("x_studio_j4_j4_order_tags_rel");
        respond.apply_operation = () => payload({revision: 1});
        await contains(".o_erplibre_studio_relation_save").click();
        expect(lastCall("apply_operation").args[4].field).toEqual({
            ttype: "many2many",
            field_description: "Tags",
            relation: "res.partner.category",
        });
    });

    test("apps and groups: an app, a group implying another, the chain warning", async () => {
        answer = payload();
        await openEditor();
        await contains(".o_erplibre_studio_apps_toggle").click();
        expect(".o_erplibre_studio_apps_panel").toHaveCount(1);
        expect(".o_erplibre_studio_palette").toHaveCount(0);
        expect(".o_erplibre_studio_app_card[data-app=menu_app] .o_erplibre_studio_group").toHaveCount(2);
        // Two groups that do not imply each other: checkboxes in developer mode only.
        expect(".o_erplibre_studio_chain_warning").toHaveCount(1);
        expect(
            ".o_erplibre_studio_group[data-group=group_j4_shop_j4_admin] .o_erplibre_studio_missing_group"
        ).toHaveText("This group no longer exists: studio_j4.group_gone");
        expect(".o_erplibre_studio_missing_group").toHaveAttribute("role", "alert");

        // « J4 admin » implies « J4 user ».
        await contains(
            ".o_erplibre_studio_group[data-group=group_j4_shop_j4_admin] .o_erplibre_studio_edit_group"
        ).click();
        expect(".o_erplibre_studio_group_form_name").toHaveValue("J4 admin");
        expect(".o_erplibre_studio_implied_group").toHaveText("Role / User");
        // A project group never implies the Settings.
        expect(".o_erplibre_studio_add_implied_group option[value='4']").toHaveCount(0);
        expect(".o_erplibre_studio_add_implied_line option[value='4']").toHaveCount(0);
        await contains(".o_erplibre_studio_add_implied_line").select("3");
        expect(".o_erplibre_studio_implied_line[data-id='3']").toHaveText("J4 user");
        const chained = [GROUPS[0], {...GROUPS[1], implied: [[3, "J4 user"]], missing_implied: []}];
        respond.save_group = () => ({
            ...payload({revision: 1, apps: [{...SHOP, chain: true}], groups: chained}),
            saved_group: 4,
        });
        await contains(".o_erplibre_studio_save_group").click();
        expect(lastCall("save_group").args[1]).toEqual({
            name: "J4 admin",
            app_id: 1,
            comment: "",
            implied_line_ids: [3],
            implied_group_ids: [1],
            id: 4,
        });
        expect(lastCall("save_group").kwargs.revision).toBe(0);
        expect(".o_erplibre_studio_group_form").toHaveCount(0);
        expect(".o_erplibre_studio_chain_warning").toHaveCount(0);
        expect(".o_erplibre_studio_group_implied").toHaveText("J4 user");

        // A new group implies the internal users by default.
        await contains(".o_erplibre_studio_new_group").click();
        expect(".o_erplibre_studio_implied_group[data-id='1']").toHaveCount(1);
        await contains(".o_erplibre_studio_group_form_name").edit("J4 reader");
        respond.save_group = () => payload({revision: 2, groups: chained});
        await contains(".o_erplibre_studio_save_group").click();
        expect(lastCall("save_group").args[1]).toEqual({
            name: "J4 reader",
            app_id: 1,
            comment: "",
            implied_line_ids: [],
            implied_group_ids: [1],
        });

        // A second app, with its icon.
        await contains(".o_erplibre_studio_new_app").click();
        expect(".o_erplibre_studio_save_app").not.toBeEnabled();
        await contains(".o_erplibre_studio_app_form_name").edit("J4 stock");
        await contains(`.o_erplibre_studio_icon[data-value='${BASE_ICON}']`).click();
        respond.save_app = () => payload({revision: 3});
        await contains(".o_erplibre_studio_save_app").click();
        expect(lastCall("save_app").args[1]).toEqual({name: "J4 stock", icon: BASE_ICON, menu_sequence: 50});

        // An app that a model uses stays: the refusal shows in the panel.
        respond.remove_app = () => {
            throw makeServerError({message: "The app J4 shop holds the model J4 order: move it first."});
        };
        await contains(".o_erplibre_studio_remove_app").click();
        expect(lastCall("remove_app").args.slice(0, 2)).toEqual([3, 1]);
        expect(".o_erplibre_studio_apps_error").toHaveText(/move it first/);
    });

    test("a rule: « Global » or groups, project groups, a group that left the database", async () => {
        const rule = {
            id: 5,
            name: "J4 own orders",
            model: ORDER,
            domain: "[]",
            groups: [],
            group_lines: [],
            global_rule: false,
            missing_groups: ["studio_j4.group_gone"],
            ...ALL_PERMS,
        };
        answer = payload({rules: [rule]});
        await openEditor();
        await contains(".o_erplibre_studio_rules_toggle").click();
        expect(".o_erplibre_studio_rule[data-id='5'] .o_erplibre_studio_missing_group").toHaveText(
            "This group no longer exists: studio_j4.group_gone"
        );
        expect(".o_erplibre_studio_rule[data-id='5'] .o_erplibre_studio_rule_no_group").toHaveCount(1);
        await contains(".o_erplibre_studio_edit_rule").click();
        expect(".o_erplibre_studio_rule_missing_group").toHaveAttribute("role", "alert");
        expect(".o_erplibre_studio_rule_global_check").not.toBeChecked();
        // A group of the project, after the existing ones.
        expect(".o_erplibre_studio_rule_add_group option:last").toHaveValue("line:3");
        await contains(".o_erplibre_studio_rule_add_group").select("line:3");
        await contains(".o_erplibre_studio_rule_add_group").select("1");
        expect(".o_erplibre_studio_rule_group").toHaveCount(2);
        expect(".o_erplibre_studio_rule_group[data-group='line:3']").toHaveText("J4 shop / J4 user");
        // « Global » clears and hides the groups.
        await contains(".o_erplibre_studio_rule_global_check").check();
        expect(".o_erplibre_studio_rule_add_group").toHaveCount(0);
        await contains(".o_erplibre_studio_rule_global_check").uncheck();
        expect(".o_erplibre_studio_rule_group").toHaveCount(0);
        await contains(".o_erplibre_studio_rule_add_group").select("line:3");
        const saved = {...rule, group_lines: [[3, "J4 shop / J4 user"]], missing_groups: []};
        respond.save_rule = () => ({...payload({revision: 1, rules: [saved]}), saved_rule: 5});
        await contains(".o_erplibre_studio_save_rule").click();
        expect(lastCall("save_rule").args[1]).toEqual({
            id: 5,
            name: "J4 own orders",
            model: ORDER,
            domain: "[]",
            group_ids: [],
            group_line_ids: [3],
            global_rule: false,
            ...ALL_PERMS,
        });
        // Saved again, the rule is no longer flagged.
        expect(".o_erplibre_studio_missing_group").toHaveCount(0);
        expect(".o_erplibre_studio_rule_group_line").toHaveText("J4 shop / J4 user");

        await contains(".o_erplibre_studio_edit_rule").click();
        await contains(".o_erplibre_studio_rule_global_check").check();
        respond.save_rule = () => ({
            ...payload({revision: 2, rules: [{...saved, group_lines: [], global_rule: true}]}),
            saved_rule: 5,
        });
        await contains(".o_erplibre_studio_save_rule").click();
        expect(lastCall("save_rule").args[1].global_rule).toBe(true);
        expect(lastCall("save_rule").args[1].group_line_ids).toEqual([]);
        expect(".o_erplibre_studio_rule_global").toHaveCount(1);
    });

    test("the access grid offers the groups of the project", async () => {
        answer = payload({access: [{id: 1, model: ORDER, group: [1, "Role / User"], ...ALL_PERMS}]});
        onRpc("erplibre.studio.editor", "get_access_existing", () => []);
        await openEditor();
        await contains(".o_erplibre_studio_access_toggle").click();
        await contains(".o_erplibre_studio_access_add_model").select(ORDER);
        await contains(".o_erplibre_studio_access_add_group").select("line:3");
        respond.set_access = (args) =>
            payload({
                revision: 1,
                access: [
                    {id: 1, model: ORDER, group: [1, "Role / User"], ...ALL_PERMS},
                    {id: 2, model: ORDER, group: false, group_line: [3, "J4 shop / J4 user"], ...ALL_PERMS},
                ],
            });
        await contains(".o_erplibre_studio_access_add_button").click();
        expect(lastCall("set_access").args[1]).toEqual([
            {model: ORDER, group_id: 1, ...ALL_PERMS},
            {
                model: ORDER,
                group_line_id: 3,
                perm_read: true,
                perm_write: false,
                perm_create: false,
                perm_unlink: false,
            },
        ]);
        expect(".o_erplibre_studio_access_row[data-group='line:3'] .o_erplibre_studio_project_badge").toHaveCount(1);
        // Toggling a right keeps the group of the project.
        await contains(
            ".o_erplibre_studio_access_row[data-group='line:3'] .o_erplibre_studio_access_perm[data-perm=perm_unlink]"
        ).click();
        expect(lastCall("set_access").args[1][1]).toEqual({
            model: ORDER,
            group_line_id: 3,
            ...ALL_PERMS,
            perm_unlink: false,
        });
    });

    test("Revert shows what it removes and sends the digest; a refusal hides the button", async () => {
        answer = payload({state: "applied", applied: true});
        respond.get_revert_report = () => ({report: REPORT, digest: "d1g3st", refused: false});
        respond.project_action = (args) => {
            expect.step(`project_action ${args.args[1]} ${args.kwargs.digest}`);
            return payload({state: "draft", applied: false, revision: 1});
        };
        await openEditor();
        expect(".o_erplibre_studio_revert").toBeEnabled();
        await contains(".o_erplibre_studio_revert").click();
        expect(lastCall("get_revert_report").args).toEqual([3]);
        expect(".o_erplibre_studio_confirm_dialog").toHaveCount(1);
        expect(".o_erplibre_studio_confirm_section").toHaveCount(8);
        expect(".o_erplibre_studio_confirm_section[data-section=models] .o_erplibre_studio_confirm_item").toHaveText(
            "J4 order (x_j4_order): 2 record(s)"
        );
        expect(".o_erplibre_studio_confirm_section[data-section=models] .o_erplibre_studio_confirm_item").toHaveClass(
            "text-danger"
        );
        expect(".o_erplibre_studio_confirm_changes").toHaveText(
            "1 change(s) of the default views go with these views."
        );
        await contains(".o_erplibre_studio_confirm_cancel").click();
        expect(".o_erplibre_studio_confirm_dialog").toHaveCount(0);
        expect.verifySteps([]);
        await contains(".o_erplibre_studio_revert").click();
        await contains(".o_erplibre_studio_confirm_button").click();
        expect.verifySteps(["project_action action_revert d1g3st"]);
        expect(".o_erplibre_studio_confirm_dialog").toHaveCount(0);
        expect(".o_erplibre_studio_revert").not.toBeEnabled();

        // The generated module owns the models: Revert is refused.
        answer = payload({state: "applied", applied: true, revision: 2});
        await getService("action").doAction(customizeAction({resModel: ORDER, viewType: "form", viewId: false}));
        await animationFrame();
        respond.get_revert_report = () => ({
            report: REPORT,
            digest: "d1g3st",
            refused: "Uninstall the module studio_j4 first: it owns its models.",
        });
        await contains(".o_erplibre_studio_revert").click();
        expect(".o_erplibre_studio_confirm_refused").toHaveText(/Uninstall the module studio_j4 first/);
        expect(".o_erplibre_studio_confirm_button").toHaveCount(0);
    });

    test("Apply that removes data asks first; a first Apply does not", async () => {
        answer = payload();
        respond.project_action = (args) => {
            expect.step(`project_action ${args.args[1]} ${args.kwargs.digest || "-"}`);
            return payload({state: "applied", applied: true, revision: 1});
        };
        await openEditor();
        await contains(".o_erplibre_studio_apply").click();
        expect.verifySteps(["project_action action_apply -"]);
        expect(lastCall("get_apply_report")).toBe(undefined);

        // An applied project whose draft removes records.
        answer = payload({applied: true, revision: 2});
        await getService("action").doAction(customizeAction({resModel: ORDER, viewType: "form", viewId: false}));
        await animationFrame();
        respond.get_apply_report = () => ({report: REPORT, digest: "4pply", confirm: true});
        await contains(".o_erplibre_studio_apply").click();
        expect(".o_erplibre_studio_confirm_dialog").toHaveCount(1);
        expect.verifySteps([]);
        await contains(".o_erplibre_studio_confirm_button").click();
        expect.verifySteps(["project_action action_apply 4pply"]);

        // Nothing with data leaves: Apply runs at once, with the digest.
        answer = payload({applied: true, revision: 3});
        await getService("action").doAction(customizeAction({resModel: ORDER, viewType: "form", viewId: false}));
        await animationFrame();
        respond.get_apply_report = () => ({report: {...REPORT, models: []}, digest: "s4fe", confirm: false});
        await contains(".o_erplibre_studio_apply").click();
        expect(".o_erplibre_studio_confirm_dialog").toHaveCount(0);
        expect.verifySteps(["project_action action_apply s4fe"]);
    });

    test("the model dialog: an app of the project, or a new one", async () => {
        const stock = {...SHOP, id: 2, name: "J4 stock", xml_name: "menu_app_j4_stock", models: [], groups: []};
        answer = payload({apps: [SHOP, stock]});
        respond.create_model = () => payload({revision: 1});
        editorRpc("create_model");
        await openEditor();
        await contains(".o_erplibre_studio_new_model").click();
        expect(".o_erplibre_studio_model_app option").toHaveCount(3);
        expect(".o_erplibre_studio_model_app").toHaveValue("1");
        await contains(".o_erplibre_studio_model_label").edit("J4 line");
        await contains(".o_erplibre_studio_model_app").select("2");
        expect(".o_erplibre_studio_app_form").toHaveCount(0);
        await contains(".o_erplibre_studio_model_save").click();
        expect(lastCall("create_model").args[1]).toEqual({
            name: "J4 line",
            model: "x_j4_line",
            chatter: false,
            menu: {mode: "app", name: "", app_id: 2},
        });
        await contains(".o_erplibre_studio_new_model").click();
        await contains(".o_erplibre_studio_model_label").edit("J4 tag");
        await contains(".o_erplibre_studio_model_app").select("new");
        expect(".o_erplibre_studio_app_name").toHaveValue("J4 tag");
        await contains(".o_erplibre_studio_model_save").click();
        expect(lastCall("create_model").args[1].menu).toEqual({
            mode: "app",
            name: "",
            new_app: {name: "J4 tag", icon: false},
        });
    });
    test("a dialog opened from the preview saves nothing, and knows the pending models", async () => {
        defineModels([PreviewPartner]);
        onRpc("j4.partner", "web_save", () => expect.step("j4.partner.web_save"));
        onRpc("j4.partner", "onchange", () => expect.step("j4.partner.onchange"));
        onRpc(`/web/dataset/call_kw/${TAG}/*`, () => expect.step(`${TAG} reached the server`));
        await mountPreview(richSimulation());
        // « Create and edit » of a many2one to a model of the database.
        await contains(".o_field_widget[name=x_partner_id] input").edit("Zed", {confirm: false});
        await runAllTimers();
        await contains(".o_field_widget[name=x_partner_id] .o_m2o_dropdown_option_create_edit").click();
        expect(".o_dialog .o_form_view").toHaveCount(1);
        await contains(".o_dialog .o_form_button_save").click();
        await animationFrame();
        expect(".o_notification").toHaveText("Preview: nothing is saved.");
        expect.verifyErrors(["Preview: j4.partner.web_save is not sent."]);
        expect.verifySteps([]);
        await contains(".o_dialog .o_form_button_cancel").click();
        // « Add a line » of a many2many to a pending model: its list, no call.
        await contains(".o_field_widget[name=x_tags] .o_field_x2many_list_row_add a").click();
        await animationFrame();
        expect(".o_dialog .o_list_view").toHaveCount(1);
        expect(".o_error_dialog").toHaveCount(0);
        expect.verifySteps([]);
    });

    test("a line of a one2many to a model of the database is added in the simulation", async () => {
        defineModels([PreviewPartner]);
        onRpc("j4.partner", "onchange", () => expect.step("j4.partner.onchange"));
        const data = richSimulation();
        data.models[ORDER].fields.x_partner_ids = info("x_partner_ids", "one2many", "Partners", {
            relation: "j4.partner",
            relation_field: "x_j4_order_id",
        });
        data.models["j4.partner"].fields.name = info("name", "char", "Name");
        data.views.form.arch =
            `<form><sheet><field name="x_name"/><field name="x_partner_ids">` +
            `<list editable="bottom"><field name="name"/></list></field></sheet></form>`;
        data.defaults.x_partner_ids = [];
        data.model_defaults[ORDER].x_partner_ids = [];
        await mountPreview(data);
        await contains(".o_field_widget[name=x_partner_ids] .o_field_x2many_list_row_add a").click();
        expect(".o_field_widget[name=x_partner_ids] .o_data_row").toHaveCount(1);
        expect(".o_notification").toHaveCount(0);
        expect.verifySteps([]);
    });

    test("the mode shown is the mode rendered; the views are tabs", async () => {
        await mountPreview({...simulation("real")});
        expect(".o_erplibre_studio_model_preview").toHaveAttribute("data-mode", "real");
        expect(".o_erplibre_studio_model_preview").toHaveAttribute("data-requested-mode", "simulation");
        expect(".o_erplibre_studio_preview_mode").toHaveText("Real (rolled back)");
        expect(".o_erplibre_studio_preview_mismatch").toHaveAttribute("role", "alert");
        expect("[role=tablist] [role=tab]").toHaveCount(3);
        expect(".o_erplibre_studio_preview_type[data-view-type=form]").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_preview_type[data-view-type=list]").toHaveAttribute("aria-selected", "false");
        expect("[role=tabpanel]").toHaveCount(1);
        expect(".o_erplibre_studio_preview_real").toHaveAttribute("aria-describedby", "o_erplibre_studio_real_hint");
        expect("#o_erplibre_studio_real_hint").toHaveText("Real: approve the draft first.");
    });

    test("the preview follows the draft: Undo shows it again, Apply closes it", async () => {
        answer = payload({change_count: 1});
        answer.changes = [{id: 1, type: "add_field", summary: "Add the field Lines"}];
        respond.get_model_preview = () => {
            expect.step("get_model_preview");
            return simulation();
        };
        await openEditor();
        await contains(".o_erplibre_studio_preview_toggle").click();
        expect.verifySteps(["get_model_preview"]);
        respond.project_action = (args) => {
            expect.step(`project_action ${args.args[1]}`);
            return payload({revision: 1, change_count: 0});
        };
        await contains(".o_erplibre_studio_undo").click();
        expect.verifySteps(["project_action action_undo", "get_model_preview"]);
        expect(".o_erplibre_studio_model_preview").toHaveCount(1);
        respond.project_action = (args) => {
            expect.step(`project_action ${args.args[1]}`);
            return {
                ...payload({state: "applied", applied: true, revision: 2, models: [orderLine({applied: true, views: {form: 99}})]}),
                view: {id: 99, name: `${ORDER}.form`, xml_id: "studio_j4.view_x_j4_order_form", pending: false},
            };
        };
        await contains(".o_erplibre_studio_apply").click();
        expect.verifySteps(["project_action action_apply"]);
        expect(".o_erplibre_studio_model_preview").toHaveCount(0);
        expect(".o_notification").toHaveText(`The model ${ORDER} exists now: its preview is closed.`);
    });

    test("a confirmation refused for a changed report shows the new one and sends its digest", async () => {
        answer = payload({state: "applied", applied: true});
        let reports = 0;
        respond.get_revert_report = () => {
            reports++;
            const report = reports === 1 ? REPORT : {...REPORT, models: [{model: ORDER, name: "J4 order", count: 3}]};
            return {report, digest: `d${reports}`, refused: false};
        };
        respond.project_action = (args) => {
            expect.step(`project_action ${args.kwargs.digest}`);
            if (args.kwargs.digest === "d1") {
                throw makeServerError({message: "What Revert removes changed since it was shown: review it again."});
            }
            return payload({revision: 1});
        };
        await openEditor();
        await contains(".o_erplibre_studio_revert").click();
        expect(".o_erplibre_studio_confirm_stale").toHaveCount(0);
        await contains(".o_erplibre_studio_confirm_button").click();
        expect.verifySteps(["project_action d1"]);
        expect(".o_erplibre_studio_confirm_dialog").toHaveCount(1);
        expect(".o_erplibre_studio_confirm_stale").toHaveAttribute("role", "alert");
        expect(".o_erplibre_studio_confirm_section[data-section=models] .o_erplibre_studio_confirm_item").toHaveText(
            "J4 order (x_j4_order): 3 record(s)"
        );
        await contains(".o_erplibre_studio_confirm_button").click();
        expect.verifySteps(["project_action d2"]);
        expect(".o_erplibre_studio_confirm_dialog").toHaveCount(0);
    });
});
