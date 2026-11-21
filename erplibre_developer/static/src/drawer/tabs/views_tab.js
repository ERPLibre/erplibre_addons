/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, toRaw, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {SourceLocation, archLines, isDimmed, moduleColor, specNote, viewHighlightItems} from "../common";

// The indentation of one level of the combined arch.
const INDENT = "  ";

/**
 * « Views & inheritance »: the view shown with its action, every view
 * combined into it in the order Odoo applies them, as a numbered rail of
 * rows that open on their specs and their arch, and the combined arch.
 *
 * The open rows and the arch shown (``data.expanded``), ``showCombined``,
 * the search in the combined arch and its « Node origins » switch live in
 * the drawer's ``data``, so they survive a switch of tab. The « Touching
 * this field » mode (``viewsByField``) and the field it takes
 * (``selectedField``) live in the service's state, which Inspect writes.
 *
 * Hovering or focusing a view outlines in the page what it touches
 * (``viewHighlightItems``); the module filter dims the views, the lines of
 * the combined arch and the card of the other modules.
 *
 * The card ends on an empty ``.o_erplibre_dev_view_actions`` that other
 * modules extend: erplibre_studio adds « Customize this view » there,
 * through the ``action`` service of this component.
 */
export class ViewsTab extends Component {
    static template = "erplibre_developer.ViewsTab";
    static components = {SourceLocation};
    static props = {
        info: Object,
        data: Object,
        dev: Object,
    };

    setup() {
        this.devState = useState(this.props.dev.state);
        this.action = useService("action");
        // The lines of the arches, tokenised once per payload: {views: Map
        // of view id → lines, combined}.
        this.archCache = new WeakMap();
    }

    get info() {
        return this.props.info;
    }

    get data() {
        return this.props.data;
    }

    // ── current view ────────────────────────────────────────────────────

    moduleColor(name) {
        return name ? moduleColor(name) : 0;
    }

    modeLabel(mode) {
        return {primary: _t("primary"), extension: _t("extension")}[mode] || mode;
    }

    // ── applied views ───────────────────────────────────────────────────

    /**
     * The fields each view touches, as a Map of view id → [field name].
     * An extension names those of its specs (``view.fields``); the root
     * view shows its fields with its own arch, which only the
     * ``view_ids`` of ``info.fields`` count. Built once per payload.
     */
    get touchedByView() {
        const cache = this.cacheOf(this.info);
        if (!cache.touched) {
            const touched = new Map();
            const add = (id, name) => {
                if (!touched.has(id)) {
                    touched.set(id, []);
                }
                const names = touched.get(id);
                if (!names.includes(name)) {
                    names.push(name);
                }
            };
            for (const view of this.info.views || []) {
                for (const name of view.fields || []) {
                    add(view.id, name);
                }
            }
            for (const field of this.info.fields || []) {
                for (const id of field.view_ids || []) {
                    add(id, field.name);
                }
            }
            cache.touched = touched;
        }
        return cache.touched;
    }

    /** The fields the views touch, in the order of the views: the picker. */
    get fieldChoices() {
        const touched = this.touchedByView;
        const names = [];
        for (const view of this.info.views || []) {
            for (const name of touched.get(view.id) || []) {
                if (!names.includes(name)) {
                    names.push(name);
                }
            }
        }
        return names;
    }

    get byField() {
        return Boolean(this.devState.viewsByField);
    }

    /**
     * The field of the « Touching this field » mode: the selected field
     * when a view names it, else the first field the views name.
     */
    get currentField() {
        const choices = this.fieldChoices;
        const selected = this.devState.selectedField;
        return choices.includes(selected) ? selected : choices[0] || null;
    }

    setByField(value) {
        this.devState.viewsByField = value;
    }

    pickField(name) {
        this.devState.selectedField = name;
    }

    /**
     * The views listed, each as {view, n}: ``n`` is its rank in the order
     * of application, which a filtered list keeps.
     */
    get rows() {
        const rows = (this.info.views || []).map((view, index) => ({view, n: index + 1}));
        if (!this.byField) {
            return rows;
        }
        const field = this.currentField;
        const touched = this.touchedByView;
        return rows.filter((row) => (touched.get(row.view.id) || []).includes(field));
    }

    get countLabel() {
        const total = (this.info.views || []).length;
        if (this.byField && this.currentField) {
            return _t("%(shown)s of %(total)s touch %(field)s", {
                shown: this.rows.length,
                total,
                field: this.currentField,
            });
        }
        return total === 1 ? _t("1 view") : _t("%s views", total);
    }

    /** The module filter names a module none of the views comes from. */
    get moduleNote() {
        const filter = this.devState.moduleFilter;
        if (!filter || (this.info.views || []).some((view) => view.module === filter)) {
            return "";
        }
        return _t("No view of %s on this page: its effects are in the Fields tab.", filter);
    }

    isExpanded(view) {
        return Boolean(this.data.expanded["view_" + view.id]);
    }

    toggleView(view) {
        this.data.expanded["view_" + view.id] = !this.isExpanded(view);
    }

    get allExpanded() {
        const rows = this.rows;
        return rows.length > 0 && rows.every((row) => this.isExpanded(row.view));
    }

