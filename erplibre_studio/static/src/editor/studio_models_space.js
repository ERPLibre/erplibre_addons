/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {PERMS, accessGroup, permLabel} from "./studio_models";
import {pickModel} from "./studio_security";
import {fieldTypeLabel, typeGlyph} from "./studio_utils";

// The default views Apply makes for a model of the project, in their order.
export const MODEL_VIEW_TYPES = ["form", "list", "search"];

// The order of the records of a model whose option « Manual order » is on.
export const MANUAL_ORDER = "x_sequence asc, id asc";

/**
 * The models of the models space: [{model, name, kind, line, touched}],
 * the models the project creates first, in their order, then the other
 * models the project touches (``touched_models``). ``kind``: « pending »
 * until Apply creates a model of the project, then « created »; «
 * existing » for a model of the database. ``line``: the model line of a
 * model of the project, else null; ``touched``: its entry of
 * ``touched_models``, null when the payload has none.
 */
export function modelEntries(project) {
    const lines = (project && project.models) || [];
    const touched = (project && project.touched_models) || [];
    const byModel = Object.fromEntries(touched.map((item) => [item.model, item]));
    const entries = lines.map((line) => ({
        model: line.model,
        name: line.name,
        kind: line.applied ? "created" : "pending",
        line,
        touched: byModel[line.model] || null,
    }));
    const own = new Set(lines.map((line) => line.model));
    for (const item of touched) {
        if (!own.has(item.model)) {
            entries.push({model: item.model, name: item.name, kind: "existing", line: null, touched: item});
        }
    }
    return entries;
}

/**
 * The path of the menu of the model line ``line``, as the home menu shows
 * it: its app among ``apps`` or its parent menu, then the label of the
 * menu (the label of the model by default).
 */
export function menuPath(line, apps = []) {
    const leaf = line.menu_name || line.name;
    if (line.menu_mode === "menu") {
        const parent = line.menu_parent
            ? line.menu_parent[1]
                  .split("/")
                  .map((part) => part.trim())
                  .join(" › ")
            : _t("Under a menu");
        return `${parent} › ${leaf}`;
    }
    const app = apps.find((a) => a.id === line.app_id);
    // Outside the template literal, where the .pot extractor sees it.
    const appName = app ? app.name : _t("No app");
    return `${appName} › ${leaf}`;
}

/** The rights of the access row ``row``, as a reader says them. */
export function permsText(row) {
    const perms = PERMS.filter((perm) => row[perm]).map(permLabel);
    return perms.length ? perms.join(" · ") : _t("No right");
}

/**
 * The models space of the editor: on the left the models of the project
 * and those it touches, in the centre the page of the chosen one (its
 * identity, its menu, its chatter, its views, its new fields, a summary
 * of its access), on the right its inspector.
 *
 * Every change goes through the editor (``updateModel``, ``removeModel``,
 * ``openModel``…). The choice of the model lives in the editor state
 * (``modelsSpace``), which this component reads through its own
 * ``useState``: it renders again when the editor changes it.
 */
export class StudioModelsSpace extends Component {
    static template = "erplibre_studio.ModelsSpace";
    static props = {
        editor: Object,
        project: Object,
        // The model of the view on screen: the page it opens on.
        screenModel: {type: [String, {value: false}], optional: true},
        // Whether a model can get a chatter: mail is installed.
        mailAvailable: {type: Boolean, optional: true},
        busy: {type: Boolean, optional: true},
    };

    setup() {
        this.es = useState(this.props.editor.state);
        this.viewTypes = MODEL_VIEW_TYPES;
    }

    get editor() {
        return this.props.editor;
    }

    get project() {
        return this.props.project;
    }

    get space() {
        return this.es.modelsSpace;
    }

    get entries() {
        return modelEntries(this.project);
    }

    /** The model the page shows: the chosen one, else the model on screen, else the first one. */
    get current() {
        const entries = this.entries;
        const model = pickModel(entries, this.space.model, this.props.screenModel);
        return entries.find((entry) => entry.model === model) || null;
    }

    get hasNewModel() {
        return Boolean((this.project.models || []).length);
    }

    select(entry) {
        this.editor.selectModelEntry(entry.model);
    }

    // ── what an entry shows ─────────────────────────────────────────────

    badge(entry) {
        return {pending: _t("Pending"), created: _t("Created"), existing: _t("Changed")}[entry.kind];
    }

    status(entry) {
        if (entry.kind === "pending") {
            return _t("Waiting for Apply");
        }
        if (entry.kind === "created") {
            return _t("Created by Apply");
        }
        const module = entry.touched && entry.touched.module;
        return module ? _t("Model of the module %(module)s", {module}) : _t("Model of the database");
    }

    kindText(entry) {
        if (entry.kind === "existing") {
            return _t("Existing model · %(model)s", {model: entry.model});
        }
        return entry.kind === "pending"
            ? _t("Model of the project · waiting for Apply")
            : _t("Model of the project · created by Apply");
    }

    /** The technical name without « x_ », which the page shows apart, for a model of the project. */
    techRest(entry) {
        return entry.line && entry.model.startsWith("x_") ? entry.model.slice(2) : entry.model;
    }

