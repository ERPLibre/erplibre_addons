/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {patch} from "@web/core/utils/patch";
import {DeveloperDrawer} from "@erplibre_developer/drawer/developer_drawer";
import {STUDIO_VIEW_TYPES, customizeAction} from "./debug_items";

// « Customize this view » in the header of the developer panel.
patch(DeveloperDrawer.prototype, {
    get canCustomize() {
        return Boolean(this.info && STUDIO_VIEW_TYPES.includes(this.info.view_type) && this.state.target);
    },

    async customizeView() {
        const target = this.state.target;
        this.dev.close();
        await this.action.doAction(
            customizeAction({
                resModel: target.resModel,
                viewType: target.viewType,
                viewId: (this.info.view && this.info.view.id) || target.viewId,
                actionId: target.actionId,
            })
        );
    },
});
