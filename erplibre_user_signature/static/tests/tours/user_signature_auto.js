/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import { registry } from "@web/core/registry";

// Ouvre la boîte de signature depuis « Mes préférences » : le mode « Auto »
// y est offert, pré-rempli avec le nom de l'utilisateur.
registry.category("web_tour.tours").add("erplibre_user_signature_auto", {
    steps: () => [
        {
            content: "open the user menu",
            trigger: ".o_user_menu .dropdown-toggle",
            run: "click",
        },
        {
            content: "open my preferences",
            trigger: ".dropdown-item[data-menu='settings']",
            run: "click",
        },
        {
            content: "open the signature dialog",
            trigger: ".modal .o_field_signature .o_signature",
            run: "click",
        },
        {
            content: "the automatic mode is offered",
            trigger: ".modal .o_web_sign_auto_button",
            run: "click",
        },
        {
            content: "the user's name is drawn",
            trigger: ".modal .o_web_sign_auto_button.active",
        },
    ],
});
