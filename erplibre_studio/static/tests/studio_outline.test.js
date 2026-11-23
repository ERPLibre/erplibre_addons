// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {after, beforeEach, describe, expect, test} from "@odoo/hoot";
import {press, queryOne} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {contains, defineWebModels, getService, mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {translatedTerms, translationLoaded} from "@web/core/l10n/translation";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {blockTrail, outlineRows} from "@erplibre_studio/editor/studio_editor";

const SHEET = "/form/sheet";
const ADDRESS = "//group[@name='address']";
const NOTEBOOK = "/form/sheet/notebook";
const NOTES = "//page[@name='notes']";
const SALES = "//page[@name='sales']";
const named = (name) => `//field[@name='${name}']`;

const FIELDS = {
    street: {string: "Street", type: "char"},
    city: {string: "City", type: "char"},
    comment: {string: "Internal notes", type: "html"},
    user_id: {string: "Salesperson", type: "many2one"},
    x_sponsor: {string: "Sponsor", type: "many2one", project: true, pending: true, definition: {}},
    lang: {string: "Langue préférée", type: "selection"},
};

/** A field block; ``kinds``: the kinds of the draft changes that touch it. */
function field(name, kinds = [], extra = {}) {
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
        ...extra,
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
        changed_inside: children.some((child) => child.changed || child.changed_inside),
    };
}

/**
 * A partner form: a sheet with an address group (the city relabelled) and
 * a notebook whose second page holds a new field and a hidden one.
 */
function formBlocks() {
    const address = container(ADDRESS, "group", "Address", [field("street"), field("city", ["renamed"])]);
    address.children[1].label = "Town";
    const notes = container(NOTES, "page", "Notes", [field("comment")]);
    const sales = container(SALES, "page", "Sales", [
        field("user_id"),
        field("x_sponsor", ["new"]),
        field("lang", ["hidden"], {attrs: {invisible: "1"}}),
    ]);
    const notebook = container(NOTEBOOK, "notebook", "notebook", [notes, sales]);
    const sheet = container(SHEET, "sheet", "sheet", [address, notebook]);
    return container("/form", "form", "form", [sheet]);
}

function payload(extra = {}) {
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "form",
        view: {id: 9, name: "res.partner.form", xml_id: "base.view_partner_form"},
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "hide", "relabel", "help"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: FIELDS,
        palette: [
            {name: "phone", string: "Phone", type: "char"},
            {name: "vat", string: "Tax ID", type: "char"},
        ],
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
            change_count: 3,
            item_count: 3,
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
        ...extra,
    };
}

let answer;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "apply_operation", (args) => {
        const operation = args.args[4];
        expect.step(`apply_operation ${operation.type} ${operation.source} ${operation.position} ${operation.target}`);
        answer = payload();
        answer.project.revision = args.kwargs.revision + 1;
        return answer;
    });
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 9}));
    await animationFrame();
}

function row(path) {
    return `.o_erplibre_studio_outline_row[data-path="${path}"]`;
}

/** The labels of the rows of the plan on screen. */
function rowLabels() {
    return [...document.querySelectorAll(".o_erplibre_studio_outline_label")].map((el) => el.textContent.trim());
}

/** Let ``_t`` answer the terms as they are: the helpers run without a web client. */
function loadTranslations() {
    const loaded = translatedTerms[translationLoaded];
    translatedTerms[translationLoaded] = true;
    after(() => {
        translatedTerms[translationLoaded] = loaded;
    });
}

