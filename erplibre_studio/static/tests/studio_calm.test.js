// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {after, beforeEach, describe, expect, test} from "@odoo/hoot";
import {press, queryOne} from "@odoo/hoot-dom";
import {animationFrame} from "@odoo/hoot-mock";
import {contains, defineWebModels, getService, mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {deserializeDate, deserializeDateTime, formatDate, formatDateTime} from "@web/core/l10n/dates";
import {translatedTerms, translationLoaded} from "@web/core/l10n/translation";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {changeKeysInside, isBaseInvisible} from "@erplibre_studio/editor/studio_editor";

const SHEET = "/form/sheet";
const MAIN = "//group[@name='main']";
const LEFT = "//group[@name='left']";
const RIGHT = "//group[@name='right']";
const NOTEBOOK = "/form/sheet/notebook";
const NOTES = "//page[@name='notes']";
const SALES = "//page[@name='sales']";
const LOYALTY = "//page[@name='loyalty']";
const CHATTER = "/form/chatter";
const named = (name) => `//field[@name='${name}']`;

// An invented contact model: none of these values exists anywhere else.
const FIELDS = {
    name: {string: "Name", type: "char"},
    street: {string: "Street", type: "char"},
    code: {string: "Internal code", type: "char"},
    x_level: {string: "Partner level", type: "selection", project: true, pending: true, definition: {}},
    phone: {string: "Phone", type: "char"},
    email: {string: "Email", type: "char"},
    fax: {string: "Fax", type: "char"},
    is_vendor: {string: "Vendor", type: "boolean"},
    comment: {string: "Notes", type: "html"},
    user_id: {string: "Salesperson", type: "many2one"},
    x_sponsor: {string: "Sponsor", type: "many2one", project: true, pending: true, definition: {}},
    terms: {string: "Payment terms", type: "many2one"},
    birthday: {string: "Birthday", type: "date"},
    last_visit: {string: "Last visit", type: "datetime"},
    child_ids: {string: "Contacts", type: "one2many", relation: "res.partner"},
};

let nextKey = 1;

/** A field block; ``kinds``: the kinds of the draft changes that touch it, each change a key of its own. */
function field(name, kinds = [], attrs = {}, extra = {}) {
    return {
        path: named(name),
        tag: "field",
        kind: "field",
        name,
        label: FIELDS[name].string,
        attrs,
        movable: true,
        changes: kinds.length ? [nextKey++] : [],
        change_kinds: kinds,
        changed: kinds.length > 0,
        changed_inside: false,
        ...extra,
    };
}

function container(path, tag, label, children, extra = {}) {
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
        ...extra,
    };
}

/**
 * A contact form: a title, a row of two groups (a field the arch always
 * hides, a new one, a moved one, a renamed one, one the draft hides), a
 * notebook whose first page shows, whose second holds two changes and
 * whose third, new, is empty; then the chatter.
 */
function formBlocks() {
    nextKey = 1;
    const title = container("/form/sheet/div/h1", "h1", "h1", [field("name")]);
    const left = container(LEFT, "group", "left", [
        field("street"),
        field("code", [], {invisible: "1"}),
        field("x_level", ["new"]),
        field("phone", ["moved"], {required: "1"}),
    ]);
    const right = container(RIGHT, "group", "right", [
        field("email", ["renamed"]),
        field("fax", ["hidden"], {invisible: "1"}),
        field("is_vendor"),
    ]);
    right.attrs = {string: "Reach"};
    const main = container(MAIN, "group", "main", [left, right]);
    const notes = container(NOTES, "page", "Notes", [field("comment")]);
    const sales = container(SALES, "page", "Sales", [
        field("user_id"),
        field("x_sponsor", ["new"]),
        field("terms", ["attribute"]),
    ]);
    const loyalty = container(LOYALTY, "page", "Loyalty", [], {
        changes: [nextKey++],
        change_kinds: ["new"],
        changed: true,
    });
    const notebook = container(NOTEBOOK, "notebook", "notebook", [notes, sales, loyalty]);
    const sheet = container(SHEET, "sheet", "sheet", [title, main, notebook]);
    const chatter = {
        path: CHATTER,
        tag: "chatter",
        kind: "other",
        label: "chatter",
        attrs: {},
        movable: false,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
    };
    return container("/form", "form", "form", [sheet, chatter]);
}

