// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryAllTexts} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
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
import {chainLevels, existingApps, inheritedLines} from "@erplibre_studio/editor/studio_groups";
import {
    accessChanged,
    pickModel,
    replaceDomainField,
    ruleConditions,
    securityModels,
    suggestField,
} from "@erplibre_studio/editor/studio_security";

const VISIT = "x_visit";
const ALL_PERMS = {perm_read: true, perm_write: true, perm_create: true, perm_unlink: true};

const APP = {
    id: 1,
    name: "Visits",
    icon: false,
    xml_name: "menu_app",
    menu_sequence: 50,
    sequence: 10,
    applied: true,
    models: [7],
    groups: [3, 4],
    chain: false,
};

function group(id, name, extra = {}) {
    return {
        id,
        app_id: 1,
        name,
        xml_name: `group_visits_${name.toLowerCase()}`,
        comment: "",
        implied: [],
        implied_groups: [],
        missing_implied: [],
        applied: true,
        ...extra,
    };
}

const GROUPS = [group(3, "User", {implied_groups: [[1, "Role / User"]]}), group(4, "Manager")];

// A row of the project on the visits whose right to create the draft gives.
const ROW = {
    id: 1,
    model: VISIT,
    group: false,
    group_line: [3, "Visits / User"],
    ...ALL_PERMS,
    perm_unlink: false,
    applied: {...ALL_PERMS, perm_create: false, perm_unlink: false},
};

// A rule on the contacts that names a field the model does not have.
const RULE = {
    id: 5,
    name: "Team contacts",
    model: "res.partner",
    domain: "[('user', '=', user.id), ('is_company', '=', True)]",
    groups: [],
    group_lines: [[3, "Visits / User"]],
    global_rule: false,
    missing_groups: [],
    ...ALL_PERMS,
};

const CHOICES = {
    mail_available: false,
    icons: [],
    menus: [],
    groups: [
        {id: 1, name: "Role / User", xml_id: "base.group_user", category: [50, "Role"]},
        {id: 2, name: "Role / Portal", xml_id: "base.group_portal", category: [50, "Role"]},
        {id: 9, name: "Administration / Settings", xml_id: "base.group_system", category: [60, "Administration"]},
        {id: false, line_id: 3, name: "Visits / User", xml_id: "studio_visits.group_visits_user", project: true},
        {id: false, line_id: 4, name: "Visits / Manager", xml_id: "studio_visits.group_visits_manager", project: true},
    ],
    apps: [{id: 1, name: "Visits", icon: false, xml_name: "menu_app"}],
    models: [
        ["res.partner", "Contact"],
        [VISIT, "Visit"],
    ],
    taken_models: [],
};

