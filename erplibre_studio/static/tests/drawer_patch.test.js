// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {waitFor} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
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

// The payload of get_view_info the Views tab needs: a list view of the
// contacts and its action.
function viewInfo(model, viewType) {
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
            file: false,
            file_rel: false,
            line: 0,
            specs: [],
            fields: [],
            groups: [],
            arch: "<list/>",
        },
        views: [],
        combined_arch: "<list/>",
        fields: [],
        modules: ["base"],
        action: false,
        server_actions_allowed: false,
        ide_available: false,
    };
}

beforeEach(() => {
    serverState.debug = "1";
    webModels.ResPartner._views.list = `<list><field name="name"/></list>`;
    defineWebModels();
    onRpc("erplibre.developer", "get_view_info", (args) => viewInfo(args.args[0], args.args[2]));
});

describe.current.tags("desktop");
describe("erplibre_studio developer panel buttons", () => {
    test("the card of the view shown opens the studio on it", async () => {
        await mountWithCleanup(WebClient);
        await getService("action").doAction({
            name: "Partners",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "list"]],
        });
        getService("erplibre_developer").open();
        await waitFor(".o_erplibre_dev_current_view");
        // Labelled buttons in the card, none left in the header.
        expect(".o_erplibre_dev_header .o_erplibre_studio_customize").toHaveCount(0);
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_view_actions .o_erplibre_studio_customize").toHaveText(
            "Customize this view"
        );
        expect(".o_erplibre_dev_current_view .o_erplibre_studio_customize_search").toHaveText(
            "Customize the search view"
        );
        patchWithCleanup(getService("action"), {
            async doAction(action) {
                expect.step(`${action.tag} ${action.params.view_type} ${action.params.view_id}`);
            },
        });
        await contains(".o_erplibre_studio_customize").click();
        await animationFrame();
        expect.verifySteps(["erplibre_studio.editor list 7"]);
        expect(document.body).not.toHaveClass("o_erplibre_dev_open");
    });

    test("the debug menu of a view gathers the studio entries under Studio", async () => {
        await mountWithCleanup(WebClient);
        await getService("action").doAction({
            name: "Partners",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "list"]],
        });
        await contains(".o_debug_manager button").click();
        await waitFor(".dropdown-menu .dropdown-menu_group");
        // Headings and entries in the order of the menu, a heading as « # ».
        const rows = [
            ...document.querySelectorAll(".dropdown-menu .dropdown-menu_group, .dropdown-menu .dropdown-item"),
        ].map((el) => (el.classList.contains("dropdown-menu_group") ? "# " : "") + el.textContent.trim());
        // The Studio section opens the menu with its three entries, and the
        // next heading closes it.
        expect(rows.slice(0, 4)).toEqual([
            "# Studio",
            "Developer panel",
            "Customize this view",
            "Customize the search view",
        ]);
        expect(rows[4]).toMatch(/^# /);
        expect(rows.filter((row) => row === "# Studio")).toHaveLength(1);
        expect(rows.filter((row) => row === "Developer panel")).toHaveLength(1);
        // The entries keep their callbacks.
        patchWithCleanup(getService("action"), {
            async doAction(action) {
                expect.step(`${action.tag} ${action.params.view_type}`);
            },
        });
        await contains(".dropdown-menu .dropdown-item:contains('Customize the search view')").click();
        await animationFrame();
        expect.verifySteps(["erplibre_studio.editor search"]);
    });
});
