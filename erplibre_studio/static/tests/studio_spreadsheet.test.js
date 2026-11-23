// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {animationFrame} from "@odoo/hoot-mock";
import {Component, xml} from "@odoo/owl";
import {
    contains,
    defineWebModels,
    getService,
    makeServerError,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    serverState,
    webModels,
} from "@web/../tests/web_test_helpers";
import {registry} from "@web/core/registry";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";

const ITEM = ".o_erplibre_studio_send_spreadsheet";
// The client action the test opens in place of the sheet of spreadsheet_oca.
const SHEET_TAG = "erplibre_studio_test_sheet";

class TestSheet extends Component {
    static template = xml`<div class="o_erplibre_studio_test_sheet"/>`;
    static props = ["*"];
}

/** The editor payload of the contact view ``viewType``, a list by default. */
function payload(extra = {}) {
    const viewType = extra.view_type || "list";
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: viewType,
        view: {id: 7, name: `res.partner.${viewType}`, xml_id: false, pending: false, added: false},
        blocks: {
            path: `/${viewType}`,
            tag: viewType,
            kind: "container",
            drop: true,
            label: viewType,
            attrs: {},
            children: [
                {
                    path: "//field[@name='name']",
                    tag: "field",
                    kind: "field",
                    name: "name",
                    label: "Name",
                    attrs: {},
                },
            ],
        },
        layout: {root: `/${viewType}`},
        operations: ["add_existing_field", "move", "remove"],
        hide_mode: "column_invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list", "kanban", "search", "pivot"],
        fields: {name: {string: "Name", type: "char"}},
        palette: [],
        field_types: ["char"],
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
        spreadsheet_available: true,
        ...extra,
    };
}

let answer;
// The answer of send_to_spreadsheet, or an error it raises.
let sent;

beforeEach(() => {
    serverState.debug = "1";
    webModels.ResPartner._views.list = `<list><field name="name"/></list>`;
    defineWebModels();
    answer = payload();
    sent = {
        action: {
            type: "ir.actions.client",
            tag: "action_spreadsheet_oca",
            params: {model: "spreadsheet.spreadsheet", spreadsheet_id: 11, import_data: {mode: "list"}},
        },
        notice: false,
    };
    onRpc("erplibre.studio.editor", "get_editor_data", (args) => {
        expect.step(`get_editor_data ${args.args.slice(0, 4).join(" ")}`);
        return answer;
    });
    onRpc("erplibre.studio.editor", "send_to_spreadsheet", (args) => {
        expect.step(`send_to_spreadsheet ${args.args.join(" ")}`);
        if (sent instanceof Error) {
            throw sent;
        }
        return sent;
    });
    registry.category("actions").add(SHEET_TAG, TestSheet, {force: true});
});

/** The editor on the contact view ``viewType``, then the action service patched to open the test sheet. */
async function openEditor(viewType = "list") {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType, viewId: 7}));
    await animationFrame();
    expect.verifySteps([`get_editor_data res.partner 7 ${viewType} false`]);
    patchWithCleanup(getService("action"), {
        doAction(action, options) {
            if (action && action.tag === "action_spreadsheet_oca") {
                expect.step(`doAction ${action.params.spreadsheet_id} ${action.params.import_data.mode}`);
                return super.doAction({type: "ir.actions.client", tag: SHEET_TAG}, options);
            }
            return super.doAction(action, options);
        },
    });
}

