// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {hover, queryOne} from "@odoo/hoot-dom";
import {Deferred, animationFrame, mockTimeZone} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    serverState,
    webModels,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {fieldNameOf, targetFromController} from "@erplibre_developer/developer_service";
import {formatIsoDateTime} from "@erplibre_developer/drawer/developer_drawer";

function payload(args) {
    const [model, viewId, viewType] = args.args;
    return {
        model,
        model_name: "Contact",
        view_type: viewType,
        view: {
            id: 7,
            name: "res.partner.list",
            xml_id: "base.view_partner_tree",
            module: "base",
            model,
            type: viewType,
            priority: 16,
            mode: "primary",
            is_current: true,
            file: "/src/base/views/res_partner_views.xml",
            file_rel: "base/views/res_partner_views.xml",
            line: 53,
            specs: [],
            fields: [],
            groups: [],
            arch: "<list/>",
            requested: viewId,
        },
        views: [
            {
                id: 7,
                name: "res.partner.list",
                xml_id: "base.view_partner_tree",
                module: "base",
                priority: 16,
                mode: "primary",
                is_current: true,
                inherit_name: false,
                groups: [],
                specs: [],
                fields: [],
                arch: "<list/>",
                file: false,
                file_rel: false,
                line: 0,
            },
            {
                id: 8,
                name: "res.partner.list.extension",
                xml_id: "example.view_partner_tree_extension",
                module: "example",
                priority: 20,
                mode: "extension",
                is_current: false,
                inherit_name: "base.view_partner_tree",
                groups: [],
                specs: [{expr: "//field[@name='name']", position: "after", attributes: []}],
                fields: ["name"],
                arch: "<field name='name' position='after'/>",
                file: "/src/example/views/views.xml",
                file_rel: "example/views/views.xml",
                line: 4,
            },
        ],
        combined_arch: '<list><field name="name"/></list>',
        fields: [
            {
                name: "name",
                string: "Name",
                type: "char",
                relation: false,
                related: false,
                inherited_model: false,
                manual: false,
                defined_in: {
                    module: "base",
                    file: "/src/base/models/res_partner.py",
                    file_rel: "base/models/res_partner.py",
                    line: 200,
                },
                overrides: [
                    {
                        kind: "field",
                        module: "example",
                        attrs: ["tracking"],
                        file: "/src/example/models/res_partner.py",
                        file_rel: "example/models/res_partner.py",
                        line: 10,
                    },
                ],
                override_modules: ["example"],
            },
        ],
        modules: ["base", "example"],
        action: false,
        server_actions_allowed: false,
        ide_available: false,
    };
}

// The answer of the next get_code_info calls; a function may return a
// promise.
let codeAnswers;

function codeModule(name) {
    return {
        name,
        state: "installed",
        installed_version: "18.0.1.0.0",
        code_version: "18.0.1.0.0",
        path: `/src/${name}`,
        path_rel: name,
        clone: false,
        clone_rel: false,
        module_rel: false,
        repo: false,
        repo_source: false,
    };
}

beforeEach(() => {
    serverState.debug = "1";
    webModels.ResPartner._views.list = `<list><field name="name"/></list>`;
    defineWebModels();
    codeAnswers = [];
    onRpc("erplibre.developer", "get_view_info", (args) => {
        expect.step(`get_view_info ${args.args[0]} ${args.args[2]}`);
        return payload(args);
    });
    onRpc("erplibre.developer", "get_code_info", (args) => {
        expect.step(`get_code_info ${args.args[0].join(",")}`);
        const answer = codeAnswers.shift();
        return answer ? answer() : {modules: [], snapshot_date: false, error: false};
    });
});

async function openPartners() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        name: "Partners",
        res_model: "res.partner",
        type: "ir.actions.act_window",
        views: [[false, "list"]],
    });
}

async function openDrawer() {
    await openPartners();
    await contains(".o_debug_manager button").click();
    await contains(".dropdown-menu .dropdown-item:contains('Developer panel')").click();
    await animationFrame();
    // One introspection call per opening, never a code call.
    expect.verifySteps(["get_view_info res.partner list"]);
}

