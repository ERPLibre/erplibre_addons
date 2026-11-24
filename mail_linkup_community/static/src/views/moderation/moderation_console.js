import {Component, onWillStart, onWillUnmount, useRef, useState} from "@odoo/owl";

import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

import {LinkupErrorAlert} from "@mail_linkup_reflet/core/common/linkup_error_alert";
import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";
import {LinkupGuideButton} from "@mail_linkup_reflet/core/common/linkup_guide";

import {
    linkupActionLabels,
    linkupAuditActionLabels,
    linkupReasonLabel,
    linkupReportStateLabels,
    linkupSourceLabels,
} from "../../core/common/linkup_moderation_texts";

/** The decisions of the console, in their order on the screen. */
const DECISIONS = ["dismiss", "hide", "warn", "suspend", "ban"];

/**
 * The console of the moderation (client action `linkup.moderation`,
 * LU-F-116), for the moderators.
 *
 * The queue (`linkup.report.linkup_moderation_queue`) lists the reports to
 * process, urgent first, then by date, with their due date; the counters
 * above it (LU-NF-042) give the reports open, urgent and late. The server
 * leaves out every report in a conflict of interest with the moderator.
 *
 * A report opens on what the moderator needs to decide, without its
 * content: the reason, the comment of the reporter, the counters of the
 * history of the member and the audit log. "Show the content" reads the
 * reported content and its immediate context
 * (`linkup_moderation_content`), which the server writes to the audit log,
 * visible to the other moderators. "Take" assigns the report; the
 * moderator who took it then dismisses it, hides the content, warns,
 * suspends or bans, always with a reason; a ban asks for a confirmation.
 * An appealed report is upheld or reversed. Every refusal shows the
 * message of its `linkup_code`; a report another moderator just closed
 * reads as such.
 */
export class LinkupModerationConsole extends Component {
    static template = "mail_linkup_community.LinkupModerationConsole";
    static components = {LinkupErrorAlert, LinkupGuideButton};
    static props = ["*"];

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.busService = useService("bus_service");
        this.store = useService("mail.store");
        this.reasonRef = useRef("reason");
        this.state = useState({
            loaded: false,
            loadError: false,
            scope: "open",
            rows: [],
            summary: {open: 0, urgent: 0, overdue: 0, urgent_hours: 24},
            detail: null,
            content: null,
            reason: "",
            days: 7,
            busy: false,
            error: null,
        });
        this.onUrgent = () => this.loadQueue();
        this.busService.subscribe("linkup.moderation/urgent", this.onUrgent);
        onWillUnmount(() => this.busService.unsubscribe("linkup.moderation/urgent", this.onUrgent));
        onWillStart(() => this.loadQueue());
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    /**
     * Run a call of the console, showing its refusal.
     *
     * @param {Function} call
     * @returns {Promise<any>} the result, or `null` after a refusal
     */
    async run(call) {
        if (this.state.busy) {
            return null;
        }
        this.state.busy = true;
        this.state.error = null;
        try {
            return await call();
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            if (info.code === "linkup.unavailable") {
                info.message = _t("This report is not in your queue.");
            } else if (info.code === "linkup.already_answered") {
                info.message = error.data?.message || _t("Another moderator just processed this report.");
            }
            this.state.error = info;
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    async loadQueue() {
        try {
            const result = await this.orm.silent.call("linkup.report", "linkup_moderation_queue", [], {
                scope: this.state.scope,
            });
            this.state.rows = result.rows;
            this.state.summary = result.summary;
            this.store.linkup_moderation_urgent = result.summary.urgent;
            this.state.loaded = true;
            this.state.loadError = false;
        } catch {
            this.state.loadError = true;
        }
    }

    /** @param {"open"|"closed"} scope */
    async setScope(scope) {
        if (this.state.scope === scope) {
            return;
        }
        this.state.scope = scope;
        await this.loadQueue();
    }

    /** @param {number} reportId */
    async open(reportId) {
        const detail = await this.run(() =>
            this.orm.silent.call("linkup.report", "linkup_moderation_detail", [reportId])
        );
        if (detail) {
            this.showDetail(detail);
            this.state.content = null;
        }
    }

    /** @param {Object} detail */
    showDetail(detail) {
        this.state.detail = detail;
        this.state.reason = "";
        this.state.days = detail.suspension_days || 7;
    }

    async back() {
        this.state.detail = null;
        this.state.content = null;
        this.state.error = null;
        await this.loadQueue();
    }

    async showContent() {
        const detail = this.state.detail;
        const content = await this.run(() =>
            this.orm.silent.call("linkup.report", "linkup_moderation_content", [detail.id])
        );
        if (content) {
            this.state.content = content;
            await this.refresh();
        }
    }

    /** Read the open report again, its audit log first. */
    async refresh() {
        const detail = await this.orm.silent.call("linkup.report", "linkup_moderation_detail", [this.state.detail.id]);
        this.state.detail = detail;
    }

    // ------------------------------------------------------------------
    // Decisions
    // ------------------------------------------------------------------

    get canTake() {
        const detail = this.state.detail;
        return detail.state === "new" || (detail.state === "in_review" && !detail.is_mine);
    }

    get canDecide() {
        const detail = this.state.detail;
        return detail.state === "in_review" && detail.is_mine;
    }

    get isAppealed() {
        return this.state.detail.state === "appealed";
    }

    async take() {
        const detail = await this.run(() =>
            this.orm.silent.call("linkup.report", "action_moderation_take", [this.state.detail.id])
        );
        if (detail) {
            this.showDetail(detail);
        }
    }

    /** The decisions offered for the open report. */
    get decisions() {
        const detail = this.state.detail;
        const labels = {
            dismiss: _t("Dismiss"),
            hide: _t("Hide the content"),
            warn: _t("Warn"),
            suspend: _t("Suspend"),
            ban: _t("Ban"),
        };
        return DECISIONS.filter(
            (code) => (code !== "hide" || detail.can_hide) && (code === "dismiss" || code === "hide" || detail.can_ban)
        ).map((code) => ({code, label: labels[code], danger: ["suspend", "ban"].includes(code)}));
    }

    /** Refuse a decision without a reason before calling the server. */
    checkReason() {
        if (this.state.reason.trim()) {
            return true;
        }
        this.state.error = {
            code: "linkup.validation",
            field: "reason",
            message: _t("Give the reason of the decision: it goes to the audit log."),
        };
        this.reasonRef.el?.focus();
        return false;
    }

    /** @param {string} decision */
    decide(decision) {
        if (this.state.busy || !this.checkReason()) {
            return;
        }
        if (decision === "ban") {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Ban %(name)s?", {name: this.state.detail.member}),
                body: _t(
                    "The account is closed and its address can no longer open an account for 24 months. The person is told by email, with the recourse."
                ),
                confirmLabel: _t("Ban"),
                confirmClass: "btn-danger o-linkup-Moderation-banConfirm",
                confirm: () => this.sendDecision(decision),
                cancel: () => {},
            });
            return;
        }
        return this.sendDecision(decision);
    }

