import {Component} from "@odoo/owl";

import {Composer} from "@mail/core/common/composer";
import {Store} from "@mail/core/common/store_service";
import {Thread} from "@mail/core/common/thread_model";

import {_t} from "@web/core/l10n/translation";
import {rpc} from "@web/core/network/rpc";
import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";

import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";
import {linkupFetchNewMessages} from "@mail_linkup_reflet/core/common/store_service_patch";
import {LinkupTour} from "@mail_linkup_reflet/core/common/linkup_tour";

/**
 * The reflection guide of a member, in Discuss (LU-F-125 RM5).
 *
 * The first-use tour proposes it at its last step:
 * `linkup.reflet.linkup_start_guide` opens a conversation with the chatbot
 * of the guide, which Discuss shows. The server runs the script there
 * (`discuss.channel.linkup_member_guide`): a choice is posted with its
 * answer (`selected_answer_id`), a text from the composer, and the next
 * steps are read right after the post, the bus bringing them as well.
 * `linkup_guide` tells the step to answer; an answer the server refuses
 * leaves no message and shows its reason above the composer.
 */
patch(Thread.prototype, {
    setup() {
        super.setup(...arguments);
        /** @type {{step_type: string|false, expects: "choice"|"text"|false, answers: {id: number, name: string}[]}|undefined} */
        this.linkup_guide = undefined;
        /** The reason of the last answer the server refused. */
        this.linkup_guide_error = "";
    },

    /** An answer of the guide reads the steps the server posted after it. */
    async post() {
        const message = await super.post(...arguments);
        if (message && this.linkup_guide) {
            await linkupFetchNewMessages(this);
        }
        return message;
    },
});

patch(Store.prototype, {
    /**
     * Post an answer of the guide, catching the refusal of the server: the
     * pending message goes, and the thread keeps its reason. Any other
     * post, and any other error, go the way of `mail`.
     */
    async doMessagePost(params, tmpMessage) {
        const thread = tmpMessage?.thread;
        if (!thread?.linkup_guide) {
            return super.doMessagePost(...arguments);
        }
        thread.linkup_guide_error = "";
        return this.messagePostMutex.exec(async () => {
            try {
                return await rpc("/mail/message/post", params, {silent: true});
            } catch (error) {
                const info = linkupErrorInfo(error);
                if (!info) {
                    tmpMessage.postFailRedo = () => {
                        tmpMessage.postFailRedo = undefined;
                        tmpMessage.thread.messages.delete(tmpMessage);
                        tmpMessage.thread.messages.add(tmpMessage);
                        this.doMessagePost(params, tmpMessage);
                    };
                    return undefined;
                }
                thread.linkup_guide_error = info.message;
                tmpMessage.delete();
                return undefined;
            }
        });
    },
});

/**
 * The answers of the current step of the guide, above the composer: a
 * button per answer of a choice, or what the text to type is.
 *
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @extends {Component<Props, Env>}
 */
export class LinkupGuideAnswers extends Component {
    static template = "im_livechat_linkup_reflect.LinkupGuideAnswers";
    static props = ["thread"];

    get guide() {
        return this.props.thread.linkup_guide;
    }

    get hint() {
        switch (this.guide?.step_type) {
            case "linkup_category":
                return _t("Choose the category of what you were told.");
            case "linkup_you_said":
                return _t("Type what the person told you.");
            case "linkup_understood":
                return _t("Type what you understood.");
        }
        return this.guide?.expects === "choice" ? _t("Choose an answer.") : "";
    }

    /** @param {{id: number, name: string}} answer */
    choose(answer) {
        return this.props.thread.post(answer.name, {}, {selected_answer_id: answer.id});
    }
}

patch(Composer, {
    components: {...Composer.components, LinkupGuideAnswers},
});

patch(Composer.prototype, {
    /** The guide of a member, outside an edition and the chatter. */
    get hasLinkupGuide() {
        return Boolean(this.thread?.linkup_guide?.expects && !this.props.composer.message && !this.env.inChatter);
    },

    get placeholder() {
        if (this.hasLinkupGuide) {
            switch (this.thread.linkup_guide.step_type) {
                case "linkup_you_said":
                    return _t("You told me…");
                case "linkup_understood":
                    return _t("I understood that…");
            }
        }
        return super.placeholder;
    },
});

/**
 * The last step of the first-use tour proposes the guide of a first
 * reflection: it ends the tour, then opens the conversation of the guide.
 */
patch(LinkupTour.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkupOrm = useService("orm");
        this.linkupStore = useService("mail.store");
    },

    async linkupStartGuide() {
        await this.tour.stop();
        const result = await this.linkupOrm.call("linkup.reflet", "linkup_start_guide", []);
        if (result.store) {
            this.linkupStore.insert(result.store);
        }
        const thread = await this.linkupStore.Thread.getOrFetch({
            model: "discuss.channel",
            id: result.channel_id,
        });
        thread?.open();
    },
});
