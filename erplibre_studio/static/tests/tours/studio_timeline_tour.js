/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const ITEM = ".o_timeline_view .vis-item";
const COMPANY = "Studio timeline company";

// A timeline whose item shows fields a studio project added: the item
// renders their values, a many2one by its name, nothing for an empty
// value, and the view raises no error.
registry.category("web_tour.tours").add("erplibre_studio_timeline", {
    steps: () => [
        {trigger: `${ITEM} .o_studio_test_item`},
        {trigger: `${ITEM} span[name=email]:contains(studio.timeline@example.invalid)`},
        {
            trigger: `${ITEM} span[name=parent_id]:contains(${COMPANY})`,
            run() {
                const texts = [...document.querySelectorAll(`${ITEM} span[name]`)].map((span) =>
                    span.textContent.trim()
                );
                const parents = [...document.querySelectorAll(`${ITEM} span[name=parent_id]`)].map((span) =>
                    span.textContent.trim()
                );
                if (parents.some((text) => text && text !== COMPANY)) {
                    throw new Error(`A many2one shows « ${parents.join(" | ")} », not its name.`);
                }
                if (texts.includes("false")) {
                    throw new Error("An empty value shows « false ».");
                }
            },
        },
    ],
});
