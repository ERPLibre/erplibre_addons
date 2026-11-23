/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {deserializeDate, deserializeDateTime, formatDate, formatDateTime} from "@web/core/l10n/dates";
import {X2MANY_TYPES} from "./studio_relations";
import {tagLabel} from "./studio_outline";
import {LEAFLET_LANES} from "./studio_leaflet";
import {
    CALENDAR_LANES,
    DEFAULT_MODES,
    FIELD_LANES_BY_TYPE,
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
    canRemoveBlock,
    canSelectBlock,
    changeKeysInside,
    changeKindLabel,
    columnLabel,
    endHook,
    findBlock,
    graphLaneLabel,
    graphLanes,
    isBaseInvisible,
    isGhost,
    isTrue,
    marginDot,
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
 *
 * A field, a container title or another element holds its name in a
 * ``<button class="o_erplibre_studio_pick">`` inside the draggable div:
 * the button is a tab stop, and Enter or Space on it fires a click that
 * bubbles to the ``t-on-click.stop`` of the div, which selects. The
 * button takes no pointer event (CSS), so the mouse lands on the div: a
 * mousedown on a ``<button>`` starts no drag in Firefox. What carries a
 * tooltip (the lock, the margin dot) stays outside the button. The editor
 * reads the other keys of the button (``onCanvasKey``): Alt+Up and
 * Alt+Down move the block, Delete removes it, Escape unselects.
 *
 * The canvas of a form draws the form as the web client does: a field of a
 * group is a line « gutter | label | value », a field elsewhere its value
 * only. A change of the draft is one dot in the gutter; its tags and the
 * flags of the block show at the Detailed level. The outline, the drag
 * handle and the label chip of a block show on hover, on focus, on the
 * selection and during a drag (CSS).
 *
 * An element the draft removes from a form or a list (``isGhost``) is one
 * muted line at its place, « label removed — show », that neither moves
 * nor leaves again; a drop beside it targets its node, which stays in the
 * arch. « show » opens its row, struck, with Restore and a fold button;
 * the Detailed level always shows the row, and draws nothing under it.
 */
export class StudioBlock extends Component {
    static template = "erplibre_studio.Block";
    static props = {
        block: Object,
        editor: Object,
        viewType: String,
        // The block the block is a child of, when there is one: a field
        // of a group draws as a form line, a button of a header as a chip.
        parent: {type: [Object, {value: null}], optional: true},
    };

    setup() {
        this.editorState = useState(this.props.editor.state);
        // Whether the removed line of an element the draft removes shows
        // its row at the Simple level (« show »): a state of the block.
        this.ghostState = useState({open: false});
    }

    get block() {
        return this.props.block;
    }

    get editor() {
        return this.props.editor;
    }

    /** Whether the technical bits of the block show (the Detailed level). */
    get detailed() {
        return this.editorState.level === "detailed";
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

    /**
     * The keys the editor reads on the button of the block, as
     * ``aria-keyshortcuts`` names them: Alt+Up and Alt+Down for a block
     * that moves, Delete for one that can leave the view, Escape always.
     */
    get pickShortcuts() {
        const keys = this.canDrag ? ["Alt+ArrowUp", "Alt+ArrowDown"] : [];
        if (canRemoveBlock(this.block, this.editor.root, this.props.viewType)) {
            keys.push("Delete");
        }
        keys.push("Escape");
        return keys.join(" ");
    }

    /** Whether a click selects the block: any block but a QWeb template. */
    get canSelect() {
        return canSelectBlock(this.block);
    }

    /**
     * The accessible name of the button that selects the block: its kind,
     * the translated name of its tag (``tagLabel``), its label and, for a
     * field or a widget, its technical name.
     */
    get pickLabel() {
        const block = this.block;
        const label = block.label;
        // The tag in the language of the user (« Group », « Tabs »…).
        const tag = tagLabel(block.tag);
        const own = label && label !== block.tag;
        switch (block.kind) {
            case "field":
                return _t("Field %(label)s (%(name)s)", {label, name: block.name});
            case "widget":
                return _t("Widget %(label)s (%(name)s)", {
                    label: (block.attrs && block.attrs.title) || label,
                    name: block.name,
                });
            case "filter":
                return _t("Filter %(label)s", {label});
            case "group_by":
                return _t("Grouping %(label)s", {label});
            case "separator":
                return block.attrs && block.attrs.string
                    ? _t("Separator %(label)s", {label: block.attrs.string})
                    : _t("Separator");
            case "container":
                return own
                    ? _t("Container %(tag)s « %(label)s »", {tag, label})
                    : _t("Container %(tag)s", {tag});
        }
        if (block.tag === "chatter") {
            return _t("Chatter: messages, followers and activities");
        }
        return own ? _t("Element %(tag)s « %(label)s »", {tag, label}) : _t("Element %(tag)s", {tag});
    }

    /** A group of groups lays its groups out side by side, as Odoo does. */
    get isRow() {
        const children = this.block.children || [];
        return this.block.tag === "group" && children.length > 0 && children.every((child) => child.tag === "group");
    }

    get showHooks() {
        return Boolean(this.block.drop) && !this.isRow;
    }

    get parentTag() {
        return (this.props.parent && this.props.parent.tag) || "";
    }

    /**
     * How a field block draws: « line » for a field of a group of a form
     * (gutter, label, value), « bare » for another node of a form (its
     * value only), « column » for a column of a list (its header, a cell
     * under it), « chip » for the others (a card, a search view, an axis).
     */
    get layout() {
        const kind = this.block.kind;
        if (this.props.viewType === "form") {
            return kind === "field" && this.parentTag === "group" ? "line" : "bare";
        }
        return this.props.viewType === "list" && kind === "field" ? "column" : "chip";
    }

    /** Whether the field is the title of a form: the field of an <h1>. */
    get isTitle() {
        return ["h1", "h2"].includes(this.parentTag);
    }

    /** Whether the value placeholder looks like an empty checkbox. */
    get isBoolean() {
        return this.field.type === "boolean";
    }

    /**
     * The value of the field on the sample record of a form, as its cell
     * shows it: {kind: « boolean », checked, text}, {kind: « count »,
     * count, text} for an x2many, else {kind: « text », text}, a date in
     * the format of the user. Null when the payload gives no value
     * (``sample_values``): the cell keeps its placeholder.
     */
    get sample() {
        const values = this.editor.data.sample_values || {};
        const name = this.block.name;
        if (this.props.viewType !== "form" || this.block.kind !== "field" || !(name in values)) {
            return null;
        }
        const value = values[name];
        if (this.isBoolean) {
            return {kind: "boolean", checked: Boolean(value), text: value ? _t("Yes") : _t("No")};
        }
        if (value && typeof value === "object") {
            const count = value.count || 0;
            return {kind: "count", count, text: _t("%(count)s record(s)", {count})};
        }
        let text = String(value);
        if (this.field.type === "date") {
            text = formatDate(deserializeDate(value));
        } else if (this.field.type === "datetime") {
            text = formatDateTime(deserializeDateTime(value));
        }
        return {kind: "text", text};
    }

    /**
     * Whether a button draws as a flat chip: a button of a header or of the
     * box of the smart buttons of a form.
     */
    get isButtonChip() {
        const parent = this.props.parent;
        return (
            this.block.tag === "button" && Boolean(parent) && (parent.tag === "header" || parent.label === "button_box")
        );
    }

    /** Whether the children of the container line up: a header, the box of the smart buttons. */
    get isButtonRow() {
        return this.props.viewType === "form" && (this.block.tag === "header" || this.block.label === "button_box");
    }

    /**
     * The dot of the margin of the block: {dot, label}, « filled » for a
     * block the draft adds or changes, « ring » for one it hides; the label
     * joins the kinds of its changes (``changeKindLabel``). Null for a
     * block no change touches.
     */
    get marginDot() {
        return this.dotOf(this.block.change_kinds || []);
    }

    /** The margin dot of the change kinds ``kinds``, or null (``marginDot`` of studio_utils). */
    dotOf(kinds) {
        return marginDot(kinds);
    }

    /**
     * The margin dot of a notebook: its own changes and those of its pages
     * themselves (a new tab, a renamed one), which have no gutter of their
     * own.
     */
    get notebookDot() {
        const kinds = new Set(this.block.change_kinds || []);
        for (const page of this.pages) {
            for (const kind of page.change_kinds || []) {
                kinds.add(kind);
            }
        }
        return this.dotOf([...kinds]);
    }

    /**
     * The number of the changes under the page ``page`` of a notebook,
     * when its tab is not the one shown (``changeKeysInside``); 0 for the
     * tab shown, whose blocks carry their own dots.
     */
    tabCount(page) {
        return page === this.activePage ? 0 : changeKeysInside(page).length;
    }

    tabCountLabel(count) {
        return _t("%(count)s change(s) inside", {count});
    }

    /** Whether the arch the draft starts from always hides the block (``isBaseInvisible``). */
    get baseInvisible() {
        return this.props.viewType === "form" && isBaseInvisible(this.block);
    }

    /**
     * Whether the block draws as one muted line at the Simple level: a
     * block the draft hides, or the selection when the form never shows
     * it. An element the draft removes from a form or a list draws as a
     * removed line instead (``isGhost``).
     */
    get mutedLine() {
        return !this.detailed && !this.isGhost && (this.isHiddenChange || (this.baseInvisible && this.isSelected));
    }

    // ── an element the draft removes ────────────────────────────────────

    /** Whether the block is an element the draft removes (``isGhost``). */
    get isGhost() {
        return isGhost(this.block, this.props.viewType);
    }

    /**
     * Whether the removed line shows its row (struck label, Restore): at
     * the Detailed level always, at the Simple level once « show » opens
     * it.
     */
    get ghostOpen() {
        return this.detailed || this.ghostState.open;
    }

    /** The texts of the removed line and of its buttons. */
    get ghostText() {
        const label = this.titleLabel;
        return {
            removed: _t("removed"),
            show: _t("show"),
            pick: this.ghostOpen
                ? _t("%(label)s removed from the view", {label})
                : _t("%(label)s removed from the view, show the line", {label}),
            fold: _t("Fold the line %(label)s", {label}),
        };
    }

    /**
     * The value of the sample record a removed form line shows struck, or
     * "": a text or a date as the line would show it.
     */
    get ghostValue() {
        const sample = this.layout === "line" ? this.sample : null;
        return sample && sample.kind === "text" ? sample.text : "";
    }

    /**
     * A click on the removed line, or Enter or Space on its button: a
     * folded line opens and takes the selection; an open one selects as
     * any block does.
     */
    onGhostClick() {
        if (this.ghostOpen) {
            this.select();
            return;
        }
        this.ghostState.open = true;
        if (!this.isSelected) {
            this.editor.select(this.block.path);
        }
    }

    /** Fold the removed line back; its button keeps the focus. */
    foldGhost(ev) {
        this.ghostState.open = false;
        const holder = ev.currentTarget.closest("[data-path]");
        const pick = holder && holder.querySelector(":scope > .o_erplibre_studio_pick");
        if (pick) {
            pick.focus();
        }
    }

    /** Undo the change that removes the block (StudioEditor.restoreBlock). */
    restoreGhost() {
        return this.editor.restoreBlock(this.block);
    }

    /** The text of the muted line (mutedLine). */
    get mutedText() {
        return _t("%(label)s hidden", {label: this.titleLabel});
    }

    /** The label a block shows: a widget its title, another node its label or tag. */
    get titleLabel() {
        const block = this.block;
        if (block.kind === "widget") {
            return (block.attrs && block.attrs.title) || block.label;
        }
        if (block.label && block.label !== block.tag) {
            return block.label;
        }
        return tagLabel(block.tag);
    }

    /**
     * Whether the child ``child`` draws on the canvas: at the Simple level
     * a form does not draw a node its arch always hides (isBaseInvisible),
     * as the web client does, unless it holds the selection. The plan
     * lists it all the same.
     */
    isDrawn(child) {
        if (this.detailed || this.props.viewType !== "form" || !isBaseInvisible(child)) {
            return true;
        }
        const selected = this.editorState.selected;
        return Boolean(selected) && Boolean(findBlock(child, (b) => b.path === selected));
    }

    /** The children of the block the canvas draws (isDrawn). */
    get drawnChildren() {
        return (this.block.children || []).filter((child) => this.isDrawn(child));
    }

    /** The title of a group: its « string », as a form shows it. */
    get groupTitle() {
        const attrs = this.block.attrs || {};
        return this.block.tag === "group" ? attrs.string || "" : "";
    }

    /**
     * The technical caption of a container at the Detailed level:
     * « <group> label », the label left out when it is the tag or the
     * group title.
     */
    get techCaption() {
        const block = this.block;
        const own = block.label && block.label !== block.tag && block.label !== this.groupTitle;
        return own ? `<${block.tag}> ${block.label}` : `<${block.tag}>`;
    }

    /** Whether the block is a page without children: it shows a hint. */
    get isEmptyPage() {
        return this.block.tag === "page" && !(this.block.children || []).length;
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
        // The widget is a technical bit: the Detailed level shows it.
        if (attrs.widget && this.props.viewType !== "form" && this.detailed) {
            flags.push({key: "widget", label: attrs.widget});
        }
        if (attrs.groups) {
            flags.push({key: "groups", label: _t("restricted")});
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
        return this.changeTagsOf(this.block);
    }

    /** The tags of the draft changes of ``block`` (changeTags). */
    changeTagsOf(block) {
        const kinds = block.change_kinds || [];
        return CHANGE_TAGS.filter((kind) => kinds.includes(kind)).map((kind) => ({kind, label: changeKindLabel(kind)}));
    }

    /** The texts of the line of a collapsed chatter. */
    get chatterText() {
        return {title: _t("Chatter"), state: _t("collapsed")};
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

    /** Show the tab ``index`` and select its page ``page``. */
    selectPage(index, page) {
        this.editorState.pages[this.block.path] = index;
        if (page && this.editorState.selected !== page.path) {
            this.editor.select(page.path);
        }
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
 * axes of a pivot or of a graph, the lanes of a timeline, of a calendar or
 * of a map.
 * It renders from its props: a component renders again
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
        // The lane of a timeline or of a calendar the inspector shows
        // (VIEW_LANES), or null.
        lane: {type: [String, {value: null}], optional: true},
        // The layer of a GeoEngine view the inspector shows: its id, « new »,
        // or null.
        geoLayer: {type: [Number, String, {value: null}], optional: true},
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

    /**
     * The layers of a GeoEngine view the project adds, as the canvas lists
     * them: [{id, kind, name, description}].
     */
    get geoLayers() {
        const added = (this.data.view && this.data.view.added) || {};
        const representations = {basic: _t("drawn as is"), colored: _t("colored by value")};
        return (added.layers || []).map((layer) => {
            let description = _t("Background");
            if (layer.kind === "vector") {
                const field = this.fieldInfo(layer.geo_field).string || layer.geo_field;
                description = _t("%(field)s (%(name)s), %(representation)s", {
                    field,
                    name: layer.geo_field,
                    representation: representations[layer.geo_repr] || layer.geo_repr,
                });
            }
            return {
                id: layer.id,
                kind: layer.kind,
                name: layer.name,
                description,
                selected: this.props.geoLayer === layer.id,
            };
        });
    }

    /**
     * Whether the GeoEngine view is one the project adds: the layers of
     * another view are records of base_geoengine the payload does not hold.
     */
    get geoLayersAdded() {
        return Boolean(this.data.view && this.data.view.added);
    }

    /** Whether the project can edit the layers: one holds the view. */
    get geoLayersEditable() {
        return Boolean(this.props.project && this.data.view && this.data.view.added);
    }

    /** Whether the map of the GeoEngine view waits for Apply. */
    get geoMapPending() {
        const added = this.data.view && this.data.view.added;
        return Boolean(added && !added.applied);
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
     * The lanes ``defs`` of the canvas (VIEW_LANES): [{key, label,
     * accepts, glyph, zone, drop, over, refused, selected, changed, chips,
     * empty, classes}]. A chip is a value of the lane: a field of an
     * attribute (removable unless the view needs it), a color rule
     * (removable when the editor can write the others again). A field of
     * the palette drops on the lanes of ``fieldLanes``. ``classes`` names
     * the lane and its flags after ``prefix``, the view type by default
     * (« o_erplibre_studio_calendar_lane_selected »).
     */
    attributeLanes(defs, fieldLanes, prefix = `o_erplibre_studio_${this.viewType}`) {
        const attrs = (this.root && this.root.attrs) || {};
        const changed = this.changedAttributes;
        const required = (this.data.required_attributes || {})[this.root.tag] || [];
        const dragging = this.props.dragging;
        const rules = this.layout.colors || [];
        const writable = writableColorRules(rules);
        const viewType = this.viewType;
        return defs.map((lane) => {
            const zone = `${LANE_ZONE_PREFIX}${lane.key}`;
            const drop = fieldLanes.includes(lane.key) && Boolean(this.project);
            const laneName = laneLabel(lane.key, viewType);
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
                    classes: `${prefix}_chip`,
                }));
                empty = _t("Default color");
            } else if (fieldLanes.includes(lane.key)) {
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
                            classes: [`${prefix}_chip`, changed.has(attribute) && `${prefix}_chip_changed`]
                                .filter(Boolean)
                                .join(" "),
                            remove:
                                required.includes(attribute) || !this.project
                                    ? null
                                    : () => this.editor.setNodeAttribute(this.root, attribute, ""),
                            removeLabel: _t("Remove %(field)s from %(lane)s", {field: label, lane: laneName}),
                        };
                    });
                empty = _t("Drop a field here");
            }
            const state = {
                drop,
                over: this.activeHook === this.editor.hookKey(this.root.path, "lane", zone),
                refused: Boolean(drop && dragging && !this.editor.accepts(dragging, zone)),
                selected: this.props.lane === lane.key,
            };
            return {
                ...lane,
                ...state,
                zone,
                label: laneName,
                accepts: laneAccepts(lane.key, viewType),
                changed: lane.attributes.some((attribute) => changed.has(attribute)),
                chips,
                empty,
                classes: [`${prefix}_lane`]
                    .concat(Object.keys(state).filter((flag) => state[flag]).map((flag) => `${prefix}_lane_${flag}`))
                    .join(" "),
            };
        });
    }

    /** The lanes of the canvas of a timeline (attributeLanes). */
    get timelineLanes() {
        return this.attributeLanes(TIMELINE_LANES, FIELD_LANES_BY_TYPE.timeline);
    }

    /** The lanes of the canvas of a calendar (attributeLanes). */
    get calendarLanes() {
        return this.attributeLanes(CALENDAR_LANES, FIELD_LANES_BY_TYPE.calendar);
    }

    /** The lanes of the canvas of a map (attributeLanes). */
    get leafletLanes() {
        // The classes of the lanes of a timeline, which the map shares.
        return this.attributeLanes(LEAFLET_LANES, FIELD_LANES_BY_TYPE.leaflet_map, "o_erplibre_studio_timeline");
    }

    /** The field blocks of the popover of a calendar, in their order. */
    get popoverBlocks() {
        const byPath = (path) => findBlock(this.root, (b) => b.path === path);
        return (this.layout.popover || []).map(byPath).filter(Boolean);
    }

    /**
     * The scale of the view on opening: its « mode », else the default of
     * its type (DEFAULT_MODES), undefined for a calendar.
     */
    get currentMode() {
        return (this.root.attrs || {}).mode || DEFAULT_MODES[this.viewType];
    }

    /**
     * The scales of a timeline or of a calendar: [{value, label, pressed}],
     * from the choices of the kind of its « mode » (timeline_mode,
     * calendar_mode).
     */
    get modes() {
        const kind = `${this.viewType}_mode`;
        const current = this.currentMode;
        return ((this.data.choices || {})[kind] || []).map(([value, label]) => ({
            value,
            label: valueLabel(kind, value) || label,
            pressed: value === current,
        }));
    }

    /** The scales of a timeline (modes). */
    get timelineModes() {
        return this.modes;
    }

    setMode(value) {
        if (value !== this.currentMode) {
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
        return ["fields", "filters", "group_bys"].map((key) => ({key, label: columnLabel(key)}));
    }

    get pivotLaneList() {
        return ["row", "col", "measure"].map((key) => ({key, label: columnLabel(key)}));
    }

    // ── graph ───────────────────────────────────────────────────────────

    get graphLanes() {
        return graphLanes(this.data);
    }

    get graphLaneList() {
        return ["row", "measure"].map((key) => ({key, label: graphLaneLabel(key)}));
    }

    /** The chart type of the graph: its « type », a bar chart without one. */
    get graphType() {
        return (this.root.attrs || {}).type || "bar";
    }

    /** The chart types of a graph: [{value, label, pressed}]. */
    get graphTypes() {
        const current = this.graphType;
        return ((this.data.choices || {}).graph_type || []).map(([value, label]) => ({
            value,
            label: valueLabel("graph_type", value) || label,
            pressed: value === current,
        }));
    }

    setGraphType(value) {
        if (value !== this.graphType) {
            return this.editor.setNodeAttribute(this.root, "type", value);
        }
    }

    /**
     * The caption of the group-by at ``index`` of a graph: the first one
     * makes the X axis, or the slices of a pie; the next ones split it
     * into series.
     */
    graphRowCaption(index) {
        if (index) {
            return _t("Series");
        }
        return this.graphType === "pie" ? _t("Slices") : _t("X axis");
    }

    /**
     * The caption of the measure at ``index`` among ``count`` measures of
     * a graph, or "": the graph draws the last one, the others are offered
     * in its Measures menu.
     */
    graphMeasureCaption(index, count) {
        return count > 1 && index === count - 1 ? _t("Drawn") : "";
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
