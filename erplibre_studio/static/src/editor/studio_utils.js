/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {serializeDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

const {DateTime} = luxon;

// The helpers of the editor and of its parts (canvas, palette, inspector):
// labels, the tree of blocks of a payload, the drop hooks. No component and
// no service: the tests import them from studio_editor.js, which re-exports
// them.

// The model whose methods the editor calls.
export const MODEL = "erplibre.studio.editor";
export const DRAGGING_CLASS = "o_erplibre_studio_dragging";

const TRUE_VALUES = ["1", "True", "true"];
// The view types whose fields show from a QWeb template.
export const TEMPLATED_TYPES = ["kanban", "timeline"];
export const DATE_TYPES = ["date", "datetime"];
export const NUMBER_TYPES = ["integer", "float", "monetary"];
// The options of a new field set before Apply, and the types that take
// each one: the FIELD_OPTIONS of the server (erplibre_studio_project.py).
export const FIELD_OPTIONS = {
    translate: ["char", "text", "html"],
    index: ["char", "integer", "float", "boolean", "date", "datetime", "selection", "many2one", "monetary"],
    size: ["char"],
};

// The largest maximum size of a new char (MAX_FIELD_SIZE of the server).
export const MAX_FIELD_SIZE = 10000;

/** {translate, index, size}: whether a field of ``ttype`` takes each option. */
export function fieldOptions(ttype) {
    return Object.fromEntries(Object.entries(FIELD_OPTIONS).map(([key, types]) => [key, types.includes(ttype)]));
}

// The ribbon colors offered for a new ribbon: bootstrap classes.
export const RIBBON_COLORS = [
    "text-bg-success",
    "text-bg-danger",
    "text-bg-warning",
    "text-bg-info",
    "text-bg-primary",
    "text-bg-secondary",
];

/** The label of a new field type. */
export function fieldTypeLabel(ttype) {
    return (
        {
            char: _t("Text"),
            integer: _t("Integer"),
            float: _t("Decimal"),
            boolean: _t("Checkbox"),
            date: _t("Date"),
            datetime: _t("Date and time"),
            selection: _t("Selection"),
            many2one: _t("Many2one"),
            text: _t("Multiline text"),
            html: _t("HTML"),
            monetary: _t("Monetary"),
            one2many: _t("One2many"),
            many2many: _t("Many2many"),
        }[ttype] || ttype
    );
}

// The glyph of a field type, in the palette and the plan: a short text, so
// that it follows the colors of the theme.
const TYPE_GLYPHS = {
    char: "Aa",
    text: "¶",
    html: "</>",
    integer: "12",
    float: "1.5",
    monetary: "$",
    boolean: "✓",
    date: "D",
    datetime: "DT",
    selection: "≡",
    many2one: "→",
    one2many: "⊞",
    many2many: "⇄",
};

/** The glyph of the field type ``ttype``. */
export function typeGlyph(ttype) {
    return TYPE_GLYPHS[ttype] || "•";
}

// The kinds of changes a canvas block shows as a tag, in this order; the
// other kinds (« moved », « attribute ») show as a dot.
export const CHANGE_TAGS = ["new", "renamed", "hidden"];

/** The label of a kind of change of a block (``change_kinds`` of a block). */
export function changeKindLabel(kind) {
    return (
        {
            new: _t("new"),
            renamed: _t("renamed"),
            hidden: _t("hidden"),
            moved: _t("moved"),
            attribute: _t("edited"),
        }[kind] || kind
    );
}

/** ``text`` in lower case without accents, as a filter compares it. */
export function searchText(text) {
    return (text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "");
}

/**
 * The blocks from ``root`` down to the block at ``path``, both included;
 * [] when no block of ``root`` has that path.
 */
export function blockTrail(root, path) {
    if (!root || !path) {
        return [];
    }
    if (root.path === path) {
        return [root];
    }
    for (const child of root.children || []) {
        const trail = blockTrail(child, path);
        if (trail.length) {
            return [root, ...trail];
        }
    }
    return [];
}

/**
 * Whether ``block`` can be dragged in a view of ``viewType``: what the
 * server lets move, and in a form or a list only the fields and the other
 * leaves.
 */
export function canDragBlock(block, viewType) {
    if (block.movable === false) {
        return false;
    }
    if (["field", "widget", "filter", "group_by", "separator"].includes(block.kind)) {
        return true;
    }
    return TEMPLATED_TYPES.includes(viewType);
}

/** Whether ``block`` can be selected: any block but a QWeb template. */
export function canSelectBlock(block) {
    return block.kind !== "template";
}

/** The label of a settable view attribute (``settable`` of the payload). */
export function attributeLabel(attribute) {
    return (
        {
            default_group_by: _t("Default grouping"),
            default_order: _t("Default order"),
            quick_create: _t("Quick create"),
            group_create: _t("Add columns"),
            group_delete: _t("Delete columns"),
            group_edit: _t("Edit columns"),
            records_draggable: _t("Drag the records"),
            archivable: _t("Archive the records of a column"),
            widget: _t("Widget"),
            options: _t("Options"),
            domain: _t("Domain"),
            groups: _t("Visible for groups"),
            disable_linking: _t("No link to the records"),
            display_quantity: _t("Show the count"),
            type: _t("Axis"),
            interval: _t("Interval"),
            date_start: _t("Start date"),
            date_stop: _t("End date"),
            date_delay: _t("Duration"),
            colors: _t("Colors"),
            mode: _t("Default scale"),
            stack: _t("Stack the items"),
            event_open_popup: _t("Open the records in a dialog"),
        }[attribute] || attribute
    );
}

/** The label of a fixed value of an attribute, by the kind of the attribute. */
export function valueLabel(kind, value) {
    const labels = {
        bool: {True: _t("Yes"), False: _t("No")},
        axis: {row: _t("Row"), col: _t("Column"), measure: _t("Measure")},
        interval: {day: _t("Day"), week: _t("Week"), month: _t("Month"), quarter: _t("Quarter"), year: _t("Year")},
        timeline_mode: {day: _t("Day"), week: _t("Week"), month: _t("Month"), fit: _t("Fit")},
    }[kind];
    return (labels && labels[value]) || null;
}

/** Whether a node attribute holds a constant true expression. */
export function isTrue(value) {
    return TRUE_VALUES.includes(value);
}

/** The first block of the tree ``root`` that ``predicate`` accepts, or null. */
export function findBlock(root, predicate) {
    if (!root) {
        return null;
    }
    if (predicate(root)) {
        return root;
    }
    for (const child of root.children || []) {
        const found = findBlock(child, predicate);
        if (found) {
            return found;
        }
    }
    return null;
}

/** Every block of the tree ``root``, depth first. */
export function allBlocks(root) {
    const blocks = [];
    const visit = (block) => {
        blocks.push(block);
        for (const child of block.children || []) {
            visit(child);
        }
    };
    if (root) {
        visit(root);
    }
    return blocks;
}

/** The « kind:name » keys of the named blocks of ``root``. */
export function namedKeys(root) {
    return new Set(
        allBlocks(root)
            .filter((b) => b.name)
            .map((b) => `${b.kind}:${b.name}`)
    );
}

/**
 * The blocks of a search view by column: {fields, filters, group_bys}, in
 * the order of the arch. A separator goes with the filters or the
 * group-bys it separates.
 */
export function searchColumns(root) {
    const columns = {fields: [], filters: [], group_bys: []};
    const visit = (block) => {
        let column = "filters";
        for (const child of block.children || []) {
            if (child.kind === "field") {
                columns.fields.push(child);
            } else if (child.kind === "filter" || child.kind === "group_by") {
                column = child.kind === "filter" ? "filters" : "group_bys";
                columns[column].push(child);
            } else if (child.kind === "separator") {
                columns[column].push(child);
            } else if (child.children) {
                visit(child);
            }
        }
    };
    visit(root || {});
    return columns;
}

/** The field blocks of a pivot view by axis: {row, col, measure, others}. */
export function pivotLanes(data) {
    const layout = data.layout || {};
    const axes = layout.axes || {};
    const byPath = (path) => findBlock(data.blocks, (b) => b.path === path);
    const lane = (paths) => (paths || []).map(byPath).filter(Boolean);
    return {row: lane(axes.row), col: lane(axes.col), measure: lane(axes.measure), others: lane(layout.others)};
}

/** The axes a field described by ``info`` (``fields_get``) can go on. */
export function pivotAxes(info) {
    const axes = info && info.groupable ? ["row", "col"] : [];
    if (info && NUMBER_TYPES.includes(info.type) && info.aggregator) {
        axes.push("measure");
    }
    return axes;
}

/**
 * [[name, label]] of the field widgets of the registry that show a field of
 * ``ttype``; a widget proper to one view type (« list.many2one ») is left
 * out.
 */
export function fieldWidgets(ttype) {
    return registry
        .category("fields")
        .getEntries()
        .filter(([name, widget]) => !name.includes(".") && (widget.supportedTypes || []).includes(ttype))
        .map(([name, widget]) => [name, widget.displayName ? `${widget.displayName} (${name})` : name])
        .sort((a, b) => a[1].localeCompare(b[1]));
}

/** « value:Label » lines <-> [[value, label]]. */
export function selectionToText(selection) {
    return (selection || []).map(([value, label]) => `${value}:${label}`).join("\n");
}

export function textToSelection(text) {
    return (text || "")
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
            const index = line.indexOf(":");
            return index < 0 ? [line, line] : [line.slice(0, index).trim(), line.slice(index + 1).trim()];
        });
}

/**
 * The value an input of a filter condition holds, as the server reads it.
 * A datetime input gives the local time « YYYY-MM-DDTHH:MM »; a domain
 * compares a datetime in UTC, « YYYY-MM-DD HH:MM:SS ».
 */
export function conditionValue(type, value) {
    if (type === "datetime" && value) {
        const local = DateTime.fromISO(value);
        return local.isValid ? serializeDateTime(local) : value;
    }
    return value;
}

/** The hook after the last block of ``blocks``, else inside ``fallback``. */
export function endHook(blocks, fallback) {
    const last = blocks[blocks.length - 1];
    return last ? {target: last.path, position: "after"} : {target: fallback, position: "inside"};
}

/**
 * The hook at the end of the column ``column`` of the search view
 * ``root``: after its last block, else inside the view, or inside its
 * group of group-bys for the column « group_bys ».
 */
export function searchEndHook(root, column) {
    let fallback = root.path;
    if (column === "group_bys") {
        const group = findBlock(root, (b) => b.kind === "container" && b.tag === "group");
        fallback = group ? group.path : fallback;
    }
    return endHook(searchColumns(root)[column], fallback);
}
