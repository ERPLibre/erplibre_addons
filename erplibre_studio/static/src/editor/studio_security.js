/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useEffect, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {Expression, formatValue, treeFromDomain} from "@web/core/tree_editor/condition_tree";
import {getOperatorLabel} from "@web/core/tree_editor/tree_editor_operator_editor";
import {useService} from "@web/core/utils/hooks";
import {StudioAppsPanel, groupValue} from "./studio_groups";
import {PERMS, accessGroup, permLabel} from "./studio_models";
import {MODEL} from "./studio_utils";

/**
 * The fields every model has, whatever the project defines on it, labelled
 * in the language of the user: the conditions of a rule on a model not
 * created yet name them too.
 */
function magicFields() {
    return {
        id: {string: _t("ID"), type: "integer"},
        display_name: {string: _t("Display Name"), type: "char"},
        create_uid: {string: _t("Created by"), type: "many2one"},
        create_date: {string: _t("Created on"), type: "datetime"},
        write_uid: {string: _t("Last Updated by"), type: "many2one"},
        write_date: {string: _t("Last Updated on"), type: "datetime"},
    };
}

/**
 * The models of the security space: [{model, name, isNew, pending,
 * access, rules}], the models the project creates first, then those its
 * access rows and its rules name, then the other models its changes touch
 * (``touched_models``). ``access`` and ``rules`` count the rows and the
 * rules of the project on the model; ``labelOf(model)`` names a model the
 * payload does not name.
 */
export function securityModels(project, labelOf = (model) => model) {
    const lines = Object.fromEntries(((project && project.models) || []).map((line) => [line.model, line]));
    const touched = Object.fromEntries(((project && project.touched_models) || []).map((item) => [item.model, item]));
    const access = (project && project.access) || [];
    const rules = (project && project.rules) || [];
    const order = [];
    const add = (model) => {
        if (model && !order.includes(model)) {
            order.push(model);
        }
    };
    Object.keys(lines).forEach(add);
    access.forEach((row) => add(row.model));
    rules.forEach((rule) => add(rule.model));
    Object.keys(touched).forEach(add);
    return order.map((model) => {
        const line = lines[model];
        return {
            model,
            name: line ? line.name : (touched[model] && touched[model].name) || labelOf(model),
            isNew: Boolean(line),
            pending: Boolean(line && !line.applied),
            access: access.filter((row) => row.model === model).length,
            rules: rules.filter((rule) => rule.model === model).length,
        };
    });
}

/**
 * The model the security space shows, among ``models`` (securityModels):
 * ``chosen`` when listed, else the model on screen ``screen``, else the
 * first one; null without a model.
 */
export function pickModel(models, chosen, screen) {
    const names = models.map((entry) => entry.model);
    for (const model of [chosen, screen]) {
        if (model && names.includes(model)) {
            return model;
        }
    }
    return names[0] || null;
}

/** Whether the draft changes the right ``perm`` of the access row ``row`` since the last Apply. */
export function accessChanged(row, perm) {
    return Boolean(row.applied) && Boolean(row.applied[perm]) !== Boolean(row[perm]);
}

/**
 * The value of an expression of a domain as a reader says it: the values
 * a record rule evaluates (the user, the companies), else its text.
 */
function expressionText(text) {
    const known = {
        "user.id": _t("Current user"),
        uid: _t("Current user"),
        "user.partner_id.id": _t("Partner of the current user"),
        company_ids: _t("Allowed companies"),
        company_id: _t("Current company"),
        "user.company_id.id": _t("Current company"),
    };
    return known[text] || text;
}

function valueText(operator, value, fieldDef) {
    if (["set", "not_set"].includes(operator)) {
        return "";
    }
    if (value instanceof Expression) {
        return expressionText(value.toString());
    }
    if (Array.isArray(value)) {
        return value.map((item) => valueText("=", item, fieldDef)).join(", ");
    }
    if (value === true) {
        return _t("Yes");
    }
    if (value === false) {
        return ["is", "is_not"].includes(operator) ? _t("No") : _t("Empty");
    }
    if (fieldDef && fieldDef.type === "selection") {
        const option = (fieldDef.selection || []).find((item) => item[0] === value);
        if (option) {
            return option[1];
        }
    }
    return String(value);
}

