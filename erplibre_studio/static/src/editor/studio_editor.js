/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillStart, useState} from "@odoo/owl";
import {serializeDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {View} from "@web/views/view";

const {DateTime} = luxon;

const MODEL = "erplibre.studio.editor";
export const DRAGGING_CLASS = "o_erplibre_studio_dragging";

const TRUE_VALUES = ["1", "True", "true"];
// The view types whose fields show from a QWeb template.
const TEMPLATED_TYPES = ["kanban", "timeline"];
const DATE_TYPES = ["date", "datetime"];
const NUMBER_TYPES = ["integer", "float", "monetary"];
// The ribbon colors offered for a new ribbon: bootstrap classes.
const RIBBON_COLORS = [
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
        }[ttype] || ttype
    );
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

/**
 * One node of the edited arch: a container with its children and the drop
 * hooks between them, a field, or another element.
 */
export class StudioBlock extends Component {
    static template = "erplibre_studio.Block";
    static props = {block: Object, editor: Object, viewType: String};

    get block() {
        return this.props.block;
    }

    get editor() {
        return this.props.editor;
    }

    get field() {
        return (this.editor.data.fields || {})[this.block.name] || {};
    }

    get isSelected() {
        return this.editor.state.selected === this.block.path;
    }

    get templated() {
        return TEMPLATED_TYPES.includes(this.props.viewType);
    }

    /**
     * Whether the block can be dragged: what the server lets move, and in
     * a form or a list only the fields.
     */
    get canDrag() {
        if (this.block.movable === false) {
            return false;
        }
        if (["field", "widget", "filter", "group_by", "separator"].includes(this.block.kind)) {
            return true;
        }
        return this.templated;
    }

    /** A block the properties describe: a field, or any node of a view other than a form or a list. */
    get canSelect() {
        if (this.block.kind === "field") {
            return true;
        }
        return !["form", "list"].includes(this.props.viewType) && this.block.kind !== "template";
    }

    /** A group of groups lays its groups out side by side, as Odoo does. */
    get isRow() {
        const children = this.block.children || [];
        return this.block.tag === "group" && children.length > 0 && children.every((child) => child.tag === "group");
    }

    get showHooks() {
        return Boolean(this.block.drop) && !this.isRow;
    }

    /**
     * Whether a hook goes before ``child``: never inside a t-if chain,
     * whose nodes must stay next to each other.
     */
    hookBefore(child) {
        return this.showHooks && !["elif", "else"].includes(child.chain);
    }

    get pages() {
        return (this.block.children || []).filter((child) => child.tag === "page");
    }

    get activePage() {
        const index = this.editor.state.pages[this.block.path] || 0;
        return this.pages[index] || this.pages[0];
    }

    get flags() {
        const attrs = this.block.attrs || {};
        const flags = [];
        if (isTrue(attrs.invisible) || isTrue(attrs.column_invisible)) {
            flags.push({key: "hidden", label: _t("hidden")});
        } else if (attrs.invisible && this.templated) {
            flags.push({key: "condition", label: _t("hidden when %(condition)s", {condition: attrs.invisible})});
        }
        if (isTrue(attrs.required) || this.field.required) {
            flags.push({key: "required", label: _t("required")});
        }
        if (isTrue(attrs.readonly) || this.field.readonly) {
            flags.push({key: "readonly", label: _t("read-only")});
        }
        if (attrs.optional) {
            flags.push({key: "optional", label: attrs.optional === "hide" ? _t("optional, hidden") : _t("optional")});
        }
        if (attrs.widget && this.props.viewType !== "form") {
            flags.push({key: "widget", label: attrs.widget});
        }
        if (this.block.interval) {
            flags.push({key: "interval", label: valueLabel("interval", this.block.interval) || this.block.interval});
        }
        if (this.field.pending) {
            flags.push({key: "pending", label: _t("new")});
        }
        return flags;
    }

    startDrag(ev) {
        ev.stopPropagation();
        this.editor.startDrag(ev, {kind: "node", path: this.block.path, name: this.block.name});
    }

    select() {
        if (this.canSelect) {
            this.editor.select(this.block.path);
        }
    }

