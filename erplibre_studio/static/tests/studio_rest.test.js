// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {animationFrame} from "@odoo/hoot-mock";
import {contains, defineWebModels, getService, mountWithCleanup, onRpc} from "@web/../tests/web_test_helpers";
import {WebClient} from "@web/webclient/webclient";
import {customizeAction} from "@erplibre_studio/debug_items";
import {isHiddenOnRecord, sampleContext, shownWhen} from "@erplibre_studio/editor/studio_editor";

// The canvas of a form at rest looks like the real form (rule 1): what the
// form hides on the sample record is not drawn, the widgets draw as
// themselves, a label-less field shows its value or its placeholder.

const SHEET = "/form/sheet";
const WARNING = "/form/sheet/div[@name='warning']";
const BOX = "/form/sheet/div[@name='button_box']";
const TITLE = "/form/sheet/h1";
const COMPANY_NAME = "/form/sheet/h1/field[1]";
const PERSON_NAME = "/form/sheet/h1/field[2]";
const MAIN = "//group[@name='main']";
const ADDRESS = "//group[@name='main']/div";
const NOTEBOOK = "/form/sheet/notebook";
const CONTACTS = "//page[@name='contacts']";
const PRIVATE = "//page[@name='private']";
const named = (name) => `//field[@name='${name}']`;

// An invented contact model: none of these values exists anywhere else.
const FIELDS = {
    name: {string: "Name", type: "char"},
    is_company: {string: "Is a company", type: "boolean"},
    kind: {
        string: "Contact kind",
        type: "selection",
        selection: [
            ["person", "Individual"],
            ["company", "Company"],
        ],
    },
    picture: {string: "Picture", type: "binary"},
    street: {string: "Street", type: "char"},
    city: {string: "City", type: "char"},
    zip: {string: "Zip", type: "char"},
    email: {string: "Email", type: "char"},
    job: {string: "Job title", type: "char"},
    sector: {string: "Sector", type: "many2one", relation: "x.sector"},
    labels: {string: "Labels", type: "many2many", relation: "x.label"},
    twin_id: {string: "Twin record", type: "many2one", relation: "res.partner"},
    member_ids: {string: "Members", type: "one2many", relation: "res.partner"},
    note: {string: "Note", type: "char"},
};

function field(name, attrs = {}, extra = {}) {
    return {
        path: named(name),
        tag: "field",
        kind: "field",
        name,
        label: FIELDS[name].string,
        attrs,
        movable: true,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
        ...extra,
    };
}

function container(path, tag, label, children, attrs = {}) {
    return {
        path,
        tag,
        kind: "container",
        label,
        attrs,
        movable: true,
        drop: true,
        children,
        changes: [],
        change_kinds: [],
        changed: false,
        changed_inside: false,
    };
}

/**
 * A contact form: a warning shown when a twin record exists, an empty box
 * of smart buttons, a picture, a radio, a title of two names (one per
 * kind of contact), a group with a label-less address, a job title for a
 * person, a sector for a company, tags; a notebook whose second tab is
 * for a person.
 */
