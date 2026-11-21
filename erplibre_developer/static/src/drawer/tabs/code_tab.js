/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillUnmount, useEffect, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {
    formatIsoDateTime,
    formatRelativeIso,
    formatServerDateTime,
    isDimmed,
    moduleColor,
    moduleHighlightItems,
    shortSha,
} from "../common";

// How long a repository's copy button shows « Copied », in milliseconds.
const COPIED_DELAY = 2000;

// The states of a repository that are no problem: on the manifest, or
// ahead of it (local work).
const SOUND_STATES = ["conforme", "en_avance"];

// The Bootstrap colour of each repository state, for its chip.
const STATE_COLORS = {
    conforme: "success",
    en_avance: "info",
    sale: "warning",
    decale: "warning",
    hors_manifeste: "warning",
    absent: "danger",
    erreur: "danger",
};

/** Whether the version on disk of ``module`` differs from the installed one. */
function upgradePending(module) {
    return Boolean(module.installed_version && module.code_version && module.code_version !== module.installed_version);
}

/**
 * « Code & repository »: the modules of the page grouped by the git
 * repository that holds them, the repositories with a problem first
 * (modified tree, upgrade pending, off the manifest), the modules in no
 * repository last.
 *
 * The drawer loads ``data.code`` (``loadCode``) when this tab shows, from
 * the last snapshot or, with « Clones », from the clones. Each repository
 * shows its state, branch, HEAD and gap to the manifest; a modified one
 * lists its uncommitted files, and « Recent commits » its last commits,
 * both read live by ``loadRepoDetails`` into ``data.repoDetails``: the
 * modified ones as soon as they show, the others when their commits open.
 *
 * The summary tiles (``data.codeTile``) hide what they leave out, with a
 * « Show all »; the module filter only dims, as in the other tabs.
 */
export class CodeTab extends Component {
    static template = "erplibre_developer.CodeTab";
    static props = {
        info: Object,
        data: Object,
        dev: Object,
        loadCode: Function,
        loadRepoDetails: Function,
    };

    setup() {
        this.devState = useState(this.props.dev.state);
        this.notification = useService("notification");
        // The path of the repository whose copy button shows « Copied ».
        this.ui = useState({copied: null});
        this.copiedTimer = null;
        onWillUnmount(() => browser.clearTimeout(this.copiedTimer));
        // The modified repositories read their uncommitted files as soon
        // as they show, and an open « Recent commits » its commits: after
        // each load of the code, and after a read of the clones dropped the
        // details.
        useEffect(
            (code, loading) => {
                if (code && !loading) {
                    this.loadMissingDetails();
                }
            },
            () => [this.data.code, this.data.codeLoading, this.data.repoDetails]
        );
    }

    get data() {
        return this.props.data;
    }

    get codeModules() {
        return (this.data.code && this.data.code.modules) || [];
    }

    // ── source ──────────────────────────────────────────────────────────

    get snapshotDate() {
        return formatServerDateTime(this.data.code && this.data.code.snapshot_date);
    }

    get readAt() {
        return formatIsoDateTime(this.data.codeReadAt);
    }

    get fromClones() {
        return this.data.codeSource === "clones";
    }

    readSnapshot() {
        if (this.fromClones || !this.data.code) {
            this.props.loadCode(false);
        }
    }

    readClones() {
        if (!this.data.codeLoading) {
            this.props.loadCode(true);
        }
    }

    // ── repositories ────────────────────────────────────────────────────

    /**
     * The modules grouped by repository: [{key, path, clone, repo, source,
     * modules, dirty, pending, problem}], ``key`` the path of the clone
     * (``clone_rel``), "" for the modules in no repository. ``problem``
     * orders them: a modified tree weighs most, then an upgrade pending,
     * then a state off the manifest; equal ones keep their order.
     */
    get groups() {
        const byKey = new Map();
        for (const module of this.codeModules) {
            const key = module.clone_rel || (module.repo && module.repo.path) || "";
            if (!byKey.has(key)) {
                byKey.set(key, {key, path: key, clone: module.clone || false, repo: false, source: false, modules: []});
            }
            const group = byKey.get(key);
            if (!group.repo && module.repo) {
                group.repo = module.repo;
                group.source = module.repo_source;
            }
            group.modules.push(module);
        }
        const groups = [...byKey.values()].map((group, index) => {
            const details = group.key && this.data.repoDetails[group.key];
            const dirty = Boolean((group.repo && group.repo.dirty) || (details && details.dirty_count));
            const pending = group.modules.some(upgradePending);
            const state = group.repo && group.repo.state;
            const offManifest = Boolean(state) && !SOUND_STATES.includes(state) && state !== "sale";
            return {
                ...group,
                index,
                dirty,
                pending,
                problem: (dirty ? 4 : 0) + (pending ? 2 : 0) + (offManifest ? 1 : 0),
            };
        });
        const rank = (group) => (group.key ? -group.problem : 1);
        return groups.sort((a, b) => rank(a) - rank(b) || a.index - b.index);
    }

    /** The counts of the summary tiles, over everything loaded. */
    get tiles() {
        const groups = this.groups.filter((group) => group.key);
        const count = (n, one, many) => ({n, label: n === 1 ? one : many});
        return [
            {id: "all", ...count(this.codeModules.length, _t("module"), _t("modules"))},
            {id: "repos", ...count(groups.length, _t("repository"), _t("repositories"))},
            {
                id: "dirty",
                ...count(
                    groups.filter((group) => group.dirty).length,
                    _t("modified repository"),
                    _t("modified repositories")
                ),
            },
            {
                id: "upgrade",
                ...count(this.codeModules.filter(upgradePending).length, _t("upgrade pending"), _t("upgrades pending")),
            },
        ];
    }

