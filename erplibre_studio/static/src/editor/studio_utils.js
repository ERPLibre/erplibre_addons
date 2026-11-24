/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {serializeDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {evaluateBooleanExpr} from "@web/core/py_js/py";
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
export const TEMPLATED_TYPES = ["kanban", "timeline", "hierarchy", "activity", "geoengine"];
export const DATE_TYPES = ["date", "datetime"];
export const NUMBER_TYPES = ["integer", "float", "monetary"];
// The options of a new field set before Apply, and the types that take
// each one: the FIELD_OPTIONS of the server (erplibre_studio_project.py).
export const FIELD_OPTIONS = {
    translate: ["char", "text", "html"],
    index: ["char", "integer", "float", "boolean", "date", "datetime", "selection", "many2one", "monetary"],
    size: ["char"],
};

// The geometry field types of base_geoengine (GEO_TYPES of the server), in
// the order the inspector lists their shapes. The palette offers them as one
// item, « Geometry », that drops a point; a geometry field shows in a form
// only.
export const GEO_TYPES = [
    "geo_point",
    "geo_multi_point",
    "geo_line",
    "geo_multi_line",
    "geo_polygon",
    "geo_multi_polygon",
];

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
            json: _t("JSON"),
            properties: _t("Properties"),
            monetary: _t("Monetary"),
            one2many: _t("One2many"),
            many2many: _t("Many2many"),
            geo_point: _t("Point"),
            geo_multi_point: _t("Multi-point"),
            // « Line » is a chart type, translated in the plural.
            geo_line: _t("Polyline"),
            geo_multi_line: _t("Multi-polyline"),
            geo_polygon: _t("Polygon"),
            geo_multi_polygon: _t("Multi-polygon"),
        }[ttype] || ttype
    );
}

/**
 * The label a new field of ``ttype`` takes when dropped, which proposes its
 * name: « Geometry » for a geometry field, whose shape changes until Apply.
 */
export function newFieldLabel(ttype) {
    return GEO_TYPES.includes(ttype) ? _t("Geometry") : fieldTypeLabel(ttype);
}

