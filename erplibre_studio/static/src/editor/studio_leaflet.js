/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {_t} from "@web/core/l10n/translation";

// The lanes of the canvas of a map (web_view_leaflet_map), in their order:
// each one holds the root attribute of <leaflet_map> that names its field.
// The marker size and the popup anchor are numbers of the inspector.
export const LEAFLET_LANES = [
    {key: "latitude", attributes: ["field_latitude"], glyph: "La"},
    {key: "longitude", attributes: ["field_longitude"], glyph: "Lo"},
    {key: "title", attributes: ["field_title"], glyph: "Aa"},
    {key: "address", attributes: ["field_address"], glyph: "Ad"},
    {key: "marker", attributes: ["field_marker_icon_image"], glyph: "Im"},
];
// The lanes a field of the palette is dropped on: all of them.
export const LEAFLET_FIELD_LANES = LEAFLET_LANES.map((lane) => lane.key);

/** The label of the lane ``key`` of a map, or null. */
export function leafletLaneLabel(key) {
    return (
        {
            latitude: _t("Latitude"),
            longitude: _t("Longitude"),
            title: _t("Popup title"),
            address: _t("Popup address"),
            marker: _t("Marker image"),
        }[key] || null
    );
}

/** What the lane ``key`` of a map takes, under its label, or null. */
export function leafletLaneAccepts(key) {
    return (
        {
            latitude: _t("decimal"),
            longitude: _t("decimal"),
            title: _t("text"),
            address: _t("text"),
            marker: _t("image"),
        }[key] || null
    );
}

/** What the lane ``key`` of a map does, for the inspector, or null. */
export function leafletLaneHelp(key) {
    return (
        {
            latitude: _t(
                "A stored decimal field. Required: a record without a latitude and a longitude shows no marker."
            ),
            longitude: _t(
                "A stored decimal field. Required: a record without a latitude and a longitude shows no marker."
            ),
            title: _t("The bold line of the popup of a marker, and the text shown when the pointer rests on it."),
            address: _t("The line under the title in the popup of a marker."),
            marker: _t(
                "An image field drawn as the marker, at the size set under Advanced. Without it, the map draws its default pin."
            ),
        }[key] || null
    );
}
