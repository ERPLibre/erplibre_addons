/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";
import {patch} from "@web/core/utils/patch";
import {escape} from "@web/core/utils/strings";

// The renderer of the « leaflet_map » view (web_view_leaflet_map) builds the
// popup of a marker as an HTML string with the title and the address of
// the record, unescaped, and Leaflet sets it as innerHTML: a record name
// such as « <img onerror=…> » would run as script for whoever opens the
// marker. The studio adds maps whose title is the record name by default,
// so it escapes these two values in every map, its own and the others.
// The patch waits for the view to be registered: the studio does not
// depend on web_view_leaflet_map, which may load after this file or not
// at all.

/**
 * A copy of ``record`` (a record the renderer read) whose title and address
 * fields, those of the arch the renderer ``renderer`` reads
 * (``fieldTitle``, ``fieldAddress``), are escaped for HTML; a value that is
 * empty stays as it is.
 */
export function escapePopupValues(renderer, record) {
    const values = {...record};
    for (const name of [renderer.fieldTitle, renderer.fieldAddress]) {
        if (name && values[name]) {
            values[name] = escape(values[name]);
        }
    }
    return values;
}

const patchedRenderers = new WeakSet();

/**
 * Patch ``Renderer``, the renderer class of a « leaflet_map » view, so that
 * its popup reads escaped values. Answer whether it patched: a class
 * without ``preparePopUpData``, or one patched already, is left alone.
 */
export function patchLeafletRenderer(Renderer) {
    if (
        !Renderer ||
        patchedRenderers.has(Renderer) ||
        typeof Renderer.prototype.preparePopUpData !== "function"
    ) {
        return false;
    }
    patchedRenderers.add(Renderer);
    patch(Renderer.prototype, {
        preparePopUpData(record) {
            return super.preparePopUpData(escapePopupValues(this, record));
        },
    });
    return true;
}

const views = registry.category("views");
if (views.contains("leaflet_map")) {
    patchLeafletRenderer(views.get("leaflet_map").Renderer);
}
views.addEventListener("UPDATE", ({detail}) => {
    if (detail.operation === "add" && detail.key === "leaflet_map" && detail.value) {
        patchLeafletRenderer(detail.value.Renderer);
    }
});
