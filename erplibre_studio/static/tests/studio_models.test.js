// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, Deferred, describe, expect, test} from "@odoo/hoot";
import {advanceTime, animationFrame} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    makeServerError,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    serverState,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {accessGrid, accessRows, filterMenus, modelNameFromLabel, slug} from "@erplibre_studio/editor/studio_models";
import {NAME_CHECK_DELAY} from "@erplibre_studio/editor/studio_field_name";

const MODEL = "x_loan_item";
const BASE_ICON = "base,static/description/icon.png";
const STUDIO_ICON = "erplibre_studio,static/description/icon.png";
const ALL_PERMS = {perm_read: true, perm_write: true, perm_create: true, perm_unlink: true};

const CHOICES = {
    mail_available: true,
    icons: [
        {value: STUDIO_ICON, label: "ERPLibre studio", url: "/erplibre_studio/static/description/icon.png"},
        {value: BASE_ICON, label: "Base", url: "/base/static/description/icon.png"},
    ],
    menus: [
        {id: 20, name: "Sales", xml_id: "sale.sale_menu_root"},
        {id: 21, name: "Settings/Technical", xml_id: "base.menu_custom"},
    ],
    groups: [
        {id: 1, name: "Role / User", xml_id: "base.group_user"},
        {id: 4, name: "Administration / Settings", xml_id: "base.group_system"},
    ],
    // The models of the database, then those of the project.
    models: [
        ["res.partner", "Contact"],
        ["res.partner.category", "Contact Tag"],
        [MODEL, "Loan item"],
    ],
    // The names a new model cannot take: a model of another project too.
    taken_models: ["res.partner", "res.partner.category", "x_loan"],
};

function container(path, tag, children, extra = {}) {
    return {path, tag, kind: "container", label: tag, attrs: {}, movable: false, drop: true, children, ...extra};
}

/** The blocks of the default form of the new model, as the server gives them. */
function formBlocks(chatter) {
    const name = {path: "//field[@name='x_name']", tag: "field", kind: "field", name: "x_name", label: "Name"};
    const children = [
        container(
            "/form/sheet",
            "sheet",
            [
                container("/form/sheet/div", "div", [{...name, attrs: {}, movable: true}]),
                container("//group[@name='studio_main']", "group", [
                    container("//group[@name='studio_left']", "group", []),
                    container("//group[@name='studio_right']", "group", []),
                ]),
            ],
            {drop: true}
        ),
    ];
    if (chatter) {
        children.push({
            path: "/form/chatter",
            tag: "chatter",
            kind: "other",
            label: "chatter",
            attrs: {},
            movable: false,
        });
    }
    return container("/form", "form", children, {drop: false});
}

function contactBlocks() {
    return container("/form", "form", [
        container("/form/sheet", "sheet", [
            {
                path: "//field[@name='name']",
                tag: "field",
                kind: "field",
                name: "name",
                label: "Name",
                attrs: {},
                movable: true,
            },
        ]),
    ]);
}

// The app of the project its models go in.
const LOANS_APP = {id: 1, name: "Loans", icon: false, xml_name: "menu_app", menu_sequence: 50, models: [7], groups: []};

function modelLine(extra = {}) {
    return {
        id: 7,
        model: MODEL,
        name: "Loan item",
        chatter: true,
        menu_mode: "app",
        app_id: 1,
        menu_parent: false,
        menu_name: "",
        applied: false,
        views: {},
        ...extra,
    };
}

const APPLIED_VIEWS = {form: 51, list: 52, search: 53};
// The menus Apply made for the app of the project and its model.
const APPLIED_MENUS = [
    [90, "Loans", STUDIO_ICON, false],
    [91, "Loan item", false, 90],
];

/** The editor payload of the form of ``model``; ``project`` completes the project. */
function payload(project = {}, {model = "res.partner", chatter = true, viewId = 12, viewType = "form"} = {}) {
    const own = model === MODEL;
    return {
        model,
        model_name: own ? "Loan item" : "Contact",
        view_type: viewType,
        view_types: ["form", "list", "kanban", "search", "pivot"],
        view: {id: viewId, name: `${model}.${viewType}`, xml_id: own ? `studio_loans.view_${MODEL}_form` : false},
        blocks: own ? formBlocks(chatter) : contactBlocks(),
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "hide"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        fields: own ? {x_name: {string: "Name", type: "char"}} : {name: {string: "Name", type: "char"}},
        palette: [],
        field_types: ["char"],
        changes: [],
        errors: [],
        project: {
            id: 3,
            name: "Loans",
            module_name: "studio_loans",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 0,
            item_count: 0,
            applied: false,
            app: false,
            apps: [],
            groups: [],
            models: [],
            access: [],
            rules: [],
            ...project,
        },
        projects: [{id: 3, name: "Loans", module_name: "studio_loans", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        mail_available: true,
    };
}

// The rules of the technical names of new models (``model_name_rule``).
const PRODUCTION_RULE = {
    prefix_required: true,
    mode: "production",
    label: "Production · x_ required",
    text: "Prefix x_ required on this database",
    detail: "Models created outside the code carry x_ on a production database.",
};
const DEVELOPMENT_RULE = {
    prefix_required: false,
    mode: "development",
    label: "Development · code_generator",
    text: "Without x_ allowed: development database (code_generator)",
    detail: "A model without x_ is written as is in the generated module.",
};
const MODEL_CHECKS = {
    format: "Lower case letters, digits, _ and dots",
    reserved: "Not a reserved name",
    prefix: "Prefix that fits the rule of the database",
    unique: "Unique among the models, the tables and the projects",
};

/** The answer of ``check_model_name`` for ``name``: available, or « taken » (the check « unique » fails). */
function modelCheck(name, status = "available") {
    const taken = status === "taken";
    return {
        name,
        proposed: false,
        status,
        message: taken ? `The model ${name} already exists.` : "Available",
        detail: taken ? "Choose another name." : `No model, table nor project uses ${name}.`,
        checks: Object.entries(MODEL_CHECKS).map(([key, text]) => ({key, ok: !(taken && key === "unique"), text})),
        rule: DEVELOPMENT_RULE,
    };
}

/** ``payload`` with the rule of the technical names of new models ``rule``. */
function rulePayload(rule, project = {}, options = {}) {
    return {...payload(project, options), model_name_rule: rule};
}

// The payload the editor shows, the choices of the dialogs, and how each
// call answers: ``respond[method](args)``.
let answer;
let choices;
let respond;
let calls;
// The calls of ``check_model_name``: [{name, kwargs}], apart from ``calls``.
let modelChecks;

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

beforeEach(() => {
    serverState.debug = "1";
    defineWebModels();
    calls = [];
    modelChecks = [];
    choices = JSON.parse(JSON.stringify(CHOICES));
    respond = {};
    onRpc("erplibre.studio.editor", "check_model_name", (args) => {
        const {line_id, label} = args.kwargs;
        modelChecks.push({name: args.args[1], kwargs: {line_id, label}});
        return respond.check_model_name ? respond.check_model_name(args) : modelCheck(args.args[1]);
    });
    onRpc("erplibre.studio.editor", "get_editor_data", (args) => {
        expect.step(`get_editor_data ${args.args.slice(0, 4).join(" ")}`);
        return respond.get_editor_data ? respond.get_editor_data(args) : answer;
    });
    onRpc("erplibre.studio.editor", "get_studio_choices", (args) => {
        expect.step(`get_studio_choices ${args.args[0]}`);
        return choices;
    });
    onRpc("erplibre.studio.editor", "get_review", () => ({
        revision: 0,
        state: "draft",
        groups: [],
        removal: {report: {}, digest: "n0thing", confirm: false},
        blocked: false,
    }));
    onRpc("erplibre.studio.editor", "get_access_existing", (args) => {
        expect.step(`get_access_existing ${args.args[1]}`);
        return respond.get_access_existing ? respond.get_access_existing(args) : [];
    });
    for (const method of [
        "create_model",
        "update_model",
        "update_app",
        "remove_model",
        "project_action",
        "set_access",
        "save_rule",
        "remove_rule",
        "check_rule_domain",
    ]) {
        editorRpc(method);
    }
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    patchWithCleanup(getService("menu"), {
        async reload() {
            expect.step("menu reload");
        },
    });
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 12}));
    await animationFrame();
    expect.verifySteps(["get_editor_data res.partner 12 form false"]);
}

