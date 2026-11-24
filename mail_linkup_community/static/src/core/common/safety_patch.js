import {useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";

import {LinkupSafetyActions} from "@mail_linkup_reflet/core/common/linkup_safety";

import {LinkupHelpNow} from "./linkup_help_now";
import {LINKUP_URGENT_REASONS} from "./linkup_moderation_texts";
import {LinkupReportDialog} from "./linkup_report_dialog";

LinkupSafetyActions.components = {...LinkupSafetyActions.components, LinkupHelpNow};

/**
 * The report and the block of a member, completed (LU-F-114, LU-F-118):
 * without a reflection, the panel of a conversation reports the member
 * themself (`LinkupReportDialog`); the form of a card says when a reason
 * is urgent and with which delay, and shows the help resources as soon as
 * a person in distress is chosen, then again in the acknowledgement.
 */
patch(LinkupSafetyActions.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkupStore = useState(useService("mail.store"));
        this.state.sentReason = "";
    },

    get reportMemberLabel() {
        return _t("Report %(name)s", {name: this.props.name});
    },

    get isUrgentReason() {
        return LINKUP_URGENT_REASONS.has(this.state.reason);
    },

    get urgentText() {
        return _t("Urgent: the moderators are told at once. It is handled within %(hours)s hours.", {
            hours: this.linkupStore.linkup_urgent_hours,
        });
    },

    openMemberReport() {
        this.dialog.add(LinkupReportDialog, {partnerId: this.props.partnerId, name: this.props.name});
    },

    async sendReport() {
        const reason = this.state.reason;
        await super.sendReport(...arguments);
        if (this.state.reported) {
            this.state.sentReason = reason;
        }
    },
});