function operatorText(operator, fieldDef, negate) {
    const labels = {
        "=": _t("is"),
        "!=": _t("is not"),
        is: _t("is"),
        is_not: _t("is not"),
        in: _t("is one of"),
        "not in": _t("is none of"),
    };
    if (!negate && typeof operator === "string" && labels[operator]) {
        return labels[operator];
    }
    return String(getOperatorLabel(operator, fieldDef && fieldDef.type, negate));
}

/**
 * The conditions of the domain ``domain`` as a reader says them, or null
 * when it does not read as a list of conditions joined by one connector:
 * {connector: "&" | "|", conditions: [{path, field, operator, value,
 * bad}]}. ``fields`` ({name: {string, type, selection}}) names the
 * fields of the model; with ``complete``, a condition on a field it does
 * not hold is ``bad``.
 */
export function ruleConditions(domain, fields = null, complete = false) {
    const fieldDef = (path) => (fields && typeof path === "string" && fields[path.split(".")[0]]) || null;
    let tree;
    try {
        tree = treeFromDomain(domain || "[]", {getFieldDef: fieldDef});
    } catch {
        return null;
    }
    let connector = "&";
    let items;
    if (tree.type === "condition") {
        items = [tree];
    } else if (tree.type === "connector" && !tree.negate && tree.children.every((c) => c.type === "condition")) {
        connector = tree.value;
        items = tree.children;
    } else {
        return null;
    }
    return {
        connector,
        conditions: items.map((item) => {
            const path = typeof item.path === "string" ? item.path : formatValue(item.path);
            const def = fieldDef(item.path);
            const tail = path.split(".").slice(1).join(".");
            return {
                path,
                field: def ? (tail ? `${def.string} › ${tail}` : def.string) : path,
                operator: operatorText(item.operator, def, item.negate),
                value: valueText(item.operator, item.value, def),
                bad: Boolean(complete && fields && typeof item.path === "string" && !def),
            };
        }),
    };
}

/**
 * The field of ``fields`` a domain most likely means by the unknown name
 * ``name``: « name_id » or « name_ids », else the closest name that starts
 * with it or that it starts with; null without one.
 */
export function suggestField(name, fields) {
    if (!fields || !name || name.length < 3) {
        return null;
    }
    const names = Object.keys(fields);
    const exact = [`${name}_id`, `${name}_ids`].find((candidate) => names.includes(candidate));
    if (exact) {
        return exact;
    }
    const near = names
        .filter((candidate) => candidate.length >= 3 && (candidate.startsWith(name) || name.startsWith(candidate)))
        .sort((a, b) => Math.abs(a.length - name.length) - Math.abs(b.length - name.length));
    return near[0] || null;
}

/**
 * ``domain`` with the field ``from`` of its conditions renamed ``to``: the
 * first string of each condition, quoted as the domain quotes it.
 */
export function replaceDomainField(domain, from, to) {
    const escaped = from.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = new RegExp(`([(\\[]\\s*)(['"])${escaped}\\2(?=\\s*,)`, "g");
    return domain.replace(pattern, `$1$2${to}$2`);
}

/**
 * The security space of the editor: on the left the models of the project,
 * in the centre the tabs Rights, Rules and Groups, on the right the
 * inspector of what the centre selects. The rows of the access grid and
 * the rules belong to a model; the apps and the groups hold for the whole
 * project (StudioAppsPanel).
 *
 * Every change goes through the editor (``projectCall``): one call, one
 * change of the draft. The state of the forms lives in the editor state,
 * which this component reads through its own ``useState``: it renders
 * again when the editor changes the keys it shows.
 */
export class StudioSecuritySpace extends Component {
    static template = "erplibre_studio.SecuritySpace";
    static components = {StudioAppsPanel};
    static props = {
        editor: Object,
        project: Object,
        choices: {type: [Object, {value: null}], optional: true},
        // The tab shown: a tab of SECURITY_TABS.
        tab: String,
        busy: {type: Boolean, optional: true},
    };

