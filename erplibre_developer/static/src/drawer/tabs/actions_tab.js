/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import {Component, onWillUnmount, useEffect, useRef, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {deserializeDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {
    Commits,
    MODEL,
    formatRelativeServerDateTime,
    formatServerDateTime,
    isDimmed,
    moduleColor,
    moduleHighlightItems,
} from "../common";

// The line the Odoo configuration file needs for the server actions, in
// its [options] section.
export const SERVER_ACTIONS_OPTION = "erplibre_info_allow_server_actions = True";

// How long the copy button of the option shows « Copied », in milliseconds.
const COPIED_DELAY = 2000;

/**
 * The three conditions of the server actions (``info.server_actions_checks``):
 * {flag, group, debug, problem}. A payload without them derives the flag
 * from ``server_actions_allowed``; the panel only opens for a Settings
 * administrator in developer mode, so the other two hold.
 */
export function serverActionsChecks(info) {
    const checks = info && info.server_actions_checks;
    if (checks) {
        return checks;
    }
    const allowed = Boolean(info && info.server_actions_allowed);
    return {flag: allowed, group: true, debug: true, problem: false};
}

/**
 * Whether ``module`` waits for an upgrade: its version on disk differs from
 * the installed one (``info.module_versions``, rule of the snapshots).
 */
export function upgradePending(info, module) {
    const versions = info && info.module_versions && info.module_versions[module];
    return Boolean(versions && versions.pending);
}

/**
 * « Dev actions »: the prerequisites of the server actions, the modules of
 * the page split into « To upgrade » (a newer version on disk, checked at
 * first) and the others, each with a checkbox, its versions and its recent
 * commits, then the action bar and the recent runs.
 *
 * The checked modules live in ``data.upgradeChecked`` ({module: bool}, null
 * until a box changes: the pending ones count as checked), so a switch of
 * tab keeps them. « Upgrade N modules » opens the erplibre_info
 * confirmation (``action_upgrade_modules``), which asks for a checkbox and
 * the database name before it restarts the server. While a prerequisite
 * fails, the boxes and that button are disabled with the reason.
 *
 * The module filter dims the rows of the other modules: a checked module
 * stays visible, and the bar counts the checked ones the filter dims. The
 * module the Code tab sends (``data.upgradeRequest``) gets checked, scrolls
 * into view and takes the focus. ``loadCommits(module)`` fills
 * ``data.commits[module]``; the drawer loads ``data.runs`` when the tab
 * shows.
 */
export class ActionsTab extends Component {
    static template = "erplibre_developer.ActionsTab";
    static components = {Commits};
    static props = {
        info: Object,
        data: Object,
        dev: Object,
        loadCommits: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.devState = useState(this.props.dev.state);
        // ``copied``: the copy button of the option shows « Copied »;
        // ``assetsDone``: the asset bundles were deleted.
        this.ui = useState({copied: false, assetsDone: false});
        this.copiedTimer = null;
        onWillUnmount(() => browser.clearTimeout(this.copiedTimer));
        this.rootRef = useRef("root");
        useEffect(
            (module) => {
                if (!module || !this.rootRef.el) {
                    return;
                }
                this.data.upgradeRequest = null;
                if (this.info.modules.includes(module)) {
                    this.setChecked(module, true);
                }
                const row = this.rootRef.el.querySelector(
                    `.o_erplibre_dev_action_row[data-module="${CSS.escape(module)}"]`
                );
                if (!row) {
                    return;
                }
                if (row.scrollIntoView) {
                    row.scrollIntoView({block: "nearest"});
                }
                const box = row.querySelector(".o_erplibre_dev_upgrade_check:not(:disabled)");
                if (box) {
                    box.focus();
                }
            },
            () => [this.data.upgradeRequest]
        );
    }

    get info() {
        return this.props.info;
    }

    get data() {
        return this.props.data;
    }

    // ── prerequisites ───────────────────────────────────────────────────

    get checks() {
        return serverActionsChecks(this.info);
    }

    /** The upgrade can run: every condition holds. */
    get allowed() {
        const checks = this.checks;
        return Boolean(checks.flag && checks.group && checks.debug);
    }

    /** The checklist: [{id, ok, label, state}], each said in words. */
    get prerequisites() {
        const checks = this.checks;
        return [
            {
                id: "flag",
                ok: Boolean(checks.flag),
                label: _t("Option in the Odoo configuration"),
                code: SERVER_ACTIONS_OPTION,
                state: checks.flag ? _t("enabled") : _t("disabled"),
            },
            {
                id: "group",
                ok: Boolean(checks.group),
                label: _t("Settings group"),
                state: checks.group ? _t("member") : _t("not a member"),
            },
            {
                id: "debug",
                ok: Boolean(checks.debug),
                label: _t("Developer mode"),
                state: checks.debug ? _t("active") : _t("inactive"),
            },
        ];
    }

    get missingCount() {
        return this.prerequisites.filter((item) => !item.ok).length;
    }

    get prerequisitesBadge() {
        const n = this.missingCount;
        if (!n) {
            return _t("Ready");
        }
        return n === 1 ? _t("1 prerequisite missing") : _t("%s prerequisites missing", n);
    }

    /** Why the upgrade is disabled, "" when it is not. */
    get lockReason() {
        const checks = this.checks;
        if (!checks.flag) {
            return _t("Unavailable: the option erplibre_info_allow_server_actions is not enabled in the Odoo configuration.");
        }
        if (!this.allowed) {
            return checks.problem || _t("Unavailable: a prerequisite is missing.");
        }
        return "";
    }

    get optionText() {
        return `[options]\n${SERVER_ACTIONS_OPTION}`;
    }

    async copyOption() {
        try {
            await browser.navigator.clipboard.writeText(SERVER_ACTIONS_OPTION);
            this.ui.copied = true;
            browser.clearTimeout(this.copiedTimer);
            this.copiedTimer = browser.setTimeout(() => {
                this.ui.copied = false;
            }, COPIED_DELAY);
        } catch {
            this.notification.add(SERVER_ACTIONS_OPTION, {title: _t("Copy this line"), type: "warning"});
        }
    }

    // ── modules ─────────────────────────────────────────────────────────

    /** {installed, code, pending} of ``module``, or null when not known. */
    versions(module) {
        return (this.info.module_versions && this.info.module_versions[module]) || null;
    }

    upgradePending(module) {
        return upgradePending(this.info, module);
    }

    get upgradeModules() {
        return this.info.modules.filter((module) => this.upgradePending(module));
    }

    get otherModules() {
        return this.info.modules.filter((module) => !this.upgradePending(module));
    }

    /** The two lists of modules: « upgrade » (pending) and « others ». */
    get sections() {
        return [
            {id: "upgrade", modules: this.upgradeModules},
            {id: "others", modules: this.otherModules},
        ];
    }

    isChecked(module) {
        const checked = this.data.upgradeChecked;
        return checked ? Boolean(checked[module]) : this.upgradePending(module);
    }

    /** Check or uncheck ``module``; the first change copies the defaults. */
    setChecked(module, value) {
        if (!this.data.upgradeChecked) {
            this.data.upgradeChecked = Object.fromEntries(this.upgradeModules.map((name) => [name, true]));
        }
        this.data.upgradeChecked[module] = value;
    }

    toggleChecked(module, ev) {
        this.setChecked(module, ev.target.checked);
    }

    get checkedModules() {
        return this.info.modules.filter((module) => this.isChecked(module));
    }

    checkTitle(module) {
        return this.lockReason || _t("Mark %s for the upgrade", module);
    }

    moduleColor(module) {
        return moduleColor(module);
    }

    /** Whether the module filter dims an item of ``modules``. */
    dimmed(modules) {
        return isDimmed(this.devState.moduleFilter, modules);
    }

    highlightModule(module) {
        this.props.dev.highlight(moduleHighlightItems(this.info, module));
    }

    unhighlight() {
        this.props.dev.clearHighlight();
    }

    // ── recent commits of a module ──────────────────────────────────────

    commitsOpen(module) {
        return Boolean(this.data.commitsOpen[module]);
    }

    /** Open or close the commits of ``module``; the first opening reads them. */
    toggleCommits(module) {
        const open = !this.commitsOpen(module);
        this.data.commitsOpen[module] = open;
        if (open && !this.data.commits[module]) {
            this.props.loadCommits(module);
        }
    }

    // ── action bar ──────────────────────────────────────────────────────

    get upgradeLabel() {
        const n = this.checkedModules.length;
        return n === 1 ? _t("Upgrade %s module (-u)", n) : _t("Upgrade %s modules (-u)", n);
    }

    get upgradeDisabled() {
        return !this.allowed || !this.checkedModules.length;
    }

    get upgradeTitle() {
        if (!this.allowed) {
            return this.lockReason;
        }
        if (!this.checkedModules.length) {
            return _t("Check at least one module to upgrade.");
        }
        return _t("Opens the confirmation that marks the checked modules and restarts the Odoo server.");
    }

    get barNote() {
        if (!this.allowed) {
            return _t("Upgrade blocked: see the prerequisites above.");
        }
        if (!this.checkedModules.length) {
            return _t("Check at least one module to upgrade.");
        }
        return _t("The upgrade restarts the whole server: every user is disconnected for a moment.");
    }

    /** The checked modules the module filter dims: they are upgraded too. */
    get dimmedCheckedNote() {
        const n = this.checkedModules.filter((module) => this.dimmed([module])).length;
        if (!n) {
            return "";
        }
        return n === 1
            ? _t("1 checked module is dimmed by the module filter and will be upgraded too.")
            : _t("%s checked modules are dimmed by the module filter and will be upgraded too.", n);
    }

    async upgrade() {
        const modules = this.checkedModules;
        if (!modules.length || !this.allowed) {
            return;
        }
        // The confirmation is a dialog: inspection would catch its clicks.
        this.props.dev.stopInspect();
        const action = await this.orm.call(MODEL, "action_upgrade_modules", [modules]);
        await this.action.doAction(action);
    }

    async reloadAssets() {
        this.ui.assetsDone = false;
        await this.orm.call(MODEL, "action_reload_assets", []);
        this.ui.assetsDone = true;
    }

    reloadPage() {
        browser.location.reload();
    }

    // ── recent runs ─────────────────────────────────────────────────────

    runIcon(run) {
        return (
            {
                done: "fa-check-circle text-success",
                failed: "fa-times-circle text-danger",
                running: "fa-spinner fa-spin text-info",
                queued: "fa-clock-o text-muted",
            }[run.state] || "fa-circle-o text-muted"
        );
    }

    runWhen(run) {
        return formatRelativeServerDateTime(run.date) || formatServerDateTime(run.date);
    }

    runDate(run) {
        return formatServerDateTime(run.date);
    }

    /** The date of ``run`` in ISO 8601, for the ``datetime`` of its time. */
    runIso(run) {
        const date = run.date ? deserializeDateTime(run.date) : null;
        return date && date.isValid ? date.toISO() : false;
    }
}