function payload(project = {}) {
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "form",
        view_types: ["form", "list"],
        view: {id: 12, name: "res.partner.form", xml_id: "base.view_partner_form"},
        blocks: {path: "/form", tag: "form", kind: "container", label: "form", attrs: {}, children: []},
        layout: {root: "/form"},
        operations: ["add_field", "move", "remove", "hide"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        fields: {},
        palette: [],
        field_types: ["char"],
        changes: [],
        errors: [],
        project: {
            id: 3,
            name: "Visits",
            module_name: "studio_visits",
            state: "draft",
            state_label: "Draft",
            revision: 0,
            preview_value: "3:0",
            change_count: 2,
            item_count: 6,
            applied: true,
            app: false,
            apps: [APP],
            groups: GROUPS,
            models: [
                {
                    id: 7,
                    model: VISIT,
                    name: "Visit",
                    chatter: false,
                    menu_mode: "app",
                    app_id: 1,
                    menu_parent: false,
                    menu_name: "",
                    applied: true,
                    views: {},
                },
            ],
            access: [ROW],
            rules: [RULE],
            touched_models: [
                {model: "res.partner", name: "Contact", new: false, pending: false, fields: [], changes: 2},
            ],
            ...project,
        },
        projects: [{id: 3, name: "Visits", module_name: "studio_visits", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        mail_available: false,
    };
}

let answer;
let respond;
let calls;

const lastCall = (method) => calls.filter((c) => c.method === method).pop();

beforeEach(() => {
    serverState.debug = "1";
    defineWebModels();
    calls = [];
    respond = {};
    answer = payload();
    for (const method of [
        "get_editor_data",
        "get_studio_choices",
        "get_access_existing",
        "get_group_members",
        "get_group_losses",
        "check_rule_domain",
        "set_access",
        "save_rule",
        "save_group",
    ]) {
        onRpc("erplibre.studio.editor", method, (args) => {
            calls.push({method, args: args.args, kwargs: args.kwargs});
            const result = respond[method] ? respond[method](args) : answer;
            if (result && result.project) {
                answer = result;
            }
            return result;
        });
    }
    respond.get_studio_choices = () => JSON.parse(JSON.stringify(CHOICES));
    respond.get_access_existing = (args) =>
        args.args[1] === "res.partner"
            ? [
                  {
                      id: 90,
                      name: "res.partner.user",
                      group: [1, "Role / User"],
                      module: "base",
                      ...ALL_PERMS,
                      perm_unlink: false,
                  },
              ]
            : [];
    respond.get_group_members = (args) => ({
        groups: (args.kwargs.group_ids || []).map((id) => ({
            id,
            name: "Role / User",
            xml_id: "base.group_user",
            category: [50, "Role"],
            implied: [],
            count: 3,
            users: [],
            more: true,
        })),
        lines: (args.kwargs.line_ids || []).map((lineId) => ({
            line_id: lineId,
            applied: true,
            count: lineId === 3 ? 2 : 1,
            users:
                lineId === 3
                    ? [
                          {id: 11, name: "Ann Demo", direct: true},
                          {id: 12, name: "Bob Demo", direct: false},
                      ]
                    : [{id: 12, name: "Bob Demo", direct: true}],
            more: false,
        })),
    });
    respond.get_group_losses = () => [];
});

async function openSecurity() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 12}));
    await animationFrame();
    await contains(".o_erplibre_studio_rail_item[data-space=security]").click();
    await animationFrame();
}

describe("the security space, helpers", () => {
    test("the models, the changed rights, the conditions of a domain", () => {
        const project = payload().project;
        expect(securityModels(project).map((entry) => [entry.model, entry.isNew, entry.access, entry.rules])).toEqual([
            [VISIT, true, 1, 0],
            ["res.partner", false, 0, 1],
        ]);
        const models = securityModels(project);
        expect(pickModel(models, null, "res.partner")).toBe("res.partner");
        expect(pickModel(models, VISIT, "res.partner")).toBe(VISIT);
        expect(pickModel(models, "x_gone", "res.users")).toBe(VISIT);
        expect(pickModel([], null, "res.partner")).toBe(null);
        expect(accessChanged(ROW, "perm_create")).toBe(true);
        expect(accessChanged(ROW, "perm_read")).toBe(false);
        expect(accessChanged({...ROW, applied: false}, "perm_create")).toBe(false);

        const fields = {
            user_id: {string: "Salesperson", type: "many2one"},
            is_company: {string: "Is a Company", type: "boolean"},
            type: {string: "Address Type", type: "selection", selection: [["other", "Other Address"]]},
            company_id: {string: "Company", type: "many2one"},
        };
        const read = ruleConditions("[('user_id', '=', user.id), ('type', '!=', 'other')]", fields, true);
        expect(read.connector).toBe("&");
        // The words of the operators and of the values the rules evaluate
        // are translated: the editor test reads them once the web client runs.
        expect(read.conditions.map((c) => [c.path, c.field, c.bad])).toEqual([
            ["user_id", "Salesperson", false],
            ["type", "Address Type", false],
        ]);
        expect(read.conditions[1].value).toBe("Other Address");
        const any = ruleConditions(
            "['|', ('is_company', '=', True), ('company_id', 'in', company_ids)]",
            fields,
            true
        );
        expect(any.connector).toBe("|");
        expect(any.conditions.map((c) => c.field)).toEqual(["Is a Company", "Company"]);
        // An unknown field is bad only when the fields of the model are known.
        expect(ruleConditions("[('user', '=', 1)]", fields, true).conditions[0].bad).toBe(true);
        expect(ruleConditions("[('user', '=', 1)]", fields, false).conditions[0].bad).toBe(false);
        expect(ruleConditions("[]", fields).conditions).toEqual([]);
        expect(ruleConditions("[(", fields)).toBe(null);
        expect(ruleConditions("['&', ('a', '=', 1), '|', ('b', '=', 2), ('c', '=', 3)]", null)).toBe(null);

        expect(suggestField("user", fields)).toBe("user_id");
        expect(suggestField("compan", fields)).toBe("company_id");
        expect(suggestField("zz", fields)).toBe(null);
        expect(replaceDomainField("[('user', '=', user.id), ('name', '=', 'user')]", "user", "user_id")).toBe(
            "[('user_id', '=', user.id), ('name', '=', 'user')]"
        );
        expect(replaceDomainField('[("user", "=", 1)]', "user", "user_id")).toBe('[("user_id", "=", 1)]');
    });

    test("the groups: levels of a chain, implications received, existing apps", () => {
        const chained = [
            group(4, "Manager", {implied: [[3, "User"]]}),
            group(3, "User", {implied_groups: [[1, "Role / User"]]}),
            group(5, "Auditor"),
        ];
        const project = {groups: chained, access: [], rules: []};
        expect(chainLevels(project, APP).map((entry) => [entry.group.name, entry.level, entry.linked])).toEqual([
            ["User", 1, false],
            ["Auditor", 1, false],
            ["Manager", 2, false],
        ]);
        const two = {groups: chained.slice(0, 2)};
        expect(chainLevels(two, APP).map((entry) => [entry.group.name, entry.linked])).toEqual([
            ["User", false],
            ["Manager", true],
        ]);
        expect(inheritedLines(project, [4])).toEqual({3: 4});
        expect(existingApps(project, CHOICES)).toEqual([
            {id: 50, name: "Role", groups: ["Role / User", "Role / Portal"]},
        ]);
    });
});