describe("the outline of a view", () => {
    test("the rows, the folded containers, the trail of a block", () => {
        loadTranslations();
        const root = formBlocks();
        const all = outlineRows(root);
        expect(all.total).toBe(11);
        expect(all.rows.map((r) => [r.block.path, r.depth])).toEqual([
            [SHEET, 0],
            [ADDRESS, 1],
            [named("street"), 2],
            [named("city"), 2],
            [NOTEBOOK, 1],
            [NOTES, 2],
            [named("comment"), 3],
            [SALES, 2],
            [named("user_id"), 3],
            [named("x_sponsor"), 3],
            [named("lang"), 3],
        ]);
        const folded = outlineRows(root, {collapsed: {[ADDRESS]: true}});
        expect(folded.rows.map((r) => r.block.path)).not.toInclude(named("street"));
        expect(folded.rows.find((r) => r.block.path === ADDRESS).open).toBe(false);
        expect(blockTrail(root, named("lang")).map((b) => b.path)).toEqual(["/form", SHEET, NOTEBOOK, SALES, named("lang")]);
        expect(blockTrail(root, "//field[@name='nothing']")).toEqual([]);
    });

    test("the filter: label or technical name, accents aside, with its containers", () => {
        loadTranslations();
        const root = formBlocks();
        // « preferee » finds « Langue préférée »; its containers show as context.
        const accent = outlineRows(root, {filter: "preferee"});
        expect(accent.matches).toBe(1);
        expect(accent.rows.map((r) => [r.block.path, r.context])).toEqual([
            [SHEET, true],
            [NOTEBOOK, true],
            [SALES, true],
            [named("lang"), false],
        ]);
        // The technical name matches too.
        expect(outlineRows(root, {filter: "X_SPON"}).rows.map((r) => r.block.path)).toInclude(named("x_sponsor"));
        // A container the text matches keeps its blocks, even folded.
        const page = outlineRows(root, {filter: "sales", collapsed: {[SALES]: true}});
        expect(page.matches).toBe(4);
        expect(page.rows.map((r) => r.block.path).slice(-3)).toEqual([
            named("user_id"),
            named("x_sponsor"),
            named("lang"),
        ]);
        // « Modified » keeps the blocks a change touches.
        const changed = outlineRows(root, {changedOnly: true});
        expect(changed.matches).toBe(3);
        expect(changed.rows.filter((r) => !r.context).map((r) => r.block.name)).toEqual(["city", "x_sponsor", "lang"]);
        // Both at once.
        expect(outlineRows(root, {filter: "town", changedOnly: true}).matches).toBe(1);
        expect(outlineRows(root, {filter: "zzz"}).rows).toEqual([]);
    });
});