    hasPrefix(entry) {
        return Boolean(entry.line) && entry.model.startsWith("x_");
    }

    nameNote(entry) {
        if (entry.kind === "pending") {
            return _t("Editable until Apply. Odoo requires the x_ prefix for the models created outside the code.");
        }
        if (entry.kind === "created") {
            return _t(
                "Locked: the table exists since Apply. Another name would make another model, without its records."
            );
        }
        return _t("A model of a module: its name does not change.");
    }

    menuPath(entry) {
        return menuPath(entry.line, this.project.apps || []);
    }

    // ── chatter ─────────────────────────────────────────────────────────

    chatterOn(entry) {
        return entry.line ? Boolean(entry.line.chatter) : Boolean(entry.touched && entry.touched.chatter);
    }

    /** Whether the switch of the chatter is read-only: a model of the database, no mail, or applied with it. */
    chatterLocked(entry) {
        if (!entry.line || !this.props.mailAvailable) {
            return true;
        }
        return Boolean(entry.line.applied && entry.line.chatter);
    }

    chatterNote(entry) {
        if (!entry.line) {
            return this.chatterOn(entry)
                ? _t("Already on this model, from its modules.")
                : _t("Not on this model; the studio adds it only to the models of the project.");
        }
        if (!this.props.mailAvailable) {
            return _t("Needs the Discuss module (mail), not installed.");
        }
        if (this.chatterLocked(entry)) {
            return _t("Once applied, the chatter cannot be removed.");
        }
        return _t("Messages, activities and followers under the record.");
    }

    async toggleChatter(entry, ev) {
        const checked = ev.target.checked;
        if (!(await this.editor.updateModel(entry.line, {chatter: checked}))) {
            ev.target.checked = !checked;
        }
    }

    // ── identity ────────────────────────────────────────────────────────

    /** Rename the model of the project; the field shows its name again when the server refuses. */
    async rename(entry, ev) {
        const name = ev.target.value.trim();
        if (!name || name === entry.line.name) {
            ev.target.value = entry.line.name;
            return;
        }
        if (!(await this.editor.updateModel(entry.line, {name}))) {
            ev.target.value = entry.line.name;
        }
    }

    /** Change the technical name of a model not created yet, « x_ » before what is typed. */
    async renameModel(entry, ev) {
        const rest = ev.target.value.trim().replace(/^x_/, "");
        const model = this.hasPrefix(entry) ? `x_${rest}` : rest;
        if (!rest || model === entry.model) {
            ev.target.value = this.techRest(entry);
            return;
        }
        if (!(await this.editor.updateModel(entry.line, {model}))) {
            ev.target.value = this.techRest(entry);
        }
    }

    // ── views ───────────────────────────────────────────────────────────

    /**
     * The views of the page: [{type, label, pending, changes, disabled,
     * open}]. A model of the project has its default views, before Apply
     * too; a model of the database the default views the studio edits.
     */
    views(entry) {
        const label = (type) => this.editor.viewTypeLabel(type);
        if (entry.line) {
            const line = entry.line;
            return this.viewTypes.map((type) => ({
                type,
                label: label(type),
                pending: !line.applied,
                changes: Boolean(!line.applied && line.pending_views && line.pending_views[type]),
                disabled: Boolean(line.applied && !(line.views || {})[type]),
                open: () => this.editor.openModel(line, type),
            }));
        }
        return ((entry.touched && entry.touched.views) || []).map((view) => ({
            type: view.type,
            label: view.label || label(view.type),
            // A view the project adds, before Apply creates it.
            pending: Boolean(view.added && !view.view_id),
            changes: false,
            disabled: false,
            open: () => this.editor.openView(entry.model, view.view_id, view.type),
        }));
    }

    /** Open the form of the model, where the palette adds its fields. */
    addField(entry) {
        const view = this.views(entry).find((item) => item.type === "form" && !item.disabled);
        if (view) {
            view.open();
        }
    }

    canAddField(entry) {
        return this.views(entry).some((item) => item.type === "form" && !item.disabled);
    }

    // ── fields ──────────────────────────────────────────────────────────

    /**
     * The fields of the page: [{name, label, type, glyph, applied}]. A
     * model of the project starts with its name field ``x_name``; then
     * come the new fields of the project on the model.
     */
    fields(entry) {
        const fields = (entry.touched && entry.touched.fields) || [];
        const rows = [];
        if (entry.line && !fields.some((field) => field.name === "x_name")) {
            rows.push({name: "x_name", label: _t("Name"), ttype: "char", relation: false, applied: entry.line.applied});
        }
        rows.push(...fields);
        return rows.map((field) => ({
            ...field,
            glyph: typeGlyph(field.ttype),
            type: field.relation
                ? `${fieldTypeLabel(field.ttype)} → ${this.modelName(field.relation)}`
                : fieldTypeLabel(field.ttype),
        }));
    }

    /** The label of ``model``: a model of the list, else as the editor names it. */
    modelName(model) {
        const entry = this.entries.find((item) => item.model === model);
        return entry ? entry.name : this.editor.modelLabel(model);
    }

