/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {user} from "@web/core/user";

// The view types the editor opens on. A page shows a timeline view only
// when web_timeline is installed, and the server refuses the type
// otherwise: the list needs no detection of its own.
export const STUDIO_VIEW_TYPES = ["form", "list", "kanban", "pivot", "timeline"];

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
 * The id of the search view of an action, from its ``views`` (the action
 * service adds the [id, "search"] pair): false for the default one.
 */
export function searchViewIdOf(action) {
    const view = ((action && action.views) || []).find((v) => v[1] === "search");
    return (view && view[0]) || false;
}

/**
 * « Customize this view » in the debug menu of a view the studio edits,
 * for the Settings administrators.
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

/**
 * « Customize the search view » in the debug menu of a view that has a
 * search view (``componentProps.info.searchViewId``, set by the View once
 * it loaded it).
 */
export function customizeSearchViewItem({component, env}) {
    if (!user.isSystem) {
        return null;
    }
    const config = component.env.config || {};
    const resModel = component.props && component.props.resModel;
    const info = (component.componentProps && component.componentProps.info) || {};
    if (!resModel || info.searchViewId === undefined) {
        return null;
    }
    return {
        type: "item",
        description: _t("Customize the search view"),
        callback: () => {
            env.services.action.doAction(
                customizeAction({
                    resModel,
                    viewType: "search",
                    viewId: info.searchViewId,
                    actionId: config.actionId,
                })
            );
        },
        sequence: 207,
        section: "ui",
    };
}

registry.category("debug").category("view").add("erplibreStudioCustomize", customizeViewItem);
registry.category("debug").category("view").add("erplibreStudioCustomizeSearch", customizeSearchViewItem);
