/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillStart, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {View} from "@web/views/view";

const MODEL = "erplibre.studio.editor";
export const DRAGGING_CLASS = "o_erplibre_studio_dragging";

const TRUE_VALUES = ["1", "True", "true"];

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

    /** A group of groups lays its groups out side by side, as Odoo does. */
    get isRow() {
        const children = this.block.children || [];
        return this.block.tag === "group" && children.length > 0 && children.every((child) => child.tag === "group");
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
        if (this.field.pending) {
            flags.push({key: "pending", label: _t("new")});
        }
        return flags;
    }

    selectPage(index) {
        this.editor.state.pages[this.block.path] = index;
    }
}
StudioBlock.components = {StudioBlock};

/**
 * The studio editor: a client action on one form or list view. The server
 * holds the draft; every drop or property change is one operation, and the
 * editor renders the payload it answers.
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
        });
        onWillStart(() => this.load());
    }

    get data() {
        return this.state.data;
    }

    /** The editor itself, for the blocks it renders. */
    get editor() {
        return this;
    }

    /**
     * The project the selector shows, or null: while « Choose a project… »
     * or « New project… » is selected, no edit reaches a project.
     */
    get project() {
        const project = this.data.project;
        return project && project.id === this.state.projectId ? project : null;
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
            this.state.error = _t("Open the studio from the debug menu of a form or a list.");
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
            ev.dataTransfer.setData("text/plain", item.path || item.ttype || item.name || "");
        }
        document.body.classList.add(DRAGGING_CLASS);
    }

    endDrag() {
        this.state.dragging = null;
        this.state.hook = null;
        document.body.classList.remove(DRAGGING_CLASS);
    }

    hookKey(target, position) {
        return `${position}:${target}`;
    }

    overHook(ev, target, position) {
        if (!this.state.dragging) {
            return;
        }
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = "move";
        }
        this.state.hook = this.hookKey(target, position);
    }

    leaveHook(target, position) {
        if (this.state.hook === this.hookKey(target, position)) {
            this.state.hook = null;
        }
    }

    async dropOnHook(ev, target, position) {
        ev.preventDefault();
        const item = this.state.dragging;
        this.endDrag();
        if (!item || this.state.busy) {
            return;
        }
        let operation;
        if (item.kind === "node") {
            if (item.path === target) {
                return;
            }
            operation = {type: "move", source: item.path, target, position};
        } else if (item.kind === "new") {
            operation = {
                type: "add_field",
                target,
                position,
                field: {ttype: item.ttype, field_description: fieldTypeLabel(item.ttype)},
            };
        } else {
            operation = {type: "add_existing_field", target, position, field_name: item.name};
        }
        const before = new Set(Object.keys(this.data.fields || {}));
        const data = await this.operate(operation);
        if (!data) {
            return;
        }
        // Select what was dropped.
        const name = item.kind === "new" ? Object.keys(data.fields).find((n) => !before.has(n)) : item.name;
        const block = name && findBlock(data.blocks, (b) => b.kind === "field" && b.name === name);
        this.state.selected = block ? block.path : null;
    }

    // ── palette ─────────────────────────────────────────────────────────

    get fieldTypes() {
        return (this.data.field_types || []).map((ttype) => ({ttype, label: fieldTypeLabel(ttype)}));
    }

    get existingFields() {
        const filter = this.state.filter.trim().toLowerCase();
        return (this.data.palette || []).filter(
            (f) => !filter || f.name.toLowerCase().includes(filter) || (f.string || "").toLowerCase().includes(filter)
        );
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
    }

    get selectedBlock() {
        return this.state.selected && findBlock(this.data.blocks, (b) => b.path === this.state.selected);
    }

    get selectedField() {
        const block = this.selectedBlock;
        return (block && block.kind === "field" && (this.data.fields || {})[block.name]) || null;
    }

    attr(name) {
        const block = this.selectedBlock;
        return (block && block.attrs && block.attrs[name]) || "";
    }

    get hideAttribute() {
        return this.data.view_type === "list" ? "column_invisible" : "invisible";
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
        const found =
            block.kind === "field"
                ? findBlock(data.blocks, (b) => b.kind === "field" && b.name === block.name)
                : findBlock(data.blocks, (b) => b.path === block.path);
        this.state.selected = found ? found.path : null;
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

    // ── toolbar ─────────────────────────────────────────────────────────

    togglePreview() {
        this.state.preview = !this.state.preview;
    }

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
        }
        return props;
    }

    get previewKey() {
        return this.project ? this.project.preview_value : "none";
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
