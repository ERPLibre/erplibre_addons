/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const ROW = ".o_erplibre_studio_axis[data-axis=row]";
const TYPE = ".o_erplibre_studio_graph_types .o_erplibre_studio_graph_type";

// From the contact kanban: a new project, a graph view added to the draft,
// a field dropped on its group-bys, the line chart chosen, then the
// preview of the graph before Apply creates it.
registry.category("web_tour.tours").add("erplibre_studio_graph_editor", {
    steps: () => [
        {trigger: ".o_kanban_view .o_kanban_record"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=kanban] .o_erplibre_studio_card"},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour graph"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_graph"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_add_view", run: "click"},
        {trigger: ".o_erplibre_studio_view_menu_add[data-view-type=graph]", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=graph] .o_erplibre_studio_added_banner[data-applied=false]"},
        {trigger: `${TYPE}[data-value=bar][aria-pressed=true]`},
        {trigger: ".o_erplibre_studio_palette_filter", run: "edit country_id"},
        {
            trigger: ".o_erplibre_studio_existing_field[data-name=country_id]",
            run: `drag_and_drop ${ROW} .o_erplibre_studio_hook:last`,
        },
        {trigger: `${ROW} .o_erplibre_studio_field[data-name=country_id]`},
        {trigger: `${TYPE}[data-value=line]:enabled`, run: "click"},
        {trigger: `${TYPE}[data-value=line][aria-pressed=true]`},
        {trigger: ".o_erplibre_studio_inspector_tab[data-tab=changes]", run: "click"},
        {trigger: ".o_erplibre_studio_changes li[data-type=set_attribute]"},
        // The preview renders the graph of the draft with the records.
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview .o_graph_renderer canvas"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: `${ROW} .o_erplibre_studio_field[data-name=country_id]`},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_kanban_view .o_kanban_record"},
    ],
});
