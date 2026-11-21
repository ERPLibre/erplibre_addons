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
 * The groups of ``app`` as a chain of levels: [{group, level, linked}],
 * by level then in their order. A group is one level above the highest
 * group of the app it implies; ``linked`` says whether it implies the
 * group listed before it.
 */
export function chainLevels(project, app) {
    const groups = appGroups(project, app);
    const ids = groups.map((group) => group.id);
    const levels = {};
    const levelOf = (group, seen = []) => {
        if (levels[group.id]) {
            return levels[group.id];
        }
        if (seen.includes(group.id)) {
            return 1;
        }
        const below = group.implied
            .map((implied) => groups.find((g) => g.id === implied[0]))
            .filter(Boolean)
            .map((g) => levelOf(g, [...seen, group.id]));
        levels[group.id] = 1 + Math.max(0, ...below);
        return levels[group.id];
    };
    const sorted = [...groups].sort((a, b) => levelOf(a) - levelOf(b) || ids.indexOf(a.id) - ids.indexOf(b.id));
    return sorted.map((group, index) => ({
        group,
        level: levelOf(group),
        linked: index > 0 && group.implied.some((implied) => implied[0] === sorted[index - 1].id),
    }));
}

/**
 * The ids of the groups of the project that the groups ``lineIds`` imply,
 * through the implications of the groups of ``project`` ({via: id}): the
 * group each one is received through.
 */
export function inheritedLines(project, lineIds) {
    const groups = (project && project.groups) || [];
    const via = {};
    const visit = (id, origin) => {
        const group = groups.find((g) => g.id === id);
        for (const [implied] of (group && group.implied) || []) {
            if (!(implied in via)) {
                via[implied] = origin;
                visit(implied, origin);
            }
        }
    };
    lineIds.forEach((id) => visit(id, id));
    return via;
}

/**
 * The existing apps the project names: [{id, name, groups}] for each
 * category of the existing groups its groups imply, its access rows and
 * its rules name; ``groups`` the names of the groups of the category
 * among ``choices``.
 */
