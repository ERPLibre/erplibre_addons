/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onError, onMounted, onPatched, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {View} from "@web/views/view";
import {allBlocks} from "./studio_utils";

// The lanes of the canvas of a timeline, in their order: each one holds
// the attributes of <timeline> it sets. « template » holds the item
// template, edited by drops, and sets no attribute.
export const TIMELINE_LANES = [
    {key: "start", attributes: ["date_start"], glyph: "D"},
    {key: "stop", attributes: ["date_stop", "date_delay"], glyph: "D"},
    {key: "group", attributes: ["default_group_by"], glyph: "→"},
    {key: "colors", attributes: ["colors"], glyph: "Co"},
    {key: "scale", attributes: ["mode"], glyph: "Sc"},
    {key: "template", attributes: [], glyph: "Aa"},
];
// The lanes of the canvas of a calendar, in their order: each one holds
// the attributes of <calendar> it sets. « popover » holds the <field>
// children, which the popover of an event shows, and sets no attribute.
export const CALENDAR_LANES = [
    {key: "start", attributes: ["date_start"], glyph: "D"},
    {key: "stop", attributes: ["date_stop", "date_delay"], glyph: "D"},
    {key: "color", attributes: ["color"], glyph: "Co"},
    {key: "all_day", attributes: ["all_day"], glyph: "AD"},
    {key: "scale", attributes: ["mode"], glyph: "Sc"},
    {key: "popover", attributes: [], glyph: "Aa"},
];
// {view type: lanes}: the views whose canvas shows attribute lanes.
export const VIEW_LANES = {timeline: TIMELINE_LANES, calendar: CALENDAR_LANES};
// The lanes a field of the palette is dropped on: their attributes name a
// field.
export const FIELD_LANES = ["start", "stop", "group"];
// FIELD_LANES by view type.
export const FIELD_LANES_BY_TYPE = {timeline: FIELD_LANES, calendar: ["start", "stop", "color", "all_day"]};
// The scale web_timeline opens on when the view sets no « mode ».
export const DEFAULT_TIMELINE_MODE = "fit";
// The scale a view opens on when it sets no « mode », by view type. The
// calendar opens on the last scale of the browser session, else the week.
export const DEFAULT_MODES = {timeline: DEFAULT_TIMELINE_MODE, calendar: "week"};
// The drop zone of a lane, as the drag and drop of the editor names zones.
export const LANE_ZONE_PREFIX = "lane:";

/** The lane ``key`` of a ``viewType`` view (VIEW_LANES), or null. */
export function laneOf(viewType, key) {
    return (VIEW_LANES[viewType] || []).find((lane) => lane.key === key) || null;
}

/** The lane of ``key`` (TIMELINE_LANES), or null. */
export function timelineLane(key) {
    return laneOf("timeline", key);
}

/** The key of the lane a drop zone names, or null for another zone. */
export function laneOfZone(zone) {
    return zone && zone.startsWith(LANE_ZONE_PREFIX) ? zone.slice(LANE_ZONE_PREFIX.length) : null;
}

/** The label of the lane ``key`` of a ``viewType`` view, a timeline by default. */
export function laneLabel(key, viewType = "timeline") {
    if (viewType === "calendar") {
        const label = {
            color: _t("Color"),
            all_day: _t("All day"),
            popover: _t("Popover"),
        }[key];
        if (label) {
            return label;
        }
    }
    return (
        {
            start: _t("Start date"),
            stop: _t("End date"),
            group: _t("Group by"),
            colors: _t("Colors"),
            scale: _t("Scale"),
            template: _t("Item template"),
        }[key] || key
    );
}

/** What the lane ``key`` of a ``viewType`` view takes, under its label. */
export function laneAccepts(key, viewType = "timeline") {
    if (viewType === "calendar") {
        const accepts = {
            color: _t("many2one, selection, integer or char"),
            all_day: _t("boolean"),
            popover: _t("fields shown"),
        }[key];
        if (accepts) {
            return accepts;
        }
    }
    return (
        {
            start: _t("date"),
            stop: _t("date or duration"),
            group: _t("many2one / many2many"),
            colors: _t("rules"),
            scale: _t("on opening"),
            template: _t("fields shown"),
        }[key] || ""
    );
}

