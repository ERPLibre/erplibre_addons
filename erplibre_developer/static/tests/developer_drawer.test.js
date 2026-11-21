// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {hover, manuallyDispatchProgrammaticEvent, press, queryAll, queryAllTexts, queryOne, waitFor} from "@odoo/hoot-dom";
import {Deferred, advanceTime, animationFrame, mockTimeZone} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    serverState,
    useTestClientAction,
    webModels,
} from "@web/../tests/web_test_helpers";
import {browser} from "@web/core/browser/browser";
import {WebClient} from "@web/webclient/webclient";
import {
    PREFS_KEY,
    fieldNameOf,
    readPrefs,
    targetFromController,
} from "@erplibre_developer/developer_service";
import {formatIsoDateTime} from "@erplibre_developer/drawer/developer_drawer";
import {SERVER_ACTIONS_OPTION, serverActionsChecks, upgradePending} from "@erplibre_developer/drawer/tabs/actions_tab";
import {
    ARCH_COLOR_MAX_LINES,
    archLines,
    formatRelativeIso,
    formatRelativeServerDateTime,
    isDimmed,
    moduleColor,
    moduleHighlightItems,
    tokenizeArchLine,
    viewHighlightItems,
} from "@erplibre_developer/drawer/common";

// Changes the payload of the next get_view_info calls: (payload) => void.
let patchPayload;

function payload(args) {
    const info = basePayload(args);
    if (patchPayload) {
        patchPayload(info);
    }
    return info;
}

