/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const EMAIL_BEFORE = `.o_erplibre_studio_hook[data-target="//field[@name='email']"][data-position=before]`;

// From the contact kanban: a new project, the phone dropped into the card
// and shown with its widget in the preview; then, from the developer
// panel, a new filter of the search view, seen in the search menu of the
// preview. A pivot view added on the way. Apply writes the three views.
registry.category("web_tour.tours").add("erplibre_studio_views", {
    steps: () => [
        {trigger: ".o_kanban_view .o_kanban_record"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=kanban] .o_erplibre_studio_card"},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour views"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_views"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_palette [data-tab=existing]", run: "click"},
        {trigger: ".o_erplibre_studio_palette_filter", run: "edit phone"},
        {trigger: ".o_erplibre_studio_existing_field[data-name=phone]", run: `drag_and_drop ${EMAIL_BEFORE}`},
        {trigger: ".o_erplibre_studio_inspector_tab[data-tab=changes]", run: "click"},
        {trigger: ".o_erplibre_studio_changes li[data-type=add_existing_field]"},
        {trigger: ".o_erplibre_studio_inspector_tab[data-tab=properties]", run: "click"},
        {
            trigger:
                ".o_erplibre_studio_properties[data-name=phone] .o_erplibre_studio_settable[data-attribute=widget] select",
            run: "select phone",
        },
        {trigger: ".o_erplibre_studio_inspector_tab[data-tab=changes]", run: "click"},
        {trigger: ".o_erplibre_studio_changes li[data-type=set_attribute]"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview .o_kanban_record .o_field_widget[name=phone]"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_card .o_erplibre_studio_field[data-name=phone]"},
        // A pivot view, which the contacts lack, added to the draft and
        // previewed before Apply creates it.
        {trigger: ".o_erplibre_studio_add_view", run: "click"},
        {trigger: ".o_erplibre_studio_view_menu_add[data-view-type=pivot]", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=pivot] .o_erplibre_studio_added_banner[data-applied=false]"},
        {trigger: ".o_erplibre_studio_view_tab[data-view-type=pivot] .o_erplibre_studio_view_tab_new"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview .o_pivot"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_view_tab[data-view-type=kanban]", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=kanban] .o_erplibre_studio_card"},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_kanban_view .o_kanban_record"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Developer panel)", run: "click"},
        {trigger: ".o_erplibre_dev_drawer .o_erplibre_studio_customize_search", run: "click"},
        {trigger: "body:not(.o_erplibre_dev_open)"},
        {trigger: ".o_erplibre_studio[data-view-type=search] .o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_new_filter", run: "click"},
        {trigger: ".o_erplibre_studio_filter_label", run: "edit Tour has a tax ID"},
        {trigger: ".o_erplibre_studio_condition_field", run: "select vat"},
        {trigger: ".o_erplibre_studio_condition_operator", run: "select set"},
        {trigger: ".o_erplibre_studio_create_filter", run: "click"},
        {trigger: ".o_erplibre_studio_inspector_tab[data-tab=changes]", run: "click"},
        {trigger: ".o_erplibre_studio_changes li[data-type=add_node]"},
        {trigger: "[data-column=filters] .o_erplibre_studio_field[data-kind=filter]:contains(Tour has a tax ID)"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview .o_searchview_dropdown_toggler", run: "click"},
        {trigger: ".o_filter_menu .o-dropdown-item:contains(Tour has a tax ID)"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        // Apply of the top bar opens the review; nothing leaves the
        // database, so its Apply needs no « I understand ».
        {trigger: ".o_erplibre_studio_apply_bar:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_review_group[data-kind=view] .o_erplibre_studio_review_item[data-type=change]"},
        {trigger: "body:not(:has(.o_erplibre_studio_review_removal))"},
        {trigger: ".o_erplibre_studio_apply:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=applied]"},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_kanban_view .o_kanban_record"},
    ],
});
