import {Component, toRaw, useEffect, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

import {LinkupCategoryIcon} from "./linkup_category_icon";
import {linkupReadWatch} from "./linkup_read_watch";
import {LinkupRefletActions} from "./reflet_actions";
import {LinkupSafetyActions} from "./linkup_safety";

/** Ids of the reflections whose reading was sent to the server, by Store. */
const LINKUP_READ_REQUESTED = new WeakMap();

/** @returns {Set<number>} */
function linkupReadRequested(store) {
    const raw = toRaw(store);
    if (!LINKUP_READ_REQUESTED.has(raw)) {
        LINKUP_READ_REQUESTED.set(raw, new Set());
    }
    return LINKUP_READ_REQUESTED.get(raw);
}

/** Label of the badge of an initial reflection, by state. */
export function linkupStateLabel(state) {
    switch (state) {
        case "draft":
            return _t("Draft");
        case "pending_invite":
            return _t("Waiting for the invitation");
        case "sent":
            return _t("Waiting");
        case "confirmed":
            return _t("Confirmed");
        case "rejected":
            return _t("Rejected");
        case "inaccurate":
            return _t("Inaccurate");
        case "expired":
            return _t("Expired");
        case "withdrawn":
            return _t("Withdrawn");
    }
    return "";
}

/** Label of the badge of a reply in the chain of turns, by kind. */
export function linkupKindLabel(kind) {
    switch (kind) {
        case "precision":
            return _t("Precision");
        case "continue":
            return _t("Continued reflection");
        case "self_disclosure":
            return _t("Talking about oneself");
        case "answer_exact":
            return _t("Exact answer");
        case "close":
            return _t("Closing");
    }
    return _t("A reflection");
}

/**
 * The card of a reflection, drawn in place of the body of its carrier
 * message, in the LinkUp panel and as the preview of a draft.
 *
 * `reflet` is a `linkup.reflet` record, or for a preview a plain object
 * with the same fields. The card shows the category, the texts and the
 * state; the sentence of its footer depends on whether the current user
 * wrote the reflection or received it. Every text is escaped.
 *
 * An `interactive` card, the one of a carrier message, also holds what its
 * recipient can do, or its author while they may withdraw it
 * (`LinkupRefletActions`), then "Report this reflection"
 * and "Block" (`LinkupSafetyActions`). While an initial reflection
 * waits for its recipient, the card takes the focus and the arrow keys
 * stand for the swipes of the mobile application: `→` presses "That's a
 * link!", `←` "This exchange did not take place", which asks for a
 * confirmation. A reflection its recipient ignored is folded for them.
 *
 * The card of a sent initial reflection records its reading by its
 * recipient (`action_mark_read`), once per reflection, when it is really
 * seen: the tab is visible and the card is on the screen
 * (`linkup_read_watch.js`). From then on, its author can no longer
 * withdraw it.
 *
 * @typedef {Object} Props
 * @property {import("models").LinkupReflet|Object} reflet
 * @property {import("models").Thread} [thread] the conversation of the card
 * @property {boolean} [interactive] show the actions of the current user
 * @property {boolean} [preview] the draft of the current user
 * @property {boolean} [compact] title and badge only
 * @property {Function} [onAction] called after an action of the card
 * @extends {Component<Props, Env>}
 */
export class LinkupRefletCard extends Component {
    static template = "mail_linkup_reflet.LinkupRefletCard";
    static components = {LinkupCategoryIcon, LinkupRefletActions, LinkupSafetyActions};
    static props = ["reflet", "thread?", "interactive?", "preview?", "compact?", "onAction?"];

    setup() {
        super.setup();
        this.root = useRef("root");
        this.store = useState(useService("mail.store"));
        this.orm = useService("orm");
        // The texts of the categories fill the records the card points to.
        this.store.fetchLinkupCategories().catch(() => {});
        useEffect(
            (needsRead, refletId) => {
                if (!needsRead || !this.root.el || linkupReadRequested(this.store).has(refletId)) {
                    return;
                }
                return this.watchReading(refletId);
            },
            () => [this.needsRead, this.reflet.id]
        );
    }

    /**
     * Record the reading of the reflection once the card is really seen:
     * the tab is visible and the card is on the screen. Each change of
     * either checks both again; a card drawn in a hidden tab, or scrolled
     * out of view, records nothing until it is seen.
     *
     * @param {number} refletId
     * @returns {() => void} stops watching
     */
    watchReading(refletId) {
        let onScreen = false;
        let stopped = false;
        let stopObserver = null;
        const stop = () => {
            stopped = true;
            stopObserver?.();
            document.removeEventListener("visibilitychange", check);
        };
        const check = () => {
            const requested = linkupReadRequested(this.store);
            if (requested.has(refletId)) {
                stop();
                return;
            }
            if (!onScreen || !linkupReadWatch.isPageVisible()) {
                return;
            }
            requested.add(refletId);
            stop();
            this.orm.silent.call("linkup.reflet", "action_mark_read", [[refletId]]).catch(() => {
                requested.delete(refletId);
            });
        };
        document.addEventListener("visibilitychange", check);
        const stopWatch = linkupReadWatch.observe(this.root.el, (isOnScreen) => {
            onScreen = isOnScreen;
            check();
        });
        // The watch may report at once, and the reading stop it already.
        if (stopped) {
            stopWatch();
        } else {
            stopObserver = stopWatch;
        }
        return stop;
    }

    /** A sent initial reflection that its recipient sees for the first time. */
    get needsRead() {
        const reflet = this.reflet;
        return Boolean(
            this.props.interactive &&
                reflet.id &&
                reflet.kind === "initial" &&
                reflet.state === "sent" &&
                !reflet.read_date &&
                this.role === "recipient"
        );
    }

    get reflet() {
        return this.props.reflet;
    }

    get isWithdrawn() {
        return this.reflet.state === "withdrawn";
    }

    /** A sent reflection that its recipient, the current user, set aside. */
    get isIgnored() {
        return this.role === "recipient" && this.reflet.state === "sent" && Boolean(this.reflet.recipient_ignored);
    }

    /** The texts are hidden once withdrawn or ignored. */
    get showTexts() {
        return !this.props.compact && !this.isWithdrawn && !this.isIgnored;
    }

    /**
     * The recipient of an interactive card reports it or blocks its
     * author, while its texts are theirs to read.
     */
    get showSafety() {
        return Boolean(
            this.props.interactive &&
                !this.props.compact &&
                !this.props.preview &&
                this.reflet.id &&
                this.reflet.author?.id &&
                this.role === "recipient" &&
                !this.isWithdrawn
        );
    }

    /** An initial reflection waiting for the current user, its recipient. */
    get isValidatable() {
        const reflet = this.reflet;
        return Boolean(
            this.props.interactive &&
                reflet.kind === "initial" &&
                reflet.state === "sent" &&
                this.role === "recipient" &&
                !reflet.recipient_ignored
        );
    }

    /**
     * The arrow keys on the focused card press the confirmation and the
     * rejection buttons of its actions. Only the card itself listens: an
     * arrow pressed on one of its buttons or fields is left alone, so that
     * moving between the buttons never confirms the reflection.
     *
     * @param {KeyboardEvent} ev
     */
    onKeydown(ev) {
        if (!this.isValidatable || ev.target !== this.root.el) {
            return;
        }
        const selector = {
            ArrowRight: ".o-linkup-RefletActions-confirm",
            ArrowLeft: ".o-linkup-RefletActions-reject",
        }[ev.key];
        const button = selector && this.root.el?.querySelector(selector);
        if (button && !button.disabled) {
            ev.preventDefault();
            ev.stopPropagation();
            button.click();
        }
    }

    /** `author`, `recipient` or `reader` (an administrator, say). */
    get role() {
        if (this.props.preview || this.reflet.author?.eq?.(this.store.self)) {
            return "author";
        }
        if (this.reflet.recipient?.eq?.(this.store.self)) {
            return "recipient";
        }
        return "reader";
    }

    /** The hidden themes the current user may read, main theme first. */
    get revealedThemes() {
        const themes = [...(this.reflet.revealed_category_ids || [])];
        const primary = this.reflet.primary_category_id;
        if (primary) {
            themes.sort((a, b) => (b.eq(primary) ? 1 : 0) - (a.eq(primary) ? 1 : 0));
        }
        return themes;
    }

    get isThemeHidden() {
        return this.reflet.kind === "precision" && this.reflet.guess_state === "pending" && !this.revealedThemes.length;
    }

    /** The category drawn in the header, if any. */
    get iconCategory() {
        if (this.isWithdrawn) {
            return null;
        }
        if (this.reflet.kind === "precision") {
            return this.revealedThemes[0] || null;
        }
        return this.reflet.category_id || null;
    }

    get iconLabel() {
        if (this.isThemeHidden) {
            return _t("Hidden theme, to guess");
        }
        const category = this.iconCategory;
        return category ? category.name || category.code : "";
    }

    get title() {
        const reflet = this.reflet;
        if (this.isWithdrawn) {
            return _t("Reflection withdrawn");
        }
        switch (reflet.kind) {
            case "continue":
                return _t("So if I understand correctly…");
            case "answer_exact":
                return _t("Yes, that's exactly it!");
            case "precision":
                return _t("I would like to clarify…");
            case "self_disclosure":
                return _t("I would like to tell you about something that matters to me.");
            case "close":
                // A closing message written by its author replaces the
                // sentence, which is otherwise shown in the reader's language.
                return reflet.body_text || _t("Thank you for our discussion.");
        }
        const category = reflet.category_id;
        return category?.reflet_title || category?.name || _t("A reflection");
    }

    get badge() {
        if (this.isIgnored) {
            return _t("Set aside");
        }
        if (this.reflet.kind === "initial" || !this.reflet.kind) {
            return linkupStateLabel(this.reflet.state);
        }
        return linkupKindLabel(this.reflet.kind);
    }

    get authorName() {
        return this.reflet.author?.name || _t("Someone");
    }

    get recipientName() {
        return this.reflet.recipient?.name || _t("the other person");
    }

    /** The sentence of the footer, for the current user. */
    get status() {
        const reflet = this.reflet;
        const role = this.role;
        if (reflet.kind === "precision") {
            return this.themeStatus;
        }
        if (reflet.kind && reflet.kind !== "initial") {
            return "";
        }
        switch (reflet.state) {
            case "draft":
                return role === "author" && this.props.preview
                    ? _t("Preview: %(name)s will see this card.", {
                          name: this.recipientName,
                      })
                    : "";
            case "sent":
                if (role === "author") {
                    return _t("Waiting for the confirmation of %(name)s", {
                        name: this.recipientName,
                    });
                }
                if (this.isIgnored) {
                    return _t("You set this reflection aside; %(name)s is not told.", {
                        name: this.authorName,
                    });
                }
                if (role === "recipient") {
                    return _t("%(name)s sent you a reflection.", {
                        name: this.authorName,
                    });
                }
                return _t("Waiting for the confirmation");
            case "confirmed":
                return _t("That's a link!");
            case "rejected":
                return role === "recipient"
                    ? _t("You said that this exchange did not take place.")
                    : _t("%(name)s said that this exchange did not take place.", {
                          name: this.recipientName,
                      });
            case "inaccurate":
                return role === "recipient"
                    ? _t("You said that the exchange took place, but not as reformulated.")
                    : _t("%(name)s said that the exchange took place, but not as reformulated.", {
                          name: this.recipientName,
                      });
            case "expired":
                return _t("Expired without an answer.");
            case "withdrawn":
                return role === "author" ? _t("You withdrew this reflection.") : "";
        }
        return "";
    }

    /** The sentence about the hidden themes of a precision. */
    get themeStatus() {
        const reflet = this.reflet;
        const names = this.revealedThemes.map((theme) => theme.name || theme.code).join(", ");
        if (reflet.guess_state === "pending") {
            return names ? _t("Hidden theme: %(themes)s", {themes: names}) : _t("A theme is hidden in this answer.");
        }
        if (reflet.guess_state === "found") {
            return _t("Theme found: %(themes)s", {themes: names});
        }
        if (reflet.guess_state === "missed") {
            return _t("Theme missed: %(themes)s", {themes: names});
        }
        return "";
    }

    /** Labels of the two texts; the space keeps them apart from the text. */
    get youSaidLabel() {
        return _t("You told me:") + " ";
    }

    /** A continued reflection reads after its title, "So if I understand
     * correctly…", without a label of its own. */
    get understoodLabel() {
        return this.reflet.kind === "continue" ? "" : _t("I understood that:") + " ";
    }

    /** The free text, unless the title already shows it. */
    get bodyText() {
        return this.reflet.kind === "close" ? "" : this.reflet.body_text;
    }

    /** Label of the free text, by kind and state. */
    get bodyLabel() {
        if (this.reflet.kind === "initial" && this.reflet.state === "inaccurate") {
            return _t("Correction:");
        }
        return "";
    }
}
