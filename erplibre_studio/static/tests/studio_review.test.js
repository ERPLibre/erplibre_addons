// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryAllAttributes, queryAllTexts} from "@odoo/hoot-dom";
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
import {reviewCounts, reviewItems, reviewWrites} from "@erplibre_studio/editor/studio_review";

const VISIT = "x_visit";
const CITY = "//field[@name='city']";
const LEVEL = "//field[@name='x_level']";

function field(name, label) {
    return {path: `//field[@name='${name}']`, tag: "field", kind: "field", name, label, attrs: {}, movable: true};
}

function payload(extra = {}) {
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "form",
        view_types: ["form", "list"],
        view: {id: 9, name: "res.partner.form", xml_id: "base.view_partner_form"},
        blocks: {
            path: "/form",
            tag: "form",
            kind: "container",
            label: "form",
            attrs: {},
            drop: true,
            children: [field("city", "Town"), field("x_level", "Level")],
        },
        layout: {root: "/form"},
        operations: ["add_field", "move", "remove", "hide", "relabel"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        fields: {
            city: {string: "City", type: "char"},
            x_level: {string: "Level", type: "char", project: true, pending: true},
        },
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
            change_count: 3,
            item_count: 6,
            applied: true,
            app: false,
            apps: [],
            groups: [],
            models: [
                {
                    id: 7,
                    model: VISIT,
                    name: "Visit",
                    chatter: false,
                    menu_mode: "app",
                    app_id: false,
                    menu_parent: false,
                    menu_name: "",
                    applied: true,
                    views: {},
                    pending_views: {},
                },
            ],
            access: [],
            rules: [],
            touched_models: [
                {model: "res.partner", name: "Contact", new: false, pending: false, fields: [], changes: 3},
            ],
        },
        projects: [{id: 3, name: "Visits", module_name: "studio_visits", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        ...extra,
    };
}

function item(type, id, category, text, values = {}) {
    return {key: `${type}:${id}`, type, id, category, text, error: false, applied: false, target: {}, ...values};
}

const VIEW_TARGET = {space: "view", model: "res.partner", view_id: 9, view_type: "form"};

/**
 * The review of the project: two views of the contacts, the visits model
 * (unchanged since the last Apply) with an access row, a rule of the
 * contacts in error.
 */
function review(values = {}) {
    return {
        revision: 0,
        state: "draft",
        groups: [
            {
                key: "view:9",
                kind: "view",
                title: "Contact — Form",
                ref: "base.view_partner_form",
                items: [
                    item("change", 1, "fields", "Add a new field: x_level", {target: {...VIEW_TARGET, path: LEVEL}}),
                    item("change", 2, "views", "Relabel: city = Town", {target: {...VIEW_TARGET, path: CITY}}),
                ],
            },
            {
                key: "view:10",
                kind: "view",
                title: "Contact — List",
                ref: "base.view_partner_tree",
                items: [
                    item("change", 3, "views", "Hide or show: email", {
                        error: "No node matches the xpath.",
                        target: {space: "view", model: "res.partner", view_id: 10, view_type: "list", path: false},
                    }),
                ],
            },
            {
                key: `model:${VISIT}`,
                kind: "model",
                title: "Model of the project",
                ref: VISIT,
                items: [
                    item("model", 7, "models", "Update the model Visit", {
                        applied: true,
                        target: {space: "models", model: VISIT},
                    }),
                    item("access", 1, "security", "Rights of Visits / User on Visit: read", {
                        target: {space: "security", tab: "access", model: VISIT},
                    }),
                ],
            },
            {
                key: "security:res.partner",
                kind: "security",
                title: "Security of Contact",
                ref: "res.partner",
                items: [
                    item("rule", 5, "security", "Rule « Team contacts » on Contact", {
                        error: "The rule Team contacts has no group.",
                        target: {space: "security", tab: "rules", model: "res.partner"},
                    }),
                ],
            },
        ],
        removal: {report: {}, digest: "n0thing", confirm: false},
        blocked: false,
        ...values,
    };
}

// The calls the tests check as steps; the others are in ``calls``.
const STEPPED = ["get_editor_data", "get_review", "project_action", "get_change_removal", "remove_change"];

let answer;
let respond;
let calls;

beforeEach(() => {
    serverState.debug = "1";
    defineWebModels();
    calls = [];
    respond = {};
    answer = payload();
    for (const method of [
        "get_editor_data",
        "get_review",
        "get_studio_choices",
        "get_access_existing",
        "get_group_members",
        "project_action",
        "get_change_removal",
        "remove_change",
    ]) {
        onRpc("erplibre.studio.editor", method, (args) => {
            calls.push({method, args: args.args, kwargs: args.kwargs});
            if (STEPPED.includes(method)) {
                expect.step(`${method} ${JSON.stringify(args.args.slice(0, 4))}`);
            }
            const result = respond[method] ? respond[method](args) : answer;
            if (result && result.project) {
                answer = result;
            }
            return result;
        });
    }
    respond.get_review = () => review();
    respond.get_studio_choices = () => ({
        mail_available: false,
        icons: [],
        menus: [],
        groups: [],
        apps: [],
        models: [
            ["res.partner", "Contact"],
            [VISIT, "Visit"],
        ],
        taken_models: [],
    });
    respond.get_access_existing = () => [];
    respond.get_group_members = () => ({groups: [], lines: []});
});

async function openReview() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 9}));
    await animationFrame();
    expect.verifySteps(['get_editor_data ["res.partner",9,"form",false]']);
    await contains(".o_erplibre_studio_apply_bar").click();
    expect.verifySteps(["get_review [3]"]);
}

