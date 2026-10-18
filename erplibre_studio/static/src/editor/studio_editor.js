/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillStart, useState} from "@odoo/owl";
import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {serializeDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {View} from "@web/views/view";
import {StudioConfirmDialog} from "./studio_confirm";
import {StudioAppsPanel, groupValue, parseGroupValue} from "./studio_groups";
import {PERMS, StudioModelDialog, accessGrid, accessGroup, accessRows, permLabel} from "./studio_models";
import {StudioModelPreview} from "./studio_preview";
import {StudioRelationDialog, X2MANY_TYPES, fieldTypeFits} from "./studio_relations";

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
            one2many: _t("One2many"),
            many2many: _t("Many2many"),
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

    /**
     * The sub-list an x2many field shows in a form: {comodel, label}, or
     * null. The editor does not descend into it: it is part of the field.
     */
    get subList() {
        if (this.props.viewType !== "form" || this.block.kind !== "field") {
            return null;
        }
        const field = this.field;
        if (!X2MANY_TYPES.includes(field.type) || !field.relation) {
            return null;
        }
        return {comodel: field.relation, label: this.editor.modelLabel(field.relation)};
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
    static components = {StudioBlock, View, StudioModelPreview, StudioAppsPanel};
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.menuService = useService("menu");
        const params = (this.props.action && this.props.action.params) || {};
        this.params = {
            resModel: params.res_model,
            viewId: params.view_id || false,
            viewType: params.view_type || "form",
            actionId: params.action_id || false,
        };
        // The view the editor was opened on: where the canvas goes back to
        // when the model on screen leaves the project.
        this.launch = {resModel: params.res_model, viewId: params.view_id || false, viewType: params.view_type || "form"};
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
            // The canvas shows the view (null), the access grid or the rules.
            panel: null,
            // What the dialogs and the panels offer (get_studio_choices).
            choices: null,
            accessAdd: this.newAccessRow(),
            accessExisting: {},
            ruleForm: null,
            ruleCheck: null,
            // Why the server refused the last Save of the rule form.
            ruleError: null,
            // The preview of a model not created yet: {lineId, viewType,
            // mode, data, key}, shown by the panel « preview ».
            modelPreview: null,
            // Why the server refused the last call of the panel « apps ».
            panelError: null,
        });
        this.previewCount = 0;
        this.ribbonColors = RIBBON_COLORS;
        this.perms = PERMS;
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

    /** The panel the canvas shows instead of the view, while a project is selected. */
    get panel() {
        return this.project ? this.state.panel : null;
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

    /**
     * Call ``method`` of the editor and show the payload it answers. On an
     * error, ``onError(message)`` when given, else a notification; answer
     * null.
     */
    async call(method, args, kwargs = {}, onError = null) {
        this.state.busy = true;
        let data;
        try {
            data = await this.orm.call(MODEL, method, args, kwargs);
        } catch (error) {
            const message = this.errorMessage(error);
            if (onError) {
                onError(message);
            } else {
                this.notification.add(message, {type: "danger"});
            }
            return null;
        } finally {
            this.state.busy = false;
        }
        this.state.data = data;
        this.state.projectId = (data.project && data.project.id) || false;
        this.state.error = null;
        if (!this.formIsCurrent(this.state.filterForm, data.project)) {
            // Its target was located in a draft that is gone.
            this.state.filterForm = null;
        }
        await this.refreshModelPreview();
        return data;
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
            this.launch.viewId = this.launch.viewId || data.view.id;
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
        this.state.panel = null;
        this.state.modelPreview = null;
        Object.assign(this.state, {selected: null, filterForm: null, colors: null, template: null, preview: false});
    }

    /**
     * Edit the view ``viewId`` (false: the default one) of ``viewType`` of
     * ``resModel``, in the same project. Answer whether it opened.
     */
    async openView(resModel, viewId, viewType) {
        if (this.state.busy) {
            return false;
        }
        const projectId = this.project ? this.project.id : false;
        this.state.busy = true;
        try {
            const data = await this.orm.call(MODEL, "get_editor_data", [resModel, viewId, viewType, projectId], {
                pick_project: Boolean(projectId),
            });
            Object.assign(this.params, {resModel, viewType, viewId: data.view.id});
            this.resetCanvas();
            this.state.data = data;
            const keep = this.state.projectId === "new" ? "new" : false;
            this.state.projectId = (data.project && data.project.id) || keep;
            return true;
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return false;
        } finally {
            this.state.busy = false;
        }
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
        if (!(await this.openView(this.params.resModel, false, viewType))) {
            ev.target.value = this.params.viewType;
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

    /** The view the editor was opened on, as ``project_action`` takes it. */
    get launchArgs() {
        const launch = this.launch;
        return [launch.resModel, launch.viewId, launch.viewType];
    }

    /** Whether the menus Apply made for ``before`` and ``after`` (two project payloads) differ. */
    menusChanged(before, after) {
        const menus = (project) => JSON.stringify((project && project.menus) || []);
        return menus(before) !== menus(after);
    }

    /**
     * Run ``action`` on the project and show the payload it answers.
     * ``digest``: the digest of the removal report the user confirmed, for
     * Apply and Revert.
     */
    async projectAction(action, {digest} = {}) {
        if (this.state.busy || !this.project) {
            return null;
        }
        const before = this.project;
        this.state.busy = true;
        let data = null;
        const kwargs = {revision: this.project.revision, fallback: this.launchArgs};
        if (digest) {
            kwargs.digest = digest;
        }
        try {
            data = await this.orm.call(MODEL, "project_action", [this.project.id, action, ...this.viewArgs()], kwargs);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return null;
        } finally {
            this.state.busy = false;
        }
        if (data.notice) {
            this.notification.add(data.notice, {type: "warning", sticky: true});
        }
        if (["action_apply", "action_revert"].includes(action)) {
            // The applied views change what every view shows.
            this.env.bus.trigger("CLEAR-CACHES");
            if (this.menusChanged(before, data.project)) {
                await this.menuService.reload();
            }
        }
        if (data.view_gone) {
            // The model on screen and the one the editor was opened on are gone.
            await this.action.doAction("home");
            return null;
        }
        if (data.view_changed || data.model !== this.params.resModel || data.view.id !== this.params.viewId) {
            // Another view, or the view of a model not created yet that
            // Apply created.
            Object.assign(this.params, {resModel: data.model, viewType: data.view_type, viewId: data.view.id});
            if (data.view_changed) {
                this.resetCanvas();
            }
        }
        this.state.data = data;
        this.state.projectId = (data.project && data.project.id) || false;
        this.state.error = null;
        if (!this.formIsCurrent(this.state.filterForm, data.project)) {
            this.state.filterForm = null;
        }
        if (action !== "action_apply") {
            this.state.selected = null;
        }
        await this.refreshModelPreview();
        return data;
    }

    /**
     * Apply the project. When Apply would remove records, values or group
     * members, its removal report shows first and Apply runs once the user
     * confirmed it, with its digest. A project never applied removes
     * nothing. Answer the payload, or null.
     */
    async applyProject() {
        if (this.state.busy || !this.project) {
            return null;
        }
        let answer = null;
        if (this.project.applied) {
            answer = await this.readReport("get_apply_report");
            if (!answer) {
                return null;
            }
        }
        if (!answer || !answer.confirm) {
            return this.projectAction("action_apply", {digest: answer && answer.digest});
        }
        return new Promise((resolve) => {
            this.dialog.add(
                StudioConfirmDialog,
                {
                    title: _t("Apply the project"),
                    intro: _t("Apply removes from the database what the draft no longer has, with its data:"),
                    report: answer.report,
                    digest: answer.digest,
                    refused: false,
                    confirmLabel: _t("Apply"),
                    confirm: async (digest) => {
                        const data = await this.projectAction("action_apply", {digest});
                        if (data) {
                            resolve(data);
                        }
                        return Boolean(data);
                    },
                    reload: () => this.readReport("get_apply_report"),
                },
                {onClose: () => resolve(null)}
            );
        });
    }

    /**
     * Revert the project, once the user confirmed what it removes from the
     * database: the report of the server, its digest sent with Revert.
     */
    async revertProject() {
        if (this.state.busy || !this.project) {
            return;
        }
        const answer = await this.readReport("get_revert_report");
        if (!answer) {
            return;
        }
        this.dialog.add(StudioConfirmDialog, {
            title: _t("Revert the project"),
            intro: _t(
                "Revert removes from the database everything the project created; its lines and its changes stay as a draft:"
            ),
            report: answer.report,
            digest: answer.digest,
            refused: answer.refused || false,
            confirmLabel: _t("Revert"),
            confirm: async (digest) => Boolean(await this.projectAction("action_revert", {digest})),
            reload: () => this.readReport("get_revert_report"),
        });
    }

    /** The answer of the report ``method`` (get_apply_report, get_revert_report), or null. */
    async readReport(method) {
        this.state.busy = true;
        try {
            return await this.orm.call(MODEL, method, [this.project.id]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    /** Whether the project has something in the database to revert. */
    get canRevert() {
        return Boolean(this.project && (this.project.applied || this.project.state !== "draft"));
    }

    async selectProject(ev) {
        if (this.state.busy) {
            return;
        }
        const value = ev.target.value;
        this.state.selected = null;
        this.closePanel();
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
        if (item.kind === "new" && !fieldTypeFits(item.ttype, viewType)) {
            return false;
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
        if (item.kind === "new" && X2MANY_TYPES.includes(item.ttype)) {
            // A relation needs its comodel, and its inverse or its table.
            await this.openRelationDialog(item.ttype, target, position);
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

    /** The new field types the palette offers: an x2many only where it shows. */
    get fieldTypes() {
        return (this.data.field_types || [])
            .filter((ttype) => fieldTypeFits(ttype, this.viewType))
            .map((ttype) => ({ttype, label: fieldTypeLabel(ttype)}));
    }

    // ── relation fields ─────────────────────────────────────────────────

    /**
     * The dialog of a new ``ttype`` field (one2many, many2many) dropped on
     * the hook ``target`` / ``position``: Create adds it there.
     */
    async openRelationDialog(ttype, target, position) {
        if (!this.project) {
            return;
        }
        let comodels;
        try {
            comodels = await this.orm.call(MODEL, "get_comodels", [this.project.id]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return;
        }
        const projectId = this.project.id;
        const model = this.params.resModel;
        this.dialog.add(StudioRelationDialog, {
            ttype,
            model,
            modelLabel: this.data.model_name || model,
            comodels,
            projectModels: this.projectModels.map((m) => m.model),
            loadChoices: (comodel, label) =>
                this.orm.call(MODEL, "get_relation_choices", [projectId, model, comodel, ttype], {label}),
            save: async (field) =>
                Boolean(await this.operateAndSelect({type: "add_field", target, position, field}, {kind: "new"})),
        });
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

    /** The models a many2one can point to, the pending models of the project too. */
    async loadComodels() {
        const projectId = this.project ? this.project.id : false;
        this.state.comodels = await this.orm.call(MODEL, "get_comodels", [projectId]);
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

    // ── models of the project ───────────────────────────────────────────

    /**
     * Call ``method`` on the project with ``params``, then the view on
     * screen and the revision, as every editor call on the draft.
     */
    async projectCall(method, params, onError = null) {
        if (this.state.busy || !this.project) {
            return null;
        }
        return this.call(
            method,
            [this.project.id, ...params, ...this.viewArgs()],
            {
                revision: this.project.revision,
            },
            onError
        );
    }

    /** What the dialogs and the panels offer, read again at each opening. */
    async loadChoices() {
        const projectId = this.project ? this.project.id : false;
        try {
            this.state.choices = await this.orm.call(MODEL, "get_studio_choices", [projectId]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            this.state.choices = null;
        }
        return this.state.choices;
    }

    /** The models the project creates, as the payload lists them. */
    get projectModels() {
        return (this.project && this.project.models) || [];
    }

    get projectRules() {
        return (this.project && this.project.rules) || [];
    }

    viewTypeLabel(viewType) {
        return {form: _t("Form"), list: _t("List"), search: _t("Search")}[viewType] || viewType;
    }

    /** The label of ``model``: a model of the project, else of the database. */
    modelLabel(model) {
        const line = this.projectModels.find((m) => m.model === model);
        if (line) {
            return line.name;
        }
        const item = this.choiceModels.find((m) => m[0] === model);
        return item ? item[1] : model;
    }

    /** The dialog of a new model, or of the model line ``line``. */
    async openModelDialog(line = null) {
        if (!this.project) {
            this.notification.add(_t("Choose or create a studio project first."), {type: "warning"});
            return;
        }
        const choices = await this.loadChoices();
        if (!choices) {
            return;
        }
        this.dialog.add(StudioModelDialog, {
            project: this.project,
            choices,
            line,
            taken: [
                ...(choices.taken_models || []),
                ...choices.models.map((m) => m[0]),
                ...this.projectModels.map((m) => m.model),
            ],
            save: (values) => (line ? this.updateModel(line, values) : this.createModel(values)),
        });
    }

    async createModel(values) {
        return Boolean(await this.projectCall("create_model", [values]));
    }

    async updateModel(line, values) {
        return Boolean(await this.projectCall("update_model", [line.id, values]));
    }

    /** The apps of the project, as the payload lists them. */
    get projectApps() {
        return (this.project && this.project.apps) || [];
    }

    /** Where the menu of the model line ``line`` goes: its app, or its parent menu. */
    menuPlace(line) {
        if (line.menu_mode === "menu") {
            return line.menu_parent ? line.menu_parent[1] : _t("Under a menu");
        }
        const app = this.projectApps.find((a) => a.id === line.app_id);
        return app ? _t("App %(name)s", {name: app.name}) : _t("No app");
    }

    get pendingViewTitle() {
        return _t("Edit this view before Apply creates the model");
    }

    removeModel(line) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove the model"),
            body: _t(
                "Remove %(model)s from the project, with its access rows, its rules and the changes of its views? " +
                    "Once applied, it leaves the database with its records.",
                {model: line.model}
            ),
            confirmLabel: _t("Remove"),
            confirm: async () => {
                const data = await this.projectCall("remove_model", [line.id]);
                if (data && line.model === this.params.resModel) {
                    // Apply removes the model on screen: back to the view
                    // the editor was opened on, or out of the editor when
                    // that view is of the model too.
                    if (this.launch.resModel === line.model) {
                        await this.close();
                    } else {
                        await this.openView(...this.launchArgs);
                    }
                }
            },
            cancel: () => {},
        });
    }

    /**
     * Edit the default ``viewType`` view of the model line ``line``: the
     * view Apply created for it, or, before Apply, the default view the
     * model will have, whose changes Apply moves to the created view.
     */
    async openModel(line, viewType = "form") {
        if (!line.applied) {
            return this.openView(line.model, false, viewType);
        }
        const viewId = line.views && line.views[viewType];
        if (!viewId) {
            return false;
        }
        return this.openView(line.model, viewId, viewType);
    }

    /** Apply the project, then edit the form of the model line ``line``. */
    async applyAndOpen(line) {
        const data = await this.applyProject();
        const applied = data && data.project && (data.project.models || []).find((m) => m.id === line.id);
        if (applied && applied.applied) {
            await this.openModel(applied, "form");
        }
    }

    // ── access rights and record rules ──────────────────────────────────

    /** Show the access grid or the rules on the canvas; again, the view. */
    async togglePanel(panel) {
        if (this.state.busy) {
            return;
        }
        if (this.state.panel === panel) {
            this.closePanel();
            return;
        }
        if (!this.project || !(await this.loadChoices())) {
            return;
        }
        Object.assign(this.state, {
            selected: null,
            preview: false,
            panel,
            ruleForm: null,
            ruleCheck: null,
            ruleError: null,
            modelPreview: null,
            panelError: null,
        });
        this.state.accessExisting = {};
        if (panel === "access") {
            await this.loadAccessExisting(this.accessGrid.map((entry) => entry.model));
        }
    }

    closePanel() {
        Object.assign(this.state, {
            panel: null,
            ruleForm: null,
            ruleCheck: null,
            ruleError: null,
            modelPreview: null,
            panelError: null,
        });
    }

    get choiceModels() {
        return (this.state.choices && this.state.choices.models) || [];
    }

    get choiceGroups() {
        return (this.state.choices && this.state.choices.groups) || [];
    }

    groupName(groupId) {
        const group = this.choiceGroups.find((g) => g.id === groupId);
        return group ? group.name : String(groupId);
    }

    /** The value of ``group`` (of the choices) in a group select. */
    groupValue(group) {
        return groupValue(group);
    }

    /** [value, name] of the group of the access row ``row`` of the payload. */
    accessGroup(row) {
        return accessGroup(row);
    }

    get projectGroupSuffix() {
        return _t("project");
    }

    /** The name of the group of the project ``lineId``, from the payload. */
    groupLineName(lineId) {
        const line = ((this.project && this.project.groups) || []).find((g) => g.id === lineId);
        if (line) {
            const app = this.projectApps.find((a) => a.id === line.app_id);
            return app ? `${app.name} / ${line.name}` : line.name;
        }
        const choice = this.choiceGroups.find((g) => g.project && g.line_id === lineId);
        return choice ? choice.name : String(lineId);
    }

    missingGroupText(xmlid) {
        return _t("This group no longer exists: %(group)s", {group: xmlid});
    }

    /** Whether Apply refuses the rule ``rule`` of the payload: no group, not global. */
    ruleNeedsGroup(rule) {
        return !rule.global_rule && !rule.groups.length && !(rule.group_lines || []).length;
    }

    permLabel(perm) {
        return permLabel(perm);
    }

    get accessGrid() {
        return this.project ? accessGrid(this.project) : [];
    }

    /** The row being added; ``group_id`` holds the value of the group select. */
    newAccessRow() {
        return {model: "", group_id: "", perm_read: true, perm_write: false, perm_create: false, perm_unlink: false};
    }

    /** The access rows of the other modules on ``models``, shown read-only. */
    async loadAccessExisting(models) {
        const projectId = this.project && this.project.id;
        for (const model of models) {
            if (model in this.state.accessExisting) {
                continue;
            }
            try {
                this.state.accessExisting[model] = await this.orm.call(MODEL, "get_access_existing", [
                    projectId,
                    model,
                ]);
            } catch (error) {
                this.notification.add(this.errorMessage(error), {type: "danger"});
                return;
            }
        }
    }

    /** Replace the access rows of the project: one call, one change of the draft. */
    async setAccess(rows) {
        return this.projectCall("set_access", [rows]);
    }

    async toggleAccess(row, perm) {
        const rows = accessRows(this.project.access);
        const index = this.project.access.findIndex((r) => r.id === row.id);
        rows[index][perm] = !rows[index][perm];
        await this.setAccess(rows);
    }

    /** Remove an access row: the grid drops a row that gives no right. */
    async removeAccess(row) {
        const rows = accessRows(this.project.access.filter((r) => r.id !== row.id));
        await this.setAccess(rows);
    }

    async addAccess() {
        const add = this.state.accessAdd;
        const group = parseGroupValue(add.group_id);
        if (!add.model || !group) {
            return;
        }
        const value = String(add.group_id);
        if (this.project.access.some((r) => r.model === add.model && accessGroup(r)[0] === value)) {
            this.notification.add(_t("This group has a row on this model already: change its rights in the grid."), {
                type: "warning",
            });
            return;
        }
        const row = {model: add.model, ...group};
        for (const perm of PERMS) {
            row[perm] = Boolean(add[perm]);
        }
        if (!PERMS.some((perm) => row[perm])) {
            this.notification.add(_t("An access row gives at least one right."), {type: "warning"});
            return;
        }
        if (await this.setAccess([...accessRows(this.project.access), row])) {
            this.state.accessAdd = this.newAccessRow();
            await this.loadAccessExisting([row.model]);
        }
    }

    /** The form of the rule ``rule`` of the payload, or of a new rule. */
    editRule(rule = null) {
        const models = this.projectModels.map((m) => m.model);
        this.state.ruleForm = rule
            ? {
                  id: rule.id,
                  name: rule.name,
                  model: rule.model,
                  domain: rule.domain,
                  group_ids: rule.groups.map((g) => g[0]),
                  group_line_ids: (rule.group_lines || []).map((g) => g[0]),
                  global_rule: Boolean(rule.global_rule),
                  // The groups the rule names that left the database:
                  // saving the rule from the form records its groups again.
                  missing_groups: [...(rule.missing_groups || [])],
                  ...Object.fromEntries(PERMS.map((perm) => [perm, rule[perm]])),
              }
            : {
                  id: false,
                  name: "",
                  model: models[0] || "",
                  domain: "[]",
                  group_ids: [],
                  group_line_ids: [],
                  global_rule: false,
                  missing_groups: [],
                  ...Object.fromEntries(PERMS.map((perm) => [perm, true])),
              };
        this.state.ruleCheck = null;
        this.state.ruleError = null;
    }

    closeRuleForm() {
        this.state.ruleForm = null;
        this.state.ruleCheck = null;
        this.state.ruleError = null;
    }

    /**
     * The groups of the rule form: [{value, name, project}], the existing
     * groups then those of the project.
     */
    get ruleFormGroups() {
        const form = this.state.ruleForm;
        if (!form) {
            return [];
        }
        return [
            ...form.group_ids.map((id) => ({value: String(id), name: this.groupName(id), project: false})),
            ...form.group_line_ids.map((id) => ({value: `line:${id}`, name: this.groupLineName(id), project: true})),
        ];
    }

    addRuleGroup(ev) {
        const group = parseGroupValue(ev.target.value);
        ev.target.value = "";
        const form = this.state.ruleForm;
        if (group && group.group_id && !form.group_ids.includes(group.group_id)) {
            form.group_ids.push(group.group_id);
        } else if (group && group.group_line_id && !form.group_line_ids.includes(group.group_line_id)) {
            form.group_line_ids.push(group.group_line_id);
        }
    }

    removeGroupLabel(name) {
        return _t("Remove the group %(group)s", {group: name});
    }

    removeRuleGroup(value) {
        const form = this.state.ruleForm;
        const group = parseGroupValue(value) || {};
        form.group_ids = form.group_ids.filter((id) => id !== group.group_id);
        form.group_line_ids = form.group_line_ids.filter((id) => id !== group.group_line_id);
    }

    /** « Global »: the rule applies to every user, and names no group. */
    setRuleGlobal(checked) {
        const form = this.state.ruleForm;
        form.global_rule = checked;
        if (checked) {
            form.group_ids = [];
            form.group_line_ids = [];
        }
    }

    get domainPlaceholder() {
        return "[('create_uid', '=', user.id)]";
    }

    /** The answer of the last check, while the form holds the domain it checked. */
    get ruleCheck() {
        const check = this.state.ruleCheck;
        const form = this.state.ruleForm;
        return check && form && check.model === form.model && check.domain === form.domain ? check : null;
    }

    ruleCheckText(check) {
        if (!check.ok) {
            return check.error;
        }
        if (check.count === false) {
            return _t("The domain reads well; Apply checks its fields once it created the model.");
        }
        return _t("The domain applies: %(count)s record(s) match it.", {count: check.count});
    }

    /** The domain of the form, as the server evaluates it for a rule. */
    async checkRule() {
        const form = this.state.ruleForm;
        if (!form || !this.project) {
            return;
        }
        const {model, domain} = form;
        try {
            const result = await this.orm.call(MODEL, "check_rule_domain", [this.project.id, model, domain]);
            this.state.ruleCheck = {...result, model, domain};
        } catch (error) {
            this.state.ruleCheck = {ok: false, error: this.errorMessage(error), model, domain};
        }
    }

    /**
     * Save the rule of the form. A refusal shows at the top of the form
     * until the next Save or Cancel: it may be about the domain, the model,
     * the groups or the draft itself.
     */
    async saveRule() {
        const form = this.state.ruleForm;
        if (!form) {
            return;
        }
        this.state.ruleError = null;
        const {missing_groups, ...values} = form; // eslint-disable-line no-unused-vars
        const data = await this.projectCall("save_rule", [values], (message) => {
            this.state.ruleError = message;
        });
        if (data) {
            this.closeRuleForm();
        }
    }

    async removeRule(rule) {
        if (this.state.ruleForm && this.state.ruleForm.id === rule.id) {
            this.closeRuleForm();
        }
        await this.projectCall("remove_rule", [rule.id]);
    }

    // ── preview of a model not created yet ──────────────────────────────

    /** The model line of the project whose model is ``model``, or null. */
    modelLine(model) {
        return this.projectModels.find((line) => line.model === model) || null;
    }

    /**
     * Show the preview of the model line ``line``, not created yet, in
     * ``viewType`` and ``mode`` (« simulation », « real »). The server
     * answers its views and fields; nothing is written.
     */
    async openModelPreview(line, viewType = "form", mode = "simulation") {
        if (this.state.busy || !this.project) {
            return;
        }
        this.state.busy = true;
        let data;
        try {
            data = await this.orm.call(MODEL, "get_model_preview", [this.project.id, line.id, viewType, mode]);
        } catch (error) {
            this.notification.add(this.errorMessage(error), {type: "danger"});
            return;
        } finally {
            this.state.busy = false;
        }
        Object.assign(this.state, {
            selected: null,
            preview: false,
            panel: "preview",
            ruleForm: null,
            filterForm: null,
            modelPreview: {lineId: line.id, viewType, mode, data, key: ++this.previewCount},
        });
    }

    /**
     * After a change of the draft, the preview on screen follows it: shown
     * again from the new draft (the real mode while the approval stands),
     * or closed, with a notice, once its model left the project or Apply
     * created it.
     */
    async refreshModelPreview() {
        const preview = this.state.modelPreview;
        if (!preview || this.state.panel !== "preview" || !this.project) {
            return;
        }
        const line = this.previewLine;
        if (!line || line.applied) {
            this.closePanel();
            this.notification.add(
                line
                    ? _t("The model %(model)s exists now: its preview is closed.", {model: line.model})
                    : _t("The model of the preview left the project: its preview is closed."),
                {type: "info"}
            );
            return;
        }
        const mode = preview.mode === "real" && this.project.approved ? "real" : "simulation";
        await this.openModelPreview(line, preview.viewType, mode);
    }

    /** The model line of the preview on screen, while it is in the project. */
    get previewLine() {
        const preview = this.state.modelPreview;
        return (preview && this.projectModels.find((line) => line.id === preview.lineId)) || null;
    }

    /** Show the preview on screen in another view type or mode. */
    async switchModelPreview(viewType, mode) {
        const line = this.previewLine;
        if (line) {
            await this.openModelPreview(line, viewType, mode);
        }
    }

    /** Approve, or withdraw the approval of, the real preview; then show the preview again. */
    async approvePreview(approve = true) {
        // The preview follows: back to the simulation once the approval is withdrawn.
        await this.projectAction(approve ? "action_approve" : "action_unapprove");
    }

    // ── toolbar ─────────────────────────────────────────────────────────

    /**
     * The preview of the view on screen: the real view with the draft, or
     * for a model not created yet, its model preview.
     */
    async togglePreview() {
        if (this.data.view && this.data.view.pending) {
            if (this.state.panel === "preview") {
                this.closePanel();
                return;
            }
            const line = this.modelLine(this.params.resModel);
            if (line) {
                await this.openModelPreview(line, this.viewType);
            }
            return;
        }
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

    get draftPreviewTitle() {
        return _t("Show the view as its editor sees the draft");
    }

    get pendingPreviewTitle() {
        return _t("Preview the model before Apply creates it: nothing is saved");
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
