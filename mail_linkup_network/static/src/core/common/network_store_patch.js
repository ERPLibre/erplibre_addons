import {Store} from "@mail/core/common/store_service";

import {patch} from "@web/core/utils/patch";

import {LinkupReflet} from "@mail_linkup_reflet/core/common/linkup_reflet_model";

// Set by `res.users._init_store_data` of this module for a LinkUp member,
// and on the bus when the member changes their preferences.
patch(Store.prototype, {
    setup() {
        super.setup(...arguments);
        /** Whether the member shows their links to their links (LU-NF-012). */
        this.linkup_links_visible = false;
        /** Whether the member shows their energy to their links. */
        this.linkup_energy_visible = false;
        /** The number of partners the density X3 keeps. */
        this.linkup_network_top_count = 2;
        /**
         * How much the decay took from the energy of the member, at the
         * opening of the web client, then at each reading of the Network
         * view (Q-41).
         */
        this.linkup_energy_decay = 0;
    },

    /**
     * The energy of the member: their karma (Q-08) less its decay (Q-41).
     * The points of the session reach the karma at once, with their full
     * weight; `undefined` until the karma is known.
     *
     * @returns {number|undefined}
     */
    get linkupEnergy() {
        if (typeof this.linkup_karma !== "number") {
            return undefined;
        }
        return this.linkup_karma - (this.linkup_energy_decay || 0);
    },
});

// The quick reply to a request for action, the same for both parties
// (`linkup.reflet._linkup_card_values`).
patch(LinkupReflet.prototype, {
    setup() {
        super.setup(...arguments);
        /** @type {"agree"|"not_now"|false} */
        this.action_reply = false;
    },
});
