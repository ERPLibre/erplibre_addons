import {Thread} from "@mail/core/common/thread_model";

import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {_t} from "@web/core/l10n/translation";
import {rpc} from "@web/core/network/rpc";
import {patch} from "@web/core/utils/patch";

import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";
import {LinkupReflet} from "@mail_linkup_reflet/core/common/linkup_reflet_model";
import {LinkupSafetyActions} from "@mail_linkup_reflet/core/common/linkup_safety";
import {LinkupRefletActions} from "@mail_linkup_reflet/core/common/reflet_actions";
import {LinkupRefletCard} from "@mail_linkup_reflet/core/common/reflet_card";
import {linkupFetchNewMessages} from "@mail_linkup_reflet/core/common/store_service_patch";

/**
 * The routes of a reflection of a live chat conversation, by the action of
 * the card they stand for. They serve the visitor of the widget and the
 * member who operates the conversation alike: the server takes the party
 * from the cookie of the visitor or from the session, never from a
 * parameter.
 */
export const LINKUP_LIVECHAT_ROUTES = {
    info: "/linkup/v1/livechat/reflet/info",
    draft: "/linkup/v1/livechat/reflet/draft",
    send: "/linkup/v1/livechat/reflet/send",
    action_confirm: "/linkup/v1/livechat/reflet/confirm",
    action_reject: "/linkup/v1/livechat/reflet/reject",
};

/** Keys of the answer of the info route that describe the conversation. */
const LINKUP_LIVECHAT_THREAD_KEYS = [
    "linkup_start_rule",
    "linkup_start_rule_satisfied",
    "linkup_livechat_kind",
    "linkup_can_reflect",
];

/**
 * Read what a party reads of the reflections of the live chat conversation
 * `thread`: insert their cards, and keep on the thread its start rule and
 * whether a reflection may go between its two parties.
 *
 * @param {import("models").Store} store
 * @param {import("models").Thread} thread
 * @returns {Promise<Object>} the answer of the info route
 */
export async function linkupFetchLivechatInfo(store, thread) {
    const info = await rpc(LINKUP_LIVECHAT_ROUTES.info, {channel_id: thread.id}, {silent: true});
    if (info.store) {
        store.insert(info.store);
    }
    for (const key of LINKUP_LIVECHAT_THREAD_KEYS) {
        if (key in info) {
            thread[key] = info[key];
        }
    }
    return info;
}

/**
 * Read again the cards and the new messages of a live chat conversation
 * after an action, which the bus also brings.
 *
 * @param {import("models").Store} store
 * @param {import("models").Thread} thread
 */
export async function linkupRefreshLivechat(store, thread) {
    await Promise.all([linkupFetchLivechatInfo(store, thread), linkupFetchNewMessages(thread)]);
}

/**
 * A live chat conversation of LinkUp, as `discuss.channel` gives it:
 * `linkup_livechat_kind` is the role of its live chat channel (`welcome`
 * or `distress`), `linkup_can_reflect` tells that it holds a visitor and
 * a member who operates it, between whom a reflection may go.
 */
patch(Thread.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkup_livechat_kind = undefined;
        this.linkup_can_reflect = false;
    },
});

/** `livechat`: the reflection lives in a live chat conversation. */
patch(LinkupReflet.prototype, {
    setup() {
        super.setup(...arguments);
        this.livechat = false;
    },
});

/**
 * The card of a reflection of a live chat conversation, between a visitor
 * and a member (LU-F-127): its recipient confirms it or declares that the
 * exchange did not take place, through the routes of the live chat, and
 * nothing else. Such a reflection has no link, so no turn, no ignoring, no
 * "That is not what I said" and no withdrawal.
 */
patch(LinkupRefletActions.prototype, {
    get mode() {
        const reflet = this.reflet;
        if (!reflet.livechat) {
            return super.mode;
        }
        return reflet.kind === "initial" &&
            reflet.state === "sent" &&
            this.props.thread &&
            reflet.recipient?.eq(this.store.self)
            ? "validate"
            : null;
    },

    async call(method, args = []) {
        if (!this.reflet.livechat) {
            return super.call(method, args);
        }
        const route = LINKUP_LIVECHAT_ROUTES[method];
        const thread = this.props.thread;
        if (!route || !thread || this.state.busy) {
            return false;
        }
        this.lastCall = [method, args];
        this.state.busy = true;
        this.state.error = null;
        let done = false;
        try {
            await rpc(route, {channel_id: thread.id, reflet_id: this.reflet.id}, {silent: true});
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
        await linkupRefreshLivechat(this.store, thread).catch(() => {});
        this.props.onDone?.();
        return done;
    },

    /** The rejection of a live chat names the only other answer: the confirmation. */
    askReject() {
        if (!this.reflet.livechat) {
            return super.askReject();
        }
        if (this.state.busy) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("This exchange did not take place"),
            body: _t("Declare that the exchange of this reflection never took place? %(name)s will see it.", {
                name: this.authorName,
            }),
            confirmLabel: _t("This exchange did not take place"),
            confirmClass: "btn-danger o-linkup-RejectDialog-confirm",
            confirm: () => this.call("action_reject"),
            cancel: () => {},
        });
    },
});

/**
 * On a card of a live chat, only the member who operates the conversation
 * reports what the visitor sent; a visitor has no account to block, and
 * the visitor reports nothing from the widget. Its reading is not
 * recorded: nothing depends on it, the withdrawal not being offered.
 */
patch(LinkupRefletCard.prototype, {
    get needsRead() {
        return !this.reflet.livechat && super.needsRead;
    },

    get showSafety() {
        if (!this.reflet.livechat) {
            return super.showSafety;
        }
        return Boolean(
            this.props.interactive &&
                !this.props.compact &&
                !this.props.preview &&
                this.props.thread &&
                this.reflet.id &&
                this.reflet.author?.type === "guest" &&
                this.store.self?.type === "partner" &&
                this.role === "recipient" &&
                !this.isWithdrawn
        );
    },
});

/**
 * `livechatChannelId`: the report targets the visitor of this live chat
 * conversation (`linkup.report.action_report_livechat_visitor`), with
 * their last message; blocking does not apply to a visitor.
 */
LinkupSafetyActions.props = [...LinkupSafetyActions.props, "livechatChannelId?"];

patch(LinkupSafetyActions.prototype, {
    async sendReport() {
        if (!this.props.livechatChannelId) {
            return super.sendReport();
        }
        if (!this.state.reason) {
            this.state.error = {code: "linkup.validation", field: "reason", message: _t("Choose a reason.")};
            this.reasonRef.el?.focus();
            return;
        }
        const done = await this.run(() =>
            this.orm.silent.call("linkup.report", "action_report_livechat_visitor", [
                this.props.livechatChannelId,
                this.state.reason,
                this.state.description.trim() || null,
            ])
        );
        if (done) {
            this.state.reportOpen = false;
            this.state.reported = true;
        }
    },
});
