/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const CARD = ".o_erplibre_studio[data-view-type=hierarchy] .o_erplibre_studio_card";

// From the contact kanban: a new project, a hierarchy view added to the
// draft (its card shows the name), the email added to the card with Enter
// on the palette, then the preview of the hierarchy before Apply creates
// it.
registry.category("web_tour.tours").add("erplibre_studio_hierarchy_editor", {
    steps: () => [
        {trigger: ".o_kanban_view .o_kanban_record"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=kanban] .o_erplibre_studio_card"},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour hierarchy"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_hierarchy"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_add_view", run: "click"},
        {trigger: ".o_erplibre_studio_view_menu_add[data-view-type=hierarchy]", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=hierarchy] .o_erplibre_studio_added_banner[data-applied=false]"},
        {trigger: ".o_erplibre_studio_hierarchy_caption"},
        {trigger: `${CARD} .o_erplibre_studio_field[data-name=name]`},
        {trigger: ".o_erplibre_studio_palette_filter", run: "edit email"},
        {
            trigger: ".o_erplibre_studio_existing_field[data-name=email] .o_erplibre_studio_palette_add",
            async run(helpers) {
                this.anchor.focus();
                await helpers.press("Enter");
            },
        },
        {trigger: `${CARD} .o_erplibre_studio_field[data-name=email]`},
        // The preview renders the hierarchy of the draft with the records.
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview .o_hierarchy_view"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: CARD},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_kanban_view .o_kanban_record"},
    ],
});
