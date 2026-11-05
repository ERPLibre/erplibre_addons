import {Component, markup, reactive, useEffect, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

import {LinkupCategoryIcon} from "./linkup_category_icon";

/** Attribute that makes an element part of the guide. */
export const LINKUP_GUIDE_ATTRIBUTE = "data-linkup-guide";

/**
 * The texts of the elements of the guide that are not categories, by the
 * value of their `data-linkup-guide`. A category takes its texts from its
 * record (`linkup.category`). `noShow` keeps "Show" from pressing an
 * element whose action cannot be undone: "Show" then gives it the focus.
 */
function linkupGuideTexts() {
    return {
        "help-more": {
            title: _t("All the categories"),
            text: _t("The twelve categories of communication, in the order of the full band."),
            behavior: _t("Outside the guide, this button unfolds the full band, then folds it back."),
        },
        "reflet-confirm": {
            title: _t("That's a link!"),
            text: _t("The exchange took place and the reformulation is right."),
            behavior: _t(
                "Outside the guide, this button confirms the reflection: the link becomes active and free text opens. Key →."
            ),
            noShow: true,
        },
        "reflet-reject": {
            title: _t("This exchange did not take place"),
            text: _t("Only for a false reflection: the exchange never happened."),
            behavior: _t("Outside the guide, this button asks for a confirmation first. Key ←."),
        },
        "reflet-inaccurate": {
            title: _t("That is not what I said"),
            text: _t("The exchange took place, but the reformulation is not right."),
            behavior: _t("Outside the guide, this button opens a form for an optional correction; no link is created."),
        },
        "reflet-ignore": {
            title: _t("Ignore"),
            text: _t("The reflection disappears for you; nobody is told."),
            behavior: _t("Outside the guide, this button folds the card; the reflection expires without an answer."),
            noShow: true,
        },
        "guess-submit": {
            title: _t("Propose this theme"),
            text: _t("Your guess of the hidden theme."),
            behavior: _t(
                "Outside the guide, this button sends the guess: one try only. The answer shows the themes to both of you."
            ),
            noShow: true,
        },
        "reflet-view-contact": {
            title: _t("A contact"),
            text: _t("A person of your conversations or of your confirmed links."),
            behavior: _t(
                "Outside the guide, choosing a person makes them the recipient of the card; dropping a category on a person does both."
            ),
        },
        "reflet-view-newlink": {
            title: _t("+ NewLink"),
            text: _t("Invite a person who is not on LinkUp yet, from a real exchange."),
            behavior: _t(
                "Outside the guide, this button opens the invitation in three steps: the email address, the reflection, the preview. Dropping a category on it does the same."
            ),
        },
        "reflet-view-send-to": {
            title: _t("Send to…"),
            text: _t("The list of your contacts, without a mouse."),
            behavior: _t(
                "Outside the guide, this button opens the list: the arrow keys move, Enter chooses and sends, Escape closes."
            ),
        },
        "reflet-view-happiness": {
            title: _t("You add to my happiness"),
            text: _t("Thank someone without words: their avatar shines until your next exchange."),
            behavior: _t(
                "Outside the guide, drag this field onto a person, or press it to choose one in the list: the arrow keys move, Enter chooses, Escape closes."
            ),
        },
        highlight: {
            title: _t("You add to my happiness"),
            text: _t("Thank someone without words: their avatar shines until your next exchange."),
            behavior: _t(
                "Outside the guide, this button asks for a confirmation, then puts the person in the light. A new press while it shines has no effect."
            ),
        },
    };
}

/**
 * The guide mode of the LinkUp screens (LU-F-081 RM2 to RM4).
 *
 * While it is active, every element marked `data-linkup-guide` that is on
 * the screen carries its number (`linkup_guide.scss`, a CSS counter in the
 * order of the document), and activating it explains it instead of acting:
 * a listener of the document, in the capture phase, stops the click before
 * it reaches the element and opens its sheet. Reading a sheet changes
 * nothing on the screen. "Show" leaves the guide and presses the element,
 * or gives it the focus when its action cannot be undone. `Escape`, the
 * close button of the sheet or a second press on a "?" button leaves the
 * guide.
 */
export class LinkupGuideState {
    constructor() {
        this.active = false;
        /** @type {HTMLElement|null} the element whose sheet is shown */
        this.element = null;
        /** Changed on every move, so that the sheet renders again. */
        this.version = 0;
        /** The listeners of the document while the guide is active. */
        this.listeners = null;
    }

    /** The elements of the guide on the screen, in document order. */
    entries() {
        return [...document.querySelectorAll(`[${LINKUP_GUIDE_ATTRIBUTE}]`)].filter(
            (el) => el.getClientRects().length > 0
        );
    }

    get position() {
        return this.element ? this.entries().indexOf(this.element) + 1 : 0;
    }

    toggle() {
        if (this.active) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        if (this.active) {
            return;
        }
        this.active = true;
        document.body.classList.add("o-linkup-guideActive");
        // Called on the reactive object, so that the listeners change it
        // through the proxy and the sheet renders again.
        this.listeners = {
            click: (ev) => this._onClick(ev),
            pointerdown: (ev) => this._onPointerDown(ev),
            keydown: (ev) => this._onKeydown(ev),
        };
        for (const [type, listener] of Object.entries(this.listeners)) {
            document.addEventListener(type, listener, true);
        }
        this.select(this.entries()[0] || null);
    }

    close() {
        if (!this.active) {
            return;
        }
        this.active = false;
        this.element = null;
        document.body.classList.remove("o-linkup-guideActive");
        for (const [type, listener] of Object.entries(this.listeners || {})) {
            document.removeEventListener(type, listener, true);
        }
        this.listeners = null;
        this.version++;
    }

    /** @param {HTMLElement|null} el */
    select(el) {
        this.element = el;
        this.version++;
    }

    /** Move to the next (1) or previous (-1) element, wrapping around. */
    move(step) {
        const entries = this.entries();
        if (!entries.length) {
            this.select(null);
            return;
        }
        const index = entries.indexOf(this.element);
        this.select(entries[(index + step + entries.length) % entries.length]);
    }

    /** Leave the guide and put the screen in the state the sheet describes. */
    show(noShow) {
        const el = this.element;
        this.close();
        if (!el?.isConnected) {
            return;
        }
        if (noShow) {
            el.focus();
        } else {
            el.click();
        }
    }

    _guideTarget(ev) {
        return ev.target instanceof Element ? ev.target.closest(`[${LINKUP_GUIDE_ATTRIBUTE}]`) : null;
    }

    _onClick(ev) {
        const target = this._guideTarget(ev);
        if (!target) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.select(target);
    }

    /** A drag would act: the pointer stays on the element, nothing starts. */
    _onPointerDown(ev) {
        if (this._guideTarget(ev)) {
            ev.stopPropagation();
        }
    }

    _onKeydown(ev) {
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.close();
        }
    }
}

