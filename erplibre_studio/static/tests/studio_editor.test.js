// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {Deferred, animationFrame} from "@odoo/hoot-mock";
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
import {findBlock, isTrue, selectionToText, textToSelection} from "@erplibre_studio/editor/studio_editor";

const NAME = "//field[@name='name']";
const EMAIL = "//field[@name='email']";

function column(name, label, attrs = {}) {
    return {path: `//field[@name='${name}']`, tag: "field", kind: "field", name, label, attrs};
}

/** The editor payload of a contact list with ``columns``. */
function payload(columns, extra = {}) {
    const fields = {
        name: {string: "Name", type: "char"},
        email: {string: "Email", type: "char"},
        ref: {string: "Reference", type: "char"},
    };
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "list",
        view: {id: 7, name: "res.partner.list", xml_id: "base.view_partner_tree"},
        blocks: {
            path: "/list",
            tag: "list",
            kind: "container",
            drop: true,
            label: "list",
            attrs: {},
            children: columns,
        },
        layout: {root: "/list"},
        operations: [
            "add_field",
            "add_existing_field",
            "move",
            "remove",
            "hide",
            "relabel",
            "required",
            "readonly",
            "help",
            "optional",
            "update_field",
        ],
        hide_mode: "column_invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list", "kanban", "search", "pivot"],
        fields,
        palette: [{name: "ref", string: "Reference", type: "char"}],
        field_types: ["char", "integer", "selection"],
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
            change_count: 1,
            applied: false,
        },
        projects: [{id: 3, name: "Contacts", module_name: "studio_contacts", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        ...extra,
    };
}

let answer;
// A promise the next apply_operation waits for, when set.
let holdOperation;

beforeEach(() => {
    serverState.debug = "1";
    webModels.ResPartner._views.list = `<list><field name="name"/><field name="email"/></list>`;
    defineWebModels();
    answer = payload([column("name", "Name"), column("email", "Email")]);
    holdOperation = null;
    onRpc("erplibre.studio.editor", "get_editor_data", (args) => {
        expect.step(`get_editor_data ${args.args.slice(0, 4).join(" ")}`);
        if (args.kwargs.pick_project === false) {
            return payload(answer.blocks.children, {project: false});
        }
        return answer;
    });
    onRpc("erplibre.studio.editor", "apply_operation", async (args) => {
        const operation = args.args[4];
        const parts = [operation.type, operation.source || operation.field_name, operation.position];
        parts.push(operation.target, operation.value);
        expect.step(["apply_operation", ...parts.filter(Boolean)].join(" "));
        expect(args.kwargs.revision).toBe(answer.project.revision);
        if (holdOperation) {
            await holdOperation;
        }
        if (operation.type === "add_field") {
            expect(operation.field.ttype).toBe("char");
            answer = payload([column("name", "Name"), column("email", "Email"), column("x_text", "Text")]);
            answer.fields.x_text = {
                string: "Text",
                type: "char",
                project: true,
                pending: true,
                definition: {ttype: "char", field_description: "Text", help: "", readonly: false},
            };
        } else if (operation.type === "move") {
            answer = payload([column("email", "Email"), column("name", "Name")]);
        } else if (operation.type === "relabel") {
            answer = payload([column("name", "Name"), column("email", operation.value, {string: operation.value})]);
        }
        answer.project.revision = args.kwargs.revision + 1;
        return answer;
    });
    onRpc("erplibre.studio.editor", "project_action", (args) => {
        expect.step(`project_action ${args.args[1]}`);
        answer = payload(answer.blocks.children, {
            project: {...answer.project, state: "applied", state_label: "Applied", applied: true},
        });
        return answer;
    });
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "list", viewId: 7}));
    await animationFrame();
    expect.verifySteps(["get_editor_data res.partner 7 list false"]);
}

function hook(target, position) {
    return `.o_erplibre_studio_hook[data-target="${target}"][data-position=${position}]`;
}

