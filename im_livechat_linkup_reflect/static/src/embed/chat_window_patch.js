import {ChatWindow} from "@mail/core/common/chat_window";
import {htmlToTextContentInline} from "@mail/utils/common/format";

import {toRaw, useEffect, useState} from "@odoo/owl";

import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";

import {linkupFetchLivechatInfo} from "../common/livechat_reflet";
import {LinkupLivechatHelp} from "./help_now";

/** The welcome conversations whose information the widget read. */
const LINKUP_INFO_READ = new WeakSet();

patch(ChatWindow, {
    components: {...ChatWindow.components, LinkupLivechatHelp},
});

/**
 * The chat window of the widget, for a conversation of LinkUp:
 *
 * - the refusal of an answer by the reflection guide, in an alert above
 *   the composer (`Chatbot.linkupError`);
 * - "Need help now" under the composer of a welcome conversation, the
 *   conversation not saved yet included; a conversation of distress
 *   already holds a person of the moderation, and keeps the help only
 *   while its panel is open;
 * - a polite live region, outside the screen, that reads the newest
 *   message of the chatbot or of the other person, so that a screen
 *   reader hears each step of the guide as it comes.
 *
 * A saved welcome conversation reads its start rule and its parties once
 * its window shows, a reloaded page included.
 */
patch(ChatWindow.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkupLivechat = useState(useService("im_livechat.livechat"));
        useEffect(
            (thread, kind) => {
                const raw = thread && toRaw(thread);
                if (kind !== "welcome" || thread.id < 0 || LINKUP_INFO_READ.has(raw)) {
                    return;
                }
                LINKUP_INFO_READ.add(raw);
                linkupFetchLivechatInfo(this.store, thread).catch(() => {});
            },
            () => [this.thread, this.thread?.linkup_livechat_kind]
        );
    },

    get linkupShowHelp() {
        const thread = this.thread;
        return Boolean(
            thread?.channel_type === "livechat" &&
                this.linkupLivechat.linkupKind === "welcome" &&
                (thread.linkup_livechat_kind !== "distress" || this.linkupLivechat.linkupHelp.open)
        );
    },

    get linkupChatbotError() {
        return this.thread?.chatbot?.linkupError || "";
    },

    get linkupAnnouncement() {
        const thread = this.thread;
        if (thread?.channel_type !== "livechat") {
            return "";
        }
        const message = thread.messages.filter((message) => !message.isSelfAuthored && !message.isEmpty).at(-1);
        return message ? htmlToTextContentInline(message.body || "") : "";
    },
});
