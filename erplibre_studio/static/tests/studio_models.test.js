// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {animationFrame} from "@odoo/hoot-mock";
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

function modelLine(extra = {}) {
    return {
        id: 7,
        model: MODEL,
        name: "Loan item",
        chatter: true,
        menu_mode: "app",
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

// The payload the editor shows, the choices of the dialogs, and how each
// call answers: ``respond[method](args)``.
let answer;
let choices;
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

beforeEach(() => {
    serverState.debug = "1";
    defineWebModels();
    calls = [];
    choices = JSON.parse(JSON.stringify(CHOICES));
    respond = {};
    onRpc("erplibre.studio.editor", "get_editor_data", (args) => {
        expect.step(`get_editor_data ${args.args.slice(0, 4).join(" ")}`);
        return respond.get_editor_data ? respond.get_editor_data(args) : answer;
    });
    onRpc("erplibre.studio.editor", "get_studio_choices", (args) => {
        expect.step(`get_studio_choices ${args.args[0]}`);
        return choices;
    });
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
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_dialog").toHaveCount(1);
        expect(".o_erplibre_studio_model_save").not.toBeEnabled();

        await contains(".o_erplibre_studio_model_label").edit("Équipement de prêt");
        expect(".o_erplibre_studio_model_name").toHaveValue("x_equipement_de_pret");
        expect(".o_erplibre_studio_app_name").toHaveValue("Équipement de prêt");
        await contains(".o_erplibre_studio_model_name").edit("x_loan_item");
        await contains(".o_erplibre_studio_model_label").edit("Loan item");
        expect(".o_erplibre_studio_model_name").toHaveValue("x_loan_item");
        expect(".o_erplibre_studio_app_name").toHaveValue("Loan item");

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

        // Back to a new app.
        await contains("#o_erplibre_studio_menu_app").click();
        expect(".o_erplibre_studio_app_form").toHaveCount(1);
        respond.create_model = () =>
            payload({revision: 1, item_count: 2, app: {name: "Loan item", icon: BASE_ICON}, models: [modelLine()]});
        await contains(".o_erplibre_studio_model_save").click();
        const call = lastCall("create_model");
        expect(call.args.slice(0, 1).concat(call.args.slice(2))).toEqual([3, "res.partner", 12, "form"]);
        expect(call.args[1]).toEqual({
            name: "Loan item",
            model: MODEL,
            chatter: true,
            menu: {mode: "app", name: "", app_name: "Loan item", app_icon: BASE_ICON},
        });
        expect(call.kwargs.revision).toBe(0);
        expect(".o_erplibre_studio_model_dialog").toHaveCount(0);

        // The model waits for Apply; Apply is enabled on the items of the project.
        expect(`.o_erplibre_studio_model[data-model=${MODEL}] .o_erplibre_studio_model_state`).toHaveAttribute(
            "data-applied",
            "0"
        );
        expect(".o_erplibre_studio_apply_open").toHaveCount(1);
        expect(".o_erplibre_studio_open_model").toHaveCount(0);
        expect(".o_erplibre_studio_apply").toBeEnabled();
    });

    test("without mail, no chatter; the app of the project; under a menu", async () => {
        answer = payload({app: {name: "Loans", icon: false}, models: [modelLine({chatter: false})], item_count: 2});
        choices.mail_available = false;
        await openEditor();
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_chatter").toHaveCount(0);
        expect("label[for=o_erplibre_studio_menu_app]").toHaveText("In the app « Loans » of the project");
        expect(".o_erplibre_studio_app_form").toHaveCount(0);
        await contains(".o_erplibre_studio_model_label").edit("Loan tag");
        await contains("#o_erplibre_studio_menu_under").click();
        await contains(".o_erplibre_studio_menu_parent").select("21");
        await contains(".o_erplibre_studio_menu_name").edit("Tags");
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
        await contains(".o_erplibre_studio_apply_open").click();
        expect(lastCall("project_action").args[1]).toBe("action_apply");
        // The view the editor was opened on, where it goes back when the model leaves.
        expect(lastCall("project_action").kwargs.fallback).toEqual(["res.partner", 12, "form"]);
        // The new app and its menu reach the web client.
        expect.verifySteps(["menu reload", `get_editor_data ${MODEL} 51 form 3`]);
        expect(".o_erplibre_studio_title").toHaveText(/Loan item\s*·\s*studio_loans\.view_x_loan_item_form/);
        expect(`.o_erplibre_studio_model[data-model=${MODEL}]`).toHaveClass("o_erplibre_studio_model_current");
        expect(".o_erplibre_studio_model_state").toHaveAttribute("data-applied", "1");
        // The chatter stays where the view puts it.
        expect(".o_erplibre_studio_other[data-tag=chatter]").toHaveAttribute("draggable", "false");
        expect(`.o_erplibre_studio_hook[data-target='/form/chatter']`).toHaveCount(0);
        expect(`.o_erplibre_studio_other[data-tag=chatter] .o_erplibre_studio_hook`).toHaveCount(0);
        expect(`.o_erplibre_studio_hook[data-target="//group[@name='studio_left']"]`).toHaveCount(1);

        await contains(".o_erplibre_studio_open_model[data-view-type=list]").click();
        expect.verifySteps([`get_editor_data ${MODEL} 52 list 3`]);
    });

    test("a model of the project is edited and removed", async () => {
        answer = payload({app: {name: "Loans", icon: false}, models: [modelLine()], item_count: 2});
        await openEditor();
        await contains(".o_erplibre_studio_edit_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_name").toHaveValue(MODEL);
        await contains(".o_erplibre_studio_model_label").edit("Loaned item");
        expect(".o_erplibre_studio_model_name").toHaveValue(MODEL);
        await contains(".o_erplibre_studio_app_name").edit("Lending");
        respond.update_app = () => payload({...answer.project, revision: 1, app: {name: "Lending", icon: false}});
        respond.update_model = () => payload({...answer.project, revision: 2});
        await contains(".o_erplibre_studio_model_save").click();
        expect(calls.map((c) => c.method)).toEqual(["update_app", "update_model"]);
        expect(lastCall("update_app").args[1]).toEqual({name: "Lending", icon: false});
        expect(lastCall("update_model").args.slice(1, 3)).toEqual([
            7,
            {name: "Loaned item", model: MODEL, chatter: true, menu: {mode: "app", name: ""}},
        ]);
        expect(lastCall("update_model").kwargs.revision).toBe(1);

        respond.remove_model = () => payload({revision: 3});
        await contains(".o_erplibre_studio_remove_model").click();
        await contains(".modal-footer .btn-primary").click();
        expect(lastCall("remove_model").args.slice(0, 2)).toEqual([3, 7]);
        expect(".o_erplibre_studio_no_model").toHaveCount(1);
    });

    test("the access grid: a toggle and a new row send set_access", async () => {
        const row = {id: 1, model: MODEL, group: [1, "Role / User"], ...ALL_PERMS};
        answer = payload({models: [modelLine({applied: true, views: APPLIED_VIEWS})], access: [row], item_count: 2});
        respond.get_access_existing = (args) =>
            args.args[1] === "res.partner.category"
                ? [{id: 90, name: "res.partner.category", group: [1, "Role / User"], module: "base", perm_read: true}]
                : [];
        await openEditor();
        await contains(".o_erplibre_studio_access_toggle").click();
        expect.verifySteps(["get_studio_choices 3", `get_access_existing ${MODEL}`]);
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
        await contains(".o_erplibre_studio_access_toggle").click();
        expect(".o_erplibre_studio_access_panel").toHaveCount(0);
        expect(".o_erplibre_studio_palette").toHaveCount(1);
    });

    test("a rule: Check shows the count or the error, Save sends save_rule", async () => {
        answer = payload({models: [modelLine({applied: true, views: APPLIED_VIEWS})], item_count: 2});
        await openEditor();
        await contains(".o_erplibre_studio_rules_toggle").click();
        expect.verifySteps(["get_studio_choices 3"]);
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
        await contains(".o_erplibre_studio_open_model[data-view-type=form]").click();
        expect.verifySteps([`get_editor_data ${MODEL} 51 form 3`]);
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
        await contains(".o_erplibre_studio_apply").click();
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
        await contains(".o_erplibre_studio_discard").click();
        expect(lastCall("project_action").args.slice(1)).toEqual(["action_discard", MODEL, 51, "form"]);
        expect(lastCall("project_action").kwargs.fallback).toEqual([MODEL, 51, "form"]);
        expect.verifySteps([]);
        expect(".o_erplibre_studio_title").toHaveText(/Contact/);
        expect(".o_notification").toHaveText(/without what left the database/);
        await contains(".o_erplibre_studio_apply").click();
        expect(lastCall("project_action").args.slice(2)).toEqual(["res.partner", 12, "form"]);
    });

    test("the model dialog: an app needs a name, a taken name is skipped", async () => {
        answer = payload({app: {name: "Loans", icon: false}, models: [modelLine()], item_count: 2});
        await openEditor();
        await contains(".o_erplibre_studio_edit_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        expect(".o_erplibre_studio_model_save").toBeEnabled();
        await contains(".o_erplibre_studio_app_name").edit("");
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
        await contains(".o_erplibre_studio_access_toggle").click();
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
        await contains(".o_erplibre_studio_new_model").click();
        expect.verifySteps(["get_studio_choices 3"]);
        await contains("#o_erplibre_studio_menu_under").click();
        for (const name of ["menu_parent", "menu_filter"]) {
            expect(accessibleName(document.querySelector(`.o_erplibre_studio_${name}`))).not.toBe("");
        }
        expect(".o_erplibre_studio_model_label").toHaveAttribute("aria-required", "true");
    });
});
