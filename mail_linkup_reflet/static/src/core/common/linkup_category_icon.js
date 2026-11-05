import {Component} from "@odoo/owl";

/**
 * Line drawings of the categories, by code, on a 24 × 24 grid. Each one is
 * stroked with `currentColor`, so it follows the text colour of its
 * container in the light and the dark themes.
 */
export const LINKUP_CATEGORY_PATHS = {
    // An eye.
    observation: ["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z", "M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6z"],
    // A smiling face.
    emotions: [
        "M12 2.5a9.5 9.5 0 1 0 0 19a9.5 9.5 0 1 0 0-19z",
        "M8 14.5s1.5 2 4 2 4-2 4-2",
        "M9 9.5h.01",
        "M15 9.5h.01",
    ],
    // A house.
    needs: ["M3 11l9-7 9 7", "M5 9.5V20h14V9.5", "M10 20v-5h4v5"],
    // An arrow towards a bar: go on.
    action: ["M3 12h12", "M11 7l5 5-5 5", "M20 5v14"],
    // A bar and a cross: stop.
    inhibition: ["M4 5v14", "M10 8l8 8", "M18 8l-8 8"],
    // An ear.
    go_listen: [
        "M7 9a5 5 0 0 1 10 0c0 4.5-4.5 5-4.5 9a2.5 2.5 0 0 1-5 0",
        "M14 9a2 2 0 0 0-4 0",
        "M19.5 6.5a7 7 0 0 1 0 5",
    ],
    // A speech bubble.
    go_speak: [
        "M20 11.5a7.5 7.5 0 0 1-10.9 6.7L4 20l1.6-4.6A7.5 7.5 0 1 1 20 11.5z",
        "M9 11.5h.01",
        "M12.5 11.5h.01",
        "M16 11.5h.01",
    ],
    // A flag on a summit.
    goals: ["M3 20l6-10 3.5 5.5 2-3 5.5 7.5z", "M9 10V3.5", "M9 3.5h6l-1.5 2 1.5 2H9"],
    // A nesting doll.
    vulnerability: [
        "M12 3a3.5 3.5 0 0 1 3.5 3.5c2 1.4 3.5 4 3.5 7.5a7 7 0 0 1-14 0c0-3.5 1.5-6.1 3.5-7.5A3.5 3.5 0 0 1 12 3z",
        "M12 5.2a1.5 1.5 0 1 0 0 3a1.5 1.5 0 1 0 0-3z",
        "M8 14h8",
    ],
    // Two overlapping circles.
    reflection: ["M8.5 5a5 5 0 1 0 0 10a5 5 0 1 0 0-10z", "M15.5 9a5 5 0 1 0 0 10a5 5 0 1 0 0-10z"],
    // A target.
    focus: [
        "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z",
        "M12 7.5a4.5 4.5 0 1 0 0 9a4.5 4.5 0 1 0 0-9z",
        "M12 11.2a.8.8 0 1 0 0 1.6a.8.8 0 1 0 0-1.6z",
    ],
    // Two people.
    team: [
        "M7.5 10.5a2.75 2.75 0 1 0 0-5.5a2.75 2.75 0 1 0 0 5.5z",
        "M16.5 10.5a2.75 2.75 0 1 0 0-5.5a2.75 2.75 0 1 0 0 5.5z",
        "M2.5 19.5c0-3 2.2-5.5 5-5.5s5 2.5 5 5.5",
        "M11.5 19.5c0-3 2.2-5.5 5-5.5s5 2.5 5 5.5",
    ],
};
/** Drawing of a category created by an administrator: a tag. */
const DEFAULT_PATHS = ["M3 12V4h8l10 10-8 7z", "M7.5 8.5h.01"];
/** Drawing of a hidden theme: a question mark in a circle. */
export const HIDDEN_THEME_PATHS = [
    "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z",
    "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6",
    "M12 17h.01",
];

/**
 * The pictogram of a category.
 *
 * With a `label`, the drawing is an image named by that label; without, it
 * is decorative and hidden from assistive technologies, for a container
 * that carries the name itself, such as a button with `aria-label`.
 *
 * @typedef {Object} Props
 * @property {string} [code] code of the category
 * @property {boolean} [hidden] draw the hidden-theme sign instead
 * @property {string} [label]
 * @property {number} [size]
 * @extends {Component<Props, Env>}
 */
export class LinkupCategoryIcon extends Component {
    static template = "mail_linkup_reflet.LinkupCategoryIcon";
    static props = ["code?", "hidden?", "label?", "size?"];
    static defaultProps = {size: 20};

    get paths() {
        if (this.props.hidden) {
            return HIDDEN_THEME_PATHS;
        }
        return LINKUP_CATEGORY_PATHS[this.props.code] || DEFAULT_PATHS;
    }
}
