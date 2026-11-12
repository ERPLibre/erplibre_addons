import {Component, useEffect, useRef, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {rpc} from "@web/core/network/rpc";
import {useService} from "@web/core/utils/hooks";

import {LinkupErrorAlert} from "@mail_linkup_reflet/core/common/linkup_error_alert";
import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";
import {LinkupGuideButton} from "@mail_linkup_reflet/core/common/linkup_guide";
import {LinkupHelpNow} from "@mail_linkup_community/core/common/linkup_help_now";

/**
 * Press "Need help now" in the conversation of the widget (LU-F-126, Q-44).
 *
 * The help resources show at once, read from the server. A conversation
 * not saved yet is saved first, then `/linkup/v1/livechat/help_now`
 * creates the urgent report and brings an available moderator in no
 * conflict of interest, or posts the resources and leaves the report
 * waiting in the queue. Once a moderator joined, the chatbot is done: its
 * last step is the one of "Need help now", and the composer is free.
 * Beyond the limit of urgent reports an hour (`limited`), the server
 * creates no report and brings nobody: the status says that the request is
 * already with the moderation team.
 *
 * The state lives on the live chat service (`linkupHelp`), so that it
 * stays when the chat window of the conversation is replaced.
 *
 * @param {Object} env the environment of the widget
 * @param {import("models").Thread} thread
 */
export async function linkupPressHelpNow(env, thread) {
    const livechat = env.services["im_livechat.livechat"];
    const store = env.services["mail.store"];
    const help = livechat.linkupHelp;
    if (help.busy) {
        return;
    }
    Object.assign(help, {
        open: true,
        busy: true,
        error: null,
        found: false,
        status: _t("Looking for a person of the moderation…"),
    });
    store.fetchLinkupHelp().catch(() => {});
    try {
        let conversation = thread;
        if (!conversation || conversation.id < 0 || conversation.isTransient) {
            conversation = await livechat.persist();
        }
        if (!conversation) {
            help.status = "";
            help.error = {code: "linkup.unavailable", message: _t("The conversation could not be opened, try again.")};
            return;
        }
        const result = await rpc("/linkup/v1/livechat/help_now", {channel_id: conversation.id}, {silent: true});
        store.applyLinkupHelp(result);
        const {Message: messages = []} = store.insert(result.store || {}, {html: true});
        for (const message of messages) {
            conversation.messages.add(message);
        }
        help.found = Boolean(result.operator_found);
        if (result.limited) {
            help.status = _t("Your request is already with the moderation team.");
        } else if (help.found) {
            linkupEndChatbot(store, conversation, result.step_id, result.message_id);
            conversation.linkup_livechat_kind = "distress";
            help.status = _t("A person of the moderation joins you in this conversation.");
        } else {
            help.status = _t(
                "No person of the moderation is available right now. Your request waits in the queue, processed within %(hours)s hours.",
                {hours: result.urgent_hours}
            );
        }
    } catch (error) {
        const info = linkupErrorInfo(error);
        if (!info) {
            throw error;
        }
        help.status = "";
        help.error = info;
    } finally {
        help.busy = false;
    }
}

/**
 * End the chatbot of `thread` on the step of "Need help now", as the
 * server did: a moderator answers from now on.
 */
function linkupEndChatbot(store, thread, stepId, messageId) {
    const chatbot = thread.chatbot;
    if (!chatbot || !stepId) {
        return;
    }
    const step = store.ChatbotStep.insert({
        scriptStep: {id: stepId},
        message: messageId ? {id: messageId} : undefined,
        operatorFound: true,
    });
    chatbot.steps.add(step);
    chatbot.currentStep = step;
    chatbot.linkupError = "";
}

/**
 * The bar of "Need help now" under a welcome conversation of the widget:
 * LinkUp is not an emergency service, and the button opens the help at
 * once; the "?" button beside it turns the guide mode on. Its panel holds the resources (`LinkupHelpNow`), then whether a
 * person of the moderation joins or the request waits, in a live region.
 *
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @extends {Component<Props, Env>}
 */
export class LinkupLivechatHelp extends Component {
    static template = "im_livechat_linkup_reflect.LinkupLivechatHelp";
    static components = {LinkupErrorAlert, LinkupGuideButton, LinkupHelpNow};
    static props = ["thread"];

    setup() {
        super.setup();
        this.livechat = useState(useService("im_livechat.livechat"));
        this.help = useState(this.livechat.linkupHelp);
        this.panel = useRef("panel");
        this.button = useRef("button");
        // The pressed button gives way to the panel, which takes the focus;
        // closing the panel gives it back to the button.
        useEffect(
            (open) => {
                if (open) {
                    this.panel.el?.focus();
                } else if (this.closed) {
                    this.closed = false;
                    this.button.el?.focus();
                }
            },
            () => [this.help.open]
        );
    }

    press() {
        return linkupPressHelpNow(this.env, this.props.thread);
    }

    close() {
        this.closed = true;
        this.help.open = false;
    }
}
