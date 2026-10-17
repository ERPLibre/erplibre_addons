/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {patch} from "@web/core/utils/patch";
import {DeveloperDrawer} from "@erplibre_developer/drawer/developer_drawer";
import {STUDIO_VIEW_TYPES, customizeAction, searchViewIdOf} from "./debug_items";

// « Customize this view » and « Customize the search view » in the header
// of the developer panel.
patch(DeveloperDrawer.prototype, {
    get canCustomize() {
        return Boolean(this.info && STUDIO_VIEW_TYPES.includes(this.info.view_type) && this.state.target);
    },

    /** Every view of a window action comes with a search view. */
    get canCustomizeSearch() {
        return Boolean(this.info && this.state.target);
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

    /**
     * The search view of the action shown, when the panel targets one of
     * its views; else the default search view of the model.
     */
    async customizeSearchView() {
        const target = this.state.target;
        const controller = this.action.currentController;
        const action = controller && controller.action;
        const own = action && action.res_model === target.resModel && (action.id || false) === target.actionId;
        this.dev.close();
        await this.action.doAction(
            customizeAction({
                resModel: target.resModel,
                viewType: "search",
                viewId: own ? searchViewIdOf(action) : false,
                actionId: target.actionId,
            })
        );
    },
});
