import {patch} from "@web/core/utils/patch";
import {formatInteger} from "@web/views/fields/formatters";

import {LinkupEnergy} from "@mail_linkup_gamification/core/common/linkup_energy";

// The energy bubble of the Reflet view and the card of the LinkUp panel
// show the energy of the member as the Network view does: their karma less
// its decay (Q-41). The rank and "My points" keep the karma.
patch(LinkupEnergy.prototype, {
    get karma() {
        return formatInteger(this.store.linkupEnergy ?? this.store.linkup_karma ?? 0);
    },
});
