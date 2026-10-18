/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {DEFAULT_APP_ICON} from "./studio_models";

// The groups a project group never implies (ADMIN_GROUPS of the server):
// they grant the Settings.
export const ADMIN_GROUPS = ["base.group_system", "base.group_erp_manager"];
// The group a new group of the project implies by default.
export const DEFAULT_IMPLIED_GROUP = "base.group_user";
// The prefix of the value of a group of the project in a group select.
export const LINE_PREFIX = "line:";

/** The groups of the project ``project`` in its app ``app``. */
export function appGroups(project, app) {
    return ((project && project.groups) || []).filter((group) => group.app_id === app.id);
}

/**
 * Whether the groups of ``app`` show as checkboxes in developer mode only
 * in the user form: Odoo makes a selection of a category only when its
 * groups imply each other in a chain (``chain`` of the server).
 */
export function chainWarning(project, app) {
    return !app.chain && appGroups(project, app).length > 1;
}

/**
 * The value of a group in a group select: the id of an existing group, or
 * « line:<id> » for a group of the project; ``parseGroupValue`` reads it
 * back as {group_id} or {group_line_id}.
 */
export function groupValue(group) {
    return group.project ? `${LINE_PREFIX}${group.line_id}` : String(group.id);
}

export function parseGroupValue(value) {
    const text = String(value || "");
    if (text.startsWith(LINE_PREFIX)) {
        const id = parseInt(text.slice(LINE_PREFIX.length));
        return id ? {group_line_id: id} : null;
    }
    const id = parseInt(text);
    return id ? {group_id: id} : null;
}

/**
 * The panel of the apps of the project and of their groups: each app has
 * a top-level menu and the category of its groups; each group implies
 * other groups of the project or existing ones. Every Save is one call of
 * the editor (``projectCall``), one change of the draft.
 */
export class StudioAppsPanel extends Component {
    static template = "erplibre_studio.AppsPanel";
    static props = {
        editor: Object,
        project: Object,
        choices: {type: [Object, {value: null}], optional: true},
        busy: {type: Boolean, optional: true},
        // The refusal of the last call, held by the editor: a refusal
        // leaves the project as it was, and only the editor renders again.
        error: {type: [String, {value: null}], optional: true},
    };

    setup() {
        this.state = useState({appForm: null, groupForm: null});
    }

    get project() {
        return this.props.project;
    }

    get apps() {
        return this.project.apps || [];
    }

    get icons() {
        return (this.props.choices && this.props.choices.icons) || [];
    }

    /** The existing groups a project group may imply. */
    get existingGroups() {
        return ((this.props.choices && this.props.choices.groups) || []).filter(
            (group) => !group.project && !ADMIN_GROUPS.includes(group.xml_id)
        );
    }

    appGroups(app) {
        return appGroups(this.project, app);
    }

    chainWarning(app) {
        return chainWarning(this.project, app);
    }

    iconOf(app) {
        const value = app.icon || DEFAULT_APP_ICON;
        return this.icons.find((icon) => icon.value === value) || null;
    }

    groupLabel(groupId) {
        const group = (this.project.groups || []).find((g) => g.id === groupId);
        return group ? group.name : String(groupId);
    }

    existingGroupLabel(groupId) {
        const group = this.existingGroups.find((g) => g.id === groupId);
        return group ? group.name : String(groupId);
    }

    removeChipLabel(name) {
        return _t("Remove %(group)s", {group: name});
    }

    missingText(xmlid) {
        return _t("This group no longer exists: %(group)s", {group: xmlid});
    }

    // ── apps ────────────────────────────────────────────────────────────

    newApp() {
        this.state.groupForm = null;
        this.props.editor.state.panelError = null;
        this.state.appForm = {id: false, name: "", icon: false, menu_sequence: 50};
    }

    editApp(app) {
        this.state.groupForm = null;
        this.props.editor.state.panelError = null;
        this.state.appForm = {id: app.id, name: app.name, icon: app.icon || false, menu_sequence: app.menu_sequence};
    }