function project() {
    return {
        id: 3,
        name: "Contacts",
        module_name: "studio_contacts",
        state: "draft",
        state_label: "Draft",
        revision: 0,
        preview_value: "3:0",
        change_count: 7,
        item_count: 7,
        app: false,
        models: [],
        access: [],
        rules: [],
        applied: false,
    };
}

function payload(extra = {}) {
    return {
        model: "res.partner",
        model_name: "Contact",
        view_type: "form",
        view: {id: 9, name: "res.partner.form", xml_id: "base.view_partner_form"},
        blocks: formBlocks(),
        layout: {root: "/form"},
        operations: ["add_field", "add_existing_field", "move", "remove", "hide", "relabel", "help", "add_page"],
        hide_mode: "invisible",
        settable: {},
        required_attributes: {},
        choices: {},
        view_types: ["form", "list"],
        fields: FIELDS,
        palette: [],
        field_types: ["char", "integer", "selection"],
        changes: [],
        errors: [],
        project: project(),
        projects: [{id: 3, name: "Contacts", module_name: "studio_contacts", state: "draft"}],
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: false,
        ...extra,
    };
}

/** The payload of a list whose second column the draft adds. */
function listPayload() {
    const columns = [field("name"), field("email", ["new"]), field("phone", ["hidden"], {column_invisible: "1"})];
    return payload({
        view_type: "list",
        view: {id: 7, name: "res.partner.list", xml_id: "base.view_partner_tree"},
        blocks: container("/list", "list", "list", columns),
        layout: {root: "/list"},
        hide_mode: "column_invisible",
    });
}

let answer;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "set_display_level", (args) => args.args[0]);
});

async function openEditor(viewType = "form") {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(
        customizeAction({resModel: "res.partner", viewType, viewId: viewType === "form" ? 9 : 7})
    );
    await animationFrame();
}

const DETAILED = ".o_erplibre_studio_level_option[data-level=detailed]";
const DOT = ".o_erplibre_studio_margin_dot";
const line = (name) => `.o_erplibre_studio_field[data-name=${name}]`;

/** Let ``_t`` answer the terms as they are: the helpers run without a web client. */
function loadTranslations() {
    const loaded = translatedTerms[translationLoaded];
    translatedTerms[translationLoaded] = true;
    after(() => {
        translatedTerms[translationLoaded] = loaded;
    });
}

describe("the helpers of the calm canvas", () => {
    test("changeKeysInside: the keys of the changes under a block, each once", () => {
        loadTranslations();
        const root = formBlocks();
        const sheet = root.children[0];
        const notebook = sheet.children[2];
        const [notes, sales, loyalty] = notebook.children;
        expect(changeKeysInside(sales)).toHaveLength(2);
        expect(changeKeysInside(notes)).toEqual([]);
        // The page's own change is not under it.
        expect(changeKeysInside(loyalty)).toEqual([]);
        // A key two blocks share counts once.
        sales.children[0].changes = [...sales.children[1].changes];
        expect(changeKeysInside(sales)).toHaveLength(2);
        // The notebook: the two changes of the sales and the new page.
        expect(changeKeysInside(notebook)).toHaveLength(3);
        expect(changeKeysInside(null)).toEqual([]);
    });

    test("isBaseInvisible: a constant invisible the draft did not write", () => {
        const root = formBlocks();
        const [left, right] = root.children[0].children[1].children;
        expect(isBaseInvisible(left.children[1])).toBe(true);
        // The draft hides it: a change, not the base arch.
        expect(isBaseInvisible(right.children[1])).toBe(false);
        expect(isBaseInvisible({attrs: {invisible: "not is_company"}, change_kinds: []})).toBe(false);
        expect(isBaseInvisible({attrs: {}})).toBe(false);
    });
});

