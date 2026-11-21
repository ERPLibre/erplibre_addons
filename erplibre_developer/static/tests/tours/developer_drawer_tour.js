/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

// Opens the drawer from the debug menu of the contact list, then walks its
// four tabs against the real server: the combined arch with its node origins,
// the field card, Inspect, the disabled upgrade and the Code tab.
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
        // Views: the tab is selected, the shown view sits on the rail, and
        // the combined arch carries the module origin of its nodes.
        {trigger: ".o_erplibre_dev_tabs [role=tab][data-tab=views][aria-selected=true]"},
        {
            trigger:
                ".o_erplibre_dev_view_row.o_erplibre_dev_view_current .o_erplibre_dev_view_xml_id:contains(base.view_partner_tree)",
        },
        {trigger: ".o_erplibre_dev_toggle_combined[aria-expanded=false]", run: "click"},
        {trigger: ".o_erplibre_dev_origin_switch[aria-checked=true]"},
        {trigger: ".o_erplibre_dev_combined.o_erplibre_dev_origins .o_erplibre_dev_line[data-origin=base]"},
        {trigger: ".o_erplibre_dev_legend [data-module=base]"},
        // Fields: the row, its hover outline on the page, then Inspect.
        {trigger: ".o_erplibre_dev_tabs [data-tab=fields]", run: "click"},
        {trigger: ".o_erplibre_dev_tabs [data-tab=fields][aria-selected=true]"},
        {trigger: ".o_erplibre_dev_field_row[data-field=email] .o_erplibre_dev_defined_in:contains(base)"},
        {trigger: ".o_erplibre_dev_field_row[data-field=email]", run: "hover"},
        {trigger: "th[data-name=email].o_erplibre_dev_highlight"},
        {trigger: ".o_erplibre_dev_inspect", run: "click"},
        {trigger: "body.o_erplibre_dev_inspecting"},
        {trigger: ".o_erplibre_dev_inspect_banner"},
        {trigger: ".o_data_row:first td.o_data_cell[name=city]", run: "click"},
        {trigger: ".o_erplibre_dev_field_row.o_erplibre_dev_selected[data-field=city]"},
        // The card above the list follows the selection and names the
        // module that defines the field in its origin chain.
        {trigger: ".o_erplibre_dev_field_card[data-field=city] .o_erplibre_dev_chain .o_erplibre_dev_step"},
        // The click selected the field: the record did not open.
        {trigger: ".o_list_view .o_data_row"},
        {trigger: "body:not(.o_erplibre_dev_inspecting)"},
        {trigger: ".o_erplibre_dev_tabs [data-tab=actions]", run: "click"},
        // The option is off: the prerequisite says so, and the boxes and the
        // upgrade button are disabled.
        {trigger: ".o_erplibre_dev_prereq_item[data-check=flag][data-ok='0']"},
        {trigger: ".o_erplibre_dev_actions_disabled"},
        {trigger: ".o_erplibre_dev_action_row[data-module=base] .o_erplibre_dev_upgrade_check:disabled"},
        {trigger: ".o_erplibre_dev_actions .o_erplibre_dev_upgrade:disabled"},
        // Code: the summary tiles, then the base module's row.
        {trigger: ".o_erplibre_dev_tabs [data-tab=code]", run: "click"},
        {trigger: ".o_erplibre_dev_code_tile[data-tile=all][aria-pressed=true]"},
        {trigger: ".o_erplibre_dev_code_row[data-module=base]"},
        {trigger: ".o_erplibre_dev_close", run: "click"},
        {trigger: "body:not(.o_erplibre_dev_open):not(:has(.o_erplibre_dev_drawer))"},
    ],
});
