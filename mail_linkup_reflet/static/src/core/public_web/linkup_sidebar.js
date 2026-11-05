import {Discuss} from "@mail/core/public_web/discuss";
import {discussSidebarItemsRegistry} from "@mail/core/public_web/discuss_sidebar";

import {Component, onMounted, useState} from "@odoo/owl";

import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";

/**
 * The LinkUp section of the sidebar of Discuss, for a member: the Reflet
 * view, "+ NewLink", which opens it on the invitation of a person who is
 * not a member, and the help of the categories. In a compact sidebar, only their
 * icons show, with their names as tooltips.
 */
export class LinkupSidebarSection extends Component {
    static template = "mail_linkup_reflet.LinkupSidebarSection";
    static props = {};

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
        this.action = useService("action");
    }

    openRefletView() {
        return this.action.doAction("mail_linkup_reflet.action_linkup_home");
    }

    /** Open the Reflet view on the first step of NewLink. */
    openNewlink() {
        return this.action.doAction("mail_linkup_reflet.action_linkup_home", {
            additionalContext: {linkup_newlink: true},
        });
    }

    openHelp() {
        return this.action.doAction("mail_linkup_reflet.action_linkup_help");
    }
}

discussSidebarItemsRegistry.add("linkup", LinkupSidebarSection, {sequence: 25});

// The first-use tour starts the first time Discuss opens for a member who
// has not seen it yet (`linkup_tour.js`).
patch(Discuss.prototype, {
    setup() {
        super.setup(...arguments);
        const tour = useService("linkup.tour");
        onMounted(() => tour.startIfPending());
    },
});
