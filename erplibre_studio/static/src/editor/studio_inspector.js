/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillUpdateProps, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {StudioDomainDialog} from "./studio_domain";
import {StudioFieldName, fieldNameKey} from "./studio_field_name";
import {StudioGeoLayers} from "./studio_geo_layers";
import {StudioWidgetOptions} from "./studio_widget_options";
import {blockGlyph, isOutlineContainer, outlineCount, outlineLabel, tagLabel} from "./studio_outline";
import {
    DEFAULT_MODES,
    fieldLabels,
    laneHelp,
    laneLabel,
    laneOf,
    openingTag,
    templateFieldLabels,
    writableColorRules,
} from "./studio_timeline";
import {
    DATE_TYPES,
    GEO_TYPES,
    MAX_FIELD_SIZE,
    attributeLabel,
    blockTrail,
    canRemoveBlock,
    changeDot,
    changeKindLabel,
    fieldOptions,
    fieldTypeLabel,
    fieldWidgets,
    findBlock,
    isGhost,
    isTrue,
    marginDot,
    selectionToText,
    textToSelection,
    valueLabel,
} from "./studio_utils";

// The tabs of the inspector: the properties of the selection, the changes
// of the draft in the view on screen.
export const INSPECTOR_TABS = ["properties", "changes"];
// The states of a module that holds the records bound to it; mirrors
// MODULE_OWNING_STATES of the server (erplibre_studio_project.py).
export const MODULE_OWNING_STATES = ["installed", "to upgrade", "to remove"];
// The change types that define a field of the project rather than edit
// the view.
const FIELD_CHANGES = ["add_field", "update_field"];
const RELATION_TYPES = ["many2one", "one2many", "many2many"];
// The kinds of attribute a field of a form or a list sets under « More
// options » (« Technical » at the Detailed level).
const ADVANCED_KINDS = ["widget", "field_options", "field_domain", "groups"];
// The view types whose fields show the attributes of ADVANCED_KINDS apart.
const ADVANCED_VIEW_TYPES = ["form", "list"];
// The field of dms_field that a form shows as a documents tree, and its
// comodel: the « mode » of that field only is settable (x2many_mode).
const DMS_FIELD = "dms_directory_ids";
const DMS_COMODEL = "dms.directory";
// The kinds of the root attributes of a view with lanes that fold under
// « Advanced » (foldedEntries): the numbers of the markers of a map.
const FOLDED_KINDS = ["pixels", "offset"];

/**
 * The inspector of the view space, in two tabs. « Properties »: the
 * selected block, else the view itself. A field shows its definition
 * (label, technical name, editable for a new field not created yet
 * (StudioFieldName), and for a field of the project its tooltip,
 * read-only, values, comodel, and the options set before Apply:
 * translatable, indexed, maximum size) apart from what this view sets
 * on it (required, hidden, optional, the attributes « set_attribute »
 * writes; in a form or a list, the widget, its options
 * (StudioWidgetOptions), the domain (as text, or in StudioDomainDialog)
 * and the groups under « Advanced »; for a new field of a model of the
 * database, the module that holds it once generated); a many2one of the
 * project, the one2many it may create on its
 * comodel and what it does when its record is deleted; a container shows
 * what it holds. « Changes »: the changes of
 * the draft in this view, each one revealing its block on the canvas or
 * undone with what depends on it. It
 * renders from its props; every change is one operation of the editor
 * ``editor``.
 */
