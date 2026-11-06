import {Component, useState} from "@odoo/owl";

import {useService} from "@web/core/utils/hooks";

import {linkupOpenSafety} from "./linkup_moderation_service";

/**
 * The banners of the moderation in the Reflet view: a decision about the
 * member they have not read yet, with "Read it"; for a moderator, the
 * urgent reports of their queue, with "Open the moderation".
 */
export class LinkupModerationBanner extends Component {
    static template = "mail_linkup_community.LinkupModerationBanner";
    static props = {};

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
        this.action = useService("action");
    }

    get unseen() {
        return this.store.linkup_is_member ? this.store.linkup_notice_unseen || 0 : 0;
    }

    get urgent() {
        return this.store.linkup_is_moderator ? this.store.linkup_moderation_urgent || 0 : 0;
    }

    openSafety() {
        return linkupOpenSafety(this.action);
    }

    openModeration() {
        return this.action.doAction("mail_linkup_community.action_linkup_moderation");
    }
}
