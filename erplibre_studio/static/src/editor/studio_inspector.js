/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {StudioFieldName} from "./studio_field_name";
import {blockGlyph, isOutlineContainer, outlineCount, outlineLabel, tagLabel} from "./studio_outline";
import {
    DEFAULT_TIMELINE_MODE,
    laneHelp,
    laneLabel,
    openingTag,
    templateFieldLabels,
    timelineLane,
    writableColorRules,
} from "./studio_timeline";
import {
    DATE_TYPES,
    TEMPLATED_TYPES,
    attributeLabel,
    changeKindLabel,
    fieldTypeLabel,
    fieldWidgets,
    findBlock,
    isTrue,
    selectionToText,
    textToSelection,
    valueLabel,
} from "./studio_utils";

// The tabs of the inspector: the properties of the selection, the changes
// of the draft in the view on screen.
export const INSPECTOR_TABS = ["properties", "changes"];
// The change types that define a field of the project rather than edit
// the view.
const FIELD_CHANGES = ["add_field", "update_field"];
const RELATION_TYPES = ["many2one", "one2many", "many2many"];

/**
 * The inspector of the view space, in two tabs. « Properties »: the
 * selected block, else the view itself. A field shows its definition
 * (label, technical name, editable for a new field not created yet
 * (StudioFieldName), and for a field of the project its tooltip,
 * read-only, values and comodel) apart from what this view sets
 * on it (required, hidden, optional, the attributes « set_attribute »
 * writes); a container shows what it holds. « Changes »: the changes of
 * the draft in this view, each one revealing its block on the canvas. It
 * renders from its props; every change is one operation of the editor
 * ``editor``.
 */
export class StudioInspector extends Component {
    static template = "erplibre_studio.Inspector";
    static components = {StudioFieldName};
    static props = {
        editor: Object,
        // The payload of the editor (get_editor_data).
        data: Object,
        viewType: String,
        // The path of the selected block.
        selected: {type: [String, {value: null}], optional: true},
        busy: {type: Boolean, optional: true},
        // The color rules of a timeline being edited, null when none is.
        colors: {type: [Array, {value: null}], optional: true},
        // [[model, label]] a many2one can point to, once loaded.
        comodels: {type: [Array, {value: null}], optional: true},
        // The tab shown, one of INSPECTOR_TABS.
        tab: {type: String, optional: true},
        // Whether a project holds the draft: the review needs one.
        hasProject: {type: Boolean, optional: true},
        // The lane of a timeline shown (TIMELINE_LANES), or null.
        lane: {type: [String, {value: null}], optional: true},
        // The preview on screen (StudioEditor.previewInfo), or null: the
        // tab « Properties » then describes it.
        preview: {type: [Object, {value: null}], optional: true},
    };

    setup() {
        // Whether the attributes the draft gives a timeline show.
        this.local = useState({generated: false});
    }

    get editor() {
        return this.props.editor;
    }

    get data() {
        return this.props.data;
    }

    get viewType() {
        return this.props.viewType;
    }

    get layout() {
        return this.data.layout || {};
    }

    get root() {
        return this.data.blocks;
    }

    allows(operation) {
        return (this.data.operations || []).includes(operation);
    }

    fieldInfo(name) {
        return (this.data.fields || {})[name] || {};
    }

    isTrue(value) {
        return isTrue(value);
    }