    toggleAll() {
        const open = !this.allExpanded;
        for (const row of this.rows) {
            this.data.expanded["view_" + row.view.id] = open;
        }
    }

    isArchShown(view) {
        return Boolean(this.data.expanded["arch_" + view.id]);
    }

    toggleArch(view) {
        this.data.expanded["arch_" + view.id] = !this.isArchShown(view);
    }

    specCount(view) {
        const count = (view.specs || []).length;
        return count ? _t("%s xpath", count) : _t("base");
    }

    /** « priority 16 · extension · groups: … » */
    viewMeta(view) {
        const parts = [_t("priority %s", view.priority), this.modeLabel(view.mode)];
        if ((view.groups || []).length) {
            parts.push(_t("groups: %s", view.groups.join(", ")));
        }
        return parts.join(" · ");
    }

    specNote(spec) {
        return specNote(spec);
    }

    /** The cached arch lines of the payload ``info``. */
    cacheOf(info) {
        const raw = toRaw(info);
        let cache = this.archCache.get(raw);
        if (!cache) {
            cache = {views: new Map(), combined: null, touched: null};
            this.archCache.set(raw, cache);
        }
        return cache;
    }

    /** The lines of a view's own arch, coloured: [{n, text, tokens}]. */
    viewArch(view) {
        const cache = this.cacheOf(this.info).views;
        if (!cache.has(view.id)) {
            cache.set(view.id, archLines((view.arch || "").split("\n")));
        }
        return cache.get(view.id);
    }

    archLabel(view) {
        return _t("Arch of %s", view.xml_id || view.name);
    }

    highlightView(view) {
        this.props.dev.highlight(viewHighlightItems(view));
    }

    unhighlight() {
        this.props.dev.clearHighlight();
    }

    /** Whether the module filter dims an item of ``modules``. */
    dimmed(modules) {
        return isDimmed(this.devState.moduleFilter, modules);
    }

    // ── combined arch ───────────────────────────────────────────────────

    toggleCombined() {
        this.data.showCombined = !this.data.showCombined;
    }

    toggleOrigins() {
        this.data.showOrigins = !this.data.showOrigins;
    }

    /**
     * The combined arch as {lines, hasOrigins, legend}. From
     * ``combined_lines`` (one per node, indented by its depth), each line
     * names the module that brought its node (``origin``) and those that
     * changed its attributes (``attrOrigin``); ``legend`` lists these
     * modules in the order they first appear. Without ``combined_lines``,
     * the lines of ``combined_arch``, with no origin.
     */
    get combinedBase() {
        const cache = this.cacheOf(this.info);
        if (cache.combined) {
            return cache.combined;
        }
        const source = this.info.combined_lines;
        let combined;
        if (Array.isArray(source) && source.length) {
            const lines = archLines(source.map((line) => INDENT.repeat(line.depth || 0) + line.text));
            const legend = [];
            const note = (module) => {
                if (module && !legend.includes(module)) {
                    legend.push(module);
                }
            };
            lines.forEach((line, index) => {
                const origin = source[index].origin || false;
                const attrOrigin = source[index].attr_origin || [];
                note(origin);
                attrOrigin.forEach(note);
                Object.assign(line, {
                    origin,
                    attrOrigin,
                    modules: [origin, ...attrOrigin].filter(Boolean),
                    title: this.originTitle(origin, attrOrigin),
                });
            });
            combined = {lines, hasOrigins: true, legend};
        } else {
            const lines = archLines((this.info.combined_arch || "").split("\n"));
            for (const line of lines) {
                Object.assign(line, {origin: false, attrOrigin: [], modules: null, title: ""});
            }
            combined = {lines, hasOrigins: false, legend: []};
        }
        for (const line of combined.lines) {
            line.lower = line.text.toLowerCase();
        }
        cache.combined = combined;
        return combined;
    }

    originTitle(origin, attrOrigin) {
        const parts = [];
        if (origin) {
            parts.push(_t("Node added by %s", origin));
        }
        if (attrOrigin.length) {
            parts.push(_t("attributes changed by %s", attrOrigin.join(", ")));
        }
        return parts.join(" · ");
    }

    get query() {
        return (this.data.archQuery || "").trim().toLowerCase();
    }

    /** The combined arch with the numbers of the lines the search finds. */
    get combined() {
        const base = this.combinedBase;
        const query = this.query;
        const matches = new Set();
        if (query) {
            for (const line of base.lines) {
                if (line.lower.includes(query)) {
                    matches.add(line.n);
                }
            }
        }
        return {...base, matches};
    }

    /** Whether the module filter dims a line of the combined arch. */
    lineDimmed(line) {
        return line.modules !== null && this.dimmed(line.modules);
    }

    combinedCountLabel(combined) {
        const query = (this.data.archQuery || "").trim();
        const count = combined.matches.size;
        if (!query) {
            return combined.lines.length === 1 ? _t("1 line") : _t("%s lines", combined.lines.length);
        }
        if (!count) {
            return _t("No line contains “%s”", query);
        }
        return count === 1
            ? _t("1 line contains “%s”", query)
            : _t("%(count)s lines contain “%(query)s”", {count, query});
    }

    get combinedSubtitle() {
        const count = (this.info.views || []).length;
        return count === 1 ? _t("the arch of the view") : _t("the %s views combined into one arch", count);
    }
}
