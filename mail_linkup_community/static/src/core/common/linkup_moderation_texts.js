import {_t} from "@web/core/l10n/translation";

import {linkupReportReasons} from "@mail_linkup_reflet/core/common/linkup_safety";

/** The reasons the server marks urgent (LU-F-114 RM4). */
export const LINKUP_URGENT_REASONS = new Set(["threat", "minor", "distress"]);

/**
 * The label of a reason of a report, those the server creates included.
 *
 * @param {string} code
 * @returns {string}
 */
export function linkupReasonLabel(code) {
    if (code === "repeated_rejections") {
        return _t("Repeated rejections (automatic signal)");
    }
    const reason = linkupReportReasons().find(([value]) => value === code);
    return reason ? reason[1] : code || "";
}

/**
 * The resources of "Need help now" (LU-F-118 RM2): those an administrator
 * set (`linkup.help_resources`, one per line), otherwise the crisis line
 * and the emergency number of Canada.
 *
 * @param {Object} store the `mail.store` service
 * @returns {string[]}
 */
export function linkupHelpResources(store) {
    const resources = store?.linkup_help_resources || [];
    if (resources.length) {
        return resources;
    }
    return [
        _t("9-8-8: suicide crisis helpline, by phone or text message, at any time (Canada)."),
        _t("9-1-1: emergency services, when a life is in danger."),
    ];
}

/** Where a report of the member stands, as they read it. */
export function linkupProgressLabels() {
    return {
        received: _t("Received"),
        in_review: _t("In review"),
        closed: _t("Processed"),
    };
}

/** What was reported. */
export function linkupSourceLabels() {
    return {
        reflet: _t("Reflection"),
        message: _t("Message"),
        member: _t("Member"),
        auto: _t("Automatic signal"),
    };
}

/** The states of a report in the console. */
export function linkupReportStateLabels() {
    return {
        new: _t("New"),
        in_review: _t("In review"),
        appealed: _t("Appealed"),
        actioned: _t("Actioned"),
        dismissed: _t("Dismissed"),
    };
}

/** The action a decision took on a report. */
export function linkupActionLabels() {
    return {
        none: _t("None"),
        hidden: _t("Content hidden"),
        warning: _t("Warning"),
        suspended: _t("Suspension"),
        banned: _t("Account closed"),
    };
}

/** The decisions a member reads about themself. */
export function linkupNoticeLabels() {
    return {
        hidden: _t("Your content was hidden by the moderation."),
        warning: _t("The moderation sent you a warning."),
        suspended: _t("Your account is suspended: you cannot send anything for now."),
        banned: _t("Your account is closed."),
    };
}

/** Where the appeal of a decision stands. */
export function linkupAppealLabels() {
    return {
        none: "",
        requested: _t("Your appeal is under review."),
        upheld: _t("After your appeal, the decision is upheld."),
        reversed: _t("After your appeal, the decision is reversed."),
    };
}

/** The rows of the audit log, by their action. */
export function linkupAuditActionLabels() {
    return {
        content_read: _t("Read the reported content and its context"),
        take: _t("Took the report"),
        dismiss: _t("Dismissed"),
        hide: _t("Hid the content"),
        warn: _t("Warned"),
        suspend: _t("Suspended"),
        ban: _t("Banned"),
        appeal: _t("Appeal of the member"),
        uphold: _t("Decision upheld"),
        reverse: _t("Decision reversed"),
        update: _t("Changed the processing"),
    };
}
