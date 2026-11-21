/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {reactive} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {DeveloperDrawer} from "./drawer/developer_drawer";

export const HIGHLIGHT_CLASS = "o_erplibre_dev_highlight";
export const DRAWER_SELECTOR = ".o_erplibre_dev_drawer";
export const BODY_OPEN_CLASS = "o_erplibre_dev_open";
export const BODY_INSPECT_CLASS = "o_erplibre_dev_inspecting";

// The page elements that render a field: a form widget, a list header or
// cell, a kanban field.
const FIELD_ELEMENTS = [".o_field_widget[name]", "th[data-name]", "td.o_data_cell[name]", ".o_kanban_record [name]"];

/**
 * The field name an element of the page renders, or null. A form label
 * points to its widget through its « for » attribute.
 */
export function fieldNameOf(element) {
    if (!element || element.closest(DRAWER_SELECTOR)) {
        return null;
    }
    const label = element.closest("label.o_form_label[for]");
    if (label) {
        const input = document.getElementById(label.getAttribute("for"));
        const widget = input && input.closest(".o_field_widget[name]");
        if (widget) {
            return widget.getAttribute("name");
        }
    }
    const node = element.closest(FIELD_ELEMENTS.join(", "));
    if (!node) {
        return null;
    }
    return node.getAttribute("name") || node.dataset.name || null;
}

/** The page elements outside the drawer that render the field ``name``. */
export function fieldElements(name) {
    const escaped = CSS.escape(name);
    const selector = FIELD_ELEMENTS.map((sel) => sel.replace(/\[((?:data-)?name)\]$/, `[$1="${escaped}"]`)).join(", ");
    return [...document.querySelectorAll(selector)].filter((el) => !el.closest(DRAWER_SELECTOR));
}

/**
 * The view shown by the action manager: {resModel, viewType, viewId,
 * actionId}, or null for a client action.
 */
export function targetFromController(controller) {
    if (!controller || !controller.action || controller.action.type !== "ir.actions.act_window") {
        return null;
    }
    const props = controller.props || {};
    const viewType = (controller.view && controller.view.type) || props.type;
    const resModel = props.resModel || controller.action.res_model;
    if (!viewType || !resModel) {
        return null;
    }
    const view = (controller.action.views || []).find((v) => v[1] === viewType);
    return {
        resModel,
        viewType,
        viewId: (view && view[0]) || false,
        actionId: controller.action.id || false,
    };
}

export const developerService = {
    dependencies: ["action"],
    start(env, {action}) {
        const state = reactive({
            open: false,
            target: null,
            // Bumped at each new target: the drawer reloads on change.
            version: 0,
            tab: "views",
            selectedField: null,
            inspecting: false,
        });
        let highlighted = [];

        function clearHighlight() {
            for (const el of highlighted) {
                el.classList.remove(HIGHLIGHT_CLASS);
            }
            highlighted = [];
        }

        function highlight(names) {
            clearHighlight();
            for (const name of names || []) {
                for (const el of fieldElements(name)) {
                    el.classList.add(HIGHLIGHT_CLASS);
                    highlighted.push(el);
                }
            }
            return highlighted.length;
        }

        function onInspectOver(ev) {
            const name = fieldNameOf(ev.target);
            if (name) {
                highlight([name]);
            }
        }

        function onInspectClick(ev) {
            if (ev.target.closest(DRAWER_SELECTOR)) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            const name = fieldNameOf(ev.target);
            stopInspect();
            if (name) {
                state.selectedField = name;
                state.tab = "fields";
                highlight([name]);
            }
        }

        function startInspect() {
            if (state.inspecting) {
                return;
            }
            state.inspecting = true;
            document.body.classList.add(BODY_INSPECT_CLASS);
            document.addEventListener("mouseover", onInspectOver, true);
            document.addEventListener("click", onInspectClick, true);
        }

        function stopInspect() {
            state.inspecting = false;
            document.body.classList.remove(BODY_INSPECT_CLASS);
            document.removeEventListener("mouseover", onInspectOver, true);
            document.removeEventListener("click", onInspectClick, true);
        }

        function setTarget(target) {
            if (!target) {
                return;
            }
            const current = state.target;
            const same =
                current &&
                current.resModel === target.resModel &&
                current.viewType === target.viewType &&
                current.viewId === target.viewId;
            if (!same) {
                state.target = target;
                state.selectedField = null;
                state.version++;
            }
        }

        function open(target) {
            setTarget(target || targetFromController(action.currentController));
            state.open = true;
            document.body.classList.add(BODY_OPEN_CLASS);
        }

        function close() {
            stopInspect();
            clearHighlight();
            state.open = false;
            document.body.classList.remove(BODY_OPEN_CLASS);
        }

        // While the drawer is open, it follows the view the user navigates to.
        env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", () => {
            if (state.open) {
                setTarget(targetFromController(action.currentController));
            }
        });

        registry.category("main_components").add("ErplibreDeveloperDrawer", {
            Component: DeveloperDrawer,
            props: {},
        });

        return {state, open, close, highlight, clearHighlight, startInspect, stopInspect, setTarget};
    },
};

registry.category("services").add("erplibre_developer", developerService);
