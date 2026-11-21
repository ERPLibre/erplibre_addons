/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const ITEM = ".o_timeline_view .vis-item";
const COMPANY = "Studio timeline company";

// A timeline whose item shows fields a studio project added: the item
// renders their values, a many2one by its name, nothing for an empty
// value, and the view raises no error.
registry.category("web_tour.tours").add("erplibre_studio_timeline", {
    steps: () => [
        {trigger: `${ITEM} .o_studio_test_item`},
        {trigger: `${ITEM} span[name=email]:contains(studio.timeline@example.invalid)`},
        {
            trigger: `${ITEM} span[name=parent_id]:contains(${COMPANY})`,
            run() {
                const texts = [...document.querySelectorAll(`${ITEM} span[name]`)].map((span) =>
                    span.textContent.trim()
                );
                const parents = [...document.querySelectorAll(`${ITEM} span[name=parent_id]`)].map((span) =>
                    span.textContent.trim()
                );
                if (parents.some((text) => text && text !== COMPANY)) {
                    throw new Error(`A many2one shows « ${parents.join(" | ")} », not its name.`);
                }
                if (texts.includes("false")) {
                    throw new Error("An empty value shows « false ».");
                }
            },
        },
    ],
});

const LANE = ".o_erplibre_studio_timeline_lane";

// The editor on a timeline: its lanes, the timeline of the canvas with
// the draft, a scale, the end date removed then dropped back from the
// palette, a color rule; then the preview of the view.
registry.category("web_tour.tours").add("erplibre_studio_timeline_editor", {
    steps: () => [
        {trigger: ITEM},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: `.o_erplibre_studio[data-view-type=timeline] ${LANE}[data-lane=start]`},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour timeline editor"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_timeline_editor"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        // The timeline of the canvas renders the records with the draft.
        {trigger: `.o_erplibre_studio_frise ${ITEM}`},
        {trigger: `${LANE}[data-lane=scale] .o_erplibre_studio_timeline_scale[data-value=week]`, run: "click"},
        {trigger: `${LANE}[data-lane=scale] .o_erplibre_studio_timeline_scale[data-value=week][aria-pressed=true]`},
        {trigger: `${LANE}[data-lane=scale] .o_erplibre_studio_change_dot`},
        // The end date leaves its lane, then comes back from the palette.
        {trigger: `${LANE}[data-lane=stop] .o_erplibre_studio_timeline_chip_remove`, run: "click"},
        {trigger: `${LANE}[data-lane=stop]:not(:has(.o_erplibre_studio_timeline_chip))`},
        {trigger: ".o_erplibre_studio_palette_filter", run: "edit write_date"},
        {
            trigger: ".o_erplibre_studio_existing_field[data-name=write_date]",
            run: `drag_and_drop ${LANE}[data-lane=stop]`,
        },
        {trigger: `${LANE}[data-lane=stop] .o_erplibre_studio_timeline_chip[data-attribute=date_stop]`},
        {trigger: ".o_erplibre_studio_view_properties[data-lane=stop]"},
        // A color rule, written from the colors lane.
        {trigger: `${LANE}[data-lane=colors] .o_erplibre_studio_timeline_add_rule`, run: "click"},
        {trigger: ".o_erplibre_studio_color_rule:last .o_erplibre_studio_color_field", run: "select is_company"},
        {trigger: ".o_erplibre_studio_color_rule:last .o_erplibre_studio_color_value", run: "edit True"},
        {trigger: ".o_erplibre_studio_save_colors:enabled", run: "click"},
        {trigger: `${LANE}[data-lane=colors] .o_erplibre_studio_timeline_chip:contains(is_company == True)`},
        {trigger: ".o_erplibre_studio_inspector_tab[data-tab=changes]", run: "click"},
        {trigger: ".o_erplibre_studio_changes li[data-type=set_attribute]:eq(1)"},
        // The preview of the view: the banner, the palette paused, the timeline.
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview_banner[data-kind=view]"},
        {trigger: ".o_erplibre_studio_palette_paused"},
        {trigger: ".o_erplibre_studio_inspector_tab[data-tab=properties]", run: "click"},
        {trigger: ".o_erplibre_studio_preview_info[data-kind=view]"},
        {trigger: `.o_erplibre_studio_preview ${ITEM}`},
        {trigger: ".o_erplibre_studio_preview_leave", run: "click"},
        {trigger: `${LANE}[data-lane=template] .o_erplibre_studio_card`},
    ],
});
