import {Component, useRef, useState} from "@odoo/owl";

import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";

import {LinkupErrorAlert} from "./linkup_error_alert";
import {linkupErrorInfo} from "./linkup_errors";

/**
 * The reasons a member gives to a report, in their order in the form; the
 * server sets the urgency from the reason.
 *
 * @returns {[string, string][]} code and label of each reason
 */
export function linkupReportReasons() {
    return [
        ["harassment", _t("Harassment")],
        ["hate", _t("Hate speech")],
        ["sexual", _t("Sexual content")],
        ["threat", _t("Threat")],
        ["minor", _t("Minor in danger")],
        ["distress", _t("Person in distress or at risk for themselves")],
        ["spam", _t("Spam")],
        ["impersonation", _t("Impersonation")],
        ["other", _t("Other")],
    ];
}

/**
 * Report and block, for the member who reads a card or a conversation
 * (LU-F-114, LU-F-115).
 *
 * "Report this reflection" opens a short form: a reason and an optional
 * comment, sent to `linkup.report.action_create_report`; the other member
 * never learns who reported. "Block" asks for a confirmation that lists
 * what a block does, then calls `linkup.block.action_block`; the
 * conversation of the pair is then hidden for the member. A member who
 * blocks the other one gets "Unblock" instead. A refusal shows the message
 * of its `linkup_code`.
 *
 * @typedef {Object} Props
 * @property {number} partnerId the partner of the other member
 * @property {string} name the name of the other member
 * @property {number} [refletId] the reflection to report, if any
 * @property {boolean} [blocked] the member blocks the other one
 * @property {Function} [onChange] called after a block or an unblock
 * @extends {Component<Props, Env>}
 */
export class LinkupSafetyActions extends Component {
    static template = "mail_linkup_reflet.LinkupSafetyActions";
    static components = {LinkupErrorAlert};
    static props = ["partnerId", "name", "refletId?", "blocked?", "onChange?"];

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.reasonRef = useRef("reason");
        this.state = useState({
            reportOpen: false,
            reason: "",
            description: "",
            reported: false,
            busy: false,
            error: null,
        });
    }

    get reasons() {
        return linkupReportReasons();
    }

    get blockLabel() {
        return _t("Block %(name)s", {name: this.props.name});
    }

    get unblockLabel() {
        return _t("Unblock %(name)s", {name: this.props.name});
    }

    get anonymityText() {
        return _t("%(name)s will not know who reported this reflection.", {name: this.props.name});
    }

    get formId() {
        return `o-linkup-Safety-${this.props.refletId || this.props.partnerId}`;
    }

    /**
     * Run a call, keeping the message of a refusal.
     *
     * @param {() => Promise<any>} callback
     * @returns {Promise<boolean>} whether the call succeeded
     */
    async run(callback) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        this.state.error = null;
        try {
            await callback();
            return true;
        } catch (error) {
            const info = linkupErrorInfo(error);
            if (!info) {
                throw error;
            }
            this.state.error = info;
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    openReport() {
        Object.assign(this.state, {
            reportOpen: true,
            reason: "",
            description: "",
            reported: false,
            error: null,
        });
    }

    closeReport() {
        this.state.reportOpen = false;
        this.state.error = null;
    }

    async sendReport() {
        if (!this.state.reason) {
            this.state.error = {code: "linkup.validation", field: "reason", message: _t("Choose a reason.")};
            this.reasonRef.el?.focus();
            return;
        }
        const done = await this.run(() =>
            this.orm.silent.call("linkup.report", "action_create_report", [], {
                reflet_id: this.props.refletId,
                reason: this.state.reason,
                description: this.state.description.trim() || null,
            })
        );
        if (done) {
            this.state.reportOpen = false;
            this.state.reported = true;
        }
    }

    /** `Escape` closes the form of the report. */
    onKeydown(ev) {
        if (ev.key === "Escape" && this.state.reportOpen) {
            ev.preventDefault();
            ev.stopPropagation();
            this.closeReport();
        }
    }

    askBlock() {
        if (this.state.busy) {
            return;
        }
        const name = this.props.name;
        const body = [
            _t(
                "%(name)s will no longer reach you in any conversation: reflection, message, mention, reaction, call, adding to a group, highlight.",
                {name}
            ),
            _t("You disappear from each other's list."),
            _t("Your conversation is hidden, not deleted."),
            _t("%(name)s is not told: what they send seems to leave, but nothing reaches you.", {name}),
            _t("You can unblock %(name)s from the LinkUp help.", {name}),
        ].join("\n");
        this.dialog.add(ConfirmationDialog, {
            title: _t("Block %(name)s?", {name}),
            body,
            confirmLabel: this.blockLabel,
            confirmClass: "btn-danger o-linkup-BlockDialog-confirm",
            confirm: () => this.block(),
            cancel: () => {},
        });
    }

    async block() {
        const done = await this.run(() =>
            this.orm.silent.call("linkup.block", "action_block", [], {
                partner_id: this.props.partnerId,
            })
        );
        if (done) {
            this.notification.add(_t("%(name)s is blocked. The conversation is hidden.", {name: this.props.name}), {
                type: "success",
            });
            this.props.onChange?.(true);
        }
    }

    async unblock() {
        const done = await this.run(() =>
            this.orm.silent.call("linkup.block", "action_unblock", [], {
                partner_id: this.props.partnerId,
            })
        );
        if (done) {
            this.notification.add(_t("%(name)s is unblocked.", {name: this.props.name}), {type: "success"});
            this.props.onChange?.(false);
        }
    }
}
