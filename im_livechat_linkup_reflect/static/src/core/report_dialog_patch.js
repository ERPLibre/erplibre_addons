import {useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

import {LinkupReportDialog} from "@mail_linkup_community/core/common/linkup_report_dialog";

/**
 * A report of distress opens, on the server, a conversation with an
 * available moderator in no conflict of interest (LU-F-126 RM1, RM2): the
 * acknowledgement reads `linkup.report.linkup_distress_info` and opens that
 * conversation, or says that no person of the moderation is available and
 * that the urgent report waits, the help resources being shown already
 * (RM3, Q-44).
 */
patch(LinkupReportDialog.prototype, {
    setup() {
        super.setup(...arguments);
        this.linkupDistress = useState({info: null});
    },

    async send() {
        await super.send(...arguments);
        const sent = this.state.sent;
        if (sent?.reason === "distress" && sent.reportId) {
            await this.linkupLoadDistress(sent.reportId);
        }
    },

    /** @param {number} reportId */
    async linkupLoadDistress(reportId) {
        let info;
        try {
            info = await this.orm.silent.call("linkup.report", "linkup_distress_info", [reportId]);
        } catch {
            return;
        }
        this.linkupDistress.info = info;
        if (info.channel_id) {
            await this.linkupOpenConversation();
        }
    },

    get linkupDistressText() {
        const info = this.linkupDistress.info;
        if (!info) {
            return "";
        }
        return info.channel_id
            ? _t("A person of the moderation joins you in a conversation.")
            : _t(
                  "No person of the moderation is available right now. Your report waits in the queue, processed within %(hours)s hours.",
                  {hours: info.urgent_hours}
              );
    },

    async linkupOpenConversation() {
        const id = this.linkupDistress.info?.channel_id;
        if (!id) {
            return;
        }
        const thread = await this.store.Thread.getOrFetch({model: "discuss.channel", id});
        thread?.open();
    },
});
