/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, useEffect, useRef, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {_t} from "@web/core/l10n/translation";
import {SourceLocation, isDimmed, moduleColor, specNote, specTarget} from "../common";

// How many frames ``openPage`` waits for the form to show a page.
const PAGE_FRAMES = 10;

// The kinds of fields the filter chips keep, each a test on a field.
const FIELD_FILTERS = {
    all: () => true,
    overridden: (field) => (field.overrides || []).length > 0,
    custom: (field) => Boolean(field.manual),
    relational: (field) => Boolean(field.relation),
};

/**
 * « Fields & modules »: the fields of the view as a compact list, and the
 * card of one field above it: its flags, the chain of the classes
 * that define and override it, the views that touch it, and the notebook
 * page that hides it.
 *
 * The text filter (``data.filter``) and the kind filter
 * (``data.fieldFilter``) live in the drawer's state, so they survive a
 * switch of tab. The card shows ``selectedField`` of the service, which a
 * click on a row or Inspect sets; without one, the first field listed. The
 * module filter dims the fields that no definition, override or view ties
 * to the module, and the steps and views of the card of other modules.
 */
export class FieldsTab extends Component {
    static template = "erplibre_developer.FieldsTab";
    static components = {SourceLocation};
    static props = {
        info: Object,
        data: Object,
        dev: Object,
    };

    setup() {
        this.state = useState(this.props.dev.state);
        // ``tick`` renders the card again after a page of the form opens:
        // the page note reads the DOM of the form, which OWL does not track.
        this.ui = useState({tick: 0});
        this.cardRef = useRef("card");
        // The card of a new selection scrolls into view when its top is
        // above the visible part of the body, the one scroll of the tab: a
        // row clicked far down the list, or Inspect, brings the card back.
        // A card already in view stays where it is.
        useEffect(
            (selected) => {
                const card = this.cardRef.el;
                if (!selected || !card || !card.scrollIntoView) {
                    return;
                }
                const body = card.closest(".o_erplibre_dev_body");
                if (
                    body &&
                    card.getBoundingClientRect().top < body.getBoundingClientRect().top
                ) {
                    card.scrollIntoView({block: "start"});
                }
            },
            () => [this.state.selectedField, this.props.info]
        );
    }

    get info() {
        return this.props.info;
    }

    get data() {
        return this.props.data;
    }

    get fields() {
        return this.info.fields || [];
    }

    // ── list ────────────────────────────────────────────────────────────

    /** The views of the payload by id, each as {view, n}: n its rank. */
    get viewsById() {
        return new Map((this.info.views || []).map((view, index) => [view.id, {view, n: index + 1}]));
    }

    /** The views that show, add or target ``field``, in their order. */
    fieldViews(field) {
        const byId = this.viewsById;
        return (field.view_ids || [])
            .map((id) => byId.get(id))
            .filter(Boolean)
            .sort((a, b) => a.n - b.n);
    }

    /**
     * The modules of a field, each once: its definition, its overrides,
     * then the views that touch it. The core of Odoo has none.
     */
    fieldModules(field) {
        const modules = [
            field.defined_in && field.defined_in.module,
            ...(field.overrides || []).map((entry) => entry.module),
            ...this.fieldViews(field).map((row) => row.view.module),
        ];
        return [...new Set(modules.filter(Boolean))];
    }

    get filterChips() {
        const labels = {
            all: _t("All"),
            overridden: _t("Overridden"),
            custom: _t("Custom fields"),
            relational: _t("Relational"),
        };
        return Object.entries(FIELD_FILTERS).map(([id, keep]) => ({
            id,
            label: labels[id],
            count: this.fields.filter(keep).length,
        }));
    }

    get fieldFilter() {
        return FIELD_FILTERS[this.data.fieldFilter] ? this.data.fieldFilter : "all";
    }

    setFieldFilter(id) {
        this.data.fieldFilter = id;
    }

    clearFilter() {
        this.data.filter = "";
    }

    /** The fields of the kind chosen whose name, label or module match. */
    get filteredFields() {
        const keep = FIELD_FILTERS[this.fieldFilter];
        const filter = this.data.filter.trim().toLowerCase();
        return this.fields.filter(
            (f) =>
                keep(f) &&
                (!filter ||
                    f.name.toLowerCase().includes(filter) ||
                    (f.string || "").toLowerCase().includes(filter) ||
                    this.fieldModules(f).some((m) => m.toLowerCase().includes(filter)))
        );
    }

    moduleLabel(entry) {
        return entry.module || _t("Odoo core");
    }

    moduleColor(name) {
        return name ? moduleColor(name) : 0;
    }

    /** « name · type → relation »: the title of a row. */
    rowTitle(field) {
        return [field.name, field.type].join(" · ") + (field.relation ? ` → ${field.relation}` : "");
    }

    definedInText(field) {
        if (field.defined_in) {
            return _t("Defined in %s", this.moduleLabel(field.defined_in));
        }
        return field.manual ? _t("Custom field, defined in the database") : "";
    }

    overriddenByText(field) {
        const modules = field.override_modules || [];
        return modules.length ? _t("Overridden by %s", modules.join(", ")) : "";
    }

    /** Every module of a row, in words: its dots carry only a colour. */
    modulesText(field) {
        const modules = this.fieldModules(field);
        return modules.length ? _t("Modules: %s", modules.join(", ")) : "";
    }

    /** The page tag of a field: « name · type · module +overrides ». */
    fieldItem(field) {
        const module = field.defined_in ? this.moduleLabel(field.defined_in) : field.manual ? _t("custom") : "";
        const count = (field.overrides || []).length;
        const label = [field.name, field.type, module].filter(Boolean).join(" · ");
        return {name: field.name, label: count ? `${label} +${count}` : label};
    }