describe.current.tags("desktop");
describe("the calm canvas of a form", () => {
    test("Simple: the real form, one margin dot per change, no tag nor flag", async () => {
        await openEditor();
        expect(".o_erplibre_studio").toHaveAttribute("data-level", "simple");
        // The fields of a group are lines: gutter, label, value.
        expect(`${line("street")}.o_erplibre_studio_line`).toHaveCount(1);
        expect(`${line("street")} > .o_erplibre_studio_gutter`).toHaveCount(1);
        expect(`${line("street")} > .o_erplibre_studio_line_label`).toHaveText("Street");
        expect(`${line("street")} > .o_erplibre_studio_line_value .o_erplibre_studio_placeholder`).toHaveText("—");
        expect(`${line("is_vendor")} .o_erplibre_studio_placeholder_check`).toHaveCount(1);
        // The title draws its value only.
        expect(`${line("name")}`).toHaveClass(["o_erplibre_studio_bare", "o_erplibre_studio_form_title"]);
        // The groups stay side by side; the one with a string shows its title.
        expect(`.o_erplibre_studio_container[data-path="${MAIN}"]`).toHaveClass("o_erplibre_studio_row");
        expect(`.o_erplibre_studio_container[data-path="${RIGHT}"] .o_erplibre_studio_group_title`).toHaveText(
            /^reach$/i
        );
        expect(`.o_erplibre_studio_container[data-path="${LEFT}"] > .o_erplibre_studio_title_chip`).toHaveCount(1);
        // At rest: no arrow, no tag, no flag, no code.
        expect(".o_erplibre_studio_canvas .fa-arrows").toHaveCount(0);
        expect(".o_erplibre_studio_change_tag").toHaveCount(0);
        expect(".o_erplibre_studio_flag").toHaveCount(0);
        expect(".o_erplibre_studio_canvas code").toHaveCount(0);
        // One dot per changed element: new, moved, renamed, the new tab;
        // a ring for the field the draft hides.
        expect(`${DOT}[data-dot=filled]`).toHaveCount(4);
        expect(`${DOT}[data-dot=ring]`).toHaveCount(1);
        expect(`${line("x_level")} > .o_erplibre_studio_gutter > ${DOT}`).toHaveAttribute("aria-label", "new");
        expect(`${line("phone")} ${DOT}`).toHaveAttribute("title", "moved");
        expect(`${line("street")} ${DOT}`).toHaveCount(0);
        // The dot of the new tab sits in the gutter of the tabs.
        expect(
            `.o_erplibre_studio_notebook > .o_erplibre_studio_notebook_head > .o_erplibre_studio_gutter > ${DOT}`
        ).toHaveCount(1);
        // No dot inside a button: the dots keep their tooltips.
        expect(`.o_erplibre_studio_pick ${DOT}`).toHaveCount(0);
    });

    test("the tabs: a count on a tab not shown, the empty hint, the chatter line", async () => {
        await openEditor();
        expect(`.o_erplibre_studio_page_tab[data-path="${NOTES}"]`).toHaveClass("active");
        expect(`.o_erplibre_studio_page_tab[data-path="${NOTES}"] .o_erplibre_studio_margin_count`).toHaveCount(0);
        expect(`.o_erplibre_studio_page_tab[data-path="${SALES}"] .o_erplibre_studio_margin_count`).toHaveText("2");
        expect(`.o_erplibre_studio_page_tab[data-path="${SALES}"] .o_erplibre_studio_margin_count`).toHaveAttribute(
            "aria-label",
            "2 change(s) inside"
        );
        // The new tab holds nothing yet: no count.
        expect(`.o_erplibre_studio_page_tab[data-path="${LOYALTY}"] .o_erplibre_studio_margin_count`).toHaveCount(0);
        // Shown, the tab carries nothing more; its blocks carry their dots.
        await contains(`.o_erplibre_studio_page_tab[data-path="${SALES}"]`).click();
        expect(`.o_erplibre_studio_page_tab[data-path="${SALES}"] .o_erplibre_studio_margin_count`).toHaveCount(0);
        expect(`${line("x_sponsor")} ${DOT}[data-dot=filled]`).toHaveCount(1);
        expect(`${line("terms")} ${DOT}`).toHaveAttribute("aria-label", "edited");
        expect(".o_erplibre_studio_empty_hint").toHaveCount(0);
        await contains(`.o_erplibre_studio_page_tab[data-path="${LOYALTY}"]`).click();
        expect(`.o_erplibre_studio_container[data-path="${LOYALTY}"] .o_erplibre_studio_empty_hint`).toHaveText(
            "Empty tab. Drag a field here from the palette or the form."
        );
        // The hook of the empty page stays under its hint.
        expect(
            `.o_erplibre_studio_container[data-path="${LOYALTY}"] .o_erplibre_studio_empty_hint + .o_erplibre_studio_hook`
        ).toHaveCount(1);
        // The chatter: one collapsed line, selectable, not draggable.
        const chatter = `.o_erplibre_studio_other[data-tag=chatter]`;
        expect(chatter).toHaveAttribute("draggable", "false");
        expect(`${chatter} > .o_erplibre_studio_chatter_line`).toHaveAttribute("aria-expanded", "false");
        expect(`${chatter} > .o_erplibre_studio_chatter_line`).toHaveText(/Chatter\s*collapsed/);
        expect(`${chatter} > .o_erplibre_studio_chatter_line`).toHaveClass("o_erplibre_studio_pick");
        await contains(chatter).click();
        expect(chatter).toHaveClass("o_erplibre_studio_selected");
        expect(".o_erplibre_studio_selected").toHaveCount(1);
    });

    test("hidden elements: the draft's as a muted line, the base arch's as the form draws them", async () => {
        await openEditor();
        // The field the draft removes: one muted line, still a block that selects.
        expect(line("fax")).toHaveClass(["o_erplibre_studio_muted_line", "o_erplibre_studio_changed_hidden"]);
        expect(`${line("fax")} > .o_erplibre_studio_pick`).toHaveText("Fax removed — show");
        expect(`${line("fax")} ${DOT}[data-dot=ring]`).toHaveAttribute("aria-label", "hidden");
        expect(`${line("fax")} .o_erplibre_studio_line_value`).toHaveCount(0);
        expect(`${line("fax")} .o_erplibre_studio_ghost_value`).toHaveCount(0);
        await contains(line("fax")).click();
        expect(line("fax")).toHaveClass("o_erplibre_studio_selected");
        // The field the arch always hides is not drawn…
        expect(line("code")).toHaveCount(0);
        // …unless it is the selection: then a muted line.
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        await contains(
            `.o_erplibre_studio_outline_row[data-path="${named("code")}"] .o_erplibre_studio_outline_pick`
        ).click();
        expect(line("code")).toHaveClass(["o_erplibre_studio_muted_line", "o_erplibre_studio_selected"]);
        expect(`${line("code")} > .o_erplibre_studio_pick`).toHaveText("Internal code hidden");
        // A click elsewhere: it leaves the canvas again.
        await contains(line("street")).click();
        expect(line("code")).toHaveCount(0);
    });

    test("Detailed brings back the tags, the flags, the names and the base-invisible fields", async () => {
        await openEditor();
        await contains(DETAILED).click();
        expect(".o_erplibre_studio").toHaveAttribute("data-level", "detailed");
        expect(`${line("x_level")} .o_erplibre_studio_change_tag[data-kind=new]`).toHaveCount(1);
        expect(`${line("email")} .o_erplibre_studio_change_tag[data-kind=renamed]`).toHaveCount(1);
        expect(`${line("phone")} .o_erplibre_studio_flag[data-flag=required]`).toHaveCount(1);
        expect(`${line("street")} code.o_erplibre_studio_tech`).toHaveText("street");
        // The dots stay.
        expect(`${DOT}[data-dot=filled]`).toHaveCount(4);
        // The field the draft hides: its whole row, muted, its tag.
        expect(line("fax")).not.toHaveClass("o_erplibre_studio_muted_line");
        expect(line("fax")).toHaveClass("o_erplibre_studio_changed_hidden");
        expect(`${line("fax")} .o_erplibre_studio_change_tag[data-kind=hidden]`).toHaveCount(1);
        // The field the arch always hides: drawn, muted, flagged.
        expect(line("code")).toHaveClass(["o_erplibre_studio_line", "o_erplibre_studio_base_invisible"]);
        expect(`${line("code")} .o_erplibre_studio_flag[data-flag=hidden]`).toHaveCount(1);
        // The groups: their technical caption.
        expect(`.o_erplibre_studio_container[data-path="${LEFT}"] > .o_erplibre_studio_container_title`).toHaveText(
            "<group> left"
        );
        expect(`.o_erplibre_studio_container[data-path="${RIGHT}"] > .o_erplibre_studio_container_title`).toHaveText(
            /Reach\s*<group> right/i
        );
        // The new tab shows its tag.
        expect(
            `.o_erplibre_studio_page_tab[data-path="${LOYALTY}"] .o_erplibre_studio_change_tag[data-kind=new]`
        ).toHaveCount(1);
    });

    test("the values of the sample record under their labels, placeholders elsewhere", async () => {
        const blocks = formBlocks();
        const [left, right] = blocks.children[0].children[1].children;
        left.children.push(field("birthday"), field("last_visit"));
        right.children.push(field("child_ids"));
        answer = payload({
            blocks,
            sample_res_id: 4,
            sample_values: {
                name: "Studio sample company",
                street: "12 Invented Road\nSample City",
                birthday: "2024-03-05",
                last_visit: "2024-03-05 14:30:00",
                is_vendor: true,
                child_ids: {count: 3},
            },
        });
        await openEditor();
        const value = (name) => `${line(name)} > .o_erplibre_studio_line_value`;
        // The title: the name of the record, in place of the label.
        expect(`${line("name")} .o_erplibre_studio_sample_value`).toHaveText("Studio sample company");
        expect(`${line("name")} .o_erplibre_studio_sample_value`).toHaveClass("o_erplibre_studio_label");
        expect(`${line("name")} .o_erplibre_studio_placeholder`).toHaveCount(0);
        // A text keeps its line break; a date and a datetime in the user's format.
        expect(`${value("street")} .o_erplibre_studio_sample_value`).toHaveText(/^12 Invented Road\s+Sample City$/);
        expect(`${value("street")} .o_erplibre_studio_placeholder`).toHaveCount(0);
        expect(`${value("birthday")} .o_erplibre_studio_sample_value`).toHaveText(
            formatDate(deserializeDate("2024-03-05"))
        );
        expect(`${value("last_visit")} .o_erplibre_studio_sample_value`).toHaveText(
            formatDateTime(deserializeDateTime("2024-03-05 14:30:00"))
        );
        // A boolean: a checkbox look; an x2many: its count in the sub-list.
        expect(`${value("is_vendor")} .o_erplibre_studio_sample_check`).toHaveAttribute("data-checked", "true");
        expect(`${value("is_vendor")} .o_erplibre_studio_sample_check`).toHaveAttribute("aria-label", "Yes");
        expect(`${value("is_vendor")} .o_erplibre_studio_placeholder_check`).toHaveCount(0);
        expect(`${value("child_ids")} .o_erplibre_studio_sublist .o_erplibre_studio_sample_count`).toHaveText(
            "3 record(s)"
        );
        // No value given: the placeholder, a new field of the project too.
        expect(`${value("phone")} .o_erplibre_studio_placeholder`).toHaveText("—");
        expect(`${value("x_level")} .o_erplibre_studio_placeholder`).toHaveText("—");
        expect(`${value("phone")} .o_erplibre_studio_sample_value`).toHaveCount(0);
    });

    test("keyboard: every block is a button, Enter selects, the arrows walk", async () => {
        await openEditor();
        const pick = (name) => `${line(name)} > .o_erplibre_studio_pick`;
        expect(pick("street")).toHaveAttribute("aria-label", "Field Street (street)");
        queryOne(pick("street")).focus();
        await press("Enter");
        await animationFrame();
        expect(line("street")).toHaveClass("o_erplibre_studio_selected");
        await press("ArrowDown");
        // The base-invisible field is not drawn: the next button is the new field.
        expect(pick("x_level")).toBeFocused();
    });
});

