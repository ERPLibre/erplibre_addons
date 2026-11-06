import {patch} from "@web/core/utils/patch";

import {LinkupSidebarSection} from "@mail_linkup_reflet/core/public_web/linkup_sidebar";

// "My points" in the LinkUp section of the sidebar of Discuss (§9.6).
patch(LinkupSidebarSection.prototype, {
    openMyPoints() {
        return this.action.doAction("mail_linkup_gamification.action_linkup_my_points");
    },
});