function formBlocks() {
    const warning = container(WARNING, "div", "warning", [field("twin_id")], {invisible: "not twin_id"});
    const box = container(BOX, "div", "button_box", []);
    const title = container(TITLE, "h1", "h1", [
        field("name", {invisible: "not is_company", placeholder: "Company name"}, {path: COMPANY_NAME}),
        field("name", {invisible: "is_company", placeholder: "Person name"}, {path: PERSON_NAME}),
    ]);
    const address = container(ADDRESS, "div", "div", [
        field("street", {placeholder: "Street..."}),
        field("city", {placeholder: "City"}),
        field("zip"),
    ]);
    const main = container(MAIN, "group", "main", [
        address,
        field("email", {widget: "email"}),
        field("job", {invisible: "is_company"}),
        field("sector", {invisible: "not is_company"}),
        field("labels", {widget: "many2many_tags"}),
        field("is_company"),
    ]);
    const contacts = container(CONTACTS, "page", "Members", [field("member_ids")]);
    const personal = container(PRIVATE, "page", "Private", [field("note")], {invisible: "is_company"});
    const notebook = container(NOTEBOOK, "notebook", "notebook", [contacts, personal]);
    const sheet = container(SHEET, "sheet", "sheet", [
        warning,
        box,
        field("picture", {widget: "image"}),
        field("kind", {widget: "radio"}),
        title,
        main,
        notebook,
    ]);
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
        operations: ["add_field", "add_existing_field", "move", "remove", "hide", "relabel", "add_page"],
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
        preview_key: "erplibre_studio_view_ref",
        sample_res_id: 4,
        sample_values: {
            name: "Invented Works",
            kind: "Company",
            street: "12 Invented Road",
            email: "orders.desk@invented-works.example",
            is_company: true,
            labels: {count: 7, names: ["Supplier", "Office", "Wholesale", "Retail", "Export"]},
            member_ids: {count: 3},
        },
        sample_record: {is_company: true, twin_id: false},
        ...extra,
    };
}

let answer;

beforeEach(() => {
    defineWebModels();
    answer = payload();
    onRpc("erplibre.studio.editor", "get_editor_data", () => answer);
    onRpc("erplibre.studio.editor", "set_display_level", (args) => args.args[0]);
});

async function openEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction(customizeAction({resModel: "res.partner", viewType: "form", viewId: 9}));
    await animationFrame();
}

const DETAILED = ".o_erplibre_studio_level_option[data-level=detailed]";
const at = (path) => `.o_erplibre_studio_canvas [data-path="${path}"]`;
const line = (name) => `.o_erplibre_studio_field[data-name=${name}]`;

describe("the helpers of the canvas at rest", () => {
    test("isHiddenOnRecord: the invisible condition evaluated on the record", () => {
        const context = {is_company: true, twin_id: false, kind: "company"};
        const hidden = (invisible, extra = {}) => isHiddenOnRecord({attrs: {invisible}, ...extra}, context);
        expect(hidden("is_company")).toBe(true);
        expect(hidden("not is_company")).toBe(false);
        expect(hidden("not twin_id")).toBe(true);
        expect(hidden("kind != 'person' and not twin_id")).toBe(true);
        // A constant is the base arch's, an element the draft hides its own.
        expect(hidden("1")).toBe(false);
        expect(hidden("is_company", {change_kinds: ["hidden"]})).toBe(false);
        // A name the context lacks, or no context: drawn.
        expect(hidden("unknown_name")).toBe(false);
        expect(isHiddenOnRecord({attrs: {invisible: "is_company"}}, null)).toBe(false);
        expect(isHiddenOnRecord({attrs: {}}, context)).toBe(false);
    });

    test("sampleContext: the values of the record, its id, the user's context", () => {
        const user = {userId: 7, context: {lang: "en_US", allowed_company_ids: [2, 5]}};
        const context = sampleContext({sample_res_id: 4, sample_record: {is_company: true}}, user);
        expect(context.is_company).toBe(true);
        expect(context.id).toBe(4);
        expect(context.uid).toBe(7);
        expect(context.allowed_company_ids).toEqual([2, 5]);
        expect(context.current_company_id).toBe(2);
        expect(context.context.lang).toBe("en_US");
        expect(sampleContext({sample_res_id: false, sample_record: {}}, user)).toBe(null);
        expect(sampleContext({sample_res_id: 4}, user)).toBe(null);
    });

    test("shownWhen: the negation of the condition, as a reader writes it", () => {
        expect(shownWhen("not twin_id")).toBe("twin_id");
        expect(shownWhen("is_company")).toBe("not is_company");
        expect(shownWhen("not (a or b)")).toBe("a or b");
        expect(shownWhen("kind == 'person'")).toBe("not (kind == 'person')");
        expect(shownWhen("not a and b")).toBe("not (not a and b)");
    });
});

