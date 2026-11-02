/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import {registry} from "@web/core/registry";

// The clone that the test case moves away from its snapshot.
const CLONE = "odoo18.0/addons/Example_pull";

// Both validations of a confirmation wizard: the database name, read
// from the wizard itself, typed again, then the box ticked.
function confirmSteps(what) {
    return [
        {
            content: `${what}: type the database name`,
            trigger: ".modal div[name='typed_database_name'] input",
            async run(helpers) {
                const shown = document.querySelector(".modal div[name='database_name'] span");
                await helpers.edit(shown.textContent.trim());
            },
        },
        {
            content: `${what}: tick the box`,
            trigger: ".modal div[name='understood'] input",
            run: "click",
        },
        {
            content: `${what}: confirm`,
            trigger: ".modal button[name='action_confirm']",
            run: "click",
        },
    ];
}

// From the snapshot form to the kept stash: the dry run, its report, the
// apply step after both validations, then the Stashes menu. The runs
// execute while their button is answered, so each step waits on the state
// the form shows once it opens.
registry.category("web_tour.tours").add("erplibre_info_git_fetch_snapshot_revert", {
    steps: () => [
        {
            content: "open the return wizard",
            trigger: ".o_form_view button[name='action_revert']",
            run: "click",
        },
        {
            content: "the ERPLibre root goes back too, by default",
            trigger: ".modal div[name='include_root'] input:checked",
        },
        {
            content: "start the dry run",
            trigger: ".modal button[name='action_start']",
            run: "click",
        },
        {
            content: "the dry run is done",
            trigger:
                ".o_form_view:has(div[name='run_type']:contains('Return to a snapshot: dry run')) " +
                ".o_statusbar_status .o_arrow_button_current:contains('Done')",
        },
        {
            content: "the report shows the clone going back",
            trigger: `div[name='report_html'] tr:contains('${CLONE}'):contains('back to an older commit')`,
        },
        {
            content: "the report announces the kept stash",
            trigger: `div[name='report_html'] tr:contains('${CLONE}'):contains('yes (stash kept)')`,
        },
        {
            content: "open the confirmation of the return",
            trigger: ".o_form_view button[name='action_snapshot_revert']",
            run: "click",
        },
        {
            content: "the plan names the clone",
            trigger: `.modal div[name='plan_paths']:contains('${CLONE}')`,
        },
        ...confirmSteps("return"),
        {
            content: "the apply step is done",
            trigger:
                ".o_form_view:has(div[name='run_type']:contains('Return to a snapshot: apply')) " +
                ".o_statusbar_status .o_arrow_button_current:contains('Done')",
        },
        {
            content: "the report shows the clone returned",
            trigger: `div[name='report_html'] tr:contains('${CLONE}'):contains('returned to the snapshot')`,
        },
        {
            content: "open the apps menu",
            trigger: ".o_navbar_apps_menu button",
            run: "click",
        },
        {
            content: "open Settings",
            trigger: ".o_app[data-menu-xmlid='base.menu_administration']",
            run: "click",
        },
        {
            content: "open the Technical menu",
            trigger: ".o_menu_sections button[data-menu-xmlid='base.menu_custom']",
            run: "click",
        },
        {
            content: "open the Stashes menu",
            trigger: ".dropdown-item[data-menu-xmlid='erplibre_info_git_fetch.erplibre_code_stash_menu']",
            run: "click",
        },
        {
            content: "the stash of the clone is kept",
            trigger: `.o_list_view .o_data_row:contains('${CLONE}'):has(.badge:contains('Kept'))`,
        },
    ],
});
