/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {registry} from "@web/core/registry";

const ITEM = ".o_erplibre_studio_model[data-model=x_tour_item]";
const LEFT = `.o_erplibre_studio_hook[data-target="//group[@name='studio_left']"][data-position=inside]`;
const UNLINK =
    ".o_erplibre_studio_access_model[data-model=x_tour_item] .o_erplibre_studio_access_perm[data-perm=perm_unlink]";

// From the contact list: a new project, a new model in a new app with the
// icon of base, its page in the models space, Apply and open its form, a
// text field dropped into it and given its technical name, the right to delete taken from the internal
// users, a record rule of the internal users checked and saved, then
// Apply. Back on the contacts, the new app is in the home menu without a
// reload of the page.
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
        {trigger: ".o_erplibre_studio_rail_item[data-space=models]:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_new_model", run: "click"},
        {trigger: ".o_erplibre_studio_model_dialog .o_erplibre_studio_model_label", run: "edit Tour item"},
        {trigger: ".o_erplibre_studio_icon[data-value='base,static/description/icon.png']", run: "click"},
        {trigger: ".o_erplibre_studio_icon_selected[data-value='base,static/description/icon.png']"},
        // The project has no app yet: the model makes one, named after it.
        {trigger: "#o_erplibre_studio_menu_new_app:checked"},
        {trigger: ".o_erplibre_studio_menu_preview:contains(Tour item › Tour item)"},
        {trigger: ".o_erplibre_studio_model_save:enabled", run: "click"},
        // The page of the new model, waiting for Apply.
        {trigger: `body:not(:has(.o_erplibre_studio_model_dialog)) ${ITEM} .o_erplibre_studio_model_state[data-applied='0']`},
        {trigger: `${ITEM} .o_erplibre_studio_model_menu_place:contains(Tour item › Tour item)`},
        {
            trigger: `body:not(:has(.o_erplibre_studio_model_dialog)) ${ITEM} .o_erplibre_studio_apply_open`,
            run: "click",
        },
        // Apply and open goes through the review, whose Apply writes.
        {trigger: ".o_erplibre_studio[data-space=review] .o_erplibre_studio_apply:enabled", run: "click"},
        {trigger: ".o_erplibre_studio[data-view-type=form][data-space=view] .o_erplibre_studio_title:contains(Tour item)"},
        {trigger: ".o_erplibre_studio_state[data-state=applied]"},
        {trigger: ".o_erplibre_studio_field[data-name=x_name]"},
        {trigger: ".o_erplibre_studio_new_field[data-type=char]", run: `drag_and_drop ${LEFT}`},
        // The new field is selected: at the Simple level its technical name
        // is under « More options ». The server checks it live; a name
        // without x_ blocks Apply, a valid one renames it.
        {trigger: ".o_erplibre_studio[data-level=simple] .o_erplibre_studio_field_advanced_toggle", run: "click"},
        {trigger: ".o_erplibre_studio_name_status:contains(Available)"},
        {trigger: ".o_erplibre_studio_field_advanced .o_erplibre_studio_prop_name", run: "edit tour_code"},
        {trigger: ".o_erplibre_studio_name_status:contains(Prefix x_ required)"},
        {trigger: ".o_erplibre_studio_name_blockers"},
        {trigger: ".o_erplibre_studio_apply_bar:disabled"},
        {
            trigger: ".o_erplibre_studio_field_advanced .o_erplibre_studio_prop_name",
            // Typing alone fires no « change »: the browser fires it on
            // Enter or when the input loses the focus.
            async run(helpers) {
                await helpers.edit("x_tour_code");
                helpers.anchor.dispatchEvent(new Event("change", {bubbles: true}));
            },
        },
        {trigger: ".o_erplibre_studio_properties[data-name=x_tour_code] .o_erplibre_studio_name_tag:contains(edited)"},
        {trigger: "body:not(:has(.o_erplibre_studio_name_blockers))"},
        {trigger: ".o_erplibre_studio_inspector_tab[data-tab=changes]", run: "click"},
        {trigger: ".o_erplibre_studio_changes li[data-type=add_field]"},
        {trigger: ".o_erplibre_studio_rail_item[data-space=security]:enabled", run: "click"},
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
        // Apply of the top bar opens the review; nothing leaves the
        // database, so its Apply needs no « I understand ».
        {trigger: ".o_erplibre_studio_apply_bar:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_review_group[data-kind=model] .o_erplibre_studio_review_item[data-type=rule]"},
        {trigger: "body:not(:has(.o_erplibre_studio_review_removal))"},
        {trigger: ".o_erplibre_studio_apply:enabled", run: "click"},
        {trigger: ".o_erplibre_studio_state[data-state=applied]"},
        {trigger: ".o_erplibre_studio_close", run: "click"},
        {trigger: ".o_list_view .o_data_row"},
        {trigger: ".o_navbar_apps_menu button", run: "click"},
        {trigger: ".o_app[data-menu-xmlid='studio_tour_models.menu_app']:contains(Tour item)"},
    ],
});
