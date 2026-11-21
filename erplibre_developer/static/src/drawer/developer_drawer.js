/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillUnmount, useEffect, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {session} from "@web/session";
import {MODEL, formatServerDateTime, moduleColor} from "./common";
import {ActionsTab} from "./tabs/actions_tab";
import {CodeTab} from "./tabs/code_tab";
import {FieldsTab} from "./tabs/fields_tab";
import {ViewsTab} from "./tabs/views_tab";

export {formatIsoDateTime, formatServerDateTime, SourceLocation} from "./common";

// The order of the tabs, for the arrow keys of the tab list.
const TAB_IDS = ["views", "fields", "code", "actions"];

/**
 * The drawer: its header, the module filter, the tabs, the status bar and
 * the loading of what the tabs show. It owns the RPC calls and the
 * ``data`` state that the tabs (``tabs/``) receive through their props, so
 * a switch of tab keeps the filter, the open rows and the loaded code. The
 * preferences (follow, width, density) and the module filter live in the
 * service's state, which the tabs read too.
 */
export class DeveloperDrawer extends Component {
    static template = "erplibre_developer.DeveloperDrawer";
    static components = {ViewsTab, FieldsTab, CodeTab, ActionsTab};
    static props = {};

    setup() {
        this.dev = useService("erplibre_developer");
        this.orm = useService("orm");
        // The studio patch of the header opens its editor through it.
        this.action = useService("action");
        this.state = useState(this.dev.state);
        this.data = useState({
            loading: false,
            error: null,
            info: null,
            code: null,
            codeLoading: false,
            codeError: null,
            // Where the Code tab reads the repositories: « snapshot » (the
            // last erplibre_info_git snapshot) or « clones » (repo_state.py
            // now); ``codeReadAt`` is when the clones were read (ISO 8601).
            codeSource: "snapshot",
            codeReadAt: null,
            // The summary tile of the Code tab that filters its list: all,
            // repos, dirty or upgrade.
            codeTile: "all",
            // The live details of each repository, by its path
            // (``get_repo_details``), and the repositories whose recent
            // commits are open.
            repoDetails: {},
            repoCommitsOpen: {},
            // The module the Code tab sends to the Actions tab to upgrade.
            upgradeRequest: null,
            // The modules checked in the Actions tab ({module: bool}), null
            // until a box changes: the modules to upgrade count as checked.
            upgradeChecked: null,
            // The recent commits of each module, and the modules whose
            // commits are open (Actions tab).
            commits: {},
            commitsOpen: {},
            // The last runs of erplibre_info (``get_recent_runs``), read
            // when the Actions tab shows.
            runs: null,
            runsLoading: false,
            runsError: null,
            showCombined: false,
            expanded: {},
            filter: "",
            // The kind of fields the Fields tab lists: all, overridden,
            // custom or relational.
            fieldFilter: "all",
            // The search in the combined arch and its « Node origins »
            // switch (Views tab).
            archQuery: "",
            showOrigins: true,
        });
        this.loadedVersion = null;
        // Request counters: the answer of a call that a newer one replaced
        // (new target, refresh) is dropped.
        this.loadSeq = 0;
        this.codeSeq = 0;
        this.detailsSeq = 0;
        this.runsSeq = 0;
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
            (tab, info) => {
                if (tab === "actions" && info && !this.data.runs && !this.data.runsLoading) {
                    this.loadRuns();
                }
            },
            () => [this.state.tab, this.data.info]
        );
        onWillUnmount(() => this.dev.clearHighlight());
    }

    // ── loading ─────────────────────────────────────────────────────────

    async load() {
        const seq = ++this.loadSeq;
        // A code call still running belongs to the former target.
        this.codeSeq++;
        this.detailsSeq++;
        this.runsSeq++;
        const target = this.state.target;
        this.loadedVersion = this.state.version;
        Object.assign(this.data, {
            info: null,
            code: null,
            codeLoading: false,
            codeError: null,
            codeSource: "snapshot",
            codeReadAt: null,
            repoDetails: {},
            repoCommitsOpen: {},
            upgradeRequest: null,
            upgradeChecked: null,
            commits: {},
            commitsOpen: {},
            runs: null,
            runsLoading: false,
            runsError: null,
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

    /**
     * Load ``data.code``: from the last snapshot, or with ``refresh`` from
     * the clones. A read of the clones also drops the repository details,
     * which the Code tab then reads again.
     */
    async loadCode(refresh = false) {
        if (!this.data.info) {
            return;
        }
        const seq = ++this.codeSeq;
        const modules = this.data.info.modules;
        this.data.codeLoading = true;
        this.data.codeError = null;
        this.data.codeSource = refresh ? "clones" : "snapshot";
        if (refresh) {
            this.detailsSeq++;
            this.data.repoDetails = {};
        }
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
            codeReadAt: refresh && code ? luxon.DateTime.now().toISO() : this.data.codeReadAt,
        });
    }

    /**
     * Read the uncommitted files and the recent commits of the repository
     * ``repo`` (a ``clone_rel``) into ``data.repoDetails[repo]``, the
     * commits marked against ``target``. An answer that a new target or a
     * read of the clones made out of date is dropped.
     */
    async loadRepoDetails(repo, target = false) {
        const seq = this.detailsSeq;
        const details = this.data.repoDetails;
        details[repo] = {loading: true, dirty_count: 0, dirty_files: [], commits: [], error: false};
        let result;
        try {
            result = await this.orm.call(MODEL, "get_repo_details", [repo], {target: target || false});
        } catch (err) {
            result = {
                dirty_count: 0,
                dirty_files: [],
                commits: [],
                error: (err.data && err.data.message) || err.message || String(err),
            };
        }
        if (seq !== this.detailsSeq) {
            return;
        }
        details[repo] = {loading: false, ...result};
    }

    /**
     * Load ``data.runs``, the last runs of erplibre_info. An answer that a
     * new target made out of date is dropped.
     */
    async loadRuns() {
        const seq = ++this.runsSeq;
        this.data.runsLoading = true;
        this.data.runsError = null;
        let runs = null;
        let error = null;
        try {
            runs = await this.orm.call(MODEL, "get_recent_runs", []);
        } catch (err) {
            error = (err.data && err.data.message) || err.message || String(err);
        }
        if (seq !== this.runsSeq) {
            return;
        }
        Object.assign(this.data, {runs: runs || [], runsError: error, runsLoading: false});
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

    // ── header and tabs ─────────────────────────────────────────────────

    get info() {
        return this.data.info;
    }

    /**
     * The tabs with their count, from ``get_view_info`` alone: the views
     * applied, the fields, the modules named (the Code tab loads its own
     * data only when it shows).
     */
    get tabs() {
        const info = this.info;
        const count = (list) => (info && list ? list.length : false);
        return [
            {id: "views", label: _t("Views"), title: _t("Views & inheritance"), count: count(info && info.views)},
            {id: "fields", label: _t("Fields"), title: _t("Fields & modules"), count: count(info && info.fields)},
            {id: "code", label: _t("Code"), title: _t("Code & repository"), count: count(info && info.modules)},
            {id: "actions", label: _t("Actions"), title: _t("Dev actions"), count: false},
        ];
    }

    selectTab(tab) {
        this.state.tab = tab;
    }

    /** Arrow keys, Home and End move between the tabs, as in a tab list. */
    onTabKeydown(ev) {
        const index = TAB_IDS.indexOf(this.state.tab);
        const next = {
            ArrowRight: (index + 1) % TAB_IDS.length,
            ArrowLeft: (index + TAB_IDS.length - 1) % TAB_IDS.length,
            Home: 0,
            End: TAB_IDS.length - 1,
        }[ev.key];
        if (next === undefined) {
            return;
        }
        ev.preventDefault();
        this.selectTab(TAB_IDS[next]);
        const list = ev.target.closest("[role=tablist]");
        const button = list && list.querySelector(`[data-tab="${TAB_IDS[next]}"]`);
        if (button) {
            button.focus();
        }
    }

    /** The page shows another view than the one the drawer describes. */
    get offView() {
        // Read through the reactive state, so the template follows it.
        return Boolean(this.state.target) && this.state.targetJsId !== this.state.pageJsId;
    }

    toggleInspect() {
        if (this.state.inspecting) {
            this.dev.stopInspect();
        } else {
            this.dev.startInspect();
        }
    }

    toggleFollow() {
        this.dev.setFollow(!this.state.follow);
    }

    followAgain() {
        this.dev.setFollow(true);
    }

    toggleWide() {
        this.dev.setWide(!this.state.wide);
    }

    setDensity(density) {
        this.dev.setDensity(density);
    }

    // ── module filter ───────────────────────────────────────────────────

    /** The modules of the page, each with its tag colour. */
    get moduleChips() {
        return ((this.info && this.info.modules) || []).map((name) => ({name, color: moduleColor(name)}));
    }

    /** Picks ``module``; picking it again, or « All » (null), clears it. */
    pickModule(module) {
        this.dev.setModuleFilter(module && module !== this.state.moduleFilter ? module : null);
    }

    // ── status bar ──────────────────────────────────────────────────────

    get serverVersion() {
        return session.server_version || "";
    }

    get snapshotDate() {
        return formatServerDateTime(this.info && this.info.snapshot_date);
    }

    close() {
        this.dev.close();
    }

    refresh() {
        this.load();
    }
}