/** What the lane ``key`` of a ``viewType`` view does, for the inspector. */
export function laneHelp(key, viewType = "timeline") {
    if (viewType === "calendar") {
        return (
            {
                start: _t("A date or date and time field. Required."),
                stop: _t(
                    "The end date wins over the duration; without either, an event lasts one day or one hour."
                ),
                color: _t("One color per value of this field."),
                all_day: _t("A boolean field: true shows the event over the whole day."),
                scale: _t("The scale when the calendar opens."),
                popover: _t("The fields the popover of an event shows, in this order."),
            }[key] || ""
        );
    }
    return (
        {
            start: _t(
                "A date or date and time field of the model. Required: without it, the timeline places nothing."
            ),
            stop: _t(
                "Without an end date, an item lasts the duration of « Duration » (a number of hours), or shows as a point."
            ),
            group: _t(
                "One row per value. A many2many puts the item on each linked row; the items without a value get a row of their own."
            ),
            colors: _t("The rules read in their order; the first true one colors the item. The other items keep the default color."),
            scale: _t("The scale of the timeline when it opens. The user changes it from the timeline afterwards."),
            template: _t("The fields each item shows, in this order. Drag a field of the palette into the item to add it."),
        }[key] || ""
    );
}

/** The labels of the field blocks ``blocks``, in their order. */
export function fieldLabels(blocks, fields = {}) {
    return blocks
        .filter((block) => block.kind === "field" && block.name)
        .map((block) => (fields[block.name] && fields[block.name].string) || block.label || block.name);
}

/**
 * The field labels of the item template ``template`` (a block), in their
 * order: what each item of the timeline shows.
 */
export function templateFieldLabels(template, fields = {}) {
    return fieldLabels(allBlocks(template), fields);
}

function escapeAttribute(value) {
    return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

/**
 * The opening tag ``tag`` with the attributes ``attrs``, one per line
 * after the first: the attributes the view gets from the draft.
 */
export function openingTag(tag, attrs = {}) {
    const entries = Object.entries(attrs).filter(([, value]) => value !== undefined && value !== null);
    if (!entries.length) {
        return `<${tag}>`;
    }
    const indent = " ".repeat(tag.length + 2);
    const lines = entries.map(([name, value], index) => {
        const text = `${name}="${escapeAttribute(value)}"`;
        return index ? indent + text : `<${tag} ${text}`;
    });
    return `${lines.join("\n")}>`;
}

/**
 * The rules of the ``colors`` attribute of the payload ({color,
 * expression, field, operator, value}) as « set_attribute » takes them;
 * null when a rule is not one the editor writes (its expression is not
 * « field operator value »), since writing the others would lose it.
 */
export function writableColorRules(rules = []) {
    if (rules.some((rule) => !rule.field)) {
        return null;
    }
    return rules.map(({color, field, operator, value}) => ({color, field, operator, value}));
}

/** Whether the web client knows a view of type ``viewType``. */
export function hasViewType(viewType) {
    return registry.category("views").contains(viewType);
}

/**
 * The timeline of the canvas: the real view with the draft (the props of
 * the preview of the editor). A new view mounts once the canvas shows the
 * key of the draft it renders: the canvas renders without waiting for the
 * records of the timeline, and a view that fails to load shows its error
 * here instead of breaking the editor.
 */
export class StudioFrise extends Component {
    static template = "erplibre_studio.Frise";
    static components = {View};
    static props = {
        // The props of the View (StudioEditor.previewProps).
        viewProps: Object,
        // Changes with the draft: a new key mounts a new view.
        viewKey: String,
    };

    setup() {
        this.state = useState({key: null, viewProps: null, error: null});
        onMounted(() => this.follow());
        onPatched(() => this.follow());
        onError((error) => {
            const cause = (error && error.cause) || error;
            Object.assign(this.state, {
                key: this.props.viewKey,
                viewProps: null,
                error: (cause && ((cause.data && cause.data.message) || cause.message)) || String(cause),
            });
        });
    }

    /** Show the view of the key the props name, once rendered without it. */
    follow() {
        if (this.state.key !== this.props.viewKey) {
            Object.assign(this.state, {key: this.props.viewKey, viewProps: this.props.viewProps, error: null});
        }
    }
}