    selectPage(index) {
        this.editor.state.pages[this.block.path] = index;
    }
}
StudioBlock.components = {StudioBlock};

/**
 * The studio editor: a client action on one view of a model. The server
 * holds the draft; every drop or property change is one operation, and the
 * editor renders the payload it answers. The canvas depends on the view
 * type: the arch tree of a form, the columns of a list, the template of a
 * kanban card or a timeline item, the columns of a search view, the axes
 * of a pivot.
 */
export class StudioEditor extends Component {
    static template = "erplibre_studio.Editor";
    static components = {StudioBlock, View};
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const params = (this.props.action && this.props.action.params) || {};
        this.params = {
            resModel: params.res_model,
            viewId: params.view_id || false,
            viewType: params.view_type || "form",
            actionId: params.action_id || false,
        };
        this.state = useState({
            loading: true,
            busy: false,
            error: null,
            data: {},
            projectId: params.project_id || false,
            selected: null,
            dragging: null,
            hook: null,
            tab: "new",
            filter: "",
            preview: false,
            pages: {},
            newProject: {name: "", module_name: ""},
            comodels: null,
            // The interval of a date field dropped as a grouping.
            interval: "month",
            template: null,
            ribbon: {title: "", bg_color: RIBBON_COLORS[0]},
            filterForm: null,
            colors: null,
        });
        this.ribbonColors = RIBBON_COLORS;
        onWillStart(() => this.load());
    }

    get data() {
        return this.state.data;
    }

    /** The editor itself, for the blocks it renders. */
    get editor() {
        return this;
    }

    get viewType() {
        return this.data.view_type || this.params.viewType;
    }

    get layout() {
        return this.data.layout || {};
    }

    get root() {
        return this.data.blocks;
    }

    /**
     * The project the selector shows, or null: while « Choose a project… »
     * or « New project… » is selected, no edit reaches a project.
     */
    get project() {
        const project = this.data.project;
        return project && project.id === this.state.projectId ? project : null;
    }

    allows(operation) {
        return (this.data.operations || []).includes(operation);
    }

    fieldInfo(name) {
        return (this.data.fields || {})[name] || {};
    }

    // ── server ──────────────────────────────────────────────────────────

    errorMessage(error) {
        return (error.data && error.data.message) || error.message || String(error);
    }

    async call(method, args, kwargs = {}) {
        this.state.busy = true;
        try {
            const data = await this.orm.call(MODEL, method, args, kwargs);
            this.state.data = data;
            this.state.projectId = (data.project && data.project.id) || false;
            this.state.error = null;
            if (!this.formIsCurrent(this.state.filterForm, data.project)) {
                // Its target was located in a draft that is gone.
                this.state.filterForm = null;
            }
            return data;
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    async load() {
        if (!this.params.resModel) {
            this.state.loading = false;
            this.state.error = _t("Open the studio from the debug menu of a view.");
            return;
        }
        try {
            const data = await this.orm.call(MODEL, "get_editor_data", [
                this.params.resModel,
                this.params.viewId,
                this.params.viewType,
                this.state.projectId,
            ]);
            this.state.data = data;
            this.params.viewId = data.view.id;
            this.state.projectId = (data.project && data.project.id) || false;
        } catch (error) {
            this.state.error = this.errorMessage(error);
        } finally {
            this.state.loading = false;
        }
    }

    viewArgs() {
        return [this.params.resModel, this.params.viewId, this.params.viewType];
    }

    /** Back to a canvas without selection, form or preview. */
    resetCanvas() {
        Object.assign(this.state, {selected: null, filterForm: null, colors: null, template: null, preview: false});
    }

    /**
     * Edit the default view of another type of the same model, in the same
     * project.
     */
    async switchViewType(ev) {
        const viewType = ev.target.value;
        if (this.state.busy || viewType === this.params.viewType) {
            return;
        }
        const projectId = this.project ? this.project.id : false;
        this.state.busy = true;
        try {
            const data = await this.orm.call(
                MODEL,
                "get_editor_data",
                [this.params.resModel, false, viewType, projectId],
                {pick_project: Boolean(projectId)}
            );
            Object.assign(this.params, {viewType, viewId: data.view.id});
            this.resetCanvas();
            this.state.data = data;
            const keep = this.state.projectId === "new" ? "new" : false;
            this.state.projectId = (data.project && data.project.id) || keep;
        } catch (error) {
            ev.target.value = this.params.viewType;
            this.notification.add(this.errorMessage(error), {type: "danger"});
        } finally {
            this.state.busy = false;
        }
    }

    /**
     * One operation on the draft. Operations run one at a time: each one
     * locates its nodes in the payload on screen, and names its revision
     * so that the server refuses it on a draft that changed meanwhile.
     */
    async operate(operation) {
        if (this.state.busy) {
            return null;
        }
        if (!this.project) {
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return null;
        }
        return this.call("apply_operation", [this.project.id, ...this.viewArgs(), operation], {
            revision: this.project.revision,
        });
    }

    async projectAction(action) {
        if (this.state.busy || !this.project) {
            return null;
        }
        const data = await this.call("project_action", [this.project.id, action, ...this.viewArgs()], {
            revision: this.project.revision,
        });
        if (data && ["action_apply", "action_revert"].includes(action)) {
            // The applied views change what every view shows.
            this.env.bus.trigger("CLEAR-CACHES");
        }
        if (data && data.notice) {
            this.notification.add(data.notice, {type: "warning", sticky: true});
        }
        if (data && action !== "action_apply") {
            this.state.selected = null;
        }
        return data;
    }

    async selectProject(ev) {
        if (this.state.busy) {
            return;
        }
        const value = ev.target.value;
        this.state.selected = null;
        const projectId = parseInt(value) || false;
        if (projectId) {
            await this.call("get_editor_data", [...this.viewArgs(), projectId]);
            return;
        }
        // No project, or one to create: the view without any draft.
        await this.call("get_editor_data", [...this.viewArgs(), false], {pick_project: false});
        if (value === "new") {
            this.state.projectId = "new";
        }
    }

    async createProject() {
        const {name, module_name} = this.state.newProject;
        try {
            const projectId = await this.orm.call(MODEL, "create_project", [name, module_name]);
            this.state.newProject = {name: "", module_name: ""};
            await this.call("get_editor_data", [...this.viewArgs(), projectId]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
        }
    }

    // ── drag and drop ───────────────────────────────────────────────────

    startDrag(ev, item) {
        if (this.state.busy) {
            ev.preventDefault();
            return;
        }
        if (!this.project) {
            ev.preventDefault();
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return;
        }
        this.state.dragging = item;
        if (ev.dataTransfer) {
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", item.path || item.ttype || item.name || item.kind || "");
        }
        document.body.classList.add(DRAGGING_CLASS);
    }

    endDrag() {
        this.state.dragging = null;
        this.state.hook = null;
        document.body.classList.remove(DRAGGING_CLASS);
    }

    hookKey(target, position, zone) {
        return `${zone || ""}:${position}:${target}`;
    }

    /**
     * Whether the dragged ``item`` can land in ``zone``: a column of a
     * search view, an axis of a pivot, the loaded fields of a timeline, or
     * the arch tree (no zone). The server checks the rest.
     */
    accepts(item, zone) {
        if (!item) {
            return false;
        }
        const viewType = this.viewType;
        if (item.kind === "widget") {
            return viewType === "kanban" && !zone;
        }
        if (item.kind === "separator") {
            return viewType === "search" && zone !== "fields";
        }
        if (viewType === "search") {
            if (item.kind === "existing" && zone === "group_bys") {
                return Boolean(this.fieldInfo(item.name).groupable);
            }
            return true;
        }
        if (viewType === "pivot") {
            const axes = item.kind === "existing" ? item.axes || [] : pivotAxes(this.fieldInfo(item.name));
            return axes.includes(zone);
        }
        if (zone === "loaded") {
            return item.kind === "existing";
        }
        return true;
    }

    overHook(ev, target, position, zone) {
        if (!this.accepts(this.state.dragging, zone)) {
            return;
        }
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = "move";
        }
        this.state.hook = this.hookKey(target, position, zone);
    }

    leaveHook(target, position, zone) {
        if (this.state.hook === this.hookKey(target, position, zone)) {
            this.state.hook = null;
        }
    }

    /** The operation a drop of ``item`` on a hook makes, or null. */
    dropOperation(item, target, position, zone) {
        const viewType = this.viewType;
        if (item.kind === "node") {
            if (item.path === target) {
                return null;
            }
            const operation = {type: "move", source: item.path, target, position};
            if (viewType === "pivot" && zone) {
                operation.axis = zone;
            }
            return operation;
        }
        if (item.kind === "new") {
            return {
                type: "add_field",
                target,
                position,
                field: {ttype: item.ttype, field_description: fieldTypeLabel(item.ttype)},
            };
        }
        if (item.kind === "widget") {
            return {type: "add_widget", target, position, widget: item.widget, attrs: {...this.state.ribbon}};
        }
        if (item.kind === "separator") {
            return {type: "add_separator", target, position};
        }
        const isDate = DATE_TYPES.includes(this.fieldInfo(item.name).type);
        if (viewType === "search" && zone === "group_bys") {
            const operation = {type: "add_group_by", target, position, field_name: item.name};
            if (isDate) {
                operation.interval = this.state.interval;
            }
            return operation;
        }
        const operation = {type: "add_existing_field", target, position, field_name: item.name};
        if (viewType === "pivot") {
            operation.axis = zone;
            if (isDate && zone !== "measure") {
                operation.interval = this.state.interval;
            }
        }
        return operation;
    }

    async dropOnHook(ev, target, position, zone) {
        ev.preventDefault();
        const item = this.state.dragging;
        this.endDrag();
        if (!item || this.state.busy || !this.accepts(item, zone)) {
            return;
        }
        if (item.kind === "existing" && this.viewType === "search" && zone === "filters") {
            // A filter on a field needs its condition first.
            this.openFilterForm(target, position, item.name);
            return;
        }
        const operation = this.dropOperation(item, target, position, zone);
        if (operation) {
            await this.operateAndSelect(operation, item);
        }
    }

    /**
     * Run ``operation`` and select what it added or moved: a new field, a
     * new named node, or the dragged one.
     */
    async operateAndSelect(operation, item = {}) {
        const before = new Set(Object.keys(this.data.fields || {}));
        const keys = namedKeys(this.root);
        const data = await this.operate(operation);
        if (!data) {
            return null;
        }
        let block = null;
        if (item.kind === "new") {
            const name = Object.keys(data.fields).find((n) => !before.has(n));
            block = name && this.fieldBlock(data.blocks, name);
        } else if (item.name && ["add_existing_field", "move"].includes(operation.type)) {
            block = this.fieldBlock(data.blocks, item.name);
        }
        if (!block) {
            block = allBlocks(data.blocks).find((b) => b.name && !keys.has(`${b.kind}:${b.name}`));
        }
        this.state.selected = block ? block.path : null;
        return data;
    }

    /**
     * The block named ``name`` in ``root``: the one the user can move first,
     * since a QWeb view also lists the fields it only loads.
     */
    fieldBlock(root, name) {
        return (
            findBlock(root, (b) => b.name === name && b.kind !== "template" && b.movable !== false) ||
            findBlock(root, (b) => b.name === name && b.kind !== "template")
        );
    }

    // ── canvas of each view type ────────────────────────────────────────

    /** The templates of a kanban view, card first: [{name, block}]. */
    get templates() {
        const templates = this.layout.templates || {};
        const names = Object.keys(templates).sort((a, b) =>
            a === "card" ? -1 : b === "card" ? 1 : a.localeCompare(b)
        );
        return names
            .map((name) => ({name, block: findBlock(this.root, (b) => b.path === templates[name])}))
            .filter((item) => item.block);
    }

    get activeTemplate() {
        const templates = this.templates;
        return templates.find((t) => t.name === this.state.template) || templates[0] || null;
    }

    selectTemplate(name) {
        this.state.template = name;
    }

    /** The fields a QWeb view declares outside its templates. */
    get loadedBlocks() {
        return ((this.root && this.root.children) || []).filter((b) => b.kind === "field");
    }

    get timelineTemplate() {
        const path = this.layout.template;
        return path ? findBlock(this.root, (b) => b.path === path) : null;
    }

    get searchColumns() {
        return searchColumns(this.root);
    }

    /** The hook after the last block of ``blocks``, else inside ``fallback``. */
    endHook(blocks, fallback) {
        const last = blocks[blocks.length - 1];
        return last ? {target: last.path, position: "after"} : {target: fallback, position: "inside"};
    }

    searchEndHook(column) {
        let fallback = this.root.path;
        if (column === "group_bys") {
            const group = findBlock(this.root, (b) => b.kind === "container" && b.tag === "group");
            fallback = group ? group.path : fallback;
        }
        return this.endHook(this.searchColumns[column], fallback);
    }

    get pivotLanes() {
        return pivotLanes(this.data);
    }

    get searchColumnList() {
        return [
            {key: "fields", label: _t("Search fields")},
            {key: "filters", label: _t("Filters")},
            {key: "group_bys", label: _t("Group by")},
        ];
    }

    get pivotLaneList() {
        return [
            {key: "row", label: _t("Rows")},
            {key: "col", label: _t("Columns")},
            {key: "measure", label: _t("Measures")},
        ];
    }

    // ── the filter form of a search view ────────────────────────────────

    operatorsOf(name) {
        const type = this.fieldInfo(name).type;
        return (this.layout.operators || {})[type] || [];
    }

    newCondition(name = "") {
        const operators = this.operatorsOf(name);
        const type = this.fieldInfo(name).type;
        return {field: name, operator: operators[0] || "=", value: type === "boolean" ? "True" : ""};
    }

    openFilterForm(target, position, name = "") {
        if (!this.project) {
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return;
        }
        if (!target) {
            ({target, position} = this.searchEndHook("filters"));
        }
        const label = name ? this.fieldInfo(name).string || name : "";
        this.state.selected = null;
        this.state.filterForm = {
            target,
            position,
            label,
            conditions: [this.newCondition(name)],
            projectId: this.project.id,
            revision: this.project.revision,
        };
    }

    /**
     * Whether the filter form ``form`` still fits the draft of ``project``:
     * its target is a path of the revision it opened on.
     */
    formIsCurrent(form, project) {
        return Boolean(!form || (project && project.id === form.projectId && project.revision === form.revision));
    }

    closeFilterForm() {
        this.state.filterForm = null;
    }

    addCondition() {
        this.state.filterForm.conditions.push(this.newCondition());
    }

    removeCondition(index) {
        this.state.filterForm.conditions.splice(index, 1);
    }

    setConditionField(condition, name) {
        Object.assign(condition, this.newCondition(name));
    }

    /** How the value of ``condition`` is typed in: none, a list, a date… */
    valueInput(condition) {
        if (["set", "not set"].includes(condition.operator)) {
            return "none";
        }
        const type = this.fieldInfo(condition.field).type;
        if (["boolean", "selection", "date", "datetime"].includes(type)) {
            return type;
        }
        return NUMBER_TYPES.includes(type) ? "number" : "text";
    }

    async createFilter() {
        const form = this.state.filterForm;
        if (!form || this.state.busy) {
            return;
        }
        if (!this.formIsCurrent(form, this.project)) {
            this.state.filterForm = null;
            this.notification.add(_t("The draft changed since the filter form opened: drop the field again."), {
                type: "warning",
            });
            return;
        }
        const conditions = form.conditions
            .filter((c) => c.field)
            .map((c) => ({
                field: c.field,
                operator: c.operator,
                value: conditionValue(this.fieldInfo(c.field).type, c.value),
            }));
        const data = await this.operateAndSelect({
            type: "add_filter",
            target: form.target,
            position: form.position,
            label: form.label,
            conditions,
        });
        if (data) {
            this.state.filterForm = null;
        }
    }

    // ── palette ─────────────────────────────────────────────────────────

    /** The tab the palette shows: one that the view type offers. */
    get paletteTab() {
        const tabs = ["existing"];
        if (this.allows("add_field")) {
            tabs.unshift("new");
        }
        if (this.allows("add_widget") || this.allows("add_separator")) {
            tabs.push("other");
        }
        return tabs.includes(this.state.tab) ? this.state.tab : tabs[0];
    }

    get fieldTypes() {
        return (this.data.field_types || []).map((ttype) => ({ttype, label: fieldTypeLabel(ttype)}));
    }

    get existingFields() {
        const filter = this.state.filter.trim().toLowerCase();
        return (this.data.palette || []).filter(
            (f) => !filter || f.name.toLowerCase().includes(filter) || (f.string || "").toLowerCase().includes(filter)
        );
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

    attributeLabel(attribute) {
        return attributeLabel(attribute);
    }

    axisLabel(axis) {
        return valueLabel("axis", axis) || axis;
    }

    // ── selection and properties ────────────────────────────────────────

    setTab(tab) {
        this.state.tab = tab;
    }

    onCanvasClick() {
        if (!this.state.preview) {
            this.state.selected = null;
        }
    }

    select(path) {
        this.state.selected = this.state.selected === path ? null : path;
        this.state.colors = null;
    }

    get selectedBlock() {
        return this.state.selected && findBlock(this.data.blocks, (b) => b.path === this.state.selected);
    }

    get selectedField() {
        const block = this.selectedBlock;
        return (block && block.kind === "field" && (this.data.fields || {})[block.name]) || null;
    }

    /** Whether ``block`` is the root of the view. */
    isRoot(block) {
        return Boolean(block && this.root && block.path === this.root.path);
    }

    /**
     * The block the properties describe: the selected one, else the view
     * itself when it has attributes to set.
     */
    get propertiesBlock() {
        const block = this.selectedBlock;
        if (block) {
            return block;
        }
        return this.settableOf(this.root).length ? this.root : null;
    }

    /** Whether ``block`` can leave the view (a native node is hidden). */
    canRemove(block) {
        if (!block || this.isRoot(block) || block.kind === "template") {
            return false;
        }
        return !TEMPLATED_TYPES.includes(this.viewType) || block.in_template !== false;
    }

    /**
     * The attributes « set_attribute » writes on ``block``: [{attribute,
     * kind, label, value, required}]. A view element nested in its own view
     * (a <kanban> of a one2many) has none.
     */
    settableOf(block) {
        if (!block || (block.tag === this.viewType && !this.isRoot(block))) {
            return [];
        }
        const attrs = (this.data.settable || {})[block.tag] || {};
        const required = (this.data.required_attributes || {})[block.tag] || [];
        const field = block.kind === "field" ? this.fieldInfo(block.name) : {};
        return Object.entries(attrs)
            .filter(([attribute]) => attribute !== "interval" || DATE_TYPES.includes(field.type))
            .map(([attribute, kind]) => ({
                attribute,
                kind,
                label: attributeLabel(attribute),
                value: (block.attrs || {})[attribute] || "",
                required: required.includes(attribute),
            }));
    }

    /** [[value, label]] of an attribute of ``kind`` on ``block``. */
    choicesOf(entry, block) {
        let choices;
        if (entry.kind === "widget") {
            choices = fieldWidgets(this.fieldInfo(block.name).type);
        } else if (entry.kind === "bool") {
            choices = [
                ["True", valueLabel("bool", "True")],
                ["False", valueLabel("bool", "False")],
            ];
        } else {
            choices = ((this.data.choices || {})[entry.kind] || []).map(([value, label]) => [
                value,
                valueLabel(entry.kind, value) || label,
            ]);
        }
        if (entry.value && !choices.some(([value]) => value === entry.value)) {
            // A value of the arch the editor does not offer stays shown.
            choices = [[entry.value, entry.value], ...choices];
        }
        return choices;
    }

    async setNodeAttribute(block, attribute, value) {
        if (!block || this.state.busy) {
            return;
        }
        const data = await this.operate({type: "set_attribute", target: block.path, attribute, value});
        this.reselect(data, block);
        return data;
    }

    attr(name) {
        const block = this.selectedBlock;
        return (block && block.attrs && block.attrs[name]) || "";
    }

    get hideAttribute() {
        return this.data.hide_mode || (this.viewType === "list" ? "column_invisible" : "invisible");
    }

    /** Whether « hide » sets an attribute (it removes the node in a search or a pivot). */
    get hidesByAttribute() {
        return this.allows("hide") && this.hideAttribute !== "remove";
    }

    async setAttribute(type, value) {
        const block = this.selectedBlock;
        if (!block || this.state.busy) {
            return;
        }
        const data = await this.operate({type, target: block.path, value});
        this.reselect(data, block);
    }

    async updateField(values) {
        const block = this.selectedBlock;
        if (!block || this.state.busy) {
            return;
        }
        const data = await this.operate({type: "update_field", field_name: block.name, field: values});
        this.reselect(data, block);
    }

    async removeSelected() {
        const block = this.selectedBlock;
        if (!block || this.state.busy) {
            return;
        }
        if (await this.operate({type: "remove", target: block.path})) {
            this.state.selected = null;
        }
    }

    reselect(data, block) {
        if (!data) {
            return;
        }
        const found = block.name
            ? this.fieldBlock(data.blocks, block.name)
            : findBlock(data.blocks, (b) => b.path === block.path);
        this.state.selected = found && !this.isRoot(found) ? found.path : null;
    }

    isTrue(value) {
        return isTrue(value);
    }

    async updateSelection(text) {
        if (this.state.busy) {
            return;
        }
        await this.updateField({selection: textToSelection(text)});
    }

    selectionText(field) {
        return selectionToText((field.definition && field.definition.selection) || field.selection);
    }

    async loadComodels() {
        if (!this.state.comodels) {
            this.state.comodels = await this.orm.call(MODEL, "get_comodels", []);
        }
    }

    // ── colors of a timeline ────────────────────────────────────────────

    /**
     * [[name, label]] of the stored fields a color rule can compare: those
     * of the types the server lists (``color_types``).
     */
    get colorFields() {
        const types = this.layout.color_types || [];
        return Object.entries(this.data.fields || {})
            .filter(([name, info]) => info.store && !info.pending && types.includes(info.type) && name !== "id")
            .map(([name, info]) => [name, info.string || name])
            .sort((a, b) => a[1].localeCompare(b[1]));
    }

    editColors() {
        this.state.colors = [this.newColorRule()];
    }

    newColorRule() {
        return {color: "#ec7063", field: "", operator: (this.layout.color_operators || ["=="])[0], value: ""};
    }

    cancelColors() {
        this.state.colors = null;
    }

    addColorRule() {
        this.state.colors.push(this.newColorRule());
    }

    removeColorRule(index) {
        this.state.colors.splice(index, 1);
    }

    /** Write the rules being edited; none removes the colors. */
    async saveColors(rules) {
        const value = (rules || []).filter((rule) => rule.field);
        if (await this.setNodeAttribute(this.root, "colors", value.length ? value : "")) {
            this.state.colors = null;
        }
    }

    // ── toolbar ─────────────────────────────────────────────────────────

    togglePreview() {
        this.state.preview = !this.state.preview;
    }

    /**
     * The props of the preview: the real view with the draft context. A
     * search view shows above the list of the model.
     */
    get previewProps() {
        const context = {[this.data.preview_key]: this.project ? this.project.preview_value : false};
        const props = {
            resModel: this.params.resModel,
            type: this.params.viewType,
            viewId: this.params.viewId,
            context,
            display: {controlPanel: false},
            loadIrFilters: false,
            loadActionMenus: false,
        };
        if (this.params.viewType === "form") {
            props.resId = this.data.sample_res_id || false;
            props.preventEdit = true;
        } else if (this.params.viewType === "search") {
            Object.assign(props, {type: "list", viewId: false, searchViewId: this.params.viewId, display: {}});
        }
        return props;
    }

    get previewKey() {
        return `${this.params.viewType}:${this.project ? this.project.preview_value : "none"}`;
    }

    async openProject() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "erplibre.studio.project",
            res_id: this.project.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async close() {
        try {
            await this.action.restore();
        } catch {
            if (this.params.actionId) {
                await this.action.doAction(this.params.actionId);
            }
        }
    }
}

registry.category("actions").add("erplibre_studio.editor", StudioEditor);
