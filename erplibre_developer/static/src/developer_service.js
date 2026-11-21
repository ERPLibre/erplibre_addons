/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {reactive} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {registry} from "@web/core/registry";
import {DeveloperDrawer} from "./drawer/developer_drawer";

export const HIGHLIGHT_CLASS = "o_erplibre_dev_highlight";
export const DRAWER_SELECTOR = ".o_erplibre_dev_drawer";
export const BODY_OPEN_CLASS = "o_erplibre_dev_open";
export const BODY_INSPECT_CLASS = "o_erplibre_dev_inspecting";
export const BODY_WIDE_CLASS = "o_erplibre_dev_wide";
export const TAGS_CLASS = "o_erplibre_dev_tags";
export const PREFS_KEY = "erplibre_developer.drawer";
// Everything the panel shows: the drawer and, while inspecting, its banner
// above the page. Neither one is a part of the page it inspects.
export const PANEL_SELECTOR = `${DRAWER_SELECTOR}, .o_erplibre_dev_inspect_banner`;
// The floating tags shown at once; the other elements keep their outline.
export const MAX_TAGS = 6;

// The page elements that render a field: a form widget, a list header or
// cell, a kanban field.
const FIELD_ELEMENTS = [".o_field_widget[name]", "th[data-name]", "td.o_data_cell[name]", ".o_kanban_record [name]"];

/**
 * The field name an element of the page renders, or null. A form label
 * points to its widget through its « for » attribute.
 */
