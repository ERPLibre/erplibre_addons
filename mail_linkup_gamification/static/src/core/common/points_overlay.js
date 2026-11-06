import {Component, useState} from "@odoo/owl";

import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

/**
 * The "+N" of the points and the announcements of a new rank or badge
 * (`linkup.points`), mounted once in the main components of the web
 * client. Each burst rises and wiggles for 1.2 s, or stays still when the
 * system asks for reduced motion; it is hidden from screen readers, which
 * read the polite live region instead (LU-F-091 RM1).
 */
export class LinkupPointsOverlay extends Component {
    static template = "mail_linkup_gamification.LinkupPointsOverlay";
    static props = {};

    setup() {
        super.setup();
        this.points = useState(useService("linkup.points").state);
    }
}

registry.category("main_components").add("mail_linkup_gamification.LinkupPointsOverlay", {
    Component: LinkupPointsOverlay,
});