    setup() {
        this.orm = useService("orm");
        this.fieldService = useService("field");
        this.perms = PERMS;
        this.es = useState(this.props.editor.state);
        // ``checks``: the answer of « Check » by rule id, with the domain
        // it checked; ``fields``: {model: {fields, complete}} of the rules;
        // ``members``: the members of a group, by « group:<id> » or
        // « line:<id> »; ``lineMembers`` and ``losses``: the members of the
        // groups of the project and what the next Apply takes from them,
        // read again at each revision of the draft.
        this.state = useState({
            checks: {},
            fields: {},
            members: {},
            lineMembers: {},
            losses: [],
            groupKey: null,
        });
        useEffect(
            () => {
                this.loadRuleFields(this.currentModel);
            },
            () => [this.props.tab, this.currentModel]
        );
        useEffect(
            () => {
                this.loadGroupData();
            },
            () => [this.props.tab, this.props.project.revision, this.props.project.state]
        );
    }

    get editor() {
        return this.props.editor;
    }

    get project() {
        return this.props.project;
    }

    get tab() {
        return this.props.tab;
    }

    // ── models ──────────────────────────────────────────────────────────

    get models() {
        return securityModels(this.project, (model) => this.modelLabel(model));
    }

    get currentModel() {
        return pickModel(this.models, this.es.security.model, this.editor.params.resModel);
    }

    get currentEntry() {
        return this.models.find((entry) => entry.model === this.currentModel) || null;
    }

    get currentLabel() {
        const entry = this.currentEntry;
        return entry ? entry.name : "";
    }

    modelSummary(entry) {
        if (!entry.access && !entry.rules) {
            return _t("Rights of the modules");
        }
        return _t("%(rights)s right(s) · %(rules)s rule(s)", {rights: entry.access, rules: entry.rules});
    }

    get modelsHint() {
        if (this.tab === "apps") {
            return _t(
                "The apps and the groups hold for the whole project. The rights and the rules are set model by model."
            );
        }
        if (this.tab === "rules") {
            return _t("A rule limits the records a group reaches; the rights say what it may do with them.");
        }
        return _t("A model shows here as soon as a change of the project touches it.");
    }

    selectModel(model) {
        this.editor.selectSecurityModel(model);
    }

    get choiceModels() {
        return (this.props.choices && this.props.choices.models) || [];
    }

    get choiceGroups() {
        return (this.props.choices && this.props.choices.groups) || [];
    }

    modelLabel(model) {
        const line = (this.project.models || []).find((m) => m.model === model);
        if (line) {
            return line.name;
        }
        const item = this.choiceModels.find((m) => m[0] === model);
        return item ? item[1] : model;
    }

    // ── tabs ────────────────────────────────────────────────────────────

    /** The tabs of the space: [{id, label, count, toggle, title}]. */
    get tabs() {
        const groups = (this.project.groups || []).length;
        return [
            {
                id: "access",
                label: _t("Rights"),
                count: this.accessRows.length + this.existingRows.length,
                toggle: "o_erplibre_studio_access_toggle",
                title: _t("The access rights the groups have on the model"),
            },
            {
                id: "rules",
                label: _t("Rules"),
                count: this.modelRules.length,
                toggle: "o_erplibre_studio_rules_toggle",
                title: _t("The record rules of the project on the model"),
            },
            {
                id: "apps",
                label: _t("Groups"),
                count: groups,
                toggle: "o_erplibre_studio_apps_toggle",
                title: _t("The apps of the project and the groups of their users"),
            },
        ];
    }

    get tabLabel() {
        const tab = this.tabs.find((t) => t.id === this.tab);
        return tab ? tab.label : "";
    }

    openTab(tab) {
        this.editor.openSecurity(tab);
    }

    permLabel(perm) {
        return permLabel(perm);
    }

    // ── rights ──────────────────────────────────────────────────────────

    get accessTitle() {
        return this.currentModel ? _t("Access rights — %(model)s", {model: this.currentLabel}) : _t("Access rights");
    }

    get onModelLabel() {
        return _t("On %(model)s", {model: this.currentLabel});
    }

    removeRowLabel(name) {
        return _t("Remove the row of %(group)s", {group: name});
    }

    /** The accessible name of a right of a row of another module: the right, the group, whether it is given. */
    fixedAria(perm, row) {
        return row[perm]
            ? _t("%(right)s – %(group)s: given by a module, read-only", {
                  right: permLabel(perm),
                  group: this.existingName(row),
              })
            : _t("%(right)s – %(group)s: not given, read-only", {
                  right: permLabel(perm),
                  group: this.existingName(row),
              });
    }

    /** The access rows of the project on the model shown. */
    get accessRows() {
        return (this.project.access || []).filter((row) => row.model === this.currentModel);
    }

