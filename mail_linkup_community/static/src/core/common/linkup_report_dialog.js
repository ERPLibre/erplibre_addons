import {Component, useRef, useState} from "@odoo/owl";

import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

import {LinkupErrorAlert} from "@mail_linkup_reflet/core/common/linkup_error_alert";
import {linkupErrorInfo} from "@mail_linkup_reflet/core/common/linkup_errors";
import {linkupReportReasons} from "@mail_linkup_reflet/core/common/linkup_safety";

import {LinkupHelpNow} from "./linkup_help_now";
import {LINKUP_URGENT_REASONS, linkupReasonLabel} from "./linkup_moderation_texts";

/**
 * Report a message or a member (LU-F-114): a reason among those of a
 * member, each one a radio button, the urgent ones marked, and an optional
 * comment, sent to `linkup.report.action_create_report`, which checks
 * again that the member reads what they report. The reported member never
 * learns who reported. The acknowledgement repeats the reason; an urgent
 * report tells the delay of the moderation, and a report of a person in
 * distress shows the help resources at once, as soon as the reason is
 * chosen (LU-F-118).
 *
 * @typedef {Object} Props
 * @property {string} name the name of the reported member
 * @property {number} [messageId] the reported message
 * @property {number} [partnerId] the reported member, when no message is
 * @property {Function} close
 * @extends {Component<Props, Env>}
 */
export class LinkupReportDialog extends Component {
    static template = "mail_linkup_community.LinkupReportDialog";
    static components = {Dialog, LinkupErrorAlert, LinkupHelpNow};
    static props = ["name", "messageId?", "partnerId?", "close"];

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.store = useState(useService("mail.store"));
        this.reasonsRef = useRef("reasons");
        this.state = useState({reason: "", description: "", busy: false, error: null, sent: null});
    }

    get title() {
        return this.props.messageId ? _t("Report this message") : _t("Report %(name)s", {name: this.props.name});
    }

    get question() {
        return this.props.messageId
            ? _t("Why are you reporting this message?")
            : _t("Why are you reporting %(name)s?", {name: this.props.name});
    }

    get reasons() {
        return linkupReportReasons().map(([code, label]) => ({
            code,
            label,
            urgent: LINKUP_URGENT_REASONS.has(code),
        }));
    }

    get anonymityText() {
        return _t("%(name)s will not know who reported this.", {name: this.props.name});
    }

    get isDistress() {
        return (this.state.sent?.reason || this.state.reason) === "distress";
    }

    get urgentText() {
        return _t("Urgent report: the moderators are told at once. It is handled within %(hours)s hours.", {
            hours: this.state.sent?.urgentHours || this.store.linkup_urgent_hours,
        });
    }

    get ackText() {
        return _t("Reason: %(reason)s. %(name)s does not know who reported it.", {
            reason: linkupReasonLabel(this.state.sent.reason),
            name: this.props.name,
        });
    }

    /** @param {string} code */
    choose(code) {
        this.state.reason = code;
        this.state.error = null;
    }

    async send() {
        if (this.state.busy) {
            return;
        }
        if (!this.state.reason) {
            this.state.error = {code: "linkup.validation", field: "reason", message: _t("Choose a reason.")};
            this.reasonsRef.el?.querySelector("input")?.focus();
            return;
        }
        this.state.busy = true;
        this.state.error = null;
        const target = this.props.messageId ? {message_id: this.props.messageId} : {partner_id: this.props.partnerId};
        try {
            const reportId = await this.orm.silent.call("linkup.report", "action_create_report", [], {
                ...target,
                reason: this.state.reason,
                description: this.state.description.trim() || null,
            });
            this.state.sent = {
                reportId,
                reason: this.state.reason,
                urgent: LINKUP_URGENT_REASONS.has(this.state.reason),
                urgentHours: this.store.linkup_urgent_hours,
            };
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.error = info;
        } finally {
            this.state.busy = false;
        }
    }
}
