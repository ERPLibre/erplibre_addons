/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {user} from "@web/core/user";

/**
 * « Developer panel » in the debug menu of a view, for the Settings
 * administrators. It opens the drawer on the view whose debug menu holds
 * the item: the main view, or the view of a dialog.
 */
export function developerPanelItem({component, env}) {
    if (!user.isSystem) {
        return null;
    }
    const config = component.env.config || {};
    const resModel = component.props && component.props.resModel;
    if (!resModel || !config.viewType) {
        return null;
    }
    return {
        type: "item",
        description: _t("Developer panel"),
        callback: () => {
            env.services.erplibre_developer.open({
                resModel,
                viewType: config.viewType,
                viewId: config.viewId || false,
                actionId: config.actionId || false,
            });
        },
        sequence: 205,
        section: "ui",
    };
}

registry.category("debug").category("view").add("erplibreDeveloperPanel", developerPanelItem);
