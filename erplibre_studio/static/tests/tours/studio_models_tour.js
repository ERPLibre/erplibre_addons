/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const ITEM = ".o_erplibre_studio_model[data-model=x_tour_item]";
const LEFT = `.o_erplibre_studio_hook[data-target="//group[@name='studio_left']"][data-position=inside]`;
const UNLINK =
    ".o_erplibre_studio_access_model[data-model=x_tour_item] .o_erplibre_studio_access_perm[data-perm=perm_unlink]";

// From the contact list: a new project, a new model in a new app with the
// icon of base, Apply and open its form, a text field dropped into it, the
// right to delete taken from the internal users, a record rule of the
// internal users checked and saved, then Apply. Back on the contacts, the new app is in the home menu
// without a reload of the page.
registry.category("web_tour.tours").add("erplibre_studio_models", {
    steps: () => [
        {trigger: ".o_list_view .o_data_row"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: ".o_erplibre_studio .o_erplibre_studio_field[data-name=email]"},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour models"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_models"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_new_model", run: "click"},
        {trigger: ".o_erplibre_studio_model_dialog .o_erplibre_studio_model_label", run: "edit Tour item"},
        {trigger: ".o_erplibre_studio_icon[data-value='base,static/description/icon.png']", run: "click"},
        {trigger: ".o_erplibre_studio_icon_selected[data-value='base,static/description/icon.png']"},
        {trigger: ".o_erplibre_studio_model_save:enabled", run: "click"},
        {
            trigger: `body:not(:has(.o_erplibre_studio_model_dialog)) ${ITEM} .o_erplibre_studio_apply_open`,
            run: "click",
        },
        {trigger: `.o_erplibre_studio[data-view-type=form] ${ITEM}.o_erplibre_studio_model_current`},
        {trigger: ".o_erplibre_studio_state[data-state=applied]"},
        {trigger: ".o_erplibre_studio_field[data-name=x_name]"},
        {trigger: ".o_erplibre_studio_new_field[data-type=char]", run: `drag_and_drop ${LEFT}`},
        {trigger: ".o_erplibre_studio_changes li[data-type=add_field]"},
        {trigger: ".o_erplibre_studio_access_toggle", run: "click"},
        {trigger: `${UNLINK}:checked`, run: "click"},
        {trigger: `${UNLINK}:not(:checked)`},
        {trigger: ".o_erplibre_studio_rules_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_new_rule", run: "click"},
        {trigger: ".o_erplibre_studio_rule_name", run: "edit Tour own items"},
        {trigger: ".o_erplibre_studio_rule_domain", run: "edit [('create_uid', '=', user.id)]"},
        {trigger: ".o_erplibre_studio_check_rule", run: "click"},
        {trigger: ".o_erplibre_studio_rule_check[data-ok='1']"},
        // A rule names its groups: Apply refuses a rule without a group.
        {trigger: ".o_erplibre_studio_rule_add_group", run: "selectByLabel Internal User"},
        {trigger: ".o_erplibre_studio_rule_group"},
        {trigger: ".o_erplibre_studio_save_rule", run: "click"},
        {trigger: ".o_erplibre_studio_rule:contains(Tour own items)"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        {trigger: ".o_erplibre_studio_apply:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=applied]"},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_list_view .o_data_row"},
        {trigger: ".o_navbar_apps_menu button", run: "click"},
        {trigger: ".o_app[data-menu-xmlid='studio_tour_models.menu_app']:contains(Tour item)"},
    ],
});