    fieldsNote(entry) {
        return entry.line
            ? _t("Plus the automatic fields: Created on, Created by, Last updated on.")
            : _t("Only the fields the project adds are listed.");
    }

    // ── access ──────────────────────────────────────────────────────────

    /** The access rows of the project on the model: [{id, group, perms}]. */
    access(entry) {
        return (this.project.access || [])
            .filter((row) => row.model === entry.model)
            .map((row) => ({id: row.id, group: accessGroup(row)[1], perms: permsText(row)}));
    }

    rules(entry) {
        return (this.project.rules || []).filter((rule) => rule.model === entry.model);
    }

    rulesText(entry) {
        const rules = this.rules(entry);
        if (!rules.length) {
            return _t("No rule: the rights hold for every record.");
        }
        return _t("%(count)s rule(s): %(names)s", {
            count: rules.length,
            names: rules.map((rule) => `« ${rule.name} »`).join(", "),
        });
    }

    openSecurity(entry) {
        this.editor.openSecurityModel(entry.model);
    }

    // ── inspector ───────────────────────────────────────────────────────

    /** What the draft holds on the model: [{key, label, count}]. */
    draftCounts(entry) {
        const touched = entry.touched || {};
        const count = (key, fallback) => (touched[key] !== undefined ? touched[key] : fallback);
        return [
            {key: "fields", label: _t("New fields"), count: (touched.fields || []).length},
            {key: "changes", label: _t("Changes of views"), count: count("changes", 0)},
            {key: "access", label: _t("Access rights"), count: count("access", this.access(entry).length)},
            {key: "rules", label: _t("Record rules"), count: count("rules", this.rules(entry).length)},
        ];
    }

    /**
     * The choices of the default order of the model line of ``entry``:
     * [{value, label}]. The order of creation (empty), the manual order
     * while its option is on, then each sortable field ascending and
     * descending; an order set otherwise stays shown as it is.
     */
    orderChoices(entry) {
        const line = entry.line;
        const choices = [{value: "", label: _t("Creation order")}];
        if (line.manual_order) {
            choices.push({value: MANUAL_ORDER, label: _t("Manual order (Sequence)")});
        }
        for (const [name, field] of line.sort_fields || []) {
            choices.push({value: `${name} asc`, label: _t("%(field)s, ascending", {field})});
            choices.push({value: `${name} desc`, label: _t("%(field)s, descending", {field})});
        }
        if (line.order && !choices.some((choice) => choice.value === line.order)) {
            choices.push({value: line.order, label: line.order});
        }
        return choices;
    }

    async changeOrder(entry, ev) {
        const order = ev.target.value;
        if (order === (entry.line.order || "")) {
            return;
        }
        if (!(await this.editor.updateModel(entry.line, {order}))) {
            ev.target.value = entry.line.order || "";
        }
    }

    /** The options of a model of the project, one field each: [{key, label, field}]. */
    get modelOptions() {
        return [
            {key: "archivable", label: _t("Archivable"), field: "x_active"},
            {key: "manual_order", label: _t("Manual order"), field: "x_sequence"},
            {key: "per_company", label: _t("Per company"), field: "x_company_id"},
        ];
    }

    /**
     * The rule line of « Per company » of the model line of ``entry``, as
     * the security payload holds it, or null once removed from the project.
     */
    companyRule(entry) {
        const ref = entry.line.company_rule;
        return (ref && this.rules(entry).find((rule) => rule.id === ref[0])) || null;
    }

    companyRuleText(entry) {
        const rule = this.companyRule(entry);
        if (!rule) {
            return _t("No rule: records are shared between companies.");
        }
        return _t("Rule « %(name)s »: a user sees the records of their companies and those of no company.", {
            name: rule.name,
        });
    }

    /** Show the rule of « Per company » of ``entry`` in the rules tab of the security space. */
    async openCompanyRule(entry) {
        const rule = this.companyRule(entry);
        this.editor.state.security.model = entry.model;
        await this.editor.openSecurity("rules");
        if (rule && this.editor.state.space === "security") {
            this.editor.editRule(rule);
        }
    }

    /** Whether the option ``key`` of the model line of ``entry`` is applied: its field exists, it stays. */
    optionLocked(entry, key) {
        return Boolean(entry.line.options_applied && entry.line.options_applied[key]);
    }

    get lockedTitle() {
        return _t("Once applied, this option cannot be removed.");
    }

    async toggleOption(entry, key, ev) {
        const checked = ev.target.checked;
        if (!(await this.editor.updateModel(entry.line, {[key]: checked}))) {
            ev.target.checked = !checked;
        }
    }

    /** The table of the model in the database. */
    table(entry) {
        return entry.model.replace(/\./g, "_");
    }

    toggleAdvanced() {
        this.space.advanced = !this.space.advanced;
    }

    removeText(entry) {
        return entry.kind === "pending" ? _t("Remove from the draft") : _t("Delete the model and its records");
    }

    remove(entry) {
        this.editor.removeModel(entry.line);
    }
}