export const linkupGuideService = {
    start() {
        return reactive(new LinkupGuideState());
    },
};

registry.category("services").add("linkup.guide", linkupGuideService);

/**
 * The round "?" button that turns the guide mode on and off.
 *
 * @extends {Component<{className?: string}, Env>}
 */
export class LinkupGuideButton extends Component {
    static template = "mail_linkup_reflet.LinkupGuideButton";
    static props = ["className?"];

    setup() {
        super.setup();
        this.guide = useState(useService("linkup.guide"));
    }

    get label() {
        return this.guide.active ? _t("Leave the guide") : _t("Guide: explain each element");
    }
}

/**
 * The sheet of the guide: "Guide · n of N", the title of the element, and
 * for a category its definition, what to say and not to say, its starter
 * and what a press does in this context; then ‹ ›, "Show" and close. It
 * floats at the bottom of the screen, and rises from the bottom on a small
 * screen. Mounted once, in the main components of the web client.
 */
export class LinkupGuideSheet extends Component {
    static template = "mail_linkup_reflet.LinkupGuideSheet";
    static components = {LinkupCategoryIcon};
    static props = {};

    setup() {
        super.setup();
        this.guide = useState(useService("linkup.guide"));
        this.store = useState(useService("mail.store"));
        this.root = useRef("root");
        useEffect(
            (active) => {
                if (active) {
                    this.store.fetchLinkupCategories?.().catch(() => {});
                }
            },
            () => [this.guide.active]
        );
    }

    get el() {
        // Read the version so that a move renders the sheet again.
        return this.guide.version >= 0 ? this.guide.element : null;
    }

    get key() {
        return this.el?.getAttribute(LINKUP_GUIDE_ATTRIBUTE) || "";
    }

    get category() {
        if (this.key !== "category") {
            return null;
        }
        const code = this.el.dataset.code;
        return this.store.linkupCategories?.find((category) => category.code === code) || null;
    }

    get texts() {
        return linkupGuideTexts()[this.key] || null;
    }

    get counter() {
        return _t("Guide · %(position)s of %(count)s", {
            position: this.guide.position,
            count: this.guide.entries().length,
        });
    }

    get title() {
        const category = this.category;
        if (category) {
            return category.name || category.code;
        }
        return this.texts?.title || _t("Guide");
    }

    get definition() {
        const category = this.category;
        if (category) {
            return category.definition ? markup(category.definition) : "";
        }
        return this.texts?.text || "";
    }

    get starter() {
        return this.category?.starter_self || "";
    }

    get behavior() {
        const category = this.category;
        if (!category) {
            return this.texts?.behavior || "";
        }
        switch (this.el.dataset.linkupGuideContext) {
            case "guess":
                return _t(
                    "Outside the guide, this button chooses this theme as your guess; “Propose this theme” sends it, once."
                );
            case "theme":
                return _t("Outside the guide, this button chooses this category for your answer.");
        }
        return _t("Outside the guide, this button opens the card “%(title)s”: You told me / I understood that.", {
            title: category.reflet_title || category.name,
        });
    }

    get doLabel() {
        return _t("What to say:") + " ";
    }

    get dontLabel() {
        return _t("What not to say:") + " ";
    }

    get starterLabel() {
        return _t("Starter:") + " ";
    }

    get behaviorLabel() {
        return _t("Behaviour:") + " ";
    }

    get hint() {
        return _t("Press a numbered element to read what it does. Escape or “?” leaves the guide.");
    }

    get noShow() {
        return Boolean(this.texts?.noShow);
    }
}

registry.category("main_components").add("mail_linkup_reflet.LinkupGuideSheet", {
    Component: LinkupGuideSheet,
});
