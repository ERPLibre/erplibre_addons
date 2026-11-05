import {onWillStart, useEffect, useRef, useState} from "@odoo/owl";

import {deserializeDateTime, formatDate} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useDraggable} from "@web/core/utils/draggable";
import {useService} from "@web/core/utils/hooks";
import {imageUrl} from "@web/core/utils/urls";

import {LinkupCategoryIcon} from "@mail_linkup_reflet/core/common/linkup_category_icon";
import {LinkupErrorAlert} from "@mail_linkup_reflet/core/common/linkup_error_alert";
import {linkupErrorInfo, linkupFieldMessage} from "@mail_linkup_reflet/core/common/linkup_errors";
import {LinkupHelpBar} from "@mail_linkup_reflet/core/common/help_bar";
import {LinkupProfileMenu} from "@mail_linkup_reflet/core/common/linkup_profile_menu";
import {linkupPlaySound} from "@mail_linkup_reflet/core/common/linkup_signals";
import {LinkupRefletCard} from "@mail_linkup_reflet/core/common/reflet_card";
import {LinkupRefletFormBase} from "@mail_linkup_reflet/core/common/reflet_form";

/**
 * The Reflet view (client action `linkup.reflet_view`): the member, the
 * Help bar, the zone of the card and the contacts of the member, as given
 * by `linkup.reflet.linkup_reflet_view_info`.
 *
 * Choosing a category opens the card of the draft, with the form "You told
 * me / I understood that" (`reflet_form.js`); choosing a contact makes it
 * the recipient. Dropping a category on a contact does both and gives the
 * focus to the first empty text. The keyboard reaches the same result: the
 * Help bar is a toolbar, each contact a button, and "Send to…" opens the
 * list of the contacts, walked with the arrow keys, where `Enter` chooses
 * the recipient and sends, and `Escape` closes. Each contact opens its
 * direct conversation in Discuss. Once a card is sent, the focus goes to
 * the link to the conversation it went to, so the keyboard never falls
 * back to the top of the page.
 *
 * The avatar of the member shines while someone puts them in the light
 * (`linkup.highlight`), with the avatars of the first three senders, and
 * each of these contacts shines in the list. The "?" button of the Help
 * bar turns the guide mode on for the whole view: "Send to…" then
 * explains itself, and the list of the contacts, which would send, closes.
 *
 * "+ NewLink" invites a person who is not a member (LU-F-020), in the
 * steps of the mock-up: the email address and a name only the member sees,
 * then the card of the same single draft, then the preview of the email,
 * which never holds the texts, with the sendings of the day. Dropping a
 * category on "+ NewLink" opens it on that category. Once sent, the view
 * shows the masked address the server gives back, the same whoever holds
 * it, the card waiting for the signup, and "Send the link again" and
 * "Cancel the invitation"; a cancelled invitation gives the card back as
 * the draft. The invitations still waiting are listed under the
 * contacts, each one opening that last step. The action context
 * `linkup_newlink` opens the view on the first step.
 *
 * The reflections the member sent and that still wait for their
 * recipient stay in the view (LU-F-010 RM2), each card offering to
 * withdraw it while it is unread (LU-F-019). The avatar of the member opens
 * the menu of their settings (`LinkupProfileMenu`, LU-F-080).
 *
 * The happiness field, at the bottom, puts a contact in the light
 * (`linkup.highlight.action_send`, LU-F-051): dropped onto a contact, or,
 * without a pointer, through "You add to my happiness", which opens the
 * list of the contacts, walked with the arrow keys, where `Enter` chooses
 * and `Escape` closes. A contact the member puts in the light carries a
 * sun.
 *
 * @extends {LinkupRefletFormBase<{}, Env>}
 */
export class LinkupRefletView extends LinkupRefletFormBase {
    static template = "mail_linkup_reflet.LinkupRefletView";
    static components = {
        ...LinkupRefletFormBase.components,
        LinkupCategoryIcon,
        LinkupErrorAlert,
        LinkupHelpBar,
        LinkupProfileMenu,
        LinkupRefletCard,
    };
    static props = ["*"];

