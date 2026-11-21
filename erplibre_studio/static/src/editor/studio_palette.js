/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {fieldTypeFits} from "./studio_relations";
import {RIBBON_COLORS, fieldTypeLabel, searchText, typeGlyph, valueLabel} from "./studio_utils";

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

    get editor() {
        return this.props.editor;
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

    /**
     * The new field types the view offers, the common ones first: an
     * x2many only where it shows. [{ttype, label, glyph}]
     */
    get fieldTypes() {
        const rank = (ttype) => {
            const index = COMMON_TYPES.indexOf(ttype);
            return index < 0 ? COMMON_TYPES.length : index;
        };
        return (this.data.field_types || [])
            .filter((ttype) => fieldTypeFits(ttype, this.viewType))
            .map((ttype, index) => ({ttype, index, label: fieldTypeLabel(ttype), glyph: typeGlyph(ttype)}))
            .sort((a, b) => rank(a.ttype) - rank(b.ttype) || a.index - b.index);
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
     * left them, else when the view offers no new field type.
     */
    get existingOpen() {
        if (this.query) {
            return true;
        }
        const existing = this.palette.existing;
        return existing === null || existing === undefined ? !this.allows("add_field") : existing;
    }

    toggleExisting() {
        this.palette.existing = !this.existingOpen;
    }

    /** Whether the palette offers the interval of a date grouping. */
    get offersInterval() {
        return ["search", "pivot"].includes(this.viewType);
    }

    get intervals() {
        return ((this.data.choices || {}).interval || []).map(([value, label]) => [
            value,
            valueLabel("interval", value) || label,
        ]);
    }

    axisLabel(axis) {
        return valueLabel("axis", axis) || axis;
    }

    startDrag(ev, item) {
        this.editor.startDrag(ev, item);
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