describe.current.tags("desktop");
describe("erplibre_studio spreadsheet", () => {
    test("Send to a spreadsheet creates the sheet and opens it", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_apply_menu").click();
        expect(ITEM).toHaveCount(1);
        expect(ITEM).toBeEnabled();
        expect(ITEM).toHaveText("Send to a spreadsheet");
        await contains(ITEM).click();
        await animationFrame();
        expect.verifySteps(["send_to_spreadsheet 3 res.partner 7 list", "doAction 11 list"]);
        expect(".o_erplibre_studio_test_sheet").toHaveCount(1);
        expect(".o_notification").toHaveCount(0);
    });

    test("the notice of the server shows as a warning", async () => {
        sent.notice = "The sheet reads the view as applied: its draft changes are not in it.";
        await openEditor();
        await contains(".o_erplibre_studio_apply_menu").click();
        await contains(ITEM).click();
        await animationFrame();
        expect.verifySteps(["send_to_spreadsheet 3 res.partner 7 list", "doAction 11 list"]);
        expect(".o_notification .o_notification_bar").toHaveClass("bg-warning");
        expect(".o_notification_content").toHaveText(sent.notice);
    });

    test("an error of the server stays in the editor", async () => {
        sent = makeServerError({message: "Apply first: the sheet reads the applied view."});
        await openEditor();
        await contains(".o_erplibre_studio_apply_menu").click();
        await contains(ITEM).click();
        await animationFrame();
        expect.verifySteps(["send_to_spreadsheet 3 res.partner 7 list"]);
        expect(".o_erplibre_studio_test_sheet").toHaveCount(0);
        expect(".o_notification .o_notification_bar").toHaveClass("bg-danger");
        expect(".o_notification_content").toHaveText("Apply first: the sheet reads the applied view.");
        expect(".o_erplibre_studio_apply_menu").toBeEnabled();
    });

    test("a pivot offers the item", async () => {
        answer = payload({view_type: "pivot"});
        await openEditor("pivot");
        await contains(".o_erplibre_studio_apply_menu").click();
        expect(ITEM).toHaveCount(1);
        await contains(ITEM).click();
        await animationFrame();
        expect.verifySteps(["send_to_spreadsheet 3 res.partner 7 pivot", "doAction 11 list"]);
    });

    test("no item on a form", async () => {
        answer = payload({view_type: "form"});
        await openEditor("form");
        await contains(".o_erplibre_studio_apply_menu").click();
        expect(".o_erplibre_studio_open_project").toHaveCount(1);
        expect(ITEM).toHaveCount(0);
    });

    test("no item without spreadsheet_oca or its group", async () => {
        answer = payload({spreadsheet_available: false});
        await openEditor();
        await contains(".o_erplibre_studio_apply_menu").click();
        expect(".o_erplibre_studio_open_project").toHaveCount(1);
        expect(ITEM).toHaveCount(0);
    });

    test("disabled on a view that is not applied yet", async () => {
        answer = payload();
        answer.view = {...answer.view, added: {line_id: 5, applied: false, name: "List", layers: []}};
        await openEditor();
        await contains(".o_erplibre_studio_apply_menu").click();
        expect(ITEM).toHaveCount(1);
        expect(ITEM).not.toBeEnabled();
    });

    test("disabled on the pending view of a model not created yet", async () => {
        answer = payload();
        answer.view = {...answer.view, pending: true, model_line_id: 4};
        await openEditor();
        await contains(".o_erplibre_studio_apply_menu").click();
        expect(ITEM).not.toBeEnabled();
    });

    test("enabled on an added view once applied", async () => {
        answer = payload();
        answer.view = {...answer.view, added: {line_id: 5, applied: true, name: "List", layers: []}};
        await openEditor();
        await contains(".o_erplibre_studio_apply_menu").click();
        expect(ITEM).toBeEnabled();
    });

    test("back from the sheet, the editor reopens on its view and project", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_apply_menu").click();
        await contains(ITEM).click();
        await animationFrame();
        expect.verifySteps(["send_to_spreadsheet 3 res.partner 7 list", "doAction 11 list"]);
        await getService("action").restore();
        await animationFrame();
        // The project on screen goes back with the view, not the action's none.
        expect.verifySteps(["get_editor_data res.partner 7 list 3"]);
        expect(".o_erplibre_studio_test_sheet").toHaveCount(0);
        expect(".o_erplibre_studio_field[data-name=name]").toHaveCount(1);
    });
});
