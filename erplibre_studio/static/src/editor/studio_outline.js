/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {
    CHANGE_TAGS,
    allBlocks,
    canDragBlock,
    changeKindLabel,
    searchText,
    typeGlyph,
} from "./studio_utils";

// The glyph of a container, by its tag.
const TAG_GLYPHS = {sheet: "▭", group: "▦", notebook: "⧉", page: "▤"};
// The glyph of a leaf that is not a field, by its kind.
const KIND_GLYPHS = {filter: "▽", group_by: "⊟", separator: "—", widget: "★"};

/** Whether ``block`` is a container of the outline: a block with children. */
export function isOutlineContainer(block) {
    return Boolean(block.children && block.children.length);
}

/** The label of a tag of a container, shown for one without a label of its own. */
export function tagLabel(tag) {
    return (
        {
            sheet: _t("Sheet"),
            group: _t("Group"),
            notebook: _t("Tabs"),
            page: _t("Tab"),
            header: _t("Header"),
            footer: _t("Footer"),
            templates: _t("Templates"),
        }[tag] || tag
    );
}

/** The text a row of the outline shows for ``block``. */
export function outlineLabel(block) {
    if (block.kind === "separator") {
        return _t("Separator");
    }
    if (block.kind === "widget") {
        return (block.attrs && block.attrs.title) || block.label || block.name;
    }
    if (block.kind === "field" || !block.children) {
        return block.label || block.name || block.tag;
    }
    const own = block.label && block.label !== block.tag;
    if (block.tag === "group" && own) {
        return _t("Group « %(label)s »", {label: block.label});
    }
    return own ? block.label : tagLabel(block.tag);
}

/**
 * The glyph of ``block``: the glyph of its field type (``fields``: the
 * fields of the payload), of its container tag, or of its kind of leaf.
 */
export function blockGlyph(block, fields = {}) {
    if (block.kind === "field") {
        return typeGlyph((fields[block.name] || {}).type);
    }
    if (isOutlineContainer(block)) {
        return TAG_GLYPHS[block.tag] || "◻";
    }
    return KIND_GLYPHS[block.kind] || "◦";
}

/** How many fields ``block`` holds, at any depth; a notebook counts its pages. */
export function outlineCount(block) {
    if (block.tag === "notebook") {
        return (block.children || []).filter((child) => child.tag === "page").length;
    }
    return allBlocks(block).filter((b) => b !== block && b.kind === "field").length;
}

/**
 * The rows of the outline of the tree ``root``, the view itself left out:
 * [{block, depth, context, open}], depth first. ``filter`` keeps the blocks
 * whose label or technical name holds it, accents and case aside;
 * ``changedOnly`` keeps the blocks a draft change touches (``changed``).
 * While one of them filters, a kept block shows with the containers above
 * it, marked ``context`` when they do not match themselves, and every
 * container shows open; a container the text matches keeps all its blocks.
 * Else a container shows open unless ``collapsed`` (path -> true) closes it.
 * Answer {rows, matches, total}: the rows, how many blocks match, how many
 * blocks the tree has.
 */
export function outlineRows(root, {filter = "", changedOnly = false, collapsed = {}} = {}) {
    const query = searchText(filter.trim());
    const filtering = Boolean(query) || changedOnly;
    const textHit = (block) => !query || searchText(`${outlineLabel(block)} ${block.name || ""}`).includes(query);
    const selfMatch = (block, force) => (changedOnly && !block.changed ? false : force || textHit(block));
    // A container the text matches keeps the blocks under it.
    const forceOf = (block, force) =>
        force || (isOutlineContainer(block) && Boolean(query) && !changedOnly && textHit(block));
    const hasMatch = (block, force) =>
        selfMatch(block, force) || (block.children || []).some((child) => hasMatch(child, forceOf(block, force)));
    const rows = [];
    let matches = 0;
    const walk = (block, depth, force) => {
        if (filtering && !hasMatch(block, force)) {
            return;
        }
        const self = selfMatch(block, force);
        if (filtering && self) {
            matches += 1;
        }
        const open = filtering || !collapsed[block.path];
        rows.push({block, depth, context: filtering && !self, open});
        if (isOutlineContainer(block) && open) {
            for (const child of block.children) {
                walk(child, depth + 1, forceOf(block, force));
            }
        }
    };
    for (const child of (root && root.children) || []) {
        walk(child, 0, false);
    }
    const total = allBlocks(root).length - (root ? 1 : 0);
    return {rows, matches, total};
}

