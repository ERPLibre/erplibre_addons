/** @odoo-module **/
// © 2021-2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import {Component, onWillStart} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {Setting} from "@web/views/form/setting/setting";
import {standardWidgetProps} from "@web/views/widgets/standard_widget_props";

// The ERPLibre block of the About section, under Odoo's own: the values
// that « make version » prints, the commit and the code mode of the
// checkout, read once when the Settings form opens.
export class ErplibreAbout extends Component {
    static template = "erplibre_info.ErplibreAbout";
    static components = {Setting};
    static props = {...standardWidgetProps};

    setup() {
        this.orm = useService("orm");
        onWillStart(async () => {
            this.info = await this.orm.call("res.config.settings", "erplibre_about", []);
        });
    }
}

registry.category("view_widgets").add("erplibre_about", {component: ErplibreAbout});