export function fieldNameOf(element) {
    if (!element || element.closest(PANEL_SELECTOR)) {
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

function outsidePanel(elements) {
    return [...elements].filter((el) => !el.closest(PANEL_SELECTOR));
}

/** The page elements outside the drawer that render the field ``name``. */
export function fieldElements(name) {
    const escaped = CSS.escape(name);
    const selector = FIELD_ELEMENTS.map((sel) => sel.replace(/\[((?:data-)?name)\]$/, `[$1="${escaped}"]`)).join(", ");
    return outsidePanel(document.querySelectorAll(selector));
}

/**
 * The page elements outside the drawer that render the arch node ``name``
 * of ``kind``: « field », « button » (a button of the view), « page » (the
 * header of a notebook page) or « button_box » (the smart buttons box,
 * whose ``name`` the form compiler drops).
 */
export function nodeElements(kind, name) {
    if (kind === "field") {
        return fieldElements(name);
    }
    const escaped = CSS.escape(name);
    const selector = {
        button: `button[name="${escaped}"]`,
        page: `.o_notebook_headers .nav-link[name="${escaped}"]`,
        button_box: ".o-form-buttonbox.position-relative",
    }[kind];
    return selector ? outsidePanel(document.querySelectorAll(selector)) : [];
}

/**
 * The header link of the notebook page ``page`` ({name, string}, as the
 * server gives it for a field) in the page outside the drawer, or null. A
 * page without a name is found by its title.
 */
export function pageLink(page) {
    if (!page || !(page.name || page.string)) {
        return null;
    }
    const links = outsidePanel(document.querySelectorAll(".o_notebook_headers .nav-link"));
    const found = page.name
        ? links.find((link) => link.getAttribute("name") === page.name)
        : links.find((link) => link.textContent.trim() === page.string);
    return found || null;
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

/** Whether two targets name the same view of the same model. */
export function sameTarget(a, b) {
    return Boolean(a && b && a.resModel === b.resModel && a.viewType === b.viewType && a.viewId === b.viewId);
}

/**
 * The preferences of this browser: {follow, wide, density}. A storage that
 * is missing, blocked or holds anything else gives the defaults.
 */
export function readPrefs() {
    const prefs = {follow: true, wide: false, density: "comfortable"};
    try {
        const stored = JSON.parse(browser.localStorage.getItem(PREFS_KEY) || "{}");
        if (typeof stored.follow === "boolean") {
            prefs.follow = stored.follow;
        }
        if (typeof stored.wide === "boolean") {
            prefs.wide = stored.wide;
        }
        if (stored.density === "compact" || stored.density === "comfortable") {
            prefs.density = stored.density;
        }
    } catch {
        // The defaults stand.
    }
    return prefs;
}

function writePrefs(state) {
    try {
        browser.localStorage.setItem(
            PREFS_KEY,
            JSON.stringify({follow: state.follow, wide: state.wide, density: state.density})
        );
    } catch {
        // Not kept past this page: the drawer works the same.
    }
}

/**
 * Normalises what ``highlight`` takes: a field name, or {kind, name,
 * label}. ``kind`` defaults to « field » and ``label`` to the name.
 */
function highlightItem(item) {
    if (typeof item === "string") {
        return {kind: "field", name: item, label: item};
    }
    return {kind: item.kind || "field", name: item.name, label: item.label || item.name};
}

export const developerService = {
    dependencies: ["action"],
    start(env, {action}) {
        const prefs = readPrefs();
        const state = reactive({
            open: false,
            // The view the drawer describes.
            target: null,
            // The view the page shows, and the ids of the action manager
            // controllers behind ``target`` and the page: they differ once
            // the user navigates while the drawer does not follow.
            pageTarget: null,
            targetJsId: null,
            pageJsId: null,
            // Bumped at each new target: the drawer reloads on change.
            version: 0,
            tab: "views",
            selectedField: null,
            // The Views tab lists only the views that touch selectedField.
            viewsByField: false,
            inspecting: false,
            // The module whose items stay bright in every tab, others dim.
            moduleFilter: null,
            follow: prefs.follow,
            wide: prefs.wide,
            density: prefs.density,
        });
        let highlighted = [];
        let tags = null;

        /**
         * Whether the page shows another view than the drawer: Inspect and
         * the highlight would then reach the elements of that other view.
         */
        function isOffView() {
            return Boolean(state.target) && state.targetJsId !== state.pageJsId;
        }

        /** Inspect needs a view described, and that view on the page. */
        function canInspect() {
            return Boolean(state.target) && !isOffView();
        }

        // ── highlight and its tags ─────────────────────────────────────

        function placeTags() {
            if (!tags) {
                return;
            }
            for (const tag of tags.children) {
                const box = tag._target.getBoundingClientRect();
                const height = tag.offsetHeight || 18;
                const above = box.top - height - 4;
                tag.style.left = `${Math.max(0, box.left)}px`;
                tag.style.top = `${above >= 0 ? above : box.bottom + 4}px`;
                tag.classList.toggle("d-none", !box.width && !box.height);
            }
        }

        function clearHighlight() {
            for (const el of highlighted) {
                el.classList.remove(HIGHLIGHT_CLASS);
            }
            highlighted = [];
            if (tags) {
                tags.remove();
                tags = null;
                window.removeEventListener("scroll", placeTags, true);
                window.removeEventListener("resize", placeTags);
            }
        }

        /**
         * Outlines the page elements of ``items`` (field names, or {kind,
         * name, label}, see ``nodeElements``) and floats the label of the
         * first ``MAX_TAGS`` items found above their first element. The
         * tags live in one fixed container of the web client that
         * ``clearHighlight`` removes. Returns the count of elements outlined;
         * nothing is outlined while the page shows another view.
         */
        function highlight(items) {
            clearHighlight();
            if (isOffView()) {
                return 0;
            }
            const labelled = [];
            for (const item of (items || []).map(highlightItem)) {
                const elements = nodeElements(item.kind, item.name);
                for (const el of elements) {
                    el.classList.add(HIGHLIGHT_CLASS);
                    highlighted.push(el);
                }
                if (elements.length && labelled.length < MAX_TAGS) {
                    labelled.push([elements[0], item.label]);
                }
            }
            if (labelled.length) {
                tags = document.createElement("div");
                tags.className = TAGS_CLASS;
                tags.setAttribute("aria-hidden", "true");
                for (const [el, label] of labelled) {
                    const tag = document.createElement("span");
                    tag.className = "o_erplibre_dev_tag";
                    tag.textContent = label;
                    tag._target = el;
                    tags.appendChild(tag);
                }
                const [first] = labelled[0];
                (first.closest(".o_web_client") || document.body).appendChild(tags);
                placeTags();
                window.addEventListener("scroll", placeTags, true);
                window.addEventListener("resize", placeTags);
            }
            return highlighted.length;
        }

        // ── inspect ────────────────────────────────────────────────────

        function onInspectOver(ev) {
            const name = fieldNameOf(ev.target);
            if (name) {
                highlight([name]);
            }
        }

        function onInspectClick(ev) {
            if (ev.target.closest(PANEL_SELECTOR)) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            const name = fieldNameOf(ev.target);
            stopInspect();
            if (name) {
                state.selectedField = name;
                // The Views tab filtered by field takes the field picked;
                // else the Fields tab shows it.
                if (!(state.tab === "views" && state.viewsByField)) {
                    state.tab = "fields";
                }
                highlight([name]);
            }
        }

        function onInspectKey(ev) {
            if (ev.key === "Escape") {
                ev.preventDefault();
                ev.stopPropagation();
                stopInspect();
            }
        }

        function startInspect() {
            if (state.inspecting || !canInspect()) {
                return;
            }
            state.inspecting = true;
            document.body.classList.add(BODY_INSPECT_CLASS);
            document.addEventListener("mouseover", onInspectOver, true);
            document.addEventListener("click", onInspectClick, true);
            document.addEventListener("keydown", onInspectKey, true);
        }

        function stopInspect() {
            state.inspecting = false;
            document.body.classList.remove(BODY_INSPECT_CLASS);
            document.removeEventListener("mouseover", onInspectOver, true);
            document.removeEventListener("click", onInspectClick, true);
            document.removeEventListener("keydown", onInspectKey, true);
        }

        // ── target, follow, preferences ────────────────────────────────

        /**
         * Describes ``target``; a new target drops the field selected, the
         * module filter and the « Touching this field » mode, and bumps
         * ``version`` so that the drawer reloads. A null target is ignored.
         */
        function setTarget(target) {
            if (!target) {
                return;
            }
            if (!sameTarget(state.target, target)) {
                resetTarget(target);
            }
        }

        function resetTarget(target) {
            state.target = target;
            state.selectedField = null;
            state.moduleFilter = null;
            state.viewsByField = false;
            state.version++;
        }

        /**
         * Describes the view the page shows. A page without a view (a
         * client action) clears the target: the drawer then says that the
         * page shows no view, instead of keeping the former view as if the
         * page still showed it.
         */
        function followPage() {
            if (state.pageTarget) {
                setTarget(state.pageTarget);
            } else if (state.target) {
                resetTarget(null);
            }
            state.targetJsId = state.pageJsId;
        }

        /** Notes the view the page shows: {jsId, target} of the controller. */
        function readPage() {
            const controller = action.currentController;
            state.pageJsId = (controller && controller.jsId) || null;
            state.pageTarget = targetFromController(controller);
        }

        function open(target) {
            readPage();
            if (target) {
                setTarget(target);
                state.targetJsId = state.pageJsId;
            } else {
                followPage();
            }
            state.open = true;
            document.body.classList.add(BODY_OPEN_CLASS);
            document.body.classList.toggle(BODY_WIDE_CLASS, state.wide);
        }

        function close() {
            stopInspect();
            clearHighlight();
            state.open = false;
            document.body.classList.remove(BODY_OPEN_CLASS, BODY_WIDE_CLASS);
        }

        /** Follows the navigation again, from the view the page shows. */
        function setFollow(follow) {
            state.follow = Boolean(follow);
            writePrefs(state);
            if (state.follow && state.open) {
                followPage();
                if (!canInspect()) {
                    stopInspect();
                }
            }
        }

        function setWide(wide) {
            state.wide = Boolean(wide);
            writePrefs(state);
            if (state.open) {
                document.body.classList.toggle(BODY_WIDE_CLASS, state.wide);
            }
        }

        function setDensity(density) {
            state.density = density === "compact" ? "compact" : "comfortable";
            writePrefs(state);
        }

        /** Dims every item of another module than ``module``; null: none. */
        function setModuleFilter(module) {
            state.moduleFilter = module || null;
        }

        // While the drawer is open, it notes the view the page shows and
        // follows it unless the user unpinned it. Elements outlined on the
        // former view are gone; Inspect stops when the page leaves the view
        // the drawer describes or shows none.
        env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", () => {
            if (!state.open) {
                return;
            }
            readPage();
            if (state.follow) {
                followPage();
            }
            clearHighlight();
            if (!canInspect()) {
                stopInspect();
            }
        });

        registry.category("main_components").add("ErplibreDeveloperDrawer", {
            Component: DeveloperDrawer,
            props: {},
        });

        return {
            state,
            open,
            close,
            highlight,
            clearHighlight,
            startInspect,
            stopInspect,
            setTarget,
            setFollow,
            setWide,
            setDensity,
            setModuleFilter,
            isOffView,
            canInspect,
            nodeElements,
            pageLink,
        };
    },
};

registry.category("services").add("erplibre_developer", developerService);