    /** The access rows of the other modules on the model shown, read-only. */
    get existingRows() {
        return this.es.accessExisting[this.currentModel] || [];
    }

    accessGroup(row) {
        return accessGroup(row);
    }

    accessChanged(row, perm) {
        return accessChanged(row, perm);
    }

    get anyAccessChanged() {
        return this.accessRows.some((row) => PERMS.some((perm) => accessChanged(row, perm)));
    }

    /** The group of the project an access row names, from the payload, or null. */
    groupLine(row) {
        return row.group_line ? (this.project.groups || []).find((g) => g.id === row.group_line[0]) || null : null;
    }

    /** The external id of the group of the access row ``row`` of the project. */
    rowXmlId(row) {
        const line = this.groupLine(row);
        if (line) {
            return `${this.project.module_name}.${line.xml_name}`;
        }
        const group = row.group && this.choiceGroups.find((g) => !g.project && g.id === row.group[0]);
        return group ? group.xml_id : "";
    }

    existingXmlId(row) {
        const group = row.group && this.choiceGroups.find((g) => !g.project && g.id === row.group[0]);
        return group ? group.xml_id : "";
    }

    existingName(row) {
        return row.group ? row.group[1] : _t("Every user");
    }

    originText(module) {
        return module ? _t("Module %(module)s", {module}) : _t("Without a module");
    }

    /**
     * The accessible name of the box of ``perm`` for the group ``name``;
     * ``changed``: the draft changed it, which the ring shows on screen.
     */
    permAria(perm, name, changed = false) {
        const label = `${permLabel(perm)} – ${name}`;
        return changed ? _t("%(label)s: changed in this draft", {label}) : label;
    }

    /** The key of the row the inspector shows: « project:<id> » or « existing:<id> ». */
    rowKey(kind, row) {
        return `${kind}:${row.id}`;
    }

    isRowSelected(kind, row) {
        return this.es.security.row === this.rowKey(kind, row);
    }

    /** Show the row ``row`` in the inspector, with the members of its group. */
    async pickRow(kind, row) {
        this.es.security.row = this.rowKey(kind, row);
        const line = kind === "project" ? this.groupLine(row) : null;
        if (line) {
            await this.loadMembers(`line:${line.id}`, {line_ids: [line.id]});
        } else if (row.group) {
            await this.loadMembers(`group:${row.group[0]}`, {group_ids: [row.group[0]]});
        }
    }

    /** The members of a group (``get_group_members``), kept by ``key``; a read. */
    async loadMembers(key, kwargs) {
        if (this.state.members[key]) {
            return;
        }
        try {
            const answer = await this.orm.call(MODEL, "get_group_members", [this.project.id], kwargs);
            this.state.members[key] = (answer.lines && answer.lines[0]) ||
                (answer.groups && answer.groups[0]) || {count: 0, users: [], more: false};
        } catch (error) {
            this.state.members[key] = {error: this.editor.errorMessage(error)};
        }
    }

    /**
     * The row the inspector shows: {kind, row, name, xmlId, app, implies,
     * members, origin, editable, summary}, or null.
     */
    get selectedRow() {
        const key = this.es.security.row;
        if (!key) {
            return null;
        }
        const [kind, id] = key.split(":");
        const rows = kind === "project" ? this.accessRows : this.existingRows;
        const row = rows.find((r) => String(r.id) === id);
        if (!row) {
            return null;
        }
        const editable = kind === "project";
        const line = editable ? this.groupLine(row) : null;
        const members = line
            ? this.state.members[`line:${line.id}`]
            : row.group
            ? this.state.members[`group:${row.group[0]}`]
            : null;
        let app = "";
        let implies = [];
        if (line) {
            const appLine = (this.project.apps || []).find((a) => a.id === line.app_id);
            app = appLine ? appLine.name : "";
            implies = [...line.implied.map((g) => g[1]), ...line.implied_groups.map((g) => g[1])];
        } else if (members && !members.error) {
            app = members.category ? members.category[1] : "";
            implies = (members.implied || []).map((g) => g[1]);
        }
        const granted = PERMS.filter((perm) => row[perm]).map((perm) => permLabel(perm).toLowerCase());
        const model = this.currentLabel;
        return {
            kind,
            row,
            name: editable ? accessGroup(row)[1] : this.existingName(row),
            xmlId: editable ? this.rowXmlId(row) : this.existingXmlId(row),
            app,
            implies,
            members,
            pending: Boolean(line && !line.applied),
            origin: editable ? _t("This project") : this.originText(row.module),
            editable,
            summary: granted.length
                ? _t("Can %(rights)s the records of %(model)s.", {rights: granted.join(", "), model})
                : _t("No access to %(model)s.", {model}),
        };
    }

