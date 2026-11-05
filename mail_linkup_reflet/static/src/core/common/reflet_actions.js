import {Component, useEffect, useRef, useState} from "@odoo/owl";

import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

import {LinkupCategoryPicker} from "./category_picker";
import {LinkupGuideButton} from "./linkup_guide";
import {LinkupCategoryIcon} from "./linkup_category_icon";
import {LinkupErrorAlert} from "./linkup_error_alert";
import {linkupClientError, linkupErrorInfo, linkupFieldMessage, linkupMediaDenied} from "./linkup_errors";

/**
 * Insert a starter at the beginning of a text.
 *
 * The starter replaces the one inserted before, when the text still begins
 * with it, so that changing the category changes the starter without
 * touching what was typed after it. An empty text becomes the starter.
 *
 * @param {string} text
 * @param {string} previous the starter inserted before, or ""
 * @param {string} starter the new starter, or ""
 * @returns {string}
 */
export function linkupInsertStarter(text, previous, starter) {
    let rest = text;
    if (previous && rest.startsWith(previous)) {
        rest = rest.slice(previous.length).trimStart();
    }
    if (!starter) {
        return rest;
    }
    return rest ? `${starter} ${rest}` : `${starter} `;
}

/**
 * What the current user can do on a card of a carrier message.
 *
 * The block depends on the card and on whether the current user is its
 * recipient; the author and the other readers get nothing.
 *
 * - `validate`: an initial reflection waiting for its recipient, who
 *   confirms it, rejects it after a confirmation dialog, ignores it or says
 *   that it is not what was said, with an optional correction.
 * - `answer`: a confirmed initial reflection, or a continued one, whose
 *   recipient holds the turn: "Yes, that's exactly it!", with an optional
 *   text, or "I would like to clarify…", with a text that starts empty and
 *   optional hidden themes (at most `Store.linkup_max_hidden_themes`).
 * - `guess`: a precision hiding a theme, whose recipient makes a single
 *   guess; the server says whether it is found.
 * - `options`: an exact answer or a resolved precision, whose recipient
 *   holds the turn: continue the reflection ("So if I understand
 *   correctly…" and the reformulation starter of a category), talk about
 *   oneself (the call buttons, then the first-person starter of a
 *   category), or end it here (the closing sentence, editable).
 * - `rephrase`: a disclosure, whose recipient reformulates it as a
 *   continued reflection.
 * - `withdraw`: a sent initial reflection that its recipient has not read
 *   yet, whose author withdraws it after a confirmation (LU-F-019).
 *
 * The validation and the guess carry the "?" button of the guide mode
 * (`linkup_guide.js`), in which each button explains itself instead of
 * acting: a proposal of the guess is only recorded outside of it.
 *
 * Each action calls the `action_*` method of `linkup.reflet`; a refusal
 * shows the message of its `linkup_code` (`LinkupErrorAlert`), which
 * stays once the card read again has no action left, so that a reflection
 * withdrawn or answered elsewhere says so. A lost connection offers to run
 * the action again. After an action the cards and the new messages of the
 * conversation are read again, which the bus also brings, and `onDone` is
 * called. `Escape` closes an open form.
 *
 * A call is not started while the browser refuses the microphone, or the
 * camera for a video call: the block says how to allow them instead.
 *
 * @typedef {Object} Props
 * @property {import("models").LinkupReflet} reflet
 * @property {import("models").Thread} [thread]
 * @property {Function} [onDone] called after each action, done or refused
 * @extends {Component<Props, Env>}
 */
