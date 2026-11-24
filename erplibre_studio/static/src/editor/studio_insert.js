/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onMounted, useExternalListener, useRef, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {_t} from "@web/core/l10n/translation";
import {LAYOUT_ITEMS, paletteFieldTypes} from "./studio_palette";
import {allBlocks, isGhost, searchText, typeGlyph} from "./studio_utils";

// The glyph of a layout item of the list, by its kind.
const LAYOUT_GLYPHS = {group: "▦", page: "▤", separator: "—"};
// A number that makes the ids of each list unique on the page.
let nextListId = 1;

/**
 * The list a « + » of the margin of a form opens at its hook (rule 5:
 * insert without dragging). ``insert`` is the place it inserts at, as
 * ``StudioEditor.openInsert`` sets it: {target, position, zone, key,
 * where, container, from}.
 *
 * A search input (a combobox) keeps the focus; the options of its listbox
 * come in groups: the existing fields the form does not show yet (those of
 * the palette, then the fields the draft hides in the form, which come
 * back at this place), the new field types the form takes (« Create
 * « text » as… » once a text is typed: the new field takes it as its
 * label), and the layout elements the hook takes. Up and Down move the
 * active option across the groups (Home and End, while the search is
 * empty, to the first and the last), Enter inserts it; Escape anywhere
 * in the list closes it and gives the focus back to its « + », or to the
 * row of the plan that opened it; the pointer moves the active
 * option and a click inserts it. The insertion runs through
 * ``StudioEditor.insertAt``, as a drop on the hook does.
 *
 * A click inside the list stays in it; a pointer pressed outside it closes
 * it, except on a « + », whose click opens its own list.
 */
export class StudioInsertList extends Component {
    static template = "erplibre_studio.InsertList";
    static props = {
        editor: Object,
        insert: Object,
    };

    setup() {
        this.editorState = useState(this.props.editor.state);
        this.state = useState({query: "", active: 0});
        this.rootRef = useRef("root");
        this.inputRef = useRef("input");
        this.uid = `o_erplibre_studio_insert_${nextListId++}`;
        onMounted(() => {
            if (this.inputRef.el) {
                this.inputRef.el.focus();
            }
            if (this.rootRef.el && this.rootRef.el.scrollIntoView) {
                this.rootRef.el.scrollIntoView({block: "nearest"});
            }
        });
        useExternalListener(window, "pointerdown", (ev) => this.onWindowPointerDown(ev), {capture: true});
    }

    get editor() {
        return this.props.editor;
    }

    get insert() {
        return this.props.insert;
    }

    get data() {
        return this.editorState.data || {};
    }

    /** Whether the options show the technical names (the Detailed level). */
    get detailed() {
        return this.editorState.level === "detailed";
    }

    get query() {
        return searchText(this.state.query.trim());
    }

    /** The text typed, as the label of a new field. */
    get typed() {
        return this.state.query.trim();
    }

    get title() {
        return _t("Insert in %(container)s, %(where)s", {
            container: this.insert.container,
            where: this.insert.where,
        });
    }

    /** Whether the hook of the list takes ``item`` (``StudioEditor.accepts``). */
    takes(item) {
        const {target, position, zone} = this.insert;
        return this.editor.accepts(item, zone, target, position);
    }

    hits(...texts) {
        const query = this.query;
        return !query || texts.some((text) => searchText(text).includes(query));
    }

    /**
     * The existing fields the hook takes and the search matches: those of
     * the palette, then the fields the draft hides in the form (an
     * element the draft hides keeps its node: it comes back here).
     */
    get existingOptions() {
        const options = [];
        for (const field of this.data.palette || []) {
            const item = {kind: "existing", name: field.name, axes: field.axes, special: field.special};
            if (this.hits(field.string, field.name) && this.takes(item)) {
                options.push({
                    key: `existing:${field.name}`,
                    item,
                    label: field.string,
                    name: field.name,
                    glyph: typeGlyph(field.type),
                    note: "",
                });
            }
        }
        const fields = this.data.fields || {};
        for (const block of allBlocks(this.data.blocks)) {
            if (block.kind !== "field" || !isGhost(block, "form")) {
                continue;
            }
            const label = block.label || block.name;
            if (this.hits(label, block.name)) {
                options.push({
                    key: `ghost:${block.path}`,
                    item: {kind: "ghost", path: block.path, name: block.name, label},
                    label,
                    name: block.name,
                    glyph: typeGlyph((fields[block.name] || {}).type),
                    note: _t("hidden by this draft"),
                });
            }
        }
        return options;
    }