    /**
     * The page items of a field: the field, and the header of the closed
     * notebook page that holds it when that page has a name.
     */
    fieldItems(field) {
        const item = this.fieldItem(field);
        const closed = this.closedPage(field);
        const page = field.node && field.node.page;
        return closed && page.name ? [item, {kind: "page", name: page.name, label: item.label}] : [item];
    }

    highlightField(field) {
        this.props.dev.highlight(this.fieldItems(field));
    }

    /** Whether the module filter dims an item of ``modules``. */
    dimmed(modules) {
        return isDimmed(this.state.moduleFilter, modules);
    }

    unhighlight() {
        this.props.dev.clearHighlight();
    }

    selectField(field) {
        this.state.selectedField = field.name;
        this.props.dev.highlight(this.fieldItems(field));
    }

    // ── card ────────────────────────────────────────────────────────────

    /** The field of the card: the selected one, else the first listed. */
    get card() {
        const selected = this.fields.find((f) => f.name === this.state.selectedField);
        return selected || this.filteredFields[0] || null;
    }

    /** The flags of a field, as Python writes them on its declaration. */
    flags(field) {
        const flags = [];
        if (field.company_dependent) {
            flags.push("company_dependent");
        }
        if (field.required) {
            flags.push("required");
        }
        if (field.readonly) {
            flags.push("readonly");
        }
        if (field.store === false) {
            flags.push("store=False");
        }
        return flags;
    }

    /**
     * The origin chain of a field in the order of the classes (MRO): its
     * first declaration, the later ones, then its compute, inverse and
     * search methods, its onchange methods and its constraints.
     */
    chain(field) {
        const steps = field.defined_in ? [{kind: "field", ...field.defined_in}] : [];
        return [...steps, ...(field.overrides || [])];
    }

    chainNote(field) {
        if (field.manual && !field.defined_in) {
            return _t("database");
        }
        const count = this.chain(field).length;
        if (!count) {
            return "";
        }
        return count === 1 ? _t("1 step") : _t("%s steps · MRO order", count);
    }

    kindLabel(kind) {
        return (
            {
                field: _t("Definition"),
                compute: _t("Computation"),
                inverse: _t("Inverse"),
                search: _t("Search method"),
                onchange: _t("Onchange"),
                constrains: _t("Constraint"),
            }[kind] || kind
        );
    }

    /**
     * The code of a step: the method, or for a declaration its source
     * (``source``, ``fields.Char(index=True)``); without a source, the
     * field class with the names of the attributes it passes,
     * ``fields.Char(index=…, tracking=…)``.
     */
    stepCode(field, step) {
        if (step.method) {
            return step.method;
        }
        if (step.source) {
            return step.source;
        }
        const type = (field.type || "")
            .split("_")
            .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
            .join("");
        const attrs = (step.attrs || []).map((attr) => `${attr}=…`).join(", ");
        return `fields.${type}(${attrs})`;
    }

    /**
     * What the view of rank ``n`` does to the field ``name``, as
     * [{position, note}]: each spec that targets it or brings it, « in the
     * arch » for the root view (rank 1), whose own arch shows it.
     */
    viewEffects(view, n, name) {
        if (n === 1) {
            return [{position: false, note: _t("in the arch")}];
        }
        const effects = [];
        for (const spec of view.specs || []) {
            const target = specTarget(spec);
            if (target && target.tag === "field" && target.name === name) {
                effects.push({position: spec.position, note: specNote(spec)});
            } else if ((spec.content || []).some((node) => node.tag === "field" && node.name === name)) {
                effects.push({position: spec.position, note: _t("adds it")});
            }
        }
        // Past the nodes a spec sends, or through an XPath on a parent.
        return effects.length ? effects : [{position: false, note: _t("names it")}];
    }

    /** Shows ``view`` open in the Views tab, among the views of ``field``. */
    showView(field, view) {
        this.data.expanded["view_" + view.id] = true;
        this.state.selectedField = field.name;
        this.state.viewsByField = true;
        this.state.tab = "views";
    }

    /**
     * The closed notebook page that holds ``field`` in the page shown, as
     * {title, link}, or null: the field shows, sits outside a page, or the
     * page shows another view than the drawer.
     */
    closedPage(field) {
        // Read so that the card renders again once a page opens.
        void this.ui.tick;
        const page = field.node && field.node.page;
        const offView = Boolean(this.state.target) && this.state.targetJsId !== this.state.pageJsId;
        if (!page || offView || this.props.dev.nodeElements("field", field.name).length) {
            return null;
        }
        const link = this.props.dev.pageLink(page);
        if (!link || link.classList.contains("active")) {
            return null;
        }
        return {title: page.string || page.name || link.textContent.trim(), link};
    }

    pageNote(closed) {
        return _t("Shown in the “%s” tab of the form.", closed.title);
    }

    /**
     * Opens the notebook page of ``field``, then outlines the field once
     * the form shows it: the form renders the page in a later frame, so
     * this waits up to ``PAGE_FRAMES`` frames for it.
     */
    async openPage(field) {
        const closed = this.closedPage(field);
        if (!closed) {
            return;
        }
        closed.link.click();
        for (let frame = 0; frame < PAGE_FRAMES; frame++) {
            await new Promise((resolve) => browser.requestAnimationFrame(resolve));
            if (this.props.dev.nodeElements("field", field.name).length) {
                break;
            }
        }
        this.ui.tick++;
        this.props.dev.highlight([this.fieldItem(field)]);
    }
}