/** The accessible name of ``el``: aria-label, aria-labelledby, label[for] or a wrapping label. */
function accessibleName(el) {
    if (el.getAttribute("aria-label")) {
        return el.getAttribute("aria-label");
    }
    if (el.getAttribute("aria-labelledby")) {
        return document.getElementById(el.getAttribute("aria-labelledby")).textContent.trim();
    }
    const label = (el.id && document.querySelector(`label[for='${el.id}']`)) || el.closest("label");
    return label ? label.textContent.trim() : "";
}

/** Show the space ``space`` of the rail (view, models, security, review). */
async function openSpace(space) {
    await contains(`.o_erplibre_studio_rail_item[data-space=${space}]`).click();
}

/** Apply of the top bar opens the review; Apply there applies the draft. */
async function applyThroughReview() {
    await contains(".o_erplibre_studio_apply_bar").click();
    await contains(".o_erplibre_studio_apply").click();
}

/** Open the menu of Apply in the top bar, then click its item ``selector``. */
async function applyMenu(selector) {
    await contains(".o_erplibre_studio_apply_menu").click();
    await contains(selector).click();
}

const lastCall = (method) => calls.filter((c) => c.method === method).pop();

describe.current.tags("desktop");
describe("erplibre_studio models", () => {
    test("the technical name follows the label until edited", () => {
        expect(slug("Équipement de prêt")).toBe("equipement_de_pret");
        expect(modelNameFromLabel("Équipement de prêt")).toBe("x_equipement_de_pret");
        expect(modelNameFromLabel("2026 loans")).toBe("x_model_2026_loans");
        expect(modelNameFromLabel("")).toBe("x_model");
        expect(modelNameFromLabel("Loan", ["x_loan", "x_loan_2"])).toBe("x_loan_3");
        expect(modelNameFromLabel("a".repeat(80)).length).toBe(46);
        expect(filterMenus(CHOICES.menus, "TECH").map((m) => m.id)).toEqual([21]);
        const project = {
            models: [modelLine()],
            access: [
                {id: 2, model: "res.partner", group: [1, "Role / User"], ...ALL_PERMS},
                {id: 1, model: MODEL, group: [1, "Role / User"], ...ALL_PERMS, perm_unlink: false},
            ],
        };
        expect(accessGrid(project).map((entry) => entry.model)).toEqual([MODEL, "res.partner"]);
        expect(accessRows(project.access)[1]).toEqual({
            model: MODEL,
            group_id: 1,
            perm_read: true,
            perm_write: true,
            perm_create: true,
            perm_unlink: false,
        });
    });

    test("the dialog of a new model creates it in a new app", async () => {
        answer = payload();
        await openEditor();
        await openSpace("models");
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_dialog").toHaveCount(1);
        expect(".o_erplibre_studio_model_save").not.toBeEnabled();
        // Without an app in the project, the model goes in a new app.
        expect("#o_erplibre_studio_menu_app").not.toBeEnabled();
        expect("#o_erplibre_studio_menu_new_app").toBeChecked();
        expect(".o_erplibre_studio_menu_preview").toHaveText("New app › New model");
        expect(".o_erplibre_studio_model_name_pill").toHaveAttribute("data-edited", "0");

        await contains(".o_erplibre_studio_model_label").edit("Équipement de prêt");
        expect(".o_erplibre_studio_model_name").toHaveValue("x_equipement_de_pret");
        expect(".o_erplibre_studio_app_name").toHaveValue("Équipement de prêt");
        await contains(".o_erplibre_studio_model_name").edit("x_loan_item");
        expect(".o_erplibre_studio_model_name_pill").toHaveAttribute("data-edited", "1");
        // « Follow the label » makes the name from the label again.
        await contains(".o_erplibre_studio_model_follow").click();
        expect(".o_erplibre_studio_model_name").toHaveValue("x_equipement_de_pret");
        expect(".o_erplibre_studio_model_name_pill").toHaveAttribute("data-edited", "0");
        expect(".o_erplibre_studio_model_follow").toHaveCount(0);
        await contains(".o_erplibre_studio_model_name").edit("x_loan_item");
        await contains(".o_erplibre_studio_model_label").edit("Loan item");
        expect(".o_erplibre_studio_model_name").toHaveValue("x_loan_item");
        expect(".o_erplibre_studio_app_name").toHaveValue("Loan item");
        expect(".o_erplibre_studio_menu_preview").toHaveText("Loan item › Loan item");

        // The chatter: mail is installed.
        expect(".o_erplibre_studio_model_chatter").toHaveCount(1);
        await contains(".o_erplibre_studio_model_chatter").check();

        // The icons of the app, the studio one by default.
        expect(".o_erplibre_studio_icon").toHaveCount(2);
        expect(`.o_erplibre_studio_icon[data-value='${STUDIO_ICON}']`).toHaveClass("o_erplibre_studio_icon_selected");
        await contains(`.o_erplibre_studio_icon[data-value='${BASE_ICON}']`).click();
        expect(`.o_erplibre_studio_icon[data-value='${BASE_ICON}']`).toHaveClass("o_erplibre_studio_icon_selected");

        // Under a menu: the model needs its parent.
        await contains("#o_erplibre_studio_menu_under").click();
        expect(".o_erplibre_studio_app_form").toHaveCount(0);
        expect(".o_erplibre_studio_menu_parent option").toHaveCount(2);
        await contains(".o_erplibre_studio_menu_filter").edit("sal");
        expect(".o_erplibre_studio_menu_parent option").toHaveCount(1);
        expect(".o_erplibre_studio_model_save").not.toBeEnabled();
        await contains(".o_erplibre_studio_menu_parent").select("20");
        expect(".o_erplibre_studio_model_save").toBeEnabled();
        expect(".o_erplibre_studio_menu_preview").toHaveText("Sales › Loan item");

        // Back to a new app.
        await contains("#o_erplibre_studio_menu_new_app").click();
        expect(".o_erplibre_studio_app_form").toHaveCount(1);
        respond.create_model = () =>
            payload({
                revision: 1,
                item_count: 2,
                apps: [{...LOANS_APP, name: "Loan item", icon: BASE_ICON}],
                models: [modelLine()],
            });
        await contains(".o_erplibre_studio_model_save").click();
        const call = lastCall("create_model");
        expect(call.args.slice(0, 1).concat(call.args.slice(2))).toEqual([3, "res.partner", 12, "form"]);
        expect(call.args[1]).toEqual({
            name: "Loan item",
            model: MODEL,
            chatter: true,
            menu: {mode: "app", name: "", new_app: {name: "Loan item", icon: BASE_ICON}},
        });
        expect(call.kwargs.revision).toBe(0);
        expect(".o_erplibre_studio_model_dialog").toHaveCount(0);

        // The model waits for Apply; Apply is enabled on the items of the project.
        expect(`.o_erplibre_studio_model[data-model=${MODEL}] .o_erplibre_studio_model_state`).toHaveAttribute(
            "data-applied",
            "0"
        );
        expect(".o_erplibre_studio_apply_open").toHaveCount(1);
        // Its default views are edited before Apply creates them.
        expect(".o_erplibre_studio_open_model.o_erplibre_studio_open_pending").toHaveCount(3);
        expect(".o_erplibre_studio_model_menu_place").toHaveText("Loan item › Loan item");
        expect(".o_erplibre_studio_apply_bar").toBeEnabled();
    });

    test("without mail, no chatter; the app of the project; under a menu", async () => {
        answer = payload({apps: [LOANS_APP], models: [modelLine({chatter: false})], item_count: 2});
        choices.mail_available = false;
        await openEditor();
        await openSpace("models");
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_chatter").toHaveCount(0);
        expect("label[for=o_erplibre_studio_menu_app]").toHaveText("In an app of the project");
        // The app of the project by default; a new app is another place.
        expect("#o_erplibre_studio_menu_app").toBeChecked();
        expect(".o_erplibre_studio_model_app").toHaveValue("1");
        expect(".o_erplibre_studio_model_app option").toHaveCount(1);
        expect(".o_erplibre_studio_app_form").toHaveCount(0);
        await contains(".o_erplibre_studio_model_label").edit("Loan tag");
        expect(".o_erplibre_studio_menu_preview").toHaveText("Loans › Loan tag");
        await contains("#o_erplibre_studio_menu_under").click();
        expect(".o_erplibre_studio_menu_preview").toHaveText("Choose a parent menu › Loan tag");
        await contains(".o_erplibre_studio_menu_parent").select("21");
        await contains(".o_erplibre_studio_menu_name").edit("Tags");
        expect(".o_erplibre_studio_menu_preview").toHaveText("Settings › Technical › Tags");
        respond.create_model = () => payload({...answer.project, revision: 1});
        await contains(".o_erplibre_studio_model_save").click();
        expect(lastCall("create_model").args[1]).toEqual({
            name: "Loan tag",
            model: "x_loan_tag",
            chatter: false,
            menu: {mode: "menu", name: "Tags", parent_id: 21},
        });
    });

    test("Apply and open edits the form of the model; its chatter has no hook", async () => {
        answer = payload({models: [modelLine()], item_count: 2});
        await openEditor();
        const applied = modelLine({applied: true, views: APPLIED_VIEWS});
        respond.project_action = () =>
            payload({state: "applied", revision: 1, models: [applied], item_count: 2, menus: APPLIED_MENUS});
        respond.get_editor_data = (args) =>
            payload(answer.project, {model: args.args[0], viewId: args.args[1], viewType: args.args[2]});
        await openSpace("models");
        // Apply and open goes through the review: nothing is written yet.
        await contains(".o_erplibre_studio_apply_open").click();
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "review");
        expect(lastCall("project_action")).toBe(undefined);
        await contains(".o_erplibre_studio_apply").click();
        expect(lastCall("project_action").args[1]).toBe("action_apply");
        // The view the editor was opened on, where it goes back when the model leaves.
        expect(lastCall("project_action").kwargs.fallback).toEqual(["res.partner", 12, "form"]);
        // The new app and its menu reach the web client.
        expect.verifySteps(["menu reload", `get_editor_data ${MODEL} 51 form 3`]);
        expect(".o_erplibre_studio_title").toHaveText(/Loan item\s*Form\s*studio_loans\.view_x_loan_item_form/);
        // The chatter stays where the view puts it.
        expect(".o_erplibre_studio_other[data-tag=chatter]").toHaveAttribute("draggable", "false");
        expect(`.o_erplibre_studio_hook[data-target='/form/chatter']`).toHaveCount(0);
        expect(`.o_erplibre_studio_other[data-tag=chatter] .o_erplibre_studio_hook`).toHaveCount(0);
        expect(`.o_erplibre_studio_hook[data-target="//group[@name='studio_left']"]`).toHaveCount(1);

        await openSpace("models");
        expect(`.o_erplibre_studio_model[data-model=${MODEL}]`).toHaveClass("o_erplibre_studio_model_current");
        expect(".o_erplibre_studio_model_state").toHaveAttribute("data-applied", "1");
        await contains(".o_erplibre_studio_open_model[data-view-type=list]").click();
        expect.verifySteps([`get_editor_data ${MODEL} 52 list 3`]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "view");
    });

    test("a model of the project is edited and removed", async () => {
        answer = payload({apps: [LOANS_APP], models: [modelLine()], item_count: 2});
        await openEditor();
        await openSpace("models");
        await contains(".o_erplibre_studio_edit_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_name").toHaveValue(MODEL);
        await contains(".o_erplibre_studio_model_label").edit("Loaned item");
        expect(".o_erplibre_studio_model_name").toHaveValue(MODEL);
        expect(".o_erplibre_studio_model_app").toHaveValue("1");
        respond.update_model = () => payload({...answer.project, revision: 2});
        await contains(".o_erplibre_studio_model_save").click();
        expect(calls.map((c) => c.method)).toEqual(["update_model"]);
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([
            7,
            {name: "Loaned item", model: MODEL, chatter: true, menu: {mode: "app", name: "", app_id: 1}},
        ]);
        expect(lastCall("update_model").kwargs.revision).toBe(0);

        respond.remove_model = () => payload({revision: 3});
        await contains(".o_erplibre_studio_remove_model").click();
        await contains(".modal-footer .btn-primary").click();
        expect(lastCall("remove_model").args.slice(0, 2)).toEqual([3, 7]);
        expect(".o_erplibre_studio_no_model").toHaveCount(1);
    });

    test("the models space: the list, the page of a model, its inspector", async () => {
        const partner = {
            model: "res.partner",
            name: "Contact",
            new: false,
            pending: false,
            module: "base",
            chatter: true,
            views: [
                {type: "form", label: "Form", view_id: 12},
                {type: "list", label: "List", view_id: 13},
            ],
            fields: [{name: "x_sponsor_id", label: "Sponsor", ttype: "many2one", relation: "res.users", applied: false}],
            changes: 2,
            access: 0,
            rules: 0,
        };
        const item = (model) => ({
            model,
            name: "Loan item",
            new: true,
            pending: true,
            module: false,
            chatter: true,
            views: [],
            fields: [{name: "x_partner_id", label: "Partner", ttype: "many2one", relation: "res.partner", applied: true}],
            changes: 1,
            access: 1,
            rules: 1,
        });
        const project = (model = MODEL, line = {}) => ({
            apps: [LOANS_APP],
            models: [modelLine({model, pending_views: {form: true, list: false, search: false}, ...line})],
            access: [{id: 1, model, group: [1, "Role / User"], ...ALL_PERMS, perm_unlink: false}],
            rules: [{id: 5, name: "Own items", model, domain: "[]", groups: [[1, "Role / User"]], ...ALL_PERMS}],
            item_count: 4,
            touched_models: [partner, item(model)],
        });
        answer = payload(project());
        respond.get_editor_data = (args) =>
            payload(answer.project, {model: args.args[0], viewId: args.args[1], viewType: args.args[2]});
        await openEditor();
        await openSpace("models");
        // The models of the project first, then those it touches.
        expect(".o_erplibre_studio_no_model").toHaveCount(0);
        expect(
            [...document.querySelectorAll(".o_erplibre_studio_models_item")].map((el) => el.dataset.kind)
        ).toEqual(["pending", "existing"]);
        expect(".o_erplibre_studio_models_item[data-model='res.partner']").toHaveText(
            /Contact\s*Changed\s*res\.partner\s*Model of the module base/
        );
        // The page opens on the model on screen: a model of the database.
        expect(".o_erplibre_studio_model[data-model='res.partner']").toHaveClass("o_erplibre_studio_model_current");
        expect(".o_erplibre_studio_models_item[data-model='res.partner']").toHaveAttribute("aria-current", "true");
        expect(".o_erplibre_studio_model_detail_label").toHaveAttribute("readonly");
        expect(".o_erplibre_studio_model_detail_name").toHaveValue("res.partner");
        expect(".o_erplibre_studio_model_locked").toHaveCount(1);
        expect(".o_erplibre_studio_model_menu_place").toHaveCount(0);
        expect(".o_erplibre_studio_model_chatter_switch").toBeChecked();
        expect(".o_erplibre_studio_model_chatter_switch").not.toBeEnabled();
        expect(".o_erplibre_studio_model_field").toHaveCount(1);
        expect(".o_erplibre_studio_model_field[data-name=x_sponsor_id]").toHaveText(
            /Sponsor\s*x_sponsor_id\s*Many2one → res\.users\s*New/
        );
        expect(".o_erplibre_studio_model_access_row").toHaveCount(0);
        expect(".o_erplibre_studio_model_rules").toHaveText("No rule: the rights hold for every record.");
        expect(".o_erplibre_studio_remove_model").toHaveCount(0);
        expect(".o_erplibre_studio_model_counts [data-count=changes]").toHaveText("2");
        // Its views open in the view space.
        expect(".o_erplibre_studio_open_model").toHaveCount(2);
        await contains(".o_erplibre_studio_open_model[data-view-type=list]").click();
        expect.verifySteps(["get_editor_data res.partner 13 list 3"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "view");

        // A model of the project, not created yet.
        await openSpace("models");
        await contains(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).click();
        expect(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).toHaveAttribute("aria-current", "true");
        expect(`.o_erplibre_studio_model[data-model=${MODEL}]`).toHaveAttribute("data-kind", "pending");
        expect(".o_erplibre_studio_model_state").toHaveAttribute("data-applied", "0");
        expect(".o_erplibre_studio_model_menu_place").toHaveText("Loans › Loan item");
        expect(".o_erplibre_studio_model_detail_name").toHaveValue("loan_item");
        expect(".o_erplibre_studio_model_detail_name").not.toHaveAttribute("readonly");
        expect(".o_erplibre_studio_model_locked").toHaveCount(0);
        expect(".o_erplibre_studio_open_pending").toHaveCount(3);
        expect(".o_erplibre_studio_pending_changes").toHaveCount(1);
        // Its name field, then the fields of the project on it.
        expect(
            [...document.querySelectorAll(".o_erplibre_studio_model_field")].map((el) => el.dataset.name)
        ).toEqual(["x_name", "x_partner_id"]);
        expect(".o_erplibre_studio_model_field[data-name=x_partner_id]").toHaveText(
            /Partner\s*x_partner_id\s*Many2one → Contact\s*Created/
        );
        expect(".o_erplibre_studio_model_access_row").toHaveText(/Role \/ User\s*Read · Write · Create/);
        expect(".o_erplibre_studio_model_rules").toHaveText("1 rule(s): « Own items »");
        expect(".o_erplibre_studio_model_kind_text").toHaveText("Model of the project · waiting for Apply");
        // The advanced section folds.
        expect(".o_erplibre_studio_model_advanced").toHaveCount(0);
        await contains(".o_erplibre_studio_model_advanced_toggle").click();
        expect(".o_erplibre_studio_model_advanced_toggle").toHaveAttribute("aria-expanded", "true");
        expect(".o_erplibre_studio_model_advanced").toHaveText(/Table\s*x_loan_item\s*Displayed name\s*x_name/);
        expect(".o_erplibre_studio_remove_model").toHaveText("Remove from the draft");

        // The chatter, the label and the technical name: one update_model each.
        expect(".o_erplibre_studio_model_chatter_switch").toBeEnabled();
        respond.update_model = () => payload({...project(MODEL, {chatter: false}), revision: 1});
        await contains(".o_erplibre_studio_model_chatter_switch").click();
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {chatter: false}]);
        expect(".o_erplibre_studio_model_chatter_switch").not.toBeChecked();
        respond.update_model = () => payload({...project(MODEL, {name: "Loaned item"}), revision: 2});
        await contains(".o_erplibre_studio_model_detail_label").edit("Loaned item");
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {name: "Loaned item"}]);
        expect(lastCall("update_model").kwargs.revision).toBe(1);
        respond.update_model = () => payload({...project("x_loan_object"), revision: 3});
        await contains(".o_erplibre_studio_model_detail_name").edit("loan_object");
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {model: "x_loan_object"}]);
        // The page follows the new name.
        expect(".o_erplibre_studio_model[data-model=x_loan_object]").toHaveCount(1);
        // A refusal shows the name of the model again.
        respond.update_model = () => {
            throw makeServerError({message: "The model x_loan is taken."});
        };
        await contains(".o_erplibre_studio_model_detail_name").edit("loan");
        expect(".o_erplibre_studio_model_detail_name").toHaveValue("loan_object");
        expect(".o_notification").toHaveText(/x_loan is taken/);

        // « Open in Security » shows the rights of the model.
        await contains(".o_erplibre_studio_model_security").click();
        expect.verifySteps(["get_studio_choices 3", "get_access_existing x_loan_object"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "security");
        expect(".o_erplibre_studio_access_toggle").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_security_model[data-model=x_loan_object]").toHaveAttribute("aria-current", "true");
    });

    test("the models space: the default order and the options of a model", async () => {
        const partner = {
            model: "res.partner",
            name: "Contact",
            new: false,
            pending: false,
            module: "base",
            chatter: true,
            views: [{type: "form", label: "Form", view_id: 12}],
            fields: [],
            changes: 0,
            access: 0,
            rules: 0,
        };
        const options = (line = {}) => ({
            order: "",
            archivable: false,
            manual_order: false,
            options_applied: {archivable: false, manual_order: false},
            sort_fields: [
                ["x_name", "Name"],
                ["id", "ID"],
            ],
            ...line,
        });
        const project = (line = {}) => ({
            apps: [LOANS_APP],
            models: [modelLine(options(line))],
            access: [],
            rules: [],
            item_count: 2,
            touched_models: [partner],
        });
        answer = payload(project());
        respond.get_editor_data = (args) =>
            payload(answer.project, {model: args.args[0], viewId: args.args[1], viewType: args.args[2]});
        await openEditor();
        await openSpace("models");
        // A model of the database: no order, no option.
        expect(".o_erplibre_studio_model[data-model='res.partner']").toHaveCount(1);
        expect(".o_erplibre_studio_model_order").toHaveCount(0);
        expect(".o_erplibre_studio_model_archivable").toHaveCount(0);

        // A model of the project, not created yet.
        await contains(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).click();
        expect(".o_erplibre_studio_model_order").toHaveValue("");
        expect(
            [...document.querySelectorAll(".o_erplibre_studio_model_order option")].map((el) => el.value)
        ).toEqual(["", "x_name asc", "x_name desc", "id asc", "id desc"]);
        expect(".o_erplibre_studio_model_order option[value='x_name desc']").toHaveText("Name, descending");
        expect(".o_erplibre_studio_model_archivable").toBeEnabled();
        expect(".o_erplibre_studio_model_archivable").not.toBeChecked();
        expect(".o_erplibre_studio_model_manual_order").toBeEnabled();
        expect(".o_erplibre_studio_model_options").toHaveText(/Archivable\s*x_active\s*Manual order\s*x_sequence/);

        respond.update_model = () => payload({...project({order: "x_name desc"}), revision: 1});
        await contains(".o_erplibre_studio_model_order").select("x_name desc");
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {order: "x_name desc"}]);
        expect(".o_erplibre_studio_model_order").toHaveValue("x_name desc");

        respond.update_model = () =>
            payload({...project({order: "x_name desc", archivable: true}), revision: 2});
        await contains(".o_erplibre_studio_model_archivable").click();
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {archivable: true}]);
        expect(".o_erplibre_studio_model_archivable").toBeChecked();

        // The manual order joins the choices with its option; an order set
        // otherwise stays shown.
        respond.update_model = () =>
            payload({
                ...project({order: "x_name desc, id asc", archivable: true, manual_order: true}),
                revision: 3,
            });
        await contains(".o_erplibre_studio_model_manual_order").click();
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {manual_order: true}]);
        expect(".o_erplibre_studio_model_order option[value='x_sequence asc, id asc']").toHaveText(
            "Manual order (Sequence)"
        );
        expect(".o_erplibre_studio_model_order").toHaveValue("x_name desc, id asc");

        // A refusal shows the order of the line again.
        respond.update_model = () => {
            throw makeServerError({message: "The records cannot be sorted by id."});
        };
        await contains(".o_erplibre_studio_model_order").select("id desc");
        expect(".o_erplibre_studio_model_order").toHaveValue("x_name desc, id asc");
    });

    test("the models space: an applied option is locked", async () => {
        answer = payload({
            apps: [LOANS_APP],
            models: [
                modelLine({
                    applied: true,
                    views: APPLIED_VIEWS,
                    order: "",
                    archivable: true,
                    manual_order: false,
                    options_applied: {archivable: true, manual_order: false},
                    sort_fields: [["x_name", "Name"]],
                }),
            ],
            item_count: 1,
            touched_models: [],
        });
        respond.get_editor_data = (args) =>
            payload(answer.project, {model: args.args[0], viewId: args.args[1], viewType: args.args[2]});
        await openEditor();
        await openSpace("models");
        await contains(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).click();
        expect(".o_erplibre_studio_model_archivable").toBeChecked();
        expect(".o_erplibre_studio_model_archivable").not.toBeEnabled();
        expect(".o_erplibre_studio_model_archivable").toHaveAttribute(
            "title",
            "Once applied, this option cannot be removed."
        );
        expect(".o_erplibre_studio_model_option_locked").toHaveCount(1);
        expect(".o_erplibre_studio_model_manual_order").toBeEnabled();
        await contains(".o_erplibre_studio_model_advanced_toggle").click();
        expect(".o_erplibre_studio_model_advanced_note").toHaveText(
            "Set by Odoo for a model created outside code: they do not change."
        );
    });

    test("the models space: per company and its rule", async () => {
        const companyRule = {
            id: 9,
            name: "Loan item: multi-company",
            model: MODEL,
            domain: "['|', ('x_company_id', '=', False), ('x_company_id', 'in', company_ids)]",
            groups: [],
            global_rule: true,
            ...ALL_PERMS,
        };
        const project = (line = {}, rules = []) => ({
            apps: [LOANS_APP],
            models: [
                modelLine({
                    order: "",
                    archivable: false,
                    manual_order: false,
                    per_company: false,
                    company_rule: false,
                    options_applied: {archivable: false, manual_order: false, per_company: false},
                    sort_fields: [["x_name", "Name"]],
                    ...line,
                }),
            ],
            access: [],
            rules,
            item_count: 2 + rules.length,
            touched_models: [],
        });
        answer = payload(project());
        respond.get_editor_data = (args) =>
            payload(answer.project, {model: args.args[0], viewId: args.args[1], viewType: args.args[2]});
        await openEditor();
        await openSpace("models");
        await contains(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).click();
        expect(".o_erplibre_studio_model_options").toHaveText(/Per company\s*x_company_id/);
        expect(".o_erplibre_studio_model_per_company").toBeEnabled();
        expect(".o_erplibre_studio_model_company_rule").toHaveCount(0);

        // On: the server adds the rule line, which the note names.
        respond.update_model = () =>
            payload({
                ...project({per_company: true, company_rule: [9, companyRule.name]}, [companyRule]),
                revision: 1,
            });
        await contains(".o_erplibre_studio_model_per_company").click();
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {per_company: true}]);
        expect(".o_erplibre_studio_model_per_company").toBeChecked();
        expect(".o_erplibre_studio_model_company_rule").toHaveText(
            /Rule « Loan item: multi-company »: a user sees the records of their companies and those of no company\.\s*Open in Security/
        );

        // « Open in Security » shows the rule in the rules tab.
        await contains(".o_erplibre_studio_model_company_rule_open").click();
        expect.verifySteps(["get_studio_choices 3", "get_access_existing x_loan_item"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "security");
        expect(".o_erplibre_studio_rule_form").toHaveCount(1);
        expect(".o_erplibre_studio_rule_domain").toHaveValue(companyRule.domain);

        // The rule removed in Security: the records are shared.
        respond.remove_rule = () => payload({...project({per_company: true, company_rule: false}), revision: 2});
        await contains(".o_erplibre_studio_remove_rule").click();
        expect(lastCall("remove_rule").args.slice(0, 2)).toEqual([3, 9]);
        await openSpace("models");
        await contains(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).click();
        expect(".o_erplibre_studio_model_company_rule").toHaveText(
            "No rule: records are shared between companies."
        );
        expect(".o_erplibre_studio_model_company_rule_open").toHaveCount(0);
    });

    test("the models space: per company applied is locked", async () => {
        answer = payload({
            apps: [LOANS_APP],
            models: [
                modelLine({
                    applied: true,
                    views: APPLIED_VIEWS,
                    order: "",
                    archivable: false,
                    manual_order: false,
                    per_company: true,
                    company_rule: false,
                    options_applied: {archivable: false, manual_order: false, per_company: true},
                    sort_fields: [["x_name", "Name"]],
                }),
            ],
            item_count: 1,
            touched_models: [],
        });
        respond.get_editor_data = (args) =>
            payload(answer.project, {model: args.args[0], viewId: args.args[1], viewType: args.args[2]});
        await openEditor();
        await openSpace("models");
        await contains(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).click();
        expect(".o_erplibre_studio_model_per_company").toBeChecked();
        expect(".o_erplibre_studio_model_per_company").not.toBeEnabled();
        expect(".o_erplibre_studio_model_option_locked").toHaveCount(1);
        expect(".o_erplibre_studio_model_archivable").toBeEnabled();
    });

    test("the access grid: a toggle and a new row send set_access", async () => {
        const row = {id: 1, model: MODEL, group: [1, "Role / User"], ...ALL_PERMS};
        answer = payload({models: [modelLine({applied: true, views: APPLIED_VIEWS})], access: [row], item_count: 2});
        respond.get_access_existing = (args) =>
            args.args[1] === "res.partner.category"
                ? [{id: 90, name: "res.partner.category", group: [1, "Role / User"], module: "base", perm_read: true}]
                : [];
        await openEditor();
        // The security space opens on its access rights.
        await openSpace("security");
        expect.verifySteps(["get_studio_choices 3", `get_access_existing ${MODEL}`]);
        expect(".o_erplibre_studio_access_toggle").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_palette").toHaveCount(0);
        expect(`.o_erplibre_studio_access_model[data-model=${MODEL}] .o_erplibre_studio_access_row`).toHaveCount(1);

        respond.set_access = (args) =>
            payload({
                ...answer.project,
                revision: answer.project.revision + 1,
                access: args.args[1].map((r, index) => ({
                    id: index + 1,
                    model: r.model,
                    group: [r.group_id, r.group_id === 1 ? "Role / User" : "Administration / Settings"],
                    perm_read: r.perm_read,
                    perm_write: r.perm_write,
                    perm_create: r.perm_create,
                    perm_unlink: r.perm_unlink,
                })),
            });
        await contains(".o_erplibre_studio_access_row .o_erplibre_studio_access_perm[data-perm=perm_unlink]").click();
        expect(lastCall("set_access").args[1]).toEqual([{model: MODEL, group_id: 1, ...ALL_PERMS, perm_unlink: false}]);
        expect(lastCall("set_access").kwargs.revision).toBe(0);
        expect(".o_erplibre_studio_access_perm[data-perm=perm_unlink]").not.toBeChecked();

        // A row on an existing model, next to the rows of its modules.
        await contains(".o_erplibre_studio_access_add_model").select("res.partner.category");
        await contains(".o_erplibre_studio_access_add_group").select("4");
        await contains(".o_erplibre_studio_access_add_perm[data-perm=perm_write]").check();
        await contains(".o_erplibre_studio_access_add_button").click();
        expect(lastCall("set_access").args[1]).toEqual([
            {model: MODEL, group_id: 1, ...ALL_PERMS, perm_unlink: false},
            {
                model: "res.partner.category",
                group_id: 4,
                perm_read: true,
                perm_write: true,
                perm_create: false,
                perm_unlink: false,
            },
        ]);
        expect(lastCall("set_access").kwargs.revision).toBe(1);
        expect.verifySteps(["get_access_existing res.partner.category"]);
        expect(
            ".o_erplibre_studio_access_model[data-model='res.partner.category'] .o_erplibre_studio_access_existing tr"
        ).toHaveCount(1);
        expect(".o_erplibre_studio_access_add_model").toHaveValue("");

        // Removing a row sends the others.
        await contains(
            ".o_erplibre_studio_access_model[data-model='res.partner.category'] .o_erplibre_studio_access_remove"
        ).click();
        expect(lastCall("set_access").args[1]).toEqual([{model: MODEL, group_id: 1, ...ALL_PERMS, perm_unlink: false}]);

        // Back to the view.
        await openSpace("view");
        expect(".o_erplibre_studio_access_panel").toHaveCount(0);
        expect(".o_erplibre_studio_palette").toHaveCount(1);
    });

    test("a rule: Check shows the count or the error, Save sends save_rule", async () => {
        answer = payload({models: [modelLine({applied: true, views: APPLIED_VIEWS})], item_count: 2});
        await openEditor();
        await openSpace("security");
        await contains(".o_erplibre_studio_rules_toggle").click();
        expect.verifySteps(["get_studio_choices 3", `get_access_existing ${MODEL}`, "get_studio_choices 3"]);
        expect(".o_erplibre_studio_no_rule").toHaveCount(1);
        await contains(".o_erplibre_studio_new_rule").click();
        expect(".o_erplibre_studio_rule_model").toHaveValue(MODEL);
        await contains(".o_erplibre_studio_rule_name").edit("Own items");
        await contains(".o_erplibre_studio_rule_add_group").select("1");
        expect(".o_erplibre_studio_rule_group[data-group='1']").toHaveCount(1);
        await contains(".o_erplibre_studio_rule_domain").edit("[('create_uid', '=', user.id)]");

        respond.check_rule_domain = () => ({ok: true, count: 3});
        await contains(".o_erplibre_studio_check_rule").click();
        expect(lastCall("check_rule_domain").args).toEqual([3, MODEL, "[('create_uid', '=', user.id)]"]);
        expect(".o_erplibre_studio_rule_check").toHaveAttribute("data-ok", "1");
        expect(".o_erplibre_studio_rule_check").toHaveText("The domain applies: 3 record(s) match it.");
        // The answer goes with the domain it checked.
        await contains(".o_erplibre_studio_rule_domain").edit("[('x_nope', '=', 1)]");
        expect(".o_erplibre_studio_rule_check").toHaveCount(0);
        respond.check_rule_domain = () => ({ok: false, error: "Invalid field x_loan_item.x_nope"});
        await contains(".o_erplibre_studio_check_rule").click();
        expect(".o_erplibre_studio_rule_check").toHaveAttribute("data-ok", "0");
        expect(".o_erplibre_studio_rule_check").toHaveText("Invalid field x_loan_item.x_nope");

        // A refusal of Save shows at the top of the form until the next Save,
        // whatever it is about; the answer of Check stays under the domain.
        await contains(".o_erplibre_studio_rule_perm[data-perm=perm_unlink]").uncheck();
        respond.save_rule = () => {
            throw makeServerError({message: "The draft of the project changed since this page loaded it: reload the editor."});
        };
        await contains(".o_erplibre_studio_save_rule").click();
        expect(".o_erplibre_studio_rule_error").toHaveText(/reload the editor/);
        expect(".o_erplibre_studio_rule_error").toHaveAttribute("role", "alert");
        expect(".o_erplibre_studio_rule_check").toHaveText("Invalid field x_loan_item.x_nope");
        expect(".o_erplibre_studio_rule_form").toHaveCount(1);
        await contains(".o_erplibre_studio_rule_domain").edit("[]");
        expect(".o_erplibre_studio_rule_error").toHaveCount(1);

        const rule = {
            id: 5,
            name: "Own items",
            model: MODEL,
            domain: "[('create_uid', '=', user.id)]",
            groups: [[1, "Role / User"]],
            ...ALL_PERMS,
            perm_unlink: false,
        };
        await contains(".o_erplibre_studio_rule_domain").edit(rule.domain);
        respond.save_rule = () => ({...payload({...answer.project, revision: 1, rules: [rule]}), saved_rule: 5});
        await contains(".o_erplibre_studio_save_rule").click();
        expect(lastCall("save_rule").args[1]).toEqual({
            id: false,
            name: "Own items",
            model: MODEL,
            domain: rule.domain,
            group_ids: [1],
            group_line_ids: [],
            global_rule: false,
            ...ALL_PERMS,
            perm_unlink: false,
        });
        expect(".o_erplibre_studio_rule_form").toHaveCount(0);
        expect(".o_erplibre_studio_rule[data-id='5']").toHaveCount(1);

        // Edit it again, then remove it.
        await contains(".o_erplibre_studio_edit_rule").click();
        expect(".o_erplibre_studio_rule_name").toHaveValue("Own items");
        expect(".o_erplibre_studio_rule_perm[data-perm=perm_unlink]").not.toBeChecked();
        respond.remove_rule = () => payload({...answer.project, revision: 2, rules: []});
        await contains(".o_erplibre_studio_remove_rule").click();
        expect(lastCall("remove_rule").args.slice(0, 2)).toEqual([3, 5]);
        expect(".o_erplibre_studio_rule_form").toHaveCount(0);
        expect(".o_erplibre_studio_no_rule").toHaveCount(1);
    });

    test("removing the model on screen goes back to the view the editor was opened on", async () => {
        const applied = modelLine({applied: true, views: APPLIED_VIEWS});
        answer = payload({state: "applied", models: [applied], item_count: 2, menus: APPLIED_MENUS});
        respond.get_editor_data = (args) =>
            payload(answer.project, {model: args.args[0], viewId: args.args[1], viewType: args.args[2]});
        await openEditor();
        await openSpace("models");
        await contains(".o_erplibre_studio_open_model[data-view-type=form]").click();
        expect.verifySteps([`get_editor_data ${MODEL} 51 form 3`]);
        await openSpace("models");
        respond.remove_model = () =>
            payload(
                {state: "draft", revision: 1, models: [], item_count: 1, menus: APPLIED_MENUS},
                {model: MODEL, viewId: 51}
            );
        await contains(".o_erplibre_studio_remove_model").click();
        await contains(".modal-footer .btn-primary").click();
        expect.verifySteps(["get_editor_data res.partner 12 form 3"]);
        expect(".o_erplibre_studio_title").toHaveText(/Contact/);
        // Apply then names the view on screen, and the menus follow.
        respond.project_action = () => payload({state: "applied", revision: 2, models: [], item_count: 0});
        await applyThroughReview();
        expect(lastCall("project_action").args.slice(1)).toEqual(["action_apply", "res.partner", 12, "form"]);
        expect.verifySteps(["menu reload"]);
    });

    test("an action that answers another view opens it", async () => {
        answer = payload({state: "draft", models: [modelLine({applied: true, views: APPLIED_VIEWS})], item_count: 2}, {
            model: MODEL,
            viewId: 51,
        });
        await mountWithCleanup(WebClient);
        patchWithCleanup(getService("menu"), {
            async reload() {
                expect.step("menu reload");
            },
        });
        await getService("action").doAction(customizeAction({resModel: MODEL, viewType: "form", viewId: 51}));
        await animationFrame();
        expect.verifySteps([`get_editor_data ${MODEL} 51 form false`]);
        // The server answers the view the editor goes back to, as when the
        // action removed the model on screen.
        respond.project_action = () => ({
            ...payload({state: "draft", revision: 1, models: [modelLine()], item_count: 2}),
            view_changed: true,
            notice: "Back to the last Apply, without what left the database since: the model x_loan_item.",
        });
        await applyMenu(".o_erplibre_studio_discard");
        expect(lastCall("project_action").args.slice(1)).toEqual(["action_discard", MODEL, 51, "form"]);
        expect(lastCall("project_action").kwargs.fallback).toEqual([MODEL, 51, "form"]);
        expect.verifySteps([]);
        expect(".o_erplibre_studio_title").toHaveText(/Contact/);
        expect(".o_notification").toHaveText(/without what left the database/);
        await applyThroughReview();
        expect(lastCall("project_action").args.slice(2)).toEqual(["res.partner", 12, "form"]);
    });

    test("the model dialog: an app needs a name, a taken name is skipped", async () => {
        answer = payload({apps: [LOANS_APP], models: [modelLine()], item_count: 2});
        await openEditor();
        await openSpace("models");
        await contains(".o_erplibre_studio_edit_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_save").toBeEnabled();
        // A new app for the model: it needs a name.
        await contains("#o_erplibre_studio_menu_new_app").click();
        expect(".o_erplibre_studio_model_save").not.toBeEnabled();
        expect(".o_erplibre_studio_app_name").toHaveClass("is-invalid");
        expect(".o_erplibre_studio_app_name").toHaveAttribute("aria-invalid", "true");
        await contains(".o_erplibre_studio_app_name").edit("Lending");
        expect(".o_erplibre_studio_model_save").toBeEnabled();
        expect(".o_erplibre_studio_app_name").toHaveAttribute("aria-invalid", "false");
        expect(".o_erplibre_studio_icon[aria-pressed=true]").toHaveCount(1);
        await contains(".modal-footer .btn-secondary").click();
        // « x_loan » is a model of another project.
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        await contains(".o_erplibre_studio_model_label").edit("Loan");
        expect(".o_erplibre_studio_model_name").toHaveValue("x_loan_2");
    });

    test("the controls of the panels have an accessible name", async () => {
        const row = {id: 1, model: MODEL, group: [1, "Role / User"], ...ALL_PERMS};
        answer = payload({models: [modelLine({applied: true, views: APPLIED_VIEWS})], access: [row], item_count: 2});
        await openEditor();
        await openSpace("security");
        expect.verifySteps(["get_studio_choices 3", `get_access_existing ${MODEL}`]);
        const perms = [...document.querySelectorAll(".o_erplibre_studio_access_perm")].map(accessibleName);
        expect(perms).toEqual(["Read – Role / User", "Write – Role / User", "Create – Role / User", "Delete – Role / User"]);
        for (const selector of [".o_erplibre_studio_access_add_model", ".o_erplibre_studio_access_add_group"]) {
            expect(accessibleName(document.querySelector(selector))).not.toBe("");
        }
        await contains(".o_erplibre_studio_rules_toggle").click();
        expect.verifySteps(["get_studio_choices 3"]);
        await contains(".o_erplibre_studio_new_rule").click();
        await contains(".o_erplibre_studio_rule_add_group").select("1");
        for (const name of ["rule_name", "rule_model", "rule_domain", "rule_add_group"]) {
            expect(accessibleName(document.querySelector(`.o_erplibre_studio_${name}`))).not.toBe("");
        }
        const remove = document.querySelector(".o_erplibre_studio_rule_group_remove");
        expect(remove.tagName).toBe("BUTTON");
        expect(accessibleName(remove)).toBe("Remove the group Role / User");
        await contains(".o_erplibre_studio_rule_group_remove").click();
        expect(".o_erplibre_studio_rule_group").toHaveCount(0);
        await openSpace("models");
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        await contains("#o_erplibre_studio_menu_under").click();
        for (const name of ["menu_parent", "menu_filter"]) {
            expect(accessibleName(document.querySelector(`.o_erplibre_studio_${name}`))).not.toBe("");
        }
        expect(".o_erplibre_studio_model_label").toHaveAttribute("aria-required", "true");
    });
    test("production: the dialog and the models space keep x_", async () => {
        answer = rulePayload(PRODUCTION_RULE, {apps: [LOANS_APP], models: [modelLine()], item_count: 2});
        await openEditor();
        await openSpace("models");
        await contains(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).click();
        expect(".o_erplibre_studio_model_detail_prefix").toHaveText("x_");
        expect(".o_erplibre_studio_model_detail_name").toHaveValue("loan_item");
        expect("#o_erplibre_studio_model_detail_name_note").toHaveText(/Odoo requires the x_ prefix/);
        // A line not applied yet: its name is checked on opening.
        await contains(".o_erplibre_studio_edit_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        await animationFrame();
        expect(modelChecks).toEqual([{name: MODEL, kwargs: {line_id: 7, label: "Loan item"}}]);
        expect(".o_erplibre_studio_model_name_status").toHaveAttribute("data-status", "available");
        expect("#o_erplibre_studio_model_name_help").toHaveText(/^Starts with x_, then lower case letters/);
        expect(".o_erplibre_studio_model_name_rule").toHaveAttribute("data-mode", "production");
        expect(".o_erplibre_studio_model_name_rule").toHaveText(/Production · x_ required/);
        await contains(".modal-footer .btn-secondary").click();
        // A new model: its name follows the label, checked once the typing pauses.
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_name_status").toHaveCount(0);
        await contains(".o_erplibre_studio_model_label").edit("Loan tag");
        expect(".o_erplibre_studio_model_name").toHaveValue("x_loan_tag");
        expect(".o_erplibre_studio_model_name_status").toHaveAttribute("data-status", "checking");
        await advanceTime(NAME_CHECK_DELAY);
        await animationFrame();
        expect(modelChecks.pop()).toEqual({name: "x_loan_tag", kwargs: {line_id: false, label: "Loan tag"}});
        expect(".o_erplibre_studio_model_name_status").toHaveAttribute("data-status", "available");
    });

    test("development: a name without x_ is checked live and created", async () => {
        answer = rulePayload(DEVELOPMENT_RULE);
        await openEditor();
        await openSpace("models");
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_name_rule").toHaveAttribute("data-mode", "development");
        expect(".o_erplibre_studio_model_name_rule").toHaveText(/Development · code_generator/);
        expect("#o_erplibre_studio_model_name_help").toHaveText(/x_ is optional on this development database/);
        await contains(".o_erplibre_studio_model_label").edit("Book");
        await contains(".o_erplibre_studio_model_name").edit("studio_demo.book");
        await advanceTime(NAME_CHECK_DELAY);
        await animationFrame();
        expect(modelChecks.map((check) => check.name)).toEqual(["studio_demo.book"]);
        expect(".o_erplibre_studio_model_name_status").toHaveAttribute("data-status", "available");
        expect(".o_erplibre_studio_model_name_message").toHaveText("Available");
        expect(".o_erplibre_studio_model_name_checks li[data-ok='1']").toHaveCount(4);
        expect(".o_erplibre_studio_model_save").toBeEnabled();
        respond.create_model = () => rulePayload(DEVELOPMENT_RULE, {revision: 1});
        await contains(".o_erplibre_studio_model_save").click();
        expect(lastCall("create_model").args[1].model).toBe("studio_demo.book");
        expect(".o_erplibre_studio_model_dialog").toHaveCount(0);
    });

    test("development: a taken name stops Save", async () => {
        answer = rulePayload(DEVELOPMENT_RULE);
        respond.check_model_name = (args) => modelCheck(args.args[1], "taken");
        await openEditor();
        await openSpace("models");
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        await contains(".o_erplibre_studio_model_label").edit("Contact");
        await contains(".o_erplibre_studio_model_name").edit("studio_demo.contact");
        await advanceTime(NAME_CHECK_DELAY);
        await animationFrame();
        expect(".o_erplibre_studio_model_name_status").toHaveAttribute("data-status", "taken");
        expect(".o_erplibre_studio_model_name_message").toHaveText("The model studio_demo.contact already exists.");
        expect(".o_erplibre_studio_model_name_checks li[data-key=unique]").toHaveAttribute("data-ok", "0");
        expect(".o_erplibre_studio_model_name_checks li[data-key=format]").toHaveAttribute("data-ok", "1");
        expect(".o_erplibre_studio_model_name").toHaveAttribute("aria-invalid", "true");
        expect(".o_erplibre_studio_model_save").not.toBeEnabled();
        // Another name, not checked yet: Save waits no more.
        respond.check_model_name = (args) => modelCheck(args.args[1]);
        await contains(".o_erplibre_studio_model_name").edit("studio_demo.person");
        expect(".o_erplibre_studio_model_save").toBeEnabled();
    });

    test("an answer older than the last check is dropped", async () => {
        answer = rulePayload(DEVELOPMENT_RULE);
        const answers = [new Deferred(), new Deferred()];
        respond.check_model_name = () => answers[modelChecks.length - 1];
        await openEditor();
        await openSpace("models");
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        await contains(".o_erplibre_studio_model_label").edit("Book");
        await contains(".o_erplibre_studio_model_name").edit("studio_demo.book");
        await advanceTime(NAME_CHECK_DELAY);
        // Away and back before the first answer: a second check of the same name.
        await contains(".o_erplibre_studio_model_name").edit("studio_demo.boo");
        await contains(".o_erplibre_studio_model_name").edit("studio_demo.book");
        await advanceTime(NAME_CHECK_DELAY);
        expect(modelChecks.map((check) => check.name)).toEqual(["studio_demo.book", "studio_demo.book"]);
        answers[1].resolve(modelCheck("studio_demo.book"));
        await animationFrame();
        expect(".o_erplibre_studio_model_name_status").toHaveAttribute("data-status", "available");
        answers[0].resolve(modelCheck("studio_demo.book", "taken"));
        await animationFrame();
        expect(".o_erplibre_studio_model_name_status").toHaveAttribute("data-status", "available");
        expect(".o_erplibre_studio_model_save").toBeEnabled();
    });

    test("development: the models space edits the whole name, x_ kept or not", async () => {
        const project = (model) => ({apps: [LOANS_APP], models: [modelLine({model})], item_count: 2});
        answer = rulePayload(DEVELOPMENT_RULE, project(MODEL));
        await openEditor();
        await openSpace("models");
        await contains(`.o_erplibre_studio_models_item[data-model=${MODEL}]`).click();
        expect(".o_erplibre_studio_model_detail_prefix").toHaveCount(0);
        expect(".o_erplibre_studio_model_detail_name").toHaveValue(MODEL);
        expect("#o_erplibre_studio_model_detail_name_note").toHaveText(
            /x_ is optional on this development database/
        );
        respond.update_model = () => rulePayload(DEVELOPMENT_RULE, {...project("studio_demo.loan"), revision: 1});
        await contains(".o_erplibre_studio_model_detail_name").edit("studio_demo.loan");
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {model: "studio_demo.loan"}]);
        expect(".o_erplibre_studio_model_detail_name").toHaveValue("studio_demo.loan");
        // A typed x_ stays.
        respond.update_model = () => rulePayload(DEVELOPMENT_RULE, {...project("x_loan_thing"), revision: 2});
        await contains(".o_erplibre_studio_model_detail_name").edit("x_loan_thing");
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([7, {model: "x_loan_thing"}]);
        expect(".o_erplibre_studio_model_detail_name").toHaveValue("x_loan_thing");
    });
});