describe.current.tags("desktop");
describe("erplibre_studio editor, security space", () => {
    test("rights: the models of the project, one table with the rows of the modules, the group of a row", async () => {
        await openSecurity();
        // The model on screen shows first, next to the other models of the project.
        expect(queryAllTexts(".o_erplibre_studio_security_model code")).toEqual([VISIT, "res.partner"]);
        expect(".o_erplibre_studio_security_model[data-model='res.partner']").toHaveAttribute("aria-current", "true");
        expect(".o_erplibre_studio_access_toggle").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_access_toggle").toHaveAttribute("role", "tab");
        expect(".o_erplibre_studio_access_toggle .o_erplibre_studio_security_count").toHaveText("1");
        expect(".o_erplibre_studio_rules_toggle .o_erplibre_studio_security_count").toHaveText("1");
        expect(".o_erplibre_studio_apps_toggle .o_erplibre_studio_security_count").toHaveText("2");
        // The rows of the modules: read-only, with their origin.
        expect(".o_erplibre_studio_access_row").toHaveCount(0);
        expect(".o_erplibre_studio_access_existing tr").toHaveCount(1);
        expect(".o_erplibre_studio_access_existing tr").toHaveText(/Module base/);
        expect(".o_erplibre_studio_access_existing .o_erplibre_studio_access_perm").toHaveCount(0);
        expect(".o_erplibre_studio_access_fixed[data-perm=perm_unlink]").toHaveAttribute(
            "aria-label",
            "Delete – Role / User: not given, read-only"
        );
        await contains(".o_erplibre_studio_access_existing .o_erplibre_studio_access_pick").click();
        await animationFrame();
        expect(lastCall("get_group_members").kwargs.group_ids).toEqual([1]);
        expect(".o_erplibre_studio_row_inspector").toHaveAttribute("data-kind", "existing");
        expect(".o_erplibre_studio_row_app").toHaveText("Role");
        expect(".o_erplibre_studio_row_members").toHaveText(/3 member\(s\)/);
        expect(".o_erplibre_studio_row_inspector").toHaveText(/installed module/);

        // The visits: the row of the project, its changed right marked.
        await contains(`.o_erplibre_studio_security_model[data-model=${VISIT}]`).click();
        expect(`.o_erplibre_studio_access_model[data-model=${VISIT}] .o_erplibre_studio_access_row`).toHaveCount(1);
        expect(".o_erplibre_studio_access_perm[data-changed='1']").toHaveCount(1);
        expect(".o_erplibre_studio_access_perm[data-changed='1']").toHaveAttribute("data-perm", "perm_create");
        expect(".o_erplibre_studio_access_perm[data-changed='1']").toHaveAttribute(
            "aria-label",
            /: changed in this draft$/
        );
        expect(".o_erplibre_studio_access_perm[data-changed='0']:first").not.toHaveAttribute(
            "aria-label",
            /changed in this draft/
        );
        expect(".o_erplibre_studio_access_legend").toHaveCount(1);
        expect(".o_erplibre_studio_access_row .o_erplibre_studio_project_badge").toHaveCount(1);
        expect(".o_erplibre_studio_access_row code").toHaveText("studio_visits.group_visits_user");
        // The inspector: the app, the implied groups, the members of the group.
        await contains(".o_erplibre_studio_access_row .o_erplibre_studio_access_pick").click();
        await animationFrame();
        expect(lastCall("get_group_members").kwargs.line_ids).toEqual([3]);
        expect(".o_erplibre_studio_row_app").toHaveText("Visits");
        expect(".o_erplibre_studio_row_implies").toHaveText("Role / User");
        expect(".o_erplibre_studio_row_members").toHaveText(/2 member\(s\)/);
        expect(".o_erplibre_studio_row_members").toHaveText(/Ann Demo/);
        expect(".o_erplibre_studio_row_summary").toHaveText("Can read, write, create the records of Visit.");
        expect(".o_erplibre_studio_access_pick[aria-pressed=true]").toHaveCount(1);
    });

    test("rules: the domain as conditions, a fix, the operations, Check, the switch Global", async () => {
        await openSecurity();
        await contains(".o_erplibre_studio_rules_toggle").click();
        await animationFrame();
        const card = ".o_erplibre_studio_rule[data-id='5']";
        expect(`${card} .o_erplibre_studio_rule_group_line`).toHaveText("Visits / User");
        expect(`${card} .o_erplibre_studio_condition`).toHaveCount(2);
        expect(`${card} .o_erplibre_studio_condition_bad`).toHaveCount(1);
        expect(`${card} .o_erplibre_studio_condition[data-path=user]`).toHaveText(/unknown field/);
        expect(`${card} .o_erplibre_studio_condition[data-path=is_company]`).toHaveText(/is\s+Yes/);
        expect(`${card} .o_erplibre_studio_condition_connector`).toHaveText("AND");
        expect(`${card} .o_erplibre_studio_rule_status`).toHaveText("Not checked yet");

        // The unknown field, replaced by the field it most likely means.
        expect(`${card} .o_erplibre_studio_rule_fix`).toHaveAttribute("data-field", "user_id");
        const saved = (values) => payload({revision: answer.project.revision + 1, rules: [{...RULE, ...values}]});
        respond.save_rule = (args) => saved({domain: args.args[1].domain, perm_unlink: args.args[1].perm_unlink});
        await contains(`${card} .o_erplibre_studio_rule_fix`).click();
        expect(lastCall("save_rule").args[1]).toEqual({
            id: 5,
            name: "Team contacts",
            model: "res.partner",
            domain: "[('user_id', '=', user.id), ('is_company', '=', True)]",
            group_ids: [],
            group_line_ids: [3],
            global_rule: false,
            ...ALL_PERMS,
        });
        expect(`${card} .o_erplibre_studio_condition_bad`).toHaveCount(0);
        expect(`${card} .o_erplibre_studio_rule_fix`).toHaveCount(0);
        expect(`${card} .o_erplibre_studio_condition[data-path=user_id]`).toHaveText(/user_id\s+is\s+Current user/);

        // An operation: one save of the rule.
        expect(`${card} .o_erplibre_studio_rule_op[data-perm=perm_unlink]`).toHaveAttribute("aria-pressed", "true");
        await contains(`${card} .o_erplibre_studio_rule_op[data-perm=perm_unlink]`).click();
        expect(lastCall("save_rule").args[1].perm_unlink).toBe(false);
        expect(lastCall("save_rule").kwargs.revision).toBe(1);
        expect(`${card} .o_erplibre_studio_rule_op[data-perm=perm_unlink]`).toHaveAttribute("aria-pressed", "false");

        // Check, then clear the answer.
        respond.check_rule_domain = () => ({ok: true, count: 4});
        await contains(`${card} .o_erplibre_studio_verify_rule`).click();
        await animationFrame();
        expect(lastCall("check_rule_domain").args).toEqual([3, "res.partner", answer.project.rules[0].domain]);
        expect(`${card} .o_erplibre_studio_rule_status`).toHaveAttribute("data-ok", "1");
        expect(`${card} .o_erplibre_studio_rule_status`).toHaveText("Valid domain · 4 record(s)");
        await contains(`${card} .o_erplibre_studio_verify_rule`).click();
        expect(`${card} .o_erplibre_studio_rule_status`).toHaveText("Not checked yet");

        // The form in the inspector: « Global » is a switch, with its warning.
        await contains(`${card} .o_erplibre_studio_rule_pick`).click();
        expect(`${card}`).toHaveClass("o_erplibre_studio_rule_selected");
        expect(".o_erplibre_studio_rule_form .o_erplibre_studio_rule_global_check").toHaveAttribute("role", "switch");
        expect(".o_erplibre_studio_rule_global_note").toHaveCount(0);
        await contains(".o_erplibre_studio_rule_global_check").check();
        expect(".o_erplibre_studio_rule_global_note").toHaveAttribute("role", "note");
        expect(".o_erplibre_studio_rule_add_group").toHaveCount(0);
        expect(".o_erplibre_studio_rule_ops_text").toHaveText(/read, write, create them/);
    });

    test("rule form: the visual domain editor checks then fills the form", async () => {
        await openSecurity();
        await contains(".o_erplibre_studio_rules_toggle").click();
        await animationFrame();
        await contains(".o_erplibre_studio_rule[data-id='5'] .o_erplibre_studio_rule_pick").click();
        expect(".o_erplibre_studio_check_rule").toHaveCount(1);
        expect(".o_erplibre_studio_rule_domain_visual").toBeEnabled();
        await contains(".o_erplibre_studio_rule_domain_visual").click();
        expect(".o_dialog .o_domain_selector").toHaveCount(1);
        const CODE = ".o_dialog .o_domain_selector_debug_container textarea";
        expect(CODE).toHaveValue(RULE.domain);

        // A refused domain: the error in the dialog, the form unchanged.
        respond.check_rule_domain = () => ({ok: false, error: "Invalid field res.partner.nowhere"});
        await contains(CODE).edit('[("nowhere", "=", 1)]');
        await contains(".o_erplibre_studio_domain_confirm").click();
        expect(".o_erplibre_studio_domain_error").toHaveText("Invalid field res.partner.nowhere");
        expect(".o_dialog").toHaveCount(1);
        expect(".o_erplibre_studio_rule_domain").toHaveValue(RULE.domain);

        // A domain that applies fills the form with its check; Save stays to do.
        const domain = '[("create_uid", "=", user.id)]';
        respond.check_rule_domain = () => ({ok: true, count: 2});
        await contains(CODE).edit(domain);
        await contains(".o_erplibre_studio_domain_confirm").click();
        expect(lastCall("check_rule_domain").args).toEqual([3, "res.partner", domain]);
        expect(".o_dialog").toHaveCount(0);
        expect(".o_erplibre_studio_rule_domain").toHaveValue(domain);
        expect(".o_erplibre_studio_rule_check").toHaveAttribute("data-ok", "1");
        expect(lastCall("save_rule")).toBe(undefined);
    });

    test("rule form: no visual domain editor on a model not created yet", async () => {
        const project = payload().project;
        answer = payload({
            models: [{...project.models[0], applied: false}],
            rules: [{...RULE, model: VISIT}],
        });
        await openSecurity();
        await contains(".o_erplibre_studio_rules_toggle").click();
        await animationFrame();
        await contains(`.o_erplibre_studio_security_model[data-model=${VISIT}]`).click();
        await contains(".o_erplibre_studio_rule[data-id='5'] .o_erplibre_studio_rule_pick").click();
        expect(".o_erplibre_studio_rule_domain_visual").not.toBeEnabled();
        expect(".o_erplibre_studio_rule_domain_visual").toHaveAttribute(
            "title",
            "Apply the model first: the visual editor reads its fields."
        );
    });

    test("a rule whose group left the database: its operations wait, Remove saves it again", async () => {
        answer = payload({rules: [{...RULE, group_lines: [], missing_groups: ["studio_visits.group_gone"]}]});
        await openSecurity();
        await contains(".o_erplibre_studio_rules_toggle").click();
        expect(".o_erplibre_studio_rule_gone").toHaveAttribute("role", "alert");
        expect(".o_erplibre_studio_missing_group").toHaveText("This group no longer exists: studio_visits.group_gone");
        expect(".o_erplibre_studio_rule_op[data-perm=perm_read]").not.toBeEnabled();
        respond.save_rule = () => payload({revision: 1, rules: [{...RULE, group_lines: []}]});
        await contains(".o_erplibre_studio_rule_drop_gone").click();
        expect(lastCall("save_rule").args[1].group_line_ids).toEqual([]);
        expect(".o_erplibre_studio_rule_gone").toHaveCount(0);
        expect(".o_erplibre_studio_rule_no_group").toHaveCount(1);
    });

    test("groups: the chain, the members, what Apply takes from them, the existing apps", async () => {
        respond.get_group_losses = () => [
            {
                group: [30, "Visits / User"],
                line_id: 3,
                via: [40, "Visits / Manager"],
                via_line_id: 4,
                count: 1,
                users: [{id: 12, name: "Bob Demo"}],
                more: false,
            },
        ];
        await openSecurity();
        await contains(".o_erplibre_studio_apps_toggle").click();
        await animationFrame();
        expect(lastCall("get_group_members").kwargs.line_ids).toEqual([3, 4]);
        expect(lastCall("get_group_losses").args).toEqual([3]);
        const card = ".o_erplibre_studio_app_card[data-app=menu_app]";
        expect(`${card} .o_erplibre_studio_app_toggle`).toHaveAttribute("aria-expanded", "true");
        expect(queryAllTexts(`${card} .o_erplibre_studio_group_name`)).toEqual(["User", "Manager"]);
        expect(queryAllTexts(`${card} .o_erplibre_studio_group_members`)).toEqual(["2 member(s)", "1 member(s)"]);
        expect(`${card} .o_erplibre_studio_chain_link`).toHaveAttribute("data-linked", "0");
        expect(`${card} .o_erplibre_studio_chain_warning`).toHaveCount(1);
        // The members the next Apply removes, and the implication back.
        expect(`${card} .o_erplibre_studio_group_loss`).toHaveAttribute("role", "alert");
        expect(`${card} .o_erplibre_studio_group_loss`).toHaveText(
            /Apply will remove 1 member\(s\) from Visits \/ User/
        );
        expect(`${card} .o_erplibre_studio_group_loss`).toHaveText(/Bob Demo/);
        const chained = [GROUPS[0], {...GROUPS[1], implied: [[3, "User"]]}];
        respond.save_group = () => payload({revision: 1, apps: [{...APP, chain: true}], groups: chained});
        respond.get_group_losses = () => [];
        await contains(`${card} .o_erplibre_studio_restore_implied`).click();
        await animationFrame();
        expect(lastCall("save_group").args[1]).toEqual({
            id: 4,
            name: "Manager",
            app_id: 1,
            comment: "",
            implied_line_ids: [3],
            implied_group_ids: [],
        });
        expect(`${card} .o_erplibre_studio_group_loss`).toHaveCount(0);
        expect(`${card} .o_erplibre_studio_chain_link`).toHaveAttribute("data-linked", "1");
        expect(queryAllTexts(`${card} .o_erplibre_studio_group_level`)).toEqual(["Level 1", "Level 2"]);
        expect(`${card} .o_erplibre_studio_chain_note`).toHaveAttribute("role", "note");

        // The form of a group in the inspector: its members, an implication received.
        await contains(
            `${card} .o_erplibre_studio_group[data-group=group_visits_user] .o_erplibre_studio_group_pick`
        ).click();
        expect(".o_erplibre_studio_group_form_name").toHaveValue("User");
        expect(queryAllTexts(".o_erplibre_studio_member .o_erplibre_studio_member_name")).toEqual([
            "Ann Demo",
            "Bob Demo",
        ]);
        expect(queryAllTexts(".o_erplibre_studio_member .badge")).toEqual(["direct", "through an implication"]);
        expect(".o_erplibre_studio_implied_line[data-id='4']").toHaveCount(0);
        await contains(".o_erplibre_studio_group_form .btn-secondary").click();

        // An existing app the project names, folded.
        const role = ".o_erplibre_studio_existing_app[data-category='50']";
        expect(`${role} .o_erplibre_studio_app_toggle`).toHaveAttribute("aria-expanded", "false");
        await contains(`${role} .o_erplibre_studio_app_toggle`).click();
        expect(`${role} .card-body`).toHaveText(/Role \/ Portal/);
    });
});
