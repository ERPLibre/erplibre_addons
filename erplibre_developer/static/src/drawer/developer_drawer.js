/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillUnmount, useEffect, useRef, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

const MODEL = "erplibre.developer";
const {DateTime} = luxon;

/** A server datetime (UTC, « YYYY-MM-DD HH:MM:SS ») in the user's timezone. */
export function formatServerDateTime(value) {
    return value ? formatDateTime(deserializeDateTime(value)) : "";
}

/** An ISO 8601 date with its offset (``git log %aI``) in the user's timezone. */
export function formatIsoDateTime(value) {
    const date = value ? DateTime.fromISO(value) : null;
    return date && date.isValid ? formatDateTime(date.setZone("default")) : value || "";
}

/** A file and a line: copied to the clipboard, or opened in the IDE. */
export class SourceLocation extends Component {
    static template = "erplibre_developer.SourceLocation";
    static props = {
        file: {type: [String, Boolean], optional: true},
        fileRel: {type: [String, Boolean], optional: true},
        line: {type: Number, optional: true},
        ide: {type: Boolean, optional: true},
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // Without a clipboard (no secure context), the path shows in a
        // selected field of the drawer, to copy by hand.
        this.copyState = useState({manual: false});
        this.manualRef = useRef("manual");
        useEffect(
            (el) => {
                if (el) {
                    el.focus();
                    el.select();
                }
            },
            () => [this.manualRef.el]
        );
    }

    get text() {
        const line = this.props.line ? `:${this.props.line}` : "";
        return `${this.props.fileRel || this.props.file}${line}`;
    }

    get fullText() {
        const line = this.props.line ? `:${this.props.line}` : "";
        return `${this.props.file}${line}`;
    }

    async copy() {
        try {
            await browser.navigator.clipboard.writeText(this.fullText);
            this.copyState.manual = false;
            this.notification.add(_t("Path copied."), {type: "info"});
        } catch {
            this.copyState.manual = true;
            this.notification.add(this.fullText, {title: _t("Copy this path"), type: "warning"});
        }
    }

    closeManual() {
        this.copyState.manual = false;
    }

    async openInIde() {
        await this.orm.call(MODEL, "action_open_in_ide", [this.props.file, this.props.line || 0]);
    }
}

export class DeveloperDrawer extends Component {
    static template = "erplibre_developer.DeveloperDrawer";
    static components = {SourceLocation};
    static props = {};

    setup() {
        this.dev = useService("erplibre_developer");
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState(this.dev.state);
        this.data = useState({
            loading: false,
            error: null,
            info: null,
            code: null,
            codeLoading: false,
            codeError: null,
            commits: {},
            showCombined: false,
            expanded: {},
            filter: "",
        });
        this.fieldsRef = useRef("fields");
        this.loadedVersion = null;
        // Request counters: the answer of a call that a newer one replaced
        // (new target, refresh) is dropped.
        this.loadSeq = 0;
        this.codeSeq = 0;
        useEffect(
            (open, version) => {
                if (open && version !== this.loadedVersion) {
                    this.load();
                }
            },
            () => [this.state.open, this.state.version]
        );
        useEffect(
            (tab, info) => {
                if (tab === "code" && info && !this.data.code && !this.data.codeLoading) {
                    this.loadCode();
                }
            },
            () => [this.state.tab, this.data.info]
        );
        useEffect(
            (selected, tab) => {
                if (!selected || tab !== "fields" || !this.fieldsRef.el) {
                    return;
                }
                const row = this.fieldsRef.el.querySelector(`[data-field="${CSS.escape(selected)}"]`);
                if (row && row.scrollIntoView) {
                    row.scrollIntoView({block: "center"});
                }
            },
            () => [this.state.selectedField, this.state.tab, this.data.info]
        );
        onWillUnmount(() => this.dev.clearHighlight());
    }

    // ── loading ─────────────────────────────────────────────────────────

    async load() {
        const seq = ++this.loadSeq;
        // A code call still running belongs to the former target.
        this.codeSeq++;
        const target = this.state.target;
        this.loadedVersion = this.state.version;
        Object.assign(this.data, {
            info: null,
            code: null,
            codeLoading: false,
            codeError: null,
            commits: {},
            error: null,
        });
        if (!target) {
            this.data.loading = false;
            this.data.error = _t("This page shows no view.");
            return;
        }
        this.data.loading = true;
        let info = null;
        let error = null;
        try {
            info = await this.orm.call(
                MODEL,
                "get_view_info",
                [target.resModel, target.viewId || false, target.viewType],
                {action_id: target.actionId || false}
            );
        } catch (err) {
            error = (err.data && err.data.message) || err.message || String(err);
        }
        if (seq !== this.loadSeq) {
            return;
        }
        Object.assign(this.data, {info, error, loading: false});
    }

