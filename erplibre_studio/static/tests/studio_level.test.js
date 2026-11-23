// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {queryAll, queryOne} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {
    contains,
    defineWebModels,
    getService,
    makeServerError,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";

const SHEET = "/form/sheet";
const ADDRESS = "//group[@name='address']";
const named = (name) => `//field[@name='${name}']`;

const FIELDS = {
    street: {string: "Street", type: "char", modules: "base"},
    user_id: {string: "Salesperson", type: "many2one", relation: "res.users", modules: "base"},
    x_sponsor: {
        string: "Sponsor",
        type: "char",
        project: true,
        pending: true,
        name_auto: true,
        definition: {field_description: "Sponsor", help: "", readonly: false},
    },
};

function field(name, kinds = []) {
    return {
        path: named(name),
        tag: "field",
        kind: "field",
        name,
        label: FIELDS[name].string,
        attrs: {},
        movable: true,
        changes: kinds.length ? [1] : [],
        change_kinds: kinds,
        changed: kinds.length > 0,
        changed_inside: false,
    };
}

function container(path, tag, label, children) {
    return {
        path,
        tag,
        kind: "container",
        label,
        attrs: {},
        movable: true,
        drop: true,
        children,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
    };
}

/** A partner form: an address group with a street, a salesperson and a new field. */
function formBlocks() {
    const address = container(ADDRESS, "group", "Address", [
        field("street"),
        field("user_id"),
        field("x_sponsor", ["new"]),
    ]);
    return container("/form", "form", "form", [container(SHEET, "sheet", "sheet", [address])]);
}

/** The payload of the form; without ``display_level`` the level stays as it is. */
function payload(extra = {}) {
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "form",
        view: {
            id: 9,
            name: "res.partner.form",
            xml_id: "base.view_partner_form",
            inherited: {views: 3, modules: 2},
        },
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "relabel", "rename_field", "set_attribute"],
        hide_mode: "invisible",
        settable: {field: {widget: "widget"}},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: JSON.parse(JSON.stringify(FIELDS)),
        palette: [{name: "phone", string: "Phone", type: "char"}],
        field_types: ["char"],
        changes: [
            {
                id: 2,
                type: "add_field",
                kind: "new",
                attribute: false,
                summary: "Add Sponsor",
                xpath: named("user_id"),
                path: named("x_sponsor"),
                error: false,
            },
        ],
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
            item_count: 1,
            counts: {fields: 1, views: 1, total: 1, name_blockers: 0},
            app: false,
            models: [],
            access: [],
            rules: [],
            applied: false,
        },
        projects: [{id: 3, name: "Contacts", module_name: "studio_contacts", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        ...extra,
    };
}

let answer;
// How many times the editor asked for its payload.
let editorCalls;
// The levels set_display_level was called with, in order.
let levels;
// The message set_display_level refuses with, or null to accept.
let refuseLevel;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    levels = [];
    refuseLevel = null;
    editorCalls = 0;
    onRpc("erplibre.studio.editor", "get_editor_data", () => {
        editorCalls++;
        return answer;
    });
    onRpc("erplibre.studio.editor", "set_display_level", (args) => {
        levels.push(args.args[0]);
        if (refuseLevel) {
            throw makeServerError({message: refuseLevel});
        }
        return args.args[0];
    });
    onRpc("erplibre.studio.editor", "check_field_name", (args) => {
        const name = args.args[2] || "x_sponsor";
        const ok = name.startsWith("x_");
        return {
            name,
            proposed: "x_sponsor",
            status: ok ? "available" : "invalid",
            message: ok ? "Available" : "Prefix x_ required on this database",
            detail: "",
            checks: [],
            rule: null,
        };
    });
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 9}));
    await animationFrame();
}

const SIMPLE = ".o_erplibre_studio_level_option[data-level=simple]";
const DETAILED = ".o_erplibre_studio_level_option[data-level=detailed]";
const TECH = ".o_erplibre_studio_tech";
const EXISTING_ADD = ".o_erplibre_studio_existing_field .o_erplibre_studio_palette_add";

/** Unfold the existing fields of the palette, when folded. */
async function showExisting() {
    const toggle = ".o_erplibre_studio_section_toggle[data-tab=existing]";
    if (queryOne(toggle).getAttribute("aria-expanded") !== "true") {
        await contains(toggle).click();
    }
    expect(".o_erplibre_studio_existing_field").toHaveCount(1);
}

/** Show the plan, then the palette, the changes, the properties: the parts that hold technical bits. */
async function eachPanel(check) {
    await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
    check("plan");
    await contains(".o_erplibre_studio_left_tab[data-panel=palette]").click();
    check("palette");
    await contains(".o_erplibre_studio_inspector_tab[data-tab=changes]").click();
    check("changes");
    await contains(".o_erplibre_studio_inspector_tab[data-tab=properties]").click();
    check("properties");
}

