/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";
import {rpc} from "@web/core/network/rpc";

const EDITOR = ".o_erplibre_studio[data-view-type=list]";
// How long the last step waits for the sheet the spreadsheet saves when the
// user leaves it: its write is sent, not awaited.
const SAVE_TIMEOUT = 30000;

/** The ``spreadsheet_raw`` of the newest spreadsheet, or null. */
async function newestSheet() {
    const sheets = await rpc("/web/dataset/call_kw/spreadsheet.spreadsheet/search_read", {
        model: "spreadsheet.spreadsheet",
        method: "search_read",
        args: [[]],
        kwargs: {fields: ["spreadsheet_raw"], order: "id desc", limit: 1},
    });
    return sheets.length ? sheets[0].spreadsheet_raw : null;
}

// From the contact list: a new project, the list sent to a spreadsheet from
// the menu of Apply; the sheet of spreadsheet_oca opens with the list, the
// breadcrumbs go back to the editor on the list and the sheet is saved.
registry.category("web_tour.tours").add("erplibre_studio_spreadsheet", {
    steps: () => [
        {trigger: ".o_list_view .o_data_row"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: `${EDITOR} .o_erplibre_studio_field[data-name=email]`},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour spreadsheet"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_spreadsheet"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_apply_menu", run: "click"},
        {trigger: ".o_erplibre_studio_send_spreadsheet:enabled", run: "click"},
        // The bundle of o-spreadsheet loads on demand: it takes its time.
        {trigger: ".o_spreadsheet_oca_container .o-spreadsheet .o-grid", timeout: 60000},
        {trigger: ".o_spreadsheet_oca_container .o_breadcrumb .o_back_button", run: "click"},
        {trigger: `${EDITOR} .o_erplibre_studio_state[data-state=draft]`},
        {
            trigger: `${EDITOR} .o_erplibre_studio_field[data-name=email]`,
            async run() {
                const deadline = Date.now() + SAVE_TIMEOUT;
                while (Date.now() < deadline) {
                    const raw = await newestSheet();
                    if (raw && raw.lists && Object.keys(raw.lists).length) {
                        return;
                    }
                    await new Promise((resolve) => setTimeout(resolve, 250));
                }
                throw new Error("The spreadsheet left holds no list.");
            },
        },
    ],
});