    /**
     * The groups the tile keeps, each with ``shown``, its modules left:
     * « repos » keeps the repositories without their modules, « dirty »
     * the modified ones, « upgrade » the modules to upgrade.
     */
    get shownGroups() {
        const tile = this.data.codeTile;
        const shown = [];
        for (const group of this.groups) {
            if ((tile === "repos" && !group.key) || (tile === "dirty" && !group.dirty)) {
                continue;
            }
            const modules = tile === "upgrade" ? group.modules.filter(upgradePending) : group.modules;
            if (modules.length) {
                shown.push({...group, shown: modules});
            }
        }
        return shown;
    }

    get filterNote() {
        return {
            repos: _t("Filtered: repositories only"),
            dirty: _t("Filtered: modified repositories"),
            upgrade: _t("Filtered: upgrades pending"),
        }[this.data.codeTile];
    }

    pickTile(tile) {
        this.data.codeTile = tile === this.data.codeTile ? "all" : tile;
    }

    showAll() {
        this.data.codeTile = "all";
    }

    modulesHeading(group) {
        const shown = group.shown.length;
        const total = group.modules.length;
        return shown === total ? _t("Modules · %s", total) : _t("Modules · %(shown)s of %(total)s", {shown, total});
    }

    repoLabel(group) {
        return group.key ? _t("Repository %s", group.path) : _t("No repository");
    }

    copyLabel(group) {
        return _t("Copy the path %s", group.path);
    }

    aheadLabel(repo) {
        return _t("ahead by %s", repo.ahead);
    }

    behindLabel(repo) {
        return _t("behind by %s", repo.behind);
    }

    stateColor(repo) {
        return STATE_COLORS[repo.state] || "secondary";
    }

    sourceLabel(group) {
        return group.source === "snapshot" ? _t("from the snapshot") : _t("read now");
    }

    /** The state of HEAD against the manifest, when a modified tree hides it. */
    alignmentLabel(repo) {
        return repo.state === "sale" && repo.alignment && repo.alignment !== "sale" ? repo.alignment_label : false;
    }

    async copyPath(group) {
        const text = group.clone || group.path;
        try {
            await browser.navigator.clipboard.writeText(text);
            this.ui.copied = group.key;
            browser.clearTimeout(this.copiedTimer);
            this.copiedTimer = browser.setTimeout(() => {
                this.ui.copied = null;
            }, COPIED_DELAY);
        } catch {
            this.notification.add(text, {title: _t("Copy this path"), type: "warning"});
        }
    }

    // ── details: uncommitted files, commits ─────────────────────────────

    repoDetails(group) {
        return (group.key && this.data.repoDetails[group.key]) || null;
    }

    /** Read the details of the modified repositories and of the open commits. */
    loadMissingDetails() {
        for (const group of this.groups) {
            const wanted = group.key && ((group.repo && group.repo.dirty) || this.data.repoCommitsOpen[group.key]);
            if (wanted && !this.data.repoDetails[group.key]) {
                this.props.loadRepoDetails(group.key, group.repo && group.repo.target);
            }
        }
    }

    dirtyLabel(details) {
        const n = details.dirty_count;
        return n === 1 ? _t("1 uncommitted file") : _t("%s uncommitted files", n);
    }

    /** The changed paths the list leaves out: it holds at most 20 of them. */
    moreLabel(details) {
        return _t("and %s more", details.dirty_count - details.dirty_files.length);
    }

    commitsOpen(group) {
        return Boolean(this.data.repoCommitsOpen[group.key]);
    }

    toggleCommits(group) {
        const open = !this.commitsOpen(group);
        this.data.repoCommitsOpen[group.key] = open;
        if (open && !this.data.repoDetails[group.key]) {
            this.props.loadRepoDetails(group.key, group.repo && group.repo.target);
        }
    }

    commitWhen(commit) {
        return formatRelativeIso(commit.date) || formatIsoDateTime(commit.date);
    }

    commitDate(commit) {
        return formatIsoDateTime(commit.date);
    }

    shortSha(sha) {
        return shortSha(sha);
    }

    // ── modules ─────────────────────────────────────────────────────────

    upgradePending(module) {
        return upgradePending(module);
    }

    moduleColor(name) {
        return name ? moduleColor(name) : 0;
    }

    /** Whether the module filter dims an item of ``modules``. */
    dimmed(modules) {
        return isDimmed(this.devState.moduleFilter, modules);
    }

    groupDimmed(group) {
        return this.dimmed(group.modules.map((module) => module.name));
    }

    /**
     * The directory of ``module`` the row shows: its path in the
     * repository when it is not at the top of the clone under its own
     * name (a sub-directory), the whole path when it is in no repository,
     * else "" (the repository path and the name already say it).
     */
    modulePath(group, module) {
        if (!group.key) {
            return module.path_rel || module.path || "";
        }
        return module.module_rel && module.module_rel !== module.name ? module.module_rel : "";
    }

    pickTitle(module) {
        return this.devState.moduleFilter === module.name
            ? _t("Remove the filter %s", module.name)
            : _t("Filter the panel on %s", module.name);
    }

    /** Filter the panel on ``module``; picking it again clears the filter. */
    pickModule(module) {
        this.props.dev.setModuleFilter(this.devState.moduleFilter === module.name ? null : module.name);
    }

    highlightModule(module) {
        this.props.dev.highlight(moduleHighlightItems(this.props.info, module.name));
    }

    unhighlight() {
        this.props.dev.clearHighlight();
    }

    /** Open the Actions tab on ``module``, to upgrade it there. */
    openUpgrade(module) {
        this.data.upgradeRequest = module.name;
        this.devState.tab = "actions";
    }
}
