// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {describe, expect, test} from "@odoo/hoot";
import {registry} from "@web/core/registry";
import {escapePopupValues, patchLeafletRenderer} from "@erplibre_studio/leaflet_popup_patch";

// A value a user may type in a record name: HTML that runs a script once
// set as innerHTML.
const SCRIPTED = `<img src=x onerror="window.studioTestHit = 1">`;

/** A renderer built as the one of web_view_leaflet_map builds its popup. */
function makeRenderer() {
    return class {
        constructor() {
            this.fieldTitle = "name";
            this.fieldAddress = "street";
        }

        preparePopUpData(record) {
            const title = record[this.fieldTitle] || "";
            const address = record[this.fieldAddress] || "";
            return `<div data-res-id='${record.resId}'><b>${title}</b><br/>${address ? ` - ${address}` : ""}</div>`;
        }
    };
}

describe("erplibre_studio, the popup of a leaflet map", () => {
    test("the title and the address are escaped, the other values stay", () => {
        const values = escapePopupValues(
            {fieldTitle: "name", fieldAddress: "street"},
            {id: 4, name: SCRIPTED, street: "1 <b>Main</b> street", city: "<i>"}
        );
        expect(values.name).toBe("&lt;img src=x onerror=&quot;window.studioTestHit = 1&quot;&gt;");
        expect(values.street).toBe("1 &lt;b&gt;Main&lt;/b&gt; street");
        expect(values.city).toBe("<i>");
        expect(values.id).toBe(4);
        const empty = escapePopupValues({fieldTitle: "name", fieldAddress: false}, {name: false});
        expect(empty.name).toBe(false);
    });

    test("a patched renderer writes no markup of the record into its popup", () => {
        const Renderer = makeRenderer();
        expect(patchLeafletRenderer(Renderer)).toBe(true);
        // Patched once: a second registration leaves it.
        expect(patchLeafletRenderer(Renderer)).toBe(false);
        expect(patchLeafletRenderer(class {})).toBe(false);
        const html = new Renderer().preparePopUpData({resId: 4, name: SCRIPTED, street: "<script>x</script>"});
        const node = document.createElement("div");
        node.innerHTML = html;
        expect(node.querySelector("img, script")).toBe(null);
        expect(node.querySelector("b").textContent).toBe(SCRIPTED);
        expect(node.textContent).toInclude("<script>x</script>");
    });

    test("the renderer of the leaflet_map view, when installed, is patched", () => {
        const views = registry.category("views");
        if (!views.contains("leaflet_map")) {
            // web_view_leaflet_map is not installed: nothing to patch.
            expect(patchLeafletRenderer(null)).toBe(false);
            return;
        }
        const {Renderer} = views.get("leaflet_map");
        // Patched already, at the registration of the view.
        expect(patchLeafletRenderer(Renderer)).toBe(false);
        const html = Renderer.prototype.preparePopUpData.call(
            {fieldTitle: "name", fieldAddress: "street"},
            {resId: 4, name: SCRIPTED, street: false}
        );
        expect(html).not.toInclude("<img");
        expect(html).toInclude("&lt;img");
    });
});
