/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onMounted, onWillUnmount, status, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";
import {useDebounced} from "@web/core/utils/timing";
import {NAME_CHECK_DELAY} from "./studio_field_name";

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

/**
 * The rows ``set_access`` takes, from the access rows of a payload: a row
 * names an existing group (``group_id``) or a group of the project
 * (``group_line_id``).
 */
export function accessRows(access) {
    return (access || []).map((row) => ({
        model: row.model,
        ...(row.group_line ? {group_line_id: row.group_line[0]} : {group_id: row.group[0]}),
        ...Object.fromEntries(PERMS.map((perm) => [perm, Boolean(row[perm])])),
    }));
}

/** The group of an access row of a payload: [value, name], as a group select gives it. */
export function accessGroup(row) {
    if (row.group_line) {
        return [`line:${row.group_line[0]}`, row.group_line[1]];
    }
    return row.group ? [String(row.group[0]), row.group[1]] : ["", ""];
}

// Where the dialog puts the menu of a model: in an app of the project, in
// a new app made with the model, under an existing menu.
export const MENU_PLACES = ["project", "new_app", "menu"];

/**
 * The place of MENU_PLACES of the model line ``line`` among the apps
 * ``apps`` of the project: « menu » under a menu, « project » in one of
 * the apps, else « new_app »; a new model goes in the first app of the
 * project, else in a new app.
 */
export function menuPlace(line, apps) {
    if (line && line.menu_mode === "menu") {
        return "menu";
    }
    const appId = line ? line.app_id : apps[0] && apps[0].id;
    return appId && apps.some((app) => app.id === appId) ? "project" : "new_app";
}

/**
 * The dialog of a model of the project: a new one, or the model line
 * ``line``. Its menu goes in an app of the project, a new app made with
 * the model, or under an existing menu (MENU_PLACES); the dialog shows
 * the path of the menu it makes. ``save(values)`` sends it and answers
 * whether the server took it.
 *
 * The technical name follows the rule of the database (``rule``, the
 * ``model_name_rule`` of the payload; none is the production rule, x_
 * required). With ``checkName(name, label)``, the name is checked once
 * the typing pauses (NAME_CHECK_DELAY), and on opening for a line not
 * applied yet; each check is a request numbered in order, and an answer
 * that arrives after a newer request, or once the dialog is gone, is
 * dropped. Save waits while the last answer about the name on screen
 * says it does not apply; an answer that is an error of the call blocks
 * nothing, the server checks the name again on save.
 */
export class StudioModelDialog extends Component {
    static template = "erplibre_studio.ModelDialog";
    static components = {Dialog};
    static props = {
        project: Object,
        choices: Object,
        line: {type: [Object, {value: null}], optional: true},
        taken: {type: Array, optional: true},
        // The rule of the database (``model_name_rule`` of the payload).
        rule: {type: [Object, {value: null}], optional: true},
        // ``checkName(name, label)``: the answer of ``check_model_name``.
        checkName: {type: Function, optional: true},
        save: Function,
        close: Function,
    };

