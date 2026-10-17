/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {user} from "@web/core/user";

export const STUDIO_VIEW_TYPES = ["form", "list"];

/** The client action of the studio editor on a view. */
export function customizeAction({resModel, viewType, viewId, actionId}) {
    return {
        type: "ir.actions.client",
        tag: "erplibre_studio.editor",
        name: _t("Studio"),
        params: {
            res_model: resModel,
            view_type: viewType,
            view_id: viewId || false,
            action_id: actionId || false,
        },
    };
}

/**
 * « Customize this view » in the debug menu of a form or a list, for the
 * Settings administrators.
 */
export function customizeViewItem({component, env}) {
    if (!user.isSystem) {
        return null;
    }
    const config = component.env.config || {};
    const resModel = component.props && component.props.resModel;
    if (!resModel || !STUDIO_VIEW_TYPES.includes(config.viewType)) {
        return null;
    }
    return {
        type: "item",
        description: _t("Customize this view"),
        callback: () => {
            env.services.action.doAction(
                customizeAction({
                    resModel,
                    viewType: config.viewType,
                    viewId: config.viewId,
                    actionId: config.actionId,
                })
            );
        },
        sequence: 206,
        section: "ui",
    };
}

registry.category("debug").category("view").add("erplibreStudioCustomize", customizeViewItem);