    setup() {
        super.setup();
        this.action = useService("action");
        this.root = useRef("root");
        this.pickerRef = useRef("picker");
        this.sendToRef = useRef("sendTo");
        this.sentRef = useRef("sent");
        this.newlinkRef = useRef("newlink");
        this.newlinkEmailRef = useRef("newlinkEmail");
        this.newlinkStatusRef = useRef("newlinkStatus");
        this.happinessRef = useRef("happiness");
        this.happinessListRef = useRef("happinessList");
        this.guide = useState(useService("linkup.guide"));
        /** What the next rendering gives the focus to: `field`, `picker`, `sendTo` or `sent`. */
        this.focusTarget = null;
        onWillStart(() => {
            this.load();
        });
        useEffect(
            () => this.applyFocus(),
            () => [this.state.focusRequest]
        );
        useEffect(
            (guideActive) => {
                if (guideActive && this.state.pickerOpen) {
                    this.state.pickerOpen = false;
                }
                if (guideActive && this.state.happinessOpen) {
                    this.state.happinessOpen = false;
                }
            },
            () => [this.guide.active]
        );
        useDraggable({
            ref: this.root,
            elements: ".o-linkup-RefletView-happiness",
            cursor: "grabbing",
            onDrag: ({x, y}) => {
                this.state.hoverUserId = this.contactAt(x, y)?.user_id || null;
            },
            onDragEnd: () => {
                this.state.hoverUserId = null;
            },
            onDrop: ({x, y}) => {
                const contact = this.contactAt(x, y);
                if (contact) {
                    this.highlightContact(contact);
                }
            },
        });
        useDraggable({
            ref: this.root,
            elements: ".o-linkup-HelpBar-category",
            cursor: "grabbing",
            onDrag: ({x, y}) => {
                this.state.hoverUserId = this.contactAt(x, y)?.user_id || null;
                this.state.hoverNewlink = this.isOverNewlink(x, y);
            },
            onDragEnd: () => {
                this.state.hoverUserId = null;
                this.state.hoverNewlink = false;
            },
            onDrop: ({element, x, y}) => {
                const category = this.store.linkupCategories.find((record) => record.code === element.dataset.code);
                if (!category) {
                    return;
                }
                if (this.isOverNewlink(x, y)) {
                    this.startNewlink(category);
                    return;
                }
                const contact = this.contactAt(x, y);
                if (contact) {
                    this.chooseCategoryAndContact(category, contact);
                }
            },
        });
    }

    extraState() {
        return {
            loaded: false,
            loadError: false,
            contacts: [],
            recipientUserId: null,
            pickerOpen: false,
            pickerIndex: 0,
            hoverUserId: null,
            lastSent: null,
            focusRequest: 0,
            hoverNewlink: false,
            /** The NewLink in progress: `{step, email, name, invitation}`, or `null`. */
            newlink: null,
            newlinkInfo: {invitations: [], quota: null, expiry_days: 0},
            newlinkBusy: false,
            sentIds: [],
            happinessOpen: false,
            happinessIndex: 0,
            happinessBusy: false,
            happinessError: null,
            happinessNotice: "",
        };
    }

    /** Read the categories, the contacts and the draft of the member. */
    async load() {
        this.state.loadError = false;
        try {
            const [info] = await Promise.all([this.fetchInfo(), this.store.fetchLinkupCategories()]);
            this.applyInfo(info);
            if (!this.state.loaded) {
                this.state.loaded = true;
                if (info.draft && !this.state.formOpen) {
                    this.restoreDraft(info.draft);
                }
                if (this.props.action?.context?.linkup_newlink && !this.state.newlink) {
                    this.startNewlink();
                }
            }
        } catch {
            this.state.loadError = true;
        }
    }

    get isLoaded() {
        return this.state.loaded;
    }

    fetchInfo() {
        return this.orm.silent.call("linkup.reflet", "linkup_reflet_view_info", []);
    }

