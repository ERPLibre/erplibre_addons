/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {patch} from "@web/core/utils/patch";
import {ViewsTab} from "@erplibre_developer/drawer/tabs/views_tab";
import {STUDIO_VIEW_TYPES, customizeAction, searchViewIdOf} from "./debug_items";

// « Customize this view » and « Customize the search view » in the card
// of the view shown, in the Views tab of the developer panel. They read
// the target of the panel from its service and open the studio through
// the ``action`` service of the tab.
patch(ViewsTab.prototype, {
    get studioTarget() {
        return this.props.dev.state.target;
    },

    get canCustomize() {
        return Boolean(this.info && STUDIO_VIEW_TYPES.includes(this.info.view_type) && this.studioTarget);
    },

    /** Every view of a window action comes with a search view. */
    get canCustomizeSearch() {
        return Boolean(this.info && this.studioTarget);
    },

    async customizeView() {
        const target = this.studioTarget;
        const viewId = (this.info.view && this.info.view.id) || target.viewId;
        this.props.dev.close();
        await this.action.doAction(
            customizeAction({
                resModel: target.resModel,
                viewType: target.viewType,
                viewId,
                actionId: target.actionId,
            })
        );
    },

    /**
     * The search view of the action shown, when the panel targets one of
     * its views; else the default search view of the model.
     */
    async customizeSearchView() {
        const target = this.studioTarget;
        const controller = this.action.currentController;
        const action = controller && controller.action;
        const own = action && action.res_model === target.resModel && (action.id || false) === target.actionId;
        this.props.dev.close();
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