describe("the calm canvas of a list", () => {
    test("a column: its header, a muted cell, the dot at its left", async () => {
        answer = listPayload();
        await openEditor("list");
        expect(`${line("name")}`).toHaveClass("o_erplibre_studio_list_column");
        expect(`${line("name")} > .o_erplibre_studio_line_label`).toHaveText("Name");
        expect(`${line("name")} > .o_erplibre_studio_line_value`).toHaveText("—");
        expect(`${line("email")} > .o_erplibre_studio_gutter > ${DOT}[data-dot=filled]`).toHaveCount(1);
        expect(`${line("phone")}`).toHaveClass("o_erplibre_studio_muted_line");
        expect(`${line("phone")} ${DOT}[data-dot=ring]`).toHaveCount(1);
        expect(".o_erplibre_studio_change_tag").toHaveCount(0);
        expect(".o_erplibre_studio_canvas .fa-arrows").toHaveCount(0);
        await contains(DETAILED).click();
        expect(`${line("email")} .o_erplibre_studio_change_tag[data-kind=new]`).toHaveCount(1);
    });

    test("a column keeps its placeholder: the values are a form's", async () => {
        answer = {...listPayload(), sample_values: {name: "Studio sample company"}};
        await openEditor("list");
        expect(`${line("name")} > .o_erplibre_studio_line_value`).toHaveText("—");
        expect(".o_erplibre_studio_sample_value").toHaveCount(0);
    });
});