function basePayload(args) {
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

// The repositories of the code sample, with the target each one's
// manifest branch resolves to.
const DIRTY_REPO = "odoo18.0/addons/sample_addons";
const DIRTY_TARGET = "19be4d0ccccccccc";
const CLEAN_REPO = "odoo18.0/odoo";
const CLEAN_TARGET = "a41c9e2aaaaaaaaa";

function repoVals(path, vals) {
    return {
        path,
        state: "conforme",
        state_label: "Matches the manifest",
        branch: "18.0",
        head: CLEAN_TARGET,
        dirty: false,
        revision: false,
        manifest_branch: "18.0",
        target: CLEAN_TARGET,
        ahead: 0,
        behind: 0,
        alignment: "conforme",
        alignment_label: "Matches the manifest",
        error: false,
        ...vals,
    };
}

function repoModule(name, repoPath, repo, vals = {}) {
    return {
        ...codeModule(name),
        path: `/src/${repoPath}/${name}`,
        path_rel: `${repoPath}/${name}`,
        clone: `/src/${repoPath}`,
        clone_rel: repoPath,
        module_rel: name,
        repo,
        repo_source: "snapshot",
        ...vals,
    };
}

/**
 * A get_code_info answer: base and other_module in a sound repository,
 * example (upgrade pending) in a modified one listed after them, orphan in
 * no repository.
 */
function codeSample() {
    const clean = repoVals(CLEAN_REPO, {});
    const dirty = repoVals(DIRTY_REPO, {
        state: "sale",
        state_label: "Modified",
        branch: "dev/sample",
        head: "7c03b1f0aaaaaaaa",
        dirty: true,
        target: DIRTY_TARGET,
        ahead: 2,
        alignment: "en_avance",
        alignment_label: "Ahead of the manifest",
    });
    return {
        modules: [
            repoModule("base", CLEAN_REPO, clean, {installed_version: "18.0.1.3", code_version: "18.0.1.3"}),
            repoModule("other_module", CLEAN_REPO, clean),
            repoModule("example", DIRTY_REPO, dirty, {code_version: "18.0.1.1.0"}),
            {...codeModule("orphan"), path: "/elsewhere/orphan", path_rel: "elsewhere/orphan"},
        ],
        snapshot_date: false,
        error: false,
    };
}

/** get_repo_details of the modified repository: 23 files, 20 listed. */
function repoDetailsSample() {
    return {
        repo: DIRTY_REPO,
        dirty_count: 23,
        dirty_files: Array.from({length: 20}, (_, i) => ({status: " M", path: `sample_module/file_${i}.py`})),
        commits: [],
        target: DIRTY_TARGET,
        error: false,
    };
}

// The answer of get_repo_details, by repository: {path: () => answer}.
let repoAnswers;

// The answer of get_recent_runs: () => runs.
let runsAnswer;

beforeEach(() => {
    serverState.debug = "1";
    webModels.ResPartner._views.list = `<list><field name="name"/></list>`;
    defineWebModels();
    codeAnswers = [];
    repoAnswers = {};
    runsAnswer = () => [];
    patchPayload = null;
    browser.localStorage.removeItem(PREFS_KEY);
    onRpc("erplibre.developer", "get_view_info", (args) => {
        expect.step(`get_view_info ${args.args[0]} ${args.args[2]}`);
        return payload(args);
    });
    onRpc("erplibre.developer", "get_code_info", (args) => {
        expect.step(`get_code_info ${args.args[0].join(",")}`);
        const answer = codeAnswers.shift();
        return answer ? answer(args) : {modules: [], snapshot_date: false, error: false};
    });
    onRpc("erplibre.developer", "get_repo_details", (args) => {
        expect.step(`get_repo_details ${args.args[0]} ${args.kwargs.target}`);
        const answer = repoAnswers[args.args[0]];
        return answer ? answer() : {dirty_count: 0, dirty_files: [], commits: [], target: false, error: false};
    });
    onRpc("erplibre.developer", "get_recent_runs", () => runsAnswer());
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
        // The rows open on their specs, collapsed at first.
        expect(".o_erplibre_dev_specs").toHaveCount(0);
        await contains(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_view_head").click();
        expect(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_view_head").toHaveAttribute("aria-expanded", "true");
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
        expect(".o_erplibre_dev_field_row[data-field=name]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_field_card").toHaveAttribute("data-field", "name");
        expect("th[data-name=name]").toHaveClass("o_erplibre_dev_highlight");
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

    test("Open in IDE shows next to each source location when the IDE is available", async () => {
        onRpc("erplibre.developer", "action_open_in_ide", (args) => {
            expect.step(`action_open_in_ide ${args.args.join(":")}`);
            return true;
        });
        patchPayload = (info) => {
            info.ide_available = true;
        };
        await openDrawer();
        // The current-view card.
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_ide").toHaveAttribute("aria-label", "Open in IDE");
        // Both buttons are the drawer's 32px icon buttons, not bare glyphs.
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_location .o_erplibre_dev_icon_btn").toHaveCount(2);
        await contains(".o_erplibre_dev_current_view .o_erplibre_dev_ide").click();
        expect.verifySteps(["action_open_in_ide /src/base/views/res_partner_views.xml:53"]);
        // An open view row.
        await contains(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_view_head").click();
        await contains(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_ide").click();
        expect.verifySteps(["action_open_in_ide /src/example/views/views.xml:4"]);
        // Each step of the origin chain of the field card.
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        await contains(".o_erplibre_dev_field_row[data-field=name]").click();
        expect(".o_erplibre_dev_field_card .o_erplibre_dev_step .o_erplibre_dev_ide").toHaveCount(2);
        await contains(".o_erplibre_dev_field_card .o_erplibre_dev_step:eq(1) .o_erplibre_dev_ide").click();
        expect.verifySteps(["action_open_in_ide /src/example/models/res_partner.py:10"]);
    });

    test("without the IDE, the source locations have no Open in IDE button", async () => {
        await openDrawer();
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_location").toHaveCount(1);
        expect(".o_erplibre_dev_ide").toHaveCount(0);
    });

    test("the filter and the open rows survive a switch of tab", async () => {
        await openDrawer();
        await contains(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_view_head").click();
        await contains(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_arch_toggle").click();
        expect(".o_erplibre_dev_arch").toHaveCount(1);
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        await contains(".o_erplibre_dev_filter").edit("nothing matches");
        expect(".o_erplibre_dev_field_row").toHaveCount(0);
        await contains(".o_erplibre_dev_tabs [data-tab=views]").click();
        expect(".o_erplibre_dev_arch").toHaveCount(1);
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        expect(".o_erplibre_dev_filter").toHaveValue("nothing matches");
        expect(".o_erplibre_dev_field_row").toHaveCount(0);
    });

    test("the recent commits of a module show in the actions tab", async () => {
        onRpc("erplibre.developer", "get_module_commits", (args) => {
            expect.step(`get_module_commits ${args.args[0]}`);
            return {
                commits: [
                    {
                        sha: "0123456789abcdef",
                        subject: "Sample subject",
                        author: "Sample author",
                        date: "2026-01-02T03:04:05+00:00",
                    },
                ],
                error: false,
            };
        });
        codeAnswers = [() => ({modules: [codeModule("example")], snapshot_date: false, error: false})];
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=actions]").click();
        await contains(".o_erplibre_dev_action_row[data-module=example] button[title='Recent commits']").click();
        await animationFrame();
        expect.verifySteps(["get_module_commits example"]);
        expect(".o_erplibre_dev_action_row[data-module=example] .o_erplibre_dev_commits code").toHaveText(
            "0123456789ab"
        );
        expect(".o_erplibre_dev_action_row[data-module=base] .o_erplibre_dev_commits").toHaveCount(0);
        // The Code tab shows the commits of a repository, not of a module.
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps(["get_code_info base,example"]);
        expect(".o_erplibre_dev_code_row[data-module=example]").toHaveCount(1);
        expect(".o_erplibre_dev_code .o_erplibre_dev_commits").toHaveCount(0);
    });

    test("the header names its buttons, the tabs count their items", async () => {
        await openDrawer();
        expect(".o_erplibre_dev_header button:not([aria-label])").toHaveCount(0);
        expect(".o_erplibre_dev_inspect").toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_dev_follow").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_width").toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_dev_view_title code").toHaveCount(3);
        expect(".o_erplibre_dev_tabs[role=tablist] [role=tab]").toHaveCount(4);
        expect("[data-tab=views]").toHaveAttribute("aria-selected", "true");
        expect("[data-tab=fields]").toHaveAttribute("aria-selected", "false");
        expect("[data-tab=views] .o_erplibre_dev_tab_count").toHaveText("2");
        expect("[data-tab=fields] .o_erplibre_dev_tab_count").toHaveText("1");
        expect("[data-tab=code] .o_erplibre_dev_tab_count").toHaveText("2");
        expect("[data-tab=actions] .o_erplibre_dev_tab_count").toHaveCount(0);
        expect("#o_erplibre_dev_panel").toHaveAttribute("aria-labelledby", "o_erplibre_dev_tab_views");
        // The arrow keys move along the tabs.
        queryOne("[data-tab=views]").focus();
        await press("ArrowRight");
        await animationFrame();
        expect("[data-tab=fields]").toHaveAttribute("aria-selected", "true");
        expect("[data-tab=fields]").toBeFocused();
        await press("ArrowLeft");
        await animationFrame();
        expect("[data-tab=views]").toHaveAttribute("aria-selected", "true");
    });

    test("inspect shows a banner above the page, Escape and Quit stop it", async () => {
        await openDrawer();
        expect(".o_erplibre_dev_inspect_banner").toHaveCount(0);
        await contains(".o_erplibre_dev_inspect").click();
        expect(".o_erplibre_dev_inspect").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_inspect_banner[role=status]").toHaveCount(1);
        await press("Escape");
        await animationFrame();
        expect(document.body).not.toHaveClass("o_erplibre_dev_inspecting");
        expect(".o_erplibre_dev_inspect_banner").toHaveCount(0);
        // The drawer stays open: Escape only left the inspect mode.
        expect(".o_erplibre_dev_drawer").toHaveCount(1);
        await contains(".o_erplibre_dev_inspect").click();
        await contains(".o_erplibre_dev_inspect_quit").click();
        expect(document.body).not.toHaveClass("o_erplibre_dev_inspecting");
        expect(".o_erplibre_dev_inspect_banner").toHaveCount(0);
    });

    test("the module filter dims the other modules in every tab", async () => {
        await openDrawer();
        expect(".o_erplibre_dev_module_chip").toHaveCount(3);
        expect(".o_erplibre_dev_module_all").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_module_chip[data-module=example] .o_erplibre_dev_dot").toHaveClass(
            `o_tag_color_${moduleColor("example")}`
        );
        await contains(".o_erplibre_dev_module_chip[data-module=example]").click();
        expect(".o_erplibre_dev_module_chip[data-module=example]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_module_all").toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_dev_current_view").toHaveClass("o_erplibre_dev_dimmed");
        expect(".o_erplibre_dev_view_row:eq(0)").toHaveClass("o_erplibre_dev_dimmed");
        expect(".o_erplibre_dev_view_row:eq(1)").not.toHaveClass("o_erplibre_dev_dimmed");
        // Dimmed, not hidden: the order of the views stays whole.
        expect(".o_erplibre_dev_view_row").toHaveCount(2);
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        // Defined in base, overridden by example.
        expect(".o_erplibre_dev_field_row[data-field=name]").not.toHaveClass("o_erplibre_dev_dimmed");
        await contains(".o_erplibre_dev_tabs [data-tab=actions]").click();
        expect(".o_erplibre_dev_action_row[data-module=base]").toHaveClass("o_erplibre_dev_dimmed");
        expect(".o_erplibre_dev_action_row[data-module=example]").not.toHaveClass("o_erplibre_dev_dimmed");
        // Picking the chip again clears the filter, « All » too.
        await contains(".o_erplibre_dev_module_chip[data-module=example]").click();
        expect(".o_erplibre_dev_dimmed").toHaveCount(0);
        await contains(".o_erplibre_dev_module_chip[data-module=base]").click();
        expect(".o_erplibre_dev_action_row[data-module=example]").toHaveClass("o_erplibre_dev_dimmed");
        await contains(".o_erplibre_dev_module_all").click();
        expect(".o_erplibre_dev_dimmed").toHaveCount(0);
    });

    test("width, density and follow are kept in this browser", async () => {
        await openDrawer();
        expect(document.body).not.toHaveClass("o_erplibre_dev_wide");
        await contains(".o_erplibre_dev_width").click();
        expect(document.body).toHaveClass("o_erplibre_dev_wide");
        expect(".o_erplibre_dev_width").toHaveAttribute("aria-pressed", "true");
        await contains(".o_erplibre_dev_density_compact").click();
        expect(".o_erplibre_dev_drawer").toHaveClass("o_erplibre_dev_compact");
        expect(".o_erplibre_dev_density_compact").toHaveAttribute("aria-pressed", "true");
        await contains(".o_erplibre_dev_follow").click();
        expect(JSON.parse(browser.localStorage.getItem(PREFS_KEY))).toEqual({
            follow: false,
            wide: true,
            density: "compact",
        });
        await contains(".o_erplibre_dev_close").click();
        expect(document.body).not.toHaveClass("o_erplibre_dev_wide");
    });

    test("the preferences read back, and default without a storage", async () => {
        browser.localStorage.setItem(PREFS_KEY, JSON.stringify({wide: true, density: "other", follow: 3}));
        expect(readPrefs()).toEqual({follow: true, wide: true, density: "comfortable"});
        await openDrawer();
        expect(document.body).toHaveClass("o_erplibre_dev_wide");
        expect(".o_erplibre_dev_drawer").not.toHaveClass("o_erplibre_dev_compact");
        browser.localStorage.setItem(PREFS_KEY, "not json");
        expect(readPrefs()).toEqual({follow: true, wide: false, density: "comfortable"});
        patchWithCleanup(browser.localStorage, {
            getItem() {
                throw new Error("Blocked storage");
            },
            setItem() {
                throw new Error("Blocked storage");
            },
        });
        expect(readPrefs()).toEqual({follow: true, wide: false, density: "comfortable"});
        // A storage that refuses to write leaves the drawer working.
        await contains(".o_erplibre_dev_width").click();
        expect(document.body).not.toHaveClass("o_erplibre_dev_wide");
    });

    test("unpinned, the drawer stays on its view and turns Inspect off elsewhere", async () => {
        webModels.ResPartner._views.form = `<form><field name="name"/></form>`;
        await openDrawer();
        await contains(".o_erplibre_dev_follow").click();
        expect(".o_erplibre_dev_follow").toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_dev_offview").toHaveCount(0);
        await getService("action").doAction({
            name: "Partner",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "form"]],
        });
        await animationFrame();
        // No new introspection: the drawer still describes the list.
        expect.verifySteps([]);
        expect(".o_erplibre_dev_view_title").toHaveText(/list/);
        expect(".o_erplibre_dev_offview").toHaveCount(1);
        expect(".o_erplibre_dev_inspect").toHaveAttribute("disabled");
        await hover(".o_erplibre_dev_view_row:eq(1)");
        expect(".o_erplibre_dev_highlight").toHaveCount(0);
        expect(".o_erplibre_dev_tags").toHaveCount(0);
        await contains(".o_erplibre_dev_follow_again").click();
        await animationFrame();
        expect.verifySteps(["get_view_info res.partner form"]);
        expect(".o_erplibre_dev_offview").toHaveCount(0);
        expect(".o_erplibre_dev_follow").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_inspect").not.toHaveAttribute("disabled");
        // Following, the drawer reloads at each new view.
        await getService("action").doAction({
            name: "Partners",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "list"]],
        });
        await animationFrame();
        expect.verifySteps(["get_view_info res.partner list"]);
    });

    test("following, a page without a view empties the drawer, a new view drops the field mode", async () => {
        const clientAction = useTestClientAction();
        await openDrawer();
        await contains(".o_erplibre_dev_views_by_field").click();
        expect(".o_erplibre_dev_views_by_field").toHaveAttribute("aria-pressed", "true");
        await contains(".o_erplibre_dev_inspect").click();
        expect(document.body).toHaveClass("o_erplibre_dev_inspecting");
        // A client action: no view to describe, Inspect stops and stays off.
        await getService("action").doAction(clientAction);
        await waitFor(".o_erplibre_dev_error");
        expect.verifySteps([]);
        expect(".test_client_action").toHaveCount(1);
        expect(".o_erplibre_dev_error").toHaveText("This page shows no view.");
        expect(".o_erplibre_dev_views").toHaveCount(0);
        expect(document.body).not.toHaveClass("o_erplibre_dev_inspecting");
        expect(".o_erplibre_dev_inspect").toHaveAttribute("disabled");
        // Back on a view: the drawer describes it, the field mode is off.
        await getService("action").doAction({
            name: "Partners",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "list"]],
        });
        await waitFor(".o_erplibre_dev_view_row");
        expect.verifySteps(["get_view_info res.partner list"]);
        expect(".o_erplibre_dev_views_all").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_view_row").toHaveCount(2);
        expect(".o_erplibre_dev_inspect").not.toHaveAttribute("disabled");
    });

    test("hovering a view outlines its fields, buttons and pages with a tag", async () => {
        webModels.ResPartner._views.form = `
            <form>
                <header><button name="action_sample" type="object" string="Sample"/></header>
                <sheet>
                    <notebook>
                        <page name="extra" string="Extra"><field name="name"/></page>
                    </notebook>
                </sheet>
            </form>`;
        patchPayload = (info) => {
            Object.assign(info.views[1], {
                specs: [
                    {
                        expr: "//page[@name='extra']",
                        position: "inside",
                        attributes: [],
                        content: [{tag: "field", name: "name", string: false}],
                        content_more: 0,
                    },
                    {
                        expr: "//header",
                        position: "inside",
                        attributes: [],
                        content: [{tag: "button", name: "action_sample", string: "Sample"}],
                        content_more: 0,
                    },
                ],
                fields: ["name"],
            });
        };
        await mountWithCleanup(WebClient);
        await getService("action").doAction({
            name: "Partner",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "form"]],
        });
        getService("erplibre_developer").open();
        await animationFrame();
        expect.verifySteps(["get_view_info res.partner form"]);
        await contains(".o_erplibre_dev_view_row:eq(1)").hover();
        expect(".o_notebook_headers .nav-link[name=extra]").toHaveClass("o_erplibre_dev_highlight");
        expect("button[name=action_sample]").toHaveClass("o_erplibre_dev_highlight");
        expect(".o_field_widget[name=name]").toHaveClass("o_erplibre_dev_highlight");
        expect(queryAllTexts(".o_erplibre_dev_tags .o_erplibre_dev_tag")).toEqual([
            "extra · inside · example",
            "name · added · example",
            "action_sample · added · example",
        ]);
        await hover(".o_erplibre_dev_header");
        expect(".o_erplibre_dev_highlight").toHaveCount(0);
        expect(".o_erplibre_dev_tags").toHaveCount(0);
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        await hover(".o_erplibre_dev_field_row[data-field=name]");
        expect(queryAllTexts(".o_erplibre_dev_tag")).toEqual(["name · char · base +1"]);
        // Closing the drawer removes the outline and the tags.
        getService("erplibre_developer").highlight(["name"]);
        expect(".o_erplibre_dev_tags").toHaveCount(1);
        getService("erplibre_developer").close();
        await animationFrame();
        expect(".o_erplibre_dev_highlight").toHaveCount(0);
        expect(".o_erplibre_dev_tags").toHaveCount(0);
    });

    test("the status bar shows the version and the snapshot date", async () => {
        mockTimeZone(-4);
        patchPayload = (info) => {
            info.snapshot_date = "2026-10-16 18:03:22";
        };
        await openDrawer();
        expect(".o_erplibre_dev_status").toHaveText(/^Odoo /);
        expect(".o_erplibre_dev_footer_snapshot").toHaveText(/14:03:22/);
        expect(".o_erplibre_dev_density[role=group] button").toHaveCount(2);
    });

    test("view and module helpers", async () => {
        const color = moduleColor("sample_module");
        expect(color).toBe(moduleColor("sample_module"));
        expect(color >= 1 && color <= 11).toBe(true);
        const colors = new Set(["a", "b", "c", "d", "e", "f"].map(moduleColor));
        expect(colors.size > 1).toBe(true);
        expect(isDimmed(null, ["base"])).toBe(false);
        expect(isDimmed("base", ["base", "mail"])).toBe(false);
        expect(isDimmed("sale", ["base", false])).toBe(true);
        const items = viewHighlightItems({
            module: "sample",
            fields: ["partner_id", "name"],
            specs: [
                {expr: "//div[@name='button_box']", position: "inside", content: []},
                {expr: "//group[@name='main']//field[@name='name']", position: "after", content: []},
                {expr: "//div[@name='other']", position: "inside", content: [{tag: "group", name: "x"}]},
            ],
        });
        expect(items.map((i) => [i.kind, i.name, i.label])).toEqual([
            ["button_box", "button_box", "button_box · inside · sample"],
            ["field", "name", "name · after · sample"],
            ["field", "partner_id", "partner_id · sample"],
        ]);
    });

    test("the views tab: the card, the rail, the specs and a coloured arch", async () => {
        patchPayload = (info) => {
            info.action = {
                id: 3,
                name: "Sample action",
                type: "ir.actions.act_window",
                xml_id: "sample_module.sample_action",
                module: "sample_module",
            };
            Object.assign(info.views[1], {
                groups: ["Sample / Group"],
                specs: [
                    {
                        expr: "//field[@name='name']",
                        position: "after",
                        attributes: [],
                        content: [
                            {tag: "field", name: "sample_field", string: false},
                            {tag: "page", name: "sample_page", string: "Sample page"},
                        ],
                        content_more: 2,
                    },
                    {
                        expr: "//field[@name='name']",
                        position: "attributes",
                        attributes: ["readonly", "widget"],
                        content: [],
                        content_more: 0,
                    },
                    {expr: "//div[@name='old']", position: "replace", attributes: [], content: [], content_more: 0},
                ],
                arch: [
                    "<data>",
                    `  <xpath expr="//field[@name='name']" position="after">`,
                    "    <!-- sample -->",
                    "  </xpath>",
                    "</data>",
                ].join("\n"),
            });
        };
        await openDrawer();
        // The card of the view shown, and its action.
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_facts dd").toHaveCount(5);
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_module_tag:first").toHaveText("base");
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_module_tag:first").toHaveClass(
            `o_tag_color_${moduleColor("base")}`
        );
        expect(".o_erplibre_dev_action code").toHaveText("sample_module.sample_action");
        expect(".o_erplibre_dev_action .o_erplibre_dev_module_tag").toHaveText("sample_module");
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_copy").toHaveAttribute("aria-label", "Copy the path");
        // The rail: numbered, collapsed, one meta line each.
        expect(queryAllTexts(".o_erplibre_dev_rail_n")).toEqual(["1", "2"]);
        expect(".o_erplibre_dev_view_row:eq(0) .o_erplibre_dev_shown").toHaveCount(1);
        expect(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_shown").toHaveCount(0);
        expect(queryAllTexts(".o_erplibre_dev_spec_count")).toEqual(["base", "3 xpath"]);
        expect(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_view_meta").toHaveText(
            "priority 20 · extension · groups: Sample / Group"
        );
        expect(".o_erplibre_dev_views_count").toHaveText("2 views");
        expect(".o_erplibre_dev_view_body").toHaveCount(0);
        await contains(".o_erplibre_dev_toggle_all").click();
        expect(".o_erplibre_dev_view_body").toHaveCount(2);
        expect(".o_erplibre_dev_toggle_all").toHaveText("Collapse all");
        expect(".o_erplibre_dev_view_row:eq(0) .o_erplibre_dev_view_body").toHaveText(/Primary view: no xpath/);
        expect(queryAllTexts(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_spec_note")).toEqual([
            "adds: field sample_field, page Sample page, 2 more",
            "attributes: readonly, widget",
            "removes the node",
        ]);
        expect(queryAllTexts(".o_erplibre_dev_position")).toEqual(["after", "attributes", "replace"]);
        expect(".o_erplibre_dev_position:eq(1)").toHaveAttribute("data-position", "attributes");
        // The arch of a view, coloured by token.
        await contains(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_arch_toggle").click();
        expect(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_arch_toggle").toHaveAttribute("aria-expanded", "true");
        expect(".o_erplibre_dev_arch[role=region]").toHaveAttribute(
            "aria-label",
            "Arch of example.view_partner_tree_extension"
        );
        expect(".o_erplibre_dev_arch .o_erplibre_dev_line").toHaveCount(5);
        expect(".o_erplibre_dev_arch .o_erplibre_dev_line:eq(1) .o_erplibre_dev_tok_tag").toHaveText("xpath");
        expect(queryAllTexts(".o_erplibre_dev_arch .o_erplibre_dev_line:eq(1) .o_erplibre_dev_tok_attr")).toEqual([
            "expr",
            "position",
        ]);
        expect(queryAllTexts(".o_erplibre_dev_arch .o_erplibre_dev_line:eq(1) .o_erplibre_dev_tok_value")).toEqual([
            `"//field[@name='name']"`,
            `"after"`,
        ]);
        expect(".o_erplibre_dev_arch .o_erplibre_dev_tok_comment").toHaveText("<!-- sample -->");
        expect(queryOne(".o_erplibre_dev_arch .o_erplibre_dev_line:eq(1)").textContent).toBe(
            `  <xpath expr="//field[@name='name']" position="after">`
        );
        await contains(".o_erplibre_dev_toggle_all").click();
        expect(".o_erplibre_dev_view_body").toHaveCount(0);
        expect(".o_erplibre_dev_toggle_all").toHaveText("Expand all");
    });

    test("touching this field lists the views of a field, Inspect picks it there", async () => {
        patchPayload = (info) => {
            info.views[0].fields = ["email"];
            info.modules = ["base", "example", "other_module"];
        };
        await openDrawer();
        expect(".o_erplibre_dev_field_picker").toHaveCount(0);
        await contains(".o_erplibre_dev_views_by_field").click();
        expect(".o_erplibre_dev_views_by_field").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_views_all").toHaveAttribute("aria-pressed", "false");
        expect(queryAllTexts(".o_erplibre_dev_field_chip")).toEqual(["email", "name"]);
        // No field selected: the first one the views name.
        expect(".o_erplibre_dev_field_chip[data-field=email]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_view_row").toHaveCount(1);
        expect(".o_erplibre_dev_views_count").toHaveText("1 of 2 touch email");
        await contains(".o_erplibre_dev_field_chip[data-field=name]").click();
        expect(".o_erplibre_dev_view_row").toHaveCount(1);
        // The rank in the order of application stays.
        expect(".o_erplibre_dev_view_row .o_erplibre_dev_rail_n").toHaveText("2");
        expect(".o_erplibre_dev_view_row").toHaveAttribute("data-view-id", "8");
        // Inspect selects the field clicked and stays on the views.
        await contains(".o_erplibre_dev_field_chip[data-field=email]").click();
        await contains(".o_erplibre_dev_inspect").click();
        await contains("th[data-name=name]").click();
        await animationFrame();
        expect("[data-tab=views]").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_dev_field_chip[data-field=name]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_view_row").toHaveAttribute("data-view-id", "8");
        await contains(".o_erplibre_dev_views_all").click();
        expect(".o_erplibre_dev_view_row").toHaveCount(2);
        expect(".o_erplibre_dev_field_picker").toHaveCount(0);
        // A module of the page without a view of its own.
        expect(".o_erplibre_dev_module_note").toHaveCount(0);
        await contains(".o_erplibre_dev_module_chip[data-module=other_module]").click();
        expect(".o_erplibre_dev_module_note").toHaveText(/^No view of other_module on this page/);
    });

    test("focusing a view highlights what it touches", async () => {
        await openDrawer();
        const head = queryOne(".o_erplibre_dev_view_row:eq(1) .o_erplibre_dev_view_head");
        await manuallyDispatchProgrammaticEvent(head, "focus");
        expect("th[data-name=name]").toHaveClass("o_erplibre_dev_highlight");
        await manuallyDispatchProgrammaticEvent(head, "blur");
        expect(".o_erplibre_dev_highlight").toHaveCount(0);
    });

    test("the combined arch: node origins, search, module filter", async () => {
        const line = (depth, text, origin, attrOrigin = []) => ({
            depth,
            text,
            origin,
            view_id: origin === "base" ? 7 : 8,
            attr_origin: attrOrigin,
            attr_view_ids: attrOrigin.length ? [8] : [],
        });
        patchPayload = (info) => {
            info.combined_arch = '<list>\n  <field name="name" readonly="1"/>\n  <field name="email"/>\n</list>';
            info.combined_lines = [
                line(0, "<list>", "base"),
                line(1, '<field name="name" readonly="1"/>', "base", ["example"]),
                line(1, '<field name="email"/>', "example"),
                line(0, "</list>", "base"),
            ];
        };
        await openDrawer();
        expect(".o_erplibre_dev_combined").toHaveCount(0);
        expect(".o_erplibre_dev_toggle_combined").toHaveAttribute("aria-expanded", "false");
        await contains(".o_erplibre_dev_toggle_combined").click();
        expect(".o_erplibre_dev_toggle_combined").toHaveAttribute("aria-expanded", "true");
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line").toHaveCount(4);
        expect(".o_erplibre_dev_arch_count").toHaveText("4 lines");
        expect(".o_erplibre_dev_origin_switch").toHaveAttribute("aria-checked", "true");
        expect(queryAllTexts(".o_erplibre_dev_legend [data-module]")).toEqual(["base", "example"]);
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line:eq(1) .o_erplibre_dev_bar_origin").toHaveClass(
            `o_tag_color_${moduleColor("base")}`
        );
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line:eq(1) .o_erplibre_dev_bar_attr").toHaveClass(
            `o_tag_color_${moduleColor("example")}`
        );
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line:eq(0) .o_erplibre_dev_bar_attr").not.toHaveClass("o_tag");
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line:eq(1)").toHaveAttribute(
            "title",
            "Node added by base · attributes changed by example"
        );
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line:eq(2)").toHaveAttribute("data-origin", "example");
        // Indented by its depth.
        const code = queryOne(".o_erplibre_dev_combined .o_erplibre_dev_line:eq(2) .o_erplibre_dev_line_code");
        expect(code.textContent).toBe('  <field name="email"/>');
        await contains(".o_erplibre_dev_arch_query").edit("email");
        expect(".o_erplibre_dev_match").toHaveCount(1);
        expect(".o_erplibre_dev_arch_count").toHaveText("1 line contains “email”");
        await contains(".o_erplibre_dev_arch_query").edit("FIELD");
        expect(".o_erplibre_dev_match").toHaveCount(2);
        expect(".o_erplibre_dev_arch_count").toHaveText("2 lines contain “FIELD”");
        await contains(".o_erplibre_dev_arch_query").edit("nothing here");
        expect(".o_erplibre_dev_match").toHaveCount(0);
        expect(".o_erplibre_dev_arch_count").toHaveText("No line contains “nothing here”");
        // The module filter dims the lines no view of the module touched.
        await contains(".o_erplibre_dev_module_chip[data-module=example]").click();
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line.o_erplibre_dev_dimmed").toHaveCount(2);
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line:eq(1)").not.toHaveClass("o_erplibre_dev_dimmed");
        // The search and the switch survive a switch of tab.
        await contains(".o_erplibre_dev_origin_switch").click();
        expect(".o_erplibre_dev_origin_switch").toHaveAttribute("aria-checked", "false");
        expect(".o_erplibre_dev_bar").toHaveCount(0);
        expect(".o_erplibre_dev_legend").toHaveCount(0);
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        await contains(".o_erplibre_dev_tabs [data-tab=views]").click();
        expect(".o_erplibre_dev_arch_query").toHaveValue("nothing here");
        expect(".o_erplibre_dev_bar").toHaveCount(0);
    });

    test("without node origins, the combined arch shows plain", async () => {
        patchPayload = (info) => {
            info.view = false;
            info.combined_lines = false;
        };
        await openDrawer();
        // No view record: the card says so, and stays.
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_no_view").toHaveCount(1);
        await contains(".o_erplibre_dev_toggle_combined").click();
        expect(".o_erplibre_dev_combined .o_erplibre_dev_line").toHaveCount(1);
        expect(".o_erplibre_dev_arch_count").toHaveText("1 line");
        expect(".o_erplibre_dev_origin_switch").toHaveCount(0);
        expect(".o_erplibre_dev_bar").toHaveCount(0);
        expect(".o_erplibre_dev_combined .o_erplibre_dev_tok_tag").toHaveCount(3);
        await contains(".o_erplibre_dev_module_chip[data-module=example]").click();
        expect(".o_erplibre_dev_combined .o_erplibre_dev_dimmed").toHaveCount(0);
    });

    test("the copy button says when the path is copied", async () => {
        patchWithCleanup(navigator.clipboard, {
            async writeText(text) {
                expect.step(`copy ${text}`);
            },
        });
        await openDrawer();
        await contains(".o_erplibre_dev_current_view .o_erplibre_dev_copy").click();
        await animationFrame();
        expect.verifySteps(["copy /src/base/views/res_partner_views.xml:53"]);
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_copy").toHaveAttribute("aria-label", "Path copied");
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_copy .fa-check").toHaveCount(1);
        await advanceTime(2000);
        await animationFrame();
        expect(".o_erplibre_dev_current_view .o_erplibre_dev_copy").toHaveAttribute("aria-label", "Copy the path");
    });

    test("arch tokens join back into their line", async () => {
        const line = `  <field name="a" string='B &amp; c'/> text = "x" <!-- note --> < odd />`;
        const tokens = tokenizeArchLine(line);
        expect(tokens.map((token) => token.text).join("")).toBe(line);
        expect(tokens.filter((token) => token.kind === "tag").map((token) => token.text)).toEqual(["field"]);
        expect(tokens.filter((token) => token.kind === "attr").map((token) => token.text)).toEqual(["name", "string"]);
        expect(tokens.filter((token) => token.kind === "value").map((token) => token.text)).toEqual([
            '"a"',
            "'B &amp; c'",
        ]);
        expect(tokens.find((token) => token.kind === "comment").text).toBe("<!-- note -->");
        expect(tokenizeArchLine("")).toEqual([]);
        expect(archLines(["<a/>", "b"]).map((l) => [l.n, l.text])).toEqual([
            [1, "<a/>"],
            [2, "b"],
        ]);
        const long = archLines(new Array(ARCH_COLOR_MAX_LINES + 1).fill("<a/>"));
        expect(long[0].tokens).toEqual([{text: "<a/>", kind: "text"}]);
    });

    test("the fields tab: kind chips, search, rows and the card", async () => {
        patchPayload = (info) => {
            const name = info.fields[0];
            Object.assign(name, {
                store: true,
                readonly: false,
                required: true,
                company_dependent: false,
                view_ids: [7, 8],
            });
            name.defined_in.source = "fields.Char(index=True)";
            name.overrides.push({
                kind: "onchange",
                module: "example",
                method: "_onchange_name",
                file: "/src/example/models/res_partner.py",
                file_rel: "example/models/res_partner.py",
                line: 30,
            });
            info.fields.push(
                {
                    name: "parent_id",
                    string: "Related company",
                    type: "many2one",
                    relation: "res.partner",
                    related: false,
                    inherited_model: false,
                    manual: false,
                    store: true,
                    readonly: false,
                    required: false,
                    company_dependent: true,
                    defined_in: {module: false, core: true, file: false, file_rel: false, line: 0, attrs: []},
                    overrides: [],
                    override_modules: [],
                    view_ids: [],
                },
                {
                    name: "x_sample_level",
                    string: "Sample level",
                    type: "selection",
                    relation: false,
                    related: false,
                    inherited_model: false,
                    manual: true,
                    store: false,
                    readonly: false,
                    required: false,
                    company_dependent: false,
                    defined_in: false,
                    overrides: [],
                    override_modules: [],
                    view_ids: [8],
                }
            );
        };
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        // The kind chips count every field of the view.
        expect(queryAllTexts(".o_erplibre_dev_field_filter .o_erplibre_dev_filter_count")).toEqual([
            "3",
            "1",
            "1",
            "1",
        ]);
        expect(".o_erplibre_dev_field_filter[data-filter=overridden]").toHaveText(/^Overridden/);
        expect(".o_erplibre_dev_field_filter[data-filter=all]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_field_row").toHaveCount(3);
        await contains(".o_erplibre_dev_field_filter[data-filter=relational]").click();
        expect(".o_erplibre_dev_field_filter[data-filter=relational]").toHaveAttribute("aria-pressed", "true");
        expect(queryAllTexts(".o_erplibre_dev_field_row .o_erplibre_dev_field_name")).toEqual(["parent_id"]);
        await contains(".o_erplibre_dev_field_filter[data-filter=all]").click();
        // The search takes the modules too; its button clears it and stays
        // out of the name of the input.
        expect(".o_erplibre_dev_filter").toHaveAttribute("aria-label", "Filter by field, label or module");
        expect(queryOne(".o_erplibre_dev_filter").closest("label")).toBe(null);
        expect(".o_erplibre_dev_filter_clear").toHaveCount(0);
        await contains(".o_erplibre_dev_filter").edit("bas");
        expect(queryAllTexts(".o_erplibre_dev_field_row .o_erplibre_dev_field_name")).toEqual(["name"]);
        await contains(".o_erplibre_dev_filter").edit("exam");
        expect(queryAllTexts(".o_erplibre_dev_field_row .o_erplibre_dev_field_name")).toEqual([
            "name",
            "x_sample_level",
        ]);
        await contains(".o_erplibre_dev_filter_clear").click();
        expect(".o_erplibre_dev_filter").toHaveValue("");
        expect(".o_erplibre_dev_field_row").toHaveCount(3);
        expect(".o_erplibre_dev_filter_clear").toHaveCount(0);

        // A row: its modules as dots, its overrides counted.
        const row = ".o_erplibre_dev_field_row[data-field=name]";
        expect(`${row} .o_erplibre_dev_dot`).toHaveCount(2);
        expect(`${row} .o_erplibre_dev_dot:eq(1)`).toHaveClass(`o_tag_color_${moduleColor("example")}`);
        expect(`${row} .o_erplibre_dev_over_count`).toHaveText(/^\+2\s*overrides$/);
        expect(`${row} .o_erplibre_dev_defined_in`).toHaveText("Defined in base");
        // The modules of the dots in words, for a screen reader.
        expect(`${row} .o_erplibre_dev_modules_text`).toHaveText("Modules: base, example");
        expect(".o_erplibre_dev_field_row[data-field=parent_id] .o_erplibre_dev_over_count").toHaveCount(0);

        // Nothing selected: the card shows the first field listed.
        expect(".o_erplibre_dev_field_card").toHaveAttribute("data-field", "name");
        expect(row).toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_field_card h3").toHaveText("Name");
        expect(queryAllTexts(".o_erplibre_dev_field_card .o_erplibre_dev_flag")).toEqual(["required"]);
        expect(".o_erplibre_dev_chain_note").toHaveText("3 steps · MRO order");
        expect(queryAllTexts(".o_erplibre_dev_step .o_erplibre_dev_kind")).toEqual([
            "Definition",
            "Definition",
            "Onchange",
        ]);
        expect(queryAllTexts(".o_erplibre_dev_step .o_erplibre_dev_module_tag")).toEqual(["base", "example", "example"]);
        // The declaration as written when the server read it, else its
        // attributes by name.
        expect(queryAllTexts(".o_erplibre_dev_step_code")).toEqual([
            "fields.Char(index=True)",
            "fields.Char(tracking=…)",
            "_onchange_name",
        ]);
        expect(".o_erplibre_dev_step:eq(2) .o_erplibre_dev_location code").toHaveText(
            "example/models/res_partner.py:30"
        );
        // The views that touch it: the root by its arch, the extension by its spec.
        expect(".o_erplibre_dev_field_view").toHaveCount(2);
        expect(".o_erplibre_dev_field_view:eq(0)").toHaveText(/in the arch/);
        expect(".o_erplibre_dev_field_view:eq(1) .o_erplibre_dev_position").toHaveText("after");
        // The module filter dims the steps of the other modules.
        await contains(".o_erplibre_dev_module_chip[data-module=example]").click();
        expect(".o_erplibre_dev_step:eq(0)").toHaveClass("o_erplibre_dev_dimmed");
        expect(".o_erplibre_dev_step:eq(1)").not.toHaveClass("o_erplibre_dev_dimmed");
        expect(".o_erplibre_dev_field_row[data-field=parent_id]").toHaveClass("o_erplibre_dev_dimmed");
        // The custom field comes from the database; its view ties it to example.
        expect(".o_erplibre_dev_field_row[data-field=x_sample_level]").not.toHaveClass("o_erplibre_dev_dimmed");
        await contains(".o_erplibre_dev_module_all").click();

        // A core field: relation and flags.
        await contains(".o_erplibre_dev_field_row[data-field=parent_id]").click();
        expect(".o_erplibre_dev_field_card").toHaveAttribute("data-field", "parent_id");
        expect(".o_erplibre_dev_field_row[data-field=parent_id]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_field_row[data-field=name]").toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_dev_relation").toHaveText("→ res.partner");
        expect(queryAllTexts(".o_erplibre_dev_field_card .o_erplibre_dev_flag")).toEqual(["company_dependent"]);
        expect(".o_erplibre_dev_step .o_erplibre_dev_module_tag").toHaveText("Odoo core");
        expect(".o_erplibre_dev_chain_note").toHaveText("1 step");
        expect(".o_erplibre_dev_field_views").toHaveCount(0);

        // A custom field: no step, the database.
        await contains(".o_erplibre_dev_field_row[data-field=x_sample_level]").click();
        expect(".o_erplibre_dev_custom_field").toHaveCount(1);
        expect(".o_erplibre_dev_step").toHaveCount(0);
        expect(".o_erplibre_dev_chain_note").toHaveText("database");
        expect(queryAllTexts(".o_erplibre_dev_field_card .o_erplibre_dev_flag")).toEqual(["store=False"]);
        expect(".o_erplibre_dev_field_view").toHaveText(/names it/);

        // The kind filter survives a switch of tab; a view of the card
        // opens in the Views tab, among the views of the field.
        await contains(".o_erplibre_dev_field_filter[data-filter=custom]").click();
        await contains(".o_erplibre_dev_field_view[data-view-id='8']").click();
        expect("[data-tab=views]").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_dev_views_by_field").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_view_row[data-view-id='8'] .o_erplibre_dev_view_head").toHaveAttribute(
            "aria-expanded",
            "true"
        );
        // The mode takes the field of the card, not the first one listed.
        expect(".o_erplibre_dev_field_chip[data-field=x_sample_level]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_views_count").toHaveText("1 of 2 touch x_sample_level");
        // A field of the root arch lists the root view too.
        await contains(".o_erplibre_dev_field_chip[data-field=name]").click();
        expect(".o_erplibre_dev_view_row").toHaveCount(2);
        expect(".o_erplibre_dev_view_row:eq(0)").toHaveAttribute("data-view-id", "7");
        await contains(".o_erplibre_dev_field_chip[data-field=x_sample_level]").click();
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        expect(".o_erplibre_dev_field_filter[data-filter=custom]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_field_row").toHaveCount(1);
        expect(".o_erplibre_dev_field_card").toHaveAttribute("data-field", "x_sample_level");
    });

    test("a field in a closed notebook page: the card opens its tab", async () => {
        webModels.ResPartner._views.form = `
            <form>
                <sheet>
                    <notebook>
                        <page name="main" string="Main"><group/></page>
                        <page name="extra" string="Extra"><field name="name"/></page>
                    </notebook>
                </sheet>
            </form>`;
        patchPayload = (info) => {
            info.fields[0].node = {name: "name", page: {name: "extra", string: "Extra"}};
        };
        await mountWithCleanup(WebClient);
        await getService("action").doAction({
            name: "Partner",
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "form"]],
        });
        getService("erplibre_developer").open();
        await animationFrame();
        expect.verifySteps(["get_view_info res.partner form"]);
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        expect(".o_field_widget[name=name]").toHaveCount(0);
        expect(".o_erplibre_dev_page_note").toHaveText(/Shown in the “Extra” tab of the form\./);
        // Hovering the field outlines the header of its page.
        await hover(".o_erplibre_dev_field_row[data-field=name]");
        expect(".o_notebook_headers .nav-link[name=extra]").toHaveClass("o_erplibre_dev_highlight");
        await contains(".o_erplibre_dev_open_page").click();
        for (let frame = 0; frame < 5 && queryAll(".o_erplibre_dev_page_note").length; frame++) {
            await animationFrame();
        }
        expect(".o_notebook_headers .nav-link[name=extra]").toHaveClass("active");
        expect(".o_field_widget[name=name]").toHaveClass("o_erplibre_dev_highlight");
        expect(".o_erplibre_dev_page_note").toHaveCount(0);
    });

    test("the code tab groups the modules by repository, problems first", async () => {
        codeAnswers = [
            () => {
                const sample = codeSample();
                // A module in a sub-directory of its repository.
                Object.assign(sample.modules[1], {
                    path_rel: `${CLEAN_REPO}/sub/other_module`,
                    module_rel: "sub/other_module",
                });
                return sample;
            },
        ];
        repoAnswers = {[DIRTY_REPO]: () => repoDetailsSample()};
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        // The modified repository reads its uncommitted files at once.
        expect.verifySteps(["get_code_info base,example", `get_repo_details ${DIRTY_REPO} ${DIRTY_TARGET}`]);
        await animationFrame();
        // The modified repository first, the sound one, then no repository.
        expect(queryAll(".o_erplibre_dev_repo").map((el) => el.dataset.repo)).toEqual([DIRTY_REPO, CLEAN_REPO, ""]);
        expect(".o_erplibre_dev_repo:eq(0)").toHaveAttribute("aria-label", `Repository ${DIRTY_REPO}`);
        expect(".o_erplibre_dev_repo:eq(0) .o_erplibre_dev_repo_state").toHaveText("Modified");
        expect(".o_erplibre_dev_repo:eq(0) .o_erplibre_dev_repo_state").toHaveClass("bg-warning-subtle");
        expect(".o_erplibre_dev_repo:eq(0) .o_erplibre_dev_repo_facts").toHaveText(
            /branch dev\/sample.*HEAD 7c03b1f0aaaa.*manifest 18\.0.*ahead by 2.*HEAD: Ahead of the manifest.*from the snapshot/s
        );
        expect(".o_erplibre_dev_repo:eq(1) .o_erplibre_dev_repo_state").toHaveClass("bg-success-subtle");
        expect(".o_erplibre_dev_repo:eq(1) .o_erplibre_dev_ahead").toHaveCount(0);
        expect(".o_erplibre_dev_repo:eq(1) .o_erplibre_dev_dirty").toHaveCount(0);
        // Uncommitted files: the count, the capped list and the rest.
        expect(".o_erplibre_dev_dirty_count").toHaveText("23 uncommitted files");
        expect(".o_erplibre_dev_dirty_files li").toHaveCount(20);
        expect(".o_erplibre_dev_dirty_files li:eq(0)").toHaveText("M sample_module/file_0.py");
        expect(".o_erplibre_dev_dirty_more").toHaveText("and 3 more");
        expect(".o_erplibre_dev_code .alert").toHaveCount(0);
        // The module rows: versions, upgrade pending, a path without a repository.
        expect(".o_erplibre_dev_code_row[data-module=example] .o_erplibre_dev_versions").toHaveText(
            /^18\.0\.1\.0\.0\s*18\.0\.1\.1\.0$/
        );
        expect(".o_erplibre_dev_code_row[data-module=example] .o_erplibre_dev_pending").toHaveText("upgrade pending");
        expect(".o_erplibre_dev_code_row[data-module=base] .o_erplibre_dev_pending").toHaveCount(0);
        expect(".o_erplibre_dev_code_row[data-module=base] code[title='Installed version']").toHaveText("18.0.1.3");
        expect(".o_erplibre_dev_repo:eq(1) .o_erplibre_dev_caps").toHaveText(/^Modules · 2$/i);
        expect(".o_erplibre_dev_code_row[data-module=orphan] .o_erplibre_dev_module_path").toHaveText(
            "elsewhere/orphan"
        );
        // In a repository, the path shows when the module sits in a sub-directory.
        expect(".o_erplibre_dev_code_row[data-module=other_module] .o_erplibre_dev_module_path").toHaveText(
            "sub/other_module"
        );
        expect(".o_erplibre_dev_code_row[data-module=base] .o_erplibre_dev_module_path").toHaveCount(0);
        expect(".o_erplibre_dev_repo:eq(2) .o_erplibre_dev_repo_commits").toHaveCount(0);
        // Hovering a module outlines what it brings to the page.
        await hover(".o_erplibre_dev_code_row[data-module=base]");
        expect("th[data-name=name]").toHaveClass("o_erplibre_dev_highlight");
        await hover(".o_erplibre_dev_header");
        expect(".o_erplibre_dev_highlight").toHaveCount(0);
        // A module button filters the panel on it, and only dims.
        await contains(".o_erplibre_dev_code_row[data-module=example] .o_erplibre_dev_code_module").click();
        expect(".o_erplibre_dev_module_chip[data-module=example]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_code_row[data-module=example] .o_erplibre_dev_code_module").toHaveAttribute(
            "aria-pressed",
            "true"
        );
        expect(".o_erplibre_dev_repo:eq(1)").toHaveClass("o_erplibre_dev_dimmed");
        expect(".o_erplibre_dev_repo:eq(0)").not.toHaveClass("o_erplibre_dev_dimmed");
        // A dimmed repository dims once: its rows do not dim again.
        expect(".o_erplibre_dev_repo:eq(1) .o_erplibre_dev_code_row.o_erplibre_dev_dimmed").toHaveCount(0);
        expect(".o_erplibre_dev_repo").toHaveCount(3);
        await contains(".o_erplibre_dev_code_row[data-module=example] .o_erplibre_dev_code_module").click();
        expect(".o_erplibre_dev_dimmed").toHaveCount(0);
    });

    test("the code summary tiles hide what they leave out", async () => {
        codeAnswers = [() => codeSample()];
        repoAnswers = {[DIRTY_REPO]: () => repoDetailsSample()};
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps(["get_code_info base,example", `get_repo_details ${DIRTY_REPO} ${DIRTY_TARGET}`]);
        await animationFrame();
        expect(queryAllTexts(".o_erplibre_dev_code_tile").map((text) => text.replace(/\s+/g, " "))).toEqual([
            "4 modules",
            "2 repositories",
            "1 modified repository",
            "1 upgrade pending",
        ]);
        // « modules » is pressed while nothing is hidden.
        expect(".o_erplibre_dev_code_tile[data-tile=all]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_code_filtered").toHaveCount(0);
        await contains(".o_erplibre_dev_code_tile[data-tile=dirty]").click();
        expect(".o_erplibre_dev_code_tile[data-tile=dirty]").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_code_filtered").toHaveText(/Filtered: modified repositories/);
        expect(queryAll(".o_erplibre_dev_repo").map((el) => el.dataset.repo)).toEqual([DIRTY_REPO]);
        await contains(".o_erplibre_dev_code_tile[data-tile=upgrade]").click();
        expect(".o_erplibre_dev_code_row").toHaveCount(1);
        expect(".o_erplibre_dev_code_row").toHaveAttribute("data-module", "example");
        await contains(".o_erplibre_dev_code_tile[data-tile=repos]").click();
        expect(".o_erplibre_dev_repo").toHaveCount(2);
        expect(".o_erplibre_dev_code_row").toHaveCount(0);
        // The tile survives a switch of tab; pressing it again shows all.
        await contains(".o_erplibre_dev_tabs [data-tab=views]").click();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        expect(".o_erplibre_dev_code_tile[data-tile=repos]").toHaveAttribute("aria-pressed", "true");
        await contains(".o_erplibre_dev_code_tile[data-tile=repos]").click();
        expect(".o_erplibre_dev_code_row").toHaveCount(4);
        await contains(".o_erplibre_dev_code_tile[data-tile=dirty]").click();
        await contains(".o_erplibre_dev_code_filtered .o_erplibre_dev_show_all").click();
        expect(".o_erplibre_dev_code_filtered").toHaveCount(0);
        expect(".o_erplibre_dev_repo").toHaveCount(3);
        // A tile that keeps nothing says so, with its own « Show all ».
        codeAnswers = [() => ({modules: [codeModule("orphan")], snapshot_date: false, error: false})];
        await contains(".o_erplibre_dev_refresh").click();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps(["get_view_info res.partner list", "get_code_info base,example"]);
        await contains(".o_erplibre_dev_code_tile[data-tile=dirty]").click();
        expect(".o_erplibre_dev_code_empty").toHaveText(/No module matches this filter\./);
        await contains(".o_erplibre_dev_code_empty .o_erplibre_dev_show_all").click();
        expect(".o_erplibre_dev_code_row").toHaveCount(1);
    });

    test("the code tab reads the snapshot or the clones", async () => {
        const slow = new Deferred();
        codeAnswers = [
            (args) => {
                expect.step(`refresh ${args.kwargs.refresh}`);
                return {...codeSample(), snapshot_date: "2026-10-16 18:03:22"};
            },
            (args) => {
                expect.step(`refresh ${args.kwargs.refresh}`);
                return slow;
            },
        ];
        repoAnswers = {[DIRTY_REPO]: () => repoDetailsSample()};
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps([
            "get_code_info base,example",
            "refresh false",
            `get_repo_details ${DIRTY_REPO} ${DIRTY_TARGET}`,
        ]);
        expect(".o_erplibre_dev_code_snapshot").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_code_source_text").toHaveText(/^Read from the snapshot of/);
        await contains(".o_erplibre_dev_code_refresh").click();
        expect.verifySteps(["get_code_info base,example", "refresh true"]);
        expect(".o_erplibre_dev_code_refresh").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_dev_code_snapshot").toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_dev_code_loading[role=status]").toHaveText(/Reading the clones with\s*repo_state\.py/);
        // A second click while the clones are read asks nothing more.
        await contains(".o_erplibre_dev_code_refresh").click();
        expect.verifySteps([]);
        const sample = codeSample();
        for (const module of sample.modules) {
            module.repo_source = module.repo ? "repo_state" : false;
        }
        slow.resolve(sample);
        await animationFrame();
        // The details are read again, from the clone as it is now.
        expect.verifySteps([`get_repo_details ${DIRTY_REPO} ${DIRTY_TARGET}`]);
        expect(".o_erplibre_dev_code_loading").toHaveCount(0);
        expect(".o_erplibre_dev_code_source_text").toHaveText(/^Read from the clones at/);
        expect(".o_erplibre_dev_repo:eq(0) .o_erplibre_dev_repo_source").toHaveText("read now");
        // Back to the snapshot.
        codeAnswers = [() => codeSample()];
        await contains(".o_erplibre_dev_code_snapshot").click();
        await animationFrame();
        expect.verifySteps(["get_code_info base,example"]);
        expect(".o_erplibre_dev_code_snapshot").toHaveAttribute("aria-pressed", "true");
    });

    test("the recent commits of a repository open on demand, marked ahead", async () => {
        codeAnswers = [() => codeSample()];
        repoAnswers = {
            [DIRTY_REPO]: () => repoDetailsSample(),
            [CLEAN_REPO]: () => ({
                repo: CLEAN_REPO,
                dirty_count: 0,
                dirty_files: [],
                commits: [
                    {sha: "a41c9e2aaaaaaaaa", subject: "Sample fix", author: "Sample author", date: "2026-01-02T03:04:05+00:00", ahead: true},
                    {sha: "b52d0f3bbbbbbbbb", subject: "Sample change", author: "Sample author", date: "2026-01-01T03:04:05+00:00", ahead: false},
                ],
                target: "b52d0f3bbbbbbbbb",
                error: false,
            }),
        };
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps(["get_code_info base,example", `get_repo_details ${DIRTY_REPO} ${DIRTY_TARGET}`]);
        await animationFrame();
        const toggle = `.o_erplibre_dev_repo[data-repo='${CLEAN_REPO}'] .o_erplibre_dev_repo_commits_toggle`;
        expect(toggle).toHaveAttribute("aria-expanded", "false");
        expect(`${toggle} .o_erplibre_dev_tab_count`).toHaveCount(0);
        await contains(toggle).click();
        await animationFrame();
        expect.verifySteps([`get_repo_details ${CLEAN_REPO} ${CLEAN_TARGET}`]);
        expect(toggle).toHaveAttribute("aria-expanded", "true");
        expect(`${toggle} .o_erplibre_dev_tab_count`).toHaveText("2");
        const list = `#${queryOne(toggle).getAttribute("aria-controls")} .o_erplibre_dev_commit`;
        expect(list).toHaveCount(2);
        expect(`${list}:eq(0) code`).toHaveText("a41c9e2aaaaa");
        expect(`${list}:eq(0) .o_erplibre_dev_commit_ahead`).toHaveText("ahead");
        expect(`${list}:eq(1) .o_erplibre_dev_commit_ahead`).toHaveCount(0);
        expect(`${list}:eq(0) .o_erplibre_dev_commit_when`).toHaveAttribute("title", formatIsoDateTime("2026-01-02T03:04:05+00:00"));
        // Closing and opening again reads nothing more.
        await contains(toggle).click();
        expect(`${list}`).toHaveCount(0);
        await contains(toggle).click();
        expect.verifySteps([]);
        expect(list).toHaveCount(2);
        // The commits stay open across a switch of tab.
        await contains(".o_erplibre_dev_tabs [data-tab=fields]").click();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        expect(toggle).toHaveAttribute("aria-expanded", "true");
        expect.verifySteps([]);
    });

    test("a pending upgrade opens the actions tab on its module", async () => {
        patchPayload = (info) => {
            info.server_actions_allowed = true;
            info.server_actions_checks = {flag: true, group: true, debug: true, problem: false};
            // Not pending in this payload: the request checks it all the same.
            info.module_versions = {
                base: {installed: "18.0.1.3", code: "18.0.1.3", pending: false},
                example: {installed: "18.0.1.0.0", code: "18.0.1.0.0", pending: false},
            };
        };
        codeAnswers = [() => codeSample()];
        repoAnswers = {[DIRTY_REPO]: () => ({...repoDetailsSample(), error: "git status failed."})};
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=code]").click();
        await animationFrame();
        expect.verifySteps(["get_code_info base,example", `get_repo_details ${DIRTY_REPO} ${DIRTY_TARGET}`]);
        await animationFrame();
        expect(".o_erplibre_dev_dirty_count").toHaveText("23 uncommitted files");
        expect(".o_erplibre_dev_details_error").toHaveText("git status failed.");
        await contains(".o_erplibre_dev_code_row[data-module=example] .o_erplibre_dev_upgrade_link").click();
        await animationFrame();
        expect("[data-tab=actions]").toHaveAttribute("aria-selected", "true");
        // The module sent is checked, its box takes the focus.
        expect(".o_erplibre_dev_action_row[data-module=example] .o_erplibre_dev_upgrade_check").toBeChecked();
        expect(".o_erplibre_dev_action_row[data-module=example] .o_erplibre_dev_upgrade_check").toBeFocused();
        expect(".o_erplibre_dev_action_row[data-module=base] .o_erplibre_dev_upgrade_check").not.toBeChecked();
        expect(".o_erplibre_dev_upgrade").toHaveText("Upgrade 1 module (-u)");
        expect(".o_erplibre_dev_upgrade").toBeEnabled();
    });

    test("the actions tab: modules to upgrade checked, the others to pick, one upgrade", async () => {
        patchPayload = (info) => {
            info.server_actions_allowed = true;
            info.server_actions_checks = {flag: true, group: true, debug: true, problem: false};
            info.module_versions = {
                base: {installed: "18.0.1.3", code: "18.0.1.3", pending: false},
                example: {installed: "18.0.1.0.0", code: "18.0.1.1.0", pending: true},
            };
        };
        onRpc("erplibre.developer", "action_upgrade_modules", (args) => {
            expect.step(`action_upgrade_modules ${args.args[0].join(",")}`);
            return {type: "ir.actions.act_window_close"};
        });
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=actions]").click();
        await animationFrame();
        // The prerequisites: each with an icon and a word.
        expect(".o_erplibre_dev_prereq_badge").toHaveText("Ready");
        expect(".o_erplibre_dev_prereq_item").toHaveCount(3);
        expect(".o_erplibre_dev_prereq_item[data-ok='1'] .fa-check-circle[role=img][aria-label=Met]").toHaveCount(3);
        expect(queryAllTexts(".o_erplibre_dev_prereq_state")).toEqual(["enabled", "member", "active"]);
        expect(".o_erplibre_dev_actions_disabled").toHaveCount(0);
        expect(".o_erplibre_dev_lock_note").toHaveCount(0);
        // To upgrade: example, checked, installed → disk. The others: base.
        const upgrade = ".o_erplibre_dev_action_section[data-section=upgrade]";
        const others = ".o_erplibre_dev_action_section[data-section=others]";
        expect(`${upgrade} .o_erplibre_dev_action_row`).toHaveAttribute("data-module", "example");
        expect(`${upgrade} .o_erplibre_dev_versions`).toHaveText(/^18\.0\.1\.0\.0\s*18\.0\.1\.1\.0$/);
        expect(`${upgrade} .o_erplibre_dev_versions [role=img]`).toHaveAttribute("aria-label", "then on disk");
        expect(`${upgrade} .o_erplibre_dev_disk_version`).toHaveText("18.0.1.1.0");
        expect(`${others} .o_erplibre_dev_action_row`).toHaveAttribute("data-module", "base");
        expect(`${others} .o_erplibre_dev_versions`).toHaveText("18.0.1.3");
        // Real checkboxes, each with its label.
        expect(`${upgrade} .o_erplibre_dev_upgrade_check`).toBeChecked();
        expect(`${others} .o_erplibre_dev_upgrade_check`).not.toBeChecked();
        expect("label[for=o_erplibre_dev_up_base]").toHaveCount(1);
        expect(".o_erplibre_dev_upgrade").toHaveText("Upgrade 1 module (-u)");
        expect(".o_erplibre_dev_upgrade").toBeEnabled();
        // The count follows the boxes.
        await contains("label[for=o_erplibre_dev_up_base]").click();
        expect(".o_erplibre_dev_upgrade").toHaveText("Upgrade 2 modules (-u)");
        await contains(`${upgrade} .o_erplibre_dev_upgrade_check`).click();
        await contains(`${others} .o_erplibre_dev_upgrade_check`).click();
        expect(".o_erplibre_dev_upgrade").toHaveText("Upgrade 0 modules (-u)");
        expect(".o_erplibre_dev_upgrade").not.toBeEnabled();
        expect(".o_erplibre_dev_bar_note").toHaveText("Check at least one module to upgrade.");
        await contains(`${others} .o_erplibre_dev_upgrade_check`).click();
        await contains(`${upgrade} .o_erplibre_dev_upgrade_check`).click();
        // The boxes survive a switch of tab.
        await contains(".o_erplibre_dev_tabs [data-tab=views]").click();
        await contains(".o_erplibre_dev_tabs [data-tab=actions]").click();
        expect(".o_erplibre_dev_upgrade").toHaveText("Upgrade 2 modules (-u)");
        // The filter dims a checked module, which the bar counts.
        await contains(".o_erplibre_dev_module_chip[data-module=base]").click();
        expect(".o_erplibre_dev_action_row[data-module=example]").toHaveClass("o_erplibre_dev_dimmed");
        expect(".o_erplibre_dev_dimmed_checked").toHaveText(
            "1 checked module is dimmed by the module filter and will be upgraded too."
        );
        // Hovering a row outlines what its module brings to the page.
        await hover(".o_erplibre_dev_action_row[data-module=example]");
        expect("th[data-name=name]").toHaveClass("o_erplibre_dev_highlight");
        // One call for every checked module: it opens the confirmation.
        await contains(".o_erplibre_dev_upgrade").click();
        await animationFrame();
        expect.verifySteps(["action_upgrade_modules base,example"]);
    });

    test("with the option off, the upgrade is disabled with its reason", async () => {
        patchPayload = (info) => {
            info.server_actions_checks = {
                flag: false,
                group: true,
                debug: true,
                problem: "The option is off in the configuration file.",
            };
            info.module_versions = {
                base: {installed: "18.0.1.3", code: "18.0.1.3", pending: false},
                example: {installed: "18.0.1.0.0", code: "18.0.1.1.0", pending: true},
            };
        };
        patchWithCleanup(navigator.clipboard, {
            async writeText(text) {
                expect.step(`copy ${text}`);
            },
        });
        onRpc("erplibre.developer", "action_reload_assets", () => {
            expect.step("action_reload_assets");
            return true;
        });
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=actions]").click();
        await animationFrame();
        expect(".o_erplibre_dev_prereq_badge").toHaveText("1 prerequisite missing");
        expect(".o_erplibre_dev_prereq_item[data-check=flag]").toHaveAttribute("data-ok", "0");
        expect(".o_erplibre_dev_prereq_item[data-check=flag] .fa-times-circle").toHaveAttribute("aria-label", "Missing");
        expect(".o_erplibre_dev_prereq_item[data-check=flag] .o_erplibre_dev_prereq_state").toHaveText("disabled");
        expect(".o_erplibre_dev_actions_disabled").toHaveCount(1);
        expect(queryOne(".o_erplibre_dev_option_text").textContent).toBe(`[options]\n${SERVER_ACTIONS_OPTION}`);
        expect(".o_erplibre_dev_prereq_problem").toHaveText("The option is off in the configuration file.");
        expect(".o_erplibre_dev_lock_note").toHaveCount(1);
        await contains(".o_erplibre_dev_option_copy").click();
        expect.verifySteps([`copy ${SERVER_ACTIONS_OPTION}`]);
        expect(".o_erplibre_dev_option_copy").toHaveText("Copied");
        // The list stays readable; the boxes and the button are disabled,
        // with the reason.
        const reason =
            "Unavailable: the option erplibre_info_allow_server_actions is not enabled in the Odoo configuration.";
        expect(".o_erplibre_dev_action_row").toHaveCount(2);
        expect(".o_erplibre_dev_upgrade_check:not(:disabled)").toHaveCount(0);
        expect(".o_erplibre_dev_action_row[data-module=base] .o_erplibre_dev_upgrade_check").toHaveAttribute(
            "title",
            reason
        );
        expect(".o_erplibre_dev_upgrade").not.toBeEnabled();
        expect(".o_erplibre_dev_upgrade").toHaveAttribute("title", reason);
        expect(".o_erplibre_dev_bar_note").toHaveText("Upgrade blocked: see the prerequisites above.");
        // Reloading the assets restarts nothing: it stays available.
        expect(".o_erplibre_dev_reload_assets").toBeEnabled();
        await contains(".o_erplibre_dev_reload_assets").click();
        await animationFrame();
        expect.verifySteps(["action_reload_assets"]);
        expect(".o_erplibre_dev_assets_done[role=status]").toHaveCount(1);
        expect(".o_erplibre_dev_reload_page").toHaveCount(1);
    });

    test("the actions tab reads the recent runs and the commits of a module once", async () => {
        runsAnswer = () => {
            expect.step("get_recent_runs");
            return [
                {
                    id: 2,
                    run_type: "restart",
                    type_label: "Server restart",
                    state: "done",
                    state_label: "Done",
                    user: "Sample user",
                    date: "2026-01-02 03:04:05",
                    date_start: false,
                    date_end: false,
                    modules: ["example"],
                },
                {
                    id: 1,
                    run_type: "restart",
                    type_label: "Server restart",
                    state: "failed",
                    state_label: "Failed",
                    user: false,
                    date: "2026-01-01 03:04:05",
                    date_start: false,
                    date_end: false,
                    modules: [],
                },
            ];
        };
        onRpc("erplibre.developer", "get_module_commits", (args) => {
            expect.step(`get_module_commits ${args.args[0]}`);
            return {module: args.args[0], clone_rel: "odoo18.0/addons/sample_addons", commits: [], error: false};
        });
        await openDrawer();
        await contains(".o_erplibre_dev_tabs [data-tab=actions]").click();
        await animationFrame();
        expect.verifySteps(["get_recent_runs"]);
        expect(".o_erplibre_dev_run").toHaveCount(2);
        expect(".o_erplibre_dev_run:eq(0)").toHaveAttribute("data-state", "done");
        expect(".o_erplibre_dev_run:eq(0) [role=img]").toHaveAttribute("aria-label", "Done");
        expect(".o_erplibre_dev_run:eq(0) .o_erplibre_dev_run_module").toHaveText("example");
        expect(".o_erplibre_dev_run:eq(0) time").toHaveAttribute("datetime", /^2026-01-02T/);
        expect(".o_erplibre_dev_run:eq(1) [role=img]").toHaveAttribute("aria-label", "Failed");
        expect(".o_erplibre_dev_run:eq(1) .o_erplibre_dev_run_state").toHaveText("Failed");
        // The commits of a module: read at the first opening only.
        const history = ".o_erplibre_dev_action_row[data-module=example] .o_erplibre_dev_history";
        expect(history).toHaveAttribute("aria-expanded", "false");
        await contains(history).click();
        await animationFrame();
        expect.verifySteps(["get_module_commits example"]);
        expect(history).toHaveAttribute("aria-expanded", "true");
        expect("#o_erplibre_dev_commits_example .o_erplibre_dev_commits_repo").toHaveText(
            "odoo18.0/addons/sample_addons"
        );
        expect("#o_erplibre_dev_commits_example").toHaveText(/No recent commit touches this module\./);
        await contains(history).click();
        expect(".o_erplibre_dev_commits").toHaveCount(0);
        await contains(history).click();
        expect(".o_erplibre_dev_commits").toHaveCount(1);
        // A switch of tab keeps the runs; a reload reads them again.
        await contains(".o_erplibre_dev_tabs [data-tab=views]").click();
        await contains(".o_erplibre_dev_tabs [data-tab=actions]").click();
        await animationFrame();
        expect.verifySteps([]);
        runsAnswer = () => {
            expect.step("get_recent_runs");
            return [];
        };
        await contains(".o_erplibre_dev_refresh").click();
        await animationFrame();
        expect.verifySteps(["get_view_info res.partner list", "get_recent_runs"]);
        expect(".o_erplibre_dev_runs_empty").toHaveText("No run recorded.");
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
        expect(formatRelativeIso("not a date")).toBe("");
        expect(formatRelativeIso(false)).toBe("");
        expect(formatRelativeIso("2010-01-02T03:04:05+00:00")).toMatch(/ago/);
        expect(formatRelativeServerDateTime("2010-01-02 03:04:05")).toMatch(/ago/);
        expect(formatRelativeServerDateTime("not a date")).toBe("");
        expect(formatRelativeServerDateTime(false)).toBe("");
        // Without the checks, the flag follows server_actions_allowed.
        expect(serverActionsChecks({server_actions_allowed: false})).toEqual({
            flag: false,
            group: true,
            debug: true,
            problem: false,
        });
        expect(upgradePending({module_versions: {a: {pending: true}}}, "a")).toBe(true);
        expect(upgradePending({}, "a")).toBe(false);
        const info = basePayload({args: ["res.partner", false, "list"]});
        expect(moduleHighlightItems(info, "example").map((i) => [i.kind, i.name, i.label])).toEqual([
            ["field", "name", "name · after · example"],
        ]);
        expect(moduleHighlightItems(info, "base").map((i) => i.label)).toEqual(["name · char · base"]);
        expect(moduleHighlightItems(info, "other")).toEqual([]);
    });
});
