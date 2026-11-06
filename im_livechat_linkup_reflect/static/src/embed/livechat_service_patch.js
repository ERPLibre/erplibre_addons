import {LivechatButton} from "@im_livechat/embed/common/livechat_button";
import {LivechatService} from "@im_livechat/embed/common/livechat_service";

import {Store} from "@mail/core/common/store_service";

import {browser} from "@web/core/browser/browser";
import {_t} from "@web/core/l10n/translation";
import {rpc} from "@web/core/network/rpc";
import {patch} from "@web/core/utils/patch";
import {session} from "@web/session";

/**
 * The widget reads what a visitor may read of LinkUp through the public
 * routes of the live chat: the visitor has no access to the models.
 *
 * - `fetchLinkupCategories`: the active categories, with the texts of the
 *   Help bar, in the language of the visitor;
 * - `fetchLinkupHelp`: the help resources, the hours of the moderation and
 *   the delay of an urgent report, kept as `linkup_help_resources`,
 *   `linkup_moderation_hours` and `linkup_urgent_hours`, which "Need help
 *   now" shows.
 */
patch(Store.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkup_help_resources = [];
        this.linkup_moderation_hours = "";
        this.linkup_urgent_hours = 0;
        this._linkupHelpPromise = null;
    },

    fetchLinkupCategories() {
        if (!this._linkupCategoriesPromise) {
            this._linkupCategoriesPromise = rpc("/linkup/v1/livechat/categories", {}, {silent: true})
                .then((records) => {
                    const categories = this["linkup.category"].insert(records);
                    this.linkupCategoryIds = categories.map((category) => category.id);
                    return categories;
                })
                .catch((error) => {
                    this._linkupCategoriesPromise = null;
                    throw error;
                });
        }
        return this._linkupCategoriesPromise;
    },

    fetchLinkupHelp() {
        if (!this._linkupHelpPromise) {
            this._linkupHelpPromise = rpc("/linkup/v1/livechat/help", {}, {silent: true})
                .then((info) => this.applyLinkupHelp(info))
                .catch((error) => {
                    this._linkupHelpPromise = null;
                    throw error;
                });
        }
        return this._linkupHelpPromise;
    },

    /** @param {{resources: string[], moderation_hours: string, urgent_hours: number}} info */
    applyLinkupHelp(info) {
        this.linkup_help_resources = info.resources || [];
        this.linkup_moderation_hours = info.moderation_hours || "";
        this.linkup_urgent_hours = info.urgent_hours || 0;
        return info;
    },
});

/**
 * The LinkUp role of the live chat channel of the widget, which `init`
 * gives before any conversation exists (`linkupKind`), and, for a member
 * logged in, the address of Discuss where the welcome widget sends them
 * (`linkupRedirect`, Q-45): the button of the widget then opens Discuss
 * instead of a conversation.
 *
 * `linkupHelp` holds "Need help now" of the widget, which outlives the
 * chat window of a conversation not saved yet, replaced once saved.
 */
patch(LivechatService.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkupKind = false;
        this.linkupRedirect = false;
        this.linkupHelp = {open: false, busy: false, status: "", found: false, error: null};
    },

    async initialize() {
        const options = session.livechatData?.options;
        if (options && !options.init && options.channel_id) {
            options.init = await rpc("/im_livechat/init", {channel_id: options.channel_id});
        }
        const init = options?.init || {};
        this.linkupKind = init.linkup_kind || false;
        this.linkupRedirect = init.linkup_redirect || false;
        if (this.linkupRedirect) {
            init.available_for_me = true;
        }
        return super.initialize(...arguments);
    },
});

patch(LivechatButton.prototype, {
    onClick() {
        if (this.livechatService.linkupRedirect) {
            browser.location.assign(this.livechatService.linkupRedirect);
            return;
        }
        return super.onClick(...arguments);
    },

    /** The name of the round button, which holds an icon only. */
    get linkupLabel() {
        if (this.livechatService.linkupRedirect) {
            return _t("Open LinkUp in Discuss");
        }
        return this.livechatService.options.button_text || _t("Open the chat");
    },
});
