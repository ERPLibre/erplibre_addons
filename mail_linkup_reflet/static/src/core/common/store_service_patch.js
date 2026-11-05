import {Store} from "@mail/core/common/store_service";

import {patch} from "@web/core/utils/patch";

/** Fields of `linkup.category` the web client reads. */
export const LINKUP_CATEGORY_FIELDS = [
    "code",
    "name",
    "definition",
    "example_do",
    "example_dont",
    "reflet_title",
    "starter_self",
    "starter_reflect",
    "sequence",
    "in_reflet_bar",
    "reflet_bar_sequence",
    "is_cnv",
];

/** @type {import("models").Store} */
const StorePatch = {
    setup() {
        super.setup(...arguments);
        /** Set by `res.users._init_store_data` for a LinkUp member. */
        this.linkup_is_member = false;
        /** Set by `res.users._init_store_data`: hidden themes of a precision. */
        this.linkup_max_hidden_themes = 2;
        /** Ids of the active categories, once fetched. */
        this.linkupCategoryIds = [];
        this._linkupCategoriesPromise = null;
    },

    /**
     * Read the active categories once, in the language of the user.
     *
     * The records of the Store are shared with the cards: a card that names
     * its category by code gets the texts of that category from here.
     *
     * @returns {Promise<import("models").LinkupCategory[]>}
     */
    fetchLinkupCategories() {
        if (!this._linkupCategoriesPromise) {
            this._linkupCategoriesPromise = this.env.services.orm
                .searchRead("linkup.category", [], LINKUP_CATEGORY_FIELDS, {
                    order: "sequence, id",
                })
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

    /** Active categories in the order of the full band. */
    get linkupCategories() {
        return this.linkupCategoryIds
            .map((id) => this["linkup.category"].get(id))
            .filter(Boolean)
            .sort((a, b) => a.sequence - b.sequence || a.id - b.id);
    },

    /** Categories of the reduced bar, in their own order. */
    get linkupBarCategories() {
        return this.linkupCategories
            .filter((category) => category.in_reflet_bar)
            .sort((a, b) => a.reflet_bar_sequence - b.reflet_bar_sequence || a.id - b.id);
    },

    /**
     * Read what LinkUp shows of a direct conversation and insert the cards
     * of its recent reflections.
     *
     * @param {number} channelId
     * @returns {Promise<Object>} the answer of `linkup.reflet.linkup_channel_info`
     */
    async fetchLinkupChannelInfo(channelId) {
        const info = await this.env.services.orm.silent.call("linkup.reflet", "linkup_channel_info", [channelId]);
        if (info.store) {
            this.insert(info.store);
        }
        return info;
    },

    /**
     * Read again what an action on a reflection changed in a conversation:
     * the recent cards of the pair and the messages posted after the
     * newest one of the thread, the carrier of a new reply among them.
     *
     * The same changes come over the bus; reading them here shows them
     * when the real-time connection is down. `Thread.fetchNewMessages`
     * leaves a loaded conversation to the bus, hence this reading.
     *
     * @param {import("models").Thread} thread
     */
    async linkupRefreshThread(thread) {
        await Promise.all([this.fetchLinkupChannelInfo(thread.id), linkupFetchNewMessages(thread)]);
    },
};

/**
 * Add to a thread the messages posted after its newest one.
 *
 * @param {import("models").Thread} thread
 */
export async function linkupFetchNewMessages(thread) {
    const after = thread.newestPersistentMessage?.id;
    const fetched = await thread.fetchMessages({after});
    const known = new Set(thread.messages.map((message) => message.id));
    const added = fetched
        .filter((message) => !known.has(message.id) && (!after || message.id > after))
        .sort((a, b) => a.id - b.id);
    thread.messages.push(...added);
}
patch(Store.prototype, StorePatch);
