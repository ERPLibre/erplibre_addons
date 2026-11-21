/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {X2MANY_TYPES} from "./studio_relations";
import {
    DEFAULT_TIMELINE_MODE,
    FIELD_LANES,
    LANE_ZONE_PREFIX,
    StudioFrise,
    TIMELINE_LANES,
    hasViewType,
    laneAccepts,
    laneLabel,
    writableColorRules,
} from "./studio_timeline";
import {
    CHANGE_TAGS,
    NUMBER_TYPES,
    TEMPLATED_TYPES,
    attributeLabel,
    canDragBlock,
    canSelectBlock,
    changeKindLabel,
    endHook,
    findBlock,
    isTrue,
    pivotLanes,
    searchColumns,
    searchEndHook,
    valueLabel,
} from "./studio_utils";

/**
 * One node of the edited arch: a container with its children and the drop
 * hooks between them, a field, or another element. It reads the selection,
 * the hook under the dragged item and the page shown of a notebook from
 * the state of the editor, through a ``useState`` of its own: a block
 * renders again when what it reads of that state changes, without the
 * props of the blocks above it changing.
 */
export class StudioBlock extends Component {
    static template = "erplibre_studio.Block";
    static props = {block: Object, editor: Object, viewType: String};

    setup() {
        this.editorState = useState(this.props.editor.state);
    }

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
        return this.editorState.selected === this.block.path;
    }

    get templated() {
        return TEMPLATED_TYPES.includes(this.props.viewType);
    }

    /** Whether the block can be dragged (``canDragBlock``). */
    get canDrag() {
        return canDragBlock(this.block, this.props.viewType);
    }

    /** Whether a click selects the block: any block but a QWeb template. */
    get canSelect() {
        return canSelectBlock(this.block);
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
        const index = this.editorState.pages[this.block.path] || 0;
        return this.pages[index] || this.pages[0];
    }

    get flags() {
        const attrs = this.block.attrs || {};
        const flags = [];
        if (isTrue(attrs.invisible) || isTrue(attrs.column_invisible)) {
            // A node the draft hides shows the tag of its change instead.
            if (!this.isHiddenChange) {
                flags.push({key: "hidden", label: _t("hidden")});
            }
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
        if (this.field.pending && !this.changeTags.some((tag) => tag.kind === "new")) {
            flags.push({key: "pending", label: _t("new")});
        }
        return flags;
    }

    /**
     * The tags of the draft changes of the block, of the kinds CHANGE_TAGS
     * names: [{kind, label}]. The changes of the payload mark the blocks
     * they touch (``change_kinds``).
     */
    get changeTags() {
        const kinds = this.block.change_kinds || [];
        return CHANGE_TAGS.filter((kind) => kinds.includes(kind)).map((kind) => ({kind, label: changeKindLabel(kind)}));
    }

    /**
     * The dot of the block: « changed » for a change of another kind than
     * the tags show (moved, an attribute), « inside » for a block under
     * which a block changed, else null.
     */
    get changeDot() {
        const block = this.block;
        if (block.changed && !this.changeTags.length) {
            return "changed";
        }
        return block.changed_inside ? "inside" : null;
    }

    /** The title of a change dot. */
    dotTitle(dot) {
        if (dot === "inside") {
            return _t("Holds changes of the draft");
        }
        return (this.block.change_kinds || []).map(changeKindLabel).join(", ");
    }

    /** Whether the hidden tag of the block marks a node the draft hides. */
    get isHiddenChange() {
        return (this.block.change_kinds || []).includes("hidden");
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
        this.editorState.pages[this.block.path] = index;
    }

    /** The hook the dragged item is over, as ``hookKey`` names it. */
    get activeHook() {
        return this.editorState.hook;
    }
}
StudioBlock.components = {StudioBlock};

/**
 * The canvas of the editor: the arch tree of a form or a list, the template
 * of a kanban card or of a timeline item, the columns of a search view, the
 * axes of a pivot. It renders from its props: a component renders again
 * when its props change, not when the editor reads its own state, so what
 * the canvas shows of that state reaches it as a prop. A drop, a selection
 * or the filter form goes through the editor ``editor``, which holds the
 * state.
 */
export class StudioCanvas extends Component {
    static template = "erplibre_studio.Canvas";
    static components = {StudioBlock, StudioFrise};
    static props = {
        editor: Object,
        // The payload of the editor (get_editor_data).
        data: Object,
        viewType: String,
        project: {type: [Object, {value: null}], optional: true},
        busy: {type: Boolean, optional: true},
        // The item being dragged and the hook it is over.
        dragging: {type: [Object, {value: null}], optional: true},
        hook: {type: [String, {value: null}], optional: true},
        // The kanban template on screen, by name.
        template: {type: [String, {value: null}], optional: true},
        // The new filter of a search view being written.
        filterForm: {type: [Object, {value: null}], optional: true},
        // The lane of a timeline the inspector shows (TIMELINE_LANES), or null.
        lane: {type: [String, {value: null}], optional: true},
    };

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

    get project() {
        return this.props.project;
    }

    get activeHook() {
        return this.props.hook;
    }

    fieldInfo(name) {
        return (this.data.fields || {})[name] || {};
    }