    membersText(members) {
        return _t("%(count)s member(s)", {count: members.count});
    }

    // ── rules ───────────────────────────────────────────────────────────

    get modelRules() {
        return (this.project.rules || []).filter((rule) => rule.model === this.currentModel);
    }

    get rulesTitle() {
        return this.currentModel ? _t("Record rules — %(model)s", {model: this.currentLabel}) : _t("Record rules");
    }

    get noRuleText() {
        if (!this.currentModel) {
            return _t("No record rule.");
        }
        return _t(
            "No rule of the project on %(model)s: the rights apply to all its records, and the rules of the modules stay in force.",
            {model: this.currentLabel}
        );
    }

    /** The fields of the rules of ``model``: fields_get of a model of the database, else what the project defines. */
    async loadRuleFields(model) {
        if (this.tab !== "rules" || !model || this.state.fields[model]) {
            return;
        }
        const line = (this.project.models || []).find((m) => m.model === model);
        if (line && !line.applied) {
            const touched = (this.project.touched_models || []).find((m) => m.model === model);
            const fields = {...magicFields(), x_name: {string: _t("Name"), type: "char"}};
            for (const field of (touched && touched.fields) || []) {
                fields[field.name] = {string: field.label, type: field.ttype};
            }
            this.state.fields[model] = {fields, complete: false};
            return;
        }
        try {
            const fields = await this.fieldService.loadFields(model);
            this.state.fields[model] = {fields, complete: true};
        } catch {
            this.state.fields[model] = {fields: null, complete: false};
        }
    }

    /** The conditions of the domain ``domain`` on ``model`` (ruleConditions). */
    conditions(domain, model) {
        const known = this.state.fields[model] || {};
        return ruleConditions(domain, known.fields || null, Boolean(known.complete));
    }

    connectorText(connector) {
        return connector === "|" ? _t("OR") : _t("AND");
    }

    /** The first unknown field of ``rule`` a field of its model replaces: {from, to, label}, or null. */
    fixOf(rule) {
        const known = this.state.fields[rule.model];
        const read = this.conditions(rule.domain, rule.model);
        if (!known || !known.complete || !read) {
            return null;
        }
        for (const condition of read.conditions) {
            if (condition.bad) {
                const to = suggestField(condition.path, known.fields);
                if (to) {
                    return {from: condition.path, to, label: known.fields[to].string || to};
                }
            }
        }
        return null;
    }

    fixLabel(fix) {
        return _t("Replace with %(field)s", {field: fix.label});
    }

    async applyFix(rule, fix) {
        await this.editor.saveRuleValues(rule, {domain: replaceDomainField(rule.domain, fix.from, fix.to)});
    }

    /** The answer of « Check » for ``rule``, while its domain is the one checked. */
    checkOf(rule) {
        const check = this.state.checks[rule.id];
        return check && check.domain === rule.domain ? check : null;
    }

    checkText(check) {
        if (!check.ok) {
            return check.error;
        }
        if (check.count === false) {
            return _t("Valid domain; Apply checks its fields once it created the model.");
        }
        return _t("Valid domain · %(count)s record(s)", {count: check.count});
    }

    /** Check the domain of ``rule`` as the server evaluates it (a read), or clear the answer. */
    async verifyRule(rule) {
        if (this.checkOf(rule)) {
            delete this.state.checks[rule.id];
            return;
        }
        try {
            const result = await this.orm.call(MODEL, "check_rule_domain", [this.project.id, rule.model, rule.domain]);
            this.state.checks[rule.id] = {...result, domain: rule.domain};
        } catch (error) {
            this.state.checks[rule.id] = {ok: false, error: this.editor.errorMessage(error), domain: rule.domain};
        }
    }

    toggleRulePerm(rule, perm) {
        return this.editor.saveRuleValues(rule, {[perm]: !rule[perm]});
    }

