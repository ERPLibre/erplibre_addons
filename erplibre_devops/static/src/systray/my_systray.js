/** @odoo-module **/

import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {Component} from "@odoo/owl";
import {Dropdown} from "@web/core/dropdown/dropdown";
import {DropdownItem} from "@web/core/dropdown/dropdown_item";

export class MySystrayMenu extends Component {
    static template = "erplibre_devops.MySystrayMenu";
    static components = {Dropdown, DropdownItem};
    static props = [];

    setup() {
        this.action = useService("action");
    }

    openWizard() {
        // Référence l'action par son XML id : module.id_externe
        this.action.doAction("erplibre_devops.action_devops_plan_action_workspace_me");
    }

    openSomethingElse() {
        // autre item du menu...
    }
}

export const mySystrayItem = {
    Component: MySystrayMenu,
};

registry.category("systray").add("erplibre_devops.MySystrayMenu", mySystrayItem, {sequence: 1});