    attributeLabel(attribute) {
        return attributeLabel(attribute);
    }

    // ── kanban and timeline ─────────────────────────────────────────────

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
        return templates.find((t) => t.name === this.props.template) || templates[0] || null;
    }

    selectTemplate(name) {
        this.editor.state.template = name;
    }

    /** The fields a QWeb view declares outside its templates. */
    get loadedBlocks() {
        return ((this.root && this.root.children) || []).filter((b) => b.kind === "field");
    }

    get timelineTemplate() {
        const path = this.layout.template;
        return path ? findBlock(this.root, (b) => b.path === path) : null;
    }

    // ── the lanes of a timeline ─────────────────────────────────────────

    /** The attributes of the root a draft « set_attribute » writes. */
    get changedAttributes() {
        return new Set(
            (this.data.changes || [])
                .filter((c) => c.type === "set_attribute" && c.attribute && c.xpath === this.root.path)
                .map((c) => c.attribute)
        );
    }

    /**
     * The lanes of the canvas of a timeline: [{key, label, accepts,
     * glyph, zone, drop, over, refused, selected, changed, chips, empty}].
     * A chip is a value of the lane: a field of an attribute (removable
     * unless the view needs it), a color rule (removable when the editor
     * can write the others again).
     */
    get timelineLanes() {
        const attrs = (this.root && this.root.attrs) || {};
        const changed = this.changedAttributes;
        const required = (this.data.required_attributes || {})[this.root.tag] || [];
        const dragging = this.props.dragging;
        const rules = this.layout.colors || [];
        const writable = writableColorRules(rules);
        return TIMELINE_LANES.map((lane) => {
            const zone = `${LANE_ZONE_PREFIX}${lane.key}`;
            const drop = FIELD_LANES.includes(lane.key) && Boolean(this.project);
            let chips = [];
            let empty = "";
            if (lane.key === "colors") {
                chips = rules.map((rule, index) => ({
                    key: `rule_${index}`,
                    index,
                    color: rule.color,
                    text: rule.expression,
                    remove: writable && this.project ? () => this.editor.deleteColorRule(index) : null,
                    removeLabel: _t("Remove the rule %(rule)s", {rule: rule.expression}),
                }));
                empty = _t("Default color");
            } else if (FIELD_LANES.includes(lane.key)) {
                chips = lane.attributes
                    .filter((attribute) => attrs[attribute])
                    .map((attribute) => {
                        const name = attrs[attribute];
                        const label = this.fieldInfo(name).string || name;
                        const text = attribute === "date_delay" ? `${attributeLabel(attribute)} · ${label}` : label;
                        return {
                            key: attribute,
                            attribute,
                            text: `${text} · ${name}`,
                            changed: changed.has(attribute),
                            remove:
                                required.includes(attribute) || !this.project
                                    ? null
                                    : () => this.editor.setNodeAttribute(this.root, attribute, ""),
                            removeLabel: _t("Remove %(field)s from %(lane)s", {field: label, lane: laneLabel(lane.key)}),
                        };
                    });
                empty = _t("Drop a field here");
            }
            return {
                ...lane,
                zone,
                label: laneLabel(lane.key),
                accepts: laneAccepts(lane.key),
                drop,
                over: this.activeHook === this.editor.hookKey(this.root.path, "lane", zone),
                refused: Boolean(drop && dragging && !this.editor.accepts(dragging, zone)),
                selected: this.props.lane === lane.key,
                changed: lane.attributes.some((attribute) => changed.has(attribute)),
                chips,
                empty,
            };
        });
    }

    /** The scales of a timeline: [{value, label, pressed}]. */
    get timelineModes() {
        const current = (this.root.attrs || {}).mode || DEFAULT_TIMELINE_MODE;
        return ((this.data.choices || {}).timeline_mode || []).map(([value, label]) => ({
            value,
            label: valueLabel("timeline_mode", value) || label,
            pressed: value === current,
        }));
    }

    setMode(value) {
        if (value !== ((this.root.attrs || {}).mode || DEFAULT_TIMELINE_MODE)) {
            return this.editor.setNodeAttribute(this.root, "mode", value);
        }
    }

    /**
     * Whether the canvas shows the timeline with the draft: web_timeline is
     * loaded and the view exists in the database.
     */
    get friseAvailable() {
        const view = this.data.view || {};
        return Boolean(view.id && !view.pending && hasViewType("timeline"));
    }

    get friseUnavailable() {
        const view = this.data.view || {};
        if (view.pending || !view.id) {
            return _t("The timeline shows here once Apply creates its view.");
        }
        return _t("The web client does not load web_timeline: reload the page.");
    }

    // ── search and pivot ────────────────────────────────────────────────

    get searchColumns() {
        return searchColumns(this.root);
    }

    searchEndHook(column) {
        return searchEndHook(this.root, column);
    }

    endHook(blocks, fallback) {
        return endHook(blocks, fallback);
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

    closeFilterForm() {
        this.editor.state.filterForm = null;
    }

    addCondition() {
        this.props.filterForm.conditions.push(this.editor.newCondition());
    }

    removeCondition(index) {
        this.props.filterForm.conditions.splice(index, 1);
    }

    setConditionField(condition, name) {
        Object.assign(condition, this.editor.newCondition(name));
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
}
