/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import { waitUntil } from "@odoo/hoot-dom";
import { registry } from "@web/core/registry";

// Signe depuis « Mon compte » en mode automatique : le composant dessine le
// nom pré-rempli, puis l'enregistrement recharge la page qui affiche l'image.
registry.category("web_tour.tours").add("erplibre_user_signature_portal", {
    url: "/my/account",
    steps: () => [
        {
            content: "open the signature dialog",
            trigger: ".o_portal_user_signature button[data-bs-target='#modal_user_signature']",
            run: "click",
        },
        {
            content: "wait for the drawn signature",
            trigger: ".modal canvas.o_web_sign_signature",
            async run(helpers) {
                await waitUntil(() => {
                    const canvas = helpers.anchor;
                    const context = canvas.getContext("2d");
                    const data = context.getImageData(0, 0, canvas.width, canvas.height);
                    return new Uint32Array(data.data.buffer).some((pixel) => pixel !== 0);
                });
            },
        },
        {
            content: "save the signature",
            trigger: ".modal .o_portal_sign_submit:enabled",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "the saved signature is shown",
            trigger: ".o_portal_user_signature img[src^='data:image/png;base64,']",
        },
    ],
});