    /** The new field types the hook takes: the text typed becomes the label of the new field. */
    get newOptions() {
        if (!(this.data.operations || []).includes("add_field")) {
            return [];
        }
        const label = this.typed;
        return paletteFieldTypes(this.data.field_types, "form")
            .map((type) => ({
                key: `new:${type.ttype}`,
                item: label ? {kind: "new", ttype: type.ttype, label} : {kind: "new", ttype: type.ttype},
                label: type.label,
                name: "",
                glyph: type.glyph,
                note: "",
            }))
            .filter((option) => this.takes(option.item));
    }

    /** The layout elements the view allows and the hook takes, the search matching their label. */
    get layoutOptions() {
        const operations = this.data.operations || [];
        const labels = {group: _t("Group"), page: _t("Tab"), separator: _t("Separator")};
        return LAYOUT_ITEMS.filter((layout) => operations.includes(layout.operation))
            .map((layout) => ({
                key: `layout:${layout.kind}`,
                item: {kind: layout.kind},
                label: labels[layout.kind],
                name: "",
                glyph: LAYOUT_GLYPHS[layout.kind],
                note: "",
            }))
            .filter((option) => this.hits(option.label) && this.takes(option.item));
    }

    /**
     * The groups of the listbox: [{key, title, chips, options}], each
     * option with its ``index`` among all the options and its ``id``.
     */
    get groups() {
        const typed = this.typed;
        const groups = [
            {key: "existing", title: _t("Existing fields"), chips: false, options: this.existingOptions},
            {
                key: "new",
                title: typed ? _t("Create « %(text)s » as…", {text: typed}) : _t("New field…"),
                chips: true,
                options: this.newOptions,
            },
            {key: "layout", title: _t("Layout"), chips: true, options: this.layoutOptions},
        ].filter((group) => group.options.length);
        let index = 0;
        for (const group of groups) {
            group.id = `${this.uid}_${group.key}`;
            for (const option of group.options) {
                option.index = index;
                option.id = `${this.uid}_${index}`;
                index += 1;
            }
        }
        return groups;
    }

    get options() {
        return this.groups.flatMap((group) => group.options);
    }

    /** The index of the active option, within the options shown. */
    activeIndex(options) {
        return Math.max(0, Math.min(this.state.active, options.length - 1));
    }

    /** Whether the search leaves no existing field: a line says so. */
    get noExisting() {
        return Boolean(this.query) && !this.existingOptions.length;
    }

    get listId() {
        return `${this.uid}_list`;
    }

    onInput(ev) {
        this.state.query = ev.target.value;
        this.state.active = 0;
    }

    /** The keys of the search input (see the class). */
    onKeydown(ev) {
        const options = this.options;
        const active = this.activeIndex(options);
        switch (ev.key) {
            case "ArrowDown":
                this.state.active = Math.min(options.length - 1, active + 1);
                break;
            case "ArrowUp":
                this.state.active = Math.max(0, active - 1);
                break;
            case "Home":
            case "End":
                if (this.state.query) {
                    return;
                }
                this.state.active = ev.key === "Home" ? 0 : options.length - 1;
                break;
            case "Enter":
                if (options[active]) {
                    this.pick(options[active]);
                }
                break;
            default:
                return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(ev.key)) {
            this.scrollToActive();
        }
    }

    /**
     * Escape on any element of the list (its input, its Close button)
     * closes it, before the canvas or the plan around it reads the key.
     */
    onRootKeydown(ev) {
        if (ev.key !== "Escape" || ev.altKey || ev.ctrlKey || ev.metaKey || ev.shiftKey) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.close();
    }

    /** Bring the active option on screen once it renders. */
    scrollToActive() {
        browser.requestAnimationFrame(() => {
            const el = this.rootRef.el && this.rootRef.el.querySelector("[role=option][aria-selected=true]");
            if (el && el.scrollIntoView) {
                el.scrollIntoView({block: "nearest"});
            }
        });
    }

    /** A click or a mousedown that stays in the list: its modifier does the work. */
    stay() {}

    hover(option) {
        if (this.state.active !== option.index) {
            this.state.active = option.index;
        }
    }

    pick(option) {
        this.editor.insertAt(option.item);
    }

    /** Close the list; the focus goes back to what opened it (``closeInsert``). */
    close() {
        this.editor.closeInsert({focus: true});
    }

    /**
     * A pointer pressed outside the list closes it; on a « + » of the
     * margin or of the plan, its click decides (``toggleInsert``).
     */
    onWindowPointerDown(ev) {
        const root = this.rootRef.el;
        const target = ev.target;
        if (!root || !target || root.contains(target)) {
            return;
        }
        if (target.closest && target.closest(".o_erplibre_studio_insert, .o_erplibre_studio_outline_add")) {
            return;
        }
        this.editor.closeInsert();
    }
}