describe("the display level of the editor", () => {
    test("Simple by default: no technical bit anywhere in the view space", async () => {
        await openEditor();
        expect(".o_erplibre_studio").toHaveAttribute("data-level", "simple");
        expect(SIMPLE).toHaveAttribute("aria-pressed", "true");
        expect(DETAILED).toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_studio_level").toHaveAttribute("aria-label", "Display level of the editor");
        expect(".o_erplibre_studio_level_note").toHaveText("Remembered for your account");
        expect(".o_erplibre_studio_xml_id").toHaveCount(0);
        expect(".o_erplibre_studio_inherited").toHaveCount(0);
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        await showExisting();
        await eachPanel((panel) => {
            expect(TECH).toHaveCount(0, {message: panel});
            expect("code").toHaveCount(0, {message: panel});
        });
        expect(EXISTING_ADD).toHaveAttribute("aria-label", "Add Phone");
        expect(".o_erplibre_studio_existing_field").not.toHaveAttribute("title");
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        expect(".o_erplibre_studio_outline_filter").toHaveAttribute("placeholder", "Filter the plan");
        expect(
            `.o_erplibre_studio_outline_row[data-path="${named("user_id")}"] .o_erplibre_studio_outline_pick`
        ).not.toHaveAttribute("title");
        expect(levels).toEqual([]);
    });

    test("Simple: the technical name and the widget fold under More options", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_name").toHaveCount(0);
        expect(".o_erplibre_studio_field_advanced_toggle").toHaveText("More options");
        expect(".o_erplibre_studio_field_advanced_toggle").toHaveAttribute("aria-expanded", "false");
        expect(".o_erplibre_studio_field_advanced").toHaveCount(0);
        expect(".o_erplibre_studio_level_hint").toHaveText(
            /^Technical name, widget and visibility: Detailed level\.\s*Switch to Detailed$/
        );
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        expect(".o_erplibre_studio_field_advanced_toggle").toHaveAttribute("aria-expanded", "true");
        // The technical name first, then the widget.
        expect(".o_erplibre_studio_field_advanced .o_erplibre_studio_prop_name").toHaveValue("user_id");
        expect(
            queryAll(
                ".o_erplibre_studio_field_advanced > label, .o_erplibre_studio_field_advanced > *[data-attribute]"
            ).map((el) => (el.querySelector(".o_erplibre_studio_prop_name") ? "name" : el.dataset.attribute))
        ).toEqual(["name", "widget"]);
        expect(".o_erplibre_studio_level_hint").toHaveText(/^Always see these options:\s*Switch to Detailed$/);
        expect(".o_erplibre_studio_inspector_tech").toHaveCount(0);
    });

    test("Detailed: chosen on the top bar, remembered on the server, every technical bit shows", async () => {
        await openEditor();
        expect(editorCalls).toBe(1);
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        await contains(DETAILED).click();
        expect(levels).toEqual(["detailed"]);
        // The payload stays: no reload of the editor.
        expect(editorCalls).toBe(1);
        expect(".o_erplibre_studio").toHaveAttribute("data-level", "detailed");
        expect(DETAILED).toHaveAttribute("aria-pressed", "true");
        expect(SIMPLE).toHaveAttribute("aria-pressed", "false");
        expect(".o_erplibre_studio_xml_id").toHaveText("base.view_partner_form");
        expect(".o_erplibre_studio_crumbs .o_erplibre_studio_inherited").toHaveText(
            "+ 3 inherited view(s) from 2 module(s)"
        );
        // The canvas: the field names and their types.
        expect(".o_erplibre_studio_field[data-name=user_id] code.o_erplibre_studio_tech").toHaveText("user_id");
        expect(".o_erplibre_studio_field[data-name=user_id] .badge.o_erplibre_studio_tech").toHaveText("many2one");
        // A group shows its technical caption: its tag, then its label.
        expect(`.o_erplibre_studio_container[data-path="${ADDRESS}"] .o_erplibre_studio_container_title`).toHaveText(
            "<group> Address"
        );
        // The inspector: the header, the name with the field, the
        // technical attributes always shown, no toggle nor hint.
        expect(".o_erplibre_studio_inspector_tech code").toHaveText("user_id");
        expect(".o_erplibre_studio_inspector_modules").toHaveText("base");
        expect(".o_erplibre_studio_inspector_origin").toHaveText("from the view base.view_partner_form");
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_name").toHaveValue("user_id");
        expect(".o_erplibre_studio_field_advanced_toggle").toHaveCount(0);
        expect(".o_erplibre_studio_level_hint").toHaveCount(0);
        expect(queryOne(".o_erplibre_studio_field_advanced legend").textContent.trim()).toBe("Technical");
        expect(".o_erplibre_studio_field_advanced [data-attribute=widget]").toHaveCount(1);
        // A field of the project.
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        expect(".o_erplibre_studio_inspector_origin").toHaveText("created by this project");
        // The plan, the palette and the changes.
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        expect(".o_erplibre_studio_outline_filter").toHaveAttribute("placeholder", "Filter: label or technical name");
        expect(
            `.o_erplibre_studio_outline_row[data-path="${named("street")}"] .o_erplibre_studio_outline_tech`
        ).toHaveText("street");
        expect(`.o_erplibre_studio_outline_row[data-path="${ADDRESS}"] .o_erplibre_studio_outline_tech`).toHaveText(
            "group"
        );
        await contains(".o_erplibre_studio_left_tab[data-panel=palette]").click();
        await showExisting();
        expect(".o_erplibre_studio_existing_field code.o_erplibre_studio_tech").toHaveText("phone");
        expect(EXISTING_ADD).toHaveAttribute("aria-label", "Add Phone (phone)");
        expect(".o_erplibre_studio_existing_field").toHaveAttribute("title", "char");
        await contains(".o_erplibre_studio_inspector_tab[data-tab=changes]").click();
        expect(".o_erplibre_studio_change_xpath").toHaveText(named("user_id"));

        // Back to Simple: the technical bits leave.
        await contains(SIMPLE).click();
        expect(levels).toEqual(["detailed", "simple"]);
        expect(TECH).toHaveCount(0);
        expect(".o_erplibre_studio_xml_id").toHaveCount(0);
    });

    test("the level of the payload: Detailed read back from the server", async () => {
        answer = payload({display_level: "detailed"});
        await openEditor();
        expect(".o_erplibre_studio").toHaveAttribute("data-level", "detailed");
        expect(DETAILED).toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_studio_crumbs .o_erplibre_studio_inherited").toHaveCount(1);
        // A view no other view extends names no inherited view.
        answer = payload({
            display_level: "detailed",
            view: {
                id: 9,
                name: "res.partner.form",
                xml_id: "base.view_partner_form",
                inherited: {views: 0, modules: 0},
            },
        });
        await contains(".o_erplibre_studio_view_tab[data-view-type=list]").click();
        expect(".o_erplibre_studio_crumbs .o_erplibre_studio_xml_id, .o_erplibre_studio_crumbs code").toHaveCount(1);
        expect(".o_erplibre_studio_inherited").toHaveCount(0);
    });

    test("a refused level comes back and the user is told", async () => {
        refuseLevel = "Only the Settings administrators open the developer panel.";
        await openEditor();
        await contains(DETAILED).click();
        expect(levels).toEqual(["detailed"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-level", "simple");
        expect(SIMPLE).toHaveAttribute("aria-pressed", "true");
        expect(TECH).toHaveCount(0);
        expect(".o_notification").toHaveText(/Only the Settings administrators/);
    });

    test("the hint switches to Detailed; the level buttons are tab stops", async () => {
        await openEditor();
        for (const selector of [SIMPLE, DETAILED]) {
            expect(selector).toHaveAttribute("type", "button");
            expect(selector).not.toHaveAttribute("tabindex");
        }
        await contains(".o_erplibre_studio_field[data-name=street]").click();
        expect(".o_erplibre_studio_level_switch").toHaveAttribute("type", "button");
        await contains(".o_erplibre_studio_level_switch").click();
        expect(levels).toEqual(["detailed"]);
        expect(".o_erplibre_studio").toHaveAttribute("data-level", "detailed");
        expect(".o_erplibre_studio_field_props .o_erplibre_studio_prop_name").toHaveValue("street");
    });

    test("a refused technical name keeps More options open", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_field[data-name=x_sponsor]").click();
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        await contains(".o_erplibre_studio_field_advanced .o_erplibre_studio_prop_name").edit("sponsor", {
            confirm: false,
        });
        await animationFrame();
        expect(".o_erplibre_studio_name_blockers").toHaveCount(1);
        expect(".o_erplibre_studio_apply_bar").not.toBeEnabled();
        // Folding is refused while the name does not apply.
        await contains(".o_erplibre_studio_field_advanced_toggle").click();
        expect(".o_erplibre_studio_field_advanced_toggle").toHaveAttribute("aria-expanded", "true");
        expect(".o_erplibre_studio_field_advanced .o_erplibre_studio_prop_name").toHaveValue("sponsor");
    });
});
