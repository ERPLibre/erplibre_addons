/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

// Opens the drawer from the debug menu of the contact list, then walks its
// tabs against the real server.
registry.category("web_tour.tours").add("erplibre_developer_drawer", {
    steps: () => [
        {trigger: ".o_list_view .o_data_row"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Developer panel)", run: "click"},
        {trigger: ".o_erplibre_dev_drawer .o_erplibre_dev_current_view:contains(base.view_partner_tree)"},
        {trigger: "body.o_erplibre_dev_open"},
        {
            // The drawer leaves the navbar systray visible and stays below
            // the dialogs.
            trigger: ".o_erplibre_dev_drawer",
            run() {
                const drawer = document.querySelector(".o_erplibre_dev_drawer");
                const toggle = document.querySelector(".o_debug_manager .dropdown-toggle");
                const box = toggle.getBoundingClientRect();
                const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
                if (!hit || !toggle.contains(hit)) {
                    throw new Error("The drawer covers the debug menu.");
                }
                if (Number(getComputedStyle(drawer).zIndex) >= 1050) {
                    throw new Error("The drawer is above the dialogs.");
                }
            },
        },
        // The debug menu stays usable while the drawer is open.
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Developer panel)", run: "click"},
        {trigger: "body.o_erplibre_dev_open .o_erplibre_dev_drawer"},
        {trigger: ".o_erplibre_dev_tabs [data-tab=fields]", run: "click"},
        {trigger: ".o_erplibre_dev_field_row[data-field=email] .o_erplibre_dev_defined_in:contains(base)"},
        {trigger: ".o_erplibre_dev_field_row[data-field=email]", run: "hover"},
        {trigger: "th[data-name=email].o_erplibre_dev_highlight"},
        {trigger: ".o_erplibre_dev_inspect", run: "click"},
        {trigger: "body.o_erplibre_dev_inspecting"},
        {trigger: ".o_data_row:first td.o_data_cell[name=city]", run: "click"},
        {trigger: ".o_erplibre_dev_field_row.o_erplibre_dev_selected[data-field=city]"},
        // The click selected the field: the record did not open.
        {trigger: ".o_list_view .o_data_row"},
        {trigger: "body:not(.o_erplibre_dev_inspecting)"},
        {trigger: ".o_erplibre_dev_tabs [data-tab=actions]", run: "click"},
        {trigger: ".o_erplibre_dev_action_row[data-module=base] .o_erplibre_dev_upgrade:disabled"},
        {trigger: ".o_erplibre_dev_tabs [data-tab=code]", run: "click"},
        {trigger: ".o_erplibre_dev_code_row[data-module=base]"},
        {trigger: ".o_erplibre_dev_close", run: "click"},
        {trigger: "body:not(.o_erplibre_dev_open):not(:has(.o_erplibre_dev_drawer))"},
    ],
});