    setup() {
        const line = this.props.line;
        const apps = this.apps;
        const place = menuPlace(line, apps);
        const appId = place === "project" ? (line ? line.app_id : apps[0].id) : (apps[0] && apps[0].id) || false;
        this.places = MENU_PLACES;
        this.state = useState({
            name: line ? line.name : "",
            model: line ? line.model : "",
            modelEdited: Boolean(line),
            chatter: line ? line.chatter : false,
            place,
            appId,
            appName: "",
            appNameEdited: Boolean(line),
            appIcon: false,
            parentId: (line && line.menu_parent && line.menu_parent[0]) || false,
            menuFilter: "",
            menuName: (line && line.menu_name) || "",
            saving: false,
            // The last answer of ``checkName``, for the name it names
            // (``check.name``); ``checking``: a request is on its way.
            check: null,
            checking: false,
        });
        this.request = 0;
        this.scheduleCheck = useDebounced(() => this.checkName(), NAME_CHECK_DELAY);
        onMounted(() => {
            if (this.state.model.trim()) {
                this.checkName();
            }
        });
        onWillUnmount(() => {
            this.request++;
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

    /** The apps of the project: [{id, name, icon}]. */
    get apps() {
        return this.props.project.apps || [];
    }

    /** Whether the model goes in a new app, made with it. */
    get isNewApp() {
        return this.state.place === "new_app";
    }

    /** The technical name cannot change once Apply created the model. */
    get modelLocked() {
        return Boolean(this.line && this.line.applied);
    }

    /** Whether the name needs x_: the rule says so, or there is no rule. */
    get prefixRequired() {
        return !this.props.rule || Boolean(this.props.rule.prefix_required);
    }

    get rule() {
        return this.props.rule || null;
    }

    get nameHelp() {
        if (this.prefixRequired) {
            return _t(
                "Starts with x_, then lower case letters, digits and underscores; it cannot change once applied."
            );
        }
        return _t(
            "Lower case letters, digits, underscores and dots; x_ is optional on this development database. It cannot change once applied."
        );
    }

    /** The answer of the last check when it is about the name on screen, else null. */
    get nameCheck() {
        const check = this.state.check;
        return !this.modelLocked && check && check.name === this.state.model.trim() ? check : null;
    }

    /** Whether the server said the name on screen does not apply. */
    get nameRefused() {
        const check = this.nameCheck;
        return Boolean(check && !check.error && check.status !== "available");
    }

    /** The class of the status of the name: available, refused, or none while checking. */
    get nameStatusClass() {
        const check = this.nameCheck;
        if (this.state.checking || !check) {
            return "text-muted";
        }
        return check.status === "available"
            ? "o_erplibre_studio_name_ok text-success-emphasis bg-success-subtle"
            : "o_erplibre_studio_name_bad text-danger-emphasis bg-danger-subtle";
    }

    /**
     * Ask ``checkName`` what the name on screen gives; an answer of an
     * older request, or once the dialog is gone, is dropped. No check of
     * an empty or locked name.
     */
    async checkName() {
        const name = this.state.model.trim();
        if (!this.props.checkName || this.modelLocked || !name) {
            this.request++;
            Object.assign(this.state, {check: null, checking: false});
            return null;
        }
        const request = ++this.request;
        this.state.checking = true;
        const check = await this.props.checkName(name, this.state.name.trim());
        if (request !== this.request || status(this) === "destroyed") {
            return null;
        }
        Object.assign(this.state, {check, checking: false});
        return check;
    }

    /** Once applied, Odoo keeps the chatter of a model. */
    get chatterLocked() {
        return Boolean(this.line && this.line.applied && this.line.chatter);
    }

    get menus() {
        return filterMenus(this.choices.menus, this.state.menuFilter);
    }

    /** Whether the dialog shows the name of a new app, and it is empty. */
    get appNameMissing() {
        return this.isNewApp && !this.state.appName.trim();
    }

    get canSave() {
        const state = this.state;
        if (state.saving || !state.name.trim() || !state.model.trim() || this.nameRefused) {
            return false;
        }
        if (state.place === "menu") {
            return Boolean(state.parentId);
        }
        if (state.place === "project") {
            return Boolean(state.appId);
        }
        return !this.appNameMissing;
    }

    /** The label and the help of the place ``place`` of MENU_PLACES. */
    placeInfo(place) {
        if (place === "project") {
            return {
                label: _t("In an app of the project"),
                help: this.apps.length
                    ? _t("Added to the menu of an app this project makes.")
                    : _t("The project has no app yet."),
            };
        }
        if (place === "new_app") {
            return {
                label: _t("In a new app"),
                help: _t("One more app on the home screen, with its name and its icon."),
            };
        }
        return {
            label: _t("Under an existing menu"),
            help: _t("In the menu of an installed app, for example Contacts."),
        };
    }

    /** The id of the radio button of the place ``place``, which the tests and tours name. */
    placeId(place) {
        const ids = {project: "o_erplibre_studio_menu_app", new_app: "o_erplibre_studio_menu_new_app"};
        return ids[place] || "o_erplibre_studio_menu_under";
    }

    /**
     * The path of the menu the model gets, as the home menu shows it:
     * the app or the parent menu, then the label of the menu.
     */
    get menuPreview() {
        const state = this.state;
        const leaf = state.menuName.trim() || state.name.trim() || _t("New model");
        let root;
        if (state.place === "menu") {
            const parent = (this.choices.menus || []).find((menu) => menu.id === state.parentId);
            root = parent ? parent.name.split("/").map((part) => part.trim()).join(" › ") : _t("Choose a parent menu");
        } else if (state.place === "project") {
            const app = this.apps.find((a) => a.id === state.appId);
            root = app ? app.name : _t("Choose an app");
        } else {
            root = state.appName.trim() || _t("New app");
        }
        return `${root} › ${leaf}`;
    }

    /** The technical name and the name of a new app follow the label until edited. */
    setName(value) {
        this.state.name = value;
        if (!this.state.modelEdited) {
            const model = value.trim() ? modelNameFromLabel(value, this.props.taken || []) : "";
            if (model !== this.state.model) {
                this.state.model = model;
                this.scheduleCheck();
            }
        }
        if (!this.state.appNameEdited) {
            this.state.appName = value;
        }
    }

    setModel(value) {
        this.state.model = value;
        this.state.modelEdited = true;
        this.scheduleCheck();
    }

    /** The technical name of a new model follows the label again. */
    followLabel() {
        this.state.modelEdited = false;
        this.setName(this.state.name);
    }

    setAppName(value) {
        this.state.appName = value;
        this.state.appNameEdited = true;
    }

    setPlace(place) {
        this.state.place = place;
        if (place === "new_app" && !this.state.appNameEdited) {
            this.state.appName = this.state.name;
        }
    }

    setApp(value) {
        this.state.appId = parseInt(value) || false;
    }

    /** Whether the icon ``value`` is the one of the new app; none is the studio one. */
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
        const menu = {mode: state.place === "menu" ? "menu" : "app", name: state.menuName.trim()};
        if (state.place === "menu") {
            menu.parent_id = state.parentId;
        } else if (this.isNewApp) {
            menu.new_app = {name: state.appName.trim(), icon: state.appIcon || false};
        } else {
            menu.app_id = state.appId;
        }
        const values = {name: state.name.trim(), chatter: state.chatter, menu};
        if (!this.modelLocked) {
            values.model = state.model.trim();
        }
        return values;
    }

    async save() {
        if (!this.canSave) {
            return;
        }
        this.state.saving = true;
        if (await this.props.save(this.values)) {
            this.props.close();
            return;
        }
        this.state.saving = false;
    }
}