describe.current.tags("desktop");
describe("erplibre_developer drawer", () => {
    test("opens from the debug menu and lists the views", async () => {
        await openDrawer();
        expect(".o_erplibre_dev_drawer").toHaveCount(1);
        expect(document.body).toHaveClass("o_erplibre_dev_open");
        expect(".o_erplibre_dev_view_row").toHaveCount(2);
        expect(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_module").toHaveText("example");
        expect(".o_erplibre_dev_specs code").toHaveText("//field[@name='name']");
        expect(".o_erplibre_dev_specs .badge").toHaveText("after");
        // The page stays usable under the drawer.
        expect(".o_list_view").toHaveCount(1);
    });

    test("hovering a view or a field highlights the page", async () => {
        await openDrawer();
        await hover(".o_erplibre_dev_view_row:eq(1)");
        expect("th[data-name=name]").toHaveClass("o_erplibre_dev_highlight");
        await hover(".o_erplibre_dev_header");
        expect(".o_erplibre_dev_highlight").toHaveCount(0);
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        expect(".o_erplibre_dev_field_row[data-field=name] .o_erplibre_dev_overridden_by").toHaveText(
            "Overridden by example"
        );
        await hover(".o_erplibre_dev_field_row[data-field=name]");
        expect("th[data-name=name]").toHaveClass("o_erplibre_dev_highlight");
    });

    test("inspect selects the clicked field", async () => {
        await openDrawer();
        await contains(".o_erplibre_dev_inspect").click();
        expect(document.body).toHaveClass("o_erplibre_dev_inspecting");
        await contains("th[data-name=name]").click();
        await animationFrame();
        expect(document.body).not.toHaveClass("o_erplibre_dev_inspecting");
        expect(".o_erplibre_dev_tabs [data-tab=fields]").toHaveClass("active");
        expect(".o_erplibre_dev_field_row[data-field=name]").toHaveClass("o_erplibre_dev_selected");
    });

    test("the code tab loads on demand, the drawer closes", async () => {
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps(["get_code_info base,example"]);
        await contains(".o_erplibre_dev_tabs [data-tab=actions]").click();
        expect(".o_erplibre_dev_upgrade:first").toHaveAttribute("disabled");
        expect(".o_erplibre_dev_actions_disabled").toHaveCount(1);
        await contains(".o_erplibre_dev_close").click();
        expect(".o_erplibre_dev_drawer").toHaveCount(0);
        expect(document.body).not.toHaveClass("o_erplibre_dev_open");
    });

    test("a code answer of a former target is dropped", async () => {
        const slow = new Deferred();
        codeAnswers = [() => slow, () => ({modules: [codeModule("fresh")], snapshot_date: false, error: false})];
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps(["get_code_info base,example"]);
        // The target reloads while the first code call runs.
        await contains(".o_erplibre_dev_refresh").click();
        await animationFrame();
        expect.verifySteps(["get_view_info res.partner list", "get_code_info base,example"]);
        expect(".o_erplibre_dev_code_row").toHaveCount(1);
        expect(".o_erplibre_dev_code_row").toHaveAttribute("data-module", "fresh");
        slow.resolve({modules: [codeModule("stale")], snapshot_date: false, error: "stale error"});
        await animationFrame();
        expect(".o_erplibre_dev_code_row").toHaveCount(1);
        expect(".o_erplibre_dev_code_row").toHaveAttribute("data-module", "fresh");
        expect(".o_erplibre_dev_code .alert").toHaveCount(0);
    });

    test("the snapshot date shows in the user's timezone", async () => {
        mockTimeZone(-4);
        codeAnswers = [() => ({modules: [], snapshot_date: "2026-10-16 18:03:22", error: false})];
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps(["get_code_info base,example"]);
        expect(".o_erplibre_dev_snapshot_date").toHaveText(/14:03:22/);
    });

    test("without a clipboard, the path shows in the drawer", async () => {
        patchWithCleanup(navigator.clipboard, {
            async writeText() {
                throw new Error("No clipboard");
            },
        });
        await openDrawer();
        await contains(".o_erplibre_dev_current_view .o_erplibre_dev_copy").click();
        await animationFrame();
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_manual_copy input").toHaveValue(
            "/src/base/views/res_partner_views.xml:53"
        );
        await contains(".o_erplibre_dev_current_view .o_erplibre_dev_manual_copy button").click();
        expect(".o_erplibre_dev_manual_copy").toHaveCount(0);
    });

    test("helpers", async () => {
        await openPartners();
        expect(fieldNameOf(queryOne("th[data-name=name]"))).toBe("name");
        expect(targetFromController(getService("action").currentController)).toEqual({
            resModel: "res.partner",
            viewType: "list",
            viewId: false,
            actionId: false,
        });
        expect(targetFromController({action: {type: "ir.actions.client"}})).toBe(null);
        expect(formatIsoDateTime("not a date")).toBe("not a date");
        expect(formatIsoDateTime(false)).toBe("");
    });
});
