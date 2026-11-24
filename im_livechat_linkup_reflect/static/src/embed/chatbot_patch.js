import {Chatbot} from "@im_livechat/embed/common/chatbot/chatbot_model";
import {ChatBotService} from "@im_livechat/embed/common/chatbot/chatbot_service";
import {ChatbotStep} from "@im_livechat/embed/common/chatbot/chatbot_step_model";

import {Composer} from "@mail/core/common/composer";

import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";

import {linkupFetchLivechatInfo} from "../common/livechat_reflet";

/**
 * The steps of the reflection guide that wait for an answer of the visitor
 * (LU-F-125): the category, chosen among the answers of the step, then
 * "You told me" and "I understood that", typed in the composer. The review
 * and "Need help now" wait for nothing.
 */
export const LINKUP_ANSWER_STEPS = ["linkup_category", "linkup_you_said", "linkup_understood"];

patch(ChatbotStep.prototype, {
    get expectAnswer() {
        return super.expectAnswer || LINKUP_ANSWER_STEPS.includes(this.type);
    },
});

/**
 * An answer the server refuses (`linkup.validation`: an empty or too long
 * text, a category no longer active) leaves its step the current one: the
 * script does not move on, the composer or the answers of the step come
 * back, and `linkupError` holds the message of the refusal until the next
 * answer. Any other error is not handled here.
 *
 * Once a person joined the conversation, the chatbot is done: the widget
 * reads the start rule of the conversation again, which now binds both
 * parties, without waiting for the bus.
 */
patch(Chatbot.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkupError = "";
    },

    async processAnswer() {
        this.linkupError = "";
        return super.processAnswer(...arguments);
    },

    async triggerNextStep() {
        await super.triggerNextStep(...arguments);
        if (this.currentStep?.operatorFound && this.thread?.linkup_livechat_kind) {
            await linkupFetchLivechatInfo(this.store, this.thread).catch(() => {});
        }
    },

    async _goToNextStep() {
        try {
            return await super._goToNextStep(...arguments);
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info || !this.currentStep) {
                throw error;
            }
            this.linkupError = info.message;
            this.currentStep.completed = false;
            this.currentStep.selectedAnswer = undefined;
        }
    },
});

patch(ChatBotService.prototype, {
    get inputDisabledText() {
        const step = this.chatbot?.currentStep;
        if (!this.inputEnabled && step?.type === "linkup_category" && !step.completed) {
            return _t("Select an option above");
        }
        return super.inputDisabledText;
    },
});

/** The composer names the text the current step of the guide asks for. */
patch(Composer.prototype, {
    get placeholder() {
        switch (this.thread?.chatbot?.currentStep?.type) {
            case "linkup_you_said":
                return _t("You told me…");
            case "linkup_understood":
                return _t("I understood that…");
        }
        return super.placeholder;
    },
});