export class LinkupRefletActions extends Component {
    static template = "mail_linkup_reflet.LinkupRefletActions";
    static components = {LinkupCategoryIcon, LinkupCategoryPicker, LinkupErrorAlert, LinkupGuideButton};
    static props = ["reflet", "thread?", "onDone?"];

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.textRef = useRef("text");
        this.state = useState({
            form: null,
            text: "",
            starter: "",
            categoryIds: [],
            guessIds: [],
            busy: false,
            error: null,
        });
        useEffect(
            (form) => {
                if (form && this.textRef.el) {
                    this.textRef.el.focus();
                    const end = this.textRef.el.value.length;
                    this.textRef.el.setSelectionRange(end, end);
                }
            },
            () => [this.state.form]
        );
    }

    get reflet() {
        return this.props.reflet;
    }

    /** The block shown to the current user; see the class comment. */
    get mode() {
        const reflet = this.reflet;
        if (reflet.author?.eq(this.store.self)) {
            return reflet.kind === "initial" && reflet.state === "sent" && !reflet.read_date ? "withdraw" : null;
        }
        if (!reflet.recipient?.eq(this.store.self)) {
            return null;
        }
        if (reflet.kind === "initial" && reflet.state === "sent") {
            return reflet.recipient_ignored ? null : "validate";
        }
        if (reflet.kind === "precision" && reflet.guess_state === "pending") {
            return "guess";
        }
        if (!reflet.holds_turn || reflet.response_state !== "none") {
            return null;
        }
        if (
            (reflet.kind === "initial" && reflet.state === "confirmed") ||
            (reflet.kind === "continue" && reflet.state === "sent")
        ) {
            return "answer";
        }
        if (["answer_exact", "precision"].includes(reflet.kind) && reflet.state === "sent") {
            return "options";
        }
        if (reflet.kind === "self_disclosure" && reflet.state === "sent") {
            return "rephrase";
        }
        return null;
    }

    get authorName() {
        return this.reflet.author?.name || _t("the other person");
    }

    get recipientName() {
        return this.reflet.recipient?.name || _t("the other person");
    }

    get withdrawHint() {
        return _t("Possible as long as %(name)s has not read it.", {name: this.recipientName});
    }

    get categories() {
        return this.store.linkupCategories;
    }

    get maxHiddenThemes() {
        return this.store.linkup_max_hidden_themes || 1;
    }

    get category() {
        const id = this.state.categoryIds[0];
        return id ? this.store["linkup.category"].get(id) : null;
    }

    get answerQuestion() {
        return _t("Did %(name)s understand you well?", {name: this.authorName});
    }

    get guessQuestion() {
        return _t("%(name)s hid a theme in this answer. Which one?", {
            name: this.authorName,
        });
    }

    get rephraseText() {
        return _t("%(name)s told you about something that matters to them. Rephrase it to show what you understood.", {
            name: this.authorName,
        });
    }

    get hiddenThemeLabel() {
        return _t("Hidden theme, optional: %(name)s will have to guess it while reading your answer.", {
            name: this.authorName,
        });
    }

    get sendLabel() {
        return _t("Send to %(name)s", {name: this.authorName});
    }

    get callLabel() {
        return _t("Call %(name)s", {name: this.authorName});
    }

    get videoLabel() {
        return _t("Video call with %(name)s", {name: this.authorName});
    }

    get canCall() {
        return Boolean(this.props.thread?.allowCalls);
    }

    /** Heading of the open form. */
    get formTitle() {
        switch (this.state.form) {
            case "inaccurate":
                return _t("The exchange took place, but that is not what I said");
            case "exact":
                return _t("Yes, that's exactly it!");
            case "precision":
                return _t("I would like to clarify…");
            case "continue":
                return _t("So if I understand correctly…");
            case "self":
                return _t("I would like to tell you about something that matters to me.");
            case "close":
                return _t("End it here");
        }
        return "";
    }

    /** Label of the text of the open form. */
    get textLabel() {
        switch (this.state.form) {
            case "inaccurate":
                return _t("Correction for %(name)s (optional)", {
                    name: this.authorName,
                });
            case "exact":
                return _t("A word to add (optional)");
            case "precision":
                return _t("Your clarification");
            case "continue":
                return _t("Your reformulation");
            case "self":
                return _t("Your message");
            case "close":
                return _t("Your closing message");
        }
        return "";
    }

    get textRequired() {
        return ["precision", "continue", "self"].includes(this.state.form);
    }

    /** The closing sentence, in the language of the current user. */
    get closingSentence() {
        return _t("Thank you for our discussion.");
    }

    // ------------------------------------------------------------------
    // Forms
    // ------------------------------------------------------------------

    /**
     * Open a form. Continuing or rephrasing preselects the category of the
     * reflection and inserts its reformulation starter; ending it here
     * starts from the closing sentence; a precision starts empty.
     *
     * @param {string} form
     */
    open(form) {
        Object.assign(this.state, {
            form,
            text: "",
            starter: "",
            categoryIds: [],
            error: null,
        });
        if (form === "close") {
            this.state.text = this.closingSentence;
        } else if (form === "continue" && this.reflet.kind === "self_disclosure" && this.reflet.category_id) {
            this.onChangeCategories([this.reflet.category_id.id]);
        }
    }

    closeForm() {
        Object.assign(this.state, {
            form: null,
            text: "",
            starter: "",
            categoryIds: [],
            error: null,
        });
    }

    /** The hidden themes of a precision never touch its text. */
    onChangeThemes(ids) {
        this.state.categoryIds = ids;
        this.state.error = null;
    }

    /**
     * The category of a continued reflection or of a disclosure inserts
     * its starter at the beginning of the text.
     *
     * @param {number[]} ids
     */
    onChangeCategories(ids) {
        this.state.categoryIds = ids;
        this.state.error = null;
        const category = ids.length ? this.store["linkup.category"].get(ids[0]) : null;
        const starter = (this.state.form === "self" ? category?.starter_self : category?.starter_reflect) || "";
        this.state.text = linkupInsertStarter(this.state.text, this.state.starter, starter);
        this.state.starter = starter;
        this.textRef.el?.focus();
    }

    onChangeGuess(ids) {
        this.state.guessIds = ids;
        this.state.error = null;
    }

    /** `Escape` closes the open form. */
    onKeydown(ev) {
        if (ev.key === "Escape" && this.state.form) {
            ev.preventDefault();
            ev.stopPropagation();
            this.closeForm();
        }
    }

    // ------------------------------------------------------------------
    // Server calls
    // ------------------------------------------------------------------

    /**
     * Call an action of the reflection, then read the conversation again.
     *
     * @param {string} method
     * @param {any[]} args after the id of the reflection
     * @returns {Promise<boolean>} whether the action succeeded
     */
    async call(method, args = []) {
        if (this.state.busy) {
            return false;
        }
        this.lastCall = [method, args];
        this.state.busy = true;
        this.state.error = null;
        const thread = this.props.thread;
        let done = false;
        try {
            await this.orm.silent.call("linkup.reflet", method, [[this.reflet.id], ...args]);
            done = true;
            this.closeForm();
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.error = info;
        } finally {
            this.state.busy = false;
        }
        if (thread) {
            // An action refused because the card is stale reads it again too.
            await this.store.linkupRefreshThread(thread).catch(() => {});
        }
        this.props.onDone?.();
        return done;
    }

    /** Run again the action a lost connection refused. */
    retry() {
        if (this.lastCall) {
            return this.call(...this.lastCall);
        }
    }

    /** A withdrawal is asked for first: it cannot be undone. */
    askWithdraw() {
        if (this.state.busy) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Withdraw this reflection"),
            body: _t("Withdraw this reflection? %(name)s will no longer see its content.", {
                name: this.recipientName,
            }),
            confirmLabel: _t("Withdraw"),
            confirmClass: "btn-danger o-linkup-WithdrawDialog-confirm",
            confirm: () => this.call("action_withdraw"),
            cancel: () => {},
        });
    }

    confirm() {
        return this.call("action_confirm");
    }

    /** A rejection is declared after a confirmation: it accuses the author. */
    askReject() {
        if (this.state.busy) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("This exchange did not take place"),
            body: _t(
                "Declare that the exchange of this reflection never took place? %(name)s will see it. For a reflection you do not want, choose “Ignore”; for a wrong reformulation, “That is not what I said”.",
                {name: this.authorName}
            ),
            confirmLabel: _t("This exchange did not take place"),
            confirmClass: "btn-danger o-linkup-RejectDialog-confirm",
            confirm: () => this.call("action_reject"),
            cancel: () => {},
        });
    }

    ignore() {
        return this.call("action_ignore");
    }

    guess() {
        const [categoryId] = this.state.guessIds;
        if (!categoryId) {
            this.state.error = {
                code: "linkup.validation",
                field: "category_id",
                message: _t("Choose a theme."),
            };
            return;
        }
        return this.call("action_guess", [categoryId]);
    }

    /** Send the open form to its action. */
    async submit() {
        const text = this.state.text.trim();
        const form = this.state.form;
        if (this.textRequired && (!text || text === this.state.starter.trim())) {
            this.state.error = {
                code: "linkup.validation",
                field: "body_text",
                message: linkupFieldMessage("body_text"),
            };
            this.textRef.el?.focus();
            return;
        }
        if (form === "continue" && !this.category) {
            this.state.error = {
                code: "linkup.validation",
                field: "category_id",
                message: linkupFieldMessage("category_id"),
            };
            return;
        }
        switch (form) {
            case "inaccurate":
                return this.call("action_mark_inaccurate", [text || null]);
            case "exact":
                return this.call("action_answer_exact", [text || null]);
            case "precision":
                return this.call("action_answer_precision", [text, [...this.state.categoryIds]]);
            case "continue":
                return this.call("action_continue", [this.category.id, text]);
            case "self":
                return this.call("action_self_disclosure", [this.category?.id || false, text]);
            case "close":
                // The unchanged sentence is left to the clients, which show
                // it in the language of each reader.
                return this.call("action_close", [text && text !== this.closingSentence ? text : null]);
        }
    }

    /** @param {{camera?: boolean}} options */
    async startCall(options = {}) {
        const thread = this.props.thread;
        if (!thread?.allowCalls) {
            return;
        }
        this.state.error = null;
        if (await linkupMediaDenied(options)) {
            this.state.error = linkupClientError("media_denied");
            return;
        }
        this.env.services["discuss.rtc"].toggleCall(thread, options);
    }
}
