import {Component, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";

import {LinkupCategoryIcon} from "./linkup_category_icon";
import {LinkupGuideButton} from "./linkup_guide";

/**
 * Move the focus between the buttons of a toolbar: the arrow keys go to the
 * next or the previous button, wrapping around, `Home` and `End` to the
 * ends. Any other key, or a key pressed outside the buttons, is left alone.
 *
 * @param {KeyboardEvent} ev
 * @param {HTMLElement} root the element holding the buttons
 */
export function linkupToolbarKeydown(ev, root) {
    const buttons = [...root.querySelectorAll("button:not([disabled])")];
    const index = buttons.indexOf(document.activeElement);
    if (index === -1) {
        return;
    }
    let next = null;
    switch (ev.key) {
        case "ArrowRight":
        case "ArrowDown":
            next = buttons[(index + 1) % buttons.length];
            break;
        case "ArrowLeft":
        case "ArrowUp":
            next = buttons[(index - 1 + buttons.length) % buttons.length];
            break;
        case "Home":
            next = buttons[0];
            break;
        case "End":
            next = buttons.at(-1);
            break;
    }
    if (next) {
        ev.preventDefault();
        ev.stopPropagation();
        next.focus();
    }
}

/**
 * The Help bar: the categories of the reduced bar, and a toggle that
 * shows all the active categories in the order of the full band.
 *
 * It is a toolbar: `Tab` reaches it, the arrow keys move between its
 * buttons, `Home` and `End` reach the ends, `Enter` and `Space` choose.
 * Its last button, "?", turns the guide mode on (`linkup_guide.js`), in
 * which each category explains itself instead of opening a card.
 *
 * @typedef {Object} Props
 * @property {import("models").LinkupCategory[]} barCategories
 * @property {import("models").LinkupCategory[]} allCategories
 * @property {import("models").LinkupCategory} [selected]
 * @property {(category: import("models").LinkupCategory) => void} onSelect
 * @property {string} label
 * @extends {Component<Props, Env>}
 */
export class LinkupHelpBar extends Component {
    static template = "mail_linkup_reflet.LinkupHelpBar";
    static components = {LinkupCategoryIcon, LinkupGuideButton};
    static props = ["barCategories", "allCategories", "selected?", "onSelect", "label"];

    setup() {
        super.setup();
        this.root = useRef("root");
        this.state = useState({expanded: false});
    }

    get categories() {
        if (this.state.expanded) {
            return this.props.allCategories;
        }
        const bar = this.props.barCategories;
        const selected = this.props.selected;
        // A category chosen in the full band stays visible once folded.
        if (selected && !bar.some((category) => category.eq(selected))) {
            return [...bar, selected];
        }
        return bar;
    }

    get toggleLabel() {
        return this.state.expanded ? _t("Show the main categories only") : _t("Show all the categories");
    }

    buttonLabel(category) {
        return _t("Write a reflection: %(category)s", {
            category: category.name || category.code,
        });
    }

    /** The tooltip: the name of the category and its short definition. */
    buttonTitle(category) {
        const name = category.name || category.code;
        return category.definition ? `${name} — ${category.definition}` : name;
    }

    isSelected(category) {
        return Boolean(this.props.selected?.eq(category));
    }

    toggle() {
        this.state.expanded = !this.state.expanded;
    }

    /** @param {KeyboardEvent} ev */
    onKeydown(ev) {
        linkupToolbarKeydown(ev, this.root.el);
    }
}
