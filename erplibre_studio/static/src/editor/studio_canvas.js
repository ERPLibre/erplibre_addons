/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {deserializeDate, deserializeDateTime, formatDate, formatDateTime} from "@web/core/l10n/dates";
import {X2MANY_TYPES} from "./studio_relations";
import {StudioInsertList} from "./studio_insert";
import {outlineCount, outlineLabel, tagLabel} from "./studio_outline";
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
    TAG_WIDGETS,
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
    isFocusContext,
    graphLanes,
    hiddenSentence,
    isBaseInvisible,
    isGhost,
    isTrue,
    marginDot,
    pageLabel,
    pivotLanes,
    searchColumns,
    searchEndHook,
    shownWhen,
    valueLabel,
} from "./studio_utils";

/**
 * One node of the edited arch: a container with its children and the drop
 * hooks between them, a field, or another element. It reads the selection,
 * the hook a drop goes to, the drop scope that holds it and the page
 * shown of a notebook from the state of the editor, through a
 * ``useState`` of its own: a block renders again when what it reads of
 * that state changes, without the props of the blocks above it changing.
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
 * At rest a field of a form draws as its widget would: an image as a
 * picture box, a radio as its options, a boolean as a checkbox, tags as
 * tags, another value on one line (``look``); a field outside a group shows
 * its value, else its placeholder. A node the real form hides on the
 * sample record (``sampleHidden``) is not drawn at the Simple level, and is
 * one folded line « shown when … » at the Detailed level.
 *
 * An element the draft hides from a form or a list (``isGhost``) is one
 * muted line at its place, « label hidden — show », that neither moves
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
        // Whether the hidden line of an element the draft hides shows
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

    /**
     * Whether the hooks of the block hold a « + » (rule 5, insert without
     * dragging): a container of a form the editor inserts in
     * (``insertsIn``), while no drag runs, outside the preview, with a
     * project.
     */
    get canInsert() {
        const state = this.editorState;
        return (
            !state.dragging &&
            !state.preview &&
            !state.panel &&
            Boolean(state.data && state.data.project) &&
            this.editor.insertsIn(this.block)
        );
    }

    /**
     * The key (``hookKey``) of the hook right after the selected block
     * when the block holds it (``hookAfter``): its « + » is a tab stop, so
     * that Tab from a selected block reaches it. Null otherwise.
     */
    get afterSelectedKey() {
        const selected = this.editorState.selected;
        if (!selected || !(this.block.children || []).some((child) => child.path === selected)) {
            return null;
        }
        const hook = this.editor.hookAfter(selected);
        return hook ? this.editor.hookKey(hook.target, hook.position) : null;
    }

    /**
     * The key of the hook of the block whose « + » is a tab stop: the one
     * after the selected child (``afterSelectedKey``), else the hook
     * « inside » of a block that draws no child, its only hook, so that
     * Tab reaches the « + » of an empty tab or group.
     */
    get tabStopKey() {
        const key = this.afterSelectedKey;
        if (key || this.drawnChildren.length) {
            return key;
        }
        return this.editor.hookKey(this.block.path, "inside");
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
            return {kind: "count", count, names: value.names || [], text: _t("%(count)s record(s)", {count})};
        }
        let text = String(value);
        if (this.field.type === "date") {
            text = formatDate(deserializeDate(value));
        } else if (this.field.type === "datetime") {
            text = formatDateTime(deserializeDateTime(value));
        }
        return {kind: "text", text};
    }

    /** The widget of the node, "" without one. */
    get widget() {
        return (this.block.attrs && this.block.attrs.widget) || "";
    }

    /**
     * How the value of a field of a form draws at rest, as its widget
     * draws it in the real form (rule 1), or null for another block or an
     * x2many drawn as a sub-list (``subList``):
     * {kind: « image »}: a picture box;
     * {kind: « radio », options: [{key, label, checked}]}: the options of a
     *   selection, the value of the sample record checked;
     * {kind: « check », checked, text}: a checkbox, empty without value;
     * {kind: « tags », tags, more}: the names of the records of an x2many
     *   of a tag widget, ``more`` the count of those left out;
     * {kind: « text », text, line}: the value of the sample record, on one
     *   line cut by an ellipsis when ``line`` (any type but a text or an
     *   html, as an input shows it);
     * {kind: « empty », text}: no value, ``text`` the placeholder of the
     *   node, "" without one.
     */
    get look() {
        if (this.props.viewType !== "form" || this.block.kind !== "field" || this.subList) {
            return null;
        }
        const field = this.field;
        const widget = this.widget;
        const sample = this.sample;
        if (widget === "image" || (field.type === "binary" && widget.startsWith("image"))) {
            return {kind: "image"};
        }
        if (widget === "radio" && field.type === "selection" && (field.selection || []).length) {
            // The key of the value when the payload gives it (sample_record),
            // else its label.
            const record = this.editor.data.sample_record || {};
            const name = this.block.name;
            const text = sample && sample.kind === "text" ? sample.text : null;
            return {
                kind: "radio",
                options: field.selection.map(([key, label]) => ({
                    key,
                    label,
                    checked: name in record ? key === record[name] : label === text,
                })),
            };
        }
        if (this.isBoolean) {
            return {kind: "check", checked: sample ? sample.checked : null, text: sample ? sample.text : ""};
        }
        if (sample && sample.kind === "count") {
            const tags = sample.names || [];
            return tags.length || sample.count
                ? {kind: "tags", tags, more: Math.max(0, sample.count - tags.length)}
                : {kind: "empty", text: this.placeholder};
        }
        if (sample) {
            return {kind: "text", text: sample.text, line: !this.isTitle && !["text", "html"].includes(field.type)};
        }
        return {kind: "empty", text: this.placeholder};
    }

    /** The placeholder of the node, "" without one. */
    get placeholder() {
        return (this.block.attrs && this.block.attrs.placeholder) || "";
    }

    /** The text of the count of the records left out of the tags, "+3". */
    moreTags(count) {
        return _t("+%(count)s", {count});
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
     * Whether the real form hides the block on the sample record: its
     * « invisible » condition holds on it (StudioEditor.hiddenOnSample).
     */
    get sampleHidden() {
        // A page is its tab: the notebook leaves the tab out instead.
        return this.props.viewType === "form" && this.block.tag !== "page" && this.editor.hiddenOnSample(this.block);
    }

    /** Whether the selection is a block under the block, itself left out. */
    get selectionInside() {
        const selected = this.editorState.selected;
        return (
            Boolean(selected) &&
            selected !== this.block.path &&
            Boolean(findBlock(this.block, (b) => b.path === selected))
        );
    }

    /**
     * Whether the block draws as one muted line. At the Simple level: a
     * block the draft hides, or the selection when the form does not show
     * it (always, or on the sample record). At the Detailed level: a block
     * the form hides on the sample record, folded with its condition
     * (``shownWhenText``) while the selection is not under it. In a form or
     * a list, an element the draft hides draws as its hidden line instead
     * (``isGhost``).
     */
    get mutedLine() {
        if (this.isGhost) {
            return false;
        }
        if (this.detailed) {
            return this.sampleHidden && !this.selectionInside;
        }
        return this.isHiddenChange || ((this.baseInvisible || this.sampleHidden) && this.isSelected);
    }

    /**
     * The condition of the folded line of a block the form hides on the
     * sample record, at the Detailed level: « shown when … » (``shownWhen``
     * of its « invisible »); "" otherwise.
     */
    get shownWhenText() {
        if (!this.detailed || !this.sampleHidden) {
            return "";
        }
        return _t("shown when %(condition)s", {condition: shownWhen(this.block.attrs.invisible)});
    }

    // ── an element the draft hides ────────────────────────────────────

    /** Whether the block is an element the draft hides (``isGhost``). */
    get isGhost() {
        return isGhost(this.block, this.props.viewType);
    }

    /**
     * Whether the hidden line shows its row (struck label, Restore): at
     * the Detailed level always, at the Simple level once « show » opens
     * it.
     */
    get ghostOpen() {
        return this.detailed || this.ghostState.open;
    }

    /**
     * The texts of the line of a hidden element and of its buttons: the
     * draft hides it (the node stays in the arch), so they say « hidden »
     * (``hiddenSentence``), never « removed ».
     */
    get ghostText() {
        const label = this.titleLabel;
        const hidden = hiddenSentence(label, this.props.viewType);
        return {
            hidden: _t("hidden"),
            show: _t("show"),
            pick: this.ghostOpen ? hidden : _t("%(hidden)s, show the line", {hidden}),
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
     * A click on the hidden line, or Enter or Space on its button: a
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

    /** Fold the hidden line back; its button keeps the focus. */
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

    /**
     * The label of the muted line: at the Detailed level the technical
     * caption of a node other than a field (``techCaption``), else its
     * label (``titleLabel``).
     */
    get mutedLabel() {
        return this.detailed && this.block.kind !== "field" ? this.techCaption : this.titleLabel;
    }

    /** The accessible name of the button of the muted line (mutedLine). */
    get mutedText() {
        const condition = this.shownWhenText;
        if (condition) {
            return _t("%(label)s, %(condition)s", {label: this.titleLabel, condition});
        }
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
     * a form does not draw a node its arch always hides (isBaseInvisible)
     * nor one it hides on the sample record (hiddenOnSample), as the web
     * client does, unless it holds the selection. The plan lists it all
     * the same. StudioEditor.isDrawnChild decides the same; this one reads
     * the state through the block, which renders again when it changes.
     */
    isDrawn(child) {
        if (this.detailed || this.props.viewType !== "form") {
            return true;
        }
        if (!isBaseInvisible(child) && !this.editor.hiddenOnSample(child)) {
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

    /**
     * Whether the block is the box of the smart buttons of a form with no
     * button drawn, at the Simple level and outside the selection: it
     * takes no height.
     */
    get isEmptyButtonBox() {
        return (
            this.props.viewType === "form" &&
            this.block.label === "button_box" &&
            !this.detailed &&
            !this.isSelected &&
            !this.selectionInside &&
            !this.drawnChildren.length
        );
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

    /**
     * The page whose tab shows: the one of ``state.pages``, else the first
     * tab drawn (``isDrawn``), as the form opens on its first visible tab.
     */
    get activePage() {
        const pages = this.pages;
        const page = pages[this.editorState.pages[this.block.path] || 0];
        if (page && this.isDrawn(page)) {
            return page;
        }
        return pages.find((p) => this.isDrawn(p)) || page || pages[0];
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
     * The sub-list an x2many field shows in a form: {comodel}, or null; an
     * x2many of a tag widget (TAG_WIDGETS) draws as tags instead
     * (``look``). The editor does not descend into it: it is part of the
     * field. It reads « label · N record(s) », the comodel at the Detailed
     * level only.
     */
    get subList() {
        if (this.props.viewType !== "form" || this.block.kind !== "field") {
            return null;
        }
        const field = this.field;
        if (!X2MANY_TYPES.includes(field.type) || !field.relation || TAG_WIDGETS.includes(this.widget)) {
            return null;
        }
        return {comodel: field.relation};
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

    /** The hook a drop goes to, as ``hookKey`` names it. */
    get activeHook() {
        return this.editorState.hook;
    }

    /** The keys of the hooks next to the hook a drop goes to (``nearKeys``). */
    get nearHooks() {
        return this.editorState.hookNear || [];
    }

    /**
     * The key of the hook after which the slot of the palette shows, while
     * the focus is on a block of a form (``StudioEditor.focusSlotKey``);
     * null otherwise.
     */
    get focusSlotKey() {
        const {focus, dragging} = this.editorState;
        if (!focus.on || !focus.path || dragging || this.props.viewType !== "form") {
            return null;
        }
        return this.editor.focusSlotKey;
    }

    /** The text of that slot (``StudioEditor.focusSlotText``). */
    get focusSlotText() {
        return this.editor.focusSlotText;
    }

    /**
     * The key of the drop scope under the pointer during a drag: the
     * children of the container whose path it is, or the tabs of a
     * notebook (``pagesScope``).
     */
    get dropScope() {
        return this.editorState.dropScope;
    }

    /** The key of the drop scope of the tabs of a notebook. */
    get pagesScope() {
        return `pages:${this.block.path}`;
    }

    /**
     * The « Focus » button of the title line of ``block`` when it is a
     * focus block of a form (``focusBlocks``): {path, label, title}; null
     * while the focus is on, during a drag, in the preview, or for
     * another block.
     */
    focusButtonFor(block) {
        const state = this.editorState;
        if (!block || this.props.viewType !== "form" || state.focus.on || state.dragging || state.preview) {
            return null;
        }
        const entry = this.editor.focusEntryAt(block.path);
        return entry
            ? {
                  path: entry.path,
                  label: this.editor.focusLabel(entry.label),
                  title: _t("Isolate this block to work in it"),
              }
            : null;
    }

    /** The « Focus » button of the title line of the block (``focusButtonFor``). */
    get focusButton() {
        return this.focusButtonFor(this.block);
    }

    /** Put the focus on the block at ``path``; its first button takes the keyboard focus. */
    enterFocus(path) {
        this.editor.enterFocus(path, {focus: true});
    }
}
StudioBlock.components = {StudioBlock, StudioInsertList};

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
    static components = {StudioBlock, StudioFrise, StudioInsertList};
    static props = {
        editor: Object,
        // The payload of the editor (get_editor_data).
        data: Object,
        viewType: String,
        project: {type: [Object, {value: null}], optional: true},
        busy: {type: Boolean, optional: true},
        // The item being dragged, the hook a drop goes to, and the key of
        // the drop scope that holds that hook (a lane, the loaded fields).
        dragging: {type: [Object, {value: null}], optional: true},
        hook: {type: [String, {value: null}], optional: true},
        dropScope: {type: [String, {value: null}], optional: true},
        // The keys of the hooks next to the hook a drop goes to.
        hookNear: {type: Array, optional: true},
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
        // The path of the block of a form in focus (StudioEditor.focusEntry),
        // or null when the focus is off.
        focus: {type: [String, {value: null}], optional: true},
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

    get nearHooks() {
        return this.props.hookNear || [];
    }

    // The lanes of a canvas draw no slot of the palette.
    get focusSlotKey() {
        return null;
    }

    get dropScope() {
        return this.props.dropScope;
    }

    fieldInfo(name) {
        return (this.data.fields || {})[name] || {};
    }

    // ── focus on a block of a form ──────────────────────────────────────

    /**
     * The rows of a form with the focus on a block, in the order of the
     * arch, or null when the focus is off: {kind, key, …}.
     * « open »: the block in focus (``entry``), drawn as the full form draws
     * it, under a title line when nothing else names it (``title``).
     * « folded »: another focus block, one line that puts the focus on it:
     * {label, meta, changes, aria}. « context »: a page that holds groups
     * only, above their rows. « static »: a summary of one line, {label,
     * meta}: the header of the form with the top of its sheet (« Header »),
     * the smart buttons, the chatter, another node of the sheet. The tabs
     * of a notebook are not drawn. ``indent`` marks the groups of a page.
     */
    get focusRows() {
        const editor = this.editor;
        const focused = this.props.focus ? editor.focusEntry : null;
        if (!focused || this.viewType !== "form") {
            return null;
        }
        const viewType = this.viewType;
        const entries = new Map(editor.focusEntries.map((entry) => [entry.path, entry]));
        const rows = [];
        let header = false;
        let seen = false;
        const addHeader = () => {
            if (!header) {
                header = true;
                rows.push({kind: "static", key: "header", label: _t("Header"), meta: ""});
            }
        };
        const blockRow = (entry, indent) => {
            if (entry.path === focused.path) {
                const own = entry.kind === "group" && (entry.block.attrs || {}).string;
                rows.push({kind: "open", key: entry.path, entry, indent, title: !own});
                return;
            }
            const keys = new Set([...(entry.block.changes || []), ...changeKeysInside(entry.block)]);
            const label = entry.kind === "page" ? _t("Tab %(label)s", {label: entry.label}) : entry.label;
            const meta = _t("%(count)s field(s)", {count: outlineCount(entry.block, viewType)});
            const changes = keys.size ? _t("%(count)s change(s)", {count: keys.size}) : "";
            rows.push({
                kind: "folded",
                key: entry.path,
                entry,
                indent,
                label,
                meta,
                changes,
                aria: [editor.focusLabel(label), meta, changes].filter(Boolean).join(", "),
            });
        };
        const visit = (container) => {
            for (const child of container.children || []) {
                const entry = entries.get(child.path);
                if (entry) {
                    seen = true;
                    blockRow(entry, false);
                } else if (child.tag === "sheet") {
                    visit(child);
                } else if (child.tag === "notebook") {
                    seen = true;
                    for (const page of (child.children || []).filter((b) => b.tag === "page")) {
                        if (entries.has(page.path)) {
                            blockRow(entries.get(page.path), false);
                        } else if (isFocusContext(page)) {
                            const label = _t("Tab %(label)s", {label: pageLabel(page)});
                            rows.push({kind: "context", key: page.path, label});
                            for (const group of page.children) {
                                if (entries.has(group.path)) {
                                    blockRow(entries.get(group.path), true);
                                }
                            }
                        }
                    }
                } else if (child.tag === "header") {
                    addHeader();
                } else if (child.tag === "chatter") {
                    rows.push({kind: "static", key: child.path, label: _t("Chatter"), meta: _t("collapsed")});
                } else if (child.label === "button_box") {
                    const count = (child.children || []).filter((b) => !isGhost(b, viewType)).length;
                    rows.push({
                        kind: "static",
                        key: child.path,
                        label: _t("Smart buttons"),
                        meta: _t("%(count)s button(s)", {count}),
                    });
                } else if (!seen) {
                    // The top of the sheet before its first block: its title.
                    addHeader();
                } else if (editor.isDrawnChild(child)) {
                    const count = outlineCount(child, viewType);
                    rows.push({
                        kind: "static",
                        key: child.path,
                        label: outlineLabel(child),
                        meta: count ? _t("%(count)s field(s)", {count}) : "",
                    });
                }
            }
        };
        visit(this.root);
        return rows;
    }

    /** Put the focus on the block at ``path`` (a folded line); its first button takes the keyboard focus. */
    enterFocus(path) {
        this.editor.enterFocus(path, {focus: true});
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
