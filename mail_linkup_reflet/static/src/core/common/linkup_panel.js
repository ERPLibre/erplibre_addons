import {ActionPanel} from "@mail/discuss/core/common/action_panel";

import {Component, onWillStart, onWillUpdateProps, useEffect, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {deserializeDateTime, formatDate} from "@web/core/l10n/dates";
import {useService} from "@web/core/utils/hooks";
import {debounce} from "@web/core/utils/timing";

import {LinkupErrorAlert} from "./linkup_error_alert";
import {linkupErrorInfo} from "./linkup_errors";
import {LinkupRefletCard, linkupStateLabel} from "./reflet_card";
import {LinkupSafetyActions} from "./linkup_safety";

/** The states the history filters on, in their order in the list. */
export const LINKUP_HISTORY_STATES = ["sent", "confirmed", "inaccurate", "rejected", "expired", "withdrawn"];

/**
 * The LinkUp panel of a direct conversation: the link with the other
 * member and the history of the reflections of the pair (LU-F-018), sent
 * and received, filtered by visible category and by state
 * (`linkup.reflet.linkup_history`). A hidden theme is never a visible
 * category: a precision whose theme is still to guess matches no
 * category.
 *
 * The panel also holds "You add to my happiness" (LU-F-050): a press asks
 * for a confirmation, then puts the other member in the light
 * (`linkup.highlight.action_send`), until their next exchange or until the
 * member withdraws it; a highlight the other member gave shows here, with
 * a button to hide it.
 *
 * The panel also blocks the other member, or unblocks them for the member
 * who blocked them (`LinkupSafetyActions`); a block the other member holds
 * is never shown.
 *
 * The cards are records of the Store, so a change sent over the bus shows
 * at once. The state of the link is read again when the state of a
 * reflection of the conversation changes, since a confirmation, a
 * rejection or an expiry moves it.
 *
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @extends {Component<Props, Env>}
 */
export class LinkupPanel extends Component {
    static template = "mail_linkup_reflet.LinkupPanel";
    static components = {ActionPanel, LinkupErrorAlert, LinkupRefletCard, LinkupSafetyActions};
    static props = ["thread", "className?"];

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
        this.orm = useService("orm");
        this.state = useState({
            info: null,
            loadError: false,
            confirmHighlight: false,
            highlightBusy: false,
            highlightError: null,
            historyCategoryId: "",
            historyState: "",
            history: null,
            historyError: false,
        });
        this.reload = debounce(() => this.load(this.props.thread), 300);
        onWillStart(() => {
            this.store.fetchLinkupCategories().catch(() => {});
            this.load(this.props.thread);
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.thread.notEq(this.props.thread)) {
                this.load(nextProps.thread);
            }
        });
        let first = true;
        useEffect(
            () => {
                if (first) {
                    first = false;
                    return;
                }
                this.reload();
            },
            () => [this.refletSignature]
        );
    }

    /** States of the reflections carried by the loaded messages. */
    get refletSignature() {
        return this.props.thread.messages
            .map((message) => message.linkup_reflet_id)
            .filter(Boolean)
            .map((reflet) => `${reflet.id}:${reflet.state}`)
            .join(",");
    }

    /** @param {import("models").Thread} thread */
    async load(thread) {
        try {
            const info = await this.store.fetchLinkupChannelInfo(thread.id);
            if (this.props.thread.eq(thread)) {
                this.state.info = info;
                this.state.loadError = false;
            }
        } catch {
            this.state.loadError = true;
        }
        await this.loadHistory(thread);
    }

    /**
     * Read the history of the pair with the filters chosen, and insert its
     * cards in the Store.
     *
     * @param {import("models").Thread} [thread]
     */
    async loadHistory(thread = this.props.thread) {
        try {
            const history = await this.orm.silent.call("linkup.reflet", "linkup_history", [thread.id], {
                category_id: Number(this.state.historyCategoryId) || false,
                state: this.state.historyState || false,
            });
            if (history.store) {
                this.store.insert(history.store);
            }
            if (this.props.thread.eq(thread)) {
                this.state.history = history;
                this.state.historyError = false;
            }
        } catch {
            this.state.historyError = true;
        }
    }

    /** @param {Event} ev */
    onChangeHistoryCategory(ev) {
        this.state.historyCategoryId = ev.target.value;
        this.loadHistory();
    }

    /** @param {Event} ev */
    onChangeHistoryState(ev) {
        this.state.historyState = ev.target.value;
        this.loadHistory();
    }

    get historyCategories() {
        return this.store.linkupCategories;
    }

    get historyStates() {
        return LINKUP_HISTORY_STATES.map((state) => ({value: state, label: linkupStateLabel(state)}));
    }

    /** @param {import("models").LinkupCategory} category */
    isHistoryCategory(category) {
        return `${category.id}` === this.state.historyCategoryId;
    }

    get isHistoryFiltered() {
        return Boolean(this.state.historyCategoryId || this.state.historyState);
    }

    get name() {
        return this.props.thread.displayName;
    }

    get withLabel() {
        return _t("With %(name)s", {name: this.name});
    }

    get reflets() {
        return (this.state.history?.reflet_ids || []).map((id) => this.store["linkup.reflet"].get(id)).filter(Boolean);
    }

    get linkState() {
        return this.state.info?.link_state || "none";
    }

    get linkStateLabel() {
        switch (this.linkState) {
            case "pending":
                return _t("A reflection is waiting for an answer.");
            case "active": {
                const date = this.state.info.first_link_date;
                return date
                    ? _t("Confirmed link since %(date)s.", {
                          date: formatDate(deserializeDateTime(date)),
                      })
                    : _t("Confirmed link.");
            }
            case "closed":
                return _t("No link: no reflection was confirmed.");
        }
        return _t("No reflection exchanged yet.");
    }

    /** The other member of the conversation, as a persona of the Store. */
    get correspondent() {
        return this.props.thread.correspondent?.persona;
    }

    /** The active highlight of the member towards the other one. */
    get highlightSent() {
        const persona = this.correspondent;
        return persona ? this.store.linkupHighlightSentTo(persona) : undefined;
    }

    /** The active highlight the other member gave the member. */
    get highlightReceived() {
        const persona = this.correspondent;
        return persona ? this.store.linkupHighlightFrom(persona) : undefined;
    }

    get highlightSubtitle() {
        if (this.highlightSent) {
            return _t("%(name)s sees your avatar on theirs until your next exchange.", {name: this.name});
        }
        return _t("Thank %(name)s for an exchange that did you good.", {name: this.name});
    }

    get highlightQuestion() {
        return _t("Put %(name)s in the light?", {name: this.name});
    }

    get highlightExplanation() {
        return _t(
            "%(name)s will see your avatar on theirs until your next exchange, with the notification “%(me)s adds to your happiness”.",
            {name: this.name, me: this.store.self?.name || ""}
        );
    }

    get highlightReceivedLabel() {
        return _t("%(name)s adds to your happiness", {name: this.name});
    }

    onClickHighlight() {
        if (this.highlightSent) {
            return;
        }
        this.state.highlightError = null;
        this.state.confirmHighlight = true;
    }

    /**
     * Call a method of `linkup.highlight`, showing the message of a refusal.
     *
     * @param {string} method
     * @param {any[]} args
     */
    async callHighlight(method, args) {
        if (this.state.highlightBusy) {
            return;
        }
        this.state.highlightBusy = true;
        this.state.highlightError = null;
        try {
            await this.orm.silent.call("linkup.highlight", method, args);
            this.state.confirmHighlight = false;
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.highlightError = info;
        } finally {
            this.state.highlightBusy = false;
        }
    }

    sendHighlight() {
        return this.callHighlight("action_send", [this.state.info.recipient_id, this.props.thread.id]);
    }

    withdrawHighlight() {
        return this.callHighlight("action_withdraw", [[this.highlightSent.id]]);
    }

    dismissHighlight() {
        return this.callHighlight("action_dismiss", [[this.highlightReceived.id]]);
    }

    get safetyLabel() {
        return _t("Safety");
    }

    /** A block or an unblock changes what the panel shows of the link. */
    onSafetyChange() {
        this.load(this.props.thread);
    }

    get countLabel() {
        const count = this.state.info?.reflet_count || 0;
        return count === 1 ? _t("1 reflection") : _t("%(count)s reflections", {count});
    }
}