    isIcon(value) {
        return value === (this.state.appForm.icon || DEFAULT_APP_ICON);
    }

    setIcon(value) {
        this.state.appForm.icon = value === DEFAULT_APP_ICON ? false : value;
    }

    closeForms() {
        Object.assign(this.state, {appForm: null, groupForm: null});
        this.props.editor.state.panelError = null;
    }

    /** Run ``method`` of the editor; a refusal shows at the top of the panel. */
    async send(method, params) {
        const editor = this.props.editor;
        editor.state.panelError = null;
        return editor.projectCall(method, params, (message) => {
            editor.state.panelError = message;
        });
    }

    async saveApp() {
        const form = this.state.appForm;
        if (!form || !form.name.trim()) {
            return;
        }
        const values = {
            name: form.name.trim(),
            icon: form.icon || false,
            menu_sequence: parseInt(form.menu_sequence) || 0,
        };
        if (form.id) {
            values.id = form.id;
        }
        if (await this.send("save_app", [values])) {
            this.closeForms();
        }
    }

    async removeApp(app) {
        this.closeForms();
        await this.send("remove_app", [app.id]);
    }

    // ── groups ──────────────────────────────────────────────────────────

    newGroup(app) {
        const implied = this.existingGroups.find((g) => g.xml_id === DEFAULT_IMPLIED_GROUP);
        this.state.appForm = null;
        this.props.editor.state.panelError = null;
        this.state.groupForm = {
            id: false,
            app_id: app.id,
            name: "",
            comment: "",
            implied_line_ids: [],
            implied_group_ids: implied ? [implied.id] : [],
        };
    }

    editGroup(group) {
        this.state.appForm = null;
        this.props.editor.state.panelError = null;
        this.state.groupForm = {
            id: group.id,
            app_id: group.app_id,
            name: group.name,
            comment: group.comment || "",
            implied_line_ids: group.implied.map((g) => g[0]),
            implied_group_ids: group.implied_groups.map((g) => g[0]),
        };
    }

    /** The groups of the project the group of the form may imply: not itself. */
    get impliableLines() {
        const form = this.state.groupForm;
        return (this.project.groups || []).filter(
            (group) => group.id !== form.id && !form.implied_line_ids.includes(group.id)
        );
    }

    get impliableGroups() {
        const form = this.state.groupForm;
        return this.existingGroups.filter((group) => !form.implied_group_ids.includes(group.id));
    }

    addImpliedLine(ev) {
        const id = parseInt(ev.target.value) || false;
        ev.target.value = "";
        if (id && !this.state.groupForm.implied_line_ids.includes(id)) {
            this.state.groupForm.implied_line_ids.push(id);
        }
    }

    removeImpliedLine(id) {
        const form = this.state.groupForm;
        form.implied_line_ids = form.implied_line_ids.filter((i) => i !== id);
    }

    addImpliedGroup(ev) {
        const id = parseInt(ev.target.value) || false;
        ev.target.value = "";
        if (id && !this.state.groupForm.implied_group_ids.includes(id)) {
            this.state.groupForm.implied_group_ids.push(id);
        }
    }

    removeImpliedGroup(id) {
        const form = this.state.groupForm;
        form.implied_group_ids = form.implied_group_ids.filter((i) => i !== id);
    }

    async saveGroup() {
        const form = this.state.groupForm;
        if (!form || !form.name.trim()) {
            return;
        }
        const values = {
            name: form.name.trim(),
            app_id: form.app_id,
            comment: form.comment.trim(),
            implied_line_ids: [...form.implied_line_ids],
            implied_group_ids: [...form.implied_group_ids],
        };
        if (form.id) {
            values.id = form.id;
        }
        if (await this.send("save_group", [values])) {
            this.closeForms();
        }
    }

    async removeGroup(group) {
        this.closeForms();
        await this.send("remove_group", [group.id]);
    }
}