export class StudioInspector extends Component {
    static template = "erplibre_studio.Inspector";
    static components = {StudioFieldName, StudioGeoLayers, StudioWidgetOptions};
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
        // The lane of a timeline or of a calendar shown (VIEW_LANES), or null.
        lane: {type: [String, {value: null}], optional: true},
        // The preview on screen (StudioEditor.previewInfo), or null: the
        // tab « Properties » then describes it.
        preview: {type: [Object, {value: null}], optional: true},
        // The layer of a GeoEngine view shown (its id, « new »), or null:
        // the tab « Properties » then edits it (StudioGeoLayers).
        geoLayer: {type: [Number, String, {value: null}], optional: true},
    };

    setup() {
        // Whether the attributes the draft gives a timeline show; whether
        // « Advanced » is open ({path, open}), null to follow the block.
        this.local = useState({generated: false, advanced: null, groupText: "", viewAdvanced: false});
        this.editorState = useState(this.props.editor.state);
        onWillUpdateProps((next) => {
            // A rename gives the selected field another path: « More
            // options » stays as it was on the field.
            const local = this.local.advanced;
            const before = this.props.selected;
            if (
                local &&
                before &&
                local.path === before &&
                next.selected &&
                next.selected !== before &&
                !findBlock(next.data.blocks, (b) => b.path === before)
            ) {
                this.local.advanced = {path: next.selected, open: local.open};
            }
        });
    }

    /** Whether the technical bits show (the Detailed level of the editor). */
    get detailed() {
        return this.editorState.level === "detailed";
    }

    /**
     * Whether the technical name input of the field block ``block`` holds a
     * name that does not apply (a local blocker of the editor).
     */
    nameBlocked(block) {
        return Boolean(
            block.kind === "field" && this.editorState.localNameBlockers.has(fieldNameKey(this.data.model, block.name))
        );
    }

    /**
     * Where the field block ``block`` came from, for the Detailed header:
     * created by the project, else the view it is read from.
     */
    fieldOrigin(block, field) {
        if (field.project) {
            return _t("created by this project");
        }
        const view = this.data.view || {};
        return _t("from the view %(xml_id)s", {xml_id: view.xml_id || view.name || ""});
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

    /**
     * Whether the attribute text ``value`` is true read as a number, as
     * base_geoengine reads « editable » (« 1 » is, « True » is not).
     */
    numberTrue(value) {
        return Boolean(Number(value));
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
        return canRemoveBlock(block, this.root, this.viewType);
    }

    // ── an element the draft removes ────────────────────────────────────

    /** Whether ``block`` is an element the draft removes (``isGhost``). */
    isGhost(block) {
        return isGhost(block, this.viewType);
    }

    /**
     * The texts of the properties of ``block``, an element the draft
     * removes: its heading, what it is, the note on Restore and, for the
     * Detailed level, the node as the arch holds it.
     */
    ghostInfo(block) {
        const attribute = this.hideAttribute === "remove" ? "invisible" : this.hideAttribute;
        const name = block.name ? ` name="${block.name}"` : "";
        return {
            heading: outlineLabel(block),
            kind: _t("Removed from this view"),
            note:
                block.kind === "field"
                    ? _t("The field stays in the database; Restore puts it back where it was.")
                    : _t("Restore puts this element back where it was."),
            node: `<${block.tag}${name} ${attribute}="True"/>`,
        };
    }

    /** Undo the change that removes ``block`` (StudioEditor.restoreBlock). */
    restoreBlock(block) {
        return this.editor.restoreBlock(block);
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
            .filter(([, kind]) => kind !== "field_domain" || RELATION_TYPES.includes(field.type))
            .filter(([, kind]) => kind !== "x2many_mode" || this.isDmsField(block, field))
            .map(([attribute, kind]) => ({
                attribute,
                kind,
                label: attributeLabel(attribute, kind),
                value: (block.attrs || {})[attribute] || "",
                required: required.includes(attribute),
            }));
    }

    /**
     * Whether the field block ``block`` (``field``: its entry of the
     * payload) holds the DMS directories of a record, shown as a list or
     * as the documents tree of dms_field.
     */
    isDmsField(block, field) {
        return block.kind === "field" && block.name === DMS_FIELD && field.relation === DMS_COMODEL;
    }

    /**
     * Open the embedded DMS templates of dms_field (``dms_template_action``
     * of the layout): without one for the model, its documents tree stays
     * empty.
     */
    openDmsTemplates() {
        return this.editor.action.doAction(this.layout.dms_template_action);
    }

    /** Whether ``block`` shows the attributes of ADVANCED_KINDS apart. */
    hasAdvanced(block) {
        return ADVANCED_VIEW_TYPES.includes(this.viewType) && block.kind === "field";
    }

    /** The entries of settableOf(block) under « Advanced ». */
    advancedEntries(block) {
        if (!this.hasAdvanced(block)) {
            return [];
        }
        return this.settableOf(block).filter((entry) => ADVANCED_KINDS.includes(entry.kind));
    }

    /** The entries of settableOf(block) in « In this view ». */
    plainEntries(block) {
        if (!this.hasAdvanced(block)) {
            return this.settableOf(block);
        }
        return this.settableOf(block).filter((entry) => !ADVANCED_KINDS.includes(entry.kind));
    }

    /**
     * Whether « More options » shows for ``block``: always while its
     * technical name does not apply, else as toggled on this block, else
     * open when the block has one of its attributes.
     */
    advancedOpen(block) {
        if (this.nameBlocked(block)) {
            return true;
        }
        const local = this.local.advanced;
        if (local && local.path === block.path) {
            return local.open;
        }
        return this.advancedEntries(block).some((entry) => entry.value);
    }

    toggleAdvanced(block) {
        const open = !this.advancedOpen(block);
        this.local.advanced = {path: block.path, open};
        if (open) {
            this.ensureChoices();
        }
    }

    /** Load the groups the editor offers, once. */
    ensureChoices() {
        if (!this.editor.state.choices && !this.choicesLoading) {
            this.choicesLoading = this.editor.loadChoices().finally(() => {
                this.choicesLoading = null;
            });
        }
        return this.choicesLoading;
    }

    /** The groups of get_studio_choices: [{name, xml_id, project, applied}]. */
    get groupChoices() {
        return (this.editor.state.choices && this.editor.state.choices.groups) || [];
    }

    /** The groups a node can show for: existing ones, applied ones of the project. */
    get groupOptions() {
        return this.groupChoices.filter((group) => !group.project || group.applied);
    }

    /** The names of the groups of the project not applied yet. */
    get pendingGroups() {
        return this.groupChoices.filter((group) => group.project && !group.applied).map((group) => group.name);
    }

    /** The external ids of the « groups » of ``entry`` (a comma text). */
    groupIds(entry) {
        return (entry.value || "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean);
    }

    /** The label of the external id ``xmlid`` (a leading « ! » excludes the group). */
    groupLabel(xmlid) {
        const negated = xmlid.startsWith("!");
        const id = negated ? xmlid.slice(1) : xmlid;
        const group = this.groupChoices.find((item) => item.xml_id === id);
        const name = group ? group.name : id;
        return negated ? _t("Not %(group)s", {group: name}) : name;
    }

    removeGroupLabel(xmlid) {
        return _t("Remove the group %(group)s", {group: this.groupLabel(xmlid)});
    }

    /**
     * Add the group typed in the input of ``entry`` (its name or its
     * external id); a group of the project not applied yet is refused.
     */
    async addGroup(block, entry, text) {
        const value = (text || "").trim();
        if (!value) {
            return;
        }
        await this.ensureChoices();
        const group = this.groupChoices.find((item) => item.name === value || item.xml_id === value);
        if (!group) {
            this.editor.notification.add(_t("No group %(group)s.", {group: value}), {type: "warning"});
            return;
        }
        if (group.project && !group.applied) {
            this.editor.notification.add(
                _t("Apply the group %(group)s first: the view names it by its external id.", {group: group.name}),
                {type: "warning"}
            );
            return;
        }
        this.local.groupText = "";
        const ids = this.groupIds(entry);
        if (!ids.includes(group.xml_id)) {
            await this.setNodeAttribute(block, entry.attribute, [...ids, group.xml_id]);
        }
    }

    removeGroup(block, entry, xmlid) {
        return this.setNodeAttribute(
            block,
            entry.attribute,
            this.groupIds(entry).filter((item) => item !== xmlid)
        );
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
        // A group, a tab or a separator of a form takes a label too.
        const layout =
            this.viewType === "form" &&
            ((block.kind === "container" && ["group", "page"].includes(block.tag)) || block.kind === "separator");
        const props = {
            definition,
            relabel:
                !definition &&
                this.allows("relabel") &&
                (["field", "filter", "group_by"].includes(block.kind) || layout),
            help: !definition && isField && this.allows("help"),
            readonly: !definition && isField && this.allows("readonly"),
            required: isField && this.allows("required"),
            hidden: this.hidesByAttribute && this.canRemove(block),
            optional: this.allows("optional"),
            settable: this.plainEntries(block).length > 0,
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

    /**
     * Where the new properties field ``field`` reads its definition:
     * « Defined on <comodel>.<definition field> through <many2one> ». It
     * never changes once the field is in the draft.
     */
    propertiesSource(field) {
        const definition = field.definition || {};
        return _t("Defined on %(target)s through %(field)s", {
            target: `${definition.relation}.${definition.definition_record_field}`,
            field: definition.definition_record,
        });
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

    /**
     * The note of the draft changes on ``block``: the summary of its one
     * change (``blockChange``) when the view lists it, else its kinds as
     * text; "" for none.
     */
    changedNote(block) {
        const kinds = block.change_kinds || [];
        if (!kinds.length) {
            return "";
        }
        const last = this.editorState.lastInsert;
        if (last && this.editor.isLastInsert(block)) {
            return _t("Inserted %(where)s in %(container)s.", {where: last.where, container: last.container});
        }
        const changeId = this.blockChange(block);
        const change = changeId && this.changes.find((c) => c.id === changeId);
        if (change && change.summary) {
            return change.summary;
        }
        return _t("Changed by the draft: %(kinds)s.", {kinds: kinds.map((k) => changeKindLabel(k)).join(", ")});
    }

    /** The margin dot of the note of ``block``: « ring » or « filled » (``marginDot``). */
    blockDot(block) {
        const dot = marginDot(block.change_kinds);
        return dot ? dot.dot : "filled";
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

    /**
     * The module that holds the selected field: {state, module, text},
     * null unless it is a new field of the project on a model of the
     * database. ``state``: « owned » once the module of the project is
     * installed, « future » before. A model the project creates is held
     * as a whole, its fields carry no note.
     */
    get ownerNote() {
        const block = this.selectedBlock;
        const field = this.selectedField;
        const project = this.data.project;
        if (!block || block.kind !== "field" || !field || !field.project || !project) {
            return null;
        }
        if ((this.data.view || {}).pending || (project.models || []).some((m) => m.model === this.data.model)) {
            return null;
        }
        if (MODULE_OWNING_STATES.includes(project.module_state)) {
            return {
                state: "owned",
                module: project.module_name,
                text: _t("The module generated from this project holds this field."),
            };
        }
        return {
            state: "future",
            module: project.module_name,
            text: field.pending
                ? _t(
                      "Apply creates it as a custom field of the database; once the project is generated and installed, this module holds it."
                  )
                : _t(
                      "Apply created it as a custom field of the database; once the project is generated and installed, this module holds it."
                  ),
        };
    }

    // ── the changes of the view ─────────────────────────────────────────

    get tab() {
        return INSPECTOR_TABS.includes(this.props.tab) ? this.props.tab : "properties";
    }

    /** The changes of the draft in the view on screen, in their order. */
    get changes() {
        return this.data.changes || [];
    }

    /**
     * The changes of the view in sections while the focus is on a block of
     * a form: [{key, title, changes}], those inside the block in focus,
     * then the others; null when the focus is off, the list stays whole.
     */
    get changeSections() {
        // Read through the state of the inspector: a move of the focus
        // renders the list again.
        const focus = this.editorState.focus;
        if (!focus.on || !focus.path) {
            return null;
        }
        const entry = this.editor.focusEntry;
        if (!entry) {
            return null;
        }
        const inside = (change) => Boolean(change.path) && blockTrail(entry.block, change.path).length > 0;
        const ins = this.changes.filter(inside);
        const others = this.changes.filter((change) => !inside(change));
        return [
            {
                key: "in",
                title: _t("In « %(block)s » · %(count)s", {block: entry.label, count: ins.length}),
                changes: ins,
            },
            {
                key: "elsewhere",
                title: _t("Elsewhere in the form · %(count)s", {count: others.length}),
                changes: others,
            },
        ];
    }

    /** The number of ``change`` in the list of the view, from 1. */
    changeNumber(change) {
        return this.changes.indexOf(change) + 1;
    }

    setTab(tab) {
        this.editor.setInspectorTab(tab);
    }

    /** Where ``change`` belongs and what it does: « Field · new », « View · moved ». */
    changeKind(change) {
        const area = FIELD_CHANGES.includes(change.type) ? _t("Field") : _t("View");
        return change.kind ? `${area} · ${changeKindLabel(change.kind)}` : area;
    }

    /** The dot of ``change`` in the list: « ring » or « filled » (``changeDot``). */
    changeDot(change) {
        return changeDot(change);
    }

    pickChange(change) {
        this.editor.revealChange(change);
    }

    /** Undo ``change`` with what depends on it (StudioEditor.removeChange). */
    removeChange(change) {
        return this.editor.removeChange(change.id);
    }

    undoLabel(change) {
        return _t("Undo this change: %(change)s", {change: change.summary});
    }

    /**
     * The id of the one change of the draft that touches ``block``, or
     * false when none or several do: the note of the block undoes only a
     * change it names without doubt.
     */
    blockChange(block) {
        const keys = block.changes || [];
        return keys.length === 1 && Number.isInteger(keys[0]) ? keys[0] : false;
    }

    /** Whether ``block`` holds the last insertion of the list of the canvas (« Cancel this insertion »). */
    isLastInsert(block) {
        return this.editorState.lastInsert ? this.editor.isLastInsert(block) : false;
    }

    cancelInsert() {
        return this.editor.cancelInsert();
    }

    /**
     * The insertion point of the list open on the form: {where}, null
     * when none is open.
     */
    get insertPoint() {
        const insert = this.editorState.insert;
        return insert
            ? {where: _t("%(container)s, %(where)s", {container: insert.container, where: insert.where})}
            : null;
    }

    removeBlockChange(block) {
        const changeId = this.blockChange(block);
        return changeId ? this.editor.removeChange(changeId) : undefined;
    }

    /** Show the review of the whole project. */
    openReview() {
        return this.editor.openSpace("review");
    }

    // ── changes, made by the editor ─────────────────────────────────────

    setNodeAttribute(block, attribute, value, extra = {}, onError = null) {
        return this.editor.setNodeAttribute(block, attribute, value, extra, onError);
    }

    /**
     * Set the attribute of ``entry`` on ``block`` to ``value``, read from the
     * input of ``ev``. When the change is not made (the server refuses the
     * value, the editor is busy), the input shows ``entry.value`` again:
     * Owl does not patch an attribute whose value did not change, and the
     * input would keep the value the view does not hold.
     */
    async setAttributeFrom(ev, block, entry, value) {
        const input = ev.target;
        const data = await this.setNodeAttribute(block, entry.attribute, value);
        if (!data) {
            if (input.type === "checkbox") {
                input.checked = this.numberTrue(entry.value);
            } else {
                input.value = entry.value || "";
            }
        }
        return data;
    }

    setAttribute(type, value) {
        return this.editor.setAttribute(type, value);
    }

    // ── the domain of a relational field ────────────────────────────────

    /**
     * {model, pending} of the domain of the field ``block``: the comodel
     * its domain searches, and whether it is a model of the project not
     * created yet, whose fields the visual editor cannot read.
     */
    domainComodel(block) {
        const field = this.fieldInfo(block.name);
        const model = field.relation || (field.definition && field.definition.relation) || "";
        const project = this.data.project || {};
        const pending = Boolean(model && (project.models || []).some((m) => m.model === model && !m.applied));
        return {model, pending};
    }

    get pendingDomainTitle() {
        return _t("Apply the model first: the visual editor reads its fields.");
    }

    /**
     * The domain of ``entry`` on the field ``block`` in the visual editor
     * (StudioDomainDialog). Its confirmation is one « set_attribute »; a
     * refusal of the server shows in the dialog. A domain is literal: no
     * expression (« uid ») is offered.
     */
    openDomainEditor(block, entry) {
        const {model, pending} = this.domainComodel(block);
        if (!model || pending || this.props.busy) {
            return;
        }
        const field = this.fieldInfo(block.name);
        this.editor.dialog.add(StudioDomainDialog, {
            resModel: model,
            domain: entry.value || "[]",
            allowExpressions: false,
            title: _t("Records %(field)s offers", {field: block.label || field.string || block.name}),
            text: _t("A condition on a record keeps its id: the generated module carries it."),
            confirm: async (domain) => {
                let error = null;
                const data = await this.setNodeAttribute(
                    block,
                    entry.attribute,
                    domain.trim() === "[]" ? "" : domain,
                    {},
                    (message) => {
                        error = message;
                    }
                );
                return error || (data ? null : _t("The domain was not saved."));
            },
        });
    }

    updateField(values) {
        return this.editor.updateField(values);
    }

    /**
     * {translate, index, size}: whether the new field ``field`` takes each
     * option, set before Apply (FIELD_OPTIONS).
     */
    fieldOptions(field) {
        return fieldOptions(field.type);
    }

    /**
     * Update the selected field with ``values``, from the input of ``ev``.
     * A refused update (a value out of range, a stale revision) leaves the
     * payload as it was, so Owl patches nothing and the input would keep
     * what the user typed or ticked: ``restore(input)`` shows again what
     * the draft holds. Answer whether the draft took the values.
     */
    async updateFieldFrom(ev, values, restore) {
        const input = ev.target;
        const done = await this.updateField(values);
        if (!done) {
            restore(input);
        }
        return done;
    }

    /** Make ``field`` translatable or not; a translatable field takes no index. */
    setTranslate(field, ev) {
        const checked = ev.target.checked;
        const values = {translate: checked};
        if (checked && field.definition && field.definition.index) {
            values.index = false;
        }
        return this.updateFieldFrom(ev, values, (input) => {
            input.checked = Boolean(field.definition && field.definition.translate);
        });
    }

    /** Index ``field`` or not. */
    setIndex(field, ev) {
        return this.updateFieldFrom(ev, {index: ev.target.checked}, (input) => {
            input.checked = Boolean(field.definition && field.definition.index);
        });
    }

    get maxFieldSize() {
        return MAX_FIELD_SIZE;
    }

    // ── a geometry field ────────────────────────────────────────────────

    /** Whether ``field`` is a geometry field (GEO_TYPES of base_geoengine). */
    isGeo(field) {
        return GEO_TYPES.includes(field.type);
    }

    /** The shapes a geometry field takes: [{ttype, label}], GEO_TYPES in order. */
    get geoShapes() {
        return GEO_TYPES.map((ttype) => ({ttype, label: fieldTypeLabel(ttype)}));
    }

    /**
     * Give the new geometry field ``field`` the shape of the select ``ev``:
     * another of GEO_TYPES, until Apply creates its column.
     */
    setShape(field, ev) {
        return this.updateFieldFrom(ev, {ttype: ev.target.value}, (input) => {
            input.value = field.type;
        });
    }

    /**
     * What the map of the geometry field ``field`` needs while the model
     * has no geoengine view (``geo_view_missing`` of the payload), else "".
     */
    geoNote(field) {
        if (!this.data.geo_view_missing) {
            return "";
        }
        return _t(
            "The map of %(field)s needs a GeoEngine view with a raster layer on %(model)s: add one (Add a view) once the field is applied.",
            {field: field.string || "", model: this.data.model_name || this.data.model}
        );
    }

    /** The text the size box of ``field`` shows: empty for no limit (0 or none). */
    sizeText(field) {
        const size = field.definition && field.definition.size;
        return size ? String(size) : "";
    }

    /** The maximum size of the new field ``field`` from its box; empty or 0 for no limit. */
    async setSize(field, ev) {
        const value = ev.target.value;
        const done = await this.updateFieldFrom(ev, {size: value ? Number(value) : 0}, (input) => {
            input.value = this.sizeText(field);
        });
        if (done && !Number(value)) {
            // 0 is no limit, shown as an empty box.
            ev.target.value = "";
        }
        return done;
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

    // ── a many2one of the project ───────────────────────────────────────

    /** The one2many the new many2one ``field`` creates on its comodel ({name, field_description}), or null. */
    inverseOf(field) {
        return (field.definition && field.definition.inverse_o2m) || null;
    }

    inverseLegend(field) {
        const comodel = (field.definition && field.definition.relation) || field.relation || "";
        return _t("Inverse field on %(comodel)s (optional)", {comodel});
    }

    /** The entry StudioFieldName reads for the inverse ``inverse``: its label proposes its name. */
    inverseField(inverse) {
        return {definition: {field_description: inverse.field_description}, name_auto: false};
    }

    inverseHelp(inverse) {
        return _t("Creates a one2many « %(label)s »: same prefix rule.", {label: inverse.field_description});
    }

    /**
     * Add the inverse one2many of ``field`` (the server names it and labels
     * it after the model), or remove it.
     */
    toggleInverse(field, ev) {
        const checked = ev.target.checked;
        return this.updateFieldFrom(ev, {inverse_o2m: checked ? {create: true} : false}, (input) => {
            input.checked = Boolean(this.inverseOf(field));
        });
    }

    /** What the many2one ``field`` does when its record is deleted: the radio ``ev`` chose ``value``. */
    setOnDelete(field, value, ev) {
        return this.updateFieldFrom(ev, {on_delete: value}, (input) => {
            const current = (field.definition && field.definition.on_delete) || "set null";
            for (const radio of input.closest("fieldset").querySelectorAll("input[type=radio]")) {
                radio.checked = radio.value === current;
            }
        });
    }

    /**
     * Give the inverse of ``field`` ``values`` ({name} or {field_description}).
     * Answer whether the draft took them.
     */
    async updateInverse(field, values) {
        const inverse = this.inverseOf(field);
        if (!inverse) {
            return false;
        }
        return this.updateField({
            inverse_o2m: {name: inverse.name, field_description: inverse.field_description, ...values},
        });
    }

    /** [{value, label, help}] of what a many2one does when its record is deleted. */
    get onDeleteChoices() {
        return [
            {
                value: "set null",
                label: _t("Empty the field"),
                help: _t("The records that point to it stay, without the link."),
            },
            {
                value: "restrict",
                label: _t("Block the deletion"),
                help: _t("The record cannot be deleted while a record points to it."),
            },
            {
                value: "cascade",
                label: _t("Delete as well"),
                help: _t("Every record that points to it is deleted with it."),
            },
        ];
    }

    removeSelected() {
        return this.editor.removeSelected();
    }

    // ── the lanes of a timeline or of a calendar ────────────────────────

    /** Whether the view on screen shows its settings as lanes (VIEW_LANES). */
    get hasLanes() {
        return ["timeline", "calendar", "leaflet_map"].includes(this.viewType);
    }

    /** The title of the properties of the view when no lane is shown. */
    get laneViewLabel() {
        return {calendar: _t("Calendar"), leaflet_map: _t("Map")}[this.viewType] || _t("Timeline");
    }

    /** The glyph of the view when no lane is shown. */
    get laneViewGlyph() {
        return {calendar: "Ca", leaflet_map: "Ma"}[this.viewType] || "TL";
    }

    get viewPropertiesLabel() {
        return _t("View properties");
    }

    /**
     * The lane of the timeline or of the calendar shown, or null: {key,
     * label, glyph, kind, help, entries (the attributes it sets), fields
     * (what the item of a timeline or the popover of a calendar shows)}.
     */
    get laneInfo() {
        const viewType = this.viewType;
        const lane = this.hasLanes && laneOf(viewType, this.props.lane);
        if (!lane || !this.root) {
            return null;
        }
        const entries = this.settableOf(this.root).filter((entry) => lane.attributes.includes(entry.attribute));
        const fields = this.data.fields || {};
        let shown = [];
        if (viewType === "calendar") {
            const blocks = (this.layout.popover || []).map((path) => findBlock(this.root, (b) => b.path === path));
            shown = fieldLabels(blocks.filter(Boolean), fields);
        } else {
            const template = this.layout.template && findBlock(this.root, (b) => b.path === this.layout.template);
            shown = template ? templateFieldLabels(template, fields) : [];
        }
        const attributes = lane.attributes.join(", ");
        let kind;
        if (viewType === "leaflet_map") {
            kind = _t("Lane of the map · %(attributes)s", {attributes});
        } else if (viewType === "calendar") {
            kind = attributes
                ? _t("Lane of the calendar · %(attributes)s", {attributes})
                : _t("Lane of the calendar");
        } else {
            kind = attributes
                ? _t("Lane of the timeline · %(attributes)s", {attributes})
                : _t("Lane of the timeline");
        }
        return {
            key: lane.key,
            glyph: lane.glyph,
            label: laneLabel(lane.key, viewType),
            kind,
            help: laneHelp(lane.key, viewType),
            entries,
            fields: shown,
        };
    }

    /**
     * The attributes of the view that fold under « Advanced », apart from
     * the lanes: the marker size and the popup anchor of a map.
     */
    get foldedEntries() {
        return this.hasLanes ? this.settableOf(this.root).filter((entry) => FOLDED_KINDS.includes(entry.kind)) : [];
    }

    /** Whether the folded attributes show (foldedEntries). */
    get foldedOpen() {
        return Boolean(this.local.viewAdvanced);
    }

    toggleFolded() {
        this.local.viewAdvanced = !this.local.viewAdvanced;
    }

    /**
     * The value web_view_leaflet_map takes for the number ``attribute``
     * when the view does not set it, as text; "" for none.
     */
    numberDefault(attribute) {
        const defaults = {
            marker_icon_size_x: 64,
            marker_icon_size_y: 64,
            marker_popup_anchor_x: 0,
            marker_popup_anchor_y: -32,
        };
        return attribute in defaults ? String(defaults[attribute]) : "";
    }

    /** The bounds [min, max] of a number attribute of ``kind``. */
    numberBounds(kind) {
        return kind === "pixels" ? [1, 512] : [-512, 512];
    }

    /** The attributes of the view outside the lane ``lane`` (laneInfo). */
    otherEntries(lane) {
        const own = lane ? lane.entries.map((entry) => entry.attribute) : [];
        return this.settableOf(this.root).filter(
            (entry) => !own.includes(entry.attribute) && !FOLDED_KINDS.includes(entry.kind)
        );
    }

    /** The scales of ``entry`` (« mode »): [{value, label, pressed}]. */
    modesOf(entry, block) {
        const current = entry.value || DEFAULT_MODES[this.viewType];
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
