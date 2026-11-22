/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const LANE = ".o_erplibre_studio_calendar_lane";
const SCALE = `${LANE}[data-lane=scale] .o_erplibre_studio_calendar_scale`;

// From the contact kanban: a new project, a calendar view added to the
// draft (it opens on the month), the week scale chosen, a date dropped on
// its end date, then the preview of the calendar before Apply creates it.
registry.category("web_tour.tours").add("erplibre_studio_calendar_editor", {
    steps: () => [
        {trigger: ".o_kanban_view .o_kanban_record"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=kanban] .o_erplibre_studio_card"},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour calendar"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_calendar"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_add_view", run: "click"},
        {trigger: ".o_erplibre_studio_view_menu_add[data-view-type=calendar]", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=calendar] .o_erplibre_studio_added_banner[data-applied=false]"},
        {trigger: `${LANE}[data-lane=start] .o_erplibre_studio_calendar_chip[data-attribute=date_start]`},
        {trigger: `${SCALE}[data-value=month][aria-pressed=true]`},
        {trigger: `${SCALE}[data-value=week]:enabled`, run: "click"},
        {trigger: `${SCALE}[data-value=week][aria-pressed=true]`},
        {trigger: `${LANE}[data-lane=scale] .o_erplibre_studio_change_dot`},
        {trigger: ".o_erplibre_studio_palette_filter", run: "edit write_date"},
        {
            trigger: ".o_erplibre_studio_existing_field[data-name=write_date]",
            run: `drag_and_drop ${LANE}[data-lane=stop]`,
        },
        {trigger: `${LANE}[data-lane=stop] .o_erplibre_studio_calendar_chip[data-attribute=date_stop]`},
        {trigger: ".o_erplibre_studio_view_properties[data-lane=stop]"},
        // The preview renders the calendar of the draft with the records.
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview .o_calendar_view"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: `${LANE}[data-lane=popover]`},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_kanban_view .o_kanban_record"},
    ],
});