    async loadCode(refresh = false) {
        if (!this.data.info) {
            return;
        }
        const seq = ++this.codeSeq;
        const modules = this.data.info.modules;
        this.data.codeLoading = true;
        this.data.codeError = null;
        let code = null;
        let error = null;
        try {
            code = await this.orm.call(MODEL, "get_code_info", [modules], {refresh});
        } catch (err) {
            error = (err.data && err.data.message) || err.message || String(err);
        }
        if (seq !== this.codeSeq) {
            return;
        }
        Object.assign(this.data, {
            code: code || this.data.code,
            codeError: error || (code && code.error) || null,
            codeLoading: false,
        });
    }

    async loadCommits(module) {
        this.data.commits[module] = {loading: true, commits: [], error: null};
        try {
            const res = await this.orm.call(MODEL, "get_module_commits", [module]);
            this.data.commits[module] = {loading: false, ...res};
        } catch (error) {
            this.data.commits[module] = {
                loading: false,
                commits: [],
                error: (error.data && error.data.message) || error.message || String(error),
            };
        }
    }

    // ── view helpers ────────────────────────────────────────────────────

    get info() {
        return this.data.info;
    }

    get tabs() {
        return [
            {id: "views", label: _t("Views & inheritance")},
            {id: "fields", label: _t("Fields & modules")},
            {id: "code", label: _t("Code & repository")},
            {id: "actions", label: _t("Dev actions")},
        ];
    }

    get filteredFields() {
        const fields = (this.info && this.info.fields) || [];
        const filter = this.data.filter.trim().toLowerCase();
        if (!filter) {
            return fields;
        }
        return fields.filter(
            (f) =>
                f.name.toLowerCase().includes(filter) ||
                (f.string || "").toLowerCase().includes(filter) ||
                (f.defined_in && (f.defined_in.module || "").includes(filter)) ||
                f.override_modules.some((m) => m.includes(filter))
        );
    }

    get codeModules() {
        return (this.data.code && this.data.code.modules) || [];
    }

    get snapshotDate() {
        return formatServerDateTime(this.data.code && this.data.code.snapshot_date);
    }

    commitDate(value) {
        return formatIsoDateTime(value);
    }

    moduleLabel(entry) {
        return entry.module || _t("Odoo core");
    }

    kindLabel(kind) {
        return (
            {
                field: _t("field"),
                compute: _t("compute"),
                inverse: _t("inverse"),
                search: _t("search"),
                onchange: _t("onchange"),
                constrains: _t("constraint"),
            }[kind] || kind
        );
    }

    shortSha(sha) {
        return (sha || "").slice(0, 12);
    }

    toggle(key) {
        this.data.expanded[key] = !this.data.expanded[key];
    }

    toggleCombined() {
        this.data.showCombined = !this.data.showCombined;
    }

    selectTab(tab) {
        this.state.tab = tab;
    }

    // ── page highlight ──────────────────────────────────────────────────

    highlight(names) {
        this.dev.highlight(names);
    }

    unhighlight() {
        this.dev.clearHighlight();
    }

    selectField(name) {
        this.state.selectedField = this.state.selectedField === name ? null : name;
        this.dev.highlight(this.state.selectedField ? [name] : []);
    }

    toggleInspect() {
        if (this.state.inspecting) {
            this.dev.stopInspect();
        } else {
            this.dev.startInspect();
        }
    }

    close() {
        this.dev.close();
    }

    refresh() {
        this.load();
    }

    // ── developer actions ───────────────────────────────────────────────

    async upgrade(module) {
        // The confirmation is a dialog: inspection would catch its clicks.
        this.dev.stopInspect();
        const action = await this.orm.call(MODEL, "action_upgrade_module", [module]);
        await this.action.doAction(action);
    }

    async reloadAssets() {
        await this.orm.call(MODEL, "action_reload_assets", []);
        this.notification.add(_t("Asset bundles deleted: the page reloads."), {type: "info"});
        browser.location.reload();
    }
}
