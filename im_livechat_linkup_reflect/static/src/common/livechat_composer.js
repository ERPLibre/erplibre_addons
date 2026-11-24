import {Composer} from "@mail/core/common/composer";

import {_t} from "@web/core/l10n/translation";
import {rpc} from "@web/core/network/rpc";
import {patch} from "@web/core/utils/patch";

import {LinkupRefletComposer} from "@mail_linkup_reflet/core/common/reflet_composer";

import {LINKUP_LIVECHAT_ROUTES, linkupFetchLivechatInfo} from "./livechat_reflet";

/**
 * The reflection of a live chat conversation between a visitor and the
 * member who operates it (LU-F-127 RM2): the Help bar and the form of a
 * direct conversation, whose draft, sending and restoring go through the
 * routes of the live chat. The recipient is the other party of the
 * conversation; the draft restored is the single draft of the party, the
 * one the reflection guide wrote for a visitor. The exchange in person is
 * always declared, as for a first reflection.
 *
 * @extends {LinkupRefletComposer}
 */
export class LinkupLivechatRefletComposer extends LinkupRefletComposer {
    fetchChannelInfo(thread) {
        return linkupFetchLivechatInfo(this.store, thread);
    }

    get available() {
        return Boolean(this.state.info?.can_send);
    }

    get recipientName() {
        return this.state.info?.recipient_name || _t("the other person");
    }

    get recipientPersona() {
        return null;
    }

    get needsRealWorld() {
        return true;
    }

    get formId() {
        return `livechat-${this.props.thread.id}`;
    }

    get sendTarget() {
        return {name: this.recipientName, thread: this.props.thread};
    }

    saveDraftCall(vals) {
        return rpc(LINKUP_LIVECHAT_ROUTES.draft, {channel_id: this.props.thread.id, vals}, {silent: true});
    }

    sendCall(draftId, target) {
        return rpc(LINKUP_LIVECHAT_ROUTES.send, {channel_id: target.thread.id}, {silent: true});
    }

    /** A visitor keeps a single draft, which Cancel empties. */
    discardCall() {
        return this.saveDraftCall({
            category_id: false,
            you_said: "",
            understood: "",
            real_world_declared: false,
            real_world_date: false,
        });
    }
}

patch(Composer, {
    components: {...Composer.components, LinkupLivechatRefletComposer},
});

/**
 * The composer of a live chat conversation of LinkUp, for its visitor in
 * the widget and for the member who operates it in Discuss.
 *
 * The start rule of a welcome conversation binds both of them once a
 * member joined the visitor (`discuss.channel._linkup_start_rule_info`):
 * in strict mode, the text field gives way to the banner and "Make a
 * reflection", which opens the reflection; in incentive mode, the banner
 * sits above the text field. The reflection is folded at first: the
 * widget is narrow, and the banner opens it. A conversation of distress
 * has no start rule and no reflection.
 */
patch(Composer.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.thread?.channel_type === "livechat") {
            this.linkupState.open = false;
        }
    },

    /** A live chat conversation of LinkUp, outside an edition and the chatter. */
    get isLinkupLivechat() {
        const thread = this.thread;
        return Boolean(
            thread?.model === "discuss.channel" &&
                thread.channel_type === "livechat" &&
                thread.linkup_livechat_kind &&
                !this.props.composer.message &&
                !this.env.inChatter
        );
    },

    get hasLinkupLivechatReflet() {
        return this.isLinkupLivechat && Boolean(this.thread.linkup_can_reflect);
    },

    get linkupStartRule() {
        if (this.thread?.channel_type !== "livechat") {
            return super.linkupStartRule;
        }
        if (!this.isLinkupLivechat || this.thread.linkup_livechat_kind !== "welcome") {
            return null;
        }
        if (this.thread.linkupStartRuleLocked) {
            return "strict";
        }
        if (this.thread.linkupStartRuleSuggested) {
            return "incitative";
        }
        return null;
    },
});