// The glyph of a field type, in the palette and the plan: a short text, so
// that it follows the colors of the theme.
const TYPE_GLYPHS = {
    char: "Aa",
    text: "¶",
    html: "</>",
    json: "{}",
    properties: "☰",
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
    geo_point: "◎",
    geo_multi_point: "◎",
    geo_line: "◎",
    geo_multi_line: "◎",
    geo_polygon: "◎",
    geo_multi_polygon: "◎",
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

/**
 * The margin dot of the change kinds ``kinds`` (``change_kinds`` of a
 * block): {dot, label}, « ring » when one of them hides the node, else
 * « filled »; the label joins the kinds (``changeKindLabel``). Null for no
 * kind.
 */
export function marginDot(kinds) {
    if (!kinds || !kinds.length) {
        return null;
    }
    return {
        dot: kinds.includes("hidden") ? "ring" : "filled",
        label: kinds.map(changeKindLabel).join(", "),
    };
}

/**
 * The dot of ``change``, a change of the payload: « ring » for a change
 * that hides or removes its node, else « filled ».
 */
export function changeDot(change) {
    return change.kind === "hidden" || change.type === "remove" ? "ring" : "filled";
}

/**
 * The plain sentence of an element ``label`` hidden in a view of
 * ``viewType``: « Website hidden in this form ». A hidden element stays in
 * the arch; only a « remove » change takes it out (``changeSentence``).
 */
export function hiddenSentence(label, viewType) {
    if (viewType === "form") {
        return _t("%(label)s hidden in this form", {label});
    }
    if (viewType === "list") {
        return _t("%(label)s hidden in this list", {label});
    }
    return _t("%(label)s hidden in this view", {label});
}

// The sentence of a new element of « add_node », by its kind: with its
// label, and without one.
function newNodeSentence(kind, label) {
    const named = {
        page: () => _t("New tab %(label)s", {label}),
        notebook: () => _t("New tab %(label)s", {label}),
        group: () => _t("New group %(label)s", {label}),
        separator: () => _t("New separator %(label)s", {label}),
        widget: () => _t("New ribbon %(label)s", {label}),
        filter: () => _t("New filter %(label)s", {label}),
        group_by: () => _t("New grouping %(label)s", {label}),
    };
    const bare = {
        page: () => _t("New tab"),
        notebook: () => _t("New tab"),
        group: () => _t("New group"),
        separator: () => _t("New separator"),
        widget: () => _t("New ribbon"),
        filter: () => _t("New filter"),
        group_by: () => _t("New grouping"),
    };
    if (label) {
        return (named[kind] || (() => _t("New element %(label)s", {label})))();
    }
    return (bare[kind] || (() => _t("New element")))();
}

/**
 * The plain sentence of a change of kind ``kind`` (``change_kinds``) on
 * the element ``label``, when nothing more is known of it.
 */
export function kindSentence(kind, label, viewType) {
    const name = label || _t("An element");
    switch (kind) {
        case "new":
            return label ? _t("New element %(label)s", {label}) : _t("New element");
        case "hidden":
            return hiddenSentence(name, viewType);
        case "moved":
            return _t("%(label)s moved", {label: name});
        case "renamed":
            return _t("%(label)s renamed", {label: name});
    }
    return label ? _t("%(label)s changed", {label}) : _t("A change of this view");
}

/**
 * The plain sentence of ``change``, a change of the payload, as the Simple
 * level shows it: built from the label of its element, never from its
 * XPath or a technical name (« Phone becomes required », « Email renamed
 * Work email »). ``subject`` of the change (``change_subject`` of the
 * server) gives the label, the place and the value; ``label``, the label
 * of its block on the canvas, stands in when the subject has none.
 * ``settable``: the ``settable`` of the payload, which names the kind of
 * an attribute (attributeLabel). A change without a subject (one the
 * server could not read) gets the sentence of its kind
 * (``kindSentence``); a type of change it does not know, a sentence that
 * names the element only.
 */
export function changeSentence(change, {viewType = null, label = "", settable = {}} = {}) {
    if (!change.subject) {
        return kindSentence(change.kind, label, viewType);
    }
    const subject = change.subject;
    const name = subject.label || label || _t("An element");
    const value = subject.value;
    const kind = (subject.tag && (settable[subject.tag] || {})[change.attribute]) || null;
    switch (change.type) {
        case "add_field":
            return subject.label || label ? _t("New field %(label)s", {label: name}) : _t("New field");
        case "add_existing_field":
            return _t("Field %(label)s added", {label: name});
        case "add_node":
            return newNodeSentence(subject.kind || subject.tag, subject.label || label);
        case "move": {
            const anchor = subject.anchor;
            if (anchor && subject.position === "before") {
                return _t("%(label)s moved before %(anchor)s", {label: name, anchor});
            }
            if (anchor && subject.position === "inside") {
                return _t("%(label)s moved into %(anchor)s", {label: name, anchor});
            }
            if (anchor) {
                return _t("%(label)s moved after %(anchor)s", {label: name, anchor});
            }
            return _t("%(label)s moved", {label: name});
        }
        case "hide":
            return value ? hiddenSentence(name, viewType) : _t("%(label)s shown again", {label: name});
        case "remove":
            return _t("%(label)s removed from this view", {label: name});
        case "relabel":
            return value
                ? _t("%(label)s renamed %(value)s", {label: name, value})
                : _t("%(label)s takes back its original label", {label: name});
        case "required":
            return value
                ? _t("%(label)s becomes required", {label: name})
                : _t("%(label)s is no longer required", {label: name});
        case "readonly":
            return value
                ? _t("%(label)s becomes read-only", {label: name})
                : _t("%(label)s is no longer read-only", {label: name});
        case "help":
            return value
                ? _t("New tooltip on %(label)s", {label: name})
                : _t("Tooltip of %(label)s cleared", {label: name});
        case "optional":
            if (value === "show") {
                return _t("%(label)s optional, shown by default", {label: name});
            }
            if (value === "hide") {
                return _t("%(label)s optional, hidden by default", {label: name});
            }
            return _t("%(label)s is no longer optional", {label: name});
        case "set_attribute": {
            if (change.attribute === "string") {
                return value
                    ? _t("%(label)s renamed %(value)s", {label: name, value})
                    : _t("%(label)s takes back its original label", {label: name});
            }
            const attribute = attributeLabel(change.attribute, kind);
            if (!change.attribute || attribute === change.attribute) {
                return _t("%(label)s: a setting changed", {label: name});
            }
            if (!subject.label && !label) {
                return _t("View setting « %(attribute)s » changed", {attribute});
            }
            return _t("%(label)s: setting « %(attribute)s » changed", {label: name, attribute});
        }
    }
    return subject.label || label ? _t("%(label)s changed", {label: name}) : _t("A change of this view");
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

// The view types whose blocks the draft hides show as a hidden line
// (``isGhost``).
export const GHOST_VIEW_TYPES = ["form", "list"];

/**
 * Whether ``block`` is an element the draft hides in a view of
 * ``viewType`` (GHOST_VIEW_TYPES): « Remove from the view » keeps the node
 * in the arch of a form or a list, hidden by a change of kind « hidden »,
 * so that the other views that locate it keep finding it. The canvas
 * draws it as one hidden line that Restore brings back; it neither moves
 * nor leaves again, and the drops around it target the real node.
 */
export function isGhost(block, viewType) {
    return Boolean(block) && GHOST_VIEW_TYPES.includes(viewType) && (block.change_kinds || []).includes("hidden");
}

/**
 * Whether ``block`` can be dragged in a view of ``viewType``: what the
 * server lets move, and in a form or a list only the fields and the other
 * leaves, an element the draft hides left out (``isGhost``).
 */
export function canDragBlock(block, viewType) {
    if (block.movable === false || isGhost(block, viewType)) {
        return false;
    }
    if (["field", "widget", "filter", "group_by", "separator"].includes(block.kind)) {
        return true;
    }
    return TEMPLATED_TYPES.includes(viewType);
}

/**
 * Whether ``block`` can leave a view of ``viewType`` whose root block is
 * ``root``: not the view itself, nor a QWeb template, and in a kanban or a
 * timeline only a node of its templates (a native node is hidden instead).
 * An element the draft already removes (``isGhost``) comes back with
 * Restore instead.
 */
export function canRemoveBlock(block, root, viewType) {
    if (!block || (root && block.path === root.path) || block.kind === "template" || isGhost(block, viewType)) {
        return false;
    }
    return !TEMPLATED_TYPES.includes(viewType) || block.in_template !== false;
}

/** Whether ``block`` can be selected: any block but a QWeb template. */
export function canSelectBlock(block) {
    return block.kind !== "template";
}

/**
 * The label of a settable view attribute (``settable`` of the payload).
 * ``kind``, the kind of its value, names the attributes whose name means
 * another thing elsewhere: the « type » of a graph is its chart type.
 */
export function attributeLabel(attribute, kind) {
    const ofKind = {graph_type: _t("Chart type"), x2many_mode: _t("Display")}[kind];
    if (ofKind) {
        return ofKind;
    }
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
            stacked: _t("Stacked"),
            order: _t("Sort"),
            cumulated: _t("Cumulative"),
            color: _t("Color"),
            all_day: _t("All day"),
            create: _t("Create records"),
            edit: _t("Move and resize events"),
            delete: _t("Delete records"),
            filters: _t("Filter in the side panel"),
            // « editable » of a GeoEngine view: the geo fields are drawn on
            // its map.
            editable: _t("Draw on the map"),
            field_latitude: _t("Latitude"),
            field_longitude: _t("Longitude"),
            field_title: _t("Popup title"),
            field_address: _t("Popup address"),
            field_marker_icon_image: _t("Marker image"),
            marker_icon_size_x: _t("Marker width"),
            marker_icon_size_y: _t("Marker height"),
            marker_popup_anchor_x: _t("Popup anchor, horizontal"),
            marker_popup_anchor_y: _t("Popup anchor, vertical"),
            parent_field: _t("Parent field"),
            child_field: _t("Children field"),
            draggable: _t("Drag the cards to change the parent"),
            display: _t("Width"),
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
        graph_axis: {row: _t("Group by"), measure: _t("Measure")},
        graph_type: {bar: _t("Bar"), line: _t("Line"), pie: _t("Pie")},
        graph_order: {asc: _t("Ascending"), desc: _t("Descending")},
        calendar_mode: {day: _t("Day"), week: _t("Week"), month: _t("Month"), year: _t("Year")},
        calendar_filter: {True: _t("Yes")},
        activity_display: {full: _t("Whole line"), right: _t("Right-aligned")},
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

/**
 * The keys of the draft changes that touch a block under ``block``, its
 * own left out: the union of the ``changes`` of its descendants, each key
 * once, in the order of the tree.
 */
export function changeKeysInside(block) {
    const keys = [];
    for (const child of (block && block.children) || []) {
        for (const descendant of allBlocks(child)) {
            for (const key of descendant.changes || []) {
                if (!keys.includes(key)) {
                    keys.push(key);
                }
            }
        }
    }
    return keys;
}

/**
 * Whether the arch the draft starts from always hides ``block``: a
 * constant true « invisible » that no change of the draft wrote (a node the
 * draft hides carries the change kind « hidden »). A condition is no
 * constant: the node shows for some records.
 */
export function isBaseInvisible(block) {
    const attrs = (block && block.attrs) || {};
    return isTrue(attrs.invisible) && !(block.change_kinds || []).includes("hidden");
}

// The widgets of an x2many that draw its records as tags, not a sub-list.
export const TAG_WIDGETS = [
    "many2many_tags",
    "many2many_tags_avatar",
    "many2many_avatar_user",
    "many2many_avatar_employee",
];

/**
 * Whether the real form hides ``block`` on the record whose expression
 * context is ``context`` (``sampleContext``): its « invisible » is a
 * condition that ``evaluateBooleanExpr`` of the web client finds true. A
 * constant gives false (``isBaseInvisible`` covers it), as do no context,
 * an element the draft hides, and an expression that reads a name the
 * context lacks or that does not parse: the canvas draws such a node.
 */
export function isHiddenOnRecord(block, context) {
    const expression = ((block && block.attrs && block.attrs.invisible) || "").trim();
    if (!context || !expression || isTrue(expression) || (block.change_kinds || []).includes("hidden")) {
        return false;
    }
    try {
        return evaluateBooleanExpr(expression, context);
    } catch {
        return false;
    }
}

/**
 * The context the « invisible » expressions of a form read on its sample
 * record, as the web client builds it for a record: the values of the
 * payload (``sample_record``), its ``id``, then ``context``, ``uid``,
 * ``allowed_company_ids`` and ``current_company_id`` of ``user``. Null
 * without sample record: nothing is evaluated.
 */
export function sampleContext(data, user) {
    if (!data || !data.sample_res_id || !data.sample_record) {
        return null;
    }
    const userContext = (user && user.context) || {};
    const companies = userContext.allowed_company_ids || [];
    return {
        ...data.sample_record,
        id: data.sample_res_id,
        context: userContext,
        uid: user && user.userId,
        allowed_company_ids: companies,
        current_company_id: companies[0] || false,
    };
}

/**
 * The condition under which a node whose « invisible » is ``expression``
 * shows: its negation, written as a reader writes it (« not a » gives
 * « a », a name « not a », anything else « not (…) »).
 */
export function shownWhen(expression) {
    const text = (expression || "").trim();
    const negated = /^not\s+([\w.]+|\([^()]*\))$/.exec(text);
    if (negated) {
        const inner = negated[1];
        return inner.startsWith("(") ? inner.slice(1, -1).trim() : inner;
    }
    return /^[\w.]+$/.test(text) ? `not ${text}` : `not (${text})`;
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

/**
 * The title of the column ``key`` of a search view (the keys of
 * ``searchColumns``) or of the axis ``key`` of a pivot view (row, col,
 * measure); ``key`` itself for another one.
 */
export function columnLabel(key) {
    return (
        {
            fields: _t("Search fields"),
            filters: _t("Filters"),
            group_bys: _t("Group by"),
            row: _t("Rows"),
            col: _t("Columns"),
            measure: _t("Measures"),
        }[key] || key
    );
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

// The axes of a graph: its group-bys, the first one the X axis and the
// next ones its series, and its measures, of which it draws the last one.
// The layout of the server files the fields as the graph reads them: any
// visible field of a groupable type not of type « measure » is a group-by,
// under « row ».
export const GRAPH_AXES = ["row", "measure"];

/** The field blocks of a graph view by axis: {row, measure, others}. */
export function graphLanes(data) {
    const lanes = pivotLanes(data);
    return {row: lanes.row, measure: lanes.measure, others: lanes.others};
}

/** The title of the axis ``key`` of a graph view (GRAPH_AXES). */
export function graphLaneLabel(key) {
    return {row: _t("Group by"), measure: _t("Measures")}[key] || key;
}

/** The axes of a graph a field described by ``info`` can go on. */
export function graphAxes(info) {
    return pivotAxes(info).filter((axis) => GRAPH_AXES.includes(axis));
}

/** The axes a field described by ``info`` can go on in a ``viewType`` view. */
export function axesOf(viewType, info) {
    return viewType === "graph" ? graphAxes(info) : pivotAxes(info);
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

// ── focus on a block of a form ──────────────────────────────────────────

/** Whether ``block`` is a group of a form. */
function isGroup(block) {
    return block.tag === "group";
}

/**
 * Whether the page ``page`` of a notebook is the context of the groups it
 * holds rather than a focus block itself: it holds groups only, at least
 * one.
 */
export function isFocusContext(page) {
    const children = page.children || [];
    return page.tag === "page" && children.length > 0 && children.every(isGroup);
}

// ── readable names, for the Simple level ───────────────────────────────

/**
 * Whether ``block`` is the box of the smart buttons of a form: the element
 * named « button_box », with its buttons or empty.
 */
export function isButtonBox(block) {
    return Boolean(block) && ((block.attrs || {}).name === "button_box" || block.label === "button_box");
}

/**
 * Whether ``block`` is a group of a form that holds groups only, at least
 * one: the web client lays its groups out side by side, as columns.
 */
export function isGroupRow(block) {
    const children = (block && block.children) || [];
    return block.tag === "group" && children.length > 0 && children.every(isGroup);
}

/** The classes of the node of ``block``, as a list. */
function classesOf(block) {
    return (((block && block.attrs) || {}).class || "").split(/\s+/).filter(Boolean);
}

/**
 * Whether ``block`` takes the label cell of a group of a form, as the
 * form compiler of the web client lays it out: a <label>, or an element
 * of class « o_td_label » or « o_wrap_label »; never a field.
 */
export function isLabelCell(block) {
    if (!block || block.kind === "field") {
        return false;
    }
    const classes = classesOf(block);
    return block.tag === "label" || classes.includes("o_td_label") || classes.includes("o_wrap_label");
}

/**
 * The part ``child``, a block of the group ``parent`` of a form, takes in
 * a line « label | value » of the web client: « label » for a label cell
 * (``isLabelCell``); « value » for the block right after one, unless it is
 * a label cell itself, a separator or a field that shows its own label
 * (no « nolabel »), which start a line of their own; "" otherwise, and in
 * a group of groups.
 */
export function pairRole(parent, child) {
    if (!parent || !child || parent.tag !== "group" || isGroupRow(parent)) {
        return "";
    }
    if (isLabelCell(child)) {
        return "label";
    }
    const siblings = parent.children || [];
    const index = siblings.findIndex((block) => block.path === child.path);
    if (index < 1 || !isLabelCell(siblings[index - 1]) || child.kind === "separator") {
        return "";
    }
    if (child.kind === "field" && !isTrue((child.attrs || {}).nolabel)) {
        return "";
    }
    return "value";
}

/**
 * The part of an address ``block`` is in a form, from the class the
 * address format of the web client gives it (« o_address_city »): one of
 * « street », « city », « state », « zip », « country », or "".
 */
export function addressPart(block) {
    for (const name of classesOf(block)) {
        const part = name.startsWith("o_address_") ? name.slice("o_address_".length) : "";
        if (["street", "city", "state", "zip", "country"].includes(part)) {
            return part;
        }
    }
    return "";
}

/** Whether ``block`` is the address of a form, laid out by its parts (« o_address_format »). */
export function isAddressFormat(block) {
    return classesOf(block).includes("o_address_format");
}

/** Whether ``block`` is the picture of the record a form floats at the right of its title (« oe_avatar »). */
export function isAvatar(block) {
    return Boolean(block) && block.kind === "field" && classesOf(block).includes("oe_avatar");
}

/**
 * The name of a group by its place among the groups of a group of groups
 * (``column`` and ``columns`` of the payload): « Left column » and « Right
 * column » for two, « Column 2 » for more; "" for another block.
 */
export function columnName(block) {
    const {column, columns} = block || {};
    if (!block || block.tag !== "group" || !column || !columns || columns < 2) {
        return "";
    }
    if (columns === 2) {
        return column === 1 ? _t("Left column") : _t("Right column");
    }
    return _t("Column %(number)s", {number: column});
}

/**
 * The name of a group without « string » that its place gives: its column
 * (``columnName``), « Columns » for a group of groups (``isGroupRow``);
 * "" otherwise.
 */
export function placeName(block) {
    return columnName(block) || (isGroupRow(block) ? _t("Columns") : "");
}

/**
 * The text of its own that names ``block`` for a reader: its « string »,
 * else its label unless that label is only its tag or its technical name
 * (« name »); "" for none.
 */
export function ownLabel(block) {
    const attrs = block.attrs || {};
    if (attrs.string) {
        return attrs.string;
    }
    return block.label && ![block.tag, attrs.name].includes(block.label) ? block.label : "";
}

/**
 * The labels of the fields ``block`` holds, at any depth in the order of
 * the arch, ``limit`` at most. With ``drawn``, a function of a block, a
 * block it answers false for is left out with what it holds; a node the
 * arch always hides (``isBaseInvisible``) always is.
 */
export function fieldLabelsIn(block, limit, drawn = null) {
    const labels = [];
    const walk = (parent) => {
        for (const child of parent.children || []) {
            if (labels.length >= limit) {
                return;
            }
            if (isBaseInvisible(child) || (drawn && !drawn(child))) {
                continue;
            }
            if (child.kind === "field") {
                labels.push(child.label || child.name);
            } else {
                walk(child);
            }
        }
    };
    walk(block);
    return labels;
}

/**
 * The fields ``block`` holds, as a reader sees them: the labels of the
 * first two, then « … » when it holds more; "" when it holds none.
 * ``drawn``: the fields to count (``fieldLabelsIn``).
 */
export function fieldsSummary(block, drawn = null) {
    const labels = fieldLabelsIn(block, 3, drawn);
    const shown = labels.slice(0, 2).join(", ");
    return labels.length > 2 ? `${shown}…` : shown;
}

/**
 * The readable name of the container ``block`` that has no « string »:
 * « Group: A, B… » for a group, « Tab: A, B… » for a page, « Block: A,
 * B… » for another element, from the first fields it holds
 * (``fieldsSummary``, of the fields ``drawn`` keeps); the bare word when
 * it holds no field. Its technical name (« name ») never shows.
 */
export function contentName(block, drawn = null) {
    const fields = fieldsSummary(block, drawn);
    if (block.tag === "group") {
        return fields ? _t("Group: %(fields)s", {fields}) : _t("Group");
    }
    if (block.tag === "page") {
        return fields ? _t("Tab: %(fields)s", {fields}) : _t("Tab");
    }
    return fields ? _t("Block: %(fields)s", {fields}) : _t("Block");
}

/**
 * The label of the page ``page``: its « string », else its label, else
 * « Tab ». With ``simple``, a page without a label of its own
 * (``ownLabel``) shows the first fields it holds (``fieldsSummary``)
 * rather than its technical name.
 */
export function pageLabel(page, {simple = false} = {}) {
    const attrs = page.attrs || {};
    if (attrs.string) {
        return attrs.string;
    }
    if (simple) {
        return ownLabel(page) || fieldsSummary(page) || _t("Tab");
    }
    return page.label && page.label !== page.tag ? page.label : _t("Tab");
}

/**
 * The focus blocks of the form whose root block is ``root``, in the order
 * of the arch: [{path, block, kind, label, parent, page, pageLabel}]. The
 * walk runs over the sheet, or the form itself when it has none: a group
 * that is a child of the sheet or of a page is a block, a row of groups
 * included as one block; a page of a notebook of the sheet is a block
 * unless it holds groups only (``isFocusContext``), which then are the
 * blocks and the page their context (``page``). ``kind`` is « group » or
 * « page », ``parent`` the block that holds the focus block. The label of
 * a group is its « string »; the first group of the sheet without one is
 * « General information », another one « Group » or « Group « name » »,
 * or with ``simple`` « Group « label » » for a label of its own
 * (``ownLabel``), else its readable name (``contentName``): the technical
 * name never shows. A group nested in a group is no focus block.
 */
export function focusBlocks(root, {simple = false} = {}) {
    const entries = [];
    if (!root) {
        return entries;
    }
    const sheet = (root.children || []).find((child) => child.tag === "sheet") || root;
    let general = true;
    const groupLabel = (group, inSheet) => {
        const attrs = group.attrs || {};
        if (attrs.string) {
            return attrs.string;
        }
        if (inSheet && general) {
            general = false;
            return _t("General information");
        }
        if (simple) {
            const own = ownLabel(group);
            return own ? _t("Group « %(label)s »", {label: own}) : contentName(group);
        }
        const own = group.label && group.label !== group.tag;
        return own ? _t("Group « %(label)s »", {label: group.label}) : _t("Group");
    };
    const groups = (container, page) => {
        for (const child of container.children || []) {
            if (isGroup(child)) {
                entries.push({
                    path: child.path,
                    block: child,
                    kind: "group",
                    label: groupLabel(child, !page),
                    parent: container,
                    page,
                    pageLabel: page ? pageLabel(page, {simple}) : "",
                });
            } else if (!page && child.tag === "notebook") {
                for (const tab of (child.children || []).filter((b) => b.tag === "page")) {
                    if (isFocusContext(tab)) {
                        groups(tab, tab);
                    } else {
                        const label = pageLabel(tab, {simple});
                        entries.push({
                            path: tab.path,
                            block: tab,
                            kind: "page",
                            label,
                            parent: child,
                            page: null,
                            pageLabel: "",
                        });
                    }
                }
            }
        }
    };
    groups(sheet, null);
    return entries;
}

/**
 * The focus block (``focusBlocks``) that holds the block at ``path``, the
 * block itself included; null when no focus block holds it: the header,
 * the chatter, a page that holds groups only, the sheet. ``entries``, the
 * focus blocks of ``root`` when the caller has them, saves the walk.
 */
export function focusBlockOf(root, path, entries = null) {
    const trail = blockTrail(root, path);
    if (!trail.length) {
        return null;
    }
    const paths = new Set(trail.map((block) => block.path));
    return (entries || focusBlocks(root)).find((entry) => paths.has(entry.path)) || null;
}

/** The technical names of the fields ``block`` holds, at any depth in the order of the arch. */
export function fieldNamesIn(block) {
    const names = [];
    const walk = (parent) => {
        for (const child of parent.children || []) {
            if (child.kind === "field") {
                names.push(child.name);
            } else {
                walk(child);
            }
        }
    };
    walk(block);
    return names;
}

/**
 * What names the focus block ``entry`` across a change of the arch, whose
 * positional paths (« /form/sheet/group[2] ») shift when a block before it
 * comes or goes: {path, tag, name, string, fields, label}. ``name`` is
 * its « name »: the one of its path when the path names it, else the
 * label the server gives it when that label is neither its « string »
 * nor its tag (the server labels a block by its « string », else its
 * « name »); "" when unknown. ``string`` is its « string » or "";
 * ``fields`` the names of the fields it holds; ``label`` what the editor
 * shows of it, for a message once it is gone.
 *
 * Two more parts name a block that has neither a name, a « string » nor
 * a field, which the parts above leave anonymous: ``added``, the keys of
 * the draft changes that touch a block a change added (``change_kinds``
 * holds « new »), which stay its own until that change goes; and
 * ``place``: {context, before, after, rank}, where it sits — ``context``
 * the « string » or « name » of its page, else the tag of its parent;
 * ``before`` and ``after`` the fields of the nearest sibling that holds
 * some, on each side; ``rank`` its order among the anonymous empty
 * siblings of its tag.
 */
export function focusIdentity(entry) {
    const block = entry.block;
    const string = (block.attrs || {}).string || "";
    const named = /^\/\/[\w.-]+\[@name='([^']+)'\]$/.exec(entry.path || "");
    let name = named ? named[1] : "";
    if (!name && !string && block.label && block.label !== block.tag) {
        name = block.label;
    }
    const added = (block.change_kinds || []).includes("new") ? [...(block.changes || [])] : [];
    return {
        path: entry.path,
        tag: block.tag,
        name,
        string,
        fields: fieldNamesIn(block),
        label: String(entry.label),
        added,
        place: focusPlace(entry),
    };
}

/** Whether ``block`` has no « string », no own label and no field: nothing but its place names it. */
function isAnonymousEmpty(block) {
    const own = block.label && block.label !== block.tag;
    return !(block.attrs || {}).string && !own && !fieldNamesIn(block).length;
}

/** The ``place`` part of ``focusIdentity``: where the block of ``entry`` sits in its parent. */
function focusPlace(entry) {
    const parent = entry.parent;
    const siblings = (parent && parent.children) || [];
    const index = siblings.indexOf(entry.block);
    const page = entry.page;
    const pageAttrs = (page && page.attrs) || {};
    const context = page
        ? pageAttrs.string || pageAttrs.name || page.label || page.tag
        : parent
        ? parent.tag
        : "";
    const nearest = (step) => {
        for (let i = index + step; i >= 0 && i < siblings.length; i += step) {
            const names = fieldNamesIn(siblings[i]);
            if (siblings[i].kind === "field" && siblings[i].name) {
                return [siblings[i].name];
            }
            if (names.length) {
                return names;
            }
        }
        return [];
    };
    const rank = siblings
        .slice(0, Math.max(index, 0))
        .filter((sibling) => sibling.tag === entry.block.tag && isAnonymousEmpty(sibling)).length;
    return {context, before: index < 0 ? [] : nearest(-1), after: index < 0 ? [] : nearest(1), rank};
}

/**
 * The focus block of ``entries`` (``focusBlocks`` of a new payload) that
 * ``identity`` (``focusIdentity``, taken from an older payload) names, or
 * null when it left. A block of another tag, or of another « name » when
 * both have one, is another block. Two « string » that differ make
 * another block too, unless the two share a field and neither has a
 * « name »: the block in focus relabelled. A candidate scores 8 for the
 * same « name », 4 for the same « string », 2 per field the two share, 1
 * for the same path; one that shares none of these but its path matches
 * only when one of the two holds no field: a change inside the block in
 * focus keeps most of its fields, a block that only took its path shares
 * none. The best score wins; a tie keeps the order of the arch.
 *
 * A block a draft change added is the block that still carries one of
 * the keys of ``added``, whatever its path; an empty one that no block
 * carries is gone (null). A block with no name, no
 * « string » and no field matches only a block alike in the same
 * ``place.context``: by the fields of its neighbours (2 per field shared
 * on each side) and its ``rank`` (1), never by its path alone, so an
 * empty group that took the path of another is not taken for it.
 */
export function resolveFocusBlock(entries, identity) {
    if (!identity) {
        return null;
    }
    if (!identity.tag) {
        return entries.find((entry) => entry.path === identity.path) || null;
    }
    if ((identity.added || []).length) {
        const keys = new Set(identity.added);
        const carrier = entries.find(
            (entry) => entry.block.tag === identity.tag && (entry.block.changes || []).some((key) => keys.has(key))
        );
        if (carrier) {
            return carrier;
        }
    }
    if (identity.place && !identity.name && !identity.string && !identity.fields.length) {
        // An empty block a change added, which no block carries any more,
        // left with that change: its place would only find a look-alike.
        return (identity.added || []).length ? null : resolveAnonymousBlock(entries, identity);
    }
    const fields = new Set(identity.fields);
    let best = null;
    let bestScore = 0;
    for (const entry of entries) {
        if (entry.block.tag !== identity.tag) {
            continue;
        }
        const other = focusIdentity(entry);
        const bothNamed = Boolean(identity.name && other.name);
        if (bothNamed && identity.name !== other.name) {
            continue;
        }
        const sameName = bothNamed;
        const shared = other.fields.filter((name) => fields.has(name)).length;
        const bothStrings = Boolean(identity.string && other.string);
        const sameString = bothStrings && identity.string === other.string;
        const relabelled = bothStrings && !sameString && shared > 0 && !identity.name && !other.name;
        if (bothStrings && !sameString && !sameName && !relabelled) {
            continue;
        }
        const samePath = entry.path === identity.path;
        const empty = !fields.size || !other.fields.length;
        if (!sameName && !sameString && !shared && !(samePath && empty)) {
            continue;
        }
        const score = (sameName ? 8 : 0) + (sameString ? 4 : 0) + 2 * shared + (samePath ? 1 : 0);
        if (score > bestScore) {
            best = entry;
            bestScore = score;
        }
    }
    return best;
}

/**
 * The focus block of ``entries`` that the anonymous empty block of
 * ``identity`` became (``resolveFocusBlock``), or null.
 */
function resolveAnonymousBlock(entries, identity) {
    const place = identity.place;
    const shared = (a, b) => {
        const set = new Set(a);
        return b.filter((name) => set.has(name)).length;
    };
    let best = null;
    let bestScore = 0;
    for (const entry of entries) {
        // A block a draft change added is that change's block, never this one.
        const added = (entry.block.change_kinds || []).includes("new");
        if (entry.block.tag !== identity.tag || added || !isAnonymousEmpty(entry.block)) {
            continue;
        }
        const other = focusPlace(entry);
        if (other.context !== place.context) {
            continue;
        }
        const neighbours = shared(place.before, other.before) + shared(place.after, other.after);
        const sameRank = other.rank === place.rank;
        const bare = !place.before.length && !place.after.length;
        if (!neighbours && !(sameRank && bare)) {
            continue;
        }
        const score = 2 * neighbours + (sameRank ? 1 : 0);
        if (score > bestScore) {
            best = entry;
            bestScore = score;
        }
    }
    return best;
}

/**
 * The hook at the end of the focus block ``entry``: inside the block,
 * inside its last group for a row of groups, which shows no hook of its
 * own.
 */
export function focusEndHook(entry) {
    const children = entry.block.children || [];
    const row = isGroup(entry.block) && children.length > 0 && children.every(isGroup);
    return {target: row ? children[children.length - 1].path : entry.path, position: "inside"};
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
