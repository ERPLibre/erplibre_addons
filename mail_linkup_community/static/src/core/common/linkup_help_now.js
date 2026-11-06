import {Component, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

import {linkupHelpResources} from "./linkup_moderation_texts";

/**
 * "Need help now" (LU-F-118 RM2): LinkUp is not an emergency service, and
 * the resources of the territory come first. When an administrator wrote
 * the hours of the moderation, they show too, with the resources standing
 * in outside them. Nothing is sent to the server.
 *
 * @typedef {Object} Props
 * @property {boolean} [fromHelp] shown in the help page itself, which then
 *   does not point to the help
 * @extends {Component<Props, Env>}
 */
export class LinkupHelpNow extends Component {
    static template = "mail_linkup_community.LinkupHelpNow";
    static props = ["fromHelp?"];

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
    }

    get resources() {
        return linkupHelpResources(this.store);
    }

    get hoursText() {
        const hours = this.store.linkup_moderation_hours;
        return hours
            ? _t("The moderation reads the reports: %(hours)s. Outside these hours, use the resources above.", {
                  hours,
              })
            : "";
    }
}