    applyInfo(info) {
        if (info.store) {
            this.store.insert(info.store);
        }
        this.state.sentIds = info.sent_ids || [];
        this.state.contacts = info.contacts;
        if (info.newlink) {
            this.state.newlinkInfo = info.newlink;
        }
        if (!this.recipient) {
            this.state.recipientUserId = null;
        }
    }

    /** @returns {Object|undefined} the chosen contact */
    get recipient() {
        return this.state.contacts.find((contact) => contact.user_id === this.state.recipientUserId);
    }

    get recipientName() {
        return this.recipient?.name || "";
    }

    get recipientPersona() {
        if (this.state.newlink) {
            return {name: this.newlinkName};
        }
        return this.recipient ? {name: this.recipient.name} : null;
    }

    get needsRealWorld() {
        return Boolean(this.state.newlink || this.recipient?.needs_real_world);
    }

    get formId() {
        return "reflet-view";
    }

    get sendTarget() {
        const newlink = this.state.newlink;
        if (newlink) {
            return {
                invite: {email: newlink.email.trim(), name: newlink.name.trim()},
                name: this.newlinkName,
            };
        }
        const contact = this.recipient;
        return {recipientId: contact.user_id, name: contact.name, contact};
    }

    afterSend(target, result) {
        if (target.invite) {
            Object.assign(this.state.newlink, {step: "sent", invitation: result});
            this.state.notice = "";
            this.requestFocus("newlinkStatus");
        } else {
            this.state.lastSent = target.contact;
            this.state.recipientUserId = null;
            // The form folds with the focus it held: the link of the card
            // sent takes it, from the send button as from "Send to…".
            this.requestFocus("sent");
        }
        this.load();
    }

    sentNotice(target, result) {
        if (target.invite) {
            return _t("Invitation sent to %(email)s.", {email: result.email});
        }
        return super.sentNotice(target, result);
    }

    /** The recipient is checked after the category, before the texts; NewLink has none. */
    validate() {
        const missing = super.validate();
        if (missing?.field === "category_id" || this.state.newlink) {
            return missing;
        }
        if (!this.recipient) {
            return {field: "recipient_id", ref: this.sendToRef};
        }
        return missing;
    }

    get sendLabel() {
        return this.state.newlink ? _t("Next: the preview") : "";
    }

    get cancelLabel() {
        return this.state.newlink ? _t("Back") : "";
    }

    /** In NewLink, the form goes on to the preview, which sends. */
    async send() {
        if (this.state.newlink?.step === "reflet") {
            return this.newlinkPreview();
        }
        return super.send();
    }

    /** In NewLink, the cancel button of the form goes back to the address; the draft stays. */
    async cancel() {
        if (this.state.newlink?.step === "reflet") {
            this.state.error = null;
            this.state.newlink.step = "contact";
            this.requestFocus("newlinkEmail");
            return;
        }
        return super.cancel();
    }

    get helpLabel() {
        if (this.state.newlink) {
            return _t("HELP — What did %(name)s tell you about?", {name: this.newlinkName});
        }
        if (this.recipient) {
            return _t("HELP — What did %(name)s tell you about?", {
                name: this.recipient.name,
            });
        }
        return _t("HELP — What were you told about?");
    }

    get recipientLabel() {
        return _t("To: %(name)s", {name: this.recipient.name});
    }

    get selfAvatarUrl() {
        return this.store.self?.avatarUrl;
    }

    /** @param {Object} contact */
    avatarUrl(contact) {
        return imageUrl("res.partner", contact.partner_id, "avatar_128");
    }

    /** The active highlights the member received, the most recent first. */
    get highlights() {
        return this.store.linkupHighlightsReceived;
    }

    get highlightsLabel() {
        const names = this.highlights.map((highlight) => highlight.sender?.name).filter(Boolean);
        return _t("Who adds to your happiness: %(names)s", {names: names.join(", ")});
    }

    get hint() {
        return _t(
            "Choose what you were told about, then the person on the right. You can also drag a category onto a person."
        );
    }

    get highlightsMore() {
        return _t("and %(count)s more", {count: this.highlights.length - 3});
    }

