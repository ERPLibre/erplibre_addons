/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const ORDER = ".o_erplibre_studio_model[data-model=x_tour_order]";
const LEFT = `.o_erplibre_studio_hook[data-target="//group[@name='studio_left']"][data-position=inside]`;
const SHOP = ".o_erplibre_studio_app_card[data-app=menu_app]";
const BASE_ICON = ".o_erplibre_studio_icon[data-value='base,static/description/icon.png']";
const PREVIEW = ".o_erplibre_studio_model_preview";

// From the contact list: a new project with two apps, a model in each, the
// pending form of the first one gets a one2many to the second with its
// inverse created; the simulation shows the sub-list, the approval opens
// the real preview; two groups (the admin implies the user), a global
// rule, Apply; Revert lists the two models, without record, then Cancel.
registry.category("web_tour.tours").add("erplibre_studio_j4", {
    steps: () => [
        {trigger: ".o_list_view .o_data_row"},
        {trigger: ".o_debug_manager .dropdown-toggle", run: "click"},
        {trigger: ".dropdown-menu .dropdown-item:contains(Customize this view)", run: "click"},
        {trigger: ".o_erplibre_studio .o_erplibre_studio_field[data-name=email]"},
        {trigger: ".o_erplibre_studio_new_name", run: "edit Tour J4"},
        {trigger: ".o_erplibre_studio_new_module", run: "edit studio_tour_j4"},
        {trigger: ".o_erplibre_studio_create_project", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=draft]"},
        // Two apps.
        {trigger: ".o_erplibre_studio_apps_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_new_app", run: "click"},
        {trigger: ".o_erplibre_studio_app_form_name", run: "edit Tour shop"},
        {trigger: BASE_ICON, run: "click"},
        {trigger: `.o_erplibre_studio_icon_selected${BASE_ICON}`},
        {trigger: ".o_erplibre_studio_save_app:enabled", run: "click"},
        {trigger: `${SHOP} .o_erplibre_studio_app_name:contains(Tour shop)`},
        {trigger: ".o_erplibre_studio_new_app", run: "click"},
        {trigger: ".o_erplibre_studio_app_form_name", run: "edit Tour stock"},
        {trigger: ".o_erplibre_studio_save_app:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_app_card[data-app=menu_app_tour_stock]"},
        // A model in each app.
        {trigger: ".o_erplibre_studio_new_model", run: "click"},
        {trigger: ".o_erplibre_studio_model_dialog .o_erplibre_studio_model_label", run: "edit Tour order"},
        {trigger: ".o_erplibre_studio_model_app", run: "selectByLabel Tour shop"},
        {trigger: ".o_erplibre_studio_model_save:enabled", run: "click"},
        {trigger: `body:not(:has(.o_erplibre_studio_model_dialog)) ${ORDER}`},
        {trigger: ".o_erplibre_studio_new_model", run: "click"},
        {trigger: ".o_erplibre_studio_model_dialog .o_erplibre_studio_model_label", run: "edit Tour line"},
        {trigger: ".o_erplibre_studio_model_app", run: "selectByLabel Tour stock"},
        {trigger: ".o_erplibre_studio_model_save:enabled", run: "click"},
        {trigger: "body:not(:has(.o_erplibre_studio_model_dialog)) .o_erplibre_studio_model[data-model=x_tour_line]"},
        // The form of the order before Apply: a one2many to the line.
        {trigger: `${ORDER} .o_erplibre_studio_open_model[data-view-type=form]`, run: "click"},
        {trigger: `.o_erplibre_studio[data-view-type=form] ${ORDER}.o_erplibre_studio_model_current`},
        {trigger: ".o_erplibre_studio_field[data-name=x_name]"},
        {trigger: ".o_erplibre_studio_new_field[data-type=one2many]", run: `drag_and_drop ${LEFT}`},
        {trigger: ".o_erplibre_studio_relation_dialog .o_erplibre_studio_relation_comodel", run: "select x_tour_line"},
        {trigger: "#o_erplibre_studio_inverse_create:checked"},
        {trigger: ".o_erplibre_studio_relation_save:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_sublist[data-comodel=x_tour_line]"},
        // The simulation, then the real preview once approved.
        {trigger: "body:not(:has(.o_erplibre_studio_relation_dialog)) .o_erplibre_studio_preview_toggle", run: "click"},
        {trigger: `${PREVIEW}[data-mode=simulation] .o_field_one2many .o_list_renderer`},
        {trigger: ".o_erplibre_studio_approve", run: "click"},
        {trigger: ".o_erplibre_studio_approved"},
        {trigger: ".o_erplibre_studio_preview_real:enabled", run: "click"},
        {trigger: `${PREVIEW}[data-mode=real] .o_field_one2many .o_list_renderer`},
        {trigger: ".o_erplibre_studio_preview_close", run: "click"},
        {trigger: ".o_erplibre_studio_sublist[data-comodel=x_tour_line]"},
        // Two groups of the first app: the admin implies the user.
        {trigger: ".o_erplibre_studio_apps_toggle", run: "click"},
        {trigger: `${SHOP} .o_erplibre_studio_new_group`, run: "click"},
        {trigger: ".o_erplibre_studio_group_form_name", run: "edit Tour user"},
        {trigger: ".o_erplibre_studio_save_group:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_group[data-group=group_tour_shop_tour_user]"},
        {trigger: `${SHOP} .o_erplibre_studio_new_group`, run: "click"},
        {trigger: ".o_erplibre_studio_group_form_name", run: "edit Tour admin"},
        {trigger: ".o_erplibre_studio_add_implied_line", run: "selectByLabel Tour user"},
        {trigger: ".o_erplibre_studio_implied_line:contains(Tour user)"},
        {trigger: ".o_erplibre_studio_save_group:enabled", run: "click"},
        {
            trigger:
                ".o_erplibre_studio_group[data-group=group_tour_shop_tour_admin] .o_erplibre_studio_group_implied:contains(Tour user)",
        },
        // A global rule.
        {trigger: ".o_erplibre_studio_rules_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_new_rule", run: "click"},
        {trigger: ".o_erplibre_studio_rule_name", run: "edit Tour all orders"},
        {trigger: ".o_erplibre_studio_rule_model", run: "select x_tour_order"},
        {trigger: ".o_erplibre_studio_rule_global_check", run: "check"},
        {trigger: "body:not(:has(.o_erplibre_studio_rule_add_group))"},
        {trigger: ".o_erplibre_studio_save_rule:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_rule:contains(Tour all orders) .o_erplibre_studio_rule_global"},
        // Apply: nothing to remove, no confirmation.
        {trigger: ".o_erplibre_studio_apply:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=applied]"},
        // Revert lists the two models, then Cancel.
        {trigger: ".o_erplibre_studio_revert:enabled", run: "click"},
        {
            trigger:
                ".o_erplibre_studio_confirm_dialog .o_erplibre_studio_confirm_section[data-section=models] .o_erplibre_studio_confirm_count:contains(2)",
        },
        {trigger: ".o_erplibre_studio_confirm_item:contains(Tour order (x_tour_order): 0 record(s))"},
        {trigger: ".o_erplibre_studio_confirm_cancel", run: "click"},
        {trigger: "body:not(:has(.o_erplibre_studio_confirm_dialog)) .o_erplibre_studio_state[data-state=applied]"},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_list_view .o_data_row"},
        {trigger: ".o_navbar_apps_menu button", run: "click"},
        {trigger: ".o_app[data-menu-xmlid='studio_tour_j4.menu_app']:contains(Tour shop)"},
        {trigger: ".o_app[data-menu-xmlid='studio_tour_j4.menu_app_tour_stock']:contains(Tour stock)"},
    ],
});
