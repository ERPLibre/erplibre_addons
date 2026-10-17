/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";

// The longest model name the server accepts (arch.MODEL_NAME_SIZE).
export const MODEL_NAME_SIZE = 50;
// The rights of an access row or a rule, in the order of the grid.
export const PERMS = ["perm_read", "perm_write", "perm_create", "perm_unlink"];
// The icon of an app without one of its own (DEFAULT_APP_ICON of the server).
export const DEFAULT_APP_ICON = "erplibre_studio,static/description/icon.png";

/** The label of a right of the grid. */
export function permLabel(perm) {
    return (
        {
            perm_read: _t("Read"),
            perm_write: _t("Write"),
            perm_create: _t("Create"),
            perm_unlink: _t("Delete"),
        }[perm] || perm
    );
}

/** ``label`` in ASCII lower case letters, digits and underscores (arch._slug). */
export function slug(label) {
    return (label || "")
        .normalize("NFKD")
        .replace(/[^\x00-\x7f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "");
}

/**
 * A free « x_ » model name made of ``label``, as the server makes it
 * (arch.model_name_from_label): a letter after « x_ », at most
 * ``MODEL_NAME_SIZE`` characters, not in ``taken``.
 */
export function modelNameFromLabel(label, taken = []) {
    let text = slug(label) || "model";
    if (!/^[a-z]/.test(text)) {
        text = `model_${text}`;
    }
    const base = `x_${text}`.slice(0, MODEL_NAME_SIZE - 4).replace(/_+$/, "");
    const used = new Set(taken);
    let name = base;
    for (let count = 2; used.has(name); count++) {
        name = `${base}_${count}`;
    }
    return name;
}

/** The menus of ``menus`` ({id, name}) whose name holds ``text``, case aside. */
export function filterMenus(menus, text) {
    const filter = (text || "").trim().toLowerCase();
    return (menus || []).filter((menu) => !filter || menu.name.toLowerCase().includes(filter));
}

/**
 * The access grid of ``project``: [{model, rows}], the models the project
 * creates first, then the other models of its rows; ``extra`` adds models
 * without a row yet.
 */
export function accessGrid(project, extra = []) {
    const models = [];
    const add = (model) => {
        if (model && !models.includes(model)) {
            models.push(model);
        }
    };
    (project.models || []).forEach((line) => add(line.model));
    (project.access || []).forEach((row) => add(row.model));
    extra.forEach(add);
    return models.map((model) => ({model, rows: (project.access || []).filter((row) => row.model === model)}));
}

/** The rows ``set_access`` takes, from the access rows of a payload. */
export function accessRows(access) {
    return (access || []).map((row) => ({
        model: row.model,
        group_id: row.group[0],
        ...Object.fromEntries(PERMS.map((perm) => [perm, Boolean(row[perm])])),
    }));
}

/**
 * The dialog of a model of the project: a new one, or the model line
 * ``line``. ``save(values, app)`` sends it and answers whether the server
 * took it; ``app`` is the new {name, icon} of the app of the project, or
 * null when it does not change.
 */
export class StudioModelDialog extends Component {
    static template = "erplibre_studio.ModelDialog";
    static components = {Dialog};
    static props = {
        project: Object,
        choices: Object,
        line: {type: [Object, {value: null}], optional: true},
        taken: {type: Array, optional: true},
        save: Function,
        close: Function,
    };

    setup() {
        const line = this.props.line;
        const app = this.props.project.app || {};
        this.state = useState({
            name: line ? line.name : "",
            model: line ? line.model : "",
            modelEdited: Boolean(line),
            chatter: line ? line.chatter : false,
            mode: line ? line.menu_mode : "app",
            appName: app.name || "",
            appNameEdited: Boolean(app.name),
            appIcon: app.icon || false,
            parentId: (line && line.menu_parent && line.menu_parent[0]) || false,
            menuFilter: "",
            menuName: (line && line.menu_name) || "",
            saving: false,
        });
    }

    get line() {
        return this.props.line || null;
    }

    get title() {
        return this.line ? _t("Edit the model %(model)s", {model: this.line.model}) : _t("New model");
    }

    get project() {
        return this.props.project;
    }

    get choices() {
        return this.props.choices;
    }

    /** Whether the project has its app already. */
    get hasApp() {
        return Boolean(this.project.app);
    }

    /** Whether the dialog shows the name and the icon of the app. */
    get editsApp() {
        return this.state.mode === "app" && (!this.hasApp || Boolean(this.line));
    }

    get appLabel() {
        return this.hasApp
            ? _t("In the app « %(name)s » of the project", {name: this.project.app.name})
            : _t("New app");
    }

    /** The technical name cannot change once Apply created the model. */
    get modelLocked() {
        return Boolean(this.line && this.line.applied);
    }

    /** Once applied, Odoo keeps the chatter of a model. */
    get chatterLocked() {
        return Boolean(this.line && this.line.applied && this.line.chatter);
    }

    get menus() {
        return filterMenus(this.choices.menus, this.state.menuFilter);
    }

    /** Whether the dialog shows the name of the app, and it is empty. */
    get appNameMissing() {
        return this.editsApp && !this.state.appName.trim();
    }

    get canSave() {
        const state = this.state;
        if (state.saving || !state.name.trim() || !state.model.trim()) {
            return false;
        }
        if (state.mode === "menu") {
            return Boolean(state.parentId);
        }
        return !this.appNameMissing;
    }

    /** The technical name and the app name follow the label until edited. */
    setName(value) {
        this.state.name = value;
        if (!this.state.modelEdited) {
            this.state.model = value.trim() ? modelNameFromLabel(value, this.props.taken || []) : "";
        }
        if (!this.state.appNameEdited) {
            this.state.appName = value;
        }
    }

    setModel(value) {
        this.state.model = value;
        this.state.modelEdited = true;
    }

    setAppName(value) {
        this.state.appName = value;
        this.state.appNameEdited = true;
    }

    setMode(mode) {
        this.state.mode = mode;
    }

    /** Whether the icon ``value`` is the one of the app; none is the studio one. */
    isIcon(value) {
        return value === (this.state.appIcon || DEFAULT_APP_ICON);
    }

    setIcon(value) {
        this.state.appIcon = value === DEFAULT_APP_ICON ? false : value;
    }

    setParent(value) {
        this.state.parentId = parseInt(value) || false;
    }

    /** The values of ``create_model`` / ``update_model``. */
    get values() {
        const state = this.state;
        const menu = {mode: state.mode, name: state.menuName.trim()};
        if (state.mode === "menu") {
            menu.parent_id = state.parentId;
        } else if (!this.hasApp) {
            Object.assign(menu, {app_name: state.appName.trim(), app_icon: state.appIcon || false});
        }
        const values = {name: state.name.trim(), chatter: state.chatter, menu};
        if (!this.modelLocked) {
            values.model = state.model.trim();
        }
        return values;
    }

    /**
     * The app of an edited model in the app: a new one, or the app of the
     * project when its name or its icon changed; else null. A new model
     * names its app in ``values``.
     */
    get app() {
        if (!this.line || this.state.mode !== "app") {
            return null;
        }
        const app = {name: this.state.appName.trim(), icon: this.state.appIcon || false};
        const current = this.project.app;
        if (current && app.name === current.name && app.icon === (current.icon || false)) {
            return null;
        }
        return app;
    }

    async save() {
        if (!this.canSave) {
            return;
        }
        this.state.saving = true;
        if (await this.props.save(this.values, this.app)) {
            this.props.close();
            return;
        }
        this.state.saving = false;
    }
}