describe.current.tags("desktop");
describe("the canvas of a form at rest", () => {
    test("Simple: what the form hides on the sample record is not drawn", async () => {
        await openEditor();
        expect(".o_erplibre_studio").toHaveAttribute("data-level", "simple");
        expect(at(WARNING)).toHaveCount(0);
        expect(line("twin_id")).toHaveCount(0);
        // The title of a company shows; the one of a person does not.
        expect(at(COMPANY_NAME)).toHaveCount(1);
        expect(at(PERSON_NAME)).toHaveCount(0);
        expect(line("job")).toHaveCount(0);
        expect(line("sector")).toHaveCount(1);
        // The tab of a person is left out; the form opens on the other.
        expect(`.o_erplibre_studio_page_tab[data-path="${PRIVATE}"]`).toHaveCount(0);
        expect(`.o_erplibre_studio_page_tab[data-path="${CONTACTS}"]`).toHaveClass("active");
        // The plan lists what the canvas draws; its filter finds the
        // others: a click selects one, a muted line at its place.
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        expect(`.o_erplibre_studio_outline_row[data-path="${WARNING}"]`).toHaveCount(0);
        expect(`.o_erplibre_studio_outline_row[data-path="${named("job")}"]`).toHaveCount(0);
        await contains(".o_erplibre_studio_outline_filter").edit("Job");
        await contains(
            `.o_erplibre_studio_outline_row[data-path="${named("job")}"] .o_erplibre_studio_outline_pick`
        ).click();
        expect(line("job")).toHaveClass(["o_erplibre_studio_muted_line", "o_erplibre_studio_selected"]);
        expect(`${line("job")} > .o_erplibre_studio_pick`).toHaveText("Job title");
        // Selected elsewhere, it leaves the canvas again.
        await contains(line("sector")).click();
        expect(line("job")).toHaveCount(0);
    });

    test("Detailed: one folded line « shown when … » per node hidden on the sample", async () => {
        await openEditor();
        await contains(DETAILED).click();
        expect(at(WARNING)).toHaveClass("o_erplibre_studio_muted_line");
        const warning = `${at(WARNING)} > .o_erplibre_studio_container_title .o_erplibre_studio_pick`;
        expect(warning).toHaveText(/^<div> warning\s*· shown when twin_id$/);
        expect(warning).toHaveAttribute("aria-label", "warning, shown when twin_id");
        // Folded: the field under it is not drawn.
        expect(line("twin_id")).toHaveCount(0);
        expect(line("job")).toHaveClass("o_erplibre_studio_muted_line");
        expect(`${line("job")} .o_erplibre_studio_shown_when`).toHaveText("· shown when not is_company");
        expect(at(PERSON_NAME)).toHaveClass("o_erplibre_studio_muted_line");
        expect(`${line("sector")}`).not.toHaveClass("o_erplibre_studio_muted_line");
        // Every tab shows at the Detailed level.
        expect(`.o_erplibre_studio_page_tab[data-path="${PRIVATE}"]`).toHaveCount(1);
        // The selection under a folded node opens it.
        await contains(".o_erplibre_studio_left_tab[data-panel=plan]").click();
        await contains(
            `.o_erplibre_studio_outline_row[data-path="${named("twin_id")}"] .o_erplibre_studio_outline_pick`
        ).click();
        expect(at(WARNING)).not.toHaveClass("o_erplibre_studio_muted_line");
        expect(line("twin_id")).toHaveClass("o_erplibre_studio_selected");
    });

    test("without sample record every node draws, as before", async () => {
        answer = payload({sample_res_id: false, sample_values: {}, sample_record: {}});
        await openEditor();
        expect(at(WARNING)).toHaveCount(1);
        expect(at(COMPANY_NAME)).toHaveCount(1);
        expect(at(PERSON_NAME)).toHaveCount(1);
        expect(line("job")).toHaveCount(1);
        expect(`.o_erplibre_studio_page_tab[data-path="${PRIVATE}"]`).toHaveCount(1);
        // No value: the placeholder of a label-less field, else its label.
        expect(`${at(COMPANY_NAME)} .o_erplibre_studio_placeholder`).toHaveText("Company name");
        expect(`${line("zip")} .o_erplibre_studio_placeholder`).toHaveText("Zip");
    });

    test("the widgets draw as themselves: picture, radio, checkbox, tags, one line", async () => {
        await openEditor();
        expect(`${line("picture")} .o_erplibre_studio_sample_image`).toHaveAttribute("aria-label", "Picture");
        expect(`${line("picture")} .o_erplibre_studio_placeholder`).toHaveCount(0);
        // A radio: its options, the value of the record checked.
        expect(`${line("kind")} .o_erplibre_studio_radio_option`).toHaveCount(2);
        expect(`${line("kind")} .o_erplibre_studio_radio_option[data-checked=true]`).toHaveText("Company");
        expect(`${line("kind")} .o_erplibre_studio_radio_option[data-checked=false]`).toHaveText("Individual");
        // A boolean: a checkbox.
        expect(`${line("is_company")} .o_erplibre_studio_sample_check`).toHaveAttribute("data-checked", "true");
        // Tags: the names given, then the count of the others.
        expect(`${line("labels")} .o_erplibre_studio_sublist`).toHaveCount(0);
        expect(`${line("labels")} .o_erplibre_studio_sample_tag`).toHaveCount(6);
        expect(`${line("labels")} .o_erplibre_studio_sample_more`).toHaveText("+2");
        // An email: one line, its full text in the tooltip.
        const email = `${line("email")} .o_erplibre_studio_sample_value`;
        expect(email).toHaveClass("o_erplibre_studio_one_line");
        expect(email).toHaveAttribute("title", "orders.desk@invented-works.example");
        // The title keeps its lines.
        expect(`${at(COMPANY_NAME)} .o_erplibre_studio_sample_value`).toHaveText("Invented Works");
        expect(`${at(COMPANY_NAME)} .o_erplibre_studio_sample_value`).not.toHaveClass("o_erplibre_studio_one_line");
    });

    test("a radio checks the key of the value when the payload gives it", async () => {
        answer = payload({sample_record: {is_company: true, twin_id: false, kind: "person"}});
        await openEditor();
        expect(`${line("kind")} .o_erplibre_studio_radio_option[data-checked=true]`).toHaveText("Individual");
    });

    test("a label-less field: its value, else its placeholder greyed, else its label", async () => {
        await openEditor();
        expect(`${line("street")}`).toHaveClass("o_erplibre_studio_bare");
        expect(`${line("street")} .o_erplibre_studio_sample_value`).toHaveText("12 Invented Road");
        expect(`${line("street")} .o_erplibre_studio_placeholder`).toHaveCount(0);
        expect(`${line("city")} .o_erplibre_studio_placeholder_text`).toHaveText("City");
        expect(`${line("city")} .o_erplibre_studio_sample_value`).toHaveCount(0);
        expect(`${line("zip")} .o_erplibre_studio_placeholder`).toHaveText("Zip");
        // The button keeps its name: the label and the technical name.
        expect(`${line("city")} > .o_erplibre_studio_pick`).toHaveAttribute("aria-label", "Field City (city)");
    });

    test("an empty box of smart buttons takes no height at the Simple level", async () => {
        await openEditor();
        expect(at(BOX)).toHaveClass("o_erplibre_studio_empty_box");
        await contains(DETAILED).click();
        expect(at(BOX)).not.toHaveClass("o_erplibre_studio_empty_box");
    });

    test("a sub-list reads « label · N record(s) », its comodel at the Detailed level", async () => {
        await openEditor();
        const sublist = `${line("member_ids")} .o_erplibre_studio_sublist`;
        expect(sublist).toHaveText(/^Members\s*·\s*3 record\(s\)$/);
        expect(`${sublist} code`).toHaveCount(0);
        // No label above it: it names its field.
        expect(`${line("member_ids")} > .o_erplibre_studio_pick .o_erplibre_studio_placeholder`).toHaveCount(0);
        await contains(DETAILED).click();
        expect(`${sublist} code`).toHaveText("res.partner");
        expect(sublist).toHaveText(/^Members\s*res\.partner\s*·\s*3 record\(s\)$/);
    });
});
