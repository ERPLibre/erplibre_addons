import {Component, useRef} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";

import {linkupToolbarKeydown} from "./help_bar";
import {LinkupCategoryIcon} from "./linkup_category_icon";

/**
 * The full band of the categories, to choose one or several of them: the
 * hidden themes of a precision, the guess of a hidden theme, the starter
 * of a continued reflection or of a disclosure.
 *
 * Each category is a toggle button; clicking a chosen one removes it. With
 * `max` 1, choosing another category replaces the chosen one; with a
 * higher `max`, the other categories are marked unavailable once `max` are
 * chosen, until one is removed. The parent owns the selection: the picker
 * calls `onChange` with the new list of ids. It is a toolbar for the
 * keyboard, as the Help bar is.
 *
 * @typedef {Object} Props
 * @property {import("models").LinkupCategory[]} categories
 * @property {number[]} selectedIds in the order of choice
 * @property {(ids: number[]) => void} onChange
 * @property {string} label
 * @property {number} [max]
 * @property {boolean} [disabled]
 * @property {string} [guideContext] what a press does, for the sheet of the
 *  guide: `guess` or `theme`
 * @extends {Component<Props, Env>}
 */
export class LinkupCategoryPicker extends Component {
    static template = "mail_linkup_reflet.LinkupCategoryPicker";
    static components = {LinkupCategoryIcon};
    static props = ["categories", "selectedIds", "onChange", "label", "max?", "disabled?", "guideContext?"];
    static defaultProps = {max: 1, guideContext: "theme"};

    setup() {
        super.setup();
        this.root = useRef("root");
    }

    isSelected(category) {
        return this.props.selectedIds.includes(category.id);
    }

    /** A category that cannot be added while the selection is full. */
    isUnavailable(category) {
        return this.props.max > 1 && !this.isSelected(category) && this.props.selectedIds.length >= this.props.max;
    }

    /** Rank of a chosen category, for the main theme of a precision. */
    rank(category) {
        return this.props.selectedIds.indexOf(category.id) + 1;
    }

    optionLabel(category) {
        const name = category.name || category.code;
        if (this.props.max > 1 && this.rank(category) === 1) {
            return _t("%(category)s, main theme", {category: name});
        }
        return name;
    }

    /** @param {import("models").LinkupCategory} category */
    onClick(category) {
        if (this.props.disabled || this.isUnavailable(category)) {
            return;
        }
        const ids = this.props.selectedIds;
        if (this.isSelected(category)) {
            this.props.onChange(ids.filter((id) => id !== category.id));
        } else if (this.props.max === 1) {
            this.props.onChange([category.id]);
        } else {
            this.props.onChange([...ids, category.id]);
        }
    }

    /** @param {KeyboardEvent} ev */
    onKeydown(ev) {
        linkupToolbarKeydown(ev, this.root.el);
    }
}
