/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {fieldTypeFits} from "./studio_relations";
import {GEO_TYPES, RIBBON_COLORS, newFieldLabel, searchText, typeGlyph, valueLabel} from "./studio_utils";

// The new field types the palette shows first, in this order; the others
// show after them once the user asks for them.
export const COMMON_TYPES = ["char", "integer", "float", "boolean", "date", "selection", "many2one", "many2many"];
// How many types the palette shows before « Show the other types ».
export const SHOWN_TYPES = 8;
// The items of the section « Layout »: the operation each one needs, its
// class (the separator keeps the one it had in « Other ») and its icon.
export const LAYOUT_ITEMS = [
    {kind: "group", operation: "add_group", className: "o_erplibre_studio_layout_group", icon: "fa-square-o"},
    {kind: "page", operation: "add_page", className: "o_erplibre_studio_layout_page", icon: "fa-folder-o"},
    {kind: "separator", operation: "add_separator", className: "o_erplibre_studio_separator", icon: "fa-minus"},
];

/**
 * The new field types of ``fieldTypes`` (the « field_types » of the
 * payload) a view of ``viewType`` offers, the common ones first: an
 * x2many only where it shows. The geometry types are one item,
 * « Geometry », that drops a point; the inspector changes its shape.
 * [{ttype, index, label, glyph}]
 */
export function paletteFieldTypes(fieldTypes, viewType) {
    const rank = (ttype) => {
        const index = COMMON_TYPES.indexOf(ttype);
        return index < 0 ? COMMON_TYPES.length : index;
    };
    return (fieldTypes || [])
        .filter((ttype) => fieldTypeFits(ttype, viewType))
        .filter((ttype) => !GEO_TYPES.includes(ttype) || ttype === GEO_TYPES[0])
        .map((ttype, index) => ({ttype, index, label: newFieldLabel(ttype), glyph: typeGlyph(ttype)}))
        .sort((a, b) => rank(a.ttype) - rank(b.ttype) || a.index - b.index);
}

/**
 * The palette of the editor, one column of sections: a search box, the new
 * field types, the existing fields (a section that folds), the layout
 * items (a group, a tab, a separator) and the other items (a ribbon) that
 * drag onto the canvas. Each item is a draggable div that holds a
 * ``<button class="o_erplibre_studio_pick">``: the button is the tab stop
 * and the accessible name for the keyboard and assistive technology, and
 * takes no pointer event, so the mouse reaches the div and a drag starts
 * there in every browser. A drag goes through the editor ``editor``; a
 * click on the div, or Enter or Space on its button (whose click bubbles
 * to the div), adds the item without a drag (``editor.addFromPalette``).
 * ``palette`` is the state of the palette the editor keeps across its
 * panels: {filter, existing, more, interval, ribbon}; ``existing`` is
 * null until the user folds or unfolds the existing fields, ``more``
 * shows every type; a drop reads its interval and its ribbon.
 */
export class StudioPalette extends Component {
    static template = "erplibre_studio.Palette";
    static props = {
        editor: Object,
        // The payload of the editor (get_editor_data).
        data: Object,
        viewType: String,
        palette: Object,
    };

    setup() {
        this.editorState = useState(this.props.editor.state);
    }

    get editor() {
        return this.props.editor;
    }

    /** Whether the existing fields show their technical names (the Detailed level). */
    get detailed() {
        return this.editorState.level === "detailed";
    }

    /** The accessible name of the existing field ``item``: its technical name at the Detailed level only. */
    existingItemLabel(item) {
        const label = this.detailed ? `${item.string} (${item.name})` : item.string;
        return this.focusItemLabel("existing", label) || this.itemLabel(label);
    }

    get data() {
        return this.props.data;
    }

    get viewType() {
        return this.props.viewType;
    }

    get palette() {
        return this.props.palette;
    }

    get ribbonColors() {
        return RIBBON_COLORS;
    }

    get ribbonLabel() {
        return _t("Ribbon");
    }

    allows(operation) {
        return (this.data.operations || []).includes(operation);
    }

    /** The LAYOUT_ITEMS the view allows, with their label. */
    get layoutItems() {
        const labels = {group: _t("Group"), page: _t("Tab"), separator: _t("Separator")};
        return LAYOUT_ITEMS.filter((item) => this.allows(item.operation)).map((item) => ({
            ...item,
            label: labels[item.kind],
            className: `o_erplibre_studio_layout_item ${item.className}`,
        }));
    }

    get query() {
        return searchText(this.palette.filter.trim());
    }

    /** The new field types the view offers (``paletteFieldTypes``). */
    get fieldTypes() {
        return paletteFieldTypes(this.data.field_types, this.viewType);
    }

    /**
     * The types the palette shows: those the search matches, else the
     * first SHOWN_TYPES unless the user asked for all of them.
     */
    get shownTypes() {
        const types = this.fieldTypes;
        if (this.query) {
            return types.filter((t) => searchText(`${t.label} ${t.ttype}`).includes(this.query));
        }
        return this.palette.more ? types : types.slice(0, SHOWN_TYPES);
    }