const FILTER = (filter) => `.o_erplibre_studio_review_filter[data-filter=${filter}]`;

describe.current.tags("desktop");
describe("erplibre_studio review", () => {
    test("the helpers: items, counts by filter, what Apply writes", () => {
        const answer = review();
        expect(reviewItems(answer).map((i) => i.key)).toEqual([
            "change:1",
            "change:2",
            "change:3",
            "model:7",
            "access:1",
            "rule:5",
        ]);
        expect(reviewCounts(reviewItems(answer))).toEqual({all: 6, fields: 1, views: 2, models: 1, security: 2});
        // The model is unchanged since the last Apply: it is not written.
        expect(reviewWrites(answer)).toEqual({fields: 1, models: 0, views: 2, security: 2});
    });

    test("the items by view and by model, the filters, the errors", async () => {
        await openReview();
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "review");
        expect(".o_erplibre_studio_rail_item[data-space=review]").toHaveAttribute("aria-current", "page");
        expect(".o_erplibre_studio_review_intro").toHaveText(
            "5 change(s) to apply. Nothing is written to the database before you confirm."
        );
        // The item the last Apply wrote as it is hides until asked.
        expect(queryAllAttributes(".o_erplibre_studio_review_group", "data-group")).toEqual([
            "view:9",
            "view:10",
            `model:${VISIT}`,
            "security:res.partner",
        ]);
        expect(".o_erplibre_studio_review_group[data-group='view:9'] h3").toHaveText(
            /Contact — Form\s*base\.view_partner_form/i
        );
        expect(".o_erplibre_studio_review_group[data-group='view:9'] .o_erplibre_studio_review_ref").toHaveText(
            "base.view_partner_form"
        );
        expect(".o_erplibre_studio_review_item").toHaveCount(5);
        expect(".o_erplibre_studio_review_item[data-key='model:7']").toHaveCount(0);
        expect(queryAllTexts(".o_erplibre_studio_review_filter_count")).toEqual(["5", "1", "2", "0", "2"]);
        expect(FILTER("fields")).toHaveText(/^Fields\s*1$/);
        expect(FILTER("all")).toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_studio_review_filters").toHaveAttribute("role", "group");
        await contains(".o_erplibre_studio_review_show_applied").click();
        expect(".o_erplibre_studio_review_show_applied").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_studio_review_item[data-key='model:7'] .o_erplibre_studio_review_applied").toHaveCount(1);
        expect(`${FILTER("models")} .o_erplibre_studio_review_filter_count`).toHaveText("1");
        await contains(".o_erplibre_studio_review_show_applied").click();

        // A filter keeps one category.
        await contains(FILTER("security")).click();
        expect(FILTER("security")).toHaveAttribute("aria-pressed", "true");
        expect(FILTER("all")).toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_studio_review_item").toHaveCount(2);
        expect(".o_erplibre_studio_review_group").toHaveCount(2);
        await contains(FILTER("models")).click();
        expect(".o_erplibre_studio_review_empty").toHaveCount(1);
        await contains(FILTER("all")).click();

        // The errors.
        expect(".o_erplibre_studio_review_item_error").toHaveCount(2);
        expect(
            ".o_erplibre_studio_review_item[data-key='rule:5'] .o_erplibre_studio_review_item_message"
        ).toHaveText("The rule Team contacts has no group.");
        expect(".o_erplibre_studio_review_item[data-key='change:3'] .o_erplibre_studio_review_kind").toHaveText("View");
        expect(".o_erplibre_studio_review_item[data-key='change:1'] .o_erplibre_studio_review_kind").toHaveText("Field");
        expect(".o_erplibre_studio_review_item[data-key='rule:5'] .o_erplibre_studio_review_show").toHaveAttribute(
            "aria-label",
            "Show: Rule « Team contacts » on Contact"
        );
        // What Apply writes; nothing leaves the database.
        expect(".o_erplibre_studio_review_writes [data-count=fields]").toHaveText("1");
        expect(".o_erplibre_studio_review_writes [data-count=views]").toHaveText("2");
        expect(".o_erplibre_studio_review_writes [data-count=security]").toHaveText("2");
        expect(".o_erplibre_studio_review_removal").toHaveCount(0);
        expect(".o_erplibre_studio_review_blocked").toHaveCount(0);
        expect(".o_erplibre_studio_apply").toHaveText("Apply 5 change(s)");
        expect(".o_erplibre_studio_apply").toBeEnabled();
        // The top bar keeps its count, and its Apply does not apply.
        expect(".o_erplibre_studio_apply_bar").toHaveCount(1);
        expect.verifySteps([]);
    });

    test("Show reaches the item: a block of a view, a model, a rule", async () => {
        await openReview();
        // A change of the view on screen: no reload, the block is selected.
        await contains(".o_erplibre_studio_review_item[data-key='change:2'] .o_erplibre_studio_review_show").click();
        expect.verifySteps([]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "view");
        expect(".o_erplibre_studio_field[data-name=city]").toHaveClass("o_erplibre_studio_selected");

        // A change of another view opens it.
        await contains(".o_erplibre_studio_rail_item[data-space=review]").click();
        expect.verifySteps(["get_review [3]"]);
        await contains(".o_erplibre_studio_review_item[data-key='change:3'] .o_erplibre_studio_review_show").click();
        expect.verifySteps(['get_editor_data ["res.partner",10,"list",3]']);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "view");

        // A model: the models space on it.
        await contains(".o_erplibre_studio_rail_item[data-space=review]").click();
        expect.verifySteps(["get_review [3]"]);
        await contains(".o_erplibre_studio_review_show_applied").click();
        await contains(".o_erplibre_studio_review_item[data-key='model:7'] .o_erplibre_studio_review_show").click();
        expect.verifySteps([]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "models");
        expect(`.o_erplibre_studio_models_item[data-model=${VISIT}]`).toHaveAttribute("aria-current", "true");

        // A rule: the rules of its model in the security space.
        await contains(".o_erplibre_studio_rail_item[data-space=review]").click();
        expect.verifySteps(["get_review [3]"]);
        await contains(".o_erplibre_studio_review_item[data-key='rule:5'] .o_erplibre_studio_review_show").click();
        expect.verifySteps([]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "security");
        expect(".o_erplibre_studio_rules_toggle").toHaveAttribute("aria-selected", "true");
        expect(calls.filter((c) => c.method === "get_access_existing").pop().args).toEqual([3, "res.partner"]);
    });

    test("what Apply refuses, what leaves the database, Discard", async () => {
        respond.get_review = () =>
            review({
                blocked: "The rule Team contacts has no group: check « Global » or choose its groups.",
                removal: {
                    report: {fields: [{model: "res.partner", name: "x_old", label: "Old", filled: 4}]},
                    digest: "d1",
                    confirm: true,
                },
            });
        await openReview();
        expect(".o_erplibre_studio_review_blocked").toHaveText(/has no group/);
        expect(".o_erplibre_studio_review_removal .o_erplibre_studio_confirm_item").toHaveText(
            "Old (res.partner.x_old): 4 value(s)"
        );
        expect("label[for=o_erplibre_studio_review_understood]").toHaveText("I understand that these will be deleted.");
        await contains(".o_erplibre_studio_review_understood").click();
        // Apply waits as long as the server refuses the draft.
        expect(".o_erplibre_studio_apply").not.toBeEnabled();
        expect(".o_erplibre_studio_apply").toHaveAttribute("title", "Fix what Apply refuses first.");

        // Discard asks first, then goes back to the last Apply.
        respond.project_action = () => payload({project: {...answer.project, revision: 1, item_count: 0}});
        await contains(".o_erplibre_studio_review_discard").click();
        expect(".modal").toHaveCount(1);
        await contains(".modal-footer .btn-primary").click();
        expect.verifySteps(['project_action [3,"action_discard","res.partner",9]', "get_review [3]"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "review");

        // Back to the editor.
        await contains(".o_erplibre_studio_review_back").click();
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "view");
    });

    test("technical names that block Apply", async () => {
        respond.get_review = () =>
            review({
                name_blockers: [
                    {
                        change_id: 1,
                        model: "res.partner",
                        name: "x_level",
                        message: "The field x_level already exists in another project (Sample)",
                    },
                ],
            });
        await openReview();
        expect(".o_erplibre_studio_review_names").toHaveText(/^1 technical name\(s\) block Apply/);
        expect(".o_erplibre_studio_review_name_badge").toHaveCount(1);
        expect(
            ".o_erplibre_studio_review_item[data-key='change:1'] .o_erplibre_studio_review_name_badge"
        ).toHaveText("Technical name to fix");
        expect(".o_erplibre_studio_review_item[data-key='change:1'] .o_erplibre_studio_review_name_problem").toHaveText(
            /x_level · The field x_level already exists in another project/
        );
        expect(".o_erplibre_studio_apply").not.toBeEnabled();
        expect(".o_erplibre_studio_apply").toHaveAttribute("title", "1 technical name(s) block Apply");
    });

    test("the technical name of a new model that blocks Apply", async () => {
        const message = "Another model uses the table x_visit";
        const base = review();
        const models = base.groups.find((group) => group.kind === "model");
        models.items[0] = {...models.items[0], applied: false, error: message};
        respond.get_review = () =>
            review({
                groups: base.groups,
                // A model names its line, not a change: no change item takes it.
                name_blockers: [{line_id: 7, model: VISIT, name: VISIT, message}],
            });
        await openReview();
        expect(".o_erplibre_studio_review_names").toHaveText(/^1 technical name\(s\) block Apply\s*.*Models space/);
        expect(".o_erplibre_studio_review_name_badge").toHaveCount(1);
        const problem = ".o_erplibre_studio_review_item[data-key='model:7'] .o_erplibre_studio_review_name_problem";
        // The error of the item says it already: the name alone.
        expect(problem).toHaveText(/^Technical name to fix\s*x_visit$/);
        expect(".o_erplibre_studio_review_item[data-key='change:1'] .o_erplibre_studio_review_name_badge").toHaveCount(
            0
        );
    });

    test("Undo on a change of the review", async () => {
        respond.get_change_removal = (args) => ({
            revision: 0,
            change: {id: args.args[1], summary: "Relabel: city = Town", view: "res.partner.form", applied: false},
            items: [],
            refused: false,
            applied: false,
        });
        respond.remove_change = (args) =>
            payload({project: {...answer.project, revision: args.kwargs.revision + 1}, removed: [2]});
        await openReview();
        // Only the changes of a view are undone from here.
        expect(".o_erplibre_studio_review_undo").toHaveCount(3);
        expect(".o_erplibre_studio_review_item[data-type=change] .o_erplibre_studio_review_undo").toHaveCount(3);
        expect(".o_erplibre_studio_review_item[data-key='change:2'] .o_erplibre_studio_review_undo").toHaveAttribute(
            "aria-label",
            "Undo: Relabel: city = Town"
        );
        await contains(".o_erplibre_studio_review_item[data-key='change:2'] .o_erplibre_studio_review_undo").click();
        // Nothing depends on it: no question; the review reads the new revision.
        expect.verifySteps(["get_change_removal [3,2]", 'remove_change [3,2,[2],"res.partner"]', "get_review [3]"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-space", "review");
        expect(".modal").toHaveCount(0);
    });

    test("what leaves without data needs no « I understand »", async () => {
        respond.get_review = () =>
            review({
                removal: {
                    report: {views: [{name: "res.partner.pivot.studio", kind: "default"}]},
                    digest: "d2",
                    confirm: false,
                },
            });
        await openReview();
        expect(".o_erplibre_studio_review_removal .o_erplibre_studio_confirm_item").toHaveCount(1);
        expect(".o_erplibre_studio_review_understood").toHaveCount(0);
        expect(".o_erplibre_studio_apply").toBeEnabled();
    });
});