describe.current.tags("desktop");
describe("erplibre_studio editor", () => {
    test("renders the columns and the palette", async () => {
        await openEditor();
        expect(".o_erplibre_studio_field").toHaveCount(2);
        expect(".o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "name");
        // A hook before each column and one at the end.
        expect(".o_erplibre_studio_hook").toHaveCount(3);
        expect(".o_erplibre_studio_new_field").toHaveCount(3);
        expect(".o_erplibre_studio_state").toHaveText("Draft");
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        expect(".o_erplibre_studio_existing_field").toHaveCount(1);
        await contains(".o_erplibre_studio_palette_filter").edit("zzz");
        expect(".o_erplibre_studio_existing_field").toHaveCount(0);
    });

    test("dragging a column onto a hook moves it", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=email]").dragAndDrop(hook(NAME, "before"));
        expect.verifySteps([`apply_operation move ${EMAIL} before ${NAME}`]);
        expect(".o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "email");
        expect(".o_erplibre_studio_field[data-name=email]").toHaveClass("o_erplibre_studio_selected");
        expect(document.body).not.toHaveClass("o_erplibre_studio_dragging");
    });

    test("dropping a new field type adds a field and selects it", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_new_field[data-type=char]").dragAndDrop(hook("/list", "inside"));
        expect.verifySteps(["apply_operation add_field inside /list"]);
        expect(".o_erplibre_studio_field[data-name=x_text]").toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_field[data-name=x_text] .o_erplibre_studio_flag[data-flag=pending]").toHaveCount(1);
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "x_text");
        expect(".o_erplibre_studio_prop_label").toHaveValue("Text");
    });

    test("the properties relabel a column; apply", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=email]").click();
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "email");
        await contains(".o_erplibre_studio_prop_label").edit("Mail");
        expect.verifySteps([`apply_operation relabel ${EMAIL} Mail`]);
        expect(".o_erplibre_studio_field[data-name=email] .o_erplibre_studio_label").toHaveText("Mail");
        await contains(".o_erplibre_studio_apply").click();
        expect.verifySteps(["project_action action_apply"]);
        expect(".o_erplibre_studio_state").toHaveText("Applied");
    });

    test("the debug menu of a form or a list opens the editor", async () => {
        await mountWithCleanup(WebClient);
        await getService("action").doAction({
            name: "Partners",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "list"]],
        });
        await contains(".o_debug_manager button").click();
        await contains(".dropdown-menu .dropdown-item:contains('Customize this view')").click();
        await animationFrame();
        expect.verifySteps(["get_editor_data res.partner false list false"]);
        expect(".o_erplibre_studio").toHaveCount(1);
    });

    test("'New project…' and 'Choose a project…' leave the project", async () => {
        await openEditor();
        for (const value of ["new", ""]) {
            await contains(".o_erplibre_studio_project_select").select(value);
            await animationFrame();
            expect.verifySteps(["get_editor_data res.partner 7 list false"]);
            expect(".o_erplibre_studio_state").toHaveCount(0);
            expect(".o_erplibre_studio_apply").toHaveCount(0);
            expect(".o_erplibre_studio_new_project").toHaveCount(value === "new" ? 1 : 0);
            expect(".o_erplibre_studio_project_select").toHaveValue(value);
            // No edit reaches the former project.
            await contains(".o_erplibre_studio_field[data-name=email]").dragAndDrop(hook(NAME, "before"));
            expect.verifySteps([]);
        }
        await contains(".o_erplibre_studio_project_select").select("3");
        await animationFrame();
        expect.verifySteps(["get_editor_data res.partner 7 list 3"]);
        expect(".o_erplibre_studio_state").toHaveText("Draft");
    });

    test("an operation waits for the answer of the previous one", async () => {
        await openEditor();
        const hold = new Deferred();
        holdOperation = hold;
        await contains(".o_erplibre_studio_field[data-name=email]").dragAndDrop(hook(NAME, "before"));
        expect.verifySteps([`apply_operation move ${EMAIL} before ${NAME}`]);
        expect(".o_erplibre_studio_canvas").toHaveClass("o_erplibre_studio_busy");
        expect(".o_erplibre_studio_project_select").toHaveAttribute("disabled");
        // A second drop while the first one runs is ignored.
        await contains(".o_erplibre_studio_field[data-name=name]").dragAndDrop(hook("/list", "inside"));
        expect.verifySteps([]);
        holdOperation = null;
        hold.resolve();
        await animationFrame();
        expect(".o_erplibre_studio_canvas").not.toHaveClass("o_erplibre_studio_busy");
        expect(".o_erplibre_studio_field:eq(0)").toHaveAttribute("data-name", "email");
        // The next operation names the revision of the last answer.
        await contains(".o_erplibre_studio_prop_label").edit("Mail");
        expect.verifySteps([`apply_operation relabel ${EMAIL} Mail`]);
    });

    test("helpers", () => {
        expect(isTrue("True")).toBe(true);
        expect(isTrue("not is_company")).toBe(false);
        expect(textToSelection("a:A\n b \n\nc: C")).toEqual([
            ["a", "A"],
            ["b", "b"],
            ["c", "C"],
        ]);
        expect(selectionToText([["a", "A"]])).toBe("a:A");
        const tree = payload([column("name", "Name")]).blocks;
        expect(findBlock(tree, (b) => b.name === "name").path).toBe(NAME);
        expect(findBlock(tree, (b) => b.name === "none")).toBe(null);
    });
});