    /** Whether the types fold past SHOWN_TYPES: not while searching. */
    get foldsTypes() {
        return !this.query && this.fieldTypes.length > SHOWN_TYPES;
    }

    get moreTypesLabel() {
        return _t("Show the %(count)s other types", {count: this.fieldTypes.length - SHOWN_TYPES});
    }

    toggleMore() {
        this.palette.more = !this.palette.more;
    }

    get existingFields() {
        const query = this.query;
        return (this.data.palette || []).filter(
            (f) => !query || searchText(f.name).includes(query) || searchText(f.string).includes(query)
        );
    }

    get existingLabel() {
        return _t("Existing fields · %(count)s", {count: (this.data.palette || []).length});
    }

    /**
     * Whether the existing fields show: while searching, else as the user
     * left them, else when the view offers no new field type or is a map,
     * whose lanes mostly take existing fields.
     */
    get existingOpen() {
        if (this.query) {
            return true;
        }
        const existing = this.palette.existing;
        if (existing === null || existing === undefined) {
            return !this.allows("add_field") || this.viewType === "leaflet_map";
        }
        return existing;
    }

    toggleExisting() {
        this.palette.existing = !this.existingOpen;
    }

    /** Whether the palette offers the interval of a date grouping. */
    get offersInterval() {
        return ["search", "pivot", "graph"].includes(this.viewType);
    }

    get intervals() {
        return ((this.data.choices || {}).interval || []).map(([value, label]) => [
            value,
            valueLabel("interval", value) || label,
        ]);
    }

    /** The label of the axis ``axis`` a field can go on, by view type. */
    axisLabel(axis) {
        return valueLabel(this.viewType === "graph" ? "graph_axis" : "axis", axis) || axis;
    }

    startDrag(ev, item) {
        this.editor.startDrag(ev, item);
    }

    /**
     * Where a click adds an item while the focus is on a block of a form:
     * {block, where}, the label of the block and « after « label » » for
     * its selected element that is no container (``focusSelectedLeaf``),
     * else « at the end of the block »; null when the focus is off.
     */
    get focusTarget() {
        // Read through the state of the palette: a change of the focus, of
        // the selection or of the level renders the palette again.
        const {focus, selected, level} = this.editorState;
        if (!focus.on || !focus.path) {
            return null;
        }
        const entry = this.editor.focusEntry;
        if (!entry) {
            return null;
        }
        const leaf = selected ? this.editor.focusSelectedLeaf : null;
        return {
            block: entry.label,
            where: leaf
                ? _t("after « %(label)s »", {label: this.editor.blockLabel(leaf, level === "detailed")})
                : _t("at the end of the block"),
        };
    }

    /**
     * What a click on an item does while the focus is on a block of a
     * form, as its accessible name and its tooltip: « Add a Text field in
     * Sales » for a new field type (``kind`` « new », ``label`` its type),
     * « Add Phone in Sales » for an existing field, « Add a group in
     * Sales » or « Add a separator in Sales »; null when the focus is off,
     * and for a tab and a ribbon, which never go into the block.
     */
    focusItemLabel(kind, label) {
        const target = this.focusTarget;
        if (!target) {
            return null;
        }
        const block = target.block;
        if (kind === "new") {
            return _t("Add a %(type)s field in %(block)s", {type: label, block});
        }
        if (kind === "existing") {
            return _t("Add %(item)s in %(block)s", {item: label, block});
        }
        if (kind === "group") {
            return _t("Add a group in %(block)s", {block});
        }
        if (kind === "separator") {
            return _t("Add a separator in %(block)s", {block});
        }
        return null;
    }

    /** The accessible name of the new field type ``item``: the block in focus when the focus is on. */
    newItemLabel(item) {
        return this.focusItemLabel("new", item.label) || this.itemLabel(item.label);
    }

    /** The tooltip of the new field type ``item``: its type, or what a click does in focus. */
    newItemTitle(item) {
        return this.focusItemLabel("new", item.label) || item.label;
    }

    /** The tooltip of the existing field ``item``: what a click does in focus, else its type at the Detailed level. */
    existingItemTitle(item) {
        return this.focusItemLabel("existing", item.string) || (this.detailed ? item.type : false);
    }

    /** The accessible name of the layout item ``item``: the block in focus when it goes there. */
    layoutItemLabel(item) {
        return this.focusItemLabel(item.kind, item.label) || this.itemLabel(item.label);
    }

    /** Add ``item`` without a drag. */
    add(item) {
        this.editor.addFromPalette(item);
    }

    /** The accessible name of an item: what it is, and that it adds it. */
    itemLabel(label) {
        return _t("Add %(item)s", {item: label});
    }

    endDrag() {
        this.editor.endDrag();
    }
}