    /** @param {string} decision */
    async sendDecision(decision) {
        const detail = await this.run(() =>
            this.orm.silent.call("linkup.report", "action_moderation_decide", [this.state.detail.id, decision], {
                reason: this.state.reason,
                days: decision === "suspend" ? Number(this.state.days) : null,
            })
        );
        if (detail) {
            this.showDetail(detail);
        }
    }

    /** @param {boolean} uphold */
    async resolveAppeal(uphold) {
        if (this.state.busy || !this.checkReason()) {
            return;
        }
        const detail = await this.run(() =>
            this.orm.silent.call("linkup.report", "action_moderation_resolve_appeal", [this.state.detail.id, uphold], {
                reason: this.state.reason,
            })
        );
        if (detail) {
            this.showDetail(detail);
        }
    }

    // ------------------------------------------------------------------
    // Texts
    // ------------------------------------------------------------------

    /** @param {string|false} value */
    formatDate(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : "";
    }

    /** @param {string} code */
    reasonLabel(code) {
        return linkupReasonLabel(code);
    }

    /** @param {string} code */
    sourceLabel(code) {
        return linkupSourceLabels()[code] || code;
    }

    /** @param {string} code */
    stateLabel(code) {
        return linkupReportStateLabels()[code] || code;
    }

    /** @param {string} code */
    actionLabel(code) {
        return linkupActionLabels()[code] || code;
    }

    /** @param {string} code */
    auditLabel(code) {
        return linkupAuditActionLabels()[code] || code;
    }

    /** @param {Object} row */
    openLabel(row) {
        return _t("Open the report: %(reason)s, %(member)s", {
            reason: this.reasonLabel(row.reason),
            member: row.member || this.sourceLabel(row.source),
        });
    }

    /** The steps of the open report, the current one marked. */
    get steps() {
        const state = this.state.detail.state;
        const last = state === "dismissed" ? "dismissed" : "actioned";
        const codes = state === "appealed" ? ["new", "in_review", "appealed"] : ["new", "in_review", last];
        return codes.map((code) => ({code, label: this.stateLabel(code), current: code === state}));
    }

    get summaryText() {
        const {open, urgent, overdue} = this.state.summary;
        return _t("%(open)s to process · %(urgent)s urgent · %(overdue)s late", {open, urgent, overdue});
    }

    get urgentDelayText() {
        return _t("Members are told that an urgent report is handled within %(hours)s hours.", {
            hours: this.state.summary.urgent_hours,
        });
    }

    get historyText() {
        const history = this.state.detail.history || {};
        if (!history.reports) {
            return _t("No earlier report.");
        }
        return _t(
            "%(reports)s earlier reports, %(open)s open; %(warnings)s warnings, %(hidden)s contents hidden, %(suspensions)s suspensions.",
            history
        );
    }

    get decisionNote() {
        const detail = this.state.detail;
        if (detail.state === "dismissed") {
            return _t("Report dismissed: %(name)s is not sanctioned.", {name: detail.member || "—"});
        }
        if (detail.state === "actioned") {
            return _t("%(name)s is told of the decision (%(decision)s) and of the possible appeal.", {
                name: detail.member,
                decision: this.actionLabel(detail.action_taken),
            });
        }
        return "";
    }

    get contentNote() {
        const source = this.state.content?.source;
        if (source === "member") {
            return _t("A member is reported: there is no content, only their history.");
        }
        if (source === "auto") {
            return _t("The rejected reflections of the member, without their texts.");
        }
        return "";
    }
}

registry.category("actions").add("linkup.moderation", LinkupModerationConsole);