export function existingApps(project, choices) {
    const groups = ((choices && choices.groups) || []).filter((group) => !group.project);
    const named = new Set();
    for (const group of (project && project.groups) || []) {
        group.implied_groups.forEach((implied) => named.add(implied[0]));
    }
    for (const row of (project && project.access) || []) {
        if (row.group) {
            named.add(row.group[0]);
        }
    }
    for (const rule of (project && project.rules) || []) {
        rule.groups.forEach((group) => named.add(group[0]));
    }
    const apps = [];
    for (const group of groups) {
        if (!named.has(group.id) || !group.category || apps.some((app) => app.id === group.category[0])) {
            continue;
        }
        const [id, name] = group.category;
        apps.push({
            id,
            name,
            groups: groups.filter((g) => g.category && g.category[0] === id).map((g) => g.name),
        });
    }
    return apps.sort((a, b) => a.name.localeCompare(b.name));
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
 * The tab Groups of the security space: the apps of the project as cards,
 * their groups as a chain of levels, the existing apps the project names;
 * on its right, the inspector holds the form of an app or of a group.
 * Each app has a top-level menu and the category of its groups; each
 * group implies other groups of the project or existing ones. Every Save
 * is one call of the editor (``projectCall``), one change of the draft.
 * The slot « head » renders above the cards: the tabs of the space.
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
        // The members of the groups of the project Apply made, by group:
        // {count, users: [{id, name, direct}], more} (get_group_members).
        members: {type: Object, optional: true},
        // What the next Apply takes from members (get_group_losses).
        losses: {type: Array, optional: true},
        slots: {type: Object, optional: true},
    };

    setup() {
        // ``open``: the cards unfolded or folded by hand, by « app:<id> »
        // or « category:<id> »; the apps of the project start unfolded,
        // the existing apps folded.
        this.state = useState({appForm: null, groupForm: null, open: {}});
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

    levels(app) {
        return chainLevels(this.project, app);
    }

    levelText(app, entry) {
        return app.chain ? _t("Level %(level)s", {level: entry.level}) : _t("Group");
    }

    get existingApps() {
        return existingApps(this.project, this.props.choices);
    }

    isOpen(key, byDefault = true) {
        return key in this.state.open ? this.state.open[key] : byDefault;
    }

    toggleCard(key, byDefault = true) {
        this.state.open[key] = !this.isOpen(key, byDefault);
    }

    toggleLabel(name) {
        return _t("Show or hide the groups of %(app)s", {app: name});
    }

    groupCountText(app) {
        return _t("%(groups)s group(s) · %(models)s model(s)", {
            groups: this.appGroups(app).length,
            models: app.models.length,
        });
    }

    addLevelLabel(app) {
        return _t("Add a level to %(app)s", {app: app.name});
    }

    /** The members of the group of the project ``group``: the payload of get_group_members, or null. */
    membersOf(group) {
        return (group.applied && (this.props.members || {})[group.id]) || null;
    }

    membersLabel(group) {
        const members = this.membersOf(group);
        if (!group.applied) {
            return _t("created by Apply");
        }
        return members ? _t("%(count)s member(s)", {count: members.count}) : "";
    }

    isGroupSelected(group) {
        return Boolean(this.state.groupForm && this.state.groupForm.id === group.id);
    }

    editLabel(name) {
        return _t("Edit %(name)s", {name});
    }

    removeLabel(name) {
        return _t("Remove %(name)s", {name});
    }

    /** What the next Apply takes from the members of the groups of ``app``. */
    lossesOf(app) {
        const ids = this.appGroups(app).map((group) => group.id);
        return (this.props.losses || []).filter((loss) => ids.includes(loss.line_id));
    }

    lossTitle(loss) {
        return _t("Apply will remove %(count)s member(s) from %(group)s.", {count: loss.count, group: loss.group[1]});
    }

    lossText(loss) {
        const names = loss.users.map((user) => user.name).join(", ") + (loss.more ? ", …" : "");
        return _t("%(names)s hold it only through %(via)s: they lose its rights.", {names, via: loss.via[1]});
    }

    /** Make the group ``via_line_id`` of ``loss`` imply its group again: one change of the draft. */
    async restoreImplication(loss) {
        const via = (this.project.groups || []).find((group) => group.id === loss.via_line_id);
        if (!via || !loss.line_id) {
            return;
        }
        this.closeForms();
        await this.send("save_group", [
            {
                id: via.id,
                name: via.name,
                app_id: via.app_id,
                comment: via.comment || "",
                implied_line_ids: [...via.implied.map((g) => g[0]), loss.line_id],
                implied_group_ids: via.implied_groups.map((g) => g[0]),
            },
        ]);
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

    /** « App / Group » of the group of the project ``group``. */
    lineLabel(group) {
        const app = this.apps.find((a) => a.id === group.app_id);
        return app ? `${app.name} / ${group.name}` : group.name;
    }

    appName(appId) {
        const app = this.apps.find((a) => a.id === appId);
        return app ? app.name : "";
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

    /**
     * The groups of the project the group of the form may imply: not
     * itself, nor a group that implies it already (directly or not).
     */
    get impliableLines() {
        const form = this.state.groupForm;
        const groups = this.project.groups || [];
        return groups.filter(
            (group) => group.id !== form.id && !(form.id && form.id in inheritedLines(this.project, [group.id]))
        );
    }

    /** {id: via} of the groups of the project the form implies through another group it implies. */
    get inheritedLines() {
        const form = this.state.groupForm;
        return inheritedLines(this.project, form.implied_line_ids);
    }

    isImpliedLine(id) {
        return this.state.groupForm.implied_line_ids.includes(id) || id in this.inheritedLines;
    }

    isInheritedLine(id) {
        return !this.state.groupForm.implied_line_ids.includes(id) && id in this.inheritedLines;
    }

    impliedNote(group) {
        if (this.isInheritedLine(group.id)) {
            return _t("Received through %(group)s", {group: this.groupLabel(this.inheritedLines[group.id])});
        }
        return _t("Group of this project");
    }

    setImpliedLine(id, checked) {
        const form = this.state.groupForm;
        form.implied_line_ids = form.implied_line_ids.filter((i) => i !== id);
        if (checked) {
            form.implied_line_ids.push(id);
        }
    }

    get groupFormTitle() {
        const form = this.state.groupForm;
        return form.id ? form.name || _t("Group") : _t("New group");
    }

    get groupFormKind() {
        const form = this.state.groupForm;
        const group = form.id && (this.project.groups || []).find((g) => g.id === form.id);
        if (!group) {
            return _t("New group of %(app)s", {app: this.appName(form.app_id)});
        }
        return group.applied
            ? _t("Group of the project · in the database")
            : _t("Group of the project · created by Apply");
    }

    /** The group of the project the form edits, or null for a new one. */
    get groupOfForm() {
        const form = this.state.groupForm;
        return (form.id && (this.project.groups || []).find((g) => g.id === form.id)) || null;
    }

    memberTag(user) {
        return user.direct ? _t("direct") : _t("through an implication");
    }

    get impliableGroups() {
        const form = this.state.groupForm;
        return this.existingGroups.filter((group) => !form.implied_group_ids.includes(group.id));
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
