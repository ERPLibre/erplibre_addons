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
