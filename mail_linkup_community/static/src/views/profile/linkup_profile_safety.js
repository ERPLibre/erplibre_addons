import {Component, onMounted, useState} from "@odoo/owl";

import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

import {LinkupErrorAlert} from "@mail_linkup_reflet/core/common/linkup_error_alert";
import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";

import {
    linkupAppealLabels,
    linkupNoticeLabels,
    linkupProgressLabels,
    linkupReasonLabel,
    linkupSourceLabels,
} from "../../core/common/linkup_moderation_texts";

/**
 * The safety of the member in their profile (LU-F-114 to LU-F-116):
 *
 * - the decisions of the moderation about them (`linkup.moderation.notice`),
 *   each with its reason and, while allowed, "Contest" and a short text
 *   (`action_appeal`); opening the profile marks them read;
 * - the reports they made, with where each one stands, never the decision
 *   taken about another member;
 * - the members they block, each with "Unblock" (LU-F-115 RM3).
 *
 * The lists come with `res.users.linkup_profile_info`; the server checks
 * every action again.
 *
 * @typedef {Object} Props
 * @property {Object} profile as `linkup_profile_info` gives it
 * @extends {Component<Props, Env>}
 */
export class LinkupProfileSafety extends Component {
    static template = "mail_linkup_community.LinkupProfileSafety";
    static components = {LinkupErrorAlert};
    static props = ["profile"];

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.store = useState(useService("mail.store"));
        this.state = useState({
            notices: this.props.profile.notices || [],
            reports: this.props.profile.reports || [],
            blocked: this.props.profile.blocked || [],
            appealFor: null,
            appealText: "",
            busy: false,
            error: null,
            notice: "",
        });
        onMounted(() => this.markSeen());
    }

    async markSeen() {
        if (!this.state.notices.some((notice) => !notice.seen)) {
            return;
        }
        await this.orm.silent.call("linkup.moderation.notice", "action_mark_seen", []);
        this.store.linkup_notice_unseen = 0;
    }

    /** @param {string|false} value */
    formatDate(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : "";
    }

    /** @param {Object} notice */
    noticeText(notice) {
        return linkupNoticeLabels()[notice.decision] || "";
    }

    /** @param {Object} notice */
    noticeDetail(notice) {
        const parts = [
            _t("On %(date)s, reason: %(reason)s.", {
                date: this.formatDate(notice.date),
                reason: linkupReasonLabel(notice.reason),
            }),
        ];
        if (notice.decision === "suspended" && notice.suspended_until) {
            parts.push(_t("Until %(date)s.", {date: this.formatDate(notice.suspended_until)}));
        }
        return parts.join(" ");
    }

    /** @param {Object} notice */
    appealText(notice) {
        return linkupAppealLabels()[notice.appeal_state] || "";
    }

    /** @param {Object} report */
    reportText(report) {
        const source = linkupSourceLabels()[report.source] || "";
        return _t("%(date)s · %(reason)s · %(source)s: %(member)s", {
            date: this.formatDate(report.date),
            reason: linkupReasonLabel(report.reason),
            source,
            member: report.member,
        });
    }

    /** @param {Object} report */
    progressText(report) {
        return linkupProgressLabels()[report.progress] || "";
    }

    /** @param {{name: string}} member */
    unblockLabel(member) {
        return _t("Unblock %(name)s", {name: member.name});
    }

    /** @param {Function} call */
    async run(call, notice) {
        if (this.state.busy) {
            return null;
        }
        this.state.busy = true;
        this.state.error = null;
        this.state.notice = "";
        try {
            const result = await call();
            this.state.notice = notice;
            return result;
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.error = info;
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    /** @param {Object} notice */
    openAppeal(notice) {
        this.state.appealFor = notice.id;
        this.state.appealText = "";
        this.state.error = null;
    }

    cancelAppeal() {
        this.state.appealFor = null;
    }

    /** @param {Object} notice */
    async sendAppeal(notice) {
        const info = await this.run(
            () =>
                this.orm.silent.call("linkup.moderation.notice", "action_appeal", [[notice.id]], {
                    text: this.state.appealText,
                }),
            _t("Your appeal is sent: another moderator reviews the decision.")
        );
        if (info) {
            Object.assign(notice, info);
            this.state.appealFor = null;
        }
    }

    /** @param {{user_id: number}} member */
    async unblock(member) {
        const blocked = await this.run(async () => {
            await this.orm.silent.call("linkup.block", "action_unblock", [], {user_id: member.user_id});
            return this.orm.silent.call("linkup.block", "linkup_blocked_members", []);
        }, _t("%(name)s is unblocked.", {name: member.name}));
        if (blocked) {
            this.state.blocked = blocked;
        }
    }
}