    /**
     * Whether the contact put the member in the light.
     *
     * @param {Object} contact
     */
    isHighlightedBy(contact) {
        return this.highlights.some((highlight) => highlight.sender?.id === contact.partner_id);
    }

    /** @param {Object} contact */
    highlightLabel(contact) {
        return _t("%(name)s adds to your happiness", {name: contact.name});
    }

    /** @param {Object} contact */
    unreadLabel(contact) {
        return _t("%(count)s unread", {count: contact.unread_count});
    }

    /** @param {Object} contact */
    openChatLabel(contact) {
        return _t("Open the conversation with %(name)s", {name: contact.name});
    }

    /** @param {Object} contact */
    pickerOptionId(contact) {
        return `o-linkup-RefletView-option-${contact.user_id}`;
    }

    get pickerActiveId() {
        const contact = this.state.contacts[this.state.pickerIndex];
        return contact ? this.pickerOptionId(contact) : undefined;
    }

    /**
     * The card of a category opens with the focus in its first empty text,
     * whether the category is clicked or chosen with the keyboard, as when
     * it is dropped on a contact. While NewLink asks for the address, the
     * card is not shown and the focus stays.
     *
     * @param {import("models").LinkupCategory} category
     */
    onSelectCategory(category) {
        super.onSelectCategory(category);
        this.state.lastSent = null;
        if (!this.state.newlink || this.state.newlink.step === "reflet") {
            this.requestFocus("field");
        }
    }

    /** @param {Object} contact */
    selectRecipient(contact) {
        this.state.recipientUserId = contact.user_id;
        this.state.lastSent = null;
        this.state.notice = "";
        if (this.state.error?.field === "recipient_id") {
            this.state.error = null;
        }
    }

    /**
     * The drop of a category on a contact: the card of that category, for
     * that contact, with the focus in its first empty text.
     */
    chooseCategoryAndContact(category, contact) {
        this.selectRecipient(contact);
        this.onSelectCategory(category);
        this.requestFocus("field");
    }