/**
 * The plan of the view: the tree of its blocks, foldable, filtered by a
 * text or by the changes of the draft. A click selects the block on the
 * canvas, and the inspector shows it; a drag moves it as a drag on the
 * canvas does, through the editor ``editor``. ``outline`` is the state the
 * editor keeps across its panels: {filter, changedOnly, collapsed}.
 *
 * The tree is one tab stop (a roving tabindex on its rows): Up and Down
 * move between the rows shown, Home and End to the first and the last,
 * Right unfolds a container then enters it, Left folds it or goes up to
 * its container, Enter and Space select the row's block. Alt+Up and
 * Alt+Down move the row's block as they do on the canvas, Delete removes
 * it (``moveByKeyboard``, ``removeByKeyboard`` of the editor).
 */
export class StudioOutline extends Component {
    static template = "erplibre_studio.Outline";
    static props = {
        editor: Object,
        // The payload of the editor (get_editor_data).
        data: Object,
        viewType: String,
        // The path of the selected block.
        selected: {type: [String, {value: null}], optional: true},
        outline: Object,
    };

    setup() {
        // The path of the row that holds the tab stop of the tree.
        this.state = useState({focus: null});
    }

    get editor() {
        return this.props.editor;
    }

    get outline() {
        return this.props.outline;
    }

    get root() {
        return this.props.data.blocks;
    }

    get result() {
        return outlineRows(this.root, this.outline);
    }

    get filtering() {
        return Boolean(this.outline.filter.trim()) || this.outline.changedOnly;
    }

    /** How many blocks a draft change touches. */
    get changedCount() {
        return allBlocks(this.root).filter((b) => b.changed).length;
    }

    countLabel(result) {
        if (this.filtering) {
            return _t("%(count)s result(s)", {count: result.matches});
        }
        return _t("%(count)s item(s)", {count: result.total});
    }

    get emptyLabel() {
        const filter = this.outline.filter.trim();
        if (filter) {
            return _t("No element matches « %(filter)s ».", {filter});
        }
        return _t("No change of the draft in this view.");
    }

    get treeLabel() {
        return _t("Structure of the view");
    }

    label(block) {
        return outlineLabel(block);
    }

    isContainer(block) {
        return isOutlineContainer(block);
    }

    count(block) {
        return outlineCount(block);
    }

    glyph(block) {
        return blockGlyph(block, this.props.data.fields || {});
    }

    /** The label of the change of ``block`` the row shows: the first tag, else the first kind. */
    changeLabel(block) {
        const kinds = block.change_kinds || [];
        const kind = CHANGE_TAGS.find((k) => kinds.includes(k)) || kinds[0];
        return kind ? changeKindLabel(kind) : "";
    }

    toggleLabel(row) {
        const label = this.label(row.block);
        return row.open ? _t("Collapse %(label)s", {label}) : _t("Expand %(label)s", {label});
    }

    holdsLabel() {
        return _t("Holds changes of the draft");
    }

    canDrag(block) {
        return canDragBlock(block, this.props.viewType);
    }

    toggle(row) {
        if (this.filtering) {
            return;
        }
        this.outline.collapsed[row.block.path] = row.open;
    }

    showChanged(changedOnly) {
        this.outline.changedOnly = changedOnly;
    }