describe.current.tags("desktop");
describe("erplibre_studio editor, plan and change marks", () => {
    test("the canvas tags the changed fields and marks the containers that hold changes", async () => {
        await openEditor();
        expect(`.o_erplibre_studio_field[data-name=city] .o_erplibre_studio_change_tag[data-kind=renamed]`).toHaveCount(
            1
        );
        // The pages: the first one shows; the tab of the second marks its changes.
        expect(`.o_erplibre_studio_page_tab[data-path="${SALES}"] .o_erplibre_studio_change_dot`).toHaveCount(1);
        expect(`.o_erplibre_studio_page_tab[data-path="${NOTES}"] .o_erplibre_studio_change_dot`).toHaveCount(0);
        expect(
            `.o_erplibre_studio_container[data-path="${ADDRESS}"] > .o_erplibre_studio_container_title .o_erplibre_studio_change_dot[data-dot=inside]`
        ).toHaveCount(1);
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        expect(".o_erplibre_studio_field[data-name=x_sponsor] .o_erplibre_studio_change_tag[data-kind=new]").toHaveCount(
            1
        );
        // The tag « new » stands for the flag of a pending field.
        expect(".o_erplibre_studio_field[data-name=x_sponsor] .o_erplibre_studio_flag[data-flag=pending]").toHaveCount(0);
        expect(".o_erplibre_studio_field[data-name=lang]").toHaveClass("o_erplibre_studio_changed_hidden");
        expect(".o_erplibre_studio_field[data-name=lang] .o_erplibre_studio_change_tag[data-kind=hidden]").toHaveCount(1);
        expect(".o_erplibre_studio_field[data-name=lang] .o_erplibre_studio_flag[data-flag=hidden]").toHaveCount(0);
        // A click on the canvas selects at once, and the trail shows it.
        await contains(".o_erplibre_studio_field[data-name=user_id]").click();
        expect(".o_erplibre_studio_field[data-name=user_id]").toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_crumb").toHaveCount(4);
        expect(".o_erplibre_studio_crumb:last").toHaveText("Salesperson");
        expect(".o_erplibre_studio_crumb:last").toHaveAttribute("aria-current", "location");
    });

    test("the plan selects, filters, folds, and drags", async () => {
        await openEditor();
        expect(".o_erplibre_studio_left_tab[data-panel=palette]").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_plan_count").toHaveText("3");
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        expect(".o_erplibre_studio_left_tab[data-panel=plan]").toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_palette [data-tab]").toHaveCount(0);
        expect(".o_erplibre_studio_outline_row").toHaveCount(11);
        expect(".o_erplibre_studio_outline_count").toHaveText("11 item(s)");
        expect(".o_erplibre_studio_outline_changed").toHaveText("Modified · 3");
        expect(`${row(named("x_sponsor"))} .o_erplibre_studio_outline_tag`).toHaveText("new");

        // A click on a field of a page not shown: the page shows, the
        // field is selected on the canvas and in the inspector.
        await contains(`${row(named("lang"))} .o_erplibre_studio_outline_pick`).click();
        expect(row(named("lang"))).toHaveAttribute("aria-selected", "true");
        expect(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).toHaveClass("active");
        expect(".o_erplibre_studio_field[data-name=lang]").toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-name", "lang");
        expect(".o_erplibre_studio_crumb").toHaveCount(4);
        // A crumb selects a container.
        await contains(`.o_erplibre_studio_crumb[data-path="${SALES}"]`).click();
        expect(`.o_erplibre_studio_container[data-path="${SALES}"]`).toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-kind", "container");
        expect(row(SALES)).toHaveAttribute("aria-selected", "true");

        // The filter: accents aside, a count, a button that clears it.
        await contains(".o_erplibre_studio_outline_filter").edit("preferee");
        expect(rowLabels()).toEqual(["Sheet", "Tabs", "Sales", "Langue préférée"]);
        expect(".o_erplibre_studio_outline_count").toHaveText("1 result(s)");
        await contains(".o_erplibre_studio_outline_filter").edit("zzz");
        expect(".o_erplibre_studio_outline_empty").toHaveText("No element matches « zzz ».");
        await contains(".o_erplibre_studio_outline_clear").click();
        expect(".o_erplibre_studio_outline_row").toHaveCount(11);

        // « Modified »: the changed blocks and their containers.
        await contains(".o_erplibre_studio_outline_changed").click();
        expect(".o_erplibre_studio_outline_changed").toHaveAttribute("aria-pressed", "true");
        expect(".o_erplibre_studio_outline_count").toHaveText("3 result(s)");
        expect(".o_erplibre_studio_outline_row:not(.o_erplibre_studio_outline_context)").toHaveCount(3);
        await contains(".o_erplibre_studio_outline_all").click();
        expect(".o_erplibre_studio_outline_row").toHaveCount(11);

        // A folded container hides its blocks and marks their changes.
        await contains(`${row(ADDRESS)} .o_erplibre_studio_outline_toggle`).click();
        expect(row(ADDRESS)).toHaveAttribute("aria-expanded", "false");
        expect(row(named("street"))).toHaveCount(0);
        expect(`${row(ADDRESS)} .o_erplibre_studio_change_dot_inside`).toHaveCount(1);
        await contains(`${row(ADDRESS)} .o_erplibre_studio_outline_toggle`).click();
        expect(row(named("street"))).toHaveCount(1);

        // A row drags onto a hook of the canvas as a block does.
        await contains(`${row(named("street"))} .o_erplibre_studio_outline_pick`).dragAndDrop(
            `.o_erplibre_studio_hook[data-target="${named("city")}"][data-position=before]`
        );
        expect.verifySteps([`apply_operation move ${named("street")} before ${named("city")}`]);
        // The plan stays open across the answer.
        expect(".o_erplibre_studio_outline_row").toHaveCount(11);
    });

    test("the plan is one tab stop that the arrow keys walk", async () => {
        await openEditor();
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        expect(row(SHEET)).toHaveAttribute("tabindex", "0");
        expect(`.o_erplibre_studio_outline_row[tabindex="0"]`).toHaveCount(1);
        expect(`${row(SHEET)} .o_erplibre_studio_outline_pick`).toHaveAttribute("tabindex", "-1");
        queryOne(row(SHEET)).focus();
        await press("ArrowDown");
        await animationFrame();
        expect(row(ADDRESS)).toBeFocused();
        expect(row(ADDRESS)).toHaveAttribute("tabindex", "0");
        expect(row(SHEET)).toHaveAttribute("tabindex", "-1");
        // Left folds an open container, Right unfolds it, then enters it.
        await press("ArrowLeft");
        await animationFrame();
        expect(row(ADDRESS)).toHaveAttribute("aria-expanded", "false");
        expect(row(named("street"))).toHaveCount(0);
        await press("ArrowRight");
        await animationFrame();
        expect(row(ADDRESS)).toHaveAttribute("aria-expanded", "true");
        await press("ArrowRight");
        await animationFrame();
        expect(row(named("street"))).toBeFocused();
        // Left on a leaf goes up to its container; Enter selects.
        await press("ArrowLeft");
        await animationFrame();
        expect(row(ADDRESS)).toBeFocused();
        await press("Enter");
        await animationFrame();
        expect(row(ADDRESS)).toHaveAttribute("aria-selected", "true");
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-kind", "container");
        await press("End");
        await animationFrame();
        expect(row(named("lang"))).toBeFocused();
        await press("Home");
        await animationFrame();
        expect(row(SHEET)).toBeFocused();
    });

    test("Alt+Arrow moves a block out of its group, from the canvas and from the plan", async () => {
        await openEditor();
        // The last field of a group goes down to the hook after the group.
        const city = ".o_erplibre_studio_field[data-name=city] .o_erplibre_studio_pick";
        queryOne(city).focus();
        await press(["Alt", "ArrowDown"]);
        await animationFrame();
        await animationFrame();
        expect.verifySteps([`apply_operation move ${named("city")} before ${NOTEBOOK}`]);
        expect(city).toBeFocused();
        // The first one goes up to the hook before it.
        queryOne(".o_erplibre_studio_field[data-name=street] .o_erplibre_studio_pick").focus();
        await press(["Alt", "ArrowUp"]);
        await animationFrame();
        expect.verifySteps([`apply_operation move ${named("street")} before ${ADDRESS}`]);

        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        const pick = `${row(named("city"))} .o_erplibre_studio_outline_pick`;
        // A div, not a button: a mousedown on a button starts no drag in Firefox.
        expect(queryOne(pick).tagName).toBe("DIV");
        expect(pick).toHaveAttribute("tabindex", "-1");
        expect(pick).toHaveAttribute("draggable", "true");
        queryOne(row(named("city"))).focus();
        await press(["Alt", "ArrowDown"]);
        await animationFrame();
        await animationFrame();
        expect.verifySteps([`apply_operation move ${named("city")} before ${NOTEBOOK}`]);
        expect(row(named("city"))).toBeFocused();
        // Delete removes the block of the row.
        await press("Delete");
        await animationFrame();
        expect.verifySteps([`apply_operation remove undefined undefined ${named("city")}`]);
    });

    test("a container title and the chatter are buttons too", async () => {
        answer.blocks.children.push({
            path: "/form/chatter",
            tag: "chatter",
            kind: "other",
            label: "chatter",
            attrs: {},
            movable: false,
            changes: [],
            change_kinds: [],
            changed: false,
            changed_inside: false,
        });
        await openEditor();
        const title = `.o_erplibre_studio_container[data-path="${ADDRESS}"] > .o_erplibre_studio_container_title`;
        const chatter = ".o_erplibre_studio_other[data-tag=chatter]";
        expect(`${title} > .o_erplibre_studio_pick`).toHaveAttribute("aria-label", "Container Group « Address »");
        // The dot of the changes inside keeps its tooltip: out of the button.
        expect(`${title} > .o_erplibre_studio_change_dot`).toHaveCount(1);
        expect(`${title} .o_erplibre_studio_pick .o_erplibre_studio_change_dot`).toHaveCount(0);
        expect(`${chatter} > .o_erplibre_studio_pick`).toHaveAttribute(
            "aria-label",
            "Chatter: messages, followers and activities"
        );
        expect(chatter).toHaveAttribute("draggable", "false");
        queryOne(`${title} > .o_erplibre_studio_pick`).focus();
        await press("Enter");
        await animationFrame();
        expect(`.o_erplibre_studio_container[data-path="${ADDRESS}"]`).toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_properties").toHaveAttribute("data-kind", "container");
        // The arrows walk into the group, then on to the chatter.
        await press("ArrowDown");
        expect(".o_erplibre_studio_field[data-name=street] .o_erplibre_studio_pick").toBeFocused();
        await press("End");
        expect(`${chatter} > .o_erplibre_studio_pick`).toBeFocused();
        await press("Enter");
        await animationFrame();
        expect(chatter).toHaveClass("o_erplibre_studio_selected");
        expect(`${chatter} > .o_erplibre_studio_pick`).toHaveAttribute("aria-pressed", "true");
    });

    test("Enter on a palette item with a group or a page selected adds it inside", async () => {
        await openEditor();
        const add = ".o_erplibre_studio_new_field[data-type=char] > .o_erplibre_studio_palette_add";
        const title = `.o_erplibre_studio_container[data-path="${ADDRESS}"] > .o_erplibre_studio_container_title`;
        await contains(title).click();
        expect(`.o_erplibre_studio_container[data-path="${ADDRESS}"]`).toHaveClass("o_erplibre_studio_selected");
        queryOne(add).focus();
        await press("Enter");
        await animationFrame();
        expect.verifySteps([`apply_operation add_field undefined inside ${ADDRESS}`]);
        // A tab page selected: at the end of the page.
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        queryOne(add).focus();
        await press("Enter");
        await animationFrame();
        expect.verifySteps([`apply_operation add_field undefined inside ${SALES}`]);
        // A field selected: right after it, as before.
        await contains(".o_erplibre_studio_field[data-name=street]").click();
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        queryOne(".o_erplibre_studio_existing_field[data-name=phone] > .o_erplibre_studio_palette_add").focus();
        await press("Enter");
        await animationFrame();
        expect.verifySteps([`apply_operation add_existing_field undefined before ${named("city")}`]);
    });

    test("the palette: a search over the types and the fields, the other types, the existing fields", async () => {
        answer = payload({
            field_types: [
                "char",
                "integer",
                "float",
                "boolean",
                "date",
                "datetime",
                "selection",
                "many2one",
                "text",
                "html",
                "monetary",
                "many2many",
            ],
        });
        await openEditor();
        expect(".o_erplibre_studio_new_field").toHaveCount(8);
        expect(".o_erplibre_studio_new_field[data-type=many2many]").toHaveCount(1);
        expect(".o_erplibre_studio_new_field[data-type=html]").toHaveCount(0);
        await contains(".o_erplibre_studio_more_types").click();
        expect(".o_erplibre_studio_new_field").toHaveCount(12);
        expect(".o_erplibre_studio_more_types").toHaveAttribute("aria-expanded", "true");
        // The existing fields fold, folded first where the view offers new types.
        // The title shows in capitals (CSS): compare the text of the DOM.
        expect(".o_erplibre_studio_palette [data-tab=existing]").toHaveText(/Existing fields · 2/i);
        expect(".o_erplibre_studio_palette [data-tab=existing]").toHaveAttribute("aria-expanded", "false");
        expect(".o_erplibre_studio_existing_field").toHaveCount(0);
        // A search shows what matches among the types and the fields.
        await contains(".o_erplibre_studio_palette_filter").edit("date");
        expect(".o_erplibre_studio_new_field").toHaveCount(2);
        expect(".o_erplibre_studio_more_types").toHaveCount(0);
        await contains(".o_erplibre_studio_palette_filter").edit("vat");
        expect(".o_erplibre_studio_new_field").toHaveCount(0);
        expect(".o_erplibre_studio_existing_field").toHaveCount(1);
        await contains(".o_erplibre_studio_palette_filter").clear();
        await contains(".o_erplibre_studio_palette [data-tab=existing]").click();
        expect(".o_erplibre_studio_existing_field").toHaveCount(2);
    });
});
