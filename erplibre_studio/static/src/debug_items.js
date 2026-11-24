/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {developerPanelItem} from "@erplibre_developer/debug_items";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {user} from "@web/core/user";

// The section of the debug menu that gathers the entries of the studio and
// of the Developer panel under one « Studio » heading. The debug menu sorts
// its sections by the sequence of registry.category("debug_section"): 5
// puts this one above « Record » (10) and « User Interface » (20).
export const STUDIO_DEBUG_SECTION = "erplibre_studio";

// The view types the editor opens on. A page shows a timeline, a hierarchy,
// an activity view, a map or a GeoEngine view only when web_timeline,
// web_hierarchy, mail, web_view_leaflet_map or base_geoengine is installed,
// and the server refuses the type otherwise: the list needs no detection of
// its own.
export const STUDIO_VIEW_TYPES = [
    "form",
    "list",
    "kanban",
    "pivot",
    "graph",
    "calendar",
    "timeline",
    "hierarchy",
    "activity",
    "leaflet_map",
    "geoengine",
];

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
        section: STUDIO_DEBUG_SECTION,
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
        section: STUDIO_DEBUG_SECTION,
    };
}

/**
 * The « Developer panel » entry of erplibre_developer, moved to the studio
 * section: same visibility rules and callback, only its ``section`` differs.
 * Without the studio, the entry stays in « User Interface ».
 */
export function studioDeveloperPanelItem(context) {
    const item = developerPanelItem(context);
    return item && {...item, section: STUDIO_DEBUG_SECTION};
}

registry.category("debug_section").add(STUDIO_DEBUG_SECTION, {label: _t("Studio"), sequence: 5});
const viewDebugItems = registry.category("debug").category("view");
viewDebugItems.add("erplibreDeveloperPanel", studioDeveloperPanelItem, {force: true});
viewDebugItems.add("erplibreStudioCustomize", customizeViewItem);
viewDebugItems.add("erplibreStudioCustomizeSearch", customizeSearchViewItem);