    opsLabel(rule) {
        return _t("Operations of the rule %(rule)s", {rule: rule.name});
    }

    isRuleSelected(rule) {
        return Boolean(this.es.ruleForm && this.es.ruleForm.id === rule.id);
    }

    missingGroupText(xmlid) {
        return _t("This group no longer exists: %(group)s", {group: xmlid});
    }

    ruleNeedsGroup(rule) {
        return !rule.global_rule && !rule.groups.length && !(rule.group_lines || []).length;
    }

    editLabel(rule) {
        return _t("Edit the rule %(rule)s", {rule: rule.name});
    }

    removeLabel(rule) {
        return _t("Remove the rule %(rule)s", {rule: rule.name});
    }

    // ── the rule form ───────────────────────────────────────────────────

    get form() {
        return this.es.ruleForm;
    }

    groupName(groupId) {
        const group = this.choiceGroups.find((g) => !g.project && g.id === groupId);
        return group ? group.name : String(groupId);
    }

    groupLineName(lineId) {
        const line = (this.project.groups || []).find((g) => g.id === lineId);
        if (line) {
            const app = (this.project.apps || []).find((a) => a.id === line.app_id);
            return app ? `${app.name} / ${line.name}` : line.name;
        }
        const choice = this.choiceGroups.find((g) => g.project && g.line_id === lineId);
        return choice ? choice.name : String(lineId);
    }

    /** The groups of the rule form: [{value, name, project}], the existing groups then those of the project. */
    get ruleFormGroups() {
        const form = this.form;
        if (!form) {
            return [];
        }
        return [
            ...form.group_ids.map((id) => ({value: String(id), name: this.groupName(id), project: false})),
            ...form.group_line_ids.map((id) => ({value: `line:${id}`, name: this.groupLineName(id), project: true})),
        ];
    }

    get formOpsText() {
        const form = this.form;
        const ops = PERMS.filter((perm) => form[perm]).map((perm) => permLabel(perm).toLowerCase());
        return ops.length
            ? _t("Filters the records when one wants to %(operations)s them.", {operations: ops.join(", ")})
            : _t("No operation: the rule filters nothing.");
    }

    get formTitle() {
        const form = this.form;
        return form.id ? form.name || _t("Rule") : _t("New rule");
    }

    get formKind() {
        return _t("Record rule · %(model)s", {model: this.modelLabel(this.form.model)});
    }

    /** The answer of the last check of the form, while the form holds the domain it checked. */
    get ruleCheck() {
        const check = this.es.ruleCheck;
        const form = this.form;
        return check && form && check.model === form.model && check.domain === form.domain ? check : null;
    }

    ruleCheckText(check) {
        return this.editor.ruleCheckText(check);
    }

    removeGroupLabel(name) {
        return _t("Remove the group %(group)s", {group: name});
    }

    /** Remove the rule the form edits. */
    async removeFormRule() {
        const rule = (this.project.rules || []).find((r) => r.id === this.form.id);
        if (rule) {
            await this.editor.removeRule(rule);
        }
    }

    groupValue(group) {
        return groupValue(group);
    }

    get projectGroupSuffix() {
        return _t("project");
    }

    get domainPlaceholder() {
        return "[('create_uid', '=', user.id)]";
    }

    // ── groups ──────────────────────────────────────────────────────────

    /**
     * The members of the groups of the project once Apply made them, and
     * what the next Apply takes from them; read again when the draft
     * changes while the tab Groups shows.
     */
    async loadGroupData() {
        const project = this.project;
        const key = `${project.id}:${project.revision}:${project.state}`;
        if (this.tab !== "apps" || this.state.groupKey === key) {
            return;
        }
        this.state.groupKey = key;
        const lines = (project.groups || []).filter((g) => g.applied).map((g) => g.id);
        const lineMembers = {};
        let losses = [];
        if (lines.length) {
            try {
                const answer = await this.orm.call(MODEL, "get_group_members", [project.id], {line_ids: lines});
                for (const entry of answer.lines || []) {
                    lineMembers[entry.line_id] = entry;
                }
                if (project.applied) {
                    losses = await this.orm.call(MODEL, "get_group_losses", [project.id]);
                }
            } catch {
                // Without them, the cards show no member count.
            }
        }
        Object.assign(this.state, {lineMembers, losses});
    }
}
