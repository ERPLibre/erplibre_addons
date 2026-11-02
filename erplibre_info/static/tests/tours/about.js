/** @odoo-module **/
// © 2021-2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import {registry} from "@web/core/registry";

// The About section of the general settings: Odoo's block, then the
// ERPLibre block with its heading, its values and its copyright line.
registry.category("web_tour.tours").add("erplibre_info_about", {
    steps: () => [
        {
            content: "Odoo's block keeps its copyright line",
            trigger: "#about a#license[href*='lgpl']",
        },
        {
            content: "the ERPLibre block has its heading",
            trigger: "#about .o_erplibre_about .erplibre-semver-version:contains('ERPLibre')",
        },
        {
            content: "the ERPLibre block comes after Odoo's",
            trigger: "#about .o_widget_res_config_edition ~ .o_widget_erplibre_about .o_erplibre_about",
        },
        {
            content: "the values are listed",
            trigger: ".o_erplibre_about .o_erplibre_about_table th:contains('Odoo version')",
        },
        {
            content: "the copyright line names TechnoLibre",
            trigger: ".o_erplibre_about a[href='https://technolibre.ca']:contains('TechnoLibre')",
        },
        {
            content: "the license is linked",
            trigger: ".o_erplibre_about a[href='https://www.gnu.org/licenses/agpl-3.0.html']",
        },
    ],
});