    get selectedBlock() {
        return this.props.selected && findBlock(this.data.blocks, (b) => b.path === this.props.selected);
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

    attr(name) {
        const block = this.selectedBlock;
        return (block && block.attrs && block.attrs[name]) || "";
    }

    get hideAttribute() {
        return this.data.hide_mode || (this.viewType === "list" ? "column_invisible" : "invisible");
    }

    /**
     * What the properties of ``block`` offer, ``field`` being its field
     * (fieldInfo): ``definition`` when the field belongs to the project and
     * its definition is edited (label, tooltip, read-only, values,
     * comodel); else what the view sets on the node: ``relabel``, ``help``,
     * ``readonly``. Then, for any block, ``required``, ``hidden``,
     * ``optional`` and the ``settable`` attributes; ``any`` when the
     * fieldset « In this view » has one of them to show.
     */
    viewProps(block, field) {
        const isField = block.kind === "field";
        const definition = Boolean(isField && field.project && this.allows("update_field"));
        const props = {
            definition,
            relabel: !definition && this.allows("relabel") && ["field", "filter", "group_by"].includes(block.kind),
            help: !definition && isField && this.allows("help"),
            readonly: !definition && isField && this.allows("readonly"),
            required: isField && this.allows("required"),
            hidden: this.hidesByAttribute && this.canRemove(block),
            optional: this.allows("optional"),
            settable: this.settableOf(block).length > 0,
        };
        props.any = Boolean(
            (props.relabel && !isField) ||
                props.help ||
                props.readonly ||
                props.required ||
                props.hidden ||
                props.optional ||
                props.settable
        );
        return props;
    }

    /** Whether « hide » sets an attribute (it removes the node in a search or a pivot). */
    get hidesByAttribute() {
        return this.allows("hide") && this.hideAttribute !== "remove";
    }

    selectionText(field) {
        return selectionToText((field.definition && field.definition.selection) || field.selection);
    }

    // ── the header of the properties ────────────────────────────────────

    /** The glyph of ``block``, as the plan shows it. */
    glyph(block) {
        return blockGlyph(block, this.data.fields || {});
    }

    /** The name the header shows for ``block``. */
    heading(block) {
        if (block.kind === "field") {
            return (block.attrs && block.attrs.string) || block.label || block.name;
        }
        return outlineLabel(block);
    }

    /**
     * What ``block`` is, under its name: for a field where it comes from
     * and its type, for a container its tag and what it holds.
     */
    kindOf(block) {
        if (block.kind === "field") {
            const field = this.fieldInfo(block.name);
            const origin = field.project ? _t("New field") : _t("Existing field");
            let type = field.type ? fieldTypeLabel(field.type) : "";
            const relation = field.relation || (field.definition && field.definition.relation);
            if (type && relation && RELATION_TYPES.includes(field.type)) {
                type = _t("%(type)s to %(model)s", {type, model: relation});
            }
            return type ? `${origin} · ${type}` : origin;
        }
        if (this.isContainer(block)) {
            return `${tagLabel(block.tag)} · ${this.contentsCount(block)}`;
        }
        return (
            {
                filter: _t("Filter"),
                group_by: _t("Group by"),
                separator: _t("Separator"),
                widget: _t("Widget"),
            }[block.kind] ||
            block.tag ||
            ""
        );
    }

    /** Whether ``block`` holds other blocks (a group, a page, a notebook…). */
    isContainer(block) {
        return Boolean(block) && block.kind !== "field" && isOutlineContainer(block);
    }

    /** How many fields ``block`` holds, or tabs for a notebook. */
    contentsCount(block) {
        const count = outlineCount(block);
        if (block.tag === "notebook") {
            return _t("%(count)s tab(s)", {count});
        }
        return _t("%(count)s field(s)", {count});
    }

    /** The labels of the blocks right under ``block``, in their order. */
    contents(block) {
        return (block.children || []).map((child) => outlineLabel(child));
    }

    /** The kinds of the draft changes on ``block``, as text; "" for none. */
    changedNote(block) {
        const kinds = block.change_kinds || [];
        if (!kinds.length) {
            return "";
        }
        return _t("Changed by the draft: %(kinds)s.", {kinds: kinds.map((k) => changeKindLabel(k)).join(", ")});
    }

    /**
     * Whether the technical name of ``field`` is edited here: a new field
     * of the project not created yet, in a view that renames fields.
     */
    nameEditable(field) {
        return Boolean(field.project && field.pending && this.allows("rename_field"));
    }

    /** Why the technical name of ``field`` cannot change here. */
    nameHelp(field) {
        if (!field.project) {
            return _t("Field of an installed module: its name does not change here.");
        }
        if (field.pending) {
            return _t("Its technical name changes in a form, list or kanban view, until Apply.");
        }
        return _t("Frozen at Apply: its name is a column of the table in the database.");
    }

    // ── the changes of the view ─────────────────────────────────────────

    get tab() {
        return INSPECTOR_TABS.includes(this.props.tab) ? this.props.tab : "properties";
    }

    /** The changes of the draft in the view on screen, in their order. */
    get changes() {
        return this.data.changes || [];
    }

    setTab(tab) {
        this.editor.setInspectorTab(tab);
    }

    /** Where ``change`` belongs and what it does: « Field · new », « View · moved ». */
    changeKind(change) {
        const area = FIELD_CHANGES.includes(change.type) ? _t("Field") : _t("View");
        return change.kind ? `${area} · ${changeKindLabel(change.kind)}` : area;
    }

    pickChange(change) {
        this.editor.revealChange(change);
    }

    /** Show the review of the whole project. */
    openReview() {
        return this.editor.openSpace("review");
    }

    // ── changes, made by the editor ─────────────────────────────────────

    setNodeAttribute(block, attribute, value) {
        return this.editor.setNodeAttribute(block, attribute, value);
    }

    setAttribute(type, value) {
        return this.editor.setAttribute(type, value);
    }

    updateField(values) {
        return this.editor.updateField(values);
    }

    async updateSelection(text) {
        if (this.editor.state.busy) {
            return;
        }
        await this.updateField({selection: textToSelection(text)});
    }

    loadComodels() {
        return this.editor.loadComodels();
    }

    removeSelected() {
        return this.editor.removeSelected();
    }

    // ── the lanes of a timeline ─────────────────────────────────────────

    get timelineLabel() {
        return _t("Timeline");
    }

    get viewPropertiesLabel() {
        return _t("View properties");
    }

    /**
     * The lane of the timeline shown, or null: {key, label, glyph, kind,
     * help, entries (the attributes it sets), fields (what the item shows,
     * for the template)}.
     */
    get laneInfo() {
        const lane = this.viewType === "timeline" && timelineLane(this.props.lane);
        if (!lane || !this.root) {
            return null;
        }
        const entries = this.settableOf(this.root).filter((entry) => lane.attributes.includes(entry.attribute));
        const template = this.layout.template && findBlock(this.root, (b) => b.path === this.layout.template);
        return {
            key: lane.key,
            glyph: lane.glyph,
            label: laneLabel(lane.key),
            kind: lane.attributes.length
                ? _t("Lane of the timeline · %(attributes)s", {attributes: lane.attributes.join(", ")})
                : _t("Lane of the timeline"),
            help: laneHelp(lane.key),
            entries,
            fields: template ? templateFieldLabels(template, this.data.fields || {}) : [],
        };
    }

    /** The attributes of the timeline outside the lane ``lane`` (laneInfo). */
    otherEntries(lane) {
        const own = lane ? lane.entries.map((entry) => entry.attribute) : [];
        return this.settableOf(this.root).filter((entry) => !own.includes(entry.attribute));
    }

    /** The scales of ``entry`` (« mode »): [{value, label, pressed}]. */
    modesOf(entry, block) {
        const current = entry.value || DEFAULT_TIMELINE_MODE;
        return this.choicesOf(entry, block).map(([value, label]) => ({value, label, pressed: value === current}));
    }

    setMode(block, entry, item) {
        if (!item.pressed) {
            return this.setNodeAttribute(block, entry.attribute, item.value);
        }
    }

    /** The opening tag of ``block`` with the attributes it has in the draft. */
    generatedTag(block) {
        return openingTag(block.tag, block.attrs || {});
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

    /** Whether the editor writes the rules of the view again (writableColorRules). */
    get colorsWritable() {
        return Boolean(writableColorRules(this.layout.colors || []));
    }

    removeRuleLabel(rule) {
        return _t("Remove the rule %(rule)s", {rule: rule.expression});
    }

    editColors() {
        this.editor.editColors();
    }

    deleteColorRule(index) {
        return this.editor.deleteColorRule(index);
    }

    cancelColors() {
        this.editor.state.colors = null;
    }

    addColorRule() {
        this.props.colors.push(this.editor.newColorRule());
    }

    removeColorRule(index) {
        this.props.colors.splice(index, 1);
    }

    /** Write the rules being edited; none removes the colors. */
    async saveColors(rules) {
        const value = (rules || []).filter((rule) => rule.field);
        if (await this.setNodeAttribute(this.root, "colors", value.length ? value : "")) {
            this.editor.state.colors = null;
        }
    }

    // ── the preview ─────────────────────────────────────────────────────

    /** How ``preview`` (props.preview) renders, under its title. */
    previewModeLabel(preview) {
        if (preview.kind === "view") {
            return _t("The view with the draft");
        }
        return preview.mode === "real" ? _t("Real, rolled back at the end") : _t("Simulation, nothing is written");
    }

    /** [[term, description]] of how ``preview`` renders. */
    renderFacts(preview) {
        if (preview.kind === "view") {
            return [
                [_t("Rendered by"), _t("The server, with the draft of the project")],
                [_t("Records"), _t("Those of the database, as you read them")],
                [_t("At the end"), _t("Nothing to roll back: nothing is saved")],
            ];
        }
        if (preview.mode === "real") {
            return [
                [_t("Rendered by"), _t("The server, as the superuser, from the model created for a moment")],
                [_t("Locks"), _t("A statement waits 2 s at most for a lock")],
                [_t("At the end"), _t("The whole savepoint rolls back")],
            ];
        }
        return [
            [_t("Rendered by"), _t("Your browser, from views the server computes from the draft")],
            [_t("Records"), _t("None: the model does not exist")],
            [_t("At the end"), _t("Nothing to roll back")],
        ];
    }

    leavePreview() {
        return this.editor.leavePreview();
    }
}
