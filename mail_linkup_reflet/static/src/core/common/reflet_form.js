import {Component, onWillUnmount, useExternalListener, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {debounce} from "@web/core/utils/timing";

import {LinkupCategoryIcon} from "./linkup_category_icon";
import {LinkupErrorAlert} from "./linkup_error_alert";
import {linkupErrorInfo, linkupFieldMessage} from "./linkup_errors";
import {linkupPlaySound} from "./linkup_signals";
import {LinkupRefletCard} from "./reflet_card";

const {DateTime} = luxon;

/** Delay of the automatic saving of the draft while typing, in ms. */
export const LINKUP_DRAFT_SAVE_DELAY = 800;

/**
 * The form "You told me / I understood that" of a reflection, shared by
 * the composer of a direct conversation and by the Reflet view. Its
 * template is `mail_linkup_reflet.LinkupRefletForm`, called from the
 * template of the subclass.
 *
 * The form works on the single draft of the member on the server: it
 * restores it, saves it while typing (`action_save_draft`), sends it
 * (`action_send`) and deletes it on Cancel (`action_discard_draft`). The
 * saves run one after the other, so two calls never compete for the lock
 * of the draft. A refused action shows the message of its code in the
 * form. Choosing a category keeps the texts already typed. A sending that
 * succeeds plays the sound `linkup-sent`, unless the member turned the
 * LinkUp sounds off.
 *
 * The last save wins between two tabs: when the window takes the focus
 * back with nothing left to save, the form reads the draft of the server
 * again, and is emptied when the draft was sent or deleted elsewhere.
 *
 * A subclass gives what depends on where the form lives:
 *
 * - `extraState()`: its own keys of `this.state`;
 * - `isLoaded`: whether the draft of the server was read once;
 * - `fetchInfo()`: an answer holding `draft`, or `null` when it no longer
 *   applies; `applyInfo(info)` keeps the rest of it;
 * - `sendTarget`: `{recipientId, name}`, or `{invite, name}` for a NewLink
 *   invitation (`invite` being `{email, name}`), read when the sending
 *   starts, and `afterSend(target, result)`, called once it succeeded with
 *   the answer of `action_send`; `sentNotice(target, result)` is the
 *   sentence shown then;
 * - `recipientName`, `recipientPersona` (for the preview),
 *   `needsRealWorld` and `formId`, unique in the page;
 * - `sendLabel` and `cancelLabel`, the texts of the two buttons of the
 *   form when they differ from "Send the reflection" and "Cancel".
 */
export class LinkupRefletFormBase extends Component {
    static components = {LinkupCategoryIcon, LinkupErrorAlert, LinkupRefletCard};

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
        this.orm = useService("orm");
        this.youSaidRef = useRef("youSaid");
        this.understoodRef = useRef("understood");
        this.realWorldRef = useRef("realWorld");
        this.state = useState({
            ...this.extraState(),
            formOpen: false,
            categoryId: null,
            you_said: "",
            understood: "",
            real_world_declared: false,
            real_world_date: this.today,
            showPreview: false,
            sending: false,
            error: null,
            notice: "",
        });
        this.draftId = null;
        /** Whether the form holds a change not yet given to a save. */
        this.dirty = false;
        this.saving = Promise.resolve();
        this.debouncedSave = debounce(() => this.saveDraft().catch(() => {}), LINKUP_DRAFT_SAVE_DELAY);
        // A save still waiting when the form goes away runs at once.
        onWillUnmount(() => this.debouncedSave.cancel(true));
        useExternalListener(window, "focus", () => this.reloadDraft());
    }

    /** @returns {Object} the keys of `this.state` proper to the subclass */
    extraState() {
        return {};
    }

    get isLoaded() {
        return true;
    }

    /** @returns {Promise<Object|null>} */
    async fetchInfo() {
        return null;
    }

    /** Keep what the subclass needs of an answer of `fetchInfo`. */
    applyInfo() {}

    /** @returns {{recipientId?: number, invite?: Object, name: string}} */
    get sendTarget() {
        return {recipientId: null, name: this.recipientName};
    }

    /** Called with the `sendTarget` of a sending that succeeded, and the answer of the server. */
    afterSend() {}

    /**
     * @param {{name: string}} target
     * @returns {string} the sentence shown once the sending succeeded
     */
    sentNotice(target) {
        return _t("Reflection sent to %(name)s.", {name: target.name});
    }

    /** @returns {string} the text of the send button, empty for the default one */
    get sendLabel() {
        return "";
    }

    /** @returns {string} the text of the cancel button, empty for the default one */
    get cancelLabel() {
        return "";
    }

    get recipientName() {
        return "";
    }

    get recipientPersona() {
        return null;
    }

    get needsRealWorld() {
        return false;
    }

    get formId() {
        return "";
    }

    /**
     * Read the draft of the server again, unless a change of this form is
     * still to be saved or a sending is running.
     */
    async reloadDraft() {
        if (this.dirty || this.state.sending || !this.isLoaded) {
            return;
        }
        await this.saving;
        let info;
        try {
            info = await this.fetchInfo();
        } catch {
            return;
        }
        if (!info || this.dirty || this.state.sending) {
            return;
        }
        this.applyInfo(info);
        if (info.draft) {
            this.restoreDraft(info.draft);
        } else if (this.draftId) {
            this.draftId = null;
            this.reset();
        }
    }

    get today() {
        return DateTime.now().toISODate();
    }

    restoreDraft(draft) {
        this.draftId = draft.id;
        Object.assign(this.state, {
            categoryId: draft.category_id || null,
            you_said: draft.you_said || "",
            understood: draft.understood || "",
            real_world_declared: Boolean(draft.real_world_declared),
            real_world_date: draft.real_world_date || this.today,
            formOpen: Boolean(draft.category_id || draft.you_said || draft.understood),
        });
    }

    get category() {
        return this.state.categoryId ? this.store["linkup.category"].get(this.state.categoryId) : null;
    }

    get exampleDoLabel() {
        return _t("What to say:") + " ";
    }

    get exampleDontLabel() {
        return _t("What not to say:") + " ";
    }

    get formTitle() {
        const category = this.category;
        return category?.reflet_title || category?.name || _t("Choose a category");
    }

    /** The draft as a card, for the preview. */
    get previewReflet() {
        return {
            kind: "initial",
            state: "draft",
            category_id: this.category,
            you_said: this.state.you_said.trim(),
            understood: this.state.understood.trim(),
            body_text: false,
            author: this.store.self,
            recipient: this.recipientPersona,
        };
    }

    /** @param {import("models").LinkupCategory} category */
    onSelectCategory(category) {
        this.state.categoryId = category.id;
        this.state.formOpen = true;
        this.state.error = null;
        this.state.notice = "";
        if (this.state.you_said || this.state.understood) {
            this.dirty = true;
            this.debouncedSave();
        }
    }

    onInput() {
        this.state.notice = "";
        this.dirty = true;
        this.debouncedSave();
    }

    togglePreview() {
        this.state.showPreview = !this.state.showPreview;
    }

    /** `Escape` folds the form; the draft stays on the server. */
    onFormKeydown(ev) {
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.state.formOpen = false;
        }
    }

    /**
     * Save the draft after the saves already started. Return its id.
     *
     * @returns {Promise<number>}
     */
    saveDraft() {
        this.debouncedSave.cancel();
        this.dirty = false;
        const next = this.saving.then(async () => {
            const vals = {
                category_id: this.state.categoryId || false,
                you_said: this.state.you_said,
                understood: this.state.understood,
                real_world_declared: this.state.real_world_declared,
                real_world_date: this.state.real_world_declared ? this.state.real_world_date || false : false,
            };
            this.draftId = await this.orm.silent.call("linkup.reflet", "action_save_draft", [vals]);
            return this.draftId;
        });
        this.saving = next.catch(() => {});
        return next;
    }

    /** The first missing piece of the reflection, checked before the server does. */
    validate() {
        if (!this.category) {
            return {field: "category_id"};
        }
        if (!this.state.you_said.trim()) {
            return {field: "you_said", ref: this.youSaidRef};
        }
        if (!this.state.understood.trim()) {
            return {field: "understood", ref: this.understoodRef};
        }
        if (this.needsRealWorld && !this.state.real_world_declared) {
            return {field: "real_world_declared", ref: this.realWorldRef};
        }
        return null;
    }

    /** @param {Error} error */
    showError(error) {
        const info = linkupErrorInfo(error);
        if (!info) {
            throw error;
        }
        this.state.error = info;
    }

    async send() {
        if (this.state.sending) {
            return;
        }
        this.state.error = null;
        this.state.notice = "";
        const missing = this.validate();
        if (missing) {
            this.state.error = {
                code: "linkup.validation",
                field: missing.field,
                message: linkupFieldMessage(missing.field),
            };
            missing.ref?.el?.focus();
            return;
        }
        this.state.sending = true;
        const target = this.sendTarget;
        try {
            const draftId = await this.saveDraft();
            const result = target.invite
                ? await this.orm.silent.call("linkup.reflet", "action_send", [[draftId]], {
                      invite: target.invite,
                  })
                : await this.orm.silent.call("linkup.reflet", "action_send", [[draftId], target.recipientId]);
            this.draftId = null;
            this.reset();
            linkupPlaySound(this.env.services, "linkup-sent");
            this.state.notice = this.sentNotice(target, result);
            this.afterSend(target, result);
        } catch (error) {
            this.showError(error);
        } finally {
            this.state.sending = false;
        }
    }

    /** Delete the draft and fold the form. */
    async cancel() {
        this.debouncedSave.cancel();
        this.dirty = false;
        this.state.error = null;
        await this.saving;
        const draftId = this.draftId;
        this.draftId = null;
        this.reset();
        if (draftId) {
            try {
                await this.orm.silent.call("linkup.reflet", "action_discard_draft", [[draftId]]);
            } catch (error) {
                this.showError(error);
            }
        }
    }

    reset() {
        Object.assign(this.state, {
            formOpen: false,
            categoryId: null,
            you_said: "",
            understood: "",
            real_world_declared: false,
            real_world_date: this.today,
            showPreview: false,
        });
    }
}
