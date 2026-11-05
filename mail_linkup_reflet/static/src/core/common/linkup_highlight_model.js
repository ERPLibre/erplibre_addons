import {Record} from "@mail/core/common/record";
import {Store} from "@mail/core/common/store_service";

import {patch} from "@web/core/utils/patch";

/**
 * "You add to my happiness": a member puts another one in the light, as
 * `linkup.highlight._to_store` gives it. `res.users._init_store_data`
 * loads the active highlights of the current member, and the bus brings
 * each change to both parties; an inactive one stays in the Store, out of
 * the light.
 */
export class LinkupHighlight extends Record {
    static _name = "linkup.highlight";
    static id = "id";

    /** @type {number} */
    id;
    sender = Record.one("Persona");
    recipient = Record.one("Persona");
    /** @type {boolean} */
    active;
    /** @type {string} */
    create_date;
    /** @type {number|false} */
    channel_id;
}
LinkupHighlight.register();

patch(Store.prototype, {
    /**
     * The active highlights the current member received, the most recent
     * first.
     *
     * @returns {LinkupHighlight[]}
     */
    get linkupHighlightsReceived() {
        return Object.values(this["linkup.highlight"].records)
            .filter((highlight) => highlight.active && highlight.recipient?.eq(this.self))
            .sort((a, b) => b.id - a.id);
    },

    /**
     * The active highlight of the current member towards a partner, if any.
     *
     * @param {import("models").Persona} persona
     * @returns {LinkupHighlight|undefined}
     */
    linkupHighlightSentTo(persona) {
        return Object.values(this["linkup.highlight"].records).find(
            (highlight) => highlight.active && highlight.sender?.eq(this.self) && highlight.recipient?.eq(persona)
        );
    },

    /**
     * The active highlight a partner gave the current member, if any.
     *
     * @param {import("models").Persona} persona
     * @returns {LinkupHighlight|undefined}
     */
    linkupHighlightFrom(persona) {
        return this.linkupHighlightsReceived.find((highlight) => highlight.sender?.eq(persona));
    },
});