    clearFilter() {
        this.outline.filter = "";
    }

    pick(block) {
        this.editor.reveal(block.path);
    }

    /**
     * The path of the row of ``rows`` that takes the tab stop: the row
     * last focused, else the selected one, else the first.
     */
    activePath(rows) {
        const paths = rows.map((row) => row.block.path);
        return [this.state.focus, this.props.selected].find((path) => path && paths.includes(path)) || paths[0];
    }

    /** The keys of the tree on the row ``row`` of ``rows`` (see the class). */
    onTreeKey(ev, row, rows) {
        if (ev.target !== ev.currentTarget || ev.ctrlKey || ev.metaKey) {
            return;
        }
        if (!ev.shiftKey && ev.altKey && ["ArrowUp", "ArrowDown"].includes(ev.key)) {
            ev.preventDefault();
            if (!ev.repeat) {
                this.moveRow(row, ev.key === "ArrowUp" ? -1 : 1);
            }
            return;
        }
        if (!ev.shiftKey && !ev.altKey && ev.key === "Delete") {
            ev.preventDefault();
            this.removeRow(row, rows);
            return;
        }
        if (ev.altKey) {
            return;
        }
        const index = rows.indexOf(row);
        const container = this.isContainer(row.block);
        let next = null;
        switch (ev.key) {
            case "ArrowDown":
                next = index + 1;
                break;
            case "ArrowUp":
                next = index - 1;
                break;
            case "Home":
                next = 0;
                break;
            case "End":
                next = rows.length - 1;
                break;
            case "ArrowRight":
                if (!container) {
                    return;
                }
                if (row.open) {
                    next = index + 1;
                } else {
                    this.toggle(row);
                }
                break;
            case "ArrowLeft":
                if (container && row.open && !this.filtering) {
                    this.toggle(row);
                } else {
                    next = rows.findLastIndex((other, i) => i < index && other.depth < row.depth);
                }
                break;
            case "Enter":
            case " ":
                this.pick(row.block);
                break;
            default:
                return;
        }
        ev.preventDefault();
        if (next !== null && next >= 0 && next < rows.length) {
            this.focusRow(ev.currentTarget.parentElement, rows[next].block.path);
        }
    }

    /** Give the tab stop and the focus to the row of ``path`` in ``tree``. */
    focusRow(tree, path) {
        this.state.focus = path;
        const item = [...tree.children].find((el) => el.dataset.path === path);
        if (item) {
            item.focus();
        }
    }

    /** The tree of the plan on screen, or null. */
    get treeElement() {
        return document.querySelector(".o_erplibre_studio_outline_tree");
    }

    /**
     * Move the block of ``row`` one place up (``direction`` -1) or down
     * (+1); its row keeps the focus, at the path the move gives it.
     */
    async moveRow(row, direction) {
        const path = await this.editor.moveByKeyboard(row.block.path, direction, {focus: false});
        if (path) {
            this.state.focus = path;
            this.editor.afterRender(() => this.treeElement && this.focusRow(this.treeElement, path));
        }
    }

    /**
     * Remove the block of ``row`` (of ``rows``); once it left, directly or
     * after the dialog of ``removeSelected``, the row that takes its place
     * takes the focus (the next one, else the new last one).
     */
    async removeRow(row, rows) {
        const index = rows.indexOf(row);
        await this.editor.removeByKeyboard(row.block.path, {
            focus: false,
            onRemoved: () =>
                this.editor.afterRender(() => {
                    const tree = this.treeElement;
                    const items = tree ? [...tree.children] : [];
                    const item = items[Math.min(index, items.length - 1)];
                    if (item) {
                        this.focusRow(tree, item.dataset.path);
                    }
                }),
        });
    }

    startDrag(ev, block) {
        this.editor.startDrag(ev, {kind: "node", path: block.path, name: block.name});
    }

    endDrag() {
        this.editor.endDrag();
    }
}
