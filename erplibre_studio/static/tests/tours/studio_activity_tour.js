/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const CARD = ".o_erplibre_studio[data-view-type=activity] .o_erplibre_studio_card";

// From the activity view of the contacts: the editor on it, a new project,
// the phone added to the « activity-box » with Enter on the palette, then
// the preview of the activity view with the draft.
registry.category("web_tour.tours").add("erplibre_studio_activity_editor", {
    steps: () => [
        {trigger: ".o_activity_view"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: CARD},
        {trigger: ".o_erplibre_studio_activity_caption"},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour activity"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_activity"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_palette_filter", run: "edit phone"},
        {
            trigger: ".o_erplibre_studio_existing_field[data-name=phone] .o_erplibre_studio_palette_add",
            async run(helpers) {
                this.anchor.focus();
                await helpers.press("Enter");
            },
        },
        {trigger: `${CARD} .o_erplibre_studio_field[data-name=phone]`},
        // The preview renders the activity view of the draft.
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_preview .o_activity_view"},
        {trigger: ".o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: CARD},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_activity_view"},
    ],
});