    /** The contact whose row holds the point `(x, y)` of the viewport. */
    contactAt(x, y) {
        for (const el of this.root.el?.querySelectorAll(".o-linkup-RefletView-contact") || []) {
            const rect = el.getBoundingClientRect();
            if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
                const userId = Number(el.dataset.userId);
                return this.state.contacts.find((contact) => contact.user_id === userId);
            }
        }
        return null;
    }

    // ------------------------------------------------------------------
    // Sent reflections
    // ------------------------------------------------------------------

    /** The initial reflections of the member still waiting for their recipient. */
    get sentReflets() {
        return this.state.sentIds.map((id) => this.store["linkup.reflet"].get(id)).filter(Boolean);
    }

    /** A withdrawal reads the view again: the card leaves the list. */
    onSentAction() {
        this.load();
    }

    // ------------------------------------------------------------------
    // You add to my happiness
    // ------------------------------------------------------------------

    /**
     * Whether the member puts the contact in the light.
     *
     * @param {Object} contact
     */
    isHighlightedByMe(contact) {
        const persona = this.store.Persona.get({type: "partner", id: contact.partner_id});
        return Boolean(persona && this.store.linkupHighlightSentTo(persona));
    }

    /** @param {Object} contact */
    highlightedByMeLabel(contact) {
        return _t("You put %(name)s in the light", {name: contact.name});
    }

    get happinessHint() {
        return _t("Drag onto a person, or choose one, to thank them for an exchange that did you good.");
    }

    /** @param {Object} contact */
    happinessOptionId(contact) {
        return `o-linkup-RefletView-happinessOption-${contact.user_id}`;
    }

    get happinessActiveId() {
        const contact = this.state.contacts[this.state.happinessIndex];
        return contact ? this.happinessOptionId(contact) : undefined;
    }

    openHappiness() {
        if (this.guide.active || !this.state.contacts.length) {
            return;
        }
        this.state.happinessIndex = 0;
        this.state.happinessOpen = true;
        this.state.happinessError = null;
        this.requestFocus("happinessList");
    }

    closeHappiness() {
        this.state.happinessOpen = false;
        this.requestFocus("happiness");
    }

    /**
     * Put a contact in the light: the same as the press of the LinkUp
     * panel, from a person instead of a conversation. A highlight already
     * active is left as it is.
     *
     * @param {Object} contact
     */
    async highlightContact(contact) {
        if (this.guide.active || this.state.happinessBusy) {
            return;
        }
        this.state.happinessOpen = false;
        this.state.happinessBusy = true;
        this.state.happinessError = null;
        this.state.happinessNotice = "";
        try {
            await this.orm.silent.call("linkup.highlight", "action_send", [contact.user_id]);
            this.state.happinessNotice = _t("%(name)s sees your avatar on theirs until your next exchange.", {
                name: contact.name,
            });
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.happinessError = info;
        } finally {
            this.state.happinessBusy = false;
        }
        this.requestFocus("happiness");
    }

    /** @param {KeyboardEvent} ev */
    onHappinessKeydown(ev) {
        const count = this.state.contacts.length;
        let index = this.state.happinessIndex;
        switch (ev.key) {
            case "ArrowDown":
                index = (index + 1) % count;
                break;
            case "ArrowUp":
                index = (index - 1 + count) % count;
                break;
            case "Home":
                index = 0;
                break;
            case "End":
                index = count - 1;
                break;
            case "Enter":
            case " ":
                ev.preventDefault();
                ev.stopPropagation();
                if (this.state.contacts[index]) {
                    this.highlightContact(this.state.contacts[index]);
                }
                return;
            case "Escape":
                ev.preventDefault();
                ev.stopPropagation();
                this.closeHappiness();
                return;
            default:
                return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.state.happinessIndex = index;
    }

    // ------------------------------------------------------------------
    // NewLink
    // ------------------------------------------------------------------

    /** The name of the invited person, as the member gave it, or a placeholder. */
    get newlinkName() {
        return this.state.newlink?.name.trim() || _t("this person");
    }

    get newlinkStepLabel() {
        const steps = {
            contact: [1, _t("Contact")],
            reflet: [2, _t("Reflection")],
            preview: [3, _t("Preview")],
        };
        const step = steps[this.state.newlink?.step];
        return step ? _t("Step %(index)s of 3 · %(name)s", {index: step[0], name: step[1]}) : "";
    }

    get newlinkQuota() {
        return this.state.newlinkInfo.quota;
    }

    get newlinkAtCap() {
        const quota = this.newlinkQuota;
        return Boolean(quota) && quota.used >= quota.max;
    }

    get newlinkQuotaLabel() {
        const quota = this.newlinkQuota;
        return quota ? _t("Invitations today: %(used)s of %(max)s", {used: quota.used, max: quota.max}) : "";
    }

    get newlinkMailSubject() {
        return _t("%(name)s would like to make you a reflection on LinkUp", {name: this.store.self?.name || ""});
    }

    get newlinkMailIntro() {
        return _t("A person you met, %(name)s, would like to make you a reflection on LinkUp.", {
            name: this.store.self?.name || "",
        });
    }

    get newlinkMailValidity() {
        return _t("Personal link, valid %(count)s days, for a single signup.", {
            count: this.state.newlinkInfo.expiry_days || 14,
        });
    }

    get newlinkNoText() {
        return _t(
            "The text of your reflection is not in the email: %(name)s reads it in LinkUp after signing up through this link.",
            {name: this.newlinkName}
        );
    }

    get newlinkRefletTitle() {
        return _t("What did %(name)s tell you about during your exchange in person?", {name: this.newlinkName});
    }

    get pendingInvitations() {
        return this.state.newlinkInfo.invitations || [];
    }

    /** @param {Object} invitation as `linkup.invitation._linkup_info` gives it */
    invitationLabel(invitation) {
        return invitation.name || invitation.email;
    }

    /** @param {Object} invitation */
    invitationCategory(invitation) {
        const code = invitation.reflet?.category_code;
        return code ? this.store.linkupCategories.find((category) => category.code === code) : null;
    }

    /** @param {Object} invitation */
    invitationExpiry(invitation) {
        return _t("Expires on %(date)s. The content of the reflection is erased the day after.", {
            date: formatDate(deserializeDateTime(invitation.expiry_date)),
        });
    }

    get newlinkNoConversation() {
        return _t(
            "No conversation exists yet with %(name)s. When the person signs up through this link, the reflection reaches them unread; the chat opens once they confirm it.",
            {name: this.newlinkName}
        );
    }

    /** Whether the point `(x, y)` of the viewport is over "+ NewLink". */
    isOverNewlink(x, y) {
        const rect = this.newlinkRef.el?.getBoundingClientRect();
        return Boolean(rect) && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
    }

    /**
     * Open NewLink on its first step, keeping the draft; a category dropped
     * on "+ NewLink" opens its card.
     *
     * @param {import("models").LinkupCategory} [category]
     */
    startNewlink(category) {
        if (this.guide.active) {
            return;
        }
        this.state.newlink = {step: "contact", email: "", name: "", invitation: null};
        Object.assign(this.state, {
            recipientUserId: null,
            pickerOpen: false,
            lastSent: null,
            notice: "",
            error: null,
        });
        if (category) {
            super.onSelectCategory(category);
        }
        this.requestFocus("newlinkEmail");
    }

    closeNewlink() {
        this.state.newlink = null;
        this.state.error = null;
    }

    /** From the address to the card: a plausible address is required, the server checks it again. */
    newlinkNext() {
        this.state.error = null;
        const email = this.state.newlink.email.trim();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            this.state.error = {code: "linkup.validation", field: "email", message: linkupFieldMessage("email")};
            this.requestFocus("newlinkEmail");
            return;
        }
        this.state.newlink.step = "reflet";
        if (this.state.formOpen) {
            this.requestFocus("field");
        }
    }

    /** From the card to the preview, once the card is complete and saved. */
    async newlinkPreview() {
        this.state.error = null;
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
        try {
            await this.saveDraft();
        } catch (error) {
            this.showError(error);
            return;
        }
        this.state.newlink.step = "preview";
    }

    newlinkBackToCard() {
        this.state.error = null;
        this.state.newlink.step = "reflet";
    }

    /** Send the invitation of the preview: the sending of the form, to an address. */
    sendInvitation() {
        return super.send();
    }

    /** @param {Object} invitation */
    openInvitation(invitation) {
        if (this.guide.active) {
            return;
        }
        this.state.newlink = {step: "sent", email: "", name: invitation.name, invitation};
        this.state.error = null;
        this.state.notice = "";
        this.requestFocus("newlinkStatus");
    }

    /** Run an action of the invitation shown, then read the view again. */
    async invitationAction(method) {
        const invitation = this.state.newlink?.invitation;
        if (!invitation || this.state.newlinkBusy) {
            return null;
        }
        this.state.newlinkBusy = true;
        this.state.error = null;
        try {
            return await this.orm.silent.call("linkup.invitation", method, [[invitation.id]]);
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.error = info;
            return null;
        } finally {
            this.state.newlinkBusy = false;
            this.load();
        }
    }

    async resendInvitation() {
        const result = await this.invitationAction("action_resend");
        if (result) {
            this.state.newlink.invitation = result;
            this.state.notice = _t("Link sent again.");
            linkupPlaySound(this.env.services, "linkup-sent");
        }
    }

    async cancelInvitation() {
        const result = await this.invitationAction("action_cancel");
        if (result !== null) {
            this.state.newlink.step = "cancelled";
            this.state.notice = "";
            this.requestFocus("newlinkStatus");
        }
    }

    /** Leave NewLink on the draft a cancelled invitation gave back. */
    async resumeDraft() {
        this.closeNewlink();
        this.draftId = null;
        await this.reloadDraft();
        this.requestFocus("field");
    }

    /** @param {"field"|"picker"|"sendTo"|"sent"|"newlinkEmail"|"newlinkStatus"|"happiness"|"happinessList"} target */
    requestFocus(target) {
        this.focusTarget = target;
        this.state.focusRequest++;
    }

    applyFocus() {
        const target = this.focusTarget;
        this.focusTarget = null;
        if (target === "picker") {
            this.pickerRef.el?.focus();
        } else if (target === "sendTo") {
            this.sendToRef.el?.focus();
        } else if (target === "sent") {
            this.sentRef.el?.focus();
        } else if (target === "newlinkEmail") {
            this.newlinkEmailRef.el?.focus();
        } else if (target === "newlinkStatus") {
            this.newlinkStatusRef.el?.focus();
        } else if (target === "happiness") {
            this.happinessRef.el?.focus();
        } else if (target === "happinessList") {
            this.happinessListRef.el?.focus();
        } else if (target === "field") {
            const declaration = this.state.error?.field === "real_world_declared" && this.realWorldRef.el;
            const field = [this.youSaidRef.el, this.understoodRef.el].find((el) => el && !el.value.trim());
            (declaration || field || this.youSaidRef.el)?.focus();
        }
    }

    openPicker() {
        const index = this.state.contacts.findIndex((contact) => contact.user_id === this.state.recipientUserId);
        this.state.pickerIndex = Math.max(index, 0);
        this.state.pickerOpen = true;
        this.requestFocus("picker");
    }

    closePicker() {
        this.state.pickerOpen = false;
        this.requestFocus("sendTo");
    }

    /**
     * Choose the recipient in the list, then send the card. The list goes
     * away with the focus it held: the focus then moves to the link of the
     * card sent, to the field to correct, such as the declaration of the
     * exchange in person that the chosen contact requires, or back to
     * "Send to…". In guide mode, nothing is chosen.
     */
    async pick(contact) {
        if (this.guide.active) {
            return;
        }
        this.selectRecipient(contact);
        this.state.pickerOpen = false;
        await this.send();
        if (!this.state.formOpen) {
            this.requestFocus("sent");
        } else if (this.state.error?.code === "linkup.validation") {
            this.requestFocus("field");
        } else {
            this.requestFocus("sendTo");
        }
    }

    /** @param {KeyboardEvent} ev */
    onPickerKeydown(ev) {
        const count = this.state.contacts.length;
        let index = this.state.pickerIndex;
        switch (ev.key) {
            case "ArrowDown":
                index = (index + 1) % count;
                break;
            case "ArrowUp":
                index = (index - 1 + count) % count;
                break;
            case "Home":
                index = 0;
                break;
            case "End":
                index = count - 1;
                break;
            case "Enter":
            case " ":
                ev.preventDefault();
                ev.stopPropagation();
                if (this.state.contacts[index]) {
                    this.pick(this.state.contacts[index]);
                }
                return;
            case "Escape":
                ev.preventDefault();
                ev.stopPropagation();
                this.closePicker();
                return;
            default:
                return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.state.pickerIndex = index;
    }

    /**
     * Whether a contact has a direct conversation to open: one the member
     * belongs to, or a confirmed link, with which the server opens it. Any
     * other conversation is opened by the server, to carry a reflection:
     * the one of a reflection just sent exists, and opens.
     *
     * @param {Object} contact
     */
    canOpenConversation(contact) {
        return Boolean(contact.channel_id) || contact.link_state === "active";
    }

    /**
     * Open the direct conversation of a contact in Discuss, creating it when
     * the member does not belong to it yet. A refusal of the server, the
     * list being stale, reads the contacts again.
     */
    async openConversation(contact) {
        let channelId = contact.channel_id;
        if (!channelId) {
            try {
                const chat = await this.store.getChat({partnerId: contact.partner_id});
                channelId = chat?.id;
            } catch {
                this.load();
                return;
            }
        }
        if (channelId) {
            await this.action.doAction({
                type: "ir.actions.client",
                tag: "mail.action_discuss",
                context: {active_id: `discuss.channel_${channelId}`},
            });
        }
    }
}

registry.category("actions").add("linkup.reflet_view", LinkupRefletView);
