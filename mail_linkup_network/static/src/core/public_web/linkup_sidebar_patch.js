import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";
import {formatInteger} from "@web/views/fields/formatters";

import {LinkupSidebarSection} from "@mail_linkup_reflet/core/public_web/linkup_sidebar";

// "Network view (n)" in the LinkUp section of the sidebar of Discuss, n
// being the energy of the member (LU-F-002 RM2); without n when the member
// hides the points.
patch(LinkupSidebarSection.prototype, {
    get networkLabel() {
        if (this.store.settings?.linkup_hide_gamification) {
            return _t("Network view");
        }
        return _t("Network view (%(energy)s)", {energy: formatInteger(this.store.linkup_karma || 0)});
    },

    openNetworkView() {
        return this.action.doAction("mail_linkup_network.action_linkup_network");
    },
});
