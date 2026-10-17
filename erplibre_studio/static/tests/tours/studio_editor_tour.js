/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const NAME_BEFORE = `.o_erplibre_studio_hook[data-target="//field[@name='complete_name']"][data-position=before]`;

// From the developer panel of the contact list: a new project, a column
// moved by drag and drop, its preview, then undone. Nothing is applied.
registry.category("web_tour.tours").add("erplibre_studio_editor", {
    steps: () => [
        {trigger: ".o_list_view .o_data_row"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Developer panel)", run: "click"},
        {trigger: ".o_erplibre_dev_drawer .o_erplibre_studio_customize", run: "click"},
        {trigger: "body:not(.o_erplibre_dev_open)"},
        {trigger: ".o_erplibre_studio .o_erplibre_studio_field[data-name=email]"},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour contacts"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_contacts"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_field[data-name=email]", run: `drag_and_drop ${NAME_BEFORE}`},
        {trigger: ".o_erplibre_studio_changes li[data-type=move]"},
        {trigger: "[data-tag=list] > .o_erplibre_studio_children > .o_erplibre_studio_field:first[data-name=email]"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview .o_list_view th[data-name=email] + th[data-name=complete_name]"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_undo", run: "click"},
        {trigger: ".o_erplibre_studio_no_change"},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_list_view .o_data_row"},
    ],
});
